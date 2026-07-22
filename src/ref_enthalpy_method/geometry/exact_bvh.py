"""Deterministic array-based AABB BVH accelerator for exact point-to-triangle projection.

Builds a median-split BVH over triangle 3D AABBs. Queries use a depth-first
stack-based traversal with conservative pruning that preserves the original
tie-break contract (smallest triangle index among equivalent distances).

The module provides:

- ``ExactBvh``: frozen dataclass holding contiguous node arrays
- ``build_exact_bvh(triangles, leaf_size) -> ExactBvh``: deterministic builder
- ``project_points_bvh(points, triangles, *, bvh=None) -> SurfaceProjection``:
  accelerated projection with diagnostic counters and brute-force fallback
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ref_enthalpy_method.geometry.exact_projection import (
    SurfaceProjection,
    TriangleProjection,
    _distances_equivalent,
    closest_point_on_triangle,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_LEAF_SIZE = 16

# Node type tags
_NODE_INTERNAL = np.int8(0)
_NODE_LEAF = np.int8(1)


# ---------------------------------------------------------------------------
# BVH data structure (array-based, contiguous)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExactBvh:
    """Deterministic array-based AABB BVH over triangle soup.

    All node data lives in contiguous numpy arrays — no Python objects per
    node. This eliminates per-node allocation overhead during queries.
    """

    # Node arrays (all indexed by node_id)
    node_type: np.ndarray           # (N_nodes,) int8
    node_aabb_min: np.ndarray       # (N_nodes, 3) float64
    node_aabb_max: np.ndarray       # (N_nodes, 3) float64
    node_min_tri_idx: np.ndarray    # (N_nodes,) int64 — smallest triangle index in subtree
    node_left: np.ndarray           # (N_nodes,) int32 — left child (internal only)
    node_right: np.ndarray          # (N_nodes,) int32 — right child (internal only)
    node_tri_start: np.ndarray      # (N_nodes,) int64 — start in leaf_tri_indices (leaf only)
    node_tri_count: np.ndarray      # (N_nodes,) int32 — count (leaf only)

    # Leaf triangle index pool
    leaf_tri_indices: np.ndarray    # (M,) int64 — triangle indices grouped by leaf

    # Precomputed per-triangle AABBs
    tri_aabb_min: np.ndarray        # (M, 3) float64
    tri_aabb_max: np.ndarray        # (M, 3) float64

    # Mesh metadata
    triangle_count: int

    # Build-time leaf_size
    leaf_size: int


# ---------------------------------------------------------------------------
# AABB lower-bound (vectorized)
# ---------------------------------------------------------------------------


def _squared_lower_bound_batch(
    point: np.ndarray,               # (3,) float64
    aabb_min: np.ndarray,            # (K, 3) float64
    aabb_max: np.ndarray,            # (K, 3) float64
) -> np.ndarray:                     # (K,) float64
    """Vectorized squared distance from *point* to K AABBs."""
    p = point.reshape(1, 3)
    lo = aabb_min
    hi = aabb_max
    d = np.zeros(lo.shape[0], dtype=np.float64)
    for axis in range(3):
        pv = float(p[0, axis])
        lv = lo[:, axis]
        hv = hi[:, axis]
        below = pv < lv
        above = pv > hv
        d[below] += (lv[below] - pv) ** 2
        d[above] += (pv - hv[above]) ** 2
    return d


def _squared_distance_point_aabb(
    point: np.ndarray,
    aabb_min: np.ndarray,
    aabb_max: np.ndarray,
) -> float:
    """Scalar squared distance from point to one AABB."""
    p = point.ravel()
    lo = aabb_min.ravel()
    hi = aabb_max.ravel()
    d = 0.0
    for axis in range(3):
        pv = float(p[axis])
        lv = float(lo[axis])
        hv = float(hi[axis])
        if pv < lv:
            d += (lv - pv) ** 2
        elif pv > hv:
            d += (pv - hv) ** 2
    return d


# ---------------------------------------------------------------------------
# Deterministic builder
# ---------------------------------------------------------------------------


def build_exact_bvh(
    triangles: np.ndarray,
    *,
    leaf_size: int = _DEFAULT_LEAF_SIZE,
) -> ExactBvh:
    """Build a deterministic median-split array-based BVH.

    Parameters
    ----------
    triangles : (M, 3, 3) float64
    leaf_size : int
        Maximum triangles per leaf.

    Returns
    -------
    ExactBvh
    """
    tris = np.asarray(triangles, dtype=np.float64)
    if tris.ndim != 3 or tris.shape[1:] != (3, 3):
        raise ValueError(f"triangles must have shape (M, 3, 3), got {tris.shape}")
    M = tris.shape[0]
    if M == 0:
        raise ValueError("triangles must contain at least one triangle")
    if not np.all(np.isfinite(tris)):
        raise ValueError("triangles must contain only finite values")

    # Precompute per-triangle AABBs and centroids
    tri_aabb_min = tris.min(axis=1).astype(np.float64, copy=False)  # (M, 3)
    tri_aabb_max = tris.max(axis=1).astype(np.float64, copy=False)  # (M, 3)
    tri_centroids = 0.5 * (tri_aabb_min + tri_aabb_max)

    leaf_sz = max(1, int(leaf_size))
    tri_indices = np.arange(M, dtype=np.int64)

    # Accumulate nodes during build
    build_state = _BuildState()

    _build_recursive_array(
        state=build_state,
        tri_indices=tri_indices,
        tri_aabb_min=tri_aabb_min,
        tri_aabb_max=tri_aabb_max,
        tri_centroids=tri_centroids,
        leaf_size=leaf_sz,
    )

    return build_state._finalize(
        tri_aabb_min=tri_aabb_min,
        tri_aabb_max=tri_aabb_max,
        triangle_count=M,
        leaf_size=leaf_sz,
    )


class _BuildState:
    """Mutable accumulator during BVH build."""

    def __init__(self) -> None:
        self.node_types: list[int] = []
        self.node_aabb_mins: list[np.ndarray] = []
        self.node_aabb_maxs: list[np.ndarray] = []
        self.node_min_tri_idxs: list[int] = []
        self.node_lefts: list[int] = []
        self.node_rights: list[int] = []
        self.node_tri_starts: list[int] = []
        self.node_tri_counts: list[int] = []
        self.leaf_tri_indices: list[int] = []

    def add_internal(
        self,
        aabb_min: np.ndarray,
        aabb_max: np.ndarray,
        min_tri_idx: int,
        left_id: int,
        right_id: int,
    ) -> int:
        idx = len(self.node_types)
        self.node_types.append(int(_NODE_INTERNAL))
        self.node_aabb_mins.append(aabb_min.copy())
        self.node_aabb_maxs.append(aabb_max.copy())
        self.node_min_tri_idxs.append(min_tri_idx)
        self.node_lefts.append(left_id)
        self.node_rights.append(right_id)
        self.node_tri_starts.append(0)
        self.node_tri_counts.append(0)
        return idx

    def add_leaf(
        self,
        aabb_min: np.ndarray,
        aabb_max: np.ndarray,
        min_tri_idx: int,
        tri_indices: np.ndarray,
    ) -> int:
        idx = len(self.node_types)
        start = len(self.leaf_tri_indices)
        cnt = int(tri_indices.shape[0])
        self.node_types.append(int(_NODE_LEAF))
        self.node_aabb_mins.append(aabb_min.copy())
        self.node_aabb_maxs.append(aabb_max.copy())
        self.node_min_tri_idxs.append(min_tri_idx)
        self.node_lefts.append(-1)
        self.node_rights.append(-1)
        self.node_tri_starts.append(start)
        self.node_tri_counts.append(cnt)
        self.leaf_tri_indices.extend(int(v) for v in tri_indices.ravel())
        return idx

    def _finalize(
        self,
        *,
        tri_aabb_min: np.ndarray,
        tri_aabb_max: np.ndarray,
        triangle_count: int,
        leaf_size: int,
    ) -> ExactBvh:
        return ExactBvh(
            node_type=np.array(self.node_types, dtype=np.int8),
            node_aabb_min=np.array(self.node_aabb_mins, dtype=np.float64),
            node_aabb_max=np.array(self.node_aabb_maxs, dtype=np.float64),
            node_min_tri_idx=np.array(self.node_min_tri_idxs, dtype=np.int64),
            node_left=np.array(self.node_lefts, dtype=np.int32),
            node_right=np.array(self.node_rights, dtype=np.int32),
            node_tri_start=np.array(self.node_tri_starts, dtype=np.int64),
            node_tri_count=np.array(self.node_tri_counts, dtype=np.int32),
            leaf_tri_indices=np.array(self.leaf_tri_indices, dtype=np.int64),
            tri_aabb_min=np.ascontiguousarray(tri_aabb_min, dtype=np.float64),
            tri_aabb_max=np.ascontiguousarray(tri_aabb_max, dtype=np.float64),
            triangle_count=int(triangle_count),
            leaf_size=int(leaf_size),
        )


def _build_recursive_array(
    *,
    state: _BuildState,
    tri_indices: np.ndarray,
    tri_aabb_min: np.ndarray,
    tri_aabb_max: np.ndarray,
    tri_centroids: np.ndarray,
    leaf_size: int,
) -> int:
    """Recursively build and return the node index."""
    idx_arr = tri_indices
    n = idx_arr.shape[0]

    # Node AABB
    node_min = tri_aabb_min[idx_arr].min(axis=0)
    node_max = tri_aabb_max[idx_arr].max(axis=0)

    # Smallest triangle index in this subtree
    min_tri_idx = int(idx_arr.min())

    if n <= leaf_size:
        return state.add_leaf(node_min, node_max, min_tri_idx, idx_arr)

    # Split along longest axis
    extents = node_max - node_min
    split_axis = int(np.argmax(extents))

    c = tri_centroids[idx_arr, split_axis]
    other_axes = [a for a in (0, 1, 2) if a != split_axis]
    order = np.lexsort(
        (
            tri_centroids[idx_arr, other_axes[1]],
            tri_centroids[idx_arr, other_axes[0]],
            c,
        )
    )
    sorted_indices = idx_arr[order]

    mid = n // 2
    left_id = _build_recursive_array(
        state=state,
        tri_indices=sorted_indices[:mid],
        tri_aabb_min=tri_aabb_min,
        tri_aabb_max=tri_aabb_max,
        tri_centroids=tri_centroids,
        leaf_size=leaf_size,
    )
    right_id = _build_recursive_array(
        state=state,
        tri_indices=sorted_indices[mid:],
        tri_aabb_min=tri_aabb_min,
        tri_aabb_max=tri_aabb_max,
        tri_centroids=tri_centroids,
        leaf_size=leaf_size,
    )

    return state.add_internal(node_min, node_max, min_tri_idx, left_id, right_id)


# ---------------------------------------------------------------------------
# Query with conservative pruning and diagnostics
# ---------------------------------------------------------------------------


@dataclass
class BvhDiagnostics:
    """Per-batch diagnostics counters (NOT per-point — aggregated)."""

    total_node_visits: int = 0
    total_internal_visits: int = 0
    total_leaf_visits: int = 0
    total_triangle_kernel_calls: int = 0
    total_stack_pushes: int = 0
    total_points_with_fallback: int = 0
    tree_depth: int = 0
    leaf_count: int = 0
    avg_leaf_tri_count: float = 0.0
    point_node_visits: list[int] = field(default_factory=list)
    point_leaf_visits: list[int] = field(default_factory=list)
    point_triangle_kernel_calls: list[int] = field(default_factory=list)
    point_stack_pushes: list[int] = field(default_factory=list)

    @classmethod
    def from_bvh(cls, bvh: ExactBvh) -> BvhDiagnostics:
        diag = cls()
        # Compute tree depth and leaf stats
        diag.tree_depth = _compute_tree_depth(bvh)
        leaf_mask = bvh.node_type == _NODE_LEAF
        diag.leaf_count = int(np.count_nonzero(leaf_mask))
        leaf_counts = bvh.node_tri_count[leaf_mask]
        diag.avg_leaf_tri_count = float(leaf_counts.mean()) if diag.leaf_count > 0 else 0.0
        return diag


def _compute_tree_depth(bvh: ExactBvh) -> int:
    """Compute max depth by DFS."""
    max_depth = 0
    # (node_idx, depth) — start from root (last node)
    root_idx = bvh.node_type.shape[0] - 1
    stack: list[tuple[int, int]] = [(root_idx, 0)]
    while stack:
        nid, depth = stack.pop()
        if depth > max_depth:
            max_depth = depth
        if bvh.node_type[nid] == _NODE_INTERNAL:
            left = int(bvh.node_left[nid])
            right = int(bvh.node_right[nid])
            if left >= 0:
                stack.append((left, depth + 1))
            if right >= 0:
                stack.append((right, depth + 1))
    return max_depth


def _query_single_point_bvh_v2(
    point: np.ndarray,
    triangles: np.ndarray,
    bvh: ExactBvh,
    diag: BvhDiagnostics | None = None,
) -> tuple[int, TriangleProjection]:
    """Query the array-based BVH for one point with conservative pruning.

    Pruning rule (preserves original tie-break):
    A node is pruned iff:
      sqrt(lb_sq) > best_dist  AND  NOT _distances_equivalent(sqrt(lb_sq), best_dist)
    OR
      _distances_equivalent(sqrt(lb_sq), best_dist)  AND  node.min_tri_idx >= best_tri
    """
    p = np.asarray(point, dtype=np.float64)

    best_sq_dist = float("inf")
    best_dist = float("inf")
    best_tri_idx = 0
    best_result: TriangleProjection | None = None

    # DFS stack: list of (node_idx, lb_sq)
    # The root is always the last node in the array (built bottom-up)
    root_idx = bvh.node_type.shape[0] - 1
    root_lb = _squared_distance_point_aabb(p, bvh.node_aabb_min[root_idx], bvh.node_aabb_max[root_idx])
    stack: list[tuple[int, float]] = [(root_idx, root_lb)]
    if diag is not None:
        diag.total_stack_pushes += 1

    while stack:
        node_idx, lb_sq = stack.pop()
        if diag is not None:
            diag.total_node_visits += 1

        # --- Pruning decision ---
        if best_result is not None:
            lb_dist = math.sqrt(lb_sq)
            if lb_dist > best_dist and not _distances_equivalent(lb_dist, best_dist):
                # Node is strictly farther (beyond contract tolerance)
                continue

            if _distances_equivalent(lb_dist, best_dist):
                # Distances are equivalent -- check tie-break
                node_min_idx = int(bvh.node_min_tri_idx[node_idx])
                if node_min_idx >= best_tri_idx:
                    # Even the smallest-indexed triangle in this node
                    # cannot beat the current tie-break winner
                    continue

        # --- Process node ---
        ntype = int(bvh.node_type[node_idx])

        if ntype == _NODE_LEAF:
            if diag is not None:
                diag.total_leaf_visits += 1
            start = int(bvh.node_tri_start[node_idx])
            cnt = int(bvh.node_tri_count[node_idx])
            for k in range(cnt):
                tri_idx = int(bvh.leaf_tri_indices[start + k])
                if diag is not None:
                    diag.total_triangle_kernel_calls += 1
                candidate = closest_point_on_triangle(p, triangles[tri_idx])
                cand_dist = candidate.distance

                if best_result is None:
                    # First candidate — accept unconditionally
                    best_sq_dist = cand_dist * cand_dist
                    best_dist = cand_dist
                    best_tri_idx = tri_idx
                    best_result = candidate
                elif cand_dist < best_dist and not _distances_equivalent(cand_dist, best_dist):
                    best_sq_dist = cand_dist * cand_dist
                    best_dist = cand_dist
                    best_tri_idx = tri_idx
                    best_result = candidate
                elif _distances_equivalent(cand_dist, best_dist):
                    # Equivalent distance — keep smallest triangle index
                    if tri_idx < best_tri_idx:
                        best_tri_idx = tri_idx
                        best_result = candidate
        elif ntype == _NODE_INTERNAL:
            if diag is not None:
                diag.total_internal_visits += 1
            left_idx = int(bvh.node_left[node_idx])
            right_idx = int(bvh.node_right[node_idx])

            left_lb = _squared_distance_point_aabb(
                p,
                bvh.node_aabb_min[left_idx],
                bvh.node_aabb_max[left_idx],
            )
            right_lb = _squared_distance_point_aabb(
                p,
                bvh.node_aabb_min[right_idx],
                bvh.node_aabb_max[right_idx],
            )

            # Push farther child first (so closer is popped first)
            if left_lb <= right_lb:
                stack.append((right_idx, right_lb))
                stack.append((left_idx, left_lb))
            else:
                stack.append((left_idx, left_lb))
                stack.append((right_idx, right_lb))
            if diag is not None:
                diag.total_stack_pushes += 2
        else:
            raise RuntimeError(f"Unknown BVH node type {ntype} at index {node_idx}")

    if best_result is None:
        raise RuntimeError("BVH query failed to find any triangle result")

    return best_tri_idx, best_result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def project_points_bvh(
    points: np.ndarray,
    triangles: np.ndarray,
    *,
    bvh: ExactBvh | None = None,
    diagnostics: bool = False,
) -> SurfaceProjection | tuple[SurfaceProjection, BvhDiagnostics]:
    """Project points onto triangles using the BVH accelerator.

    Parameters
    ----------
    points : (N, 3) float64
    triangles : (M, 3, 3) float64
    bvh : ExactBvh | None
        Pre-built or built on the fly.
    diagnostics : bool
        If True, return (SurfaceProjection, BvhDiagnostics).

    Returns
    -------
    SurfaceProjection or (SurfaceProjection, BvhDiagnostics)
    """
    points_array = np.asarray(points, dtype=np.float64)
    triangles_array = np.asarray(triangles, dtype=np.float64)

    if points_array.ndim != 2 or points_array.shape[1:] != (3,):
        raise ValueError(f"points must have shape (N, 3), got {points_array.shape}")
    if triangles_array.ndim != 3 or triangles_array.shape[1:] != (3, 3):
        raise ValueError(f"triangles must have shape (M, 3, 3), got {triangles_array.shape}")
    if triangles_array.shape[0] == 0:
        raise ValueError("triangles must contain at least one triangle")
    if not np.all(np.isfinite(points_array)):
        raise ValueError("points must contain only finite values")
    if not np.all(np.isfinite(triangles_array)):
        raise ValueError("triangles must contain only finite values")

    if bvh is None:
        bvh = build_exact_bvh(triangles_array)
    elif bvh.triangle_count != triangles_array.shape[0]:
        raise ValueError(
            f"BVH was built for {bvh.triangle_count} triangles, "
            f"but mesh has {triangles_array.shape[0]}"
        )

    diag = BvhDiagnostics.from_bvh(bvh) if diagnostics else None

    count = points_array.shape[0]
    triangle_ids = np.empty(count, dtype=np.int64)
    closest_points = np.empty((count, 3), dtype=np.float64)
    distances = np.empty(count, dtype=np.float64)
    raw_normals = np.empty((count, 3), dtype=np.float64)

    for point_id in range(count):
        before_node_visits = diag.total_node_visits if diag is not None else 0
        before_leaf_visits = diag.total_leaf_visits if diag is not None else 0
        before_kernel_calls = (
            diag.total_triangle_kernel_calls if diag is not None else 0
        )
        before_stack_pushes = diag.total_stack_pushes if diag is not None else 0
        try:
            tri_id, result = _query_single_point_bvh_v2(
                points_array[point_id], triangles_array, bvh, diag
            )
            triangle_ids[point_id] = tri_id
            closest_points[point_id] = result.closest_point
            distances[point_id] = result.distance
            raw_normals[point_id] = result.raw_normal
        except RuntimeError:
            # Only RuntimeError triggers fallback (tree inconsistency).
            # ValueError from input validation is NOT fallback-eligible.
            if diag is not None:
                diag.total_points_with_fallback += 1
            from ref_enthalpy_method.geometry.exact_projection import (
                project_points_exact,
            )
            single_result = project_points_exact(
                points_array[point_id:point_id + 1], triangles_array
            )
            triangle_ids[point_id] = single_result.triangle_id[0]
            closest_points[point_id] = single_result.closest_point[0]
            distances[point_id] = single_result.distance[0]
            raw_normals[point_id] = single_result.raw_normal[0]
        if diag is not None:
            diag.point_node_visits.append(
                diag.total_node_visits - before_node_visits
            )
            diag.point_leaf_visits.append(
                diag.total_leaf_visits - before_leaf_visits
            )
            diag.point_triangle_kernel_calls.append(
                diag.total_triangle_kernel_calls - before_kernel_calls
            )
            diag.point_stack_pushes.append(
                diag.total_stack_pushes - before_stack_pushes
            )

    result = SurfaceProjection(
        triangle_id=triangle_ids,
        closest_point=closest_points,
        distance=distances,
        raw_normal=raw_normals,
    )

    if diagnostics:
        return result, diag
    return result