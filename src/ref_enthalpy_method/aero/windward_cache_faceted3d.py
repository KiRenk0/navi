"""Windward edge-cache for faceted 3D (sx, sy) slopes.

This is a minimal 3D upgrade that preserves the original solver architecture:
- keep the same reference-enthalpy "soup"
- replace the 2D windward slope dz/dx with a facet-normal based inflow angle phi(sx, sy)

Coordinate convention:
- x: streamwise (chordwise)
- y: spanwise
- z: upward

Definitions:
- surface slopes: sx = dz/dx, sy = dz/dy
- (unnormalized) facet normal used here: n = (sx, sy, 1)
- effective AoA with sweep: alpha_e (same as 2D solver, via independence principle)
- incoming unit flow direction (no sideslip): u = (cos(alpha_e), 0, -sin(alpha_e))

We choose phi such that it *exactly* reduces to the baseline 2D definition when sy=0:
    phi_2d = alpha_e - atan(sx)

Derivation (sy=0):
    s = - u路n_hat = (sin(alpha_e) - sx*cos(alpha_e)) / sqrt(1+sx^2) = sin(phi_2d)
    => phi = asin(s) = alpha_e - atan(sx)   (within principal range)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..aero.busemann import busemann_cp, compute_cp
from ..aero.edge_conditions import compute_edge_conditions, effective_alpha, effective_ma_inf
from ..aero.transition import transition_reynolds, transition_weight
from ..config.lf_qw import LfQwConfig
from ..heatflux.windward import windward_ref_enthalpy_branches
from ..types import EdgeConditions, GasModel


@dataclass(frozen=True)
class Faceted3DEdgeInflow:
    alpha_input_rad: float
    alpha_effective_rad: float
    alpha_edge_rad: float
    mach_input: float
    mach_effective: float
    mach_edge: float
    use_effective_alpha: bool
    use_effective_mach: bool


@dataclass(frozen=True)
class WindwardEdgeCacheFaceted3D:
    edges: list[EdgeConditions]  # length nx
    x_over_c: np.ndarray  # (nx,)
    x_phys: np.ndarray  # (nx,)
    lf_cfg: LfQwConfig
    transition_x_over_c: float | None
    alpha_edge_rad: float = float("nan")
    alpha_effective_rad: float = float("nan")
    mach_edge: float = float("nan")
    mach_effective: float = float("nan")
    use_effective_alpha: bool = True
    use_effective_mach: bool = False
    phi_arr: np.ndarray | None = None  # (nx,) inflow angle rad
    cp_arr: np.ndarray | None = None  # (nx,) Busemann cp
    cp0_raw: float = float("nan")
    cp0_used: float = float("nan")
    cp0_override_applied: bool = False
    cp0_regularized: bool = False
    min_ma_e_raw: float = float("nan")
    min_ma_e_used: float = float("nan")
    collapsed_edge_count_raw: int = 0
    collapsed_edge_count_used: int = 0
    taw_tpg: np.ndarray | None = None  # (nx,) Route A-TPG adiabatic wall temp
    h0_tpg: float | None = None  # total enthalpy (J/kg) from TPG thermo
    tpg_ve2_neg_count: int = 0  # V_e^2 < 0 occurrences per strip


_EDGE_MAE_FLOOR = 1.0
_CP0_BISECT_ITERS = 28
_CP0_BISECT_TOL = 1e-6

# Dhawan-Narasimha Simon ZPG closure constants (hardcoded, matching solver_faceted3d.py diagnostic)
_DN_CONST_0p412 = 0.412
_DN_CONST_0p664 = 0.664
_DN_CONST_124 = 124.0
_DN_XI_99 = float(np.sqrt(-np.log(0.01) / _DN_CONST_0p412))


def resolve_faceted3d_edge_inflow(
    *,
    mach: float,
    alpha_deg: float,
    sweep_le_deg: float,
    use_effective_alpha: bool = True,
    use_effective_mach: bool = False,
) -> Faceted3DEdgeInflow:
    """Resolve the alpha/Mach pair used by the faceted-3D windward edge chain.

    The current faceted3d engineering default keeps the sweep-corrected alpha
    but uses the freestream Mach in the edge chain. Experimental studies can
    independently toggle the alpha and Mach corrections to test whether sweep is
    already sufficiently represented by the local 3D facet normal.
    """

    alpha_input_rad = float(np.deg2rad(float(alpha_deg)))
    chi_rad = float(np.deg2rad(float(sweep_le_deg)))
    alpha_effective_rad = float(effective_alpha(alpha_input_rad, chi_rad))
    mach_effective = float(effective_ma_inf(float(mach), alpha_rad=alpha_input_rad, chi_w_rad=chi_rad))
    alpha_edge_rad = float(alpha_effective_rad if bool(use_effective_alpha) else alpha_input_rad)
    mach_edge = float(mach_effective if bool(use_effective_mach) else float(mach))
    return Faceted3DEdgeInflow(
        alpha_input_rad=float(alpha_input_rad),
        alpha_effective_rad=float(alpha_effective_rad),
        alpha_edge_rad=float(alpha_edge_rad),
        mach_input=float(mach),
        mach_effective=float(mach_effective),
        mach_edge=float(mach_edge),
        use_effective_alpha=bool(use_effective_alpha),
        use_effective_mach=bool(use_effective_mach),
    )


def _phi_from_slopes_3d(*, alpha_e: float, sx: float, sy: float) -> float:
    """3D inflow angle phi using (sx, sy) facet slopes.

    Returns phi in radians (principal asin range).
    """

    a = float(alpha_e)
    sx = float(sx)
    sy = float(sy)
    # n = (sx, sy, 1) and u = (cos a, 0, -sin a)
    # s = -u路n_hat
    denom = float(np.sqrt(1.0 + sx * sx + sy * sy))
    if not (denom > 0.0):
        denom = 1.0
    s = (float(np.sin(a)) - sx * float(np.cos(a))) / denom
    s = float(np.clip(s, -1.0, 1.0))
    return float(np.arcsin(s))


def _build_edges_for_cp0(
    *,
    gas: GasModel,
    mach_edge: float,
    p_inf: float,
    T_inf: float,
    rho_inf: float,
    cp_arr: np.ndarray,
    cp0_pressure: float,
) -> tuple[list[EdgeConditions], float, int]:
    edges: list[EdgeConditions] = []
    min_ma_non_le = float("nan")
    collapsed_non_le = 0

    for i in range(int(cp_arr.size)):
        edge = compute_edge_conditions(
            gas=gas,
            ma_inf=float(mach_edge),
            p_inf=float(p_inf),
            T_inf=float(T_inf),
            rho_inf=float(rho_inf),
            cp_pressure=float(cp_arr[i]),
            cp0_pressure=float(cp0_pressure),
        )
        edges.append(edge)
        if i == 0:
            continue
        ma_e = float(edge.ma_e)
        if not np.isfinite(min_ma_non_le):
            min_ma_non_le = ma_e
        else:
            min_ma_non_le = min(min_ma_non_le, ma_e)
        if ma_e <= 0.0:
            collapsed_non_le += 1

    return edges, float(min_ma_non_le), int(collapsed_non_le)


def _regularize_cp0_for_supersonic_edge(
    *,
    gas: GasModel,
    mach_edge: float,
    p_inf: float,
    T_inf: float,
    rho_inf: float,
    cp_arr: np.ndarray,
    cp0_raw: float,
) -> tuple[list[EdgeConditions], float, bool, float, float, int, int]:
    raw_edges, min_ma_raw, collapsed_raw = _build_edges_for_cp0(
        gas=gas,
        mach_edge=float(mach_edge),
        p_inf=float(p_inf),
        T_inf=float(T_inf),
        rho_inf=float(rho_inf),
        cp_arr=np.asarray(cp_arr, dtype=float),
        cp0_pressure=float(cp0_raw),
    )

    # The strip-theory closure used downstream assumes a supersonic edge flow.
    # If the raw leading-edge reference pressure drives the strip subsonic, cap cp0
    # downward to the largest value that keeps the non-leading-edge edge states supersonic.
    if cp_arr.size <= 1 or not np.isfinite(min_ma_raw) or min_ma_raw >= _EDGE_MAE_FLOOR or not (float(cp0_raw) > 0.0):
        return raw_edges, float(cp0_raw), False, float(min_ma_raw), float(min_ma_raw), int(collapsed_raw), int(collapsed_raw)

    lo_cp0 = 0.0
    lo_edges, lo_min_ma, lo_collapsed = _build_edges_for_cp0(
        gas=gas,
        mach_edge=float(mach_edge),
        p_inf=float(p_inf),
        T_inf=float(T_inf),
        rho_inf=float(rho_inf),
        cp_arr=np.asarray(cp_arr, dtype=float),
        cp0_pressure=float(lo_cp0),
    )

    # Even cp0=0 can be the best available engineering fallback if the raw state collapses.
    if not np.isfinite(lo_min_ma) or lo_min_ma < _EDGE_MAE_FLOOR:
        use_lo = bool(np.isfinite(lo_min_ma) and lo_min_ma > min_ma_raw)
        if use_lo:
            return (
                lo_edges,
                float(lo_cp0),
                True,
                float(min_ma_raw),
                float(lo_min_ma),
                int(collapsed_raw),
                int(lo_collapsed),
            )
        return raw_edges, float(cp0_raw), False, float(min_ma_raw), float(min_ma_raw), int(collapsed_raw), int(collapsed_raw)

    hi_cp0 = float(cp0_raw)
    best_cp0 = float(lo_cp0)
    best_edges = lo_edges
    best_min_ma = float(lo_min_ma)
    best_collapsed = int(lo_collapsed)

    for _ in range(_CP0_BISECT_ITERS):
        if (hi_cp0 - lo_cp0) <= _CP0_BISECT_TOL:
            break
        mid_cp0 = 0.5 * (lo_cp0 + hi_cp0)
        mid_edges, mid_min_ma, mid_collapsed = _build_edges_for_cp0(
            gas=gas,
            mach_edge=float(mach_edge),
            p_inf=float(p_inf),
            T_inf=float(T_inf),
            rho_inf=float(rho_inf),
            cp_arr=np.asarray(cp_arr, dtype=float),
            cp0_pressure=float(mid_cp0),
        )
        if np.isfinite(mid_min_ma) and mid_min_ma >= _EDGE_MAE_FLOOR:
            lo_cp0 = float(mid_cp0)
            best_cp0 = float(mid_cp0)
            best_edges = mid_edges
            best_min_ma = float(mid_min_ma)
            best_collapsed = int(mid_collapsed)
        else:
            hi_cp0 = float(mid_cp0)

    return (
        best_edges,
        float(best_cp0),
        bool(best_cp0 < (float(cp0_raw) - _CP0_BISECT_TOL)),
        float(min_ma_raw),
        float(best_min_ma),
        int(collapsed_raw),
        int(best_collapsed),
    )


def build_windward_edge_cache_faceted3d(
    *,
    gas: GasModel,
    lf_cfg: LfQwConfig,
    mach: float,
    alpha_deg: float,
    sweep_le_deg: float,
    p_inf: float,
    rho_inf: float,
    T_inf: float,
    chord_m: float,
    xc_grid: np.ndarray,
    sx_arr: np.ndarray,
    sy_arr: np.ndarray,
    transition_x_over_c: float | None,
    cp0_override: float | None = None,
    use_effective_alpha: bool = True,
    use_effective_mach: bool = False,
    x_phys_override: np.ndarray | None = None,
    cp_model: str = "busemann",
    cp_newtonian_A: float = 0.38,
    cp_newtonian_n: float = 1.15,
) -> WindwardEdgeCacheFaceted3D:
    """Compute edge conditions along one windward strip for faceted 3D geometry.

    Engineering guard:
    - If the raw leading-edge reference pressure coefficient `cp0` drives the
      non-leading-edge edge states subsonic, reduce `cp0` just enough to keep the
      strip edge marginally supersonic again. This avoids a pathological `Ma_e=0`
      collapse that otherwise turns the whole strip heat flux to zero.
    """

    inflow = resolve_faceted3d_edge_inflow(
        mach=float(mach),
        alpha_deg=float(alpha_deg),
        sweep_le_deg=float(sweep_le_deg),
        use_effective_alpha=bool(use_effective_alpha),
        use_effective_mach=bool(use_effective_mach),
    )
    alpha_e = float(inflow.alpha_edge_rad)
    mach_edge = float(inflow.mach_edge)

    x_over_c = np.asarray(xc_grid, dtype=float).reshape(-1)
    sx_arr = np.asarray(sx_arr, dtype=float).reshape(-1)
    sy_arr = np.asarray(sy_arr, dtype=float).reshape(-1)
    if sx_arr.size != x_over_c.size or sy_arr.size != x_over_c.size:
        raise ValueError("sx_arr and sy_arr must have the same length as xc_grid")

    # Internal x clamp for strip-theory evaluation (does not affect sampling grid)
    x_min_over_c = float(getattr(lf_cfg, "x_model").x_min_over_c) if hasattr(lf_cfg, "x_model") else 0.003
    x_eff_over_c = np.maximum(x_over_c, max(x_min_over_c, 0.0))
    if x_phys_override is None:
        x_phys = np.maximum(x_eff_over_c * float(chord_m), 1e-6)
    else:
        x_phys = np.asarray(x_phys_override, dtype=float).reshape(-1)
        if x_phys.size != x_over_c.size:
            raise ValueError("x_phys_override must have the same length as xc_grid")
        x_phys = np.maximum(x_phys, 1e-6)

    # phi clamp
    phi_clamp = bool(lf_cfg.phi_clamp.enable)
    phi_min = float(lf_cfg.phi_clamp.phi_min_rad)

    # Cp0 at leading edge should not depend on the first sampling point.
    # If x/c does not start at 0, extrapolate (sx, sy) to x/c=0 using the first two points.
    sx0 = float(sx_arr[0])
    sy0 = float(sy_arr[0])
    try:
        if x_over_c.size >= 2 and float(x_over_c[0]) > 0.0:
            x0 = float(x_over_c[0])
            x1 = float(x_over_c[1])
            if x1 != x0:
                sx0 = float(sx_arr[0] + (0.0 - x0) * (float(sx_arr[1]) - float(sx_arr[0])) / (x1 - x0))
                sy0 = float(sy_arr[0] + (0.0 - x0) * (float(sy_arr[1]) - float(sy_arr[0])) / (x1 - x0))
    except Exception:
        sx0 = float(sx_arr[0])
        sy0 = float(sy_arr[0])

    phi0 = _phi_from_slopes_3d(alpha_e=alpha_e, sx=sx0, sy=sy0)
    if phi_clamp and phi0 <= phi_min:
        phi0 = phi_min
    cp0_raw = float(compute_cp(ma_inf=mach_edge, phi_rad=float(phi0),
                               cp_model=cp_model, newtonian_A=cp_newtonian_A, newtonian_n=cp_newtonian_n))

    phi_arr = np.full_like(x_over_c, np.nan, dtype=float)
    cp_arr = np.full_like(x_over_c, np.nan, dtype=float)
    for i in range(x_over_c.size):
        phi = _phi_from_slopes_3d(alpha_e=alpha_e, sx=float(sx_arr[i]), sy=float(sy_arr[i]))
        if phi_clamp and phi <= phi_min:
            phi = phi_min
        phi_arr[i] = float(phi)
        cp_arr[i] = float(compute_cp(ma_inf=mach_edge, phi_rad=float(phi),
                                     cp_model=cp_model, newtonian_A=cp_newtonian_A, newtonian_n=cp_newtonian_n))

    raw_edges, min_ma_raw, collapsed_raw = _build_edges_for_cp0(
        gas=gas,
        mach_edge=float(mach_edge),
        p_inf=float(p_inf),
        T_inf=float(T_inf),
        rho_inf=float(rho_inf),
        cp_arr=cp_arr,
        cp0_pressure=float(cp0_raw),
    )

    cp0_override_val = None
    cp0_override_applied = False
    if cp0_override is not None and np.isfinite(float(cp0_override)):
        cp0_override_val = float(cp0_override)

    if cp0_override_val is not None:
        override_edges, min_ma_override, collapsed_override = _build_edges_for_cp0(
            gas=gas,
            mach_edge=float(mach_edge),
            p_inf=float(p_inf),
            T_inf=float(T_inf),
            rho_inf=float(rho_inf),
            cp_arr=cp_arr,
            cp0_pressure=float(cp0_override_val),
        )
        if np.isfinite(min_ma_override) and min_ma_override >= _EDGE_MAE_FLOOR:
            edges = override_edges
            cp0_used = float(cp0_override_val)
            cp0_override_applied = bool(abs(float(cp0_used) - float(cp0_raw)) > _CP0_BISECT_TOL)
            cp0_regularized = False
            min_ma_used = float(min_ma_override)
            collapsed_used = int(collapsed_override)
        else:
            (
                edges,
                cp0_used,
                cp0_regularized,
                _min_ma_raw_unused,
                min_ma_used,
                _collapsed_raw_unused,
                collapsed_used,
            ) = _regularize_cp0_for_supersonic_edge(
                gas=gas,
                mach_edge=float(mach_edge),
                p_inf=float(p_inf),
                T_inf=float(T_inf),
                rho_inf=float(rho_inf),
                cp_arr=cp_arr,
                cp0_raw=float(cp0_raw),
            )
    else:
        (
            edges,
            cp0_used,
            cp0_regularized,
            _min_ma_raw_unused,
            min_ma_used,
            _collapsed_raw_unused,
            collapsed_used,
        ) = _regularize_cp0_for_supersonic_edge(
            gas=gas,
            mach_edge=float(mach_edge),
            p_inf=float(p_inf),
            T_inf=float(T_inf),
            rho_inf=float(rho_inf),
            cp_arr=cp_arr,
            cp0_raw=float(cp0_raw),
        )

    taw_tpg: np.ndarray | None = None
    h0_tpg: float | None = None
    tpg_ve2_neg_count: int = 0

    if getattr(gas, "tpg", None) is not None:
        from ..aero.edge_conditions import get_tpg_ve2_neg_count, reset_tpg_ve2_neg_count

        reset_tpg_ve2_neg_count()
        tpg = gas.tpg
        a_inf = float(tpg.a_T(float(T_inf)))
        v_inf = float(mach_edge) * a_inf
        h_inf_tpg = float(tpg.h_from_T(float(T_inf)))
        h0_val = h_inf_tpg + 0.5 * v_inf * v_inf
        h0_tpg = h0_val

        nx_val = int(len(edges))
        taw_arr = np.full(nx_val, np.nan, dtype=float)
        Pr = float(gas.prandtl)
        # Recovery: fully turbulent, fixed Pr^(1/3).
        # Taw is decoupled from q-chain transition weighting (w_tr).
        r_aw = Pr ** (1.0 / 3.0)

        for i in range(nx_val):
            e = edges[i]
            T_e_i = float(e.T_e)
            V_e_i = float(e.v_e)
            if not (np.isfinite(T_e_i) and np.isfinite(V_e_i)):
                continue

            h_e_val = float(tpg.h_from_T(T_e_i))
            h_aw_val = h_e_val + r_aw * 0.5 * V_e_i * V_e_i
            taw_arr[i] = float(tpg.T_from_h(h_aw_val))

        taw_tpg = taw_arr
        tpg_ve2_neg_count = int(get_tpg_ve2_neg_count())

    return WindwardEdgeCacheFaceted3D(
        edges=edges,
        x_over_c=x_over_c,
        x_phys=x_phys,
        lf_cfg=lf_cfg,
        transition_x_over_c=transition_x_over_c,
        alpha_edge_rad=float(inflow.alpha_edge_rad),
        alpha_effective_rad=float(inflow.alpha_effective_rad),
        mach_edge=float(inflow.mach_edge),
        mach_effective=float(inflow.mach_effective),
        use_effective_alpha=bool(inflow.use_effective_alpha),
        use_effective_mach=bool(inflow.use_effective_mach),
        phi_arr=np.asarray(phi_arr, dtype=float),
        cp_arr=np.asarray(cp_arr, dtype=float),
        cp0_raw=float(cp0_raw),
        cp0_used=float(cp0_used),
        cp0_override_applied=bool(cp0_override_applied),
        cp0_regularized=bool(cp0_regularized),
        min_ma_e_raw=float(min_ma_raw),
        min_ma_e_used=float(min_ma_used),
        collapsed_edge_count_raw=int(collapsed_raw),
        collapsed_edge_count_used=int(collapsed_used),
        taw_tpg=taw_tpg,
        h0_tpg=h0_tpg,
        tpg_ve2_neg_count=tpg_ve2_neg_count,
    )


def windward_q_distribution_from_Tw(
    *,
    gas: GasModel,
    cache: WindwardEdgeCacheFaceted3D,
    Tw: np.ndarray,
    include_leading_edge: bool = False,
) -> np.ndarray:
    """Same semantics as aero/windward_cache.py (faceted 3D cache variant).

    Phase 3-B: Dhawan-Narasimha physical-q wiring.

    When weighting == "dhawan_narasimha", this function finds the onset index
    along the current strip, computes a Simon ZPG lambda_m closure (hardcoded
    constants, no YAML/config keys), then passes x_tr_phys and lambda_m into
    transition_weight for each point.

    Fallback: if onset not found, lambda_m is non-positive/non-finite, or edge
    quantities are invalid, the strip reverts to fully laminar (w=0).
    """

    _DN_WEIGHTING = "dhawan_narasimha"

    Tw = np.asarray(Tw, dtype=float).reshape(-1)
    if Tw.size != cache.x_over_c.size:
        raise ValueError("Tw must have same length as cache.x_over_c")

    q = np.full_like(Tw, np.nan, dtype=float)
    i0 = 0 if bool(include_leading_edge) else 1
    weighting = str(cache.lf_cfg.transition.weighting).strip().lower()
    is_dn = weighting == _DN_WEIGHTING

    if is_dn:
        onset_idx = None
        for j in range(i0, Tw.size):
            if not np.isfinite(float(Tw[j])):
                continue
            branches_j = windward_ref_enthalpy_branches(
                gas=gas, edge=cache.edges[j], x=float(cache.x_phys[j]), h_w=float(gas.h_from_T(float(Tw[j])))
            )
            re_x_lam_j = float(branches_j.Re_x_star_lam)
            if not np.isfinite(re_x_lam_j) or re_x_lam_j <= 0.0:
                continue
            re_tri_j = float(transition_reynolds(ma_e=float(cache.edges[j].ma_e)))
            if re_x_lam_j >= re_tri_j:
                onset_idx = j
                break

        dn_x_tr_phys: float | None = None
        dn_lambda_m: float | None = None
        if onset_idx is not None:
            o_edge = cache.edges[onset_idx]
            rho_e = float(o_edge.rho_e)
            v_e = float(o_edge.v_e)
            mu_e = float(o_edge.mu_e)
            x_tr = float(cache.x_phys[onset_idx])
            if (
                np.isfinite(rho_e) and rho_e > 0.0
                and np.isfinite(v_e) and v_e > 0.0
                and np.isfinite(mu_e) and mu_e > 0.0
                and np.isfinite(x_tr) and x_tr > 0.0
            ):
                Re_x_tr = rho_e * v_e * x_tr / mu_e
                if Re_x_tr > 0.0:
                    Re_theta_tr = _DN_CONST_0p664 * np.sqrt(Re_x_tr)
                    Re_L_tr = _DN_CONST_124 * (Re_theta_tr ** 1.5)
                    L_tr = Re_L_tr * mu_e / (rho_e * v_e)
                    lm = float(L_tr / _DN_XI_99)
                    if np.isfinite(lm) and lm > 0.0:
                        dn_x_tr_phys = x_tr
                        dn_lambda_m = lm

    for i in range(i0, Tw.size):
        Tw_i = float(Tw[i])
        if not np.isfinite(Tw_i):
            continue
        h_w = float(gas.h_from_T(Tw_i))
        q_lam, q_turb, re_lam, _re_turb = windward_ref_enthalpy_branches(
            gas=gas, edge=cache.edges[i], x=float(cache.x_phys[i]), h_w=h_w
        )
        re_tri = float(transition_reynolds(ma_e=float(cache.edges[i].ma_e)))

        if is_dn and dn_lambda_m is not None:
            w = float(
                transition_weight(
                    enable=True,
                    re_measure=1.0,
                    re_tri=1.0,
                    weighting=_DN_WEIGHTING,
                    x_phys=float(cache.x_phys[i]),
                    x_tr_phys=float(dn_x_tr_phys),
                    lambda_m=float(dn_lambda_m),
                )
            )
        else:
            w = float(
                transition_weight(
                    enable=bool(cache.lf_cfg.transition.enable),
                    re_measure=float(re_lam),
                    re_tri=re_tri,
                    weighting=weighting,
                    width_decades=float(cache.lf_cfg.transition.width_decades),
                    delta_decades=float(cache.lf_cfg.transition.delta_decades),
                    x_over_c=float(cache.x_over_c[i]),
                    transition_x_over_c=cache.transition_x_over_c,
                    x_phys=float(cache.x_phys[i]),
                )
            )
        q[i] = (1.0 - w) * float(q_lam) + w * float(q_turb)
    return q


def windward_q_at_index(
    *,
    gas: GasModel,
    cache: WindwardEdgeCacheFaceted3D,
    i: int,
    Tw_i: float,
) -> float:
    """Same semantics as aero/windward_cache.py (faceted 3D cache variant)."""

    i = int(i)
    if i < 0:
        raise ValueError("windward_q_at_index expects i>=0.")
    if i >= cache.x_over_c.size:
        raise IndexError("i out of range for cache")
    Tw_i = float(Tw_i)
    if not np.isfinite(Tw_i):
        return float("nan")
    h_w = float(gas.h_from_T(Tw_i))
    q_lam, q_turb, re_lam, _re_turb = windward_ref_enthalpy_branches(
        gas=gas, edge=cache.edges[i], x=float(cache.x_phys[i]), h_w=h_w
    )
    re_tri = float(transition_reynolds(ma_e=float(cache.edges[i].ma_e)))
    w = float(
        transition_weight(
            enable=bool(cache.lf_cfg.transition.enable),
            re_measure=float(re_lam),
            re_tri=re_tri,
            weighting=str(cache.lf_cfg.transition.weighting),
            width_decades=float(cache.lf_cfg.transition.width_decades),
            delta_decades=float(cache.lf_cfg.transition.delta_decades),
            x_over_c=float(cache.x_over_c[i]),
            transition_x_over_c=cache.transition_x_over_c,
            x_phys=float(cache.x_phys[i]),
        )
    )
    return float((1.0 - w) * float(q_lam) + w * float(q_turb))