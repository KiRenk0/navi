"""Boundary-layer edge conditions for the fully turbulent Taw chain.

Closure (one thermodynamic model throughout: thermally perfect gas with the
Fluent NASA-9 ``h(T)``, ``s0(T)`` and ``p = rho R T``):

1. Reference shock.  A strip's reference shock is a normal shock with normal
   Mach number ``M_inf * s_ref`` (``s_ref`` = reference incidence).  Mass,
   momentum and total enthalpy are solved with the TPG ``h(T)``; the
   post-shock static state fixes the reference entropy ``s_ref_entropy``.
   ``M_inf * s_ref <= 1`` means no shock and the freestream entropy applies.
2. Local edge state.  The surface static pressure ``p_e`` comes from the
   modified-Newtonian pressure model.  The edge state lies on the reference
   isentrope: ``s0(T_e) - R ln p_e = s_ref_entropy``.  Then
   ``V_e^2 = 2 (h0 - h(T_e))``.

If ``h(T_e) > h0`` the pressure/reference pair has no admissible edge state in
this model.  That is reported as a failed state; it is never rewritten into a
stagnation point.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from ..types import EdgeConditions, GasModel


@dataclass(frozen=True)
class ReferenceShockState:
    """Post-shock static state of the TPG reference normal shock."""

    normal_mach: float
    p2_Pa: float
    T2_K: float
    rho2_kg_m3: float
    u2_m_s: float
    entropy_J_kgK: float  # s0(T2) - R ln p2 (same datum as every edge state)
    mass_residual: float
    momentum_residual: float
    energy_residual: float


@dataclass(frozen=True)
class EdgeSolution:
    """Edge state plus the residuals and status needed for auditing."""

    edge: EdgeConditions | None
    status: str  # "ok" or a failure reason
    h_e_J_kg: float
    h0_J_kg: float
    raw_h_e_J_kg: float
    energy_residual_J_kg: float
    entropy_residual_J_kgK: float
    reference: ReferenceShockState
    in_property_fit_range: bool


def _entropy(tpg, T: float, p: float, R: float) -> float:
    return float(tpg.s0_from_T(T)) - R * float(np.log(p))


def solve_reference_normal_shock(
    *,
    gas: GasModel,
    normal_mach: float,
    p_inf: float,
    T_inf: float,
) -> ReferenceShockState:
    """Solve a TPG normal shock (mass, momentum, total enthalpy)."""

    return _solve_reference_normal_shock_cached(
        id(gas.tpg), gas.tpg, float(gas.R), float(normal_mach), float(p_inf), float(T_inf)
    )


@lru_cache(maxsize=4096)
def _solve_reference_normal_shock_cached(
    _tpg_id: int, tpg, R: float, normal_mach: float, p_inf: float, T_inf: float
) -> ReferenceShockState:
    if not (np.isfinite(normal_mach) and normal_mach >= 0.0):
        raise ValueError("reference normal Mach must be finite and non-negative")
    rho1 = p_inf / (R * T_inf)
    if normal_mach <= 1.0:
        return ReferenceShockState(
            normal_mach=normal_mach,
            p2_Pa=p_inf,
            T2_K=T_inf,
            rho2_kg_m3=rho1,
            u2_m_s=float(normal_mach * tpg.a_T(T_inf)),
            entropy_J_kgK=_entropy(tpg, T_inf, p_inf, R),
            mass_residual=0.0,
            momentum_residual=0.0,
            energy_residual=0.0,
        )
    u1 = normal_mach * float(tpg.a_T(T_inf))
    h1 = float(tpg.h_from_T(T_inf))
    H = h1 + 0.5 * u1 * u1

    def state(eps: float) -> tuple[float, float, float]:
        # eps = rho1 / rho2 = u2 / u1 (mass); momentum gives p2.
        p2 = p_inf + rho1 * u1 * u1 * (1.0 - eps)
        T2 = p2 * eps / (R * rho1)
        return p2, T2, u1 * eps

    def energy(eps: float) -> float:
        _, T2, u2 = state(eps)
        return float(tpg.h_from_T(T2)) + 0.5 * u2 * u2 - H

    # f(eps) < 0 on the over-compressed side (T2 below T_inf is not a shock
    # state) and f > 0 between the shock root and the trivial root eps = 1.
    # The TPG root lies below the perfect-gas density ratio (cp rises with T),
    # so the bracket is [eps(T2 = T_inf), midpoint(eps_pg, 1)].
    gamma_inf = float(tpg.gamma_T(T_inf))
    m2 = normal_mach * normal_mach
    eps_pg = ((gamma_inf - 1.0) * m2 + 2.0) / ((gamma_inf + 1.0) * m2)
    # T2(eps) = (p_inf + rho1 u1^2 (1-eps)) eps / (R rho1); smaller root of
    # T2 = T_inf is eps = 1/(gamma M^2)-like; solve the quadratic exactly.
    q = rho1 * u1 * u1
    # q eps^2 - (p_inf + q) eps + R rho1 T_inf = 0
    disc = (p_inf + q) ** 2 - 4.0 * q * R * rho1 * T_inf
    lo = ((p_inf + q) - np.sqrt(max(disc, 0.0))) / (2.0 * q)
    hi = 0.5 * (eps_pg + 1.0)
    f_lo, f_hi = energy(lo), energy(hi)
    if not (f_lo < 0.0 < f_hi):
        raise ValueError("TPG normal shock bracket failed")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        f_mid = energy(mid)
        if f_mid < 0.0:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1.0e-15:
            break
    root = 0.5 * (lo + hi)
    p2, T2, u2 = state(root)
    rho2 = p2 / (R * T2)
    return ReferenceShockState(
        normal_mach=normal_mach,
        p2_Pa=float(p2),
        T2_K=float(T2),
        rho2_kg_m3=float(rho2),
        u2_m_s=float(u2),
        entropy_J_kgK=_entropy(tpg, T2, p2, R),
        mass_residual=float(rho1 * u1 - rho2 * u2) / (rho1 * u1),
        momentum_residual=float(p_inf + rho1 * u1 * u1 - p2 - rho2 * u2 * u2)
        / (rho1 * u1 * u1),
        energy_residual=float(energy(root)),
    )


def solve_edge_state(
    *,
    gas: GasModel,
    ma_inf: float,
    p_inf: float,
    T_inf: float,
    cp_pressure: float,
    reference_incidence_s: float,
) -> EdgeSolution:
    """Edge state on the reference isentrope at the local surface pressure."""

    tpg = gas.tpg
    R = float(gas.R)
    ma_value = float(ma_inf)
    p_inf = float(p_inf)
    T_inf = float(T_inf)
    gamma = float(gas.gamma)
    s_ref = float(np.clip(float(reference_incidence_s), 0.0, 1.0))

    a_inf = float(tpg.a_T(T_inf))
    v_inf = ma_value * a_inf
    h0 = float(tpg.h_from_T(T_inf)) + 0.5 * v_inf * v_inf

    reference = solve_reference_normal_shock(
        gas=gas, normal_mach=ma_value * s_ref, p_inf=p_inf, T_inf=T_inf
    )
    p_e = (1.0 + 0.5 * gamma * ma_value**2 * float(cp_pressure)) * p_inf
    s0_e = reference.entropy_J_kgK + R * float(np.log(p_e))
    T_e = float(tpg.T_from_s0(s0_e))
    h_e = float(tpg.h_from_T(T_e))
    entropy_residual = _entropy(tpg, T_e, p_e, R) - reference.entropy_J_kgK
    in_range = bool(tpg.in_fit_range(T_e))

    if h_e > h0:
        return EdgeSolution(
            edge=None,
            status="edge_static_enthalpy_exceeds_total",
            h_e_J_kg=float("nan"),
            h0_J_kg=h0,
            raw_h_e_J_kg=h_e,
            energy_residual_J_kg=float("nan"),
            entropy_residual_J_kgK=entropy_residual,
            reference=reference,
            in_property_fit_range=in_range,
        )
    v_e = float(np.sqrt(2.0 * (h0 - h_e)))
    a_e = float(tpg.a_T(T_e))
    edge = EdgeConditions(
        p_e=float(p_e),
        rho_e=float(gas.rho(p_e, T_e)),
        T_e=T_e,
        ma_e=float(v_e / a_e),
        a_e=a_e,
        v_e=v_e,
        mu_e=float(gas.mu(T_e)),
    )
    return EdgeSolution(
        edge=edge,
        status="ok",
        h_e_J_kg=h_e,
        h0_J_kg=h0,
        raw_h_e_J_kg=h_e,
        energy_residual_J_kg=float(h_e + 0.5 * v_e * v_e - h0),
        entropy_residual_J_kgK=entropy_residual,
        reference=reference,
        in_property_fit_range=in_range,
    )


def compute_edge_conditions(
    *,
    gas: GasModel,
    ma_inf: float,
    p_inf: float,
    T_inf: float,
    rho_inf: float | None = None,
    cp_pressure: float,
    reference_incidence_s: float,
) -> EdgeConditions:
    """Return the edge state or raise if the model has no admissible state."""

    del rho_inf  # density follows from p_inf, T_inf and R
    solution = solve_edge_state(
        gas=gas,
        ma_inf=ma_inf,
        p_inf=p_inf,
        T_inf=T_inf,
        cp_pressure=cp_pressure,
        reference_incidence_s=reference_incidence_s,
    )
    if solution.edge is None:
        raise ValueError(f"edge state failed: {solution.status}")
    return solution.edge
