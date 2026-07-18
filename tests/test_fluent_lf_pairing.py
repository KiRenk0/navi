from __future__ import annotations

import unittest
from dataclasses import fields as dataclass_fields
from pathlib import Path

import numpy as np

from ref_enthalpy_method.geometry.projected_semantics import ProjectedGeometrySemantics
from ref_enthalpy_method.mapping.fluent_clean import FluentCleanLeewardMasks
from ref_enthalpy_method.mapping.fluent_lf_pairing import (
    FluentLfCleanPairing,
    _pair_projected_physical_points,
    build_fluent_lf_clean_pairing,
)
from ref_enthalpy_method.mapping.fluent_projection import FluentSurfaceProjection
from ref_enthalpy_method.mapping.fluent_semantics import (
    FluentProjectedSemanticsIntegration,
)
from ref_enthalpy_method.mapping.lf_clean import LfCleanLeewardMasks


def _readonly(value, dtype) -> np.ndarray:
    result = np.array(value, dtype=dtype, copy=True, order="C")
    result.setflags(write=False)
    return result


def _pair(
    source_index,
    source_coordinates,
    target_index,
    target_coordinates,
    *,
    sheet="upper",
    source_domain=100,
    target_domain=100,
) -> FluentLfCleanPairing:
    source_index_array = np.asarray(source_index)
    target_index_array = np.asarray(target_index)
    if source_index_array.size == 0:
        source_index_array = source_index_array.astype(np.int64)
    if target_index_array.size == 0:
        target_index_array = target_index_array.astype(np.int64)
    return _pair_projected_physical_points(
        sheet=sheet,
        source_canonical_index=source_index_array,
        source_x_span_m=np.asarray(source_coordinates),
        source_full_domain_size=source_domain,
        target_canonical_index=target_index_array,
        target_x_span_m=np.asarray(target_coordinates),
        target_full_domain_size=target_domain,
    )


def _fluent_masks(upper, lower) -> FluentCleanLeewardMasks:
    upper_array = np.asarray(upper, dtype=np.bool_)
    lower_array = np.asarray(lower, dtype=np.bool_)
    any_sheet = upper_array | lower_array
    return FluentCleanLeewardMasks(
        projection_gate_valid=_readonly(np.ones(upper_array.size), np.bool_),
        semantic_valid=_readonly(np.ones(upper_array.size), np.bool_),
        planform_domain_valid=_readonly(np.ones(upper_array.size), np.bool_),
        clean_eligible=_readonly(any_sheet, np.bool_),
        clean_leeward_upper=_readonly(upper_array, np.bool_),
        clean_leeward_lower=_readonly(lower_array, np.bool_),
        clean_leeward_any=_readonly(any_sheet, np.bool_),
    )


def _lf_masks(upper, lower) -> LfCleanLeewardMasks:
    upper_array = np.asarray(upper, dtype=np.bool_)
    lower_array = np.asarray(lower, dtype=np.bool_)
    any_sheet = upper_array | lower_array
    return LfCleanLeewardMasks(
        planform_domain_valid=_readonly(np.ones(upper_array.size), np.bool_),
        semantic_valid_upper=_readonly(np.ones(upper_array.size), np.bool_),
        semantic_valid_lower=_readonly(np.ones(upper_array.size), np.bool_),
        clean_eligible_upper=_readonly(upper_array, np.bool_),
        clean_eligible_lower=_readonly(lower_array, np.bool_),
        clean_leeward_upper=_readonly(upper_array, np.bool_),
        clean_leeward_lower=_readonly(lower_array, np.bool_),
        clean_leeward_any=_readonly(any_sheet, np.bool_),
    )


def _integration(projected_xyz) -> FluentProjectedSemanticsIntegration:
    projected = _readonly(projected_xyz, np.float64)
    count = projected.shape[0]
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
        geometric_sheet=_readonly(np.ones(count), np.int8),
        outward_normal=_readonly(np.tile([0.0, 0.0, 1.0], (count, 1)), np.float64),
        incidence_s=_readonly(np.full(count, -0.5), np.float64),
        surface_class=_readonly(np.full(count, -1), np.int8),
        qchain_stl_accepted=_readonly(np.ones(count), np.bool_),
        normal_source=_readonly(np.ones(count), np.int8),
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


class PairingGeometryTest(unittest.TestCase):
    def test_assignment_offsets_second_nearest_and_multiplicity(self) -> None:
        pairing = _pair(
            [12, 3, 8],
            [[2.0, 1.0], [0.0, 0.0], [0.2, 0.0]],
            [20, 5, 30],
            [[1.0, 1.0], [0.1, 0.2], [3.0, 1.0]],
        )
        np.testing.assert_array_equal(pairing.source_canonical_index, [3, 8, 12])
        np.testing.assert_array_equal(pairing.target_canonical_index, [5, 5, 20])
        np.testing.assert_allclose(pairing.dx_m, [0.1, -0.1, -1.0])
        np.testing.assert_allclose(pairing.dspan_m, [0.2, 0.2, 0.0])
        np.testing.assert_allclose(pairing.distance_m, np.hypot(pairing.dx_m, pairing.dspan_m))
        np.testing.assert_array_equal(pairing.second_target_canonical_index, [20, 20, 30])
        np.testing.assert_allclose(
            pairing.ambiguity_margin_m,
            pairing.second_distance_m - pairing.distance_m,
        )
        np.testing.assert_array_equal(pairing.target_multiplicity, [2, 2, 1])
        self.assertEqual(pairing.target_pool_size, 3)
        self.assertEqual(pairing.metric, "projected_physical_x_span_euclidean_m")

    def test_exact_ties_use_canonical_identity_and_permutations_are_invariant(self) -> None:
        source_index = np.array([8, 2], dtype=np.int64)
        source_coordinates = np.array([[0.0, 0.0], [10.0, 0.0]])
        target_index = np.array([9, 3, 7], dtype=np.int64)
        target_coordinates = np.array([[1.0, 0.0], [-1.0, 0.0], [11.0, 0.0]])
        baseline = _pair(source_index, source_coordinates, target_index, target_coordinates)
        permuted = _pair(
            source_index[::-1],
            source_coordinates[::-1],
            target_index[[2, 0, 1]],
            target_coordinates[[2, 0, 1]],
        )
        np.testing.assert_array_equal(baseline.target_canonical_index, [7, 3])
        np.testing.assert_array_equal(baseline.second_target_canonical_index, [9, 9])
        for item in dataclass_fields(FluentLfCleanPairing):
            left = getattr(baseline, item.name)
            right = getattr(permuted, item.name)
            if isinstance(left, np.ndarray):
                np.testing.assert_array_equal(left, right)
            else:
                self.assertEqual(left, right)

    def test_exact_equal_target_coordinates_keep_distinct_identities(self) -> None:
        pairing = _pair(
            [4],
            [[1.0, 2.0]],
            [9, 2],
            [[1.0, 2.0], [1.0, 2.0]],
        )
        self.assertEqual(pairing.target_canonical_index[0], 2)
        self.assertEqual(pairing.second_target_canonical_index[0], 9)
        self.assertEqual(pairing.distance_m[0], 0.0)
        self.assertEqual(pairing.second_distance_m[0], 0.0)
        self.assertEqual(pairing.ambiguity_margin_m[0], 0.0)

    def test_mutual_true_false_and_reverse_exact_tie(self) -> None:
        pairing = _pair(
            [9, 2, 6],
            [[0.0, 0.0], [0.0, 0.0], [10.0, 0.0]],
            [4, 8],
            [[0.0, 0.0], [10.0, 0.0]],
        )
        np.testing.assert_array_equal(pairing.source_canonical_index, [2, 6, 9])
        np.testing.assert_array_equal(pairing.mutual_nearest, [True, True, False])
        np.testing.assert_array_equal(pairing.target_multiplicity, [2, 1, 2])


class PairingBoundaryTest(unittest.TestCase):
    def test_empty_set_contracts(self) -> None:
        both_empty = _pair([], np.empty((0, 2)), [], np.empty((0, 2)), source_domain=0, target_domain=0)
        target_only = _pair([], np.empty((0, 2)), [4], [[1.0, 2.0]], source_domain=0)
        for pairing, pool_size in ((both_empty, 0), (target_only, 1)):
            self.assertEqual(pairing.target_pool_size, pool_size)
            for item in dataclass_fields(FluentLfCleanPairing):
                value = getattr(pairing, item.name)
                if isinstance(value, np.ndarray):
                    self.assertEqual(value.shape, (0,))
        with self.assertRaisesRegex(ValueError, "nonempty source and empty target"):
            _pair([1], [[0.0, 0.0]], [], np.empty((0, 2)))

    def test_single_target_sentinels(self) -> None:
        pairing = _pair([1, 3], [[0.0, 0.0], [2.0, 0.0]], [7], [[1.0, 0.0]])
        np.testing.assert_array_equal(pairing.second_target_canonical_index, [-1, -1])
        self.assertTrue(np.all(np.isposinf(pairing.second_distance_m)))
        self.assertTrue(np.all(np.isposinf(pairing.ambiguity_margin_m)))
        self.assertTrue(np.all(np.isfinite(pairing.distance_m)))

    def test_output_dtype_layout_immutability_and_input_nonmutation(self) -> None:
        source_index_base = np.array([99, 5, 88, 1], dtype=np.int32)
        source_index = source_index_base[1::2]
        source_coordinates_base = np.arange(8, dtype=np.float64).reshape(4, 2)
        source_coordinates = source_coordinates_base[::2]
        target_index = _readonly([3, 7], np.int16)
        target_coordinates = _readonly([[0.0, 1.0], [4.0, 5.0]], np.float64)
        before = (
            source_index_base.copy(),
            source_coordinates_base.copy(),
            target_index.copy(),
            target_coordinates.copy(),
            target_index.flags.writeable,
            target_coordinates.flags.writeable,
        )
        pairing = _pair(source_index, source_coordinates, target_index, target_coordinates)
        for item in dataclass_fields(FluentLfCleanPairing):
            value = getattr(pairing, item.name)
            if not isinstance(value, np.ndarray):
                continue
            self.assertTrue(value.flags.owndata, item.name)
            self.assertTrue(value.flags.c_contiguous, item.name)
            self.assertFalse(value.flags.writeable, item.name)
        self.assertEqual(pairing.source_canonical_index.dtype, np.dtype(np.int64))
        self.assertEqual(pairing.distance_m.dtype, np.dtype(np.float64))
        self.assertEqual(pairing.mutual_nearest.dtype, np.dtype(np.bool_))
        self.assertEqual(pairing.target_multiplicity.dtype, np.dtype(np.int64))
        np.testing.assert_array_equal(source_index_base, before[0])
        np.testing.assert_array_equal(source_coordinates_base, before[1])
        np.testing.assert_array_equal(target_index, before[2])
        np.testing.assert_array_equal(target_coordinates, before[3])
        self.assertEqual(target_index.flags.writeable, before[4])
        self.assertEqual(target_coordinates.flags.writeable, before[5])

    def test_corrupt_identity_coordinates_shapes_and_sheet_fail_closed(self) -> None:
        invalid_calls = (
            lambda: _pair([1.5], [[0.0, 0.0]], [2], [[1.0, 0.0]]),
            lambda: _pair([True], [[0.0, 0.0]], [2], [[1.0, 0.0]]),
            lambda: _pair([-1], [[0.0, 0.0]], [2], [[1.0, 0.0]]),
            lambda: _pair([100], [[0.0, 0.0]], [2], [[1.0, 0.0]]),
            lambda: _pair([1, 1], [[0.0, 0.0], [1.0, 0.0]], [2], [[1.0, 0.0]]),
            lambda: _pair([1], [[0.0, 0.0]], [2, 2], [[1.0, 0.0], [2.0, 0.0]]),
            lambda: _pair([1], [[np.nan, 0.0]], [2], [[1.0, 0.0]]),
            lambda: _pair([1], [[0.0, 0.0]], [2], [[np.inf, 0.0]]),
            lambda: _pair([1], np.array([[0.0, 0.0]], dtype=np.float32), [2], [[1.0, 0.0]]),
            lambda: _pair([1], [[0.0, 0.0, 1.0]], [2], [[1.0, 0.0]]),
            lambda: _pair([1], [[1.0e308, 0.0]], [2], [[-1.0e308, 0.0]]),
            lambda: _pair([1], [[0.0, 0.0]], [2], [[1.0, 0.0]], sheet="UPPER"),
        )
        for index, call in enumerate(invalid_calls):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    call()


class PairingBuilderTest(unittest.TestCase):
    def test_builder_uses_only_leeward_target_coordinates(self) -> None:
        integration = _integration([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [5.0, 0.0, 0.0]])
        fluent_masks = _fluent_masks([True, True, False], [False, False, True])
        lf_masks = _lf_masks([True, True, False], [False, False, True])
        fields = {
            "x_l_m": np.array([0.1, 9.9, 5.2], dtype=np.float64),
            "span_l_m": np.zeros(3, dtype=np.float64),
            "x_w_m": np.array([9.9, 0.1, -100.0], dtype=np.float64),
            "span_w_m": np.full(3, 500.0, dtype=np.float64),
        }
        upper = build_fluent_lf_clean_pairing(
            integration=integration,
            fluent_masks=fluent_masks,
            lf_fields=fields,
            lf_masks=lf_masks,
            sheet="upper",
        )
        lower = build_fluent_lf_clean_pairing(
            integration=integration,
            fluent_masks=fluent_masks,
            lf_fields=fields,
            lf_masks=lf_masks,
            sheet="lower",
        )
        np.testing.assert_array_equal(upper.target_canonical_index, [0, 1])
        np.testing.assert_allclose(upper.dx_m, [0.1, -0.1])
        np.testing.assert_array_equal(lower.source_canonical_index, [2])
        np.testing.assert_array_equal(lower.target_canonical_index, [2])
        self.assertAlmostEqual(lower.dx_m[0], 0.2)

    def test_builder_accepts_explicit_empty_lower_sheet(self) -> None:
        integration = _integration([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        pairing = build_fluent_lf_clean_pairing(
            integration=integration,
            fluent_masks=_fluent_masks([True, False], [False, False]),
            lf_fields={
                "x_l_m": np.array([0.0, 1.0], dtype=np.float64),
                "span_l_m": np.zeros(2, dtype=np.float64),
            },
            lf_masks=_lf_masks([True, False], [False, False]),
            sheet="lower",
        )
        self.assertEqual(pairing.sheet, "lower")
        self.assertEqual(pairing.target_pool_size, 0)
        self.assertEqual(pairing.source_canonical_index.size, 0)

    def test_builder_rejects_missing_leeward_fields_and_invalid_sheet(self) -> None:
        integration = _integration([[0.0, 0.0, 0.0]])
        fluent_masks = _fluent_masks([True], [False])
        lf_masks = _lf_masks([True], [False])
        with self.assertRaisesRegex(ValueError, "missing required LF pairing fields"):
            build_fluent_lf_clean_pairing(
                integration=integration,
                fluent_masks=fluent_masks,
                lf_fields={
                    "x_w_m": np.array([0.0], dtype=np.float64),
                    "span_w_m": np.array([0.0], dtype=np.float64),
                },
                lf_masks=lf_masks,
                sheet="upper",
            )
        with self.assertRaises(ValueError):
            build_fluent_lf_clean_pairing(
                integration=integration,
                fluent_masks=fluent_masks,
                lf_fields={
                    "x_l_m": np.array([0.0], dtype=np.float64),
                    "span_l_m": np.array([0.0], dtype=np.float64),
                },
                lf_masks=lf_masks,
                sheet="Upper",
            )


if __name__ == "__main__":
    unittest.main()
