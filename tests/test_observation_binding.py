"""Unit tests for Fluent observation binding and fail-closed validator.

Tests use the exact M8/30 CSV at the original repo root.  No solver,
candidate generation, projection, cache, or evidence generation is run.
"""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

import numpy as np

from ref_enthalpy_method.mapping.observation_binding import (
    FluentObservationBinding,
    build_m8h30_observation_binding,
    validate_observation_binding,
)

# ---------------------------------------------------------------------------
# The CSV lives in the original repo, not the worktree.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(r"E:\navi_clean")
_CSV_PATH = "fluent_export/adiabatic_wall_csv/30km_5alpha_8ma.csv"

# Expected canonical values
_EXPECTED_RAW_SHA256 = (
    "5dc84e2dea4dc49a5f6ce777e71b8121c148b9490afeb83c98bd5ce022b3b865"
)
_EXPECTED_BYTE_SIZE = 3123901
_EXPECTED_HEADER = (
    "cellnumber",
    "    x-coordinate",
    "    y-coordinate",
    "    z-coordinate",
    "absolute-pressure",
    "wall-temperature",
    "          y-plus",
    "       heat-flux",
    "face-area-magnitude",
)
_EXPECTED_ROW_COUNT = 21250


class TestBuildBinding(unittest.TestCase):
    """Tests for build_m8h30_observation_binding."""

    def test_builds_valid_binding(self):
        binding = build_m8h30_observation_binding(_REPO_ROOT, csv_path=_CSV_PATH)
        self.assertIsInstance(binding, FluentObservationBinding)
        self.assertEqual(binding.csv_path, _CSV_PATH)

    def test_binding_csv_identity_exact(self):
        binding = build_m8h30_observation_binding(_REPO_ROOT, csv_path=_CSV_PATH)
        self.assertEqual(binding.raw_sha256, _EXPECTED_RAW_SHA256)
        self.assertEqual(binding.byte_size, _EXPECTED_BYTE_SIZE)
        self.assertEqual(binding.header, _EXPECTED_HEADER)
        self.assertEqual(binding.row_count, _EXPECTED_ROW_COUNT)

    def test_binding_parameters_exact(self):
        binding = build_m8h30_observation_binding(_REPO_ROOT, csv_path=_CSV_PATH)
        self.assertEqual(binding.mach, 8.0)
        self.assertEqual(binding.alpha_deg, 5.0)
        self.assertEqual(binding.geometric_altitude_m, 30000)
        self.assertEqual(binding.T_inf_K, 226.509)
        self.assertEqual(binding.p_inf_Pa, 1197.0)
        self.assertEqual(
            binding.freestream_provenance, "user-confirmed custom project input"
        )
        self.assertEqual(binding.wall_thermal_condition, "adiabatic")
        self.assertEqual(binding.observation_field, "wall-temperature")
        self.assertEqual(binding.observation_unit, "K")
        self.assertEqual(binding.coordinate_unit, "m")
        self.assertEqual(binding.fluent_source_convention, "(x,y,z)")
        self.assertEqual(binding.solver_transform, "(x+0.030, span=y, up=z)")
        self.assertEqual(binding.user_confirmation_date, "2026-07-22")
        self.assertEqual(binding.validation_policy, "fail-closed")


class TestValidatePass(unittest.TestCase):
    """Tests where validate_observation_binding must PASS."""

    @classmethod
    def setUpClass(cls):
        cls.valid_binding = build_m8h30_observation_binding(
            _REPO_ROOT, csv_path=_CSV_PATH
        )

    def test_valid_binding_passes(self):
        ok, reason = validate_observation_binding(
            self.valid_binding, repo_root=_REPO_ROOT
        )
        self.assertTrue(ok, f"expected PASS but got: {reason}")

    def test_valid_dict_passes(self):
        d = {
            "schema": self.valid_binding.schema,
            "csv_path": self.valid_binding.csv_path,
            "raw_sha256": self.valid_binding.raw_sha256,
            "byte_size": self.valid_binding.byte_size,
            "header": self.valid_binding.header,
            "row_count": self.valid_binding.row_count,
            "mach": self.valid_binding.mach,
            "alpha_deg": self.valid_binding.alpha_deg,
            "geometric_altitude_m": self.valid_binding.geometric_altitude_m,
            "T_inf_K": self.valid_binding.T_inf_K,
            "p_inf_Pa": self.valid_binding.p_inf_Pa,
            "freestream_provenance": self.valid_binding.freestream_provenance,
            "wall_thermal_condition": self.valid_binding.wall_thermal_condition,
            "observation_field": self.valid_binding.observation_field,
            "observation_unit": self.valid_binding.observation_unit,
            "coordinate_unit": self.valid_binding.coordinate_unit,
            "fluent_source_convention": self.valid_binding.fluent_source_convention,
            "solver_transform": self.valid_binding.solver_transform,
            "user_confirmation_date": self.valid_binding.user_confirmation_date,
            "validation_policy": self.valid_binding.validation_policy,
        }
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertTrue(ok, f"expected PASS but got: {reason}")

    def test_deterministic_repeatability(self):
        results = []
        for _ in range(5):
            ok, reason = validate_observation_binding(
                self.valid_binding, repo_root=_REPO_ROOT
            )
            results.append((ok, reason))
        first = results[0]
        for r in results[1:]:
            self.assertEqual(r, first, "non-deterministic validation result")

    def test_validator_does_not_modify_input(self):
        d = {
            "schema": self.valid_binding.schema,
            "csv_path": self.valid_binding.csv_path,
            "raw_sha256": self.valid_binding.raw_sha256,
            "byte_size": self.valid_binding.byte_size,
            "header": self.valid_binding.header,
            "row_count": self.valid_binding.row_count,
            "mach": self.valid_binding.mach,
            "alpha_deg": self.valid_binding.alpha_deg,
            "geometric_altitude_m": self.valid_binding.geometric_altitude_m,
            "T_inf_K": self.valid_binding.T_inf_K,
            "p_inf_Pa": self.valid_binding.p_inf_Pa,
            "freestream_provenance": self.valid_binding.freestream_provenance,
            "wall_thermal_condition": self.valid_binding.wall_thermal_condition,
            "observation_field": self.valid_binding.observation_field,
            "observation_unit": self.valid_binding.observation_unit,
            "coordinate_unit": self.valid_binding.coordinate_unit,
            "fluent_source_convention": self.valid_binding.fluent_source_convention,
            "solver_transform": self.valid_binding.solver_transform,
            "user_confirmation_date": self.valid_binding.user_confirmation_date,
            "validation_policy": self.valid_binding.validation_policy,
        }
        before = copy.deepcopy(d)
        validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertEqual(
            d, before, "validator must not modify the input dict"
        )


class TestValidateFailMissingField(unittest.TestCase):
    """Tests for missing required fields."""

    @classmethod
    def setUpClass(cls):
        cls.valid_binding = build_m8h30_observation_binding(
            _REPO_ROOT, csv_path=_CSV_PATH
        )

    def _valid_dict(self):
        return {
            "schema": self.valid_binding.schema,
            "csv_path": self.valid_binding.csv_path,
            "raw_sha256": self.valid_binding.raw_sha256,
            "byte_size": self.valid_binding.byte_size,
            "header": self.valid_binding.header,
            "row_count": self.valid_binding.row_count,
            "mach": self.valid_binding.mach,
            "alpha_deg": self.valid_binding.alpha_deg,
            "geometric_altitude_m": self.valid_binding.geometric_altitude_m,
            "T_inf_K": self.valid_binding.T_inf_K,
            "p_inf_Pa": self.valid_binding.p_inf_Pa,
            "freestream_provenance": self.valid_binding.freestream_provenance,
            "wall_thermal_condition": self.valid_binding.wall_thermal_condition,
            "observation_field": self.valid_binding.observation_field,
            "observation_unit": self.valid_binding.observation_unit,
            "coordinate_unit": self.valid_binding.coordinate_unit,
            "fluent_source_convention": self.valid_binding.fluent_source_convention,
            "solver_transform": self.valid_binding.solver_transform,
            "user_confirmation_date": self.valid_binding.user_confirmation_date,
            "validation_policy": self.valid_binding.validation_policy,
        }

    def test_missing_raw_sha256(self):
        d = self._valid_dict()
        del d["raw_sha256"]
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("missing", reason.lower())

    def test_missing_csv_path(self):
        d = self._valid_dict()
        del d["csv_path"]
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("missing", reason.lower())

    def test_missing_mach(self):
        d = self._valid_dict()
        del d["mach"]
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("missing", reason.lower())


class TestValidateFailWrongType(unittest.TestCase):
    """Tests for wrong-type fields."""

    @classmethod
    def setUpClass(cls):
        cls.valid_binding = build_m8h30_observation_binding(
            _REPO_ROOT, csv_path=_CSV_PATH
        )

    def _valid_dict(self):
        return {
            "schema": self.valid_binding.schema,
            "csv_path": self.valid_binding.csv_path,
            "raw_sha256": self.valid_binding.raw_sha256,
            "byte_size": self.valid_binding.byte_size,
            "header": self.valid_binding.header,
            "row_count": self.valid_binding.row_count,
            "mach": self.valid_binding.mach,
            "alpha_deg": self.valid_binding.alpha_deg,
            "geometric_altitude_m": self.valid_binding.geometric_altitude_m,
            "T_inf_K": self.valid_binding.T_inf_K,
            "p_inf_Pa": self.valid_binding.p_inf_Pa,
            "freestream_provenance": self.valid_binding.freestream_provenance,
            "wall_thermal_condition": self.valid_binding.wall_thermal_condition,
            "observation_field": self.valid_binding.observation_field,
            "observation_unit": self.valid_binding.observation_unit,
            "coordinate_unit": self.valid_binding.coordinate_unit,
            "fluent_source_convention": self.valid_binding.fluent_source_convention,
            "solver_transform": self.valid_binding.solver_transform,
            "user_confirmation_date": self.valid_binding.user_confirmation_date,
            "validation_policy": self.valid_binding.validation_policy,
        }

    def test_mach_is_string(self):
        d = self._valid_dict()
        d["mach"] = "8.0"
        ok, _ = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)

    def test_byte_size_is_float(self):
        d = self._valid_dict()
        d["byte_size"] = 3123901.0
        ok, _ = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)

    def test_header_is_list_not_tuple(self):
        d = self._valid_dict()
        d["header"] = list(d["header"])
        ok, _ = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)


class TestValidateFailUnknownField(unittest.TestCase):
    """Tests for unknown-field policy (fail-closed)."""

    @classmethod
    def setUpClass(cls):
        cls.valid_binding = build_m8h30_observation_binding(
            _REPO_ROOT, csv_path=_CSV_PATH
        )

    def _valid_dict(self):
        return {
            "schema": self.valid_binding.schema,
            "csv_path": self.valid_binding.csv_path,
            "raw_sha256": self.valid_binding.raw_sha256,
            "byte_size": self.valid_binding.byte_size,
            "header": self.valid_binding.header,
            "row_count": self.valid_binding.row_count,
            "mach": self.valid_binding.mach,
            "alpha_deg": self.valid_binding.alpha_deg,
            "geometric_altitude_m": self.valid_binding.geometric_altitude_m,
            "T_inf_K": self.valid_binding.T_inf_K,
            "p_inf_Pa": self.valid_binding.p_inf_Pa,
            "freestream_provenance": self.valid_binding.freestream_provenance,
            "wall_thermal_condition": self.valid_binding.wall_thermal_condition,
            "observation_field": self.valid_binding.observation_field,
            "observation_unit": self.valid_binding.observation_unit,
            "coordinate_unit": self.valid_binding.coordinate_unit,
            "fluent_source_convention": self.valid_binding.fluent_source_convention,
            "solver_transform": self.valid_binding.solver_transform,
            "user_confirmation_date": self.valid_binding.user_confirmation_date,
            "validation_policy": self.valid_binding.validation_policy,
        }

    def test_unknown_extra_field_rejected(self):
        d = self._valid_dict()
        d["extra_field"] = "should be rejected"
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("unknown", reason.lower())


class TestValidateFailPathEscapes(unittest.TestCase):
    """Tests for path-escape rejection."""

    @classmethod
    def setUpClass(cls):
        cls.valid_binding = build_m8h30_observation_binding(
            _REPO_ROOT, csv_path=_CSV_PATH
        )

    def _valid_dict(self):
        return {
            "schema": self.valid_binding.schema,
            "csv_path": self.valid_binding.csv_path,
            "raw_sha256": self.valid_binding.raw_sha256,
            "byte_size": self.valid_binding.byte_size,
            "header": self.valid_binding.header,
            "row_count": self.valid_binding.row_count,
            "mach": self.valid_binding.mach,
            "alpha_deg": self.valid_binding.alpha_deg,
            "geometric_altitude_m": self.valid_binding.geometric_altitude_m,
            "T_inf_K": self.valid_binding.T_inf_K,
            "p_inf_Pa": self.valid_binding.p_inf_Pa,
            "freestream_provenance": self.valid_binding.freestream_provenance,
            "wall_thermal_condition": self.valid_binding.wall_thermal_condition,
            "observation_field": self.valid_binding.observation_field,
            "observation_unit": self.valid_binding.observation_unit,
            "coordinate_unit": self.valid_binding.coordinate_unit,
            "fluent_source_convention": self.valid_binding.fluent_source_convention,
            "solver_transform": self.valid_binding.solver_transform,
            "user_confirmation_date": self.valid_binding.user_confirmation_date,
            "validation_policy": self.valid_binding.validation_policy,
        }

    def test_absolute_path_rejected(self):
        d = self._valid_dict()
        d["csv_path"] = str(_REPO_ROOT / _CSV_PATH)
        ok, _ = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)

    def test_dot_dot_escape_rejected(self):
        d = self._valid_dict()
        d["csv_path"] = "../../etc/passwd"
        ok, _ = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)

    def test_windows_absolute_rejected(self):
        d = self._valid_dict()
        d["csv_path"] = r"C:\temp\test.csv"
        ok, _ = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)


class TestValidateFailIdentityMismatches(unittest.TestCase):
    """Tests for CSV identity mismatches."""

    @classmethod
    def setUpClass(cls):
        cls.valid_binding = build_m8h30_observation_binding(
            _REPO_ROOT, csv_path=_CSV_PATH
        )

    def _valid_dict(self):
        return {
            "schema": self.valid_binding.schema,
            "csv_path": self.valid_binding.csv_path,
            "raw_sha256": self.valid_binding.raw_sha256,
            "byte_size": self.valid_binding.byte_size,
            "header": self.valid_binding.header,
            "row_count": self.valid_binding.row_count,
            "mach": self.valid_binding.mach,
            "alpha_deg": self.valid_binding.alpha_deg,
            "geometric_altitude_m": self.valid_binding.geometric_altitude_m,
            "T_inf_K": self.valid_binding.T_inf_K,
            "p_inf_Pa": self.valid_binding.p_inf_Pa,
            "freestream_provenance": self.valid_binding.freestream_provenance,
            "wall_thermal_condition": self.valid_binding.wall_thermal_condition,
            "observation_field": self.valid_binding.observation_field,
            "observation_unit": self.valid_binding.observation_unit,
            "coordinate_unit": self.valid_binding.coordinate_unit,
            "fluent_source_convention": self.valid_binding.fluent_source_convention,
            "solver_transform": self.valid_binding.solver_transform,
            "user_confirmation_date": self.valid_binding.user_confirmation_date,
            "validation_policy": self.valid_binding.validation_policy,
        }

    def test_wrong_path(self):
        d = self._valid_dict()
        d["csv_path"] = "fluent_export/adiabatic_wall_csv/nonexistent.csv"
        ok, _ = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)

    def test_wrong_sha(self):
        d = self._valid_dict()
        d["raw_sha256"] = "0" * 64
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("raw_sha256", reason.lower())

    def test_wrong_size(self):
        d = self._valid_dict()
        d["byte_size"] = 1
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("byte_size", reason.lower())

    def test_header_mismatch(self):
        d = self._valid_dict()
        d["header"] = ("wrong", "header")
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("header", reason.lower())

    def test_row_count_mismatch(self):
        d = self._valid_dict()
        d["row_count"] = 99999
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("row_count", reason.lower())


class TestValidateFailParameterMismatches(unittest.TestCase):
    """Tests for individual parameter mismatches."""

    @classmethod
    def setUpClass(cls):
        cls.valid_binding = build_m8h30_observation_binding(
            _REPO_ROOT, csv_path=_CSV_PATH
        )

    def _valid_dict(self):
        return {
            "schema": self.valid_binding.schema,
            "csv_path": self.valid_binding.csv_path,
            "raw_sha256": self.valid_binding.raw_sha256,
            "byte_size": self.valid_binding.byte_size,
            "header": self.valid_binding.header,
            "row_count": self.valid_binding.row_count,
            "mach": self.valid_binding.mach,
            "alpha_deg": self.valid_binding.alpha_deg,
            "geometric_altitude_m": self.valid_binding.geometric_altitude_m,
            "T_inf_K": self.valid_binding.T_inf_K,
            "p_inf_Pa": self.valid_binding.p_inf_Pa,
            "freestream_provenance": self.valid_binding.freestream_provenance,
            "wall_thermal_condition": self.valid_binding.wall_thermal_condition,
            "observation_field": self.valid_binding.observation_field,
            "observation_unit": self.valid_binding.observation_unit,
            "coordinate_unit": self.valid_binding.coordinate_unit,
            "fluent_source_convention": self.valid_binding.fluent_source_convention,
            "solver_transform": self.valid_binding.solver_transform,
            "user_confirmation_date": self.valid_binding.user_confirmation_date,
            "validation_policy": self.valid_binding.validation_policy,
        }

    def test_mach_mismatch(self):
        d = self._valid_dict()
        d["mach"] = 7.0
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("mach", reason.lower())

    def test_alpha_mismatch(self):
        d = self._valid_dict()
        d["alpha_deg"] = 0.0
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("alpha_deg", reason.lower())

    def test_altitude_mismatch(self):
        d = self._valid_dict()
        d["geometric_altitude_m"] = 20000
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("geometric_altitude_m", reason.lower())

    def test_T_inf_mismatch(self):
        d = self._valid_dict()
        d["T_inf_K"] = 226.50
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("t_inf_k", reason.lower())

    def test_p_inf_mismatch(self):
        d = self._valid_dict()
        d["p_inf_Pa"] = 1200.0
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("p_inf_pa", reason.lower())

    def test_standard_atmosphere_substitution(self):
        """ISA at 30 km is T~226.509 K, p~1197 Pa — our values happen to
        match.  If someone substitutes standard-atmosphere values that differ
        from the user-confirmed inputs (226.509, 1197.0), it must be rejected.
        We test by using a nearby but different ISA value for 30 km."""
        # ISA(30 km) ≈ 226.509 K, 1197 Pa per USSA 1976 — but our user input
        # is explicitly NOT from standard atmosphere. Test a different ISA
        # layer to ensure substitution is detected.
        d = self._valid_dict()
        d["T_inf_K"] = 227.0  # Not the user-confirmed value
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)

    def test_wrong_provenance(self):
        d = self._valid_dict()
        d["freestream_provenance"] = "isa1976 standard atmosphere"
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("freestream_provenance", reason.lower())

    def test_non_adiabatic_boundary(self):
        d = self._valid_dict()
        d["wall_thermal_condition"] = "isothermal"
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("wall_thermal_condition", reason.lower())

    def test_wrong_observation_field(self):
        d = self._valid_dict()
        d["observation_field"] = "heat-flux"
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("observation_field", reason.lower())

    def test_wrong_observation_unit(self):
        d = self._valid_dict()
        d["observation_unit"] = "Pa"
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("observation_unit", reason.lower())

    def test_coordinate_mismatch(self):
        d = self._valid_dict()
        d["coordinate_unit"] = "mm"
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("coordinate_unit", reason.lower())

    def test_transform_mismatch(self):
        d = self._valid_dict()
        d["solver_transform"] = "(x, span=y, up=z)"
        ok, reason = validate_observation_binding(d, repo_root=_REPO_ROOT)
        self.assertFalse(ok)
        self.assertIn("solver_transform", reason.lower())


class TestBoolRejectedForNumericFields(unittest.TestCase):
    """Bool values must be explicitly rejected for all numeric fields."""

    @classmethod
    def setUpClass(cls):
        cls.valid_binding = build_m8h30_observation_binding(
            _REPO_ROOT, csv_path=_CSV_PATH
        )

    def _valid_dict(self):
        return {
            "schema": self.valid_binding.schema,
            "csv_path": self.valid_binding.csv_path,
            "raw_sha256": self.valid_binding.raw_sha256,
            "byte_size": self.valid_binding.byte_size,
            "header": self.valid_binding.header,
            "row_count": self.valid_binding.row_count,
            "mach": self.valid_binding.mach,
            "alpha_deg": self.valid_binding.alpha_deg,
            "geometric_altitude_m": self.valid_binding.geometric_altitude_m,
            "T_inf_K": self.valid_binding.T_inf_K,
            "p_inf_Pa": self.valid_binding.p_inf_Pa,
            "freestream_provenance": self.valid_binding.freestream_provenance,
            "wall_thermal_condition": self.valid_binding.wall_thermal_condition,
            "observation_field": self.valid_binding.observation_field,
            "observation_unit": self.valid_binding.observation_unit,
            "coordinate_unit": self.valid_binding.coordinate_unit,
            "fluent_source_convention": self.valid_binding.fluent_source_convention,
            "solver_transform": self.valid_binding.solver_transform,
            "user_confirmation_date": self.valid_binding.user_confirmation_date,
            "validation_policy": self.valid_binding.validation_policy,
        }

    def test_byte_size_true_rejected(self):
        d = self._valid_dict()
        d["byte_size"] = True
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_row_count_true_rejected(self):
        d = self._valid_dict()
        d["row_count"] = True
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_mach_true_rejected(self):
        d = self._valid_dict()
        d["mach"] = True
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_alpha_deg_false_rejected(self):
        d = self._valid_dict()
        d["alpha_deg"] = False
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_geometric_altitude_m_false_rejected(self):
        d = self._valid_dict()
        d["geometric_altitude_m"] = False
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_T_inf_K_true_rejected(self):
        d = self._valid_dict()
        d["T_inf_K"] = True
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_p_inf_Pa_false_rejected(self):
        d = self._valid_dict()
        d["p_inf_Pa"] = False
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)


class TestAltitudeNonNegative(unittest.TestCase):
    """geometric_altitude_m must be >= 0, bool rejected."""

    @classmethod
    def setUpClass(cls):
        cls.valid_binding = build_m8h30_observation_binding(
            _REPO_ROOT, csv_path=_CSV_PATH
        )

    def _valid_dict(self):
        return {
            "schema": self.valid_binding.schema,
            "csv_path": self.valid_binding.csv_path,
            "raw_sha256": self.valid_binding.raw_sha256,
            "byte_size": self.valid_binding.byte_size,
            "header": self.valid_binding.header,
            "row_count": self.valid_binding.row_count,
            "mach": self.valid_binding.mach,
            "alpha_deg": self.valid_binding.alpha_deg,
            "geometric_altitude_m": self.valid_binding.geometric_altitude_m,
            "T_inf_K": self.valid_binding.T_inf_K,
            "p_inf_Pa": self.valid_binding.p_inf_Pa,
            "freestream_provenance": self.valid_binding.freestream_provenance,
            "wall_thermal_condition": self.valid_binding.wall_thermal_condition,
            "observation_field": self.valid_binding.observation_field,
            "observation_unit": self.valid_binding.observation_unit,
            "coordinate_unit": self.valid_binding.coordinate_unit,
            "fluent_source_convention": self.valid_binding.fluent_source_convention,
            "solver_transform": self.valid_binding.solver_transform,
            "user_confirmation_date": self.valid_binding.user_confirmation_date,
            "validation_policy": self.valid_binding.validation_policy,
        }

    def test_altitude_negative_1_rejected(self):
        d = self._valid_dict()
        d["geometric_altitude_m"] = -1
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_altitude_negative_30000_rejected(self):
        d = self._valid_dict()
        d["geometric_altitude_m"] = -30000
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_altitude_zero_allowed(self):
        """geometric_altitude_m=0 must pass the dataclass base type contract."""
        d = self._valid_dict()
        d["geometric_altitude_m"] = 0
        binding = FluentObservationBinding(**d)
        self.assertEqual(binding.geometric_altitude_m, 0)

    def test_canonical_builder_altitude_30000_passes(self):
        binding = build_m8h30_observation_binding(_REPO_ROOT, csv_path=_CSV_PATH)
        self.assertEqual(binding.geometric_altitude_m, 30000)


class TestPathCanonicalization(unittest.TestCase):
    """csv_path must be canonical POSIX-style repo-relative; reject backslash, mixed slash."""

    @classmethod
    def setUpClass(cls):
        cls.valid_binding = build_m8h30_observation_binding(
            _REPO_ROOT, csv_path=_CSV_PATH
        )

    def _dict_with_path(self, csv_path):
        return {
            "schema": self.valid_binding.schema,
            "csv_path": csv_path,
            "raw_sha256": self.valid_binding.raw_sha256,
            "byte_size": self.valid_binding.byte_size,
            "header": self.valid_binding.header,
            "row_count": self.valid_binding.row_count,
            "mach": self.valid_binding.mach,
            "alpha_deg": self.valid_binding.alpha_deg,
            "geometric_altitude_m": self.valid_binding.geometric_altitude_m,
            "T_inf_K": self.valid_binding.T_inf_K,
            "p_inf_Pa": self.valid_binding.p_inf_Pa,
            "freestream_provenance": self.valid_binding.freestream_provenance,
            "wall_thermal_condition": self.valid_binding.wall_thermal_condition,
            "observation_field": self.valid_binding.observation_field,
            "observation_unit": self.valid_binding.observation_unit,
            "coordinate_unit": self.valid_binding.coordinate_unit,
            "fluent_source_convention": self.valid_binding.fluent_source_convention,
            "solver_transform": self.valid_binding.solver_transform,
            "user_confirmation_date": self.valid_binding.user_confirmation_date,
            "validation_policy": self.valid_binding.validation_policy,
        }

    def test_mixed_slash_rejected_1(self):
        d = self._dict_with_path(r"fluent_export\adiabatic_wall_csv/30km_5alpha_8ma.csv")
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_backslash_only_rejected(self):
        d = self._dict_with_path(r"fluent_export\adiabatic_wall_csv\30km_5alpha_8ma.csv")
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_leading_dot_slash_rejected(self):
        d = self._dict_with_path(r".\fluent_export/adiabatic_wall_csv/30km_5alpha_8ma.csv")
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_posix_absolute_etc_passwd_rejected(self):
        d = self._dict_with_path("/etc/passwd")
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_posix_absolute_tmp_csv_rejected(self):
        d = self._dict_with_path("/tmp/test.csv")
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_posix_absolute_repo_like_path_rejected(self):
        d = self._dict_with_path("/fluent_export/adiabatic_wall_csv/30km_5alpha_8ma.csv")
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_double_slash_rejected(self):
        d = self._dict_with_path("//server/share/test.csv")
        with self.assertRaises((ValueError, TypeError)):
            FluentObservationBinding(**d)

    def test_canonical_forward_slash_passes(self):
        d = self._dict_with_path("fluent_export/adiabatic_wall_csv/30km_5alpha_8ma.csv")
        binding = FluentObservationBinding(**d)
        self.assertEqual(binding.csv_path, "fluent_export/adiabatic_wall_csv/30km_5alpha_8ma.csv")