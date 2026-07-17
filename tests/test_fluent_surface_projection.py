from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from ref_enthalpy_method.geometry.exact_projection import (
    SurfaceProjection,
    project_points_exact,
)
from ref_enthalpy_method.mapping.fluent_projection import (
    canonical_values_to_source_order,
    project_fluent_surface_exact,
)
from ref_enthalpy_method.mapping.fluent_surface import read_fluent_surface_geometry_csv


_HEADER = "cellnumber,x-coordinate,y-coordinate,z-coordinate\n"
_XY_TRIANGLE = np.array(
    [[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 2.0, 0.0]],
    dtype=np.float64,
)


class FluentSurfaceProjectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def load_geometry(self, rows: list[tuple[str, float, float, float]], *, name: str = "surface.csv"):
        path = self.root / name
        text = _HEADER + "".join(
            f"{cellnumber},{x},{span},{up}\n"
            for cellnumber, x, span, up in rows
        )
        path.write_text(text, encoding="utf-8")
        return read_fluent_surface_geometry_csv(path, x_offset_m=0.030)

    def test_adapter_passes_complete_canonical_points_and_mesh_to_formal_kernel(self) -> None:
        geometry = self.load_geometry(
            [("9", 0.47, 0.5, 0.3), ("8", -0.03, 0.2, 0.1)]
        )
        triangles = np.stack([_XY_TRIANGLE, _XY_TRIANGLE + [0.0, 0.0, 5.0]])
        expected = SurfaceProjection(
            triangle_id=np.array([0, 1]),
            closest_point=np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]),
            distance=np.array([0.001, 0.002]),
            raw_normal=np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]]),
        )
        with mock.patch(
            "ref_enthalpy_method.mapping.fluent_projection.project_points_exact",
            return_value=expected,
        ) as kernel:
            result = project_fluent_surface_exact(
                geometry, triangles, projection_gate_m=0.005
            )
        kernel.assert_called_once()
        passed_points, passed_triangles = kernel.call_args.args
        np.testing.assert_array_equal(passed_points, geometry.canonical_solver_xyz)
        np.testing.assert_array_equal(passed_triangles, triangles)
        self.assertEqual(passed_points.shape, (2, 3))
        self.assertEqual(passed_triangles.shape, (2, 3, 3))
        np.testing.assert_array_equal(result.solver_xyz, geometry.canonical_solver_xyz)

    def test_interior_edge_vertex_and_global_nearest_projection(self) -> None:
        geometry = self.load_geometry(
            [
                ("1", 0.47, 0.5, 0.4),
                ("2", 0.97, -1.0, 0.0),
                ("3", -2.03, -1.0, 0.0),
                ("4", 4.47, 0.5, 0.2),
            ]
        )
        triangles = np.stack([_XY_TRIANGLE, _XY_TRIANGLE + [4.0, 0.0, 0.0]])
        result = project_fluent_surface_exact(geometry, triangles, projection_gate_m=3.0)
        np.testing.assert_array_equal(result.triangle_id, [0, 0, 0, 1])
        np.testing.assert_allclose(
            result.projected_xyz,
            [[0.0, 0.0, 0.0], [0.5, 0.5, 0.0], [1.0, 0.0, 0.0], [4.5, 0.5, 0.0]],
            atol=1.0e-15,
        )
        np.testing.assert_array_equal(result.raw_normal, [[0.0, 0.0, 1.0]] * 4)

    def test_gate_is_closed_at_boundary(self) -> None:
        geometry = self.load_geometry(
            [("1", 0.17, 0.2, 0.004), ("2", 0.27, 0.2, 0.005), ("3", 0.37, 0.2, 0.006)]
        )
        result = project_fluent_surface_exact(
            geometry, np.stack([_XY_TRIANGLE]), projection_gate_m=0.005
        )
        np.testing.assert_allclose(result.projection_distance_m, [0.004, 0.005, 0.006])
        np.testing.assert_array_equal(result.projection_gate_pass, [True, True, False])

    def test_canonical_index_and_projection_are_source_order_independent(self) -> None:
        rows = [("7", 0.47, 0.5, 0.3), ("7", -0.03, 0.2, 0.1), ("9", 0.97, 0.1, 0.2)]
        first = self.load_geometry(rows, name="first.csv")
        second = self.load_geometry(list(reversed(rows)), name="second.csv")
        triangles = np.stack([_XY_TRIANGLE])
        left = project_fluent_surface_exact(first, triangles, projection_gate_m=1.0)
        right = project_fluent_surface_exact(second, triangles, projection_gate_m=1.0)
        np.testing.assert_array_equal(left.canonical_index, np.arange(3))
        for field in (
            "solver_xyz", "projected_xyz", "triangle_id", "projection_distance_m",
            "raw_normal", "projection_gate_pass",
        ):
            np.testing.assert_array_equal(getattr(left, field), getattr(right, field))
        self.assertEqual(left.canonical_geometry_sha256, right.canonical_geometry_sha256)
        self.assertEqual(first.cellnumber[0], first.cellnumber[1])

    def test_canonical_fields_restore_two_source_orderings_and_round_trip(self) -> None:
        rows = [("1", 2.0, 0.0, 0.0), ("2", 0.0, 0.0, 0.0), ("3", 1.0, 0.0, 0.0)]
        first = self.load_geometry(rows, name="first.csv")
        second = self.load_geometry([rows[1], rows[0], rows[2]], name="second.csv")
        canonical = np.array([[10.0, 11.0], [20.0, 21.0], [30.0, 31.0]])
        for geometry in (first, second):
            source = canonical_values_to_source_order(
                canonical, geometry.source_to_canonical_row
            )
            restored = source[geometry.canonical_to_source_row]
            np.testing.assert_array_equal(restored, canonical)
        np.testing.assert_array_equal(
            canonical_values_to_source_order(
                np.array([10, 20, 30]), first.source_to_canonical_row
            ),
            [30, 10, 20],
        )
        np.testing.assert_array_equal(
            canonical_values_to_source_order(
                np.array([10, 20, 30]), second.source_to_canonical_row
            ),
            [10, 30, 20],
        )

    def test_inputs_unchanged_and_outputs_owned_c_contiguous_read_only(self) -> None:
        geometry = self.load_geometry([("1", 0.17, 0.2, 0.3), ("2", 0.37, 0.4, 0.5)])
        triangles = np.stack([_XY_TRIANGLE])
        triangle_copy = triangles.copy()
        geometry_bytes = geometry.canonical_solver_xyz.tobytes(order="C")
        result = project_fluent_surface_exact(geometry, triangles, projection_gate_m=1.0)
        np.testing.assert_array_equal(triangles, triangle_copy)
        self.assertEqual(geometry.canonical_solver_xyz.tobytes(order="C"), geometry_bytes)
        arrays = (
            result.canonical_index, result.solver_xyz, result.projected_xyz,
            result.triangle_id, result.projection_distance_m, result.raw_normal,
            result.projection_gate_pass,
        )
        for value in arrays:
            self.assertTrue(value.flags.c_contiguous)
            self.assertTrue(value.flags.owndata)
            self.assertFalse(value.flags.writeable)
            self.assertFalse(np.shares_memory(value, triangles))
            self.assertFalse(np.shares_memory(value, geometry.solver_xyz))
        for index, left in enumerate(arrays):
            for right in arrays[index + 1:]:
                self.assertFalse(np.shares_memory(left, right))

    def test_repeated_calls_are_bitwise_deterministic(self) -> None:
        geometry = self.load_geometry([("1", 0.17, 0.2, 0.3), ("2", 3.97, 0.2, 0.1)])
        triangles = np.stack([_XY_TRIANGLE, _XY_TRIANGLE + [4.0, 0.0, 0.0]])
        first = project_fluent_surface_exact(geometry, triangles, projection_gate_m=1.0)
        second = project_fluent_surface_exact(geometry, triangles, projection_gate_m=1.0)
        for field in (
            "canonical_index", "solver_xyz", "projected_xyz", "triangle_id",
            "projection_distance_m", "raw_normal", "projection_gate_pass",
        ):
            np.testing.assert_array_equal(getattr(first, field), getattr(second, field))

    def test_invalid_gate_fails_fast(self) -> None:
        geometry = self.load_geometry([("1", 0.0, 0.0, 0.0)])
        for gate in (0.0, -1.0, np.nan, np.inf, -np.inf):
            with self.subTest(gate=gate):
                with self.assertRaisesRegex(ValueError, "projection_gate_m"):
                    project_fluent_surface_exact(geometry, np.stack([_XY_TRIANGLE]), projection_gate_m=gate)

    def test_invalid_triangles_fail_fast(self) -> None:
        geometry = self.load_geometry([("1", 0.0, 0.0, 0.0)])
        invalid = (
            np.zeros((1, 3, 2)), np.empty((0, 3, 3)),
            np.full((1, 3, 3), np.nan), np.full((1, 3, 3), np.inf),
        )
        for triangles in invalid:
            with self.subTest(shape=triangles.shape):
                with self.assertRaises(ValueError):
                    project_fluent_surface_exact(geometry, triangles, projection_gate_m=1.0)

    def test_empty_geometry_fails_fast(self) -> None:
        geometry = mock.Mock()
        geometry.canonical_solver_xyz = np.empty((0, 3), dtype=np.float64)
        with self.assertRaisesRegex(ValueError, "at least one point"):
            project_fluent_surface_exact(
                geometry, np.stack([_XY_TRIANGLE]), projection_gate_m=1.0
            )

    def test_ordering_helper_rejects_shape_dtype_and_nonpermutation(self) -> None:
        values = np.arange(3)
        invalid = (
            np.array([[0, 1, 2]]), np.array([0, 1]),
            np.array([0.0, 1.0, 2.0]), np.array([0, 0, 2]), np.array([-1, 1, 2]),
        )
        for mapping in invalid:
            with self.subTest(mapping=mapping):
                with self.assertRaises(ValueError):
                    canonical_values_to_source_order(values, mapping)
        with self.assertRaisesRegex(ValueError, "at least one dimension"):
            canonical_values_to_source_order(np.array(1), np.array([0]))

    def test_degenerate_triangle_nan_normal_is_preserved(self) -> None:
        geometry = self.load_geometry([("1", 0.97, 2.0, 0.0)])
        degenerate = np.array([[[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [1.0, 0.0, 0.0]]])
        result = project_fluent_surface_exact(geometry, degenerate, projection_gate_m=3.0)
        np.testing.assert_array_equal(np.isnan(result.raw_normal), [[True, True, True]])

    def test_invalid_kernel_outputs_fail_fast(self) -> None:
        geometry = self.load_geometry([("1", 0.17, 0.2, 0.3)])
        triangles = np.stack([_XY_TRIANGLE])
        valid = dict(
            triangle_id=np.array([0]), closest_point=np.array([[0.2, 0.2, 0.0]]),
            distance=np.array([0.3]), raw_normal=np.array([[0.0, 0.0, 1.0]]),
        )
        invalid_results = (
            SurfaceProjection(**{**valid, "triangle_id": np.array([1])}),
            SurfaceProjection(**{**valid, "closest_point": np.array([[np.nan, 0.0, 0.0]])}),
            SurfaceProjection(**{**valid, "distance": np.array([-1.0])}),
            SurfaceProjection(**{**valid, "raw_normal": np.array([[np.nan, np.nan, np.nan]])}),
            SurfaceProjection(**{**valid, "distance": np.array([0.3, 0.4])}),
        )
        for kernel_result in invalid_results:
            with self.subTest(kernel_result=kernel_result):
                with mock.patch(
                    "ref_enthalpy_method.mapping.fluent_projection.project_points_exact",
                    return_value=kernel_result,
                ):
                    with self.assertRaises(ValueError):
                        project_fluent_surface_exact(geometry, triangles, projection_gate_m=1.0)

    def test_contiguous_point_chunk_sizes_preserve_exact_truth(self) -> None:
        points = np.array(
            [
                [0.2, 0.2, 0.1], [0.4, 0.4, 0.2], [1.0, -1.0, 0.3],
                [4.2, 0.2, 0.4], [4.4, 0.4, 0.5], [6.0, 0.0, 0.6],
            ],
            dtype=np.float64,
        )
        triangles = np.stack([_XY_TRIANGLE, _XY_TRIANGLE + [4.0, 0.0, 0.0]])
        expected = project_points_exact(points, triangles)
        for chunk_size in (1, 2, 4, 6):
            chunks = [
                project_points_exact(points[start:start + chunk_size], triangles)
                for start in range(0, points.shape[0], chunk_size)
            ]
            np.testing.assert_array_equal(
                np.concatenate([chunk.triangle_id for chunk in chunks]),
                expected.triangle_id,
            )
            np.testing.assert_array_equal(
                np.concatenate([chunk.closest_point for chunk in chunks]),
                expected.closest_point,
            )
            np.testing.assert_array_equal(
                np.concatenate([chunk.distance for chunk in chunks]), expected.distance
            )
            np.testing.assert_array_equal(
                np.concatenate([chunk.raw_normal for chunk in chunks]), expected.raw_normal
            )

    def test_long_triangle_inherits_exhaustive_exact_truth(self) -> None:
        long_triangle = np.array([[0.0, 0.0, 0.0], [300.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        near_centroid_far_surface = np.array([[0.0, 0.0, 5.0], [1.0, 0.0, 5.0], [0.0, 1.0, 5.0]])
        triangles = np.stack([near_centroid_far_surface, long_triangle])
        geometry = self.load_geometry([("1", 0.07, 0.1, 0.2)])
        point = geometry.canonical_solver_xyz[0]
        self.assertLess(
            np.linalg.norm(triangles[0].mean(axis=0) - point),
            np.linalg.norm(triangles[1].mean(axis=0) - point),
        )
        adapter = project_fluent_surface_exact(geometry, triangles, projection_gate_m=1.0)
        exact = project_points_exact(geometry.canonical_solver_xyz, triangles)
        np.testing.assert_array_equal(adapter.triangle_id, exact.triangle_id)
        np.testing.assert_array_equal(adapter.projected_xyz, exact.closest_point)
        np.testing.assert_array_equal(adapter.projection_distance_m, exact.distance)
        np.testing.assert_array_equal(adapter.raw_normal, exact.raw_normal)
        np.testing.assert_array_equal(adapter.triangle_id, [1])


if __name__ == "__main__":
    unittest.main()
