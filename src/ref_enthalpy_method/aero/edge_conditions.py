"""Boundary-layer edge (external) conditions derived from the doc.

Equations covered:
- (2.48) pe/p_inf
- (2.49) pc/p_inf (leading edge reference pressure)
- (2.50) rhoc/rho_inf (Rankine-Hugoniot for normal shock proxy)
- (2.51)-(2.52) rhoe/rho_inf
- (2.53) Te
- (2.54) Mae

Active TPG chain:
- Edge conditions use TPG isentropic relations with the frozen-gamma pressure closure.
"""

from __future__ import annotations

import numpy as np

from ..types import EdgeConditions, GasModel


def compute_edge_conditions(
    *,
    gas: GasModel,
    ma_inf: float,
    p_inf: float,
    T_inf: float,
    rho_inf: float,
    cp_pressure: float,
    cp0_pressure: float,
) -> EdgeConditions:
    """Compute TPG edge conditions at a windward surface location."""

    tpg = gas.tpg
    R = float(gas.R)

    ma_value = float(ma_inf)
    p_inf = float(p_inf)
    T_inf_val = float(T_inf)
    rho_inf_val = float(rho_inf)

    gamma = float(gas.gamma)

    a_inf = float(tpg.a_T(T_inf_val))
    v_inf = ma_value * a_inf
    h_inf_tpg = float(tpg.h_from_T(T_inf_val))
    h0 = h_inf_tpg + 0.5 * v_inf * v_inf

    pe_over_pinf = 1.0 + (gamma / 2.0) * ma_value**2 * float(cp_pressure)
    p_e = pe_over_pinf * p_inf

    pc_over_pinf = 1.0 + (gamma / 2.0) * ma_value**2 * float(cp0_pressure)
    p_c = pc_over_pinf * p_inf

    rhoc_over_rhoinf = ((gamma + 1.0) * pc_over_pinf + (gamma - 1.0)) / (
        (gamma - 1.0) * pc_over_pinf + (gamma + 1.0)
    )

    Tc = T_inf_val * pc_over_pinf / rhoc_over_rhoinf

    s0_c = float(tpg.s0_from_T(float(Tc)))
    s0_e = s0_c + R * float(np.log(max(float(p_e) / max(float(p_c), 1e-12), 1e-12)))
    T_e = float(tpg.T_from_s0(float(s0_e)))

    h_e_tpg = float(tpg.h_from_T(T_e))
    # The pressure/entropy closure can otherwise produce a static enthalpy
    # above the freestream total enthalpy near a blunt nose.  That state has
    # no real edge velocity.  Enforce the total-enthalpy bound and represent
    # it as the physical stagnation limit instead of silently clipping only
    # Ve^2 while leaving T_e above T0.
    if h_e_tpg > h0:
        h_e_tpg = float(h0)
        T_e = float(tpg.T_from_h(h_e_tpg))

    rho_e = float(gas.rho(p_e, T_e)) if float(T_e) > 0 else rho_inf_val

    ve_sq = float(2.0 * (h0 - h_e_tpg))

    ve_sq = max(ve_sq, 0.0)

    v_e = float(np.sqrt(ve_sq))
    a_e = float(tpg.a_T(T_e))
    ma_e = float(v_e / a_e) if a_e > 0 else 0.0

    mu_e = float(gas.mu(T_e))

    return EdgeConditions(
        p_e=p_e, rho_e=rho_e, T_e=T_e, ma_e=ma_e, a_e=a_e, v_e=v_e, mu_e=mu_e
    )
