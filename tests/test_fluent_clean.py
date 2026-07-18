from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from ref_enthalpy_method.geometry.local_incidence import (
    NORMAL_SOURCE_ANALYTIC_FALLBACK_NO_STL_COVERAGE,
    NORMAL_SOURCE_INVALID,
    NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER,
    NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION,
    SURFACE_CLASS_INVALID,
    SURFACE_CLASS_LEEWARD,
    SURFACE_CLASS_NEAR_TANGENT,
    SURFACE_CLASS_WINDWARD,
)
from ref_enthalpy_method.geometry.projected_semantics import (
    GEOMETRIC_SHEET_INVALID,
    GEOMETRIC_SHEET_LOWER,
    GEOMETRIC_SHEET_OTHER,
    GEOMETRIC_SHEET_UPPER,
    ProjectedGeometrySemantics,
)
from ref_enthalpy_method.mapping.fluent_clean import (
    build_fluent_clean_leeward_masks,
    fluent_clean_qa,
)
from ref_enthalpy_method.mapping.fluent_projection import FluentSurfaceProjection
from ref_enthalpy_method.mapping.fluent_semantics import (
    FluentProjectedSemanticsIntegration,
    semantic_valid_mask,
)


def _readonly(value, dtype) -> np.ndarray:
    result = np.array(value, dtype=dtype, copy=True, order="C")
    result.setflags(write=False)
    return result


def _integration(count: int = 4) -> FluentProjectedSemanticsIntegration:
    projected = _readonly(np.column_stack((np.linspace(0.0, 0.03, count), np.zeros(count), np.zeros(count))), np.float64)
    projection = FluentSurfaceProjection(
        canonical_index=_readonly(np.arange(count), np.int64),
        solver_xyz=projected,
        projected_xyz=projected,
        triangle_id=_readonly(np.zeros(count), np.int64),
        projection_distance_m=_readonly(np.zeros(count), np.float64),
        raw_normal=_readonly(np.tile([0.0, 0.0, 1.0], (count, 1)), np.float64),
        projection_gate_m=0.005,
        projection_gate_pass=_readonly(np.ones(count), np.bool_),
        geometry_source_path=Path("synthetic.csv"),
        geometry_source_sha256="synthetic",
        canonical_geometry_sha256="synthetic",
        triangle_count=1,
    )
    semantics = ProjectedGeometrySemantics(
        projected_xyz=projected,
        triangle_id=_readonly(np.zeros(count), np.int64),
        geometric_sheet=_readonly(np.full(count, GEOMETRIC_SHEET_UPPER), np.int8),
        outward_normal=_readonly(np.tile([0.0, 0.0, 1.0], (count, 1)), np.float64),
        incidence_s=_readonly(np.full(count, -0.5), np.float64),
        surface_class=_readonly(np.full(count, SURFACE_CLASS_LEEWARD), np.int8),
        qchain_stl_accepted=_readonly(np.ones(count), np.bool_),
        normal_source=_readonly(np.full(count, NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER), np.int8),
        x_over_c=_readonly(np.full(count, 0.5), np.float64),
        y_over_b=_readonly(np.full(count, 0.5), np.float64),
        planform_parameterization_valid=_readonly(np.ones(count), np.bool_),
    )
    return FluentProjectedSemanticsIntegration(
        projection=projection,
        semantics=semantics,
        geometry_qa={},
        ordering_round_trip={},
    )


def _replace_semantics(integration: FluentProjectedSemanticsIntegration, **updates) -> FluentProjectedSemanticsIntegration:
    return replace(integration, semantics=replace(integration.semantics, **updates))


def _force_corrupt_semantics(
    integration: FluentProjectedSemanticsIntegration,
    field: str,
    value: np.ndarray,
) -> FluentProjectedSemanticsIntegration:
    corrupted = replace(integration.semantics)
    object.__setattr__(corrupted, field, value)
    return replace(integration, semantics=corrupted)


class FluentCleanFormulaTest(unittest.TestCase):
    def test_formula_boundaries_sources_classes_and_no_hidden_edge_filter(self) -> None:
        integration = _integration(19)
        gate = np.ones(19, dtype=bool)
        gate[0] = False
        source = np.full(19, NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER, dtype=np.int8)
        source[[1, 14]] = NORMAL_SOURCE_INVALID
        source[13] = NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION
        source[15] = NORMAL_SOURCE_ANALYTIC_FALLBACK_NO_STL_COVERAGE
        planform = np.ones(19, dtype=bool)
        planform[2] = False
        x_over_c = np.full(19, 0.5)
        x_over_c[3], x_over_c[4] = -0.01, 1.01
        x_over_c[7], x_over_c[8], x_over_c[16] = 0.0, 1.0, 0.99
        y_over_b = np.full(19, 0.5)
        y_over_b[5], y_over_b[6] = -0.01, 1.01
        y_over_b[7], y_over_b[8] = 0.0, 1.0
        sheet = np.full(19, GEOMETRIC_SHEET_UPPER, dtype=np.int8)
        sheet[8] = GEOMETRIC_SHEET_LOWER
        sheet[18] = GEOMETRIC_SHEET_OTHER
        surface_class = np.full(19, SURFACE_CLASS_LEEWARD, dtype=np.int8)
        surface_class[9] = SURFACE_CLASS_WINDWARD
        surface_class[10] = SURFACE_CLASS_NEAR_TANGENT
        surface_class[11] = SURFACE_CLASS_INVALID
        qchain = np.ones(19, dtype=bool)
        qchain[13] = False
        projected = integration.semantics.projected_xyz.copy()
        projected[17, 0] = 0.030

        integration = replace(
            integration,
            projection=replace(integration.projection, projection_gate_pass=_readonly(gate, np.bool_)),
            semantics=replace(
                integration.semantics,
                projected_xyz=_readonly(projected, np.float64),
                normal_source=_readonly(source, np.int8),
                planform_parameterization_valid=_readonly(planform, np.bool_),
                x_over_c=_readonly(x_over_c, np.float64),
                y_over_b=_readonly(y_over_b, np.float64),
                geometric_sheet=_readonly(sheet, np.int8),
                surface_class=_readonly(surface_class, np.int8),
                qchain_stl_accepted=_readonly(qchain, np.bool_),
            ),
        )
        masks = build_fluent_clean_leeward_masks(integration)

        expected_upper = np.zeros(19, dtype=bool)
        expected_upper[[7, 12, 13, 16, 17]] = True
        expected_lower = np.zeros(19, dtype=bool)
        expected_lower[8] = True
        np.testing.assert_array_equal(masks.clean_leeward_upper, expected_upper)
        np.testing.assert_array_equal(masks.clean_leeward_lower, expected_lower)
        self.assertTrue(masks.clean_leeward_upper[13])
        self.assertFalse(integration.semantics.qchain_stl_accepted[13])
        self.assertTrue(masks.clean_leeward_upper[16])
        self.assertTrue(masks.clean_leeward_upper[17])
        self.assertFalse(np.any(masks.clean_leeward_any[[9, 10, 11, 14, 15, 18]]))

    def test_output_array_contract_ordering_and_qa(self) -> None:
        integration = _integration(4)
        integration = _replace_semantics(
            integration,
            geometric_sheet=_readonly([GEOMETRIC_SHEET_UPPER, GEOMETRIC_SHEET_LOWER, GEOMETRIC_SHEET_UPPER, GEOMETRIC_SHEET_LOWER], np.int8),
            normal_source=_readonly([1, 2, 2, 1], np.int8),
            qchain_stl_accepted=_readonly([True, False, False, True], np.bool_),
        )
        masks = build_fluent_clean_leeward_masks(integration)
        for value in vars(masks).values():
            self.assertEqual(value.dtype, np.dtype(np.bool_))
            self.assertEqual(value.shape, (4,))
            self.assertTrue(value.flags.owndata)
            self.assertTrue(value.flags.c_contiguous)
            self.assertFalse(value.flags.writeable)
        np.testing.assert_array_equal(masks.clean_leeward_upper, [True, False, True, False])
        np.testing.assert_array_equal(masks.clean_leeward_lower, [False, True, False, True])
        np.testing.assert_array_equal(masks.clean_leeward_any, masks.clean_leeward_upper | masks.clean_leeward_lower)
        self.assertFalse(np.any(masks.clean_leeward_upper & masks.clean_leeward_lower))
        qa = fluent_clean_qa(integration, masks)
        self.assertEqual(qa["clean_upper_source_1_count"], 1)
        self.assertEqual(qa["clean_upper_source_2_count"], 1)
        self.assertEqual(qa["clean_lower_source_1_count"], 1)
        self.assertEqual(qa["clean_lower_source_2_count"], 1)
        self.assertEqual(qa["upper_lower_overlap_count"], 0)


class FluentCleanFailClosedTest(unittest.TestCase):
    def test_corrupted_dependencies_raise_value_error(self) -> None:
        base = _integration(4)
        writable_x = base.semantics.x_over_c.copy()
        non_owned_x = base.semantics.x_over_c.view()
        fortran_normal = np.asfortranarray(base.semantics.outward_normal)
        fortran_normal.setflags(write=False)
        invalid = (
            replace(base, projection=replace(base.projection, projection_gate_pass=_readonly([1, 1, 1, 1], np.int8))),
            replace(base, projection=replace(base.projection, projection_gate_pass=_readonly([[True, True, True, True]], np.bool_))),
            _replace_semantics(base, x_over_c=_readonly([0.5] * 4, np.float32)),
            _replace_semantics(base, x_over_c=_readonly([0.5] * 3, np.float64)),
            _replace_semantics(base, y_over_b=_readonly([0.5] * 3, np.float64)),
            _replace_semantics(base, planform_parameterization_valid=_readonly([1] * 4, np.int8)),
            _replace_semantics(base, geometric_sheet=_readonly([1] * 4, np.int16)),
            _replace_semantics(base, geometric_sheet=_readonly([1] * 3, np.int8)),
            _replace_semantics(base, surface_class=_readonly([-1] * 4, np.int16)),
            _replace_semantics(base, surface_class=_readonly([-1] * 3, np.int8)),
            _replace_semantics(base, normal_source=_readonly([1] * 4, np.int16)),
            _replace_semantics(base, normal_source=_readonly([1] * 3, np.int8)),
            _replace_semantics(base, outward_normal=_readonly(np.ones((4, 2)), np.float64)),
            _replace_semantics(base, incidence_s=_readonly([-0.5] * 3, np.float64)),
            _force_corrupt_semantics(base, "x_over_c", writable_x),
            _replace_semantics(base, outward_normal=fortran_normal),
            _replace_semantics(base, x_over_c=non_owned_x),
            replace(base, projection=replace(base.projection, projection_gate_pass=_readonly([True] * 3, np.bool_))),
        )
        for index, integration in enumerate(invalid):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    build_fluent_clean_leeward_masks(integration)


class SemanticValidMaskTest(unittest.TestCase):
    def test_public_single_source_formula_and_exclusions(self) -> None:
        integration = _integration(9)
        source = _readonly([1, 2, 0, 3, 1, 1, 1, 1, 2], np.int8)
        sheet = _readonly([1, 2, 1, 1, 0, -1, 1, 1, 1], np.int8)
        normal = np.tile([0.0, 0.0, 1.0], (9, 1))
        normal[6, 0] = np.nan
        incidence = np.full(9, -0.5)
        incidence[7] = np.nan
        surface_class = np.full(9, SURFACE_CLASS_LEEWARD, dtype=np.int8)
        surface_class[8] = SURFACE_CLASS_INVALID
        semantics = replace(
            integration.semantics,
            normal_source=source,
            geometric_sheet=sheet,
            outward_normal=_readonly(normal, np.float64),
            incidence_s=_readonly(incidence, np.float64),
            surface_class=_readonly(surface_class, np.int8),
            planform_parameterization_valid=_readonly(np.zeros(9), np.bool_),
            x_over_c=_readonly(np.full(9, np.nan), np.float64),
            y_over_b=_readonly(np.full(9, np.nan), np.float64),
        )
        np.testing.assert_array_equal(
            semantic_valid_mask(semantics),
            [True, True, False, False, False, False, False, False, False],
        )


if __name__ == "__main__":
    unittest.main()
