"""US Standard Atmosphere 1976 for geometric altitudes from 0 to 86 km."""

from __future__ import annotations

import math
from dataclasses import dataclass


_EARTH_EFFECTIVE_RADIUS_M = 6_356_766.0
_STANDARD_GRAVITY_M_PER_S2 = 9.80665
_USSA_UNIVERSAL_GAS_CONSTANT_J_PER_KMOL_K = 8_314.32
_USSA_SEA_LEVEL_MOLAR_MASS_KG_PER_KMOL = 28.9644
_DRY_AIR_GAS_CONSTANT_J_PER_KG_K = (
    _USSA_UNIVERSAL_GAS_CONSTANT_J_PER_KMOL_K
    / _USSA_SEA_LEVEL_MOLAR_MASS_KG_PER_KMOL
)
_MAX_GEOMETRIC_ALTITUDE_M = 86_000.0


@dataclass(frozen=True)
class AtmosphereState:
    T: float
    p: float
    rho: float


def _geopotential_altitude(h_geom_m: float) -> float:
    return (_EARTH_EFFECTIVE_RADIUS_M * h_geom_m) / (
        _EARTH_EFFECTIVE_RADIUS_M + h_geom_m
    )


def ussa1976(
    altitude_m: float,
) -> AtmosphereState:
    """Return the strict USSA1976 state at a geometric altitude in metres.

    The atmosphere-specific dry-air gas constant and standard gravity are
    fixed here. They are intentionally independent of the gas/transport model
    used by the aerodynamic and thermal solvers.
    """
    h_geom_m = float(altitude_m)
    if (
        not math.isfinite(h_geom_m)
        or h_geom_m < 0.0
        or h_geom_m > _MAX_GEOMETRIC_ALTITUDE_M
    ):
        raise ValueError("altitude_m must be finite and within [0, 86000] m")
    h_m = _geopotential_altitude(h_geom_m)

    layers = (
        (0.0, 11_000.0, -0.0065),
        (11_000.0, 20_000.0, 0.0),
        (20_000.0, 32_000.0, 0.0010),
        (32_000.0, 47_000.0, 0.0028),
        (47_000.0, 51_000.0, 0.0),
        (51_000.0, 71_000.0, -0.0028),
        (
            71_000.0,
            _geopotential_altitude(_MAX_GEOMETRIC_ALTITUDE_M),
            -0.0020,
        ),
    )
    T_base_K = 288.15
    p_base_Pa = 101_325.0
    h_base_m = 0.0

    for _, h_top_m, lapse_K_per_m in layers:
        if h_m <= h_top_m:
            dh_m = h_m - h_base_m
            if abs(lapse_K_per_m) < 1.0e-12:
                T_K = T_base_K
                p_Pa = p_base_Pa * math.exp(
                    (-_STANDARD_GRAVITY_M_PER_S2 * dh_m)
                    / (_DRY_AIR_GAS_CONSTANT_J_PER_KG_K * T_K)
                )
            else:
                T_K = T_base_K + lapse_K_per_m * dh_m
                p_Pa = p_base_Pa * pow(
                    T_K / T_base_K,
                    -_STANDARD_GRAVITY_M_PER_S2
                    / (_DRY_AIR_GAS_CONSTANT_J_PER_KG_K * lapse_K_per_m),
                )
            return AtmosphereState(
                T=float(T_K),
                p=float(p_Pa),
                rho=float(
                    p_Pa / (_DRY_AIR_GAS_CONSTANT_J_PER_KG_K * T_K)
                ),
            )

        dh_m = h_top_m - h_base_m
        if abs(lapse_K_per_m) < 1.0e-12:
            p_base_Pa *= math.exp(
                (-_STANDARD_GRAVITY_M_PER_S2 * dh_m)
                / (_DRY_AIR_GAS_CONSTANT_J_PER_KG_K * T_base_K)
            )
        else:
            T_next_K = T_base_K + lapse_K_per_m * dh_m
            p_base_Pa *= pow(
                T_next_K / T_base_K,
                -_STANDARD_GRAVITY_M_PER_S2
                / (_DRY_AIR_GAS_CONSTANT_J_PER_KG_K * lapse_K_per_m),
            )
            T_base_K = T_next_K
        h_base_m = h_top_m

    raise RuntimeError("USSA1976 layer lookup failed for a validated altitude")


def ussa1976_0_32km(*, h_m: float, R_gas_J_per_kgK: float) -> tuple[float, float, float]:
    """Return ``(p_Pa, rho_kg_m3, T_K)`` using the full USSA model.

    The function name is retained for API compatibility; the model supports
    geometric altitudes through 86 km. ``R_gas_J_per_kgK`` is retained only
    for call compatibility and no longer changes the strict USSA constants.
    """
    compatibility_R = float(R_gas_J_per_kgK)
    if not math.isfinite(compatibility_R) or compatibility_R <= 0.0:
        raise ValueError("R_gas_J_per_kgK must be finite and positive")
    atm = ussa1976(float(h_m))
    return float(atm.p), float(atm.rho), float(atm.T)
