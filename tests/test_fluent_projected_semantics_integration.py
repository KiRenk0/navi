from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from ref_enthalpy_method.mapping.fluent_projection import project_fluent_surface_exact
from ref_enthalpy_method.mapping.fluent_semantics import integrate_fluent_projected_semantics
from ref_enthalpy_method.mapping.fluent_surface import (
    compare_canonical_geometry,
    read_fluent_surface_geometry_csv,
)
from scripts.tools.faceted3d_phase4b_geometry_qa import _execution_metadata

_HEADER = "cellnumber,x-coordinate,y-coordinate,z-coordinate\n"


def _surface_triangles() -> np.ndarray:
    upper_a = [[0.0, 0.0, 0.2], [1.0, 0.0, 0.2], [0.0, 1.0, 0.2]]
    upper_b = [[1.0, 1.0, 0.2], [0.0, 1.0, 0.2], [1.0, 0.0, 0.2]]
    lower_a = [[0.0, 0.0, -0.2], [0.0, 1.0, -0.2], [1.0, 0.0, -0.2]]
    lower_b = [[1.0, 1.0, -0.2], [1.0, 0.0, -0.2], [0.0, 1.0, -0.2]]
    return np.asarray([upper_a, upper_b, lower_a, lower_b], dtype=np.float64)


class FluentProjectedSemanticsIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.triangles = _surface_triangles()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _geometry(
        self,
        rows: list[tuple[str, float, float, float]],
        *,
        name: str = "surface.csv",
    ):
        path = self.root / name
        path.write_text(
            _HEADER
            + "".join(
                f"{cellnumber},{x - 0.030},{span},{up}\n"
                for cellnumber, x, span, up in rows
            ),
            encoding="utf-8",
        )
        return read_fluent_surface_geometry_csv(path, x_offset_m=0.030)

    @staticmethod
    def _readonly(value, dtype=None):
        array = np.array(value, dtype=dtype, copy=True, order="C")
        array.setflags(write=False)
        return array

    def _integrate(self, geometry, *, gate: float = 0.005, projection=None):
        if projection is None:
            projection = project_fluent_surface_exact(
                geometry,
                self.triangles,
                projection_gate_m=gate,
            )
        return integrate_fluent_projected_semantics(
            geometry=geometry,
            projection=projection,
            triangles=self.triangles,
            alpha_deg=5.0,
            planform_b_half_m=1.0,
            chord_min_m=0.02,
            upper_reference_normal_out=np.asarray([0.0, 0.0, 1.0]),
            lower_reference_normal_out=np.asarray([0.0, 0.0, -1.0]),
            outline_x_m=np.asarray([0.0, 1.0, 1.0, 0.0]),
            outline_span_m=np.asarray([0.0, 0.0, 1.0, 1.0]),
        )

    def test_happy_path_preserves_projection_identity_and_array_contract(self) -> None:
        geometry = self._geometry(
            [("u", 0.2, 0.2, 0.201), ("l", 0.8, 0.8, -0.201)]
        )
        projection = project_fluent_surface_exact(
            geometry,
            self.triangles,
            projection_gate_m=0.005,
        )
        result = self._integrate(geometry, projection=projection)
        self.assertIs(result.projection, projection)
        np.testing.assert_array_equal(result.semantics.triangle_id, result.projection.triangle_id)
        self.assertEqual(
            result.semantics.projected_xyz.tobytes(order="C"),
            result.projection.projected_xyz.tobytes(order="C"),
        )
        self.assertEqual(result.geometry_qa["identity"]["point_count"], 2)
        self.assertEqual(result.geometry_qa["normal_source"]["3_analytic_fallback"]["count"], 0)
        for value in vars(result.semantics).values():
            self.assertTrue(value.flags.owndata)
            self.assertTrue(value.flags.c_contiguous)
            self.assertFalse(value.flags.writeable)

    def test_canonical_order_and_scalar_integer_boolean_vector_round_trip(self) -> None:
        geometry = self._geometry(
            [("third", 0.8, 0.8, -0.201), ("first", 0.2, 0.2, 0.201), ("second", 0.4, 0.4, 0.201)]
        )
        result = self._integrate(geometry)
        np.testing.assert_array_equal(result.projection.canonical_index, [0, 1, 2])
        self.assertTrue(all(result.ordering_round_trip.values()))
        for field in (
            "incidence_s",
            "triangle_id",
            "qchain_stl_accepted",
            "outward_normal",
        ):
            self.assertTrue(result.ordering_round_trip[field])

    def test_reordered_sources_with_equal_canonical_geometry_are_byte_identical(self) -> None:
        rows = [
            ("a", 0.2, 0.2, 0.201),
            ("b", 0.8, 0.8, -0.201),
            ("c", 0.4, 0.4, 0.201),
        ]
        left_geometry = self._geometry(rows, name="left.csv")
        right_geometry = self._geometry(list(reversed(rows)), name="right.csv")
        comparison = compare_canonical_geometry(left_geometry, right_geometry)
        self.assertTrue(comparison.equal)
        left = self._integrate(left_geometry)
        right = self._integrate(right_geometry)
        for field in vars(left.semantics):
            self.assertEqual(
                getattr(left.semantics, field).tobytes(order="C"),
                getattr(right.semantics, field).tobytes(order="C"),
            )
        self.assertEqual(left.deterministic_qa_json(), right.deterministic_qa_json())

    def test_qa_serialization_has_stable_key_order_and_repeats_exactly(self) -> None:
        geometry = self._geometry([("u", 0.2, 0.2, 0.201)])
        first = self._integrate(geometry)
        second = self._integrate(geometry)
        expected_keys = [
            "schema",
            "identity",
            "geometric_sheet",
            "normal_source",
            "aerodynamic_surface_class",
            "planform_parameters",
            "semantic_validity",
            "projection_gate_x_semantic_validity",
            "geometric_sheet_x_normal_source",
            "geometric_sheet_x_surface_class",
            "consistency",
            "canonical_source_round_trip",
        ]
        self.assertEqual(list(first.geometry_qa), expected_keys)
        self.assertEqual(first.deterministic_qa_json(), second.deterministic_qa_json())

    def test_raw_planform_outliers_are_counted_without_clipping(self) -> None:
        wide_triangles = _surface_triangles().copy()
        wide_triangles[:, :, 0] = wide_triangles[:, :, 0] * 2.0 - 0.5
        wide_triangles[:, :, 1] *= 1.5
        geometry = self._geometry(
            [("before", -0.2, 0.2, 0.201), ("after", 1.2, 0.2, 0.201), ("span", 0.5, 1.2, 0.201)]
        )
        projection = project_fluent_surface_exact(geometry, wide_triangles, projection_gate_m=1.0)
        result = integrate_fluent_projected_semantics(
            geometry=geometry,
            projection=projection,
            triangles=wide_triangles,
            alpha_deg=5.0,
            planform_b_half_m=1.0,
            chord_min_m=0.02,
            upper_reference_normal_out=np.asarray([0.0, 0.0, 1.0]),
            lower_reference_normal_out=np.asarray([0.0, 0.0, -1.0]),
            outline_x_m=np.asarray([0.0, 1.0, 1.0, 0.0]),
            outline_span_m=np.asarray([0.0, 0.0, 1.5, 1.5]),
        )
        x_stats = result.geometry_qa["planform_parameters"]["x_over_c"]
        y_stats = result.geometry_qa["planform_parameters"]["y_over_b"]
        self.assertEqual(x_stats["less_than_zero_count"], 1)
        self.assertEqual(x_stats["greater_than_one_count"], 1)
        self.assertLess(x_stats["min"], 0.0)
        self.assertGreater(x_stats["max"], 1.0)
        self.assertEqual(y_stats["greater_than_one_count"], 1)
        np.testing.assert_allclose(result.semantics.y_over_b, [0.2, 1.2, 0.2])

    def test_projection_gate_and_semantic_validity_remain_independent(self) -> None:
        geometry = self._geometry(
            [("pass", 0.2, 0.2, 0.201), ("fail", 0.8, 0.8, -0.210)]
        )
        result = self._integrate(geometry, gate=0.005)
        cross = result.geometry_qa["projection_gate_x_semantic_validity"]
        self.assertEqual(cross["gate_pass_semantic_valid"], 1)
        self.assertEqual(cross["gate_fail_semantic_valid"], 1)
        self.assertEqual(result.geometry_qa["semantic_validity"]["valid_count"], 2)
        self.assertIn("projection gate", result.geometry_qa["semantic_validity"]["definition"])

    def test_projection_contract_rejects_corrupted_fields_fail_closed(self) -> None:
        geometry = self._geometry(
            [("u1", 0.2, 0.2, 0.201), ("u2", 0.8, 0.8, 0.202)]
        )
        projection = project_fluent_surface_exact(
            geometry, self.triangles, projection_gate_m=0.005
        )
        writeable_projected = projection.projected_xyz.copy()
        fortran_projected = np.asfortranarray(projection.projected_xyz)
        fortran_projected.setflags(write=False)
        non_owned_projected = projection.projected_xyz.view()
        invalid_projections = (
            replace(projection, canonical_geometry_sha256="0" * 64),
            replace(
                projection,
                projected_xyz=self._readonly(projection.projected_xyz, np.float32),
            ),
            replace(
                projection,
                triangle_id=self._readonly(projection.triangle_id, np.int32),
            ),
            replace(
                projection,
                projection_distance_m=self._readonly(
                    projection.projection_distance_m[:1], np.float64
                ),
            ),
            replace(
                projection,
                projection_distance_m=self._readonly([np.nan, 0.0], np.float64),
            ),
            replace(
                projection,
                projection_distance_m=self._readonly([-1.0, 0.0], np.float64),
            ),
            replace(
                projection,
                raw_normal=self._readonly(projection.raw_normal[:, :2], np.float64),
            ),
            replace(projection, projection_gate_m=0.0),
            replace(projection, projection_gate_m=np.inf),
            replace(
                projection,
                projection_gate_pass=self._readonly(
                    projection.projection_gate_pass, np.int8
                ),
            ),
            replace(
                projection,
                projection_gate_pass=self._readonly(
                    projection.projection_gate_pass[:1], np.bool_
                ),
            ),
            replace(
                projection,
                projection_gate_pass=self._readonly(
                    ~projection.projection_gate_pass, np.bool_
                ),
            ),
            replace(projection, projected_xyz=writeable_projected),
            replace(projection, projected_xyz=fortran_projected),
            replace(projection, projected_xyz=non_owned_projected),
        )
        for invalid_projection in invalid_projections:
            with self.subTest(projection=invalid_projection):
                with self.assertRaises(ValueError):
                    self._integrate(geometry, projection=invalid_projection)

    def test_formal_qa_execution_metadata_distinguishes_chunk_calls_and_reuse(self) -> None:
        metadata = _execution_metadata(8)
        self.assertEqual(
            metadata["exact_kernel_invocation_count"],
            metadata["projection_chunk_count"],
        )
        self.assertEqual(metadata["formal_projection_dataset_count"], 1)
        self.assertTrue(metadata["projection_reused_after_canonical_identity"])
        self.assertFalse(metadata["independent_second_projection_executed"])

    def test_invalid_parameters_shapes_dtypes_and_projection_identity_fail_closed(self) -> None:
        geometry = self._geometry([("u", 0.2, 0.2, 0.201)])
        projection = project_fluent_surface_exact(
            geometry, self.triangles, projection_gate_m=0.005
        )
        common = dict(
            geometry=geometry,
            projection=projection,
            triangles=self.triangles,
            alpha_deg=5.0,
            planform_b_half_m=1.0,
            chord_min_m=0.02,
            upper_reference_normal_out=np.asarray([0.0, 0.0, 1.0]),
            lower_reference_normal_out=np.asarray([0.0, 0.0, -1.0]),
            c_root_m=1.0,
            planform_half_angle_deg=45.0,
        )
        invalid_cases = (
            {"triangles": self.triangles.astype(np.float32)},
            {"triangles": np.zeros((4, 3, 2), dtype=np.float64)},
            {"planform_b_half_m": 0.0},
            {"chord_min_m": np.nan},
            {"projection": replace(projection, solver_xyz=projection.solver_xyz + np.asarray([[0.1, 0.0, 0.0]]))},
            {"projection": replace(projection, triangle_count=99)},
        )
        for updates in invalid_cases:
            with self.subTest(updates=tuple(updates)):
                with self.assertRaises(ValueError):
                    integrate_fluent_projected_semantics(**{**common, **updates})


if __name__ == "__main__":
    unittest.main()
