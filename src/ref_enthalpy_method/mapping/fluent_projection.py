"""Exact projection adapter for canonical Fluent surface geometry."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ref_enthalpy_method.geometry.exact_projection import project_points_exact
from ref_enthalpy_method.geometry.exact_bvh import (
    ExactBvh,
    build_exact_bvh,
    project_points_bvh,
)
from ref_enthalpy_method.mapping.fluent_surface import FluentSurfaceGeometry


def _readonly_copy(value: np.ndarray, *, dtype: np.dtype | type) -> np.ndarray:
    result = np.array(value, dtype=dtype, copy=True, order="C")
    result.setflags(write=False)
    return result


def _positive_finite_scalar(value: float, *, name: str) -> float:
    try:
        scalar = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite scalar greater than zero") from error
    if not np.isfinite(scalar) or scalar <= 0.0:
        raise ValueError(f"{name} must be a finite scalar greater than zero")
    return scalar


def _validate_selected_raw_normals(
    triangles: np.ndarray,
    triangle_id: np.ndarray,
    raw_normal: np.ndarray,
) -> None:
    selected = triangles[triangle_id]
    edge_ab = selected[:, 1] - selected[:, 0]
    edge_ac = selected[:, 2] - selected[:, 0]
    normal_norm = np.linalg.norm(np.cross(edge_ab, edge_ac), axis=1)
    scale_squared = np.maximum(
        np.einsum("ij,ij->i", edge_ab, edge_ab),
        np.einsum("ij,ij->i", edge_ac, edge_ac),
    )
    nondegenerate = (scale_squared > 0.0) & (
        normal_norm > np.finfo(np.float64).eps * scale_squared
    )
    if not np.all(np.isfinite(raw_normal[nondegenerate])):
        raise ValueError("kernel raw_normal must be finite for selected nondegenerate triangles")


@dataclass(frozen=True)
class FluentSurfaceProjection:
    """Immutable exact projection in canonical Fluent geometry ordering."""

    canonical_index: np.ndarray
    solver_xyz: np.ndarray
    projected_xyz: np.ndarray
    triangle_id: np.ndarray
    projection_distance_m: np.ndarray
    raw_normal: np.ndarray
    projection_gate_m: float
    projection_gate_pass: np.ndarray
    geometry_source_path: Path
    geometry_source_sha256: str
    canonical_geometry_sha256: str
    triangle_count: int


def project_fluent_surface_exact(
    geometry: FluentSurfaceGeometry,
    triangles: np.ndarray,
    *,
    projection_gate_m: float,
    use_bvh: bool = False,
    bvh: ExactBvh | None = None,
    return_diagnostics: bool = False,
) -> FluentSurfaceProjection | tuple[FluentSurfaceProjection, dict[str, Any]]:
    """Project canonical solver coordinates through the exact kernel.

    Parameters
    ----------
    use_bvh : bool
        When ``True``, accelerate with BVH (same exact results).
        Default ``False`` preserves the original brute-force behavior.
    bvh : ExactBvh | None
        Pre-built BVH for the given *triangles*. Built on the fly if
        ``None`` and *use_bvh* is ``True``.
    return_diagnostics : bool
        If True and use_bvh is True, return (result, diagnostics_dict).
    """
    gate = _positive_finite_scalar(projection_gate_m, name="projection_gate_m")

    canonical_xyz = np.asarray(geometry.canonical_solver_xyz)
    if canonical_xyz.dtype != np.dtype(np.float64):
        raise ValueError(
            f"geometry canonical solver coordinates must have dtype float64, got {canonical_xyz.dtype}"
        )
    if canonical_xyz.ndim != 2 or canonical_xyz.shape[1:] != (3,):
        raise ValueError(
            "geometry canonical solver coordinates must have shape "
            f"(N, 3), got {canonical_xyz.shape}"
        )
    if canonical_xyz.shape[0] == 0:
        raise ValueError("geometry canonical solver coordinates must contain at least one point")
    if not np.all(np.isfinite(canonical_xyz)):
        raise ValueError("geometry canonical solver coordinates must contain only finite values")

    triangle_array = np.asarray(triangles)
    if triangle_array.dtype != np.dtype(np.float64):
        triangle_array = np.asarray(triangles, dtype=np.float64)
    if triangle_array.ndim != 3 or triangle_array.shape[1:] != (3, 3):
        raise ValueError(f"triangles must have shape (M, 3, 3), got {triangle_array.shape}")
    if triangle_array.shape[0] == 0:
        raise ValueError("triangles must contain at least one triangle")
    if not np.all(np.isfinite(triangle_array)):
        raise ValueError("triangles must contain only finite values")

    points_for_kernel = np.array(canonical_xyz, dtype=np.float64, copy=True, order="C")
    triangles_for_kernel = np.array(triangle_array, dtype=np.float64, copy=True, order="C")

    if use_bvh:
        current_bvh: ExactBvh
        if bvh is not None:
            current_bvh = bvh
        else:
            current_bvh = build_exact_bvh(triangles_for_kernel)
        bvh_result_raw = project_points_bvh(
            points_for_kernel, triangles_for_kernel, bvh=current_bvh,
            diagnostics=return_diagnostics,
        )
        if return_diagnostics:
            kernel_result, bvh_diag = bvh_result_raw
        else:
            kernel_result = bvh_result_raw
    else:
        if return_diagnostics:
            raise ValueError(
                "return_diagnostics=True requires use_bvh=True"
            )
        kernel_result = project_points_exact(points_for_kernel, triangles_for_kernel)

    count = canonical_xyz.shape[0]
    triangle_id = np.asarray(kernel_result.triangle_id)
    projected_xyz = np.asarray(kernel_result.closest_point)
    distance = np.asarray(kernel_result.distance)
    raw_normal = np.asarray(kernel_result.raw_normal)
    if triangle_id.shape != (count,):
        raise ValueError(f"kernel triangle_id must have shape ({count},), got {triangle_id.shape}")
    if projected_xyz.shape != (count, 3):
        raise ValueError(
            f"kernel closest_point must have shape ({count}, 3), got {projected_xyz.shape}"
        )
    if distance.shape != (count,):
        raise ValueError(f"kernel distance must have shape ({count},), got {distance.shape}")
    if raw_normal.shape != (count, 3):
        raise ValueError(f"kernel raw_normal must have shape ({count}, 3), got {raw_normal.shape}")
    if not np.issubdtype(triangle_id.dtype, np.integer):
        raise ValueError("kernel triangle_id must have an integer dtype")

    triangle_id = np.asarray(triangle_id, dtype=np.int64)
    projected_xyz = np.asarray(projected_xyz, dtype=np.float64)
    distance = np.asarray(distance, dtype=np.float64)
    raw_normal = np.asarray(raw_normal, dtype=np.float64)
    if np.any(triangle_id < 0) or np.any(triangle_id >= triangle_array.shape[0]):
        raise ValueError("kernel triangle_id contains an index outside the triangle mesh")
    if not np.all(np.isfinite(projected_xyz)):
        raise ValueError("kernel closest_point must contain only finite values")
    if not np.all(np.isfinite(distance)) or np.any(distance < 0.0):
        raise ValueError("kernel distance must contain only finite nonnegative values")
    _validate_selected_raw_normals(triangle_array, triangle_id, raw_normal)

    solver_xyz = _readonly_copy(canonical_xyz, dtype=np.float64)
    canonical_hash = hashlib.sha256(solver_xyz.tobytes(order="C")).hexdigest()
    projection = FluentSurfaceProjection(
        canonical_index=_readonly_copy(np.arange(count), dtype=np.int64),
        solver_xyz=solver_xyz,
        projected_xyz=_readonly_copy(projected_xyz, dtype=np.float64),
        triangle_id=_readonly_copy(triangle_id, dtype=np.int64),
        projection_distance_m=_readonly_copy(distance, dtype=np.float64),
        raw_normal=_readonly_copy(raw_normal, dtype=np.float64),
        projection_gate_m=gate,
        projection_gate_pass=_readonly_copy(distance <= gate, dtype=np.bool_),
        geometry_source_path=Path(geometry.source_path),
        geometry_source_sha256=str(geometry.source_sha256),
        canonical_geometry_sha256=canonical_hash,
        triangle_count=int(triangle_array.shape[0]),
    )
    if return_diagnostics and use_bvh:
        diag_dict = {
            "node_visits": int(bvh_diag.total_node_visits),
            "leaf_visits": int(bvh_diag.total_leaf_visits),
            "triangle_kernel_calls": int(bvh_diag.total_triangle_kernel_calls),
            "fallback_count": int(bvh_diag.total_points_with_fallback),
            "tree_depth": int(bvh_diag.tree_depth),
            "leaf_count": int(bvh_diag.leaf_count),
            "avg_leaf_tri_count": float(bvh_diag.avg_leaf_tri_count),
            "triangle_count": int(triangle_array.shape[0]),
            "point_count": int(count),
        }
        return projection, diag_dict
    return projection


def canonical_values_to_source_order(
    canonical_values: np.ndarray,
    source_to_canonical_row: np.ndarray,
) -> np.ndarray:
    """Restore a canonical field to CSV source rows using the parser permutation."""
    values = np.asarray(canonical_values)
    mapping = np.asarray(source_to_canonical_row)
    if values.ndim == 0:
        raise ValueError("canonical_values must have at least one dimension")
    if mapping.ndim != 1:
        raise ValueError(
            f"source_to_canonical_row must have shape (N,), got {mapping.shape}"
        )
    if not np.issubdtype(mapping.dtype, np.integer):
        raise ValueError("source_to_canonical_row must have an integer dtype")
    count = values.shape[0]
    if mapping.shape != (count,):
        raise ValueError(
            "source_to_canonical_row length must match canonical_values first dimension"
        )
    mapping_int64 = np.asarray(mapping, dtype=np.int64)
    if not np.array_equal(np.sort(mapping_int64), np.arange(count, dtype=np.int64)):
        raise ValueError("source_to_canonical_row must be a permutation of 0..N-1")
    return _readonly_copy(values[mapping_int64], dtype=values.dtype)


# ---------------------------------------------------------------------------
# Cache orchestration — single public entry point
# ---------------------------------------------------------------------------


def project_fluent_surface_with_cache(
    geometry: FluentSurfaceGeometry,
    triangles: np.ndarray,
    *,
    projection_gate_m: float,
    use_bvh: bool = True,
    bvh: ExactBvh | None = None,
    cache_path: str | Path | None = None,
    write_cache: bool = False,
    geometry_identity_kwargs: dict[str, Any] | None = None,
) -> FluentSurfaceProjection:
    """Single orchestration entry point for Fluent projection with optional caching.

    Cache lookup priority:
      1. If *cache_path* is given and file exists: load with fail-closed identity
         validation. On hit, return cached result immediately.
      2. Otherwise: run projection (BVH or brute-force as specified by *use_bvh*).
      3. If *write_cache* is True and *cache_path* is given: atomically write the
         freshly computed projection to cache. This is always opt-in — cache is
         never written automatically.

    Cache identity validation requires *geometry_identity_kwargs* with all the
    fields documented in ``projection_cache.build_geometry_identity``.

    Returns
    -------
    FluentSurfaceProjection
    """
    from ref_enthalpy_method.geometry.projection_cache import (
        build_cache_manifest,
        build_geometry_identity,
        load_projection_cache,
        write_projection_cache,
    )

    gate = _positive_finite_scalar(projection_gate_m, name="projection_gate_m")
    solver_xyz = np.asarray(geometry.canonical_solver_xyz)
    if solver_xyz.dtype != np.dtype(np.float64):
        raise ValueError(
            "geometry canonical solver coordinates must have dtype float64"
        )
    if solver_xyz.ndim != 2 or solver_xyz.shape[1:] != (3,):
        raise ValueError(
            "geometry canonical solver coordinates must have shape (N, 3)"
        )
    if solver_xyz.shape[0] == 0 or not np.all(np.isfinite(solver_xyz)):
        raise ValueError(
            "geometry canonical solver coordinates must be nonempty and finite"
        )

    triangle_array = np.asarray(triangles)
    if triangle_array.dtype != np.dtype(np.float64):
        triangle_array = np.asarray(triangles, dtype=np.float64)
    if triangle_array.ndim != 3 or triangle_array.shape[1:] != (3, 3):
        raise ValueError(
            f"triangles must have shape (M, 3, 3), got {triangle_array.shape}"
        )
    if triangle_array.shape[0] == 0 or not np.all(np.isfinite(triangle_array)):
        raise ValueError("triangles must be nonempty and finite")

    canonical_hash = hashlib.sha256(
        np.ascontiguousarray(solver_xyz).tobytes(order="C")
    ).hexdigest()

    identity: dict[str, Any] | None = None
    if geometry_identity_kwargs is not None:
        identity_inputs = dict(geometry_identity_kwargs)
        identity_inputs.update(
            fluent_geometry_source_path=Path(geometry.source_path),
            fluent_canonical_geometry_sha256=canonical_hash,
            canonical_point_count=int(solver_xyz.shape[0]),
            triangles=triangle_array,
            projection_gate_m=gate,
        )
        identity = build_geometry_identity(**identity_inputs)

    cache_p = Path(cache_path).resolve() if cache_path is not None else None
    if cache_p is not None and cache_p.exists() and not cache_p.is_file():
        raise ValueError(f"cache_path exists but is not a file: {cache_p}")

    if cache_p is not None and cache_p.is_file():
        if identity is None:
            raise ValueError(
                "geometry_identity_kwargs required for cache identity validation"
            )
        cached = load_projection_cache(
            cache_p,
            **identity,
            triangle_count=triangle_array.shape[0],
        )
        _validate_selected_raw_normals(
            triangle_array, cached.triangle_id, cached.raw_normal
        )
        projection = FluentSurfaceProjection(
            canonical_index=_readonly_copy(
                np.arange(solver_xyz.shape[0]), dtype=np.int64
            ),
            solver_xyz=_readonly_copy(solver_xyz, dtype=np.float64),
            projected_xyz=_readonly_copy(cached.projected_xyz, dtype=np.float64),
            triangle_id=_readonly_copy(cached.triangle_id, dtype=np.int64),
            projection_distance_m=_readonly_copy(
                cached.projection_distance_m, dtype=np.float64
            ),
            raw_normal=_readonly_copy(cached.raw_normal, dtype=np.float64),
            projection_gate_m=gate,
            projection_gate_pass=_readonly_copy(
                cached.projection_gate_pass, dtype=np.bool_
            ),
            geometry_source_path=Path(geometry.source_path),
            geometry_source_sha256=str(geometry.source_sha256),
            canonical_geometry_sha256=canonical_hash,
            triangle_count=int(triangle_array.shape[0]),
        )
        return projection

    projection = project_fluent_surface_exact(
        geometry,
        triangle_array,
        projection_gate_m=gate,
        use_bvh=use_bvh,
        bvh=bvh,
        return_diagnostics=False,
    )

    if write_cache and cache_p is not None:
        if identity is None:
            raise ValueError(
                "geometry_identity_kwargs required for cache writing"
            )
        manifest = build_cache_manifest(
            **identity,
            projected_xyz=projection.projected_xyz,
            triangle_id=projection.triangle_id,
            raw_normal=projection.raw_normal,
            projection_distance_m=projection.projection_distance_m,
            projection_gate_pass=projection.projection_gate_pass,
        )
        write_projection_cache(
            target_path=cache_p,
            projected_xyz=projection.projected_xyz,
            triangle_id=projection.triangle_id,
            raw_normal=projection.raw_normal,
            projection_distance_m=projection.projection_distance_m,
            projection_gate_pass=projection.projection_gate_pass,
            manifest=manifest,
        )

    return projection
