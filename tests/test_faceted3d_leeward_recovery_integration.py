"""Faceted3D integration contract for sheet-specific leeward recovery fields."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from ref_enthalpy_method.geometry.local_incidence import SURFACE_CLASS_LEEWARD
from ref_enthalpy_method.solver_faceted3d import WingLowFidelitySolverFaceted3D


ROOT = Path(__file__).resolve().parents[1]
VEHICLE = ROOT / "specs" / "vehicles" / "htv2_faceted3d_0629.yaml"
CASE = ROOT / "specs" / "cases" / "doc_ma6_alpha5_h30km_faceted3d.yaml"
SAMPLING = ROOT / "specs" / "sampling" / "engineering_full_wing_surface_grid_81x41.yaml"
MACH = 6.0
ALPHA_DEG = 5.0
FIELD_SIZE = 81 * 41

FLOAT_FIELDS_BY_SHEET = {
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
MASK_FIELDS = {
    "upper": "mask_leeward_upper",
    "lower": "mask_leeward_lower",
}
ALL_NEW_FIELDS = tuple(MASK_FIELDS.values()) + tuple(
    field for fields in FLOAT_FIELDS_BY_SHEET.values() for field in fields
)


class Faceted3DLeewardRecoveryIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.run_dir = Path(tempfile.mkdtemp(prefix="faceted3d_leeward_recovery_"))
        cls.solver = WingLowFidelitySolverFaceted3D(
            vehicle_config=str(VEHICLE),
            case_config=str(CASE),
            sampling_config=str(SAMPLING),
            run_dir=str(cls.run_dir),
        )
        cls.solver.compute_snapshot(mach=MACH, alpha=ALPHA_DEG)
        cls.fields = cls.solver.last_fields

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.run_dir, ignore_errors=True)

    def test_new_field_contract_and_classification(self) -> None:
        self.assertEqual(len(ALL_NEW_FIELDS), 18)
        for field in ALL_NEW_FIELDS:
            self.assertIn(field, self.fields)
            self.assertEqual(self.fields[field].shape, (FIELD_SIZE,))

        for sheet in ("upper", "lower"):
            mask = self.fields[MASK_FIELDS[sheet]]
            expected = self.fields[f"surface_class_{sheet}"] == SURFACE_CLASS_LEEWARD
            self.assertEqual(mask.dtype, np.dtype(bool))
            np.testing.assert_array_equal(mask, expected)
            for field in FLOAT_FIELDS_BY_SHEET[sheet]:
                values = self.fields[field]
                self.assertEqual(values.dtype, np.dtype(np.float64))
                np.testing.assert_array_equal(np.isfinite(values), mask)
                np.testing.assert_array_equal(np.isnan(values), ~mask)

        self.assertEqual(np.count_nonzero(self.fields["mask_leeward_upper"]), 256)
        self.assertEqual(np.count_nonzero(self.fields["mask_leeward_lower"]), 0)

    def test_upper_freestream_state_and_tpg_recovery(self) -> None:
        mask = self.fields["mask_leeward_upper"]
        p_inf, rho_inf, T_inf, V_inf = self.solver._freestream(MACH)
        expected_constants = {
            "T_e_leeward_upper": T_inf,
            "p_e_leeward_upper": p_inf,
            "rho_e_leeward_upper": rho_inf,
            "V_e_leeward_upper": V_inf,
            "Ma_e_leeward_upper": MACH,
            "h_e_leeward_upper": float(self.solver.gas.h_from_T(T_inf)),
            "mu_e_leeward_upper": float(self.solver.gas.mu(T_inf)),
        }
        for field, expected in expected_constants.items():
            np.testing.assert_array_equal(
                self.fields[field][mask],
                np.full(np.count_nonzero(mask), expected, dtype=np.float64),
            )

        h_e = float(self.solver.gas.h_from_T(T_inf))
        h_aw = h_e + float(self.solver.gas.prandtl) ** (1.0 / 3.0) * V_inf**2 / 2.0
        expected_taw = float(self.solver.gas.T_from_h(h_aw))
        np.testing.assert_array_equal(
            self.fields["Taw_tpg_leeward_upper"][mask],
            np.full(np.count_nonzero(mask), expected_taw, dtype=np.float64),
        )

    def test_empty_lower_sheet_and_legacy_fields(self) -> None:
        self.assertFalse(np.any(self.fields["mask_leeward_lower"]))
        for field in FLOAT_FIELDS_BY_SHEET["lower"]:
            self.assertTrue(np.all(np.isnan(self.fields[field])))
        for field in ("Taw_tpg_w", "q_l", "Tw_l", "St_l", "Re_ns_l"):
            self.assertIn(field, self.fields)

    def test_outputs_do_not_share_writable_memory_with_surface_class(self) -> None:
        for sheet in ("upper", "lower"):
            surface_class = self.fields[f"surface_class_{sheet}"]
            for field in (MASK_FIELDS[sheet], *FLOAT_FIELDS_BY_SHEET[sheet]):
                self.assertFalse(np.shares_memory(self.fields[field], surface_class), field)


if __name__ == "__main__":
    unittest.main()