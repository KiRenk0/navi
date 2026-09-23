"""Pressure-coefficient closure used by the formal 0920 Taw chain."""

from __future__ import annotations

import math


def modified_newtonian_cp_max(*, mach: float, gamma: float) -> float:
    """Return the perfect-gas stagnation ``Cp`` used by modified Newtonian theory.

    The value is the normal-shock stagnation pressure coefficient.  It depends
    on the freestream Mach number and gamma; using a fixed coefficient is not
    consistent across the requested Mach 5--12 envelope.
    """

    ma = float(mach)
    g = float(gamma)
    if not (math.isfinite(ma) and math.isfinite(g) and ma > 1.0 and g > 1.0):
        raise ValueError("modified Newtonian Cp requires Mach > 1 and gamma > 1")
    shock_pressure_ratio = ((g + 1.0) * ma * ma / 2.0) ** (g / (g - 1.0)) * (
        (g + 1.0) / (2.0 * g * ma * ma - (g - 1.0))
    ) ** (1.0 / (g - 1.0))
    return 2.0 * (shock_pressure_ratio - 1.0) / (g * ma * ma)


def modified_newtonian_cp(*, incidence_s: float, mach: float, gamma: float) -> float:
    """Return ``Cp_max(M, gamma) * max(-u.n, 0)^2``.

    ``incidence_s`` is the signed outward-normal incidence.  The pressure
    increment is zero on leeward and tangent faces.
    """

    s = float(incidence_s)
    if not math.isfinite(s):
        return 0.0
    s = max(0.0, min(1.0, s))
    return modified_newtonian_cp_max(mach=mach, gamma=gamma) * s * s
