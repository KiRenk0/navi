from __future__ import annotations

import unittest

import numpy as np

from ref_enthalpy_method.geometry.exact_projection import (
    closest_point_on_triangle,
    project_points_exact,
)


_XY_TRIANGLE = np.array(
    [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 2.0, 0.0]],
    dtype=np.float64,
)


class ExactTriangleProjectionTest(unittest.TestCase):
    def assertProjection(
        self,
        point: list[float],
        expected: list[float],
        *,
        triangle: np.ndarray = _XY_TRIANGLE,
    ) -> None:
        projection = closest_point_on_triangle(np.array(point, dtype=np.float64), triangle)
        np.testing.assert_allclose(projection.closest_point, expected, atol=1.0e-15)
        self.assertGreaterEqual(projection.distance, 0.0)

    def test_triangle_interior_vertical_projection(self) -> None:
        projection = closest_point_on_triangle(np.array([0.5, 0.5, 3.0]), _XY_TRIANGLE)
        np.testing.assert_allclose(projection.closest_point, [0.5, 0.5, 0.0], atol=1.0e-15)
        self.assertEqual(projection.distance, 3.0)

    def test_two_differently_oriented_edges_are_selected(self) -> None:
        self.assertProjection([1.0, -1.0, 0.0], [1.0, 0.0, 0.0])
        self.assertProjection([-1.0, 1.0, 0.0], [0.0, 1.0, 0.0])
        self.assertProjection([1.5, 1.5, 0.0], [1.0, 1.0, 0.0])

    def test_two_distinct_vertices_are_selected(self) -> None:
        self.assertProjection([-2.0, -1.0, 0.0], [0.0, 0.0, 0.0])
        self.assertProjection([3.0, -1.0, 0.0], [2.0, 0.0, 0.0])

    def test_coplanar_projection_outside_triangle_uses_boundary(self) -> None:
        projection = closest_point_on_triangle(np.array([1.8, 1.0, 0.0]), _XY_TRIANGLE)
        np.testing.assert_allclose(projection.closest_point, [1.4, 0.6, 0.0], atol=1.0e-15)
        self.assertAlmostEqual(projection.distance, np.sqrt(0.32), places=15)

    def test_degenerate_collinear_triangle_reduces_to_segments(self) -> None:
        triangle = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        projection = closest_point_on_triangle(np.array([1.5, 2.0, 0.0]), triangle)
        np.testing.assert_allclose(projection.closest_point, [1.5, 0.0, 0.0], atol=0.0)
        self.assertEqual(projection.distance, 2.0)
        np.testing.assert_array_equal(np.isnan(projection.raw_normal), [True, True, True])

    def test_fully_collapsed_triangle_returns_shared_vertex(self) -> None:
        triangle = np.repeat(np.array([[4.0, -2.0, 1.0]]), 3, axis=0)
        projection = closest_point_on_triangle(np.array([5.0, -2.0, 1.0]), triangle)
        np.testing.assert_array_equal(projection.closest_point, triangle[0])
        self.assertEqual(projection.distance, 1.0)
        np.testing.assert_array_equal(np.isnan(projection.raw_normal), [True, True, True])

    def test_raw_normal_strictly_follows_input_winding(self) -> None:
        forward = closest_point_on_triangle(np.array([0.2, 0.2, 1.0]), _XY_TRIANGLE)
        reversed_winding = closest_point_on_triangle(np.array([0.2, 0.2, 1.0]), _XY_TRIANGLE[[0, 2, 1]])
        np.testing.assert_array_equal(forward.raw_normal, [0.0, 0.0, 1.0])
        np.testing.assert_array_equal(reversed_winding.raw_normal, [0.0, 0.0, -1.0])

    def test_single_triangle_input_contract_rejects_invalid_values(self) -> None:
        invalid_cases = (
            (np.zeros((1, 3)), _XY_TRIANGLE),
            (np.zeros(3), np.zeros((2, 3))),
            (np.array([np.nan, 0.0, 0.0]), _XY_TRIANGLE),
            (np.zeros(3), np.array([[0.0, 0.0, 0.0], [np.inf, 0.0, 0.0], [0.0, 1.0, 0.0]])),
        )
        for point, triangle in invalid_cases:
            with self.subTest(point_shape=point.shape, triangle_shape=triangle.shape):
                with self.assertRaises(ValueError):
                    closest_point_on_triangle(point, triangle)


class ExactSurfaceProjectionTest(unittest.TestCase):
    def test_global_nearest_triangle_is_selected(self) -> None:
        triangles = np.stack([_XY_TRIANGLE + [0.0, 0.0, 5.0], _XY_TRIANGLE])
        result = project_points_exact(np.array([[0.5, 0.5, 0.2]]), triangles)
        np.testing.assert_array_equal(result.triangle_id, [1])
        np.testing.assert_allclose(result.closest_point, [[0.5, 0.5, 0.0]], atol=1.0e-15)
        np.testing.assert_allclose(result.distance, [0.2], atol=1.0e-15)

    def test_equal_and_tolerance_equivalent_distances_choose_smallest_index(self) -> None:
        point = np.array([[0.25, 0.25, 0.0]])
        equal = np.stack([_XY_TRIANGLE + [0.0, 0.0, 1.0], _XY_TRIANGLE + [0.0, 0.0, -1.0]])
        within_tolerance = np.stack([_XY_TRIANGLE + [0.0, 0.0, 1.0 + 5.0e-13], _XY_TRIANGLE + [0.0, 0.0, -1.0]])
        np.testing.assert_array_equal(project_points_exact(point, equal).triangle_id, [0])
        np.testing.assert_array_equal(project_points_exact(point, within_tolerance).triangle_id, [0])

    def test_long_triangle_beats_nearby_centroid_triangle(self) -> None:
        long_triangle = np.array([[0.0, 0.0, 0.0], [300.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        near_centroid_but_far_surface = np.array([[0.0, 0.0, 5.0], [1.0, 0.0, 5.0], [0.0, 1.0, 5.0]])
        point = np.array([[0.1, 0.1, 0.2]])
        triangles = np.stack([near_centroid_but_far_surface, long_triangle])
        centroid_distances = np.linalg.norm(triangles.mean(axis=1) - point[0], axis=1)
        self.assertLess(centroid_distances[0], centroid_distances[1])
        result = project_points_exact(point, triangles)
        np.testing.assert_array_equal(result.triangle_id, [1])
        np.testing.assert_allclose(result.distance, [0.2], atol=1.0e-15)

    def test_batch_matches_independently_derived_expected_values(self) -> None:
        points = np.array([[0.2, 0.3, 0.4], [4.2, 0.2, 0.1], [-1.0, -1.0, 0.0]])
        triangles = np.stack([_XY_TRIANGLE, _XY_TRIANGLE + [4.0, 0.0, 0.0]])
        batch = project_points_exact(points, triangles)

        np.testing.assert_array_equal(batch.triangle_id, [0, 1, 0])
        np.testing.assert_allclose(
            batch.closest_point,
            [[0.2, 0.3, 0.0], [4.2, 0.2, 0.0], [0.0, 0.0, 0.0]],
            atol=0.0,
        )
        np.testing.assert_allclose(batch.distance, [0.4, 0.1, np.sqrt(2.0)], atol=1.0e-15)
        np.testing.assert_array_equal(batch.raw_normal, [[0.0, 0.0, 1.0]] * 3)

    def test_inputs_are_byte_and_value_unchanged(self) -> None:
        point = np.array([0.2, 0.3, 0.4], dtype=np.float64)
        triangle = _XY_TRIANGLE.copy()
        points = np.array([[0.2, 0.3, 0.4], [0.5, 0.5, -1.0]], dtype=np.float64)
        triangles = np.stack([triangle, triangle + [0.0, 0.0, 2.0]])
        originals = [(array, array.copy(), array.tobytes()) for array in (point, triangle, points, triangles)]
        closest_point_on_triangle(point, triangle)
        project_points_exact(points, triangles)
        for array, values, byte_string in originals:
            np.testing.assert_array_equal(array, values)
            self.assertEqual(array.tobytes(), byte_string)

    def test_surface_input_contract_rejects_invalid_values(self) -> None:
        valid_points = np.zeros((1, 3))
        valid_triangles = np.stack([_XY_TRIANGLE])
        invalid_cases = (
            (np.zeros(3), valid_triangles),
            (valid_points, np.zeros((1, 3, 2))),
            (valid_points, np.empty((0, 3, 3))),
            (np.array([[np.inf, 0.0, 0.0]]), valid_triangles),
            (valid_points, np.full((1, 3, 3), np.nan)),
        )
        for points, triangles in invalid_cases:
            with self.subTest(points_shape=points.shape, triangles_shape=triangles.shape):
                with self.assertRaises(ValueError):
                    project_points_exact(points, triangles)

    def test_repeated_calls_are_bitwise_deterministic(self) -> None:
        points = np.array([[0.5, 0.5, 1.0], [3.0, 0.2, 0.1]])
        triangles = np.stack([_XY_TRIANGLE, _XY_TRIANGLE + [3.0, 0.0, 0.0]])
        first = project_points_exact(points, triangles)
        second = project_points_exact(points, triangles)
        np.testing.assert_array_equal(first.triangle_id, second.triangle_id)
        np.testing.assert_array_equal(first.closest_point, second.closest_point)
        np.testing.assert_array_equal(first.distance, second.distance)
        np.testing.assert_array_equal(first.raw_normal, second.raw_normal)


if __name__ == "__main__":
    unittest.main()