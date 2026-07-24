"""Closed additive QA for official CLI leeward-recovery serialization."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

import numpy as np

from ref_enthalpy_method.gas import make_fluent_tpg_thermo, mu_sutherland
from ref_enthalpy_method.geometry.local_incidence import SURFACE_CLASS_LEEWARD
from scripts.tools.current_baseline_regression_check import baseline_replay_command


ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = ROOT / "runs" / "current_baseline_snapshot" / "tpg" / "ma6_a5_h30km"
BASELINE_FIELDS = BASELINE_DIR / "fields.npz"
BASELINE_MANIFEST = BASELINE_DIR / "manifest.json"
BASELINE_SUMMARY = BASELINE_DIR / "summary.json"
CASE_ID = "ma6_a5_h30km"
FIELD_SHAPE = (81 * 41,)

MASK_FIELDS = {
    "upper": "mask_leeward_upper",
    "lower": "mask_leeward_lower",
}
FLOAT_FIELDS = {
    "upper": (
        "T_e_leeward_upper",
        "p_e_leeward_upper",
        "rho_e_leeward_upper",
        "V_e_leeward_upper",
        "Ma_e_leeward_upper",
        "h_e_leeward_upper",
        "mu_e_leeward_upper",
        "Taw_tpg_leeward_upper",
    ),
    "lower": (
        "T_e_leeward_lower",
        "p_e_leeward_lower",
        "rho_e_leeward_lower",
        "V_e_leeward_lower",
        "Ma_e_leeward_lower",
        "h_e_leeward_lower",
        "mu_e_leeward_lower",
        "Taw_tpg_leeward_lower",
    ),
}
NEW_FIELDS = {
    "mask_leeward_upper",
    "mask_leeward_lower",
    "T_e_leeward_upper",
    "T_e_leeward_lower",
    "p_e_leeward_upper",
    "p_e_leeward_lower",
    "rho_e_leeward_upper",
    "rho_e_leeward_lower",
    "V_e_leeward_upper",
    "V_e_leeward_lower",
    "Ma_e_leeward_upper",
    "Ma_e_leeward_lower",
    "h_e_leeward_upper",
    "h_e_leeward_lower",
    "mu_e_leeward_upper",
    "mu_e_leeward_lower",
    "Taw_tpg_leeward_upper",
    "Taw_tpg_leeward_lower",
}


def _dict_key_paths(value: Any, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            path = (*prefix, str(key))
            paths.add(path)
            paths.update(_dict_key_paths(child, path))
    elif isinstance(value, list):
        for child in value:
            paths.update(_dict_key_paths(child, prefix))
    return paths


class Faceted3DLeewardRecoverySerializationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary_directory = tempfile.TemporaryDirectory(prefix="faceted3d_leeward_serialization_")
        cls.run_dir = Path(cls._temporary_directory.name) / "ma6_a5_h30km"
        cls.command = baseline_replay_command(CASE_ID, cls.run_dir)
        cls.completed = subprocess.run(
            cls.command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        cls.fields_path = cls.run_dir / "fields.npz"
        cls.summary_path = cls.run_dir / "summary.json"

    @classmethod
    def tearDownClass(cls) -> None:
        temporary_root = Path(cls._temporary_directory.name)
        cls._temporary_directory.cleanup()
        if temporary_root.exists():
            raise AssertionError(f"TemporaryDirectory was not removed: {temporary_root}")

    def _assert_cli_succeeded(self) -> None:
        self.assertEqual(
            self.completed.returncode,
            0,
            msg=f"stdout:\n{self.completed.stdout}\nstderr:\n{self.completed.stderr}",
        )
        self.assertTrue(self.fields_path.is_file())
        self.assertTrue(self.summary_path.is_file())

    def test_official_cli_produces_required_artifacts(self) -> None:
        self._assert_cli_succeeded()

    def test_v5_fields_have_exact_names_dtypes_shapes_and_counts(self) -> None:
        self._assert_cli_succeeded()
        self.assertEqual(len(NEW_FIELDS), 18)
        with np.load(BASELINE_FIELDS, allow_pickle=False) as baseline, np.load(self.fields_path, allow_pickle=False) as candidate:
            baseline_fields = set(baseline.files)
            candidate_fields = set(candidate.files)
            self.assertEqual(len(baseline_fields), 72)
            self.assertEqual(len(candidate_fields), 72)
            self.assertEqual(candidate_fields, baseline_fields)
            self.assertTrue(NEW_FIELDS <= baseline_fields)
            self.assertEqual(candidate_fields - baseline_fields, set())

            for field in MASK_FIELDS.values():
                values = candidate[field]
                self.assertEqual(values.dtype, np.dtype(bool), field)
                self.assertEqual(values.shape, FIELD_SHAPE, field)
            for fields in FLOAT_FIELDS.values():
                for field in fields:
                    values = candidate[field]
                    self.assertEqual(values.dtype, np.dtype(np.float64), field)
                    self.assertEqual(values.shape, FIELD_SHAPE, field)

            upper_mask = candidate[MASK_FIELDS["upper"]]
            lower_mask = candidate[MASK_FIELDS["lower"]]
            self.assertEqual(int(np.count_nonzero(upper_mask)), 256)
            self.assertEqual(int(np.count_nonzero(~upper_mask)), 3065)
            self.assertEqual(int(np.count_nonzero(lower_mask)), 0)
            self.assertEqual(int(np.count_nonzero(~lower_mask)), 3321)

    def test_masks_and_nan_placement_follow_surface_class(self) -> None:
        self._assert_cli_succeeded()
        with np.load(self.fields_path, allow_pickle=False) as fields:
            for sheet in ("upper", "lower"):
                mask = fields[MASK_FIELDS[sheet]]
                expected_mask = fields[f"surface_class_{sheet}"] == SURFACE_CLASS_LEEWARD
                np.testing.assert_array_equal(mask, expected_mask)
                for field in FLOAT_FIELDS[sheet]:
                    np.testing.assert_array_equal(np.isfinite(fields[field]), mask, err_msg=field)
                    np.testing.assert_array_equal(np.isnan(fields[field]), ~mask, err_msg=field)

    def test_freestream_edge_state_and_independent_taw_recalculation(self) -> None:
        self._assert_cli_succeeded()
        manifest = json.loads(BASELINE_MANIFEST.read_text(encoding="utf-8"))
        baseline_summary = json.loads(BASELINE_SUMMARY.read_text(encoding="utf-8"))
        candidate_summary = json.loads(self.summary_path.read_text(encoding="utf-8"))
        freestream = manifest["freestream"]
        case = manifest["case"]
        gas_contract = baseline_summary["case"]

        T_inf = float(freestream["actual_T_inf_K"])
        p_inf = float(freestream["actual_p_inf_Pa"])
        rho_inf = float(freestream["actual_rho_inf_kg_m3"])
        mach = float(case["mach"])
        gas_constant = float(gas_contract["R_J_per_kgK"])
        prandtl = float(gas_contract["pr"])
        V_inf = float(candidate_summary["freestream"]["V_inf_m_s"])

        tpg = make_fluent_tpg_thermo(R=gas_constant)
        h_inf = float(tpg.h_from_T(T_inf))
        mu_inf = float(mu_sutherland(T_inf))
        h_aw = h_inf + prandtl ** (1.0 / 3.0) * V_inf**2 / 2.0
        expected_taw = float(tpg.T_from_h(h_aw))
        expected = {
            "T_e": T_inf,
            "p_e": p_inf,
            "rho_e": rho_inf,
            "V_e": V_inf,
            "Ma_e": mach,
            "h_e": h_inf,
            "mu_e": mu_inf,
            "Taw_tpg": expected_taw,
        }

        with np.load(self.fields_path, allow_pickle=False) as fields:
            for sheet in ("upper", "lower"):
                mask = fields[MASK_FIELDS[sheet]]
                for stem, expected_value in expected.items():
                    actual = fields[f"{stem}_leeward_{sheet}"][mask]
                    np.testing.assert_array_equal(
                        actual,
                        np.full(int(np.count_nonzero(mask)), expected_value, dtype=np.float64),
                    )

    def test_all_v5_baseline_fields_are_byte_exact_and_no_extra_field_exists(self) -> None:
        self._assert_cli_succeeded()
        max_abs_diff = 0.0
        with np.load(BASELINE_FIELDS, allow_pickle=False) as baseline, np.load(self.fields_path, allow_pickle=False) as candidate:
            baseline_fields = set(baseline.files)
            self.assertEqual(len(baseline_fields), 72)
            self.assertEqual(set(candidate.files), baseline_fields)
            for field in sorted(baseline_fields):
                expected = np.asarray(baseline[field])
                actual = np.asarray(candidate[field])
                self.assertEqual(actual.dtype, expected.dtype, field)
                self.assertEqual(actual.shape, expected.shape, field)
                if expected.dtype.kind in "fc":
                    np.testing.assert_array_equal(np.isnan(actual), np.isnan(expected), err_msg=field)
                    np.testing.assert_array_equal(np.isinf(actual), np.isinf(expected), err_msg=field)
                    finite = np.isfinite(expected) & np.isfinite(actual)
                    if np.any(finite):
                        field_diff = float(np.max(np.abs(actual[finite] - expected[finite])))
                        max_abs_diff = max(max_abs_diff, field_diff)
                        np.testing.assert_array_equal(actual[finite], expected[finite], err_msg=field)
                else:
                    np.testing.assert_array_equal(actual, expected, err_msg=field)
                self.assertEqual(actual.tobytes(order="C"), expected.tobytes(order="C"), field)
        self.assertEqual(max_abs_diff, 0.0)

    def test_summary_has_no_new_diagnostic_metadata_keys(self) -> None:
        self._assert_cli_succeeded()
        baseline = json.loads(BASELINE_SUMMARY.read_text(encoding="utf-8"))
        candidate = json.loads(self.summary_path.read_text(encoding="utf-8"))
        self.assertEqual(_dict_key_paths(candidate), _dict_key_paths(baseline))

        forbidden_keys = {
            "provider",
            "leeward_count",
            "taw_min",
            "taw_max",
            "schema_version",
            "validation_status",
        }
        for path in _dict_key_paths(candidate):
            key = path[-1].lower()
            self.assertNotIn(key, forbidden_keys, ".".join(path))
            self.assertNotIn("leeward_recovery", key, ".".join(path))
            self.assertNotIn("mask_leeward", key, ".".join(path))
            self.assertNotIn("taw_tpg_leeward", key, ".".join(path))


if __name__ == "__main__":
    unittest.main()