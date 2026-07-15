"""USSA1976 thin alias — delegates to isa1976 with geopotential correction.

This module exists only for backward compatibility. All active code paths use
the single authoritative `isa1976` implementation.
"""

from __future__ import annotations

from .isa1976 import isa1976 as _isa1976


def ussa1976_0_32km(*, h_m: float, R_gas_J_per_kgK: float) -> tuple[float, float, float]:
    """Return (p_Pa, rho_kg_m3, T_K) — thin alias to isa1976.

    The name "0_32km" is historical. The underlying isa1976 covers 0–86 km.
    """
    atm = _isa1976(float(h_m), R=float(R_gas_J_per_kgK))
    return float(atm.p), float(atm.rho), float(atm.T)