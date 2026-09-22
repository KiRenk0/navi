from __future__ import annotations

import pytest

from ref_enthalpy_method.gas.thermo import make_fluent_tpg_thermo
from ref_enthalpy_method.gas.transport import (
    density_ideal_gas,
    k_kinetic_theory,
    mu_sutherland,
)


@pytest.mark.parametrize(
    ("temperature_K", "expected_cp"),
    [
        (200.0, 1002.3291094),
        (1000.0, 1140.9451430),
        (1500.0, 1210.9038141),
        (6000.0, 1360.5592978),
    ],
)
def test_fluent_nasa9_cp_matches_transcribed_coefficients(
    temperature_K: float, expected_cp: float
) -> None:
    thermo = make_fluent_tpg_thermo()
    assert thermo.cp(temperature_K) == pytest.approx(expected_cp)


def test_fluent_nasa9_enthalpy_round_trip() -> None:
    thermo = make_fluent_tpg_thermo()
    temperature_K = 1732.5
    assert thermo.T_from_h(thermo.h_from_T(temperature_K)) == pytest.approx(temperature_K)
    assert thermo.T_from_s0(thermo.s0_from_T(temperature_K)) == pytest.approx(temperature_K)


def test_fluent_air_transport_models_use_supplied_parameters() -> None:
    assert density_ideal_gas(21.96, 247.02) == pytest.approx(21.96 / (287.0 * 247.02))
    assert mu_sutherland(273.11) == pytest.approx(1.716e-5)
    thermo = make_fluent_tpg_thermo()
    expected_k_300 = mu_sutherland(300.0) * (thermo.cp(300.0) + 1.25 * 287.0)
    assert k_kinetic_theory(
        300.0, cp=thermo.cp, mu=mu_sutherland
    ) == pytest.approx(expected_k_300)
    assert expected_k_300 == pytest.approx(0.02517, rel=2.0e-4)
