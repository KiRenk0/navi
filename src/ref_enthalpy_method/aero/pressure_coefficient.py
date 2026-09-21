"""Pressure-coefficient closure used by the formal 0920 Taw chain."""

from __future__ import annotations

import math


def newtonian_like_cp(*, phi_rad: float, A: float, n: float) -> float:
    """Return the formal ``Cp = A * sin(phi)^n`` closure."""
    sine = math.sin(float(phi_rad))
    if sine <= 0.0:
        return 0.0
    return float(A) * sine ** float(n)
