from __future__ import annotations

import numpy as np
import pytest

from ref_enthalpy_method.aero.edge_conditions import compute_edge_conditions
from ref_enthalpy_method.aero.pressure_coefficient import (
    modified_newtonian_cp,
    modified_newtonian_cp_max,
)
from ref_enthalpy_method.aero.windward_cache_faceted3d import (
    build_windward_edge_cache_faceted3d,
)
from ref_enthalpy_method.gas.thermo import make_fluent_tpg_thermo
from ref_enthalpy_method.gas.transport import (
    density_ideal_gas,
    k_kinetic_theory,
    mu_sutherland,
)
from ref_enthalpy_method.geometry.local_incidence import (
    classify_incidence,
    outward_normal_from_slopes,
)
from ref_enthalpy_method.types import GasModel


def _fluent_air() -> GasModel:
    thermo = make_fluent_tpg_thermo(R=287.0)
    return GasModel(
        gamma=1.4,
        R=287.0,
        cp_gas=thermo.cp,
        h_from_T=thermo.h_from_T,
        T_from_h=thermo.T_from_h,
        mu=mu_sutherland,
        rho=lambda p, T: density_ideal_gas(p, T, R=287.0),
        k=lambda T: k_kinetic_theory(T, cp=thermo.cp, mu=mu_sutherland, R=287.0),
        tpg=thermo,
    )


def test_modified_newtonian_stagnation_cp_at_mach5() -> None:
    assert modified_newtonian_cp_max(mach=5.0, gamma=1.4) == pytest.approx(
        1.8087699607, rel=1.0e-10
    )


@pytest.mark.parametrize("mach", (5.0, 8.0, 12.0))
def test_modified_newtonian_cp_max_covers_design_mach_envelope(mach: float) -> None:
    cp_max = modified_newtonian_cp_max(mach=mach, gamma=1.4)
    assert np.isfinite(cp_max)
    assert 0.0 < cp_max < 2.0


def test_modified_newtonian_cp_uses_signed_normal_incidence() -> None:
    assert modified_newtonian_cp(incidence_s=-0.4, mach=5.0, gamma=1.4) == 0.0
    assert modified_newtonian_cp(incidence_s=0.4, mach=5.0, gamma=1.4) > 0.0


@pytest.mark.parametrize(
    ("incidence_s", "expected_cp"),
    ((0.781818, 1.1056), (0.952033, 1.6392)),
)
def test_modified_newtonian_matches_nose_pressure_scale(
    incidence_s: float, expected_cp: float
) -> None:
    assert modified_newtonian_cp(
        incidence_s=incidence_s, mach=5.0, gamma=1.4
    ) == pytest.approx(expected_cp, rel=1.0e-3)


def test_upper_and_lower_sheet_normals_have_opposite_incidence() -> None:
    upper_normal = outward_normal_from_slopes(
        sx=np.asarray(0.5), sy=np.asarray(0.0), sheet="upper"
    )
    lower_normal = outward_normal_from_slopes(
        sx=np.asarray(0.5), sy=np.asarray(0.0), sheet="lower"
    )
    upper = float(classify_incidence(normal_out=upper_normal, alpha_deg=0.0)[0])
    lower = float(classify_incidence(normal_out=lower_normal, alpha_deg=0.0)[0])
    assert upper == pytest.approx(-lower)
    assert upper > 0.0
    assert lower < 0.0


@pytest.mark.parametrize(
    ("alpha_deg", "upper_windward"),
    ((-10.0, True), (10.0, False)),
)
def test_flat_sheet_incidence_tracks_angle_of_attack_sign(
    alpha_deg: float, upper_windward: bool
) -> None:
    upper_normal = outward_normal_from_slopes(
        sx=np.asarray(0.0), sy=np.asarray(0.0), sheet="upper"
    )
    lower_normal = outward_normal_from_slopes(
        sx=np.asarray(0.0), sy=np.asarray(0.0), sheet="lower"
    )
    upper = float(classify_incidence(normal_out=upper_normal, alpha_deg=alpha_deg)[0])
    lower = float(classify_incidence(normal_out=lower_normal, alpha_deg=alpha_deg)[0])
    assert (upper > 0.0) is upper_windward
    assert (lower > 0.0) is (not upper_windward)


def test_modified_newtonian_preserves_zero_pressure_on_leeward_incidence() -> None:
    cp = modified_newtonian_cp(incidence_s=-0.01, mach=12.0, gamma=1.4)
    assert cp == 0.0


def test_modified_newtonian_cache_keeps_leeward_pressure_zero() -> None:
    gas = _fluent_air()
    cache = build_windward_edge_cache_faceted3d(
        gas=gas,
        mach=5.0,
        alpha_deg=10.0,
        p_inf=21.96,
        rho_inf=gas.rho(21.96, 247.02),
        T_inf=247.02,
        xc_grid=np.asarray([0.0]),
        sx_arr=np.asarray([0.0]),
        sy_arr=np.asarray([0.0]),
        sheet="upper",
    )
    assert cache.pressure_incidence_arr[0] < 0.0
    assert cache.cp_arr[0] == 0.0
    assert cache.cp0 == 0.0


def test_edge_state_caps_static_enthalpy_at_total_enthalpy() -> None:
    gas = _fluent_air()
    T_inf = 247.02
    mach = 5.0
    edge = compute_edge_conditions(
        gas=gas,
        ma_inf=mach,
        p_inf=21.96,
        T_inf=T_inf,
        rho_inf=gas.rho(21.96, T_inf),
        cp_pressure=50.0,
        cp0_pressure=0.0,
    )
    h0 = gas.tpg.h_from_T(T_inf) + 0.5 * (mach * gas.tpg.a_T(T_inf)) ** 2
    assert gas.tpg.h_from_T(edge.T_e) == pytest.approx(h0)
    assert edge.v_e == pytest.approx(0.0, abs=1.0e-10)


def test_edge_state_normal_shock_density_ratio_uses_configured_gamma() -> None:
    gas = _fluent_air()
    gas = GasModel(
        gamma=1.3,
        R=gas.R,
        cp_gas=gas.cp_gas,
        h_from_T=gas.h_from_T,
        T_from_h=gas.T_from_h,
        mu=gas.mu,
        rho=gas.rho,
        k=gas.k,
        tpg=gas.tpg,
    )
    edge = compute_edge_conditions(
        gas=gas,
        ma_inf=5.0,
        p_inf=21.96,
        T_inf=247.02,
        rho_inf=gas.rho(21.96, 247.02),
        cp_pressure=0.5,
        cp0_pressure=0.5,
    )
    pressure_ratio = 1.0 + 0.5 * gas.gamma * 5.0**2 * 0.5
    density_ratio = ((gas.gamma + 1.0) * pressure_ratio + (gas.gamma - 1.0)) / (
        (gas.gamma - 1.0) * pressure_ratio + (gas.gamma + 1.0)
    )
    assert edge.T_e == pytest.approx(247.02 * pressure_ratio / density_ratio)
