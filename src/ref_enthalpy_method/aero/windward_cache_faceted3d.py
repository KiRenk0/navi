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

from ..aero.edge_conditions import (
    compute_edge_conditions,
    effective_alpha,
    effective_ma_inf,
)
from ..aero.pressure_coefficient import newtonian_like_cp
from ..config.windward_taw import WindwardTawConfig
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
    taw_cfg: WindwardTawConfig
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
    taw_cfg: WindwardTawConfig,
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
    cp0_override: float | None = None,
    use_effective_alpha: bool = True,
    use_effective_mach: bool = False,
    x_phys_override: np.ndarray | None = None,
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
    x_min_over_c = float(taw_cfg.x_min_over_c)
    x_eff_over_c = np.maximum(x_over_c, max(x_min_over_c, 0.0))
    if x_phys_override is None:
        x_phys = np.maximum(x_eff_over_c * float(chord_m), 1e-6)
    else:
        x_phys = np.asarray(x_phys_override, dtype=float).reshape(-1)
        if x_phys.size != x_over_c.size:
            raise ValueError("x_phys_override must have the same length as xc_grid")
        x_phys = np.maximum(x_phys, 1e-6)

    # phi clamp
    phi_clamp = bool(taw_cfg.phi_clamp.enable)
    phi_min = float(taw_cfg.phi_clamp.phi_min_rad)

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
    except (IndexError, TypeError, ValueError, OverflowError):
        sx0 = float(sx_arr[0])
        sy0 = float(sy_arr[0])

    phi0 = _phi_from_slopes_3d(alpha_e=alpha_e, sx=sx0, sy=sy0)
    if phi_clamp and phi0 <= phi_min:
        phi0 = phi_min
    cp0_raw = newtonian_like_cp(
        phi_rad=float(phi0), A=cp_newtonian_A, n=cp_newtonian_n
    )

    phi_arr = np.full_like(x_over_c, np.nan, dtype=float)
    cp_arr = np.full_like(x_over_c, np.nan, dtype=float)
    for i in range(x_over_c.size):
        phi = _phi_from_slopes_3d(alpha_e=alpha_e, sx=float(sx_arr[i]), sy=float(sy_arr[i]))
        if phi_clamp and phi <= phi_min:
            phi = phi_min
        phi_arr[i] = float(phi)
        cp_arr[i] = newtonian_like_cp(
            phi_rad=float(phi), A=cp_newtonian_A, n=cp_newtonian_n
        )

    _raw_edges, min_ma_raw, collapsed_raw = _build_edges_for_cp0(
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
        from ..aero.edge_conditions import (
            get_tpg_ve2_neg_count,
            reset_tpg_ve2_neg_count,
        )

        reset_tpg_ve2_neg_count()
        tpg = gas.tpg
        a_inf = float(tpg.a_T(float(T_inf)))
        v_inf = float(mach_edge) * a_inf
        h_inf_tpg = float(tpg.h_from_T(float(T_inf)))
        h0_val = h_inf_tpg + 0.5 * v_inf * v_inf
        h0_tpg = h0_val

        nx_val = len(edges)
        taw_arr = np.full(nx_val, np.nan, dtype=float)
        for i in range(nx_val):
            e = edges[i]
            T_e_i = float(e.T_e)
            V_e_i = float(e.v_e)
            if not (np.isfinite(T_e_i) and np.isfinite(V_e_i)):
                continue

            r_aw = float(gas.prandtl_at_T(T_e_i)) ** (1.0 / 3.0)
            h_e_val = float(tpg.h_from_T(T_e_i))
            h_aw_val = h_e_val + r_aw * 0.5 * V_e_i * V_e_i
            taw_arr[i] = float(tpg.T_from_h(h_aw_val))

        taw_tpg = taw_arr
        tpg_ve2_neg_count = int(get_tpg_ve2_neg_count())

    return WindwardEdgeCacheFaceted3D(
        edges=edges,
        x_over_c=x_over_c,
        x_phys=x_phys,
        taw_cfg=taw_cfg,
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
