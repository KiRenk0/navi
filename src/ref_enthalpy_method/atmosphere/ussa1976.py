"""US Standard Atmosphere 1976 for geometric altitudes from 0 to 86 km."""

from __future__ import annotations

import math
from dataclasses import dataclass


_EARTH_EFFECTIVE_RADIUS_M = 6_356_766.0


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
    *,
    R: float = 287.0,
    g0: float = 9.80665,
) -> AtmosphereState:
    """Return the USSA1976 state at a geometric altitude in metres."""
    h_geom_m = float(altitude_m)
    R = float(R)
    g0 = float(g0)
    if not math.isfinite(h_geom_m) or h_geom_m < 0.0:
        raise ValueError("altitude_m must be finite and nonnegative")
    if not math.isfinite(R) or R <= 0.0:
        raise ValueError("R must be finite and positive")
    if not math.isfinite(g0) or g0 <= 0.0:
        raise ValueError("g0 must be finite and positive")
    h_m = _geopotential_altitude(h_geom_m)

    layers = (
        (0.0, 11_000.0, -0.0065),
        (11_000.0, 20_000.0, 0.0),
        (20_000.0, 32_000.0, 0.0010),
        (32_000.0, 47_000.0, 0.0028),
        (47_000.0, 51_000.0, 0.0),
        (51_000.0, 71_000.0, -0.0028),
        (71_000.0, 86_000.0, -0.0020),
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
                    (-g0 * dh_m) / (R * T_K)
                )
            else:
                T_K = T_base_K + lapse_K_per_m * dh_m
                p_Pa = p_base_Pa * pow(
                    T_K / T_base_K,
                    -g0 / (R * lapse_K_per_m),
                )
            return AtmosphereState(
                T=float(T_K),
                p=float(p_Pa),
                rho=float(p_Pa / (R * T_K)),
            )

        dh_m = h_top_m - h_base_m
        if abs(lapse_K_per_m) < 1.0e-12:
            p_base_Pa *= math.exp(
                (-g0 * dh_m) / (R * T_base_K)
            )
        else:
            T_next_K = T_base_K + lapse_K_per_m * dh_m
            p_base_Pa *= pow(
                T_next_K / T_base_K,
                -g0 / (R * lapse_K_per_m),
            )
            T_base_K = T_next_K
        h_base_m = h_top_m

    return AtmosphereState(
        T=float(T_base_K),
        p=float(p_base_Pa),
        rho=float(p_base_Pa / (R * T_base_K)),
    )


def ussa1976_0_32km(*, h_m: float, R_gas_J_per_kgK: float) -> tuple[float, float, float]:
    """Return ``(p_Pa, rho_kg_m3, T_K)`` using the full USSA model.

    The function name is retained for API compatibility; the model supports
    geometric altitudes through 86 km.
    """
    atm = ussa1976(float(h_m), R=float(R_gas_J_per_kgK))
    return float(atm.p), float(atm.rho), float(atm.T)
