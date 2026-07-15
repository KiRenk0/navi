"""Busemann theory pressure coefficient approximation + alternative Cp models.

Implements eq. (2.47) and its helper coefficients c1/c2/c3 from Ma_inf.
Also provides newtonian_like Cp = A * sin(phi)^n and a dispatch function.
"""

from __future__ import annotations

import math


def _busemann_coeffs(ma_inf: float) -> tuple[float, float, float]:
    ma = float(ma_inf)
    if ma <= 1.0:
        raise ValueError("Busemann approximation expects supersonic/hypersonic Ma_inf > 1.")

    c1 = 2.0 / math.sqrt(ma**2 - 1.0)
    c2 = ((ma**2 - 2.0) ** 2 + 1.4 * ma**4) / ((ma**2 - 1.0) ** 2)
    c3 = (
        (0.36 * ma**8 - 1.493 * ma**6 + 3.6 * ma**4 - 2.0 * ma**2 + 1.33)
        / ((ma**2 - 1.0) ** 3.5)
    )
    return c1, c2, c3


def busemann_cp(*, ma_inf: float, phi_rad: float) -> float:
    """Pressure coefficient Cp from Busemann theory (eq. 2.47).

    Parameters
    - ma_inf: freestream Mach number (use effective Mach if you apply sweep/alpha correction first)
    - phi_rad: local angle between tangent and freestream direction (radians)
    """

    c1, c2, c3 = _busemann_coeffs(ma_inf)
    phi = float(phi_rad)
    return c1 * phi + c2 * phi**2 + c3 * phi**3


def newtonian_like_cp(*, phi_rad: float, A: float = 0.38, n: float = 1.15) -> float:
    """Newtonian-like Cp = A * sin(phi)^n, fitted from Fluent data.

    Default parameters from 3-case validation (Ma=6-8, α=5-10°, h=30-50km):
      A = 0.38, n = 1.15
    """
    phi = float(phi_rad)
    s = math.sin(phi)
    if s <= 0.0:
        return 0.0
    return float(A) * s ** float(n)


def compute_cp(*, ma_inf: float, phi_rad: float, cp_model: str = "busemann",
               newtonian_A: float = 0.38, newtonian_n: float = 1.15) -> float:
    """Dispatch Cp computation to the selected model.

    Parameters
    - cp_model: "busemann" (default, legacy) or "newtonian_like"
    """
    if cp_model == "newtonian_like":
        return newtonian_like_cp(phi_rad=phi_rad, A=newtonian_A, n=newtonian_n)
    return busemann_cp(ma_inf=ma_inf, phi_rad=phi_rad)

