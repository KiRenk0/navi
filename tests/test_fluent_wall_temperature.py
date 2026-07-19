from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from ref_enthalpy_method.geometry.projected_semantics import ProjectedGeometrySemantics
from ref_enthalpy_method.mapping.fluent_clean import FluentCleanLeewardMasks
from ref_enthalpy_method.mapping.fluent_lf_pairing import FluentLfCleanPairing
from ref_enthalpy_method.mapping.fluent_projection import FluentSurfaceProjection
from ref_enthalpy_method.mapping.fluent_semantics import (
    FluentProjectedSemanticsIntegration,
)
from ref_enthalpy_method.mapping.fluent_surface import read_fluent_surface_geometry_csv
from ref_enthalpy_method.mapping.fluent_wall_temperature import (
    FluentWallTemperatureObservations,
    _read_wall_temperature_column,
    build_fluent_wall_temperature_observations,
)


_HEADER = "cellnumber,x-coordinate,y-coordinate,z-coordinate,wall-temperature\n"
_ROWS = (
    ("7", 2.0, 0.0, 0.0, 220.0),
    ("7", 0.0, 0.0, 0.0, 200.0),
    ("9", 1.0, 0.0, 0.0, 210.0),
)


def _readonly(value, dtype) -> np.ndarray:
    result = np.array(value, dtype=dtype, copy=True, order="C")
    result.setflags(write=False)
    return result


def _csv_text(rows=_ROWS, *, header=_HEADER) -> str:
    return header + "".join(
        f"{cell},{x},{span},{up},{temperature}\n"
        for cell, x, span, up, temperature in rows
    )


def _masks(upper=(True, False, True), lower=(False, False, False)) -> FluentCleanLeewardMasks:
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


def _pairing(source=(0, 2), *, sheet="upper", target=(91, 90)) -> FluentLfCleanPairing:
    count = len(source)
    return FluentLfCleanPairing(
        sheet=sheet,
        metric="projected_physical_x_span_euclidean_m",
        target_pool_size=2 if count else 0,
        source_canonical_index=_readonly(source, np.int64),
        target_canonical_index=_readonly(target if count else (), np.int64),
        distance_m=_readonly(np.zeros(count), np.float64),
        dx_m=_readonly(np.zeros(count), np.float64),
        dspan_m=_readonly(np.zeros(count), np.float64),
        second_target_canonical_index=_readonly(
            np.full(count, 92), np.int64
        ),
        second_distance_m=_readonly(np.ones(count), np.float64),
        ambiguity_margin_m=_readonly(np.ones(count), np.float64),
        mutual_nearest=_readonly(np.ones(count), np.bool_),
        target_multiplicity=_readonly(np.ones(count), np.int64),
    )


def _integration(provenance_path: Path) -> FluentProjectedSemanticsIntegration:
    geometry = read_fluent_surface_geometry_csv(provenance_path, x_offset_m=0.030)
    solver_xyz = geometry.canonical_solver_xyz
    count = solver_xyz.shape[0]
    projection = FluentSurfaceProjection(
        canonical_index=_readonly(np.arange(count), np.int64),
        solver_xyz=_readonly(solver_xyz, np.float64),
        projected_xyz=_readonly(solver_xyz, np.float64),
        triangle_id=_readonly(np.zeros(count), np.int64),
        projection_distance_m=_readonly(np.zeros(count), np.float64),
        raw_normal=_readonly(np.tile([0.0, 0.0, 1.0], (count, 1)), np.float64),
        projection_gate_m=0.005,
        projection_gate_pass=_readonly(np.ones(count), np.bool_),
        geometry_source_path=provenance_path,
        geometry_source_sha256=geometry.source_sha256,
        canonical_geometry_sha256=hashlib.sha256(
            solver_xyz.tobytes(order="C")
        ).hexdigest(),
        triangle_count=1,
    )
    semantics = ProjectedGeometrySemantics(
        projected_xyz=_readonly(solver_xyz, np.float64),
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


class FluentWallTemperatureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.provenance_path = self.root / "geometry.csv"
        self.provenance_path.write_text(_csv_text(), encoding="utf-8", newline="")
        self.csv_path = self.root / "observation.csv"
        self.csv_path.write_text(_csv_text(), encoding="utf-8", newline="")
        self.integration = _integration(self.provenance_path)
        self.masks = _masks()
        self.pairing = _pairing()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def build(self, **updates) -> FluentWallTemperatureObservations:
        arguments = {
            "csv_path": self.csv_path,
            "integration": self.integration,
            "fluent_masks": self.masks,
            "pairing": self.pairing,
            "sheet": "upper",
        }
        arguments.update(updates)
        return build_fluent_wall_temperature_observations(**arguments)

    def test_source_canonical_pairing_and_provenance_chain(self) -> None:
        source_before = self.pairing.source_canonical_index.copy()
        target_before = self.pairing.target_canonical_index.copy()
        result = self.build()

        np.testing.assert_array_equal(result.source_canonical_index, [0, 2])
        np.testing.assert_array_equal(result.source_row_index, [1, 0])
        np.testing.assert_array_equal(result.wall_temperature_K, [200.0, 220.0])
        np.testing.assert_array_equal(self.pairing.source_canonical_index, source_before)
        np.testing.assert_array_equal(self.pairing.target_canonical_index, target_before)
        self.assertEqual(result.column_name, "wall-temperature")
        self.assertEqual(result.unit, "K")
        self.assertEqual(result.sheet, "upper")

        surface = read_fluent_surface_geometry_csv(self.csv_path, x_offset_m=0.030)
        source_temperature, _ = _read_wall_temperature_column(self.csv_path)
        canonical = source_temperature[surface.canonical_to_source_row]
        np.testing.assert_array_equal(
            canonical[surface.source_to_canonical_row], source_temperature
        )
        np.testing.assert_array_equal(
            result.wall_temperature_K,
            source_temperature[result.source_row_index],
        )

    def test_output_array_contract_and_raw_byte_hash(self) -> None:
        raw_bytes = self.csv_path.read_bytes()
        result = self.build()
        self.assertEqual(result.source_csv_sha256, hashlib.sha256(raw_bytes).hexdigest())
        for value, dtype in (
            (result.source_canonical_index, np.int64),
            (result.source_row_index, np.int64),
            (result.wall_temperature_K, np.float64),
        ):
            self.assertEqual(value.dtype, np.dtype(dtype))
            self.assertEqual(value.shape, (2,))
            self.assertTrue(value.flags.owndata)
            self.assertTrue(value.flags.c_contiguous)
            self.assertFalse(value.flags.writeable)

    def test_empty_lower_is_typed_and_keeps_hash(self) -> None:
        result = self.build(
            sheet="lower",
            pairing=_pairing((), sheet="lower"),
        )
        self.assertEqual(result.sheet, "lower")
        self.assertEqual(
            result.source_csv_sha256,
            hashlib.sha256(self.csv_path.read_bytes()).hexdigest(),
        )
        for value, dtype in (
            (result.source_canonical_index, np.int64),
            (result.source_row_index, np.int64),
            (result.wall_temperature_K, np.float64),
        ):
            self.assertEqual(value.dtype, np.dtype(dtype))
            self.assertEqual(value.shape, (0,))
            self.assertTrue(value.flags.owndata)
            self.assertTrue(value.flags.c_contiguous)
            self.assertFalse(value.flags.writeable)

    def test_duplicate_cellnumber_is_not_temperature_identity(self) -> None:
        result = self.build()
        np.testing.assert_array_equal(result.wall_temperature_K, [200.0, 220.0])

    def test_target_canonical_index_is_not_used_for_selection(self) -> None:
        first = self.build(pairing=_pairing(target=(91, 90)))
        second = self.build(pairing=_pairing(target=(190, 191)))
        np.testing.assert_array_equal(first.wall_temperature_K, second.wall_temperature_K)
        np.testing.assert_array_equal(first.source_row_index, second.source_row_index)

    def test_sheet_and_pairing_identity_mismatch_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "pairing sheet"):
            self.build(pairing=_pairing((), sheet="lower"))
        corrupted = object.__new__(FluentLfCleanPairing)
        for name, value in vars(self.pairing).items():
            object.__setattr__(corrupted, name, value)
        object.__setattr__(corrupted, "metric", "wrong")
        with self.assertRaisesRegex(ValueError, "pairing metric"):
            self.build(pairing=corrupted)
        with self.assertRaisesRegex(ValueError, "sheet must"):
            self.build(sheet="UPPER")

    def test_pairing_source_must_exactly_match_mask(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.build(pairing=_pairing((0, 1)))
        corrupted = object.__new__(FluentLfCleanPairing)
        for name, value in vars(self.pairing).items():
            object.__setattr__(corrupted, name, value)
        object.__setattr__(
            corrupted,
            "source_canonical_index",
            _readonly((2, 0), np.int64),
        )
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            self.build(pairing=corrupted)

    def test_every_clean_mask_must_have_full_domain_shape(self) -> None:
        corrupted = replace(
            self.masks,
            semantic_valid=_readonly((True, True), np.bool_),
        )
        with self.assertRaisesRegex(ValueError, "full-domain"):
            self.build(fluent_masks=corrupted)

    def test_geometry_identity_mismatch_fails_exactly(self) -> None:
        rows = list(_ROWS)
        rows[0] = ("7", 2.001, 0.0, 0.0, 220.0)
        self.csv_path.write_text(_csv_text(rows), encoding="utf-8", newline="")
        with self.assertRaisesRegex(ValueError, "does not exactly match"):
            self.build()

    def test_row_count_mismatch_fails(self) -> None:
        self.csv_path.write_text(_csv_text(_ROWS[:-1]), encoding="utf-8", newline="")
        with self.assertRaisesRegex(ValueError, "row count|does not exactly match"):
            self.build()

    def test_missing_and_duplicate_temperature_column_fail(self) -> None:
        missing = _csv_text().replace("wall-temperature", "pressure")
        self.csv_path.write_text(missing, encoding="utf-8", newline="")
        with self.assertRaisesRegex(ValueError, "exactly once"):
            self.build()
        duplicate_header = _HEADER.rstrip("\n") + ", wall-temperature \n"
        duplicate_rows = tuple((*row, row[-1]) for row in _ROWS)
        self.csv_path.write_text(
            duplicate_header
            + "".join(
                ",".join(str(value) for value in row) + "\n"
                for row in duplicate_rows
            ),
            encoding="utf-8",
            newline="",
        )
        with self.assertRaisesRegex(ValueError, "exactly once"):
            self.build()

    def test_blank_missing_and_non_numeric_temperature_fail(self) -> None:
        for value, message in (("", "blank"), ("bad", "non-numeric")):
            with self.subTest(value=value):
                rows = list(_ROWS)
                rows[1] = (*rows[1][:-1], value)
                self.csv_path.write_text(_csv_text(rows), encoding="utf-8", newline="")
                with self.assertRaisesRegex(ValueError, message):
                    self.build()
        incomplete = _csv_text().replace("0.0,200.0", "0.0")
        self.csv_path.write_text(incomplete, encoding="utf-8", newline="")
        with self.assertRaisesRegex(ValueError, "missing"):
            self.build()

    def test_non_finite_and_non_positive_temperature_fail(self) -> None:
        for value, message in (
            ("NaN", "non-finite"),
            ("+Inf", "non-finite"),
            ("-Inf", "non-finite"),
            ("0", "greater than zero"),
            ("-1", "greater than zero"),
        ):
            with self.subTest(value=value):
                rows = list(_ROWS)
                rows[0] = (*rows[0][:-1], value)
                self.csv_path.write_text(_csv_text(rows), encoding="utf-8", newline="")
                with self.assertRaisesRegex(ValueError, message):
                    self.build()


if __name__ == "__main__":
    unittest.main()
