"""Minimal ISA1976 atmosphere (0-86km) with geopotential altitude correction.

Input h_m is geometric altitude (m). The function internally converts to
geopotential altitude per USSA1976 convention before layer lookup.

This is the sole authoritative atmosphere model for the project.
Default for 20-40 km formal parameter domain.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Earth effective radius for USSA1976 geopotential conversion (m)
_R_E = 6356766.0


@dataclass(frozen=True)
class AtmosphereState:
    T: float  # K
    p: float  # Pa
    rho: float  # kg/m^3


def _geopotential(h_geom_m: float) -> float:
    """Convert geometric altitude (m) to geopotential altitude (m)."""
    return (_R_E * h_geom_m) / (_R_E + h_geom_m)


def isa1976(altitude_m: float, *, R: float = 287.0, g0: float = 9.80665) -> AtmosphereState:
    """Return ISA1976 state at geometric altitude (m) with geopotential correction.

    Standard regression (20-40 km, geometric input):
    - 30 km: T ≈ 226.509 K, p ≈ 1197 Pa
    - 35 km: T ≈ 236.5 K, p ≈ 574.6 Pa
    - 40 km: T ≈ 250.35 K, p ≈ 286.8 Pa

    If upstream data already provides (T_inf, p_inf), use explicit override.
    """

    # Layers up to ~86 km; values from standard ISA tables.
    # Base: sea level
    T0 = 288.15
    p0 = 101325.0

    h = float(altitude_m)
    if h < 0:
        h = 0.0

    # Convert geometric to geopotential altitude (USSA1976 convention)
    h = _geopotential(h)

    # Define layer boundaries (m) and lapse rates (K/m)
    layers = [
        (0.0, 11000.0, -0.0065),
        (11000.0, 20000.0, 0.0),
        (20000.0, 32000.0, 0.0010),
        (32000.0, 47000.0, 0.0028),
        (47000.0, 51000.0, 0.0),
        (51000.0, 71000.0, -0.0028),
        (71000.0, 86000.0, -0.0020),
    ]

    T_b = T0
    p_b = p0
    h_b = 0.0

    for h0, h1, L in layers:
        if h <= h1:
            # compute within this layer from (h_b, T_b, p_b)
            dh = h - h_b
            if abs(L) < 1e-12:
                T = T_b
                p = p_b * math.exp((-g0 * dh) / (R * T))
            else:
                T = T_b + L * dh
                p = p_b * pow(T / T_b, -g0 / (R * L))
            rho = p / (R * T)
            return AtmosphereState(T=T, p=p, rho=rho)

        # advance to next layer base
        dh = h1 - h_b
        if abs(L) < 1e-12:
            p_b = p_b * math.exp((-g0 * dh) / (R * T_b))
            # T_b unchanged
        else:
            T_next = T_b + L * dh
            p_b = p_b * pow(T_next / T_b, -g0 / (R * L))
            T_b = T_next
        h_b = h1

    # Above 86km: clamp to top layer result
    rho = p_b / (R * T_b)
    return AtmosphereState(T=T_b, p=p_b, rho=rho)

