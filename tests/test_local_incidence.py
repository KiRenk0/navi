from __future__ import annotations

import unittest

import numpy as np

from ref_enthalpy_method.geometry.local_incidence import (
    NORMAL_SOURCE_ANALYTIC_FALLBACK_NO_STL_COVERAGE,
    NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION,
    SURFACE_CLASS_LEEWARD,
    SURFACE_CLASS_NEAR_TANGENT,
    SURFACE_CLASS_WINDWARD,
    classify_incidence,
    diagnose_sheet,
    diagnose_sheet_from_geometry,
    freestream_velocity_direction,
    orient_outward_normal,
    outward_normal_from_slopes,
)
from ref_enthalpy_method.solver_faceted3d import _reject_stl_surface_outliers


class LocalIncidenceTest(unittest.TestCase):
    def test_horizontal_plate_alpha_zero_is_near_tangent(self) -> None:
        upper, s_upper, class_upper = diagnose_sheet(sx=np.array([0.0]), sy=np.array([0.0]), sheet="upper", alpha_deg=0.0)
        lower, s_lower, class_lower = diagnose_sheet(sx=np.array([0.0]), sy=np.array([0.0]), sheet="lower", alpha_deg=0.0)
        np.testing.assert_allclose(upper[0], [0.0, 0.0, 1.0], atol=0.0)
        np.testing.assert_allclose(lower[0], [0.0, 0.0, -1.0], atol=0.0)
        self.assertEqual(float(s_upper[0]), 0.0)
        self.assertEqual(float(s_lower[0]), 0.0)
        self.assertEqual(int(class_upper[0]), SURFACE_CLASS_NEAR_TANGENT)
        self.assertEqual(int(class_lower[0]), SURFACE_CLASS_NEAR_TANGENT)

    def test_horizontal_plate_positive_alpha(self) -> None:
        _, _, upper = diagnose_sheet(sx=np.array([0.0]), sy=np.array([0.0]), sheet="upper", alpha_deg=5.0)
        _, _, lower = diagnose_sheet(sx=np.array([0.0]), sy=np.array([0.0]), sheet="lower", alpha_deg=5.0)
        self.assertEqual(int(lower[0]), SURFACE_CLASS_WINDWARD)
        self.assertEqual(int(upper[0]), SURFACE_CLASS_LEEWARD)

    def test_horizontal_plate_negative_alpha(self) -> None:
        _, _, upper = diagnose_sheet(sx=np.array([0.0]), sy=np.array([0.0]), sheet="upper", alpha_deg=-5.0)
        _, _, lower = diagnose_sheet(sx=np.array([0.0]), sy=np.array([0.0]), sheet="lower", alpha_deg=-5.0)
        self.assertEqual(int(upper[0]), SURFACE_CLASS_WINDWARD)
        self.assertEqual(int(lower[0]), SURFACE_CLASS_LEEWARD)

    def test_wedge_matches_analytic_dot_and_existing_phi_sine(self) -> None:
        sx = -0.12
        sy = 0.07
        alpha_deg = 8.0
        normal = outward_normal_from_slopes(sx=np.array([sx]), sy=np.array([sy]), sheet="lower")
        s, _ = classify_incidence(normal_out=normal, alpha_deg=alpha_deg)
        expected = -float(np.dot(freestream_velocity_direction(alpha_deg=alpha_deg), normal[0]))
        self.assertAlmostEqual(float(s[0]), expected, places=15)
        alpha = float(np.deg2rad(alpha_deg))
        existing_phi_sine = (np.sin(alpha) - sx * np.cos(alpha)) / np.sqrt(1.0 + sx * sx + sy * sy)
        self.assertAlmostEqual(float(s[0]), float(existing_phi_sine), places=15)

    def test_reversed_winding_has_same_oriented_normal_and_class(self) -> None:
        raw = np.array([[-0.2, 0.1, 0.9]], dtype=float)
        for sheet in ("upper", "lower"):
            a = orient_outward_normal(normal=raw, sheet=sheet)
            b = orient_outward_normal(normal=-raw, sheet=sheet)
            np.testing.assert_allclose(a, b, atol=0.0)
            s_a, class_a = classify_incidence(normal_out=a, alpha_deg=5.0)
            s_b, class_b = classify_incidence(normal_out=b, alpha_deg=5.0)
            np.testing.assert_allclose(s_a, s_b, atol=0.0)
            np.testing.assert_array_equal(class_a, class_b)

    def test_qchain_rejected_facet_is_used_for_classification(self) -> None:
        raw = np.array([[0.0, -0.5, 0.5]], dtype=float)
        sx = np.array([0.0])
        sy = np.array([1.0])
        filtered_sx, filtered_sy = _reject_stl_surface_outliers(
            sx_arr=sx,
            sy_arr=sy,
            ref_sx=0.0,
            ref_sy=0.0,
        )
        self.assertFalse(bool(np.isfinite(filtered_sx[0]) and np.isfinite(filtered_sy[0])))

        normal, _, _, source = diagnose_sheet_from_geometry(
            raw_facet_normal=raw,
            qchain_stl_accepted=np.array([False]),
            analytic_sx=np.array([0.0]),
            analytic_sy=np.array([0.0]),
            sheet="upper",
            alpha_deg=5.0,
        )
        np.testing.assert_allclose(normal, orient_outward_normal(normal=raw, sheet="upper"), atol=0.0)
        self.assertEqual(int(source[0]), NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION)

    def test_no_stl_coverage_uses_analytic_fallback(self) -> None:
        expected = outward_normal_from_slopes(sx=np.array([0.2]), sy=np.array([-0.1]), sheet="upper")
        normal, _, _, source = diagnose_sheet_from_geometry(
            raw_facet_normal=np.full((1, 3), np.nan),
            qchain_stl_accepted=np.array([False]),
            analytic_sx=np.array([0.2]),
            analytic_sy=np.array([-0.1]),
            sheet="upper",
            alpha_deg=5.0,
        )
        np.testing.assert_allclose(normal, expected, atol=0.0)
        self.assertEqual(int(source[0]), NORMAL_SOURCE_ANALYTIC_FALLBACK_NO_STL_COVERAGE)

    def test_direct_facet_and_classification_normal_are_identical(self) -> None:
        raw = np.array([[-0.2, 0.1, 0.9]], dtype=float)
        direct = orient_outward_normal(normal=raw, sheet="upper")
        normal, s, surface_class, _ = diagnose_sheet_from_geometry(
            raw_facet_normal=raw,
            qchain_stl_accepted=np.array([True]),
            analytic_sx=np.array([0.0]),
            analytic_sy=np.array([0.0]),
            sheet="upper",
            alpha_deg=5.0,
        )
        np.testing.assert_allclose(normal, direct, atol=0.0)
        angle = np.arccos(np.clip(np.sum(normal * direct, axis=-1), -1.0, 1.0))
        np.testing.assert_allclose(angle, 0.0, atol=1e-15)
        direct_s, direct_class = classify_incidence(normal_out=direct, alpha_deg=5.0)
        np.testing.assert_allclose(s, direct_s, atol=0.0)
        np.testing.assert_array_equal(surface_class, direct_class)

    def test_raw_facet_winding_flip_preserves_geometry_diagnostic(self) -> None:
        raw = np.array([[-0.2, 0.1, 0.9]], dtype=float)
        results = []
        for winding in (raw, -raw):
            results.append(
                diagnose_sheet_from_geometry(
                    raw_facet_normal=winding,
                    qchain_stl_accepted=np.array([False]),
                    analytic_sx=np.array([0.0]),
                    analytic_sy=np.array([0.0]),
                    sheet="lower",
                    alpha_deg=5.0,
                )
            )
        for a, b in zip(results[0], results[1]):
            np.testing.assert_allclose(a, b, atol=0.0)


if __name__ == "__main__":
    unittest.main()