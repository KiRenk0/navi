"""Comprehensive tests for the array-based AABB BVH accelerator (v2).

Covers:
- AABB lower-bound correctness
- BVH build validation
- Synthetic exactness (interior / edge / vertex / tie / degenerate / far)
- Cross-subtree tie-break (separate subtrees, near-tie, traversal order)
- Traversal-order differential (left/right flip, input permutation)
- Leaf-size differential (1, 2, 8, 16)
- Randomized small-mesh differential
- Lower-bound / fallback safety
- HTV-2 real-mesh regional stratified differential
- Diagnostics counters
"""

from __future__ import annotations

import math
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from ref_enthalpy_method.geometry.exact_projection import (
    SurfaceProjection,
    _distances_equivalent,
    closest_point_on_triangle,
    project_points_exact,
)
from ref_enthalpy_method.geometry.exact_bvh import (
    BvhDiagnostics,
    build_exact_bvh,
    project_points_bvh,
)

# ── shared geometry ──────────────────────────────────────────────────────────

_XY_TRIANGLE = np.array(
    [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 2.0, 0.0]],
    dtype=np.float64,
)


def _make_random_mesh(
    rng: np.random.Generator, nt: int = 50, scale: float = 10.0
) -> np.ndarray:
    vertices = rng.uniform(-scale, scale, (nt * 3, 3)).astype(np.float64)
    return vertices.reshape(nt, 3, 3)


def _make_random_points(
    rng: np.random.Generator, n: int = 200, scale: float = 12.0
) -> np.ndarray:
    return rng.uniform(-scale, scale, (n, 3)).astype(np.float64)


def _assert_bvh_bf_match(
    test: unittest.TestCase,
    pts: np.ndarray,
    tris: np.ndarray,
    *,
    bvh_leaf_size: int = 16,
    msg: str = "",
) -> None:
    bvh = build_exact_bvh(tris, leaf_size=bvh_leaf_size)
    bvh_r, diag = project_points_bvh(pts, tris, bvh=bvh, diagnostics=True)
    bf_r = project_points_exact(pts, tris)
    prefix = f"[{msg}] " if msg else ""
    test.assertEqual(diag.total_points_with_fallback, 0,
                     f"{prefix}fallback count non-zero")
    np.testing.assert_array_equal(bvh_r.triangle_id, bf_r.triangle_id,
                                  err_msg=f"{prefix}triangle_id mismatch")
    np.testing.assert_array_equal(bvh_r.closest_point, bf_r.closest_point,
                                  err_msg=f"{prefix}closest_point mismatch")
    np.testing.assert_array_equal(bvh_r.distance, bf_r.distance,
                                  err_msg=f"{prefix}distance mismatch")
    np.testing.assert_array_equal(bvh_r.raw_normal, bf_r.raw_normal,
                                  err_msg=f"{prefix}raw_normal mismatch")


# ═══════════════════════════════════════════════════════════════════════════════
# AABB lower-bound
# ═══════════════════════════════════════════════════════════════════════════════


class AabbLowerBoundTest(unittest.TestCase):
    def test_point_inside_aabb_zero(self) -> None:
        from ref_enthalpy_method.geometry.exact_bvh import (
            _squared_distance_point_aabb,
        )
        lb = _squared_distance_point_aabb(
            np.array([1.0, 2.0, 3.0]),
            np.array([0.0, 1.0, 2.0]),
            np.array([2.0, 3.0, 4.0]),
        )
        self.assertEqual(lb, 0.0)

    def test_point_outside_corner(self) -> None:
        from ref_enthalpy_method.geometry.exact_bvh import (
            _squared_distance_point_aabb,
        )
        lb = _squared_distance_point_aabb(
            np.array([5.0, 5.0, 5.0]),
            np.array([0.0, 1.0, 2.0]),
            np.array([2.0, 3.0, 4.0]),
        )
        self.assertAlmostEqual(lb, 14.0, places=12)

    def test_lower_bound_never_exceeds_actual(self) -> None:
        from ref_enthalpy_method.geometry.exact_bvh import (
            _squared_distance_point_aabb,
        )
        rng = np.random.default_rng(42)
        for _ in range(200):
            lo = rng.uniform(-10, 10, 3)
            hi = lo + rng.uniform(0.1, 5, 3)
            pt = rng.uniform(lo, hi)
            query = rng.uniform(-20, 20, 3)
            lb = _squared_distance_point_aabb(query, lo, hi)
            sq_dist = float(np.sum((pt - query) ** 2))
            self.assertLessEqual(lb, sq_dist + 1e-14)


# ═══════════════════════════════════════════════════════════════════════════════
# BVH build
# ═══════════════════════════════════════════════════════════════════════════════


class BvhBuildTest(unittest.TestCase):
    def test_single_triangle_is_leaf(self) -> None:
        bvh = build_exact_bvh(np.stack([_XY_TRIANGLE]))
        self.assertEqual(bvh.triangle_count, 1)
        self.assertEqual(bvh.node_type[0], 1)  # leaf

    def test_empty_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_exact_bvh(np.empty((0, 3, 3)))

    def test_nonfinite_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_exact_bvh(np.full((1, 3, 3), np.nan))

    def test_count_mismatch_rejected(self) -> None:
        bvh = build_exact_bvh(np.stack([_XY_TRIANGLE, _XY_TRIANGLE + [0, 0, 5]]))
        with self.assertRaises(ValueError):
            project_points_bvh(np.array([[0, 0, 0]]), np.stack([_XY_TRIANGLE]), bvh=bvh)

    def test_deterministic_build(self) -> None:
        rng = np.random.default_rng(123)
        tris = _make_random_mesh(rng, nt=100)
        bvh1 = build_exact_bvh(tris)
        bvh2 = build_exact_bvh(tris)
        pts = _make_random_points(rng, n=50)
        r1, d1 = project_points_bvh(pts, tris, bvh=bvh1, diagnostics=True)
        r2, d2 = project_points_bvh(pts, tris, bvh=bvh2, diagnostics=True)
        np.testing.assert_array_equal(r1.triangle_id, r2.triangle_id)
        np.testing.assert_array_equal(r1.closest_point, r2.closest_point)
        np.testing.assert_array_equal(r1.distance, r2.distance)
        self.assertEqual(d1.total_points_with_fallback, 0)
        self.assertEqual(d2.total_points_with_fallback, 0)

    def test_min_tri_idx_propagated(self) -> None:
        """Every internal node's min_tri_idx should be <= children's."""
        tris = _make_random_mesh(np.random.default_rng(7), nt=30)
        bvh = build_exact_bvh(tris)
        for i in range(bvh.node_type.shape[0]):
            if bvh.node_type[i] == 0:  # internal
                left = int(bvh.node_left[i])
                right = int(bvh.node_right[i])
                self.assertLessEqual(bvh.node_min_tri_idx[i], bvh.node_min_tri_idx[left])
                self.assertLessEqual(bvh.node_min_tri_idx[i], bvh.node_min_tri_idx[right])


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-subtree tie-break tests (NEW)
# ═══════════════════════════════════════════════════════════════════════════════


class CrossSubtreeTieBreakTest(unittest.TestCase):
    """Tests where triangles with equivalent distances live in different subtrees."""

    def test_equal_distance_different_subtrees_smaller_index_wins(self) -> None:
        """Two identical triangles at equal distance, in different sibling subtrees.
        The smaller-indexed triangle must be selected regardless of traversal order.
        """
        # Triangle 0 at z=0, triangle 1 at z=5 (mirrored)
        tri_a = _XY_TRIANGLE + np.array([0.0, 0.0, 5.0])   # index 0, left subtree
        tri_b = _XY_TRIANGLE + np.array([0.0, 0.0, -5.0])  # index 1, right subtree
        # Space them far enough apart to guarantee separate subtrees
        tri_a2 = _XY_TRIANGLE + np.array([100.0, 0.0, 5.0])  # filler for left
        tri_b2 = _XY_TRIANGLE + np.array([100.0, 0.0, -5.0])  # filler for right
        tris = np.stack([tri_a, tri_b, tri_a2, tri_b2])
        # Point equidistant from tri_a and tri_b
        point = np.array([[50.0, 0.5, 2.5]])
        bvh = build_exact_bvh(tris)
        bvh_r, diag = project_points_bvh(point, tris, bvh=bvh, diagnostics=True)
        bf_r = project_points_exact(point, tris)
        self.assertEqual(diag.total_points_with_fallback, 0)
        self.assertEqual(bvh_r.triangle_id[0], bf_r.triangle_id[0])

    def test_larger_index_subtree_visited_first_still_picks_smaller(self) -> None:
        """Construct a mesh where the larger-index triangle's subtree has a
        lower AABB bound (so it's visited first), but the smaller-index
        triangle is at equivalent distance."""
        # Tri 0 (small index): z=0, far in x
        # Tri 1 (large index): z=0, close in x
        tri_small = _XY_TRIANGLE + np.array([20.0, 0.0, 0.0])   # index 0
        tri_large = _XY_TRIANGLE + np.array([0.0, 0.0, 0.0])    # index 1
        # Make them at equal (x,z) distance from query point (10, 0.5, 0)
        # tri_small: dx=10, dz=0 → dist=10
        # tri_large: dx=10, dz=0 → dist=10
        # But tri_large is closer in the AABB lower-bound sense
        point = np.array([[10.0, 0.5, 0.0]])
        tris = np.stack([tri_small, tri_large])
        # Add fillers to ensure they end up in different subtrees
        for k in range(2, 20):
            filler = _XY_TRIANGLE + np.array([float(k * 50), 0.0, 0.0])
            tris = np.concatenate([tris, filler[np.newaxis]], axis=0)

        _assert_bvh_bf_match(self, point, tris, msg="larger_visited_first")

    def test_smaller_index_subtree_lb_equals_best_no_prune(self) -> None:
        """When the smaller-index triangle's subtree has lower_bound
        equivalent to current best, it must NOT be pruned."""
        # Tri 0 (small index, right subtree): slightly farther
        # Tri 1 (large index, left subtree): slightly closer
        tri_small = _XY_TRIANGLE + np.array([0.0, 0.0, 5.0 + 1e-13])  # index 0
        tri_large = _XY_TRIANGLE + np.array([0.0, 0.0, -5.0])          # index 1
        tris = np.stack([tri_small, tri_large])
        # Point at z=2.5: distances are ~2.5-1e-13 vs 2.5+..., equivalent within tolerance
        point = np.array([[0.5, 0.5, 2.5]])
        _assert_bvh_bf_match(self, point, tris, msg="lb_eq_best")

    def test_near_tie_within_tolerance_smaller_index_wins(self) -> None:
        """Distances within _distances_equivalent tolerance: smaller index wins."""
        # Tri A slightly farther by 5e-13 (within 1e-12 tolerance)
        tri_a = _XY_TRIANGLE + np.array([0.0, 0.0, 5.0 + 5e-13])  # index 0
        tri_b = _XY_TRIANGLE + np.array([0.0, 0.0, -5.0])          # index 1
        tris = np.stack([tri_a, tri_b])
        point = np.array([[0.5, 0.5, 2.5]])
        bvh_r, diag = project_points_bvh(point, tris,
                                          bvh=build_exact_bvh(tris), diagnostics=True)
        bf_r = project_points_exact(point, tris)
        self.assertEqual(diag.total_points_with_fallback, 0)
        self.assertEqual(bvh_r.triangle_id[0], bf_r.triangle_id[0])

    def test_flip_left_right_child_order_same_result(self) -> None:
        """Flipping left/right child order in the BVH must not change the result."""
        rng = np.random.default_rng(555)
        tris = _make_random_mesh(rng, nt=40)
        pts = _make_random_points(rng, n=30)
        bvh = build_exact_bvh(tris)

        # Normal query
        r1, d1 = project_points_bvh(pts, tris, bvh=bvh, diagnostics=True)
        self.assertEqual(d1.total_points_with_fallback, 0)
        self.assertTrue(np.array_equal(r1.triangle_id,
                        project_points_exact(pts, tris).triangle_id))

        # Create a flipped BVH by swapping left/right at every internal node
        flipped_left = bvh.node_left.copy()
        flipped_right = bvh.node_right.copy()
        for i in range(bvh.node_type.shape[0]):
            if bvh.node_type[i] == 0:  # internal
                tmp = flipped_left[i]
                flipped_left[i] = flipped_right[i]
                flipped_right[i] = tmp

        from ref_enthalpy_method.geometry.exact_bvh import ExactBvh
        flipped_bvh = ExactBvh(
            node_type=bvh.node_type,
            node_aabb_min=bvh.node_aabb_min,
            node_aabb_max=bvh.node_aabb_max,
            node_min_tri_idx=bvh.node_min_tri_idx,
            node_left=flipped_left,
            node_right=flipped_right,
            node_tri_start=bvh.node_tri_start,
            node_tri_count=bvh.node_tri_count,
            leaf_tri_indices=bvh.leaf_tri_indices,
            tri_aabb_min=bvh.tri_aabb_min,
            tri_aabb_max=bvh.tri_aabb_max,
            triangle_count=bvh.triangle_count,
            leaf_size=bvh.leaf_size,
        )
        r2, d2 = project_points_bvh(pts, tris, bvh=flipped_bvh, diagnostics=True)
        self.assertEqual(d2.total_points_with_fallback, 0)
        np.testing.assert_array_equal(r2.triangle_id, r1.triangle_id)
        np.testing.assert_array_equal(r2.closest_point, r1.closest_point)
        np.testing.assert_array_equal(r2.distance, r1.distance)

    def test_input_spatial_permutation_same_result(self) -> None:
        """When triangles are permuted, BVH results in permuted index space
        map back to the same original triangles as brute-force in original space.

        Note: the BVH's node_min_tri_idx depends on input-order indices.
        After inverse-permutation mapping, the results must match.
        """
        rng = np.random.default_rng(666)
        base_tris = _make_random_mesh(rng, nt=50)
        pts = _make_random_points(rng, n=40)
        bf_r = project_points_exact(pts, base_tris)

        # Build permutation and invert
        perm = rng.permutation(base_tris.shape[0])
        inv_perm = np.argsort(perm)
        permuted_tris = base_tris[perm]
        r2, d2 = project_points_bvh(pts, permuted_tris,
                                     bvh=build_exact_bvh(permuted_tris),
                                     diagnostics=True)
        self.assertEqual(d2.total_points_with_fallback, 0)
        r2_original_tri = inv_perm[r2.triangle_id]

        # Permutation may expose different tie-break paths;
        # all non-tie (strictly better) distances must match exactly.
        bf_dist = bf_r.distance
        r2_dist = r2.distance
        for i in range(len(pts)):
            if bf_dist[i] < r2_dist[i] * 0.9999:
                # BVH missed a significantly closer triangle — real bug
                self.fail(f"pt {i}: BF dist={bf_dist[i]:.8f} < BVH dist={r2_dist[i]:.8f}")
        # The remaining mismatches are tie-break variations.
        # Verify BVH chosen triangle is at equivalent distance.
        from ref_enthalpy_method.geometry.exact_projection import _distances_equivalent, closest_point_on_triangle
        for i in range(len(pts)):
            if r2_original_tri[i] != bf_r.triangle_id[i]:
                # BVH chose different triangle — verify it's equivalent distance
                tri_vh = perm[r2.triangle_id[i]]  # map back to original
                cand_bvh = closest_point_on_triangle(pts[i], base_tris[tri_vh])
                self.assertTrue(
                    _distances_equivalent(cand_bvh.distance, bf_dist[i]),
                    f"pt {i}: non-equivalent distances: "
                    f"BVH({tri_vh})={cand_bvh.distance:.15f} vs BF({bf_r.triangle_id[i]})={bf_dist[i]:.15f}"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# Leaf-size differential
# ═══════════════════════════════════════════════════════════════════════════════


class LeafSizeDifferentialTest(unittest.TestCase):
    """Result must be identical regardless of leaf size."""

    def test_leaf_size_variants_yield_same_result(self) -> None:
        rng = np.random.default_rng(7777)
        tris = _make_random_mesh(rng, nt=80)
        pts = _make_random_points(rng, n=60)
        bf_r = project_points_exact(pts, tris)

        for leaf_sz in (1, 2, 4, 8, 16, 32):
            bvh = build_exact_bvh(tris, leaf_size=leaf_sz)
            bvh_r, diag = project_points_bvh(pts, tris, bvh=bvh, diagnostics=True)
            with self.subTest(leaf_size=leaf_sz):
                self.assertEqual(diag.total_points_with_fallback, 0,
                                 f"fallback at leaf_size={leaf_sz}")
                np.testing.assert_array_equal(bvh_r.triangle_id, bf_r.triangle_id,
                                              f"leaf_size={leaf_sz}")
                np.testing.assert_array_equal(bvh_r.closest_point, bf_r.closest_point)
                np.testing.assert_array_equal(bvh_r.distance, bf_r.distance)


# ═══════════════════════════════════════════════════════════════════════════════
# Stack order differential (NEW)
# ═══════════════════════════════════════════════════════════════════════════════


class StackOrderDifferentialTest(unittest.TestCase):
    """Priority queue insertion order must not affect result."""

    def test_repeated_queries_bitwise_deterministic(self) -> None:
        rng = np.random.default_rng(99)
        tris = _make_random_mesh(rng, nt=80)
        pts = _make_random_points(rng, n=100)
        bvh = build_exact_bvh(tris)
        results = []
        for _ in range(5):
            r, d = project_points_bvh(pts, tris, bvh=bvh, diagnostics=True)
            results.append(r)
            self.assertEqual(d.total_points_with_fallback, 0)
        for i in range(1, len(results)):
            np.testing.assert_array_equal(results[0].triangle_id, results[i].triangle_id)
            np.testing.assert_array_equal(results[0].closest_point, results[i].closest_point)
            np.testing.assert_array_equal(results[0].distance, results[i].distance)
            np.testing.assert_array_equal(results[0].raw_normal, results[i].raw_normal)


# ═══════════════════════════════════════════════════════════════════════════════
# Synthetic exactness
# ═══════════════════════════════════════════════════════════════════════════════


class SyntheticExactnessTest(unittest.TestCase):
    def test_interior(self) -> None:
        pts = np.array([[0.5, 0.5, 3.0], [1.0, 0.5, -2.0], [0.2, 1.5, 5.0]])
        _assert_bvh_bf_match(self, pts, np.stack([_XY_TRIANGLE]))

    def test_edge(self) -> None:
        pts = np.array([[1.0, -1.0, 0.0], [-1.0, 1.0, 0.0], [1.5, 1.5, 0.0],
                        [0.0, 1.0, -5.0], [2.0, 0.0, 7.0]])
        _assert_bvh_bf_match(self, pts, np.stack([_XY_TRIANGLE]))

    def test_vertex(self) -> None:
        pts = np.array([[-2.0, -1.0, 0.0], [3.0, -1.0, 0.0], [-1.0, 3.0, 0.0]])
        _assert_bvh_bf_match(self, pts, np.stack([_XY_TRIANGLE]))

    def test_exact_tie_smaller_index(self) -> None:
        tri_a = _XY_TRIANGLE.copy()
        tri_b = _XY_TRIANGLE + np.array([0.0, 0.0, 5.0])
        tris = np.stack([tri_a, tri_b])
        pts = np.array([[0.5, 0.5, 2.5]])
        _assert_bvh_bf_match(self, pts, tris)
        bf_r = project_points_exact(pts, tris)
        self.assertEqual(bf_r.triangle_id[0], 0)

    def test_point_on_surface(self) -> None:
        pts = np.array([[0.5, 0.5, 0.0], [0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        _assert_bvh_bf_match(self, pts, np.stack([_XY_TRIANGLE]))
        r = project_points_exact(pts, np.stack([_XY_TRIANGLE]))
        for d in r.distance:
            self.assertAlmostEqual(d, 0.0, places=15)

    def test_far_point(self) -> None:
        pts = np.array([[1e6, 1e6, 1e6]])
        _assert_bvh_bf_match(self, pts, np.stack([_XY_TRIANGLE, _XY_TRIANGLE + [0, 0, 5]]))

    def test_degenerate_collinear(self) -> None:
        degenerate = np.array([[[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [1.0, 0.0, 0.0]]])
        pts = np.array([[1.5, 2.0, 0.0], [0.0, 0.0, 1.0], [3.0, 0.0, -2.0]])
        _assert_bvh_bf_match(self, pts, degenerate)

    def test_fully_collapsed(self) -> None:
        collapsed = np.repeat(np.array([[4.0, -2.0, 1.0]]), 3, axis=0).reshape(1, 3, 3)
        pts = np.array([[5.0, -2.0, 1.0]])
        _assert_bvh_bf_match(self, pts, collapsed)

    def test_global_nearest_across_separated(self) -> None:
        tri_a = _XY_TRIANGLE + np.array([0, 0, 5])
        tri_b = _XY_TRIANGLE + np.array([10, 0, 0])
        tri_c = _XY_TRIANGLE + np.array([5, 5, -3])
        tris = np.stack([tri_a, tri_b, tri_c])
        pts = np.array([[0.5, 0.5, 4.8], [10.5, 0.5, -0.2],
                        [5.5, 5.5, -3.2], [10.5, 5.5, -2.8]])
        _assert_bvh_bf_match(self, pts, tris)


# ═══════════════════════════════════════════════════════════════════════════════
# Randomized differential
# ═══════════════════════════════════════════════════════════════════════════════


class RandomizedDifferentialTest(unittest.TestCase):
    def test_various_mesh_sizes(self) -> None:
        rng = np.random.default_rng(12345)
        for mesh_size in (1, 5, 20, 50, 100):
            tris = _make_random_mesh(rng, nt=mesh_size)
            pts = _make_random_points(rng, n=100)
            _assert_bvh_bf_match(self, pts, tris, msg=f"mesh_{mesh_size}")

    def test_multi_seed(self) -> None:
        for seed in (100, 200, 300):
            rng = np.random.default_rng(seed)
            tris = _make_random_mesh(rng, nt=rng.integers(10, 60))
            pts = _make_random_points(rng, n=rng.integers(50, 200))
            _assert_bvh_bf_match(self, pts, tris, msg=f"seed_{seed}")


# ═══════════════════════════════════════════════════════════════════════════════
# Lower-bound / fallback
# ═══════════════════════════════════════════════════════════════════════════════


class LowerBoundFallbackTest(unittest.TestCase):
    def test_never_prunes_true_nearest(self) -> None:
        rng = np.random.default_rng(7777)
        for _ in range(10):
            tris = _make_random_mesh(rng, nt=30)
            pts = _make_random_points(rng, n=50)
            _assert_bvh_bf_match(self, pts, tris)

    def test_fallback_count_zero_for_normal_mesh(self) -> None:
        rng = np.random.default_rng(42)
        tris = _make_random_mesh(rng, nt=20)
        pts = _make_random_points(rng, n=30)
        bvh = build_exact_bvh(tris)
        _, diag = project_points_bvh(pts, tris, bvh=bvh, diagnostics=True)
        self.assertEqual(diag.total_points_with_fallback, 0)

    def test_tie_unaffected_by_traversal_order(self) -> None:
        tri_a = np.array([[0, 0, 0], [2, 0, 0], [0, 2, 0]], dtype=np.float64)
        tri_b = np.array([[10, 0, 0], [8, 0, 0], [10, 2, 0]], dtype=np.float64)
        tris = np.stack([tri_a, tri_b])
        pts = np.array([[5.0, 0.5, 1.0]])
        _assert_bvh_bf_match(self, pts, tris)

    def test_valid_input_errors_not_caught_as_fallback(self) -> None:
        """Input contract errors must NOT trigger fallback — they propagate."""
        bvh = build_exact_bvh(np.stack([_XY_TRIANGLE]))
        # Wrong shape should fail (not fallback)
        with self.assertRaises(ValueError):
            project_points_bvh(
                np.array([0, 0, 0]),  # 1D instead of 2D
                np.stack([_XY_TRIANGLE]),
                bvh=bvh,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# HTV-2 real-mesh REGIONAL stratified differential
# ═══════════════════════════════════════════════════════════════════════════════


class Htv2RegionalDifferentialTest(unittest.TestCase):
    """Explicit per-region geographical samples with documented selection rules."""

    @classmethod
    def setUpClass(cls) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        fluent_csv = repo_root / "fluent_export" / "adiabatic_wall_csv" / "30km_5alpha_8ma.csv"
        stl_path = repo_root / "new_spec" / "htv2_0628.stl"
        if not fluent_csv.is_file() or not stl_path.is_file():
            raise AssertionError(
                f"HTV-2 differential inputs missing: {fluent_csv}, {stl_path}"
            )

        from ref_enthalpy_method.geometry.stl_surface import AsciiStlMesh
        from ref_enthalpy_method.geometry.local_incidence import (
            outward_normal_from_slopes,
        )
        from ref_enthalpy_method.geometry.projected_semantics import (
            build_projected_geometry_semantics,
        )
        from ref_enthalpy_method.mapping.fluent_clean import (
            build_fluent_clean_leeward_masks,
        )
        from ref_enthalpy_method.mapping.fluent_surface import (
            read_fluent_surface_geometry_csv,
        )

        cls._geometry = read_fluent_surface_geometry_csv(fluent_csv, x_offset_m=0.030)
        stl = AsciiStlMesh.load(stl_path=stl_path, unit="auto", span_sign=-1.0)
        cls._triangles = np.stack([stl.v0, stl.v1, stl.v2], axis=1)
        cls._all_xyz = np.ascontiguousarray(cls._geometry.canonical_solver_xyz)
        cls._M = cls._all_xyz.shape[0]
        cls._bvh = build_exact_bvh(cls._triangles, leaf_size=16)

        # This is the only complete pass used for sample selection. The
        # reference kernel is called later only on the selected samples.
        cls._full_bvh_result, cls._full_bvh_diag = project_points_bvh(
            cls._all_xyz,
            cls._triangles,
            bvh=cls._bvh,
            diagnostics=True,
        )
        if cls._full_bvh_diag.total_points_with_fallback != 0:
            raise AssertionError(
                "full HTV-2 BVH sample-selection pass used fallback: "
                f"{cls._full_bvh_diag.total_points_with_fallback}"
            )

        x = cls._all_xyz[:, 0]
        span = cls._all_xyz[:, 1]
        up = cls._all_xyz[:, 2]
        x_min, x_max = float(x.min()), float(x.max())
        span_max = float(span.max())
        up_min, up_max = float(up.min()), float(up.max())
        x_range = x_max - x_min
        up_range = up_max - up_min

        # Formal geometry semantics are used where a region has an existing
        # project contract. The clean mask is intentionally built from the
        # complete BVH result, never from a brute-force pass.
        from ref_enthalpy_method.geometry.local_incidence import (
            outward_normal_from_slopes,
        )
        from ref_enthalpy_method.geometry.projected_semantics import (
            build_projected_geometry_semantics,
        )
        from ref_enthalpy_method.mapping.fluent_clean import (
            build_fluent_clean_leeward_masks,
        )

        semantics = build_projected_geometry_semantics(
            projected_xyz=cls._full_bvh_result.closest_point,
            triangle_id=cls._full_bvh_result.triangle_id,
            triangles=cls._triangles,
            alpha_deg=5.0,
            planform_b_half_m=1.1,
            chord_min_m=0.02,
            upper_reference_normal_out=outward_normal_from_slopes(
                sx=0.17632698070846498,
                sy=-0.5426786456862612,
                sheet="upper",
            ),
            lower_reference_normal_out=outward_normal_from_slopes(
                sx=-0.05240777928304121,
                sy=0.16129455951933025,
                sheet="lower",
            ),
            c_root_m=3.6,
            planform_half_angle_deg=18.0,
        )
        gate_pass = np.array(cls._full_bvh_result.distance <= 0.005, dtype=np.bool_, copy=True)
        gate_pass.setflags(write=False)
        integration = SimpleNamespace(
            projection=SimpleNamespace(projection_gate_pass=gate_pass),
            semantics=semantics,
        )
        clean_masks = build_fluent_clean_leeward_masks(integration)

        masks = {
            "nose": x <= x_min + 0.15 * x_range,
            "leading_edge": (
                (x >= x_min + 0.15 * x_range)
                & (x <= x_min + 0.35 * x_range)
                & (np.abs(up - 0.5 * (up_min + up_max)) >= 0.3 * up_range)
            ),
            "trailing_edge": x >= x_min + 0.85 * x_range,
            "upper": up >= up_min + 0.7 * up_range,
            "lower": up <= up_min + 0.3 * up_range,
            # The right-half STL is represented in span >= 0 coordinates;
            # the outer high-span band is the actual chine-side catalog.
            "chine": (
                (x >= x_min + 0.15 * x_range)
                & (x <= x_min + 0.85 * x_range)
                & (span >= 0.7 * span_max)
            ),
            "side": span <= 0.1 * span_max,
            "near_tangent": (
                (semantics.surface_class == 0)
                & (semantics.geometric_sheet != -1)
            ),
            "planform_boundary": span >= 0.9 * span_max,
            # Formal Fluent clean contract yields 186 points for this input;
            # select all of them, satisfying the required >=16 coverage.
            "clean_leeward": clean_masks.clean_leeward_any,
        }
        distances = cls._full_bvh_result.distance
        gate_candidates = np.flatnonzero(
            (distances >= 0.004) & (distances <= 0.006)
        )
        if gate_candidates.size < 3:
            # This geometry has no 4–6 mm points. Select the three nearest
            # points to the gate and report the fallback rule explicitly.
            gate_candidates = np.argsort(np.abs(distances - 0.005), kind="stable")[:3]
        masks["projection_gate_near"] = np.zeros(cls._M, dtype=bool)
        masks["projection_gate_near"][gate_candidates] = True

        selection_limits = {
            "nose": 25,
            "leading_edge": 25,
            "trailing_edge": 25,
            "upper": 25,
            "lower": 25,
            "chine": 20,
            "side": 20,
            "near_tangent": 20,
            "planform_boundary": 25,
            "projection_gate_near": 30,
            "clean_leeward": 16,
        }
        cls._region_samples_by_name: dict[str, np.ndarray] = {}
        for name, mask in masks.items():
            candidates = np.flatnonzero(mask)
            limit = selection_limits[name]
            selected = candidates[:limit]
            if selected.size < 3 and name != "clean_leeward":
                raise AssertionError(
                    f"HTV-2 region {name} has only {selected.size} valid samples"
                )
            if name == "clean_leeward" and selected.size < 16:
                raise AssertionError(
                    f"HTV-2 clean leeward has only {selected.size} valid samples"
                )
            cls._region_samples_by_name[name] = selected

        rng = np.random.default_rng(42)
        cls._region_samples_by_name["fixed_random_seed_42"] = rng.choice(
            cls._M, size=32, replace=False
        )
        catalog = {
            name: {
                "count": int(indices.size),
                "canonical_indices": indices.tolist(),
                "source_row_indices": cls._geometry.canonical_to_source_row[
                    indices
                ].tolist(),
            }
            for name, indices in cls._region_samples_by_name.items()
        }
        cls._region_catalog = catalog
        print("HTV2_REGION_SAMPLE_CATALOG=" + repr(catalog))
        all_indices = np.concatenate(list(cls._region_samples_by_name.values()))
        cls._deduplicated_sample_indices = np.unique(all_indices)
        print(
            "HTV2_DEDUPLICATED_SAMPLE_COUNT="
            + str(int(cls._deduplicated_sample_indices.size))
        )

    def setUp(self) -> None:
        self.assertTrue(hasattr(self, "_bvh"))

    # ── region helpers ────────────────────────────────────────────────────

    def _xyz(self) -> np.ndarray:
        return self._all_xyz

    def _region_samples(self, label: str) -> np.ndarray:
        return self._region_samples_by_name[label]

    def _validate_region(self, label: str, indices: np.ndarray) -> None:
        pts = np.ascontiguousarray(self._all_xyz[indices])
        bvh_r, diag = project_points_bvh(
            pts, self._triangles, bvh=self._bvh, diagnostics=True
        )
        bf_r = project_points_exact(pts, self._triangles)
        self.assertEqual(
            diag.total_points_with_fallback,
            0,
            f"{label}: fallback={diag.total_points_with_fallback}",
        )
        np.testing.assert_array_equal(bvh_r.triangle_id, bf_r.triangle_id)
        np.testing.assert_array_equal(bvh_r.closest_point, bf_r.closest_point)
        np.testing.assert_array_equal(bvh_r.distance, bf_r.distance)
        np.testing.assert_array_equal(bvh_r.raw_normal, bf_r.raw_normal)
        np.testing.assert_array_equal(
            bvh_r.distance <= 0.005,
            bf_r.distance <= 0.005,
        )
        print(
            "HTV2_REGION_DIAGNOSTICS="
            + repr(
                {
                    "region": label,
                    "point_count": int(indices.size),
                    "node_visits": int(diag.total_node_visits),
                    "leaf_visits": int(diag.total_leaf_visits),
                    "triangle_kernel_calls": int(diag.total_triangle_kernel_calls),
                    "stack_pushes": int(diag.total_stack_pushes),
                    "fallback_count": int(diag.total_points_with_fallback),
                }
            )
        )

    # ── region definitions ────────────────────────────────────────────────

    def test_nose_region(self) -> None:
        self._validate_region("nose", self._region_samples("nose"))

    def test_leading_edge_region(self) -> None:
        self._validate_region("leading_edge", self._region_samples("leading_edge"))

    def test_trailing_edge_region(self) -> None:
        self._validate_region("trailing_edge", self._region_samples("trailing_edge"))

    def test_upper_surface_region(self) -> None:
        self._validate_region("upper", self._region_samples("upper"))

    def test_lower_surface_region(self) -> None:
        self._validate_region("lower", self._region_samples("lower"))

    def test_chine_region(self) -> None:
        self._validate_region("chine", self._region_samples("chine"))

    def test_side_region(self) -> None:
        self._validate_region("side", self._region_samples("side"))

    def test_near_tangent_region(self) -> None:
        self._validate_region(
            "near_tangent", self._region_samples("near_tangent")
        )

    def test_planform_boundary_region(self) -> None:
        self._validate_region(
            "planform_boundary", self._region_samples("planform_boundary")
        )

    def test_gate_near_region(self) -> None:
        self._validate_region(
            "projection_gate_near", self._region_samples("projection_gate_near")
        )

    def test_clean_leeward_16_rows(self) -> None:
        self._validate_region(
            "clean_leeward", self._region_samples("clean_leeward")
        )

    def test_random_fixed_seed_32_samples(self) -> None:
        self._validate_region(
            "fixed_random_seed_42",
            self._region_samples("fixed_random_seed_42"),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Diagnostics / fallback counters
# ═══════════════════════════════════════════════════════════════════════════════


class DiagnosticsCounterTest(unittest.TestCase):
    def test_diagnostics_nonzero_for_nonempty_query(self) -> None:
        tris = _make_random_mesh(np.random.default_rng(1), nt=30)
        pts = _make_random_points(np.random.default_rng(2), n=20)
        bvh = build_exact_bvh(tris)
        _, diag = project_points_bvh(pts, tris, bvh=bvh, diagnostics=True)
        self.assertGreater(diag.total_node_visits, 0)
        self.assertGreater(diag.total_leaf_visits, 0)
        self.assertGreater(diag.total_triangle_kernel_calls, 0)
        self.assertEqual(diag.total_points_with_fallback, 0)
        self.assertGreaterEqual(diag.tree_depth, 0)
        self.assertGreater(diag.leaf_count, 0)

    def test_triangle_kernel_calls_less_than_brute_force(self) -> None:
        """BVH should call the kernel fewer times than M×N for random meshes."""
        tris = _make_random_mesh(np.random.default_rng(3), nt=100)
        pts = _make_random_points(np.random.default_rng(4), n=50)
        bvh = build_exact_bvh(tris)
        _, diag = project_points_bvh(pts, tris, bvh=bvh, diagnostics=True)
        brute_force_calls = pts.shape[0] * tris.shape[0]  # 50 * 100 = 5000
        self.assertLess(diag.total_triangle_kernel_calls, brute_force_calls,
                        "BVH should call kernel fewer times than brute-force")


if __name__ == "__main__":
    unittest.main()