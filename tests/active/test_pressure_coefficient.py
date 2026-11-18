from __future__ import annotations

import numpy as np
import pytest

from ref_enthalpy_method.aero.edge_conditions import (
    compute_edge_conditions,
    solve_edge_state,
    solve_reference_normal_shock,
)
from ref_enthalpy_method.aero.pressure_coefficient import (
    modified_newtonian_cp,
    modified_newtonian_cp_max,
)
from ref_enthalpy_method.aero.recovery import reference_enthalpy_recovery
from ref_enthalpy_method.aero.strip_reference import StripLeadingEdgeReference
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
        T_inf=247.02,
        sx_arr=np.asarray([0.0]),
        sy_arr=np.asarray([0.0]),
        reference_incidence_s=np.asarray([0.0]),
        sheet="upper",
    )
    assert cache.pressure_incidence_arr[0] < 0.0
    assert cache.cp_arr[0] == 0.0
    assert cache.reference_incidence_arr[0] == 0.0


@pytest.mark.parametrize(
    ("mach", "T_inf", "p_inf"),
    ((5.0, 247.02, 21.96), (12.0, 216.65, 5529.31), (12.0, 270.65, 79.78)),
)
def test_tpg_reference_shock_satisfies_conservation(
    mach: float, T_inf: float, p_inf: float
) -> None:
    gas = _fluent_air()
    shock = solve_reference_normal_shock(
        gas=gas, normal_mach=mach, p_inf=p_inf, T_inf=T_inf
    )
    assert abs(shock.mass_residual) < 1.0e-12
    assert abs(shock.momentum_residual) < 1.0e-12
    h0 = gas.tpg.h_from_T(T_inf) + 0.5 * (mach * gas.tpg.a_T(T_inf)) ** 2
    assert abs(shock.energy_residual) <= max(1.0e-4, 1.0e-10 * h0)
    assert shock.T2_K > T_inf and shock.p2_Pa > p_inf


@pytest.mark.parametrize("s_local", (1.0, 0.6, 0.2))
@pytest.mark.parametrize(
    ("mach", "T_inf", "p_inf"), ((5.0, 247.02, 21.96), (12.0, 216.65, 5529.31))
)
def test_edge_state_satisfies_energy_and_entropy(
    mach: float, T_inf: float, p_inf: float, s_local: float
) -> None:
    gas = _fluent_air()
    cp = modified_newtonian_cp(incidence_s=s_local, mach=mach, gamma=1.4)
    solution = solve_edge_state(
        gas=gas,
        ma_inf=mach,
        p_inf=p_inf,
        T_inf=T_inf,
        cp_pressure=cp,
        reference_incidence_s=1.0,
    )
    assert solution.status == "ok"
    tol_h = max(1.0e-4, 1.0e-10 * solution.h0_J_kg)
    assert abs(solution.energy_residual_J_kg) <= tol_h
    assert abs(solution.entropy_residual_J_kgK) <= 1.0e-6
    assert solution.h_e_J_kg < solution.h0_J_kg
    assert solution.edge.v_e > 0.0


def test_edge_state_without_admissible_solution_is_reported() -> None:
    gas = _fluent_air()
    # Pressure far above the reference total pressure: no edge state exists.
    solution = solve_edge_state(
        gas=gas,
        ma_inf=5.0,
        p_inf=21.96,
        T_inf=247.02,
        cp_pressure=50.0,
        reference_incidence_s=0.0,
    )
    assert solution.edge is None
    assert solution.status == "edge_static_enthalpy_exceeds_total"
    assert solution.raw_h_e_J_kg > solution.h0_J_kg
    with pytest.raises(ValueError, match="edge state failed"):
        compute_edge_conditions(
            gas=gas,
            ma_inf=5.0,
            p_inf=21.96,
            T_inf=247.02,
            cp_pressure=50.0,
            reference_incidence_s=0.0,
        )


def test_windward_cache_result_does_not_depend_on_sample_order() -> None:
    gas = _fluent_air()
    sx = np.asarray([-0.6, -0.2, 0.1])
    sy = np.asarray([0.0, 0.05, -0.1])
    s_ref = np.full(3, 0.9)
    kwargs = {
        "gas": gas, "mach": 8.0, "alpha_deg": 5.0,
        "p_inf": 100.0, "T_inf": 230.0, "sheet": "lower",
    }
    together = build_windward_edge_cache_faceted3d(
        sx_arr=sx, sy_arr=sy, reference_incidence_s=s_ref, **kwargs
    )
    for index in range(3):
        single = build_windward_edge_cache_faceted3d(
            sx_arr=sx[index : index + 1],
            sy_arr=sy[index : index + 1],
            reference_incidence_s=s_ref[index : index + 1],
            **kwargs,
        )
        assert single.taw_tpg[0] == together.taw_tpg[index]
        assert single.reference_incidence_arr[0] == together.reference_incidence_arr[index]


def test_strip_reference_ignores_invalid_first_sample() -> None:
    xc = np.linspace(0.0, 1.0, 21)
    yb = np.asarray([0.0, 0.5, 1.0])
    incidence = np.tile(np.linspace(0.9, 0.2, xc.size), (3, 1))
    valid = np.ones_like(incidence, dtype=bool)
    valid[:, 0] = False  # first sample invalid on every strip
    incidence[:, 0] = np.nan
    reference = StripLeadingEdgeReference.from_structured(
        x_over_c=xc, y_over_b=yb, incidence_s=incidence, geometry_valid=valid
    )
    assert reference.at(x_over_c=0.3, y_over_b=0.25) == pytest.approx(incidence[0, 1])
    # Moving the first valid sample shifts the window, not the definition.
    valid[:, 1] = False
    shifted = StripLeadingEdgeReference.from_structured(
        x_over_c=xc, y_over_b=yb, incidence_s=incidence, geometry_valid=valid
    )
    assert shifted.at(x_over_c=0.3, y_over_b=0.25) == pytest.approx(incidence[0, 2])


def test_strip_reference_requires_positive_leading_edge() -> None:
    xc = np.linspace(0.0, 1.0, 5)
    incidence = -np.ones((2, 5))
    with pytest.raises(ValueError, match="positive leading-edge"):
        StripLeadingEdgeReference.from_structured(
            x_over_c=xc,
            y_over_b=np.asarray([0.0, 1.0]),
            incidence_s=incidence,
            geometry_valid=np.ones((2, 5), dtype=bool),
        )


@pytest.mark.parametrize(("h_e", "V_e"), ((246000.0, 1580.0), (220000.0, 3500.0), (270000.0, 3900.0)))
def test_reference_enthalpy_recovery_is_self_consistent(h_e: float, V_e: float) -> None:
    gas = _fluent_air()
    state = reference_enthalpy_recovery(gas=gas, h_e=h_e, V_e=V_e)
    h_star = h_e + 0.72 * (state.h_aw_J_kg - h_e)
    assert state.T_star_K == pytest.approx(gas.tpg.T_from_h(h_star), rel=1.0e-12)
    r = gas.prandtl_at_T(state.T_star_K) ** (1.0 / 3.0)
    assert abs(state.h_aw_J_kg - (h_e + r * 0.5 * V_e**2)) <= 1.0e-5
    assert h_e < state.h_aw_J_kg < h_e + 0.5 * V_e**2
