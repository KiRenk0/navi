from __future__ import annotations

import unittest
from dataclasses import fields as dataclass_fields

import numpy as np

from ref_enthalpy_method.geometry.local_incidence import (
    SURFACE_CLASS_INVALID,
    SURFACE_CLASS_LEEWARD,
    SURFACE_CLASS_WINDWARD,
)
from ref_enthalpy_method.mapping.lf_clean import (
    LfCleanLeewardMasks,
    build_lf_clean_leeward_masks,
    lf_clean_qa,
)


def _fields(count: int = 8) -> dict[str, np.ndarray]:
    x = np.linspace(0.0, 1.0, count, dtype=np.float64)
    span = np.linspace(0.0, 1.0, count, dtype=np.float64)
    result: dict[str, np.ndarray] = {
        "x_w_m": x.copy(),
        "span_w_m": span.copy(),
        "x_l_m": x.copy(),
        "span_l_m": span.copy(),
        "xc_w": x.copy(),
        "yb_w": span.copy(),
        "xc_l": x.copy(),
        "yb_l": span.copy(),
    }
    for sheet in ("upper", "lower"):
        result[f"normal_x_{sheet}"] = np.zeros(count, dtype=np.float64)
        result[f"normal_y_{sheet}"] = np.zeros(count, dtype=np.float64)
        result[f"normal_z_{sheet}"] = np.ones(count, dtype=np.float64)
        result[f"incidence_s_{sheet}"] = np.full(count, -0.5, dtype=np.float64)
        result[f"surface_class_{sheet}"] = np.full(
            count, SURFACE_CLASS_WINDWARD, dtype=np.int8
        )
        result[f"normal_source_{sheet}"] = np.ones(count, dtype=np.int8)
    return result


def _snapshot(fields: dict[str, np.ndarray]) -> dict[str, tuple[tuple[int, ...], np.dtype, bytes, bool]]:
    return {
        name: (value.shape, value.dtype, value.tobytes(order="A"), value.flags.writeable)
        for name, value in fields.items()
    }


class LfCleanFormulaTest(unittest.TestCase):
    def test_frozen_source_policy_and_sheet_specific_formula(self) -> None:
        fields = _fields(8)
        fields["surface_class_upper"][:] = SURFACE_CLASS_LEEWARD
        fields["normal_source_upper"][:] = np.array([1, 2, 0, 3, 1, 2, 1, 2], dtype=np.int8)
        fields["surface_class_upper"][6] = SURFACE_CLASS_WINDWARD
        fields["surface_class_lower"][6] = SURFACE_CLASS_LEEWARD
        fields["normal_source_lower"][6] = 1

        masks = build_lf_clean_leeward_masks(fields)

        np.testing.assert_array_equal(
            masks.clean_leeward_upper,
            [True, True, False, False, True, True, False, True],
        )
        np.testing.assert_array_equal(
            masks.clean_leeward_lower,
            [False, False, False, False, False, False, True, False],
        )
        self.assertTrue(masks.clean_leeward_upper[1])
        self.assertTrue(masks.clean_leeward_upper[5])
        self.assertNotIn("qchain_stl_accepted", fields)

    def test_planform_closed_boundaries_and_raw_outliers(self) -> None:
        fields = _fields(12)
        fields["surface_class_upper"][:] = SURFACE_CLASS_LEEWARD
        xc = np.array([0.0, 1.0, 0.5, 0.5, -0.01, 1.01, 0.5, 0.5, np.nan, np.inf, 0.5, 0.5])
        yb = np.array([0.5, 0.5, 0.0, 1.0, 0.5, 0.5, -0.01, 1.01, 0.5, 0.5, np.nan, np.inf])
        for name in ("xc_w", "xc_l"):
            fields[name] = xc.copy()
        for name in ("yb_w", "yb_l"):
            fields[name] = yb.copy()

        masks = build_lf_clean_leeward_masks(fields)
        np.testing.assert_array_equal(
            masks.planform_domain_valid,
            [True, True, True, True, False, False, False, False, False, False, False, False],
        )
        np.testing.assert_array_equal(masks.clean_leeward_upper, masks.planform_domain_valid)

    def test_semantic_fail_closed(self) -> None:
        fields = _fields(7)
        fields["surface_class_upper"][:] = SURFACE_CLASS_LEEWARD
        fields["normal_x_upper"][0] = np.nan
        fields["normal_y_upper"][1] = np.nan
        fields["normal_z_upper"][2] = np.nan
        fields["incidence_s_upper"][3] = np.nan
        fields["surface_class_upper"][4] = SURFACE_CLASS_INVALID
        fields["normal_source_upper"][5] = 0
        fields["normal_source_upper"][6] = 3

        masks = build_lf_clean_leeward_masks(fields)
        self.assertFalse(np.any(masks.semantic_valid_upper))
        self.assertFalse(np.any(masks.clean_leeward_upper))

    def test_disjoint_union_and_overlap_failure(self) -> None:
        fields = _fields(4)
        fields["surface_class_upper"][[0, 2]] = SURFACE_CLASS_LEEWARD
        fields["surface_class_lower"][[1, 3]] = SURFACE_CLASS_LEEWARD
        masks = build_lf_clean_leeward_masks(fields)
        np.testing.assert_array_equal(
            masks.clean_leeward_any,
            masks.clean_leeward_upper | masks.clean_leeward_lower,
        )
        self.assertFalse(np.any(masks.clean_leeward_upper & masks.clean_leeward_lower))

        fields["surface_class_lower"][0] = SURFACE_CLASS_LEEWARD
        with self.assertRaisesRegex(ValueError, "overlap"):
            build_lf_clean_leeward_masks(fields)


class LfCleanStructureTest(unittest.TestCase):
    def test_canonical_coordinate_identity_is_a_structural_gate(self) -> None:
        for left, right in (
            ("x_w_m", "x_l_m"),
            ("span_w_m", "span_l_m"),
            ("xc_w", "xc_l"),
            ("yb_w", "yb_l"),
        ):
            with self.subTest(left=left, right=right):
                fields = _fields()
                fields[right][3] += 1.0e-15
                with self.assertRaisesRegex(ValueError, "canonical coordinate identity"):
                    build_lf_clean_leeward_masks(fields)

    def test_missing_shape_dtype_dimension_and_layout_fail_closed(self) -> None:
        invalid: list[dict[str, np.ndarray]] = []
        missing = _fields()
        del missing["normal_x_upper"]
        invalid.append(missing)
        wrong_shape = _fields()
        wrong_shape["incidence_s_lower"] = np.zeros(7, dtype=np.float64)
        invalid.append(wrong_shape)
        wrong_float_dtype = _fields()
        wrong_float_dtype["xc_w"] = wrong_float_dtype["xc_w"].astype(np.float32)
        invalid.append(wrong_float_dtype)
        wrong_int_dtype = _fields()
        wrong_int_dtype["normal_source_upper"] = wrong_int_dtype["normal_source_upper"].astype(np.int16)
        invalid.append(wrong_int_dtype)
        two_dimensional = _fields()
        two_dimensional["normal_z_lower"] = np.ones((2, 4), dtype=np.float64)
        invalid.append(two_dimensional)
        empty = _fields(1)
        for name, value in empty.items():
            empty[name] = value[:0]
        invalid.append(empty)

        for index, fields in enumerate(invalid):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    build_lf_clean_leeward_masks(fields)

    def test_outputs_are_owned_c_contiguous_read_only_and_ordered(self) -> None:
        fields = _fields(6)
        fields["surface_class_upper"][[4, 1]] = SURFACE_CLASS_LEEWARD
        masks = build_lf_clean_leeward_masks(fields)
        for item in dataclass_fields(LfCleanLeewardMasks):
            value = getattr(masks, item.name)
            self.assertEqual(value.dtype, np.dtype(np.bool_))
            self.assertEqual(value.shape, (6,))
            self.assertTrue(value.flags.owndata)
            self.assertTrue(value.flags.c_contiguous)
            self.assertFalse(value.flags.writeable)
        np.testing.assert_array_equal(
            np.flatnonzero(masks.clean_leeward_upper), [1, 4]
        )

    def test_builder_accepts_non_contiguous_inputs_without_modifying_them(self) -> None:
        fields = _fields()
        fields["x_w_m"] = np.arange(16, dtype=np.float64)[::2]
        fields["x_l_m"] = fields["x_w_m"]
        self.assertFalse(fields["x_w_m"].flags.c_contiguous)
        self.assertFalse(fields["x_l_m"].flags.c_contiguous)
        before = _snapshot(fields)
        masks = build_lf_clean_leeward_masks(fields)
        self.assertEqual(_snapshot(fields), before)
        self.assertEqual(masks.clean_leeward_any.shape, (8,))

    def test_builder_does_not_modify_or_write_protect_inputs(self) -> None:
        fields = _fields()
        fields["surface_class_upper"][2] = SURFACE_CLASS_LEEWARD
        before = _snapshot(fields)
        build_lf_clean_leeward_masks(fields)
        self.assertEqual(_snapshot(fields), before)


class LfCleanQaTest(unittest.TestCase):
    def test_qa_counts_raw_clean_global_sources_and_overlap(self) -> None:
        fields = _fields(8)
        fields["normal_source_upper"][:] = np.array([0, 1, 1, 2, 2, 3, 3, 1], dtype=np.int8)
        fields["normal_source_lower"][:] = np.array([0, 1, 2, 2, 3, 3, 1, 2], dtype=np.int8)
        fields["surface_class_upper"][[0, 1, 3, 5, 7]] = SURFACE_CLASS_LEEWARD
        fields["surface_class_lower"][[2, 4, 5]] = SURFACE_CLASS_LEEWARD

        masks = build_lf_clean_leeward_masks(fields)
        qa = lf_clean_qa(fields, masks)

        expected = {
            "point_count": 8,
            "planform_domain_valid_count": 8,
            "semantic_valid_upper_count": 5,
            "semantic_valid_lower_count": 5,
            "clean_eligible_upper_count": 5,
            "clean_eligible_lower_count": 5,
            "raw_upper_leeward_count": 5,
            "raw_lower_leeward_count": 3,
            "clean_upper_count": 3,
            "clean_lower_count": 1,
            "clean_any_count": 4,
            "upper_lower_overlap_count": 0,
            "clean_upper_source_1_count": 2,
            "clean_upper_source_2_count": 1,
            "clean_upper_source_3_count": 0,
            "clean_lower_source_1_count": 0,
            "clean_lower_source_2_count": 1,
            "clean_lower_source_3_count": 0,
            "global_upper_source_0_count": 1,
            "global_upper_source_1_count": 3,
            "global_upper_source_2_count": 2,
            "global_upper_source_3_count": 2,
            "global_lower_source_0_count": 1,
            "global_lower_source_1_count": 2,
            "global_lower_source_2_count": 3,
            "global_lower_source_3_count": 2,
            "raw_upper_source_1_count": 2,
            "raw_upper_source_2_count": 1,
            "raw_upper_source_3_count": 1,
            "raw_lower_source_1_count": 0,
            "raw_lower_source_2_count": 1,
            "raw_lower_source_3_count": 2,
        }
        for key, value in expected.items():
            self.assertEqual(qa[key], value, key)


if __name__ == "__main__":
    unittest.main()
