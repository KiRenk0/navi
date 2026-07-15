"""Boundary-layer edge (external) conditions derived from the doc.

Equations covered:
- (2.48) pe/p_inf
- (2.49) pc/p_inf (leading edge reference pressure)
- (2.50) rhoc/rho_inf (Rankine-Hugoniot for normal shock proxy)
- (2.51)-(2.52) rhoe/rho_inf
- (2.53) Te
- (2.54) Mae
- (2.55)-(2.56) effective alpha and Mach with sweep/alpha

Active TPG chain:
- Edge conditions use TPG isentropic relations with the frozen-gamma pressure closure.
"""

from __future__ import annotations

import math

import numpy as np

from ..types import EdgeConditions, GasModel


def effective_alpha(alpha_rad: float, chi_w_rad: float) -> float:
    """Eq. (2.55): effective angle of attack with sweep."""

    return math.atan(math.tan(float(alpha_rad)) / math.cos(float(chi_w_rad)))


def effective_ma_inf(ma_inf: float, *, alpha_rad: float, chi_w_rad: float) -> float:
    """Eq. (2.56): effective Mach number with sweep and AoA."""

    ma = float(ma_inf)
    chi = float(chi_w_rad)
    a = float(alpha_rad)
    factor = 1.0 - (math.sin(chi) ** 2) * (math.cos(a) ** 2)
    return ma * math.sqrt(max(factor, 0.0))


# Global counters for TPG V_e^2 < 0 occurrences (reported per call)
_TPG_VE2_NEG_COUNT: int = 0


def _compute_edge_conditions_tpg(
    *,
    gas: GasModel,
    ma_inf: float,
    p_inf: float,
    T_inf: float,
    rho_inf: float,
    cp_pressure: float,
    cp0_pressure: float,
    ma_inf_effective: float | None = None,
) -> EdgeConditions:
    global _TPG_VE2_NEG_COUNT

    tpg = gas.tpg
    R = float(gas.R)

    ma_eff = float(ma_inf_effective) if ma_inf_effective is not None else float(ma_inf)
    p_inf = float(p_inf)
    T_inf_val = float(T_inf)
    rho_inf_val = float(rho_inf)

    k_legacy = float(gas.gamma)

    a_inf = float(tpg.a_T(T_inf_val))
    v_inf = float(ma_eff) * a_inf
    h_inf_tpg = float(tpg.h_from_T(T_inf_val))
    h0 = h_inf_tpg + 0.5 * v_inf * v_inf

    pe_over_pinf = 1.0 + (k_legacy / 2.0) * (float(ma_eff) ** 2) * float(cp_pressure)
    p_e = pe_over_pinf * p_inf

    pc_over_pinf = 1.0 + (k_legacy / 2.0) * (float(ma_eff) ** 2) * float(cp0_pressure)
    p_c = pc_over_pinf * p_inf

    rhoc_over_rhoinf = (6.0 * pc_over_pinf + 1.0) / (pc_over_pinf + 6.0)

    Tc = T_inf_val * pc_over_pinf / rhoc_over_rhoinf

    s0_c = float(tpg.s0_from_T(float(Tc)))
    s0_e = s0_c + R * float(np.log(max(float(p_e) / max(float(p_c), 1e-12), 1e-12)))
    T_e = float(tpg.T_from_s0(float(s0_e)))

    rho_e = float(p_e) / (R * float(T_e)) if float(T_e) > 0 else rho_inf_val

    h_e_tpg = float(tpg.h_from_T(T_e))
    ve_sq = float(2.0 * (h0 - h_e_tpg))

    if ve_sq < 0.0:
        _TPG_VE2_NEG_COUNT += 1
        ve_sq = 0.0

    v_e = float(np.sqrt(ve_sq))
    a_e = float(tpg.a_T(T_e))
    ma_e = float(v_e / a_e) if a_e > 0 else 0.0

    mu_e = float(gas.mu(T_e))

    return EdgeConditions(p_e=p_e, rho_e=rho_e, T_e=T_e, ma_e=ma_e, a_e=a_e, v_e=v_e, mu_e=mu_e)


def reset_tpg_ve2_neg_count() -> None:
    global _TPG_VE2_NEG_COUNT
    _TPG_VE2_NEG_COUNT = 0


def get_tpg_ve2_neg_count() -> int:
    return int(_TPG_VE2_NEG_COUNT)


def compute_edge_conditions(
    *,
    gas: GasModel,
    ma_inf: float,
    p_inf: float,
    T_inf: float,
    rho_inf: float,
    cp_pressure: float,
    cp0_pressure: float,
    ma_inf_effective: float | None = None,
) -> EdgeConditions:
    """Compute TPG edge conditions at a windward surface location."""

    return _compute_edge_conditions_tpg(
        gas=gas,
        ma_inf=float(ma_inf),
        p_inf=float(p_inf),
        T_inf=float(T_inf),
        rho_inf=float(rho_inf),
        cp_pressure=float(cp_pressure),
        cp0_pressure=float(cp0_pressure),
        ma_inf_effective=ma_inf_effective,
    )


compute_edge_conditions_tpg = _compute_edge_conditions_tpg
