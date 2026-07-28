from __future__ import annotations

import math

import pytest

from ref_enthalpy_method.atmosphere.ussa1976 import ussa1976


_REFERENCE_STATES = (
    # Geometric altitude [m], temperature [K], pressure [Pa], density [kg/m3].
    (0.0, 288.15, 101_325.0, 1.2249991558877125),
    (20_000.0, 216.65, 5_529.3118923, 8.89099150888865e-2),
    (30_000.0, 226.5090836, 1_197.0316404, 1.8410170384692327e-2),
    (35_000.0, 236.5133721, 574.5945305, 8.463375083259974e-3),
    (40_000.0, 250.3496461, 287.1439555, 3.995678140481709e-3),
    (50_000.0, 270.65, 79.7790930, 1.0268780342616332e-3),
    (60_000.0, 247.0208848, 21.9586661, 3.096778076475165e-4),
    (86_000.0, 186.9459083, 0.3733804618, 6.9578237813e-6),
)


@pytest.mark.parametrize(
    ("altitude_m", "expected_T_K", "expected_p_Pa", "expected_rho_kg_m3"),
    _REFERENCE_STATES,
)
def test_geometric_altitude_reference_states(
    altitude_m: float,
    expected_T_K: float,
    expected_p_Pa: float,
    expected_rho_kg_m3: float,
) -> None:
    state = ussa1976(altitude_m)

    assert state.T == pytest.approx(expected_T_K, rel=2.0e-9, abs=2.0e-7)
    assert state.p == pytest.approx(expected_p_Pa, rel=2.0e-9, abs=2.0e-9)
    assert state.rho == pytest.approx(
        expected_rho_kg_m3,
        rel=2.0e-9,
        abs=2.0e-12,
    )


@pytest.mark.parametrize(
    "geopotential_boundary_m",
    (11_000.0, 20_000.0, 32_000.0, 47_000.0, 51_000.0, 71_000.0),
)
def test_layer_boundaries_are_continuous(geopotential_boundary_m: float) -> None:
    earth_radius_m = 6_356_766.0
    geometric_boundary_m = (
        earth_radius_m
        * geopotential_boundary_m
        / (earth_radius_m - geopotential_boundary_m)
    )
    below = ussa1976(geometric_boundary_m - 1.0e-4)
    above = ussa1976(geometric_boundary_m + 1.0e-4)

    assert above.T == pytest.approx(below.T, rel=0.0, abs=1.0e-5)
    assert above.p == pytest.approx(below.p, rel=2.0e-7)
    assert above.rho == pytest.approx(below.rho, rel=2.0e-7)


@pytest.mark.parametrize(
    "altitude_m",
    (-1.0, math.nan, math.inf, -math.inf, 86_000.000_001),
)
def test_invalid_or_out_of_range_altitudes_fail_closed(altitude_m: float) -> None:
    with pytest.raises(ValueError, match="altitude_m"):
        ussa1976(altitude_m)


def test_density_uses_the_fixed_ussa_dry_air_constant() -> None:
    state = ussa1976(60_000.0)

    assert state.rho == pytest.approx(
        state.p / ((8_314.32 / 28.9644) * state.T),
        rel=1.0e-15,
    )
