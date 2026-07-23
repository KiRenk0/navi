from __future__ import annotations

import inspect
import unittest
from dataclasses import FrozenInstanceError, fields, replace

import numpy as np

from ref_enthalpy_method.mapping.fluent_lf_pairing import FluentLfCleanPairing
from ref_enthalpy_method.mapping.fluent_lf_taw_comparison import (
    FluentLfTawComparison,
    build_fluent_lf_taw_comparison,
)
from ref_enthalpy_method.mapping.fluent_wall_temperature import (
    FluentWallTemperatureObservations,
)
from ref_enthalpy_method.mapping.lf_clean import LfCleanLeewardMasks


EXPECTED_FIELDS = (
    "sheet",
    "source_csv_sha256",
    "observation_field_name",
    "prediction_field_name",
    "unit",
    "prediction_provider",
    "pairing_metric",
    "source_canonical_index",
    "source_row_index",
    "target_canonical_index",
    "wall_temperature_K",
    "Taw_tpg_leeward_K",
    "signed_error_K",
    "signed_relative_error_pct",
    "absolute_error_K",
    "absolute_relative_error_pct",
)
ARRAY_FIELDS = EXPECTED_FIELDS[7:]
INDEX_FIELDS = ARRAY_FIELDS[:3]
FLOAT_FIELDS = ARRAY_FIELDS[3:]


def _readonly(value, dtype) -> np.ndarray:
    result = np.array(value, dtype=dtype, copy=True, order="C")
    result.setflags(write=False)
    return result


def _observation(
    *,
    sheet="upper",
    source=(3, 7, 11),
    rows=(30, 70, 110),
    temperature=(200.0, 300.0, 400.0),
) -> FluentWallTemperatureObservations:
    return FluentWallTemperatureObservations(
        sheet=sheet,
        column_name="wall-temperature",
        unit="K",
        source_csv_sha256="a" * 64,
        source_canonical_index=_readonly(source, np.int64),
        source_row_index=_readonly(rows, np.int64),
        wall_temperature_K=_readonly(temperature, np.float64),
    )


def _pairing(
    *,
    sheet="upper",
    source=(3, 7, 11),
    target=(1, 1, 4),
    target_pool_size=2,
) -> FluentLfCleanPairing:
    count = len(source)
    return FluentLfCleanPairing(
        sheet=sheet,
        metric="projected_physical_x_span_euclidean_m",
        target_pool_size=target_pool_size,
        source_canonical_index=_readonly(source, np.int64),
        target_canonical_index=_readonly(target, np.int64),
        distance_m=_readonly(np.zeros(count), np.float64),
        dx_m=_readonly(np.zeros(count), np.float64),
        dspan_m=_readonly(np.zeros(count), np.float64),
        second_target_canonical_index=_readonly(
            np.full(count, 4 if target_pool_size >= 2 else -1), np.int64
        ),
        second_distance_m=_readonly(
            np.ones(count) if target_pool_size >= 2 else np.full(count, np.inf),
            np.float64,
        ),
        ambiguity_margin_m=_readonly(
            np.ones(count) if target_pool_size >= 2 else np.full(count, np.inf),
            np.float64,
        ),
        mutual_nearest=_readonly(np.ones(count), np.bool_),
        target_multiplicity=_readonly(np.ones(count), np.int64),
    )


def _masks(*, upper=(False, True, False, False, True, False), lower=None):
    upper_array = np.asarray(upper, dtype=np.bool_)
    lower_array = (
        np.zeros(upper_array.size, dtype=np.bool_)
        if lower is None
        else np.asarray(lower, dtype=np.bool_)
    )
    common = np.ones(upper_array.size, dtype=np.bool_)
    return LfCleanLeewardMasks(
        planform_domain_valid=_readonly(common, np.bool_),
        semantic_valid_upper=_readonly(common, np.bool_),
        semantic_valid_lower=_readonly(common, np.bool_),
        clean_eligible_upper=_readonly(common, np.bool_),
        clean_eligible_lower=_readonly(common, np.bool_),
        clean_leeward_upper=_readonly(upper_array, np.bool_),
        clean_leeward_lower=_readonly(lower_array, np.bool_),
        clean_leeward_any=_readonly(upper_array | lower_array, np.bool_),
    )


def _corrupt(instance, **updates):
    corrupted = object.__new__(type(instance))
    for name, value in vars(instance).items():
        object.__setattr__(corrupted, name, updates.get(name, value))
    return corrupted


class FluentLfTawComparisonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.observation = _observation()
        self.pairing = _pairing()
        self.lf_fields = {
            "Taw_tpg_leeward_upper": np.array(
                [999.0, 250.0, 888.0, 777.0, 400.0, 666.0], dtype=np.float64
            ),
            "Tw_l": np.full(6, -123.0, dtype=np.float64),
        }
        self.lf_masks = _masks()

    def build(self, **updates) -> FluentLfTawComparison:
        arguments = {
            "observation": self.observation,
            "pairing": self.pairing,
            "lf_fields": self.lf_fields,
            "lf_masks": self.lf_masks,
            "sheet": "upper",
        }
        arguments.update(updates)
        return build_fluent_lf_taw_comparison(**arguments)

    def test_api_frozen_keyword_only_and_field_order(self) -> None:
        parameters = inspect.signature(build_fluent_lf_taw_comparison).parameters.values()
        self.assertTrue(all(item.kind is inspect.Parameter.KEYWORD_ONLY for item in parameters))
        self.assertTrue(FluentLfTawComparison.__dataclass_params__.frozen)
        self.assertEqual(tuple(item.name for item in fields(FluentLfTawComparison)), EXPECTED_FIELDS)
        with self.assertRaises(FrozenInstanceError):
            self.build().unit = "C"

    def test_public_import_surface_preserves_definition_identity(self) -> None:
        from ref_enthalpy_method.mapping import (
            FluentLfTawComparison as PublicComparison,
            build_fluent_lf_taw_comparison as public_comparison_builder,
            build_m8h30_comparison_inputs,
        )
        from ref_enthalpy_method.mapping.m8h30_comparison_inputs import (
            build_m8h30_comparison_inputs as definition_input_builder,
        )

        self.assertIs(PublicComparison, FluentLfTawComparison)
        self.assertIs(public_comparison_builder, build_fluent_lf_taw_comparison)
        self.assertIs(build_m8h30_comparison_inputs, definition_input_builder)

    def test_direct_indexing_many_to_one_formulas_metadata_and_prohibitions(self) -> None:
        result = self.build()
        np.testing.assert_array_equal(result.source_canonical_index, [3, 7, 11])
        np.testing.assert_array_equal(result.source_row_index, [30, 70, 110])
        np.testing.assert_array_equal(result.target_canonical_index, [1, 1, 4])
        np.testing.assert_array_equal(result.wall_temperature_K, [200.0, 300.0, 400.0])
        np.testing.assert_array_equal(result.Taw_tpg_leeward_K, [250.0, 250.0, 400.0])
        np.testing.assert_array_equal(result.signed_error_K, [50.0, -50.0, 0.0])
        np.testing.assert_array_equal(
            result.signed_relative_error_pct,
            [25.0, -100.0 / 6.0, 0.0],
        )
        np.testing.assert_array_equal(result.absolute_error_K, [50.0, 50.0, 0.0])
        np.testing.assert_array_equal(
            result.absolute_relative_error_pct,
            [25.0, 100.0 / 6.0, 0.0],
        )
        self.assertEqual(result.sheet, "upper")
        self.assertEqual(result.source_csv_sha256, "a" * 64)
        self.assertEqual(result.observation_field_name, "wall-temperature")
        self.assertEqual(result.prediction_field_name, "Taw_tpg_leeward_upper")
        self.assertEqual(result.unit, "K")
        self.assertEqual(
            result.prediction_provider,
            "ref_enthalpy_method.aero.leeward_recovery.build_leeward_freestream_recovery",
        )
        self.assertEqual(result.pairing_metric, self.pairing.metric)
        self.assertNotIn("Tw_l", EXPECTED_FIELDS)
        for prohibited in (
            "distance_m",
            "dx_m",
            "dspan_m",
            "second_target_canonical_index",
            "second_distance_m",
            "ambiguity_margin_m",
            "mutual_nearest",
            "target_multiplicity",
            "accepted",
            "gate",
            "weight",
        ):
            self.assertNotIn(prohibited, EXPECTED_FIELDS)

    def test_upper_preserves_all_186_source_rows(self) -> None:
        sources = tuple(range(186))
        targets = tuple(index % 80 for index in range(186))
        observation = _observation(
            source=sources,
            rows=tuple(range(1000, 1186)),
            temperature=np.full(186, 300.0),
        )
        pairing = _pairing(
            source=sources,
            target=targets,
            target_pool_size=80,
        )
        masks = _masks(upper=np.ones(80, dtype=np.bool_))
        fields_map = {"Taw_tpg_leeward_upper": np.arange(80, dtype=np.float64) + 500.0}
        result = self.build(
            observation=observation,
            pairing=pairing,
            lf_fields=fields_map,
            lf_masks=masks,
        )
        self.assertEqual(result.source_canonical_index.shape, (186,))
        self.assertEqual(np.unique(result.target_canonical_index).size, 80)
        np.testing.assert_array_equal(
            result.Taw_tpg_leeward_K,
            fields_map["Taw_tpg_leeward_upper"][np.asarray(targets)],
        )

    def test_lower_typed_empty_keeps_metadata_and_array_contract(self) -> None:
        observation = _observation(sheet="lower", source=(), rows=(), temperature=())
        pairing = _pairing(
            sheet="lower", source=(), target=(), target_pool_size=0
        )
        masks = _masks(upper=(False, False), lower=(False, False))
        result = self.build(
            observation=observation,
            pairing=pairing,
            lf_fields={"Taw_tpg_leeward_lower": np.array([1.0, 2.0])},
            lf_masks=masks,
            sheet="lower",
        )
        self.assertEqual(result.sheet, "lower")
        self.assertEqual(result.source_csv_sha256, "a" * 64)
        self.assertEqual(result.prediction_field_name, "Taw_tpg_leeward_lower")
        self.assertEqual(result.unit, "K")
        for name in INDEX_FIELDS:
            self.assertEqual(getattr(result, name).dtype, np.dtype(np.int64))
            self.assertEqual(getattr(result, name).shape, (0,))
        for name in FLOAT_FIELDS:
            self.assertEqual(getattr(result, name).dtype, np.dtype(np.float64))
            self.assertEqual(getattr(result, name).shape, (0,))

    def test_sheet_source_shape_dtype_and_identity_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "observation sheet"):
            self.build(observation=_observation(sheet="lower"))
        with self.assertRaisesRegex(ValueError, "pairing sheet"):
            self.build(pairing=_pairing(sheet="lower"))
        with self.assertRaisesRegex(ValueError, "shapes differ"):
            self.build(pairing=_pairing(source=(3, 7), target=(1, 4)))
        bad_dtype = _corrupt(
            self.observation,
            source_canonical_index=_readonly((3, 7, 11), np.int32),
        )
        with self.assertRaisesRegex(ValueError, "dtype int64"):
            self.build(observation=bad_dtype)
        with self.assertRaisesRegex(ValueError, "identities differ"):
            self.build(pairing=_pairing(source=(3, 8, 11)))

    def test_target_dtype_shape_domain_and_clean_pool_fail_closed(self) -> None:
        bad_dtype = _corrupt(
            self.pairing,
            target_canonical_index=_readonly((1, 1, 4), np.int32),
        )
        with self.assertRaisesRegex(ValueError, "dtype int64"):
            self.build(pairing=bad_dtype)
        bad_shape = _corrupt(
            self.pairing,
            target_canonical_index=_readonly([[1, 1, 4]], np.int64),
        )
        with self.assertRaisesRegex(ValueError, "shape"):
            self.build(pairing=bad_shape)
        for target in ((1, 1, 6), (1, 1, 3), (1, 1, -1)):
            with self.subTest(target=target):
                bad_domain = _corrupt(
                    self.pairing,
                    target_canonical_index=_readonly(target, np.int64),
                )
                with self.assertRaisesRegex(ValueError, "clean target pool"):
                    self.build(pairing=bad_domain)
        with self.assertRaisesRegex(ValueError, "target_pool_size"):
            self.build(pairing=replace(self.pairing, target_pool_size=3))

    def test_prediction_field_shape_dtype_selected_domain_and_validity_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required"):
            self.build(lf_fields={"Taw_tpg_leeward_lower": np.ones(6)})
        with self.assertRaisesRegex(ValueError, "shape"):
            self.build(lf_fields={"Taw_tpg_leeward_upper": np.ones(5)})
        with self.assertRaisesRegex(ValueError, "dtype float64"):
            self.build(lf_fields={"Taw_tpg_leeward_upper": np.ones(6, dtype=np.float32)})
        for value, message in ((np.nan, "finite"), (np.inf, "finite"), (0.0, "greater"), (-1.0, "greater")):
            with self.subTest(value=value):
                field = self.lf_fields["Taw_tpg_leeward_upper"].copy()
                field[1] = value
                with self.assertRaisesRegex(ValueError, message):
                    self.build(lf_fields={"Taw_tpg_leeward_upper": field})
        unselected_invalid = self.lf_fields["Taw_tpg_leeward_upper"].copy()
        unselected_invalid[0] = np.nan
        self.build(lf_fields={"Taw_tpg_leeward_upper": unselected_invalid})

    def test_observation_validity_fail_closed(self) -> None:
        for value, message in ((np.nan, "finite"), (np.inf, "finite"), (0.0, "greater"), (-1.0, "greater")):
            with self.subTest(value=value):
                temperature = self.observation.wall_temperature_K.copy()
                temperature[0] = value
                corrupted = _corrupt(
                    self.observation,
                    wall_temperature_K=_readonly(temperature, np.float64),
                )
                with self.assertRaisesRegex(ValueError, message):
                    self.build(observation=corrupted)

    def test_inputs_unchanged_and_outputs_owned_c_contiguous_read_only(self) -> None:
        observation_snapshot = {
            name: getattr(self.observation, name).tobytes(order="C")
            for name in (
                "source_canonical_index",
                "source_row_index",
                "wall_temperature_K",
            )
        }
        pairing_snapshot = {
            name: getattr(self.pairing, name).tobytes(order="C")
            for name in ("source_canonical_index", "target_canonical_index")
        }
        field_snapshot = self.lf_fields["Taw_tpg_leeward_upper"].copy()
        result = self.build()
        for name in INDEX_FIELDS:
            value = getattr(result, name)
            self.assertEqual(value.dtype, np.dtype(np.int64))
            self.assertEqual(value.shape, (3,))
            self.assertTrue(value.flags.owndata)
            self.assertTrue(value.flags.c_contiguous)
            self.assertFalse(value.flags.writeable)
        for name in FLOAT_FIELDS:
            value = getattr(result, name)
            self.assertEqual(value.dtype, np.dtype(np.float64))
            self.assertEqual(value.shape, (3,))
            self.assertTrue(value.flags.owndata)
            self.assertTrue(value.flags.c_contiguous)
            self.assertFalse(value.flags.writeable)
        for name, raw in observation_snapshot.items():
            self.assertEqual(getattr(self.observation, name).tobytes(order="C"), raw)
        for name, raw in pairing_snapshot.items():
            self.assertEqual(getattr(self.pairing, name).tobytes(order="C"), raw)
        np.testing.assert_array_equal(
            self.lf_fields["Taw_tpg_leeward_upper"], field_snapshot
        )


if __name__ == "__main__":
    unittest.main()
