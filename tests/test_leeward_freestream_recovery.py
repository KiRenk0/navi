"""Unit tests for leeward freestream-recovery TPG Taw provider.

Covers: classification gating, NaN semantics, freestream edge-state,
TPG property calls, recovery formula, empty mask, spatial constancy,
sheet isolation, shape guard, input immutability, and single-thermo guarantee.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from ref_enthalpy_method.aero.leeward_recovery import (
    LeewardFreestreamRecoveryFields,
    build_leeward_freestream_recovery,
)
from ref_enthalpy_method.gas import make_fluent_tpg_thermo, mu_sutherland
from ref_enthalpy_method.geometry.local_incidence import (
    SURFACE_CLASS_LEEWARD,
    SURFACE_CLASS_NEAR_TANGENT,
    SURFACE_CLASS_WINDWARD,
    SURFACE_CLASS_INVALID,
)
from ref_enthalpy_method.types import GasModel


# ── shared test GasModel (constructed once) ────────────────────────────────

def _make_test_gas() -> GasModel:
    tpg = make_fluent_tpg_thermo(R=287.0)
    return GasModel(
        gamma=1.4,
        R=287.0,
        cp_gas=tpg.cp,
        h_from_T=tpg.h_from_T,
        T_from_h=tpg.T_from_h,
        mu=mu_sutherland,
        prandtl=0.72,
        tpg=tpg,
    )


_gas: GasModel | None = None


def _get_gas() -> GasModel:
    global _gas
    if _gas is None:
        _gas = _make_test_gas()
    return _gas


# ── test constants ─────────────────────────────────────────────────────────

_T_INF = 225.0       # K
_P_INF = 1200.0      # Pa
_RHO_INF = 0.018     # kg/m^3 (approx for h=30km)
_V_INF = 1800.0      # m/s (Ma≈6 at h=30km)
_MA_INF = 6.0


# ── tests ──────────────────────────────────────────────────────────────────

class LeewardFreestreamRecoveryTest(unittest.TestCase):
    """Grouped test suite for build_leeward_freestream_recovery."""

    # ── 1. classification gating ───────────────────────────────────────

    def test_classification_gating(self) -> None:
        """surface_class = [-1, 1, 0, -2] → only index 0 is leeward."""
        sc = np.array([-1, 1, 0, -2], dtype=np.int32)
        result = build_leeward_freestream_recovery(
            surface_class=sc,
            T_inf_K=_T_INF,
            p_inf_Pa=_P_INF,
            rho_inf_kg_m3=_RHO_INF,
            V_inf_m_s=_V_INF,
            Ma_inf=_MA_INF,
            gas=_get_gas(),
        )
        expected_mask = np.array([True, False, False, False])
        np.testing.assert_array_equal(result.mask, expected_mask)
        self.assertEqual(result.mask.dtype, bool)

    # ── 2. mask-outside NaN ────────────────────────────────────────────

    def test_mask_outside_nan(self) -> None:
        """Every float field is NaN exactly where mask is False."""
        sc = np.array([-1, 1, 0, -2], dtype=np.int32)
        result = build_leeward_freestream_recovery(
            surface_class=sc,
            T_inf_K=_T_INF,
            p_inf_Pa=_P_INF,
            rho_inf_kg_m3=_RHO_INF,
            V_inf_m_s=_V_INF,
            Ma_inf=_MA_INF,
            gas=_get_gas(),
        )
        float_fields = [
            result.T_e, result.p_e, result.rho_e, result.V_e, result.Ma_e,
            result.h_e, result.mu_e, result.Taw_tpg,
        ]
        for arr in float_fields:
            self.assertEqual(arr.dtype, np.float64)
            np.testing.assert_array_equal(np.isnan(arr), ~result.mask)

    # ── 3. freestream edge-state ───────────────────────────────────────

    def test_freestream_edge_state(self) -> None:
        """Inside mask: T, p, rho, V, Ma equal input scalars."""
        sc = np.array([1, -1, 0], dtype=np.int32)
        result = build_leeward_freestream_recovery(
            surface_class=sc,
            T_inf_K=_T_INF,
            p_inf_Pa=_P_INF,
            rho_inf_kg_m3=_RHO_INF,
            V_inf_m_s=_V_INF,
            Ma_inf=_MA_INF,
            gas=_get_gas(),
        )
        mask = result.mask
        self.assertTrue(mask[1])
        np.testing.assert_allclose(result.T_e[mask], _T_INF, atol=0)
        np.testing.assert_allclose(result.p_e[mask], _P_INF, atol=0)
        np.testing.assert_allclose(result.rho_e[mask], _RHO_INF, atol=0)
        np.testing.assert_allclose(result.V_e[mask], _V_INF, atol=0)
        np.testing.assert_allclose(result.Ma_e[mask], _MA_INF, atol=0)

    # ── 4. TPG property ────────────────────────────────────────────────

    def test_tpg_property(self) -> None:
        """h_e == gas.h_from_T(T_inf); mu_e == gas.mu(T_inf)."""
        gas = _get_gas()
        sc = np.array([-1], dtype=np.int32)
        result = build_leeward_freestream_recovery(
            surface_class=sc,
            T_inf_K=_T_INF,
            p_inf_Pa=_P_INF,
            rho_inf_kg_m3=_RHO_INF,
            V_inf_m_s=_V_INF,
            Ma_inf=_MA_INF,
            gas=gas,
        )
        expected_h = float(gas.h_from_T(_T_INF))
        expected_mu = float(gas.mu(_T_INF))
        np.testing.assert_allclose(result.h_e[result.mask], expected_h, atol=0)
        np.testing.assert_allclose(result.mu_e[result.mask], expected_mu, atol=0)

    # ── 5. recovery formula ────────────────────────────────────────────

    def test_recovery_formula(self) -> None:
        """Taw_tpg matches the documented recovery chain."""
        gas = _get_gas()
        sc = np.array([-1], dtype=np.int32)
        result = build_leeward_freestream_recovery(
            surface_class=sc,
            T_inf_K=_T_INF,
            p_inf_Pa=_P_INF,
            rho_inf_kg_m3=_RHO_INF,
            V_inf_m_s=_V_INF,
            Ma_inf=_MA_INF,
            gas=gas,
        )
        h_inf = float(gas.h_from_T(_T_INF))
        r_aw = float(gas.prandtl) ** (1.0 / 3.0)
        expected_h_aw = h_inf + r_aw * _V_INF * _V_INF / 2.0
        expected_Taw = float(gas.T_from_h(expected_h_aw))
        np.testing.assert_allclose(result.Taw_tpg[result.mask], expected_Taw, atol=0)

    # ── 6. empty mask ──────────────────────────────────────────────────

    def test_empty_mask(self) -> None:
        """No -1 in surface_class → mask all False, all float fields all NaN."""
        sc = np.array([1, 0, 1], dtype=np.int32)
        gas = _get_gas()
        result = build_leeward_freestream_recovery(
            surface_class=sc,
            T_inf_K=_T_INF,
            p_inf_Pa=_P_INF,
            rho_inf_kg_m3=_RHO_INF,
            V_inf_m_s=_V_INF,
            Ma_inf=_MA_INF,
            gas=gas,
        )
        self.assertFalse(np.any(result.mask))
        self.assertEqual(result.mask.shape, (3,))
        float_fields = [
            result.T_e, result.p_e, result.rho_e, result.V_e, result.Ma_e,
            result.h_e, result.mu_e, result.Taw_tpg,
        ]
        for arr in float_fields:
            self.assertEqual(arr.shape, (3,))
            self.assertTrue(np.all(np.isnan(arr)))

    # ── 7. multiple leeward points spatial constancy ───────────────────

    def test_multiple_leeward_points_constancy(self) -> None:
        """All leeward points have identical freestream fields and Taw."""
        sc = np.array([-1, 1, -1, 0, -1], dtype=np.int32)
        result = build_leeward_freestream_recovery(
            surface_class=sc,
            T_inf_K=_T_INF,
            p_inf_Pa=_P_INF,
            rho_inf_kg_m3=_RHO_INF,
            V_inf_m_s=_V_INF,
            Ma_inf=_MA_INF,
            gas=_get_gas(),
        )
        mask = result.mask
        # indices 0, 2, 4 are leeward
        leeward_idx = np.where(mask)[0]
        self.assertEqual(len(leeward_idx), 3)
        for arr in (
            result.T_e, result.p_e, result.rho_e, result.V_e, result.Ma_e,
            result.h_e, result.mu_e, result.Taw_tpg,
        ):
            self.assertTrue(np.all(arr[leeward_idx[0]] == arr[leeward_idx]))

    # ── 8. sheet isolation ─────────────────────────────────────────────

    def test_sheet_isolation(self) -> None:
        """Two calls with different surface_class arrays must not cross-talk."""
        sc1 = np.array([-1, 1], dtype=np.int32)
        sc2 = np.array([1, -1], dtype=np.int32)
        r1 = build_leeward_freestream_recovery(
            surface_class=sc1,
            T_inf_K=_T_INF,
            p_inf_Pa=_P_INF,
            rho_inf_kg_m3=_RHO_INF,
            V_inf_m_s=_V_INF,
            Ma_inf=_MA_INF,
            gas=_get_gas(),
        )
        r2 = build_leeward_freestream_recovery(
            surface_class=sc2,
            T_inf_K=_T_INF,
            p_inf_Pa=_P_INF,
            rho_inf_kg_m3=_RHO_INF,
            V_inf_m_s=_V_INF,
            Ma_inf=_MA_INF,
            gas=_get_gas(),
        )
        np.testing.assert_array_equal(r1.mask, [True, False])
        np.testing.assert_array_equal(r2.mask, [False, True])
        self.assertFalse(np.shares_memory(r1.mask, r2.mask))
        for f in ("T_e", "p_e", "rho_e", "V_e", "Ma_e", "h_e", "mu_e", "Taw_tpg"):
            arr1 = getattr(r1, f)
            arr2 = getattr(r2, f)
            self.assertFalse(np.shares_memory(arr1, arr2))

    # ── 9. shape guard ─────────────────────────────────────────────────

    def test_shape_guard_rejects_2d(self) -> None:
        """2-D surface_class must raise ValueError, never silently flatten."""
        sc_2d = np.array([[-1, 1], [0, -1]], dtype=np.int32)
        with self.assertRaises(ValueError):
            build_leeward_freestream_recovery(
                surface_class=sc_2d,
                T_inf_K=_T_INF,
                p_inf_Pa=_P_INF,
                rho_inf_kg_m3=_RHO_INF,
                V_inf_m_s=_V_INF,
                Ma_inf=_MA_INF,
                gas=_get_gas(),
            )

    # ── 10. input immutability ─────────────────────────────────────────

    def test_input_immutability(self) -> None:
        """surface_class must be identical before and after the call."""
        sc = np.array([-1, 1, 0, -2], dtype=np.int32)
        sc_copy = sc.copy()
        build_leeward_freestream_recovery(
            surface_class=sc,
            T_inf_K=_T_INF,
            p_inf_Pa=_P_INF,
            rho_inf_kg_m3=_RHO_INF,
            V_inf_m_s=_V_INF,
            Ma_inf=_MA_INF,
            gas=_get_gas(),
        )
        np.testing.assert_array_equal(sc, sc_copy)
        self.assertEqual(sc.dtype, sc_copy.dtype)

    # ── 11. no duplicate thermo construction ───────────────────────────

    def test_no_duplicate_thermo_construction(self) -> None:
        """Provider must not call make_fluent_tpg_thermo internally."""
        sc = np.array([-1], dtype=np.int32)
        gas = _get_gas()
        # Patch the canonical definition site — if the provider ever imports
        # and calls make_fluent_tpg_thermo this will trip.
        with patch(
            "ref_enthalpy_method.gas.thermo.make_fluent_tpg_thermo",
            side_effect=RuntimeError("must not construct second thermo"),
        ):
            result = build_leeward_freestream_recovery(
                surface_class=sc,
                T_inf_K=_T_INF,
                p_inf_Pa=_P_INF,
                rho_inf_kg_m3=_RHO_INF,
                V_inf_m_s=_V_INF,
                Ma_inf=_MA_INF,
                gas=gas,
            )
        self.assertIsInstance(result, LeewardFreestreamRecoveryFields)


if __name__ == "__main__":
    unittest.main()