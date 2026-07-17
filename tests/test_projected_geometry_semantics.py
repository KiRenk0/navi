from __future__ import annotations

import unittest

import numpy as np

from ref_enthalpy_method.geometry.local_incidence import (
    NORMAL_SOURCE_INVALID,
    NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER,
    NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION,
    SURFACE_CLASS_INVALID,
    SURFACE_CLASS_LEEWARD,
    SURFACE_CLASS_NEAR_TANGENT,
    SURFACE_CLASS_WINDWARD,
    classify_incidence,
)
from ref_enthalpy_method.geometry.projected_semantics import (
    GEOMETRIC_SHEET_INVALID,
    GEOMETRIC_SHEET_LOWER,
    GEOMETRIC_SHEET_OTHER,
    GEOMETRIC_SHEET_UPPER,
    build_projected_geometry_semantics,
    classify_triangle_geometric_sheets,
)
from ref_enthalpy_method.geometry.qchain_surface import qchain_stl_acceptance
from ref_enthalpy_method.solver_faceted3d import _reject_stl_surface_outliers


def _surface_triangles() -> np.ndarray:
    upper_a = [[0.0, 0.0, 0.2], [1.0, 0.0, 0.2], [0.0, 1.0, 0.2]]
    upper_b = [[1.0, 1.0, 0.2], [0.0, 1.0, 0.2], [1.0, 0.0, 0.2]]
    lower_a = [[0.0, 0.0, -0.2], [0.0, 1.0, -0.2], [1.0, 0.0, -0.2]]
    lower_b = [[1.0, 1.0, -0.2], [1.0, 0.0, -0.2], [0.0, 1.0, -0.2]]
    side = [[0.0, 0.0, -0.2], [1.0, 0.0, -0.2], [0.0, 0.0, 0.2]]
    degenerate = [[2.0, 0.0, 0.0], [2.0, 0.0, 0.0], [2.0, 0.0, 0.0]]
    return np.asarray([upper_a, upper_b, lower_a, lower_b, side, degenerate], dtype=float)


class TriangleSheetIdentityTest(unittest.TestCase):
    def test_upper_lower_shared_boundaries_and_non_skin_states(self) -> None:
        triangles = _surface_triangles()
        sheet = classify_triangle_geometric_sheets(triangles)
        np.testing.assert_array_equal(
            sheet,
            [GEOMETRIC_SHEET_UPPER, GEOMETRIC_SHEET_UPPER, GEOMETRIC_SHEET_LOWER,
             GEOMETRIC_SHEET_LOWER, GEOMETRIC_SHEET_OTHER, GEOMETRIC_SHEET_INVALID],
        )
        self.assertEqual(
            classify_triangle_geometric_sheets(triangles)[1],
            GEOMETRIC_SHEET_UPPER,
        )

    def test_winding_flip_does_not_change_sheet(self) -> None:
        triangles = _surface_triangles()
        flipped = triangles[:, [0, 2, 1], :]
        np.testing.assert_array_equal(
            classify_triangle_geometric_sheets(triangles),
            classify_triangle_geometric_sheets(flipped),
        )


class IncidenceAndAcceptanceTest(unittest.TestCase):
    def test_incidence_classes_and_closed_epsilon_boundaries(self) -> None:
        normals = np.asarray([
            [-1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [-0.05, np.sqrt(1.0 - 0.05**2), 0.0],
            [0.05, np.sqrt(1.0 - 0.05**2), 0.0],
            [np.nan, np.nan, np.nan],
        ])
        _, classes = classify_incidence(normal_out=normals, alpha_deg=0.0, epsilon=0.05)
        np.testing.assert_array_equal(classes, [
            SURFACE_CLASS_WINDWARD,
            SURFACE_CLASS_LEEWARD,
            SURFACE_CLASS_NEAR_TANGENT,
            SURFACE_CLASS_NEAR_TANGENT,
            SURFACE_CLASS_INVALID,
        ])

    def test_qchain_angle_nz_boundaries_and_sheet_references(self) -> None:
        def tilted(angle_deg: float, nz: float = 1.0) -> np.ndarray:
            angle = np.deg2rad(angle_deg)
            return np.asarray([np.sin(angle), 0.0, np.cos(angle)]) if nz > 0 else np.asarray([np.sin(angle), 0.0, -np.cos(angle)])

        nz_boundary = np.asarray([np.sqrt(1.0 - 0.45**2), 0.0, 0.45])
        nz_reject = np.asarray([np.sqrt(1.0 - 0.449**2), 0.0, 0.449])
        candidates = np.asarray([tilted(0), tilted(19.9), tilted(20.1), nz_boundary, nz_reject])
        references = np.asarray([tilted(0), tilted(0), tilted(0), nz_boundary, nz_boundary])
        np.testing.assert_array_equal(
            qchain_stl_acceptance(candidate_normal_out=candidates, reference_normal_out=references),
            [True, True, False, True, False],
        )
        upper_lower = qchain_stl_acceptance(
            candidate_normal_out=np.asarray([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]]),
            reference_normal_out=np.asarray([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]]),
        )
        np.testing.assert_array_equal(upper_lower, [True, True])

    def test_solver_wrapper_mask_matches_shared_contract(self) -> None:
        sx = np.asarray([0.0, np.tan(np.deg2rad(19.9)), np.tan(np.deg2rad(20.1)), np.nan])
        sy = np.zeros_like(sx)
        filtered_sx, filtered_sy = _reject_stl_surface_outliers(sx_arr=sx, sy_arr=sy, ref_sx=0.0, ref_sy=0.0)
        np.testing.assert_array_equal(np.isfinite(filtered_sx) & np.isfinite(filtered_sy), [True, True, False, False])


class ProjectedSemanticsContractTest(unittest.TestCase):
    def _build(self, points: np.ndarray, ids: np.ndarray, *, outline: bool = False):
        kwargs = {}
        if outline:
            kwargs.update(
                outline_x_m=np.asarray([0.0, 1.0, 1.0, 0.0]),
                outline_span_m=np.asarray([0.0, 0.0, 1.0, 1.0]),
            )
        else:
            kwargs.update(c_root_m=2.0, planform_half_angle_deg=45.0)
        return build_projected_geometry_semantics(
            projected_xyz=points,
            triangle_id=ids,
            triangles=_surface_triangles(),
            alpha_deg=0.0,
            planform_b_half_m=1.0,
            chord_min_m=0.02,
            upper_reference_normal_out=np.asarray([0.0, 0.0, 1.0]),
            lower_reference_normal_out=np.asarray([0.0, 0.0, -1.0]),
            **kwargs,
        )

    def test_outward_normal_source_invalid_and_raw_z_independence(self) -> None:
        points = np.asarray([[0.2, 0.2, -9.0], [0.2, 0.2, 9.0], [0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
        result = self._build(points, np.asarray([0, 2, 4, 5]))
        self.assertGreater(result.outward_normal[0, 2], 0.0)
        self.assertLess(result.outward_normal[1, 2], 0.0)
        np.testing.assert_array_equal(result.geometric_sheet, [GEOMETRIC_SHEET_UPPER, GEOMETRIC_SHEET_LOWER, GEOMETRIC_SHEET_OTHER, GEOMETRIC_SHEET_INVALID])
        np.testing.assert_array_equal(result.normal_source, [
            NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER,
            NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER,
            NORMAL_SOURCE_INVALID,
            NORMAL_SOURCE_INVALID,
        ])
        self.assertTrue(np.all(np.isnan(result.outward_normal[2:])))
        np.testing.assert_array_equal(result.surface_class[2:], [SURFACE_CLASS_INVALID, SURFACE_CLASS_INVALID])

    def test_outline_parameterization_raw_ranges_and_outside(self) -> None:
        points = np.asarray([
            [-0.2, 0.0, 0.2], [0.5, 0.5, 0.2], [1.2, 0.999999, 0.2],
            [0.5, -0.2, 0.2], [0.5, 1.2, 0.2],
        ])
        result = self._build(points, np.zeros(5, dtype=int), outline=True)
        np.testing.assert_allclose(result.x_over_c[:3], [-0.2, 0.5, 1.2])
        np.testing.assert_allclose(result.y_over_b, [0.0, 0.5, 0.999999, -0.2, 1.2])
        np.testing.assert_array_equal(result.planform_parameterization_valid, [True, True, True, False, False])
        self.assertTrue(np.all(np.isnan(result.x_over_c[3:])))

    def test_triangular_fallback_root_mid_tip_invalid_and_unclipped(self) -> None:
        points = np.asarray([[0.0, 0.0, 0.2], [1.25, 0.5, 0.2], [1.99, 1.99, 0.2], [2.0, 2.0, 0.2], [-0.2, -0.5, 0.2]])
        result = self._build(points, np.zeros(5, dtype=int))
        np.testing.assert_allclose(result.x_over_c[[0, 1, 4]], [0.0, 0.5, 0.12])
        np.testing.assert_array_equal(result.planform_parameterization_valid, [True, True, False, False, True])
        np.testing.assert_allclose(result.y_over_b, [0.0, 0.5, 1.99, 2.0, -0.5])

    def test_results_are_owned_read_only_and_preserve_order(self) -> None:
        points = np.asarray([[0.8, 0.2, 0.2], [0.1, 0.0, -0.2], [0.4, 0.1, 0.2]])
        ids = np.asarray([1, 2, 0])
        result = self._build(points, ids)
        points[:] = 99.0
        ids[:] = 0
        np.testing.assert_allclose(result.projected_xyz[:, 0], [0.8, 0.1, 0.4])
        np.testing.assert_array_equal(result.triangle_id, [1, 2, 0])
        for value in vars(result).values():
            self.assertFalse(value.flags.writeable)
            self.assertTrue(value.flags.c_contiguous)
            with self.assertRaises(ValueError):
                value.flat[0] = value.flat[0]

    def test_invalid_b_half_fails_clearly(self) -> None:
        with self.assertRaisesRegex(ValueError, "planform_b_half_m"):
            build_projected_geometry_semantics(
                projected_xyz=np.asarray([[0.0, 0.0, 0.2]]),
                triangle_id=np.asarray([0]), triangles=_surface_triangles(), alpha_deg=0.0,
                planform_b_half_m=0.0, chord_min_m=0.02,
                upper_reference_normal_out=np.asarray([0.0, 0.0, 1.0]),
                lower_reference_normal_out=np.asarray([0.0, 0.0, -1.0]),
                c_root_m=2.0, planform_half_angle_deg=45.0,
            )


if __name__ == "__main__":
    unittest.main()