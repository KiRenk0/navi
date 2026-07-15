#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run one case using the rewritten ref_enthalpy_method solver.

This script mirrors the baseline workflow:
- load vehicle/case/sampling specs
- run one (mach, alpha)
- write runs/<run_dir>/summary.json and fields.npz
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


def _ensure_import_path() -> Path:
    """Ensure `import ref_enthalpy_method` works for src-layout.

    Supports running from:
    - repo root:   python scripts/run_case_rem.py
    - scripts dir: python run_case_rem.py
    """

    here = Path(__file__).resolve()
    repo_root = here.parents[1]  # .../<repo>/scripts/run_case_rem.py
    src_root = repo_root / "src"
    # Add both repo_root and src_root for flexibility
    for p in (str(repo_root), str(src_root)):
        if p not in sys.path:
            sys.path.insert(0, p)
    return repo_root


def _np_to_builtin(x: Any) -> Any:
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.ndarray,)):
        return x.tolist()
    return x


def _override_transition_case(
    case,
    *,
    transition_mode: str,
    transition_weighting: str | None,
    transition_x_over_c: float | None,
    no_transition_x_cutoff: bool,
):
    """Apply command-line transition overrides to a loaded CaseSpec."""

    mode = str(transition_mode).strip().lower()
    if mode not in {"case", "on", "off"}:
        mode = "case"

    lf = dict(getattr(case, "lf_qw_model", {}) or {})
    tr = dict(lf.get("transition", {}) or {})
    lf_changed = False

    if mode != "case":
        tr["enable"] = bool(mode == "on")
        lf_changed = True
    if transition_weighting is not None:
        tr["weighting"] = str(transition_weighting).strip().lower()
        lf_changed = True

    case_new = case
    if lf_changed:
        lf["transition"] = tr
        case_new = replace(case_new, lf_qw_model=lf)

    if bool(no_transition_x_cutoff):
        case_new = replace(case_new, transition_x_over_c=None)
    elif transition_x_over_c is not None:
        case_new = replace(case_new, transition_x_over_c=float(transition_x_over_c))

    return case_new


def _override_faceted3d_config(
    solver,
    *,
    effective_alpha_mode: str,
    effective_mach_mode: str,
    x_length_mode: str,
) -> None:
    """Apply runtime faceted3d overrides to an instantiated solver."""

    if not hasattr(solver, "f3_cfg"):
        return

    def _norm_on_off_case(text: str) -> str:
        mode = str(text or "").strip().lower()
        return mode if mode in {"case", "on", "off"} else "case"

    alpha_mode = _norm_on_off_case(effective_alpha_mode)
    mach_mode = _norm_on_off_case(effective_mach_mode)
    x_mode = str(x_length_mode or "").strip().lower()
    if x_mode not in {"case", "local", "global", "streamline"}:
        x_mode = "case"

    updates: dict[str, Any] = {}
    if alpha_mode != "case":
        updates["edge_use_effective_alpha"] = bool(alpha_mode == "on")
    if mach_mode != "case":
        updates["edge_use_effective_mach"] = bool(mach_mode == "on")
    if x_mode != "case":
        updates["x_length_mode"] = str(x_mode)

    if not updates:
        return

    old_cfg = getattr(solver, "f3_cfg")
    new_cfg = replace(old_cfg, **updates)
    setattr(solver, "f3_cfg", new_cfg)

    changed = (
        bool(new_cfg.edge_use_effective_alpha) != bool(old_cfg.edge_use_effective_alpha)
        or bool(new_cfg.edge_use_effective_mach) != bool(old_cfg.edge_use_effective_mach)
        or str(new_cfg.x_length_mode).strip().lower() != str(old_cfg.x_length_mode).strip().lower()
    )
    if changed and hasattr(solver, "warning_log"):
        solver.warning_log.warn(
            "faceted3d runtime override active"
            f" | use_effective_alpha={bool(new_cfg.edge_use_effective_alpha)}"
            f" | use_effective_mach={bool(new_cfg.edge_use_effective_mach)}"
            f" | x_length_mode={str(new_cfg.x_length_mode).strip().lower()}"
        )


def _summarize_array(name: str, arr: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(arr, dtype=float).reshape(-1)
    finite = np.isfinite(arr)
    out: dict[str, Any] = {
        "name": name,
        "shape": list(arr.shape),
        "finite_count": int(np.sum(finite)),
        "nan_count": int(np.sum(np.isnan(arr))),
        "inf_count": int(np.sum(~finite) - np.sum(np.isnan(arr))),
    }
    if np.any(finite):
        a = arr[finite]
        out.update({"min": float(np.min(a)), "max": float(np.max(a)), "mean": float(np.mean(a))})
    return out


def _profile_samples(xc: np.ndarray, arr: np.ndarray, n_points: int = 6) -> list[dict[str, Any]]:
    xc = np.asarray(xc, dtype=float).reshape(-1)
    arr = np.asarray(arr, dtype=float).reshape(-1)
    if xc.size != arr.size or xc.size == 0:
        return []
    idx = np.unique(np.round(np.linspace(0, xc.size - 1, max(int(n_points), 2))).astype(int))
    out: list[dict[str, Any]] = []
    for i in idx.tolist():
        out.append({"i": int(i), "x_over_c": float(xc[i]), "value": _np_to_builtin(arr[i])})
    return out


def _edge_arrays(edges: list) -> dict[str, Any]:
    p_e = np.array([float(e.p_e) for e in edges], dtype=float)
    rho_e = np.array([float(e.rho_e) for e in edges], dtype=float)
    T_e = np.array([float(e.T_e) for e in edges], dtype=float)
    ma_e = np.array([float(e.ma_e) for e in edges], dtype=float)
    a_e = np.array([float(e.a_e) for e in edges], dtype=float)
    v_e = np.array([float(e.v_e) for e in edges], dtype=float)
    mu_e = np.array([float(e.mu_e) for e in edges], dtype=float)
    return {
        "p_e_Pa": _np_to_builtin(p_e),
        "rho_e_kg_m3": _np_to_builtin(rho_e),
        "T_e_K": _np_to_builtin(T_e),
        "ma_e": _np_to_builtin(ma_e),
        "a_e_m_s": _np_to_builtin(a_e),
        "v_e_m_s": _np_to_builtin(v_e),
        "mu_e_Pa_s": _np_to_builtin(mu_e),
    }


def _windward_intermediate_2d(
    *,
    solver,
    mach: float,
    alpha_deg: float,
    chord_m: float,
    slope_arr: np.ndarray,
) -> dict[str, Any]:
    from ref_enthalpy_method.aero.busemann import busemann_cp
    from ref_enthalpy_method.aero.edge_conditions import compute_edge_conditions, effective_alpha, effective_ma_inf

    chi_rad = float(np.deg2rad(float(solver.vehicle.sweep_le_deg)))
    alpha_rad = float(np.deg2rad(float(alpha_deg)))
    alpha_e = float(effective_alpha(alpha_rad, chi_rad))
    mach_eff = float(effective_ma_inf(float(mach), alpha_rad=alpha_rad, chi_w_rad=chi_rad))

    x_over_c = np.asarray(solver.xc_grid, dtype=float).reshape(-1)
    x_min_over_c = float(getattr(solver.lf_cfg, "x_model").x_min_over_c) if hasattr(solver.lf_cfg, "x_model") else 0.003
    x_eff_over_c = np.maximum(x_over_c, max(x_min_over_c, 0.0))
    x_phys = np.maximum(x_eff_over_c * float(chord_m), 1e-6)

    phi_clamp = bool(solver.lf_cfg.phi_clamp.enable)
    phi_min = float(solver.lf_cfg.phi_clamp.phi_min_rad)

    slope_arr = np.asarray(slope_arr, dtype=float).reshape(-1)
    slope0 = float(slope_arr[0]) if slope_arr.size > 0 else 0.0
    try:
        if x_over_c.size >= 2 and float(x_over_c[0]) > 0.0:
            x0 = float(x_over_c[0])
            x1 = float(x_over_c[1])
            s0 = float(slope_arr[0])
            s1 = float(slope_arr[1])
            if x1 != x0:
                slope0 = s0 + (0.0 - x0) * (s1 - s0) / (x1 - x0)
    except Exception:
        slope0 = float(slope_arr[0]) if slope_arr.size > 0 else 0.0

    phi0_raw = float(alpha_e) - float(np.arctan(float(slope0)))
    phi0_used = float(phi0_raw)
    if phi_clamp and phi0_used <= phi_min:
        phi0_used = float(phi_min)
    cp0 = float(busemann_cp(ma_inf=mach_eff, phi_rad=float(phi0_used)))

    phi_raw = alpha_e - np.arctan(slope_arr)
    if phi_clamp:
        phi_used = np.where(phi_raw <= phi_min, float(phi_min), phi_raw)
    else:
        phi_used = phi_raw
    cp = np.array([float(busemann_cp(ma_inf=mach_eff, phi_rad=float(v))) for v in phi_used], dtype=float)

    p_inf, rho_inf, T_inf, _v_inf = solver._freestream(float(mach))
    edges = []
    for i in range(x_over_c.size):
        edge = compute_edge_conditions(
            gas=solver.gas,
            ma_inf=float(mach_eff),
            p_inf=float(p_inf),
            T_inf=float(T_inf),
            rho_inf=float(rho_inf),
            cp_pressure=float(cp[i]),
            cp0_pressure=float(cp0),
        )
        edges.append(edge)

    return {
        "alpha_e_rad": float(alpha_e),
        "mach_eff": float(mach_eff),
        "x_over_c": _np_to_builtin(x_over_c),
        "x_eff_over_c": _np_to_builtin(x_eff_over_c),
        "x_phys_m": _np_to_builtin(x_phys),
        "slope": _np_to_builtin(slope_arr),
        "phi_raw_rad": _np_to_builtin(phi_raw),
        "phi_used_rad": _np_to_builtin(phi_used),
        "phi0_raw_rad": float(phi0_raw),
        "phi0_used_rad": float(phi0_used),
        "cp": _np_to_builtin(cp),
        "cp0": float(cp0),
        "edge": _edge_arrays(edges),
    }


def _windward_intermediate_faceted3d(
    *,
    solver,
    strip_idx: int | None,
    mach: float,
    alpha_deg: float,
    chord_m: float,
    sx_arr: np.ndarray,
    sy_arr: np.ndarray,
) -> dict[str, Any]:
    from ref_enthalpy_method.aero.busemann import busemann_cp
    from ref_enthalpy_method.aero.windward_cache_faceted3d import _phi_from_slopes_3d, resolve_faceted3d_edge_inflow

    inflow = resolve_faceted3d_edge_inflow(
        mach=float(mach),
        alpha_deg=float(alpha_deg),
        sweep_le_deg=float(solver.vehicle.sweep_le_deg),
        use_effective_alpha=bool(getattr(solver.f3_cfg, "edge_use_effective_alpha", True)),
        use_effective_mach=bool(getattr(solver.f3_cfg, "edge_use_effective_mach", False)),
    )

    x_over_c = np.asarray(solver.xc_grid, dtype=float).reshape(-1)
    x_min_over_c = float(getattr(solver.lf_cfg, "x_model").x_min_over_c) if hasattr(solver.lf_cfg, "x_model") else 0.003
    x_eff_over_c = np.maximum(x_over_c, max(x_min_over_c, 0.0))
    x_phys = np.maximum(x_eff_over_c * float(chord_m), 1e-6)

    sx_arr = np.asarray(sx_arr, dtype=float).reshape(-1)
    sy_arr = np.asarray(sy_arr, dtype=float).reshape(-1)
    phi_clamp = bool(solver.lf_cfg.phi_clamp.enable)
    phi_min = float(solver.lf_cfg.phi_clamp.phi_min_rad)

    sx0 = float(sx_arr[0]) if sx_arr.size > 0 else 0.0
    sy0 = float(sy_arr[0]) if sy_arr.size > 0 else 0.0
    try:
        if x_over_c.size >= 2 and float(x_over_c[0]) > 0.0:
            x0 = float(x_over_c[0])
            x1 = float(x_over_c[1])
            if x1 != x0:
                sx0 = float(sx_arr[0] + (0.0 - x0) * (float(sx_arr[1]) - float(sx_arr[0])) / (x1 - x0))
                sy0 = float(sy_arr[0] + (0.0 - x0) * (float(sy_arr[1]) - float(sy_arr[0])) / (x1 - x0))
    except Exception:
        sx0 = float(sx_arr[0]) if sx_arr.size > 0 else 0.0
        sy0 = float(sy_arr[0]) if sy_arr.size > 0 else 0.0

    phi0_raw = float(_phi_from_slopes_3d(alpha_e=float(inflow.alpha_edge_rad), sx=sx0, sy=sy0))
    phi0_used = float(phi0_raw)
    if phi_clamp and phi0_used <= phi_min:
        phi0_used = float(phi_min)
    cp0_raw = float(busemann_cp(ma_inf=float(inflow.mach_edge), phi_rad=float(phi0_used)))

    phi_raw = np.array(
        [float(_phi_from_slopes_3d(alpha_e=float(inflow.alpha_edge_rad), sx=float(sx_arr[i]), sy=float(sy_arr[i]))) for i in range(x_over_c.size)],
        dtype=float,
    )
    if phi_clamp:
        phi_used = np.where(phi_raw <= phi_min, float(phi_min), phi_raw)
    else:
        phi_used = phi_raw
    cp = np.array([float(busemann_cp(ma_inf=float(inflow.mach_edge), phi_rad=float(v))) for v in phi_used], dtype=float)

    cp0_override = None
    x_phys_override = None
    if strip_idx is not None:
        try:
            overrides = getattr(solver, "_cp0_override_by_strip", [])
            if int(strip_idx) < len(overrides):
                cp0_override = overrides[int(strip_idx)]
        except Exception:
            cp0_override = None
        try:
            x_list = getattr(solver, "_x_phys_override_by_strip", [])
            if int(strip_idx) < len(x_list):
                candidate = x_list[int(strip_idx)]
                if candidate is not None:
                    x_phys_override = np.asarray(candidate, dtype=float)
        except Exception:
            x_phys_override = None
    p_inf, rho_inf, T_inf, _v_inf = solver._freestream(float(mach))
    cache = solver._build_windward_edge_cache(
        mach=float(mach),
        alpha_deg=float(alpha_deg),
        p_inf=float(p_inf),
        rho_inf=float(rho_inf),
        T_inf=float(T_inf),
        chord_m=float(chord_m),
        sx_arr=sx_arr,
        sy_arr=sy_arr,
        transition_x_over_c=solver.case.transition_x_over_c,
        cp0_override=cp0_override,
        x_phys_override=x_phys_override,
    )
    x_phys = np.asarray(cache.x_phys, dtype=float).reshape(-1)
    phi0_report = (None if (bool(cache.cp0_regularized) or bool(getattr(cache, "cp0_override_applied", False))) else float(phi0_used))

    return {
        "alpha_e_rad": float(inflow.alpha_edge_rad),
        "alpha_input_rad": float(inflow.alpha_input_rad),
        "alpha_eff_rad": float(inflow.alpha_effective_rad),
        "alpha_edge_rad": float(inflow.alpha_edge_rad),
        "mach_input": float(inflow.mach_input),
        "mach_eff": float(inflow.mach_effective),
        "mach_edge": float(inflow.mach_edge),
        "use_effective_alpha": bool(inflow.use_effective_alpha),
        "use_effective_mach": bool(inflow.use_effective_mach),
        "x_length_mode": str(getattr(solver.f3_cfg, "x_length_mode", "streamline")),
        "x_over_c": _np_to_builtin(x_over_c),
        "x_eff_over_c": _np_to_builtin(x_eff_over_c),
        "x_phys_m": _np_to_builtin(x_phys),
        "sx": _np_to_builtin(sx_arr),
        "sy": _np_to_builtin(sy_arr),
        "phi_raw_rad": _np_to_builtin(phi_raw),
        "phi_used_rad": _np_to_builtin(phi_used),
        "phi0_raw_rad": float(phi0_raw),
        "phi0_used_rad": phi0_report,
        "cp": _np_to_builtin(cp),
        "cp0": float(cache.cp0_used),
        "cp0_raw": float(cp0_raw),
        "cp0_used": float(cache.cp0_used),
        "cp0_override_applied": bool(getattr(cache, "cp0_override_applied", False)),
        "cp0_regularized": bool(cache.cp0_regularized),
        "min_ma_e_raw": float(cache.min_ma_e_raw),
        "min_ma_e_used": float(cache.min_ma_e_used),
        "collapsed_edge_count_raw": int(cache.collapsed_edge_count_raw),
        "collapsed_edge_count_used": int(cache.collapsed_edge_count_used),
        "edge": _edge_arrays(cache.edges),
    }


def _build_intermediate(*, solver, fields: dict[str, np.ndarray], mach: float, alpha: float) -> dict[str, Any]:
    from ref_enthalpy_method.heatflux.leeward import leeward_re_ns, leeward_stanton_distribution, normal_shock_temperature_ratio

    xc = np.asarray(getattr(solver, "xc_grid"), dtype=float).reshape(-1)
    yb = np.asarray(getattr(solver, "yb_grid"), dtype=float).reshape(-1)
    nx = int(xc.size)
    ny = int(yb.size)

    p_inf, rho_inf, T_inf, v_inf = solver._freestream(float(mach))
    h_inf = float(solver.gas.h_from_T(T_inf))
    h0 = float(h_inf + 0.5 * (float(v_inf) ** 2))
    mu_inf = float(solver.gas.mu(T_inf))

    Tw_w = fields.get("Tw_w")
    Tw_l = fields.get("Tw_l")
    Tw_w_2d = None
    Tw_l_2d = None
    if Tw_w is not None:
        Tw_w_2d = np.asarray(Tw_w, dtype=float).reshape(ny, nx)
    if Tw_l is not None:
        Tw_l_2d = np.asarray(Tw_l, dtype=float).reshape(ny, nx)

    windward_strips: list[dict[str, Any]] = []
    leeward_strips: list[dict[str, Any]] = []
    use_faceted3d = hasattr(solver, "_strip_xle_chord_mask")

    for j in range(ny):
        ybj = float(yb[j])
        if use_faceted3d:
            x_le, chord, mask_x = solver._strip_xle_chord_mask(y_over_b=ybj)
            mask_x = np.asarray(mask_x, dtype=bool).reshape(-1)
            chord_eff = float(max(float(chord), float(solver.f3_cfg.chord_min_m)))
            if solver.slope_sampler is not None:
                span_m = float(ybj) * float(solver.planform_b_half_m)
                x_pts = float(x_le) + np.asarray(xc, dtype=float) * float(chord)
                sx_up_arr = np.full((nx,), np.nan, dtype=float)
                sy_up_arr = np.full((nx,), np.nan, dtype=float)
                sx_lo_arr = np.full((nx,), np.nan, dtype=float)
                sy_lo_arr = np.full((nx,), np.nan, dtype=float)
                for i in range(nx):
                    if not bool(mask_x[i]):
                        continue
                    up_s, lo_s = solver.slope_sampler.sample_upper_lower(x=float(x_pts[i]), span=float(span_m))
                    if up_s is not None:
                        sx_up_arr[i], sy_up_arr[i] = float(up_s[0]), float(up_s[1])
                    if lo_s is not None:
                        sx_lo_arr[i], sy_lo_arr[i] = float(lo_s[0]), float(lo_s[1])
                sx_up_arr = np.where(np.isfinite(sx_up_arr), sx_up_arr, float(solver.sx_up))
                sy_up_arr = np.where(np.isfinite(sy_up_arr), sy_up_arr, float(solver.sy_up))
                sx_lo_arr = np.where(np.isfinite(sx_lo_arr), sx_lo_arr, float(solver.sx_lo))
                sy_lo_arr = np.where(np.isfinite(sy_lo_arr), sy_lo_arr, float(solver.sy_lo))
            else:
                sx_up_arr = np.full((nx,), float(solver.sx_up), dtype=float)
                sy_up_arr = np.full((nx,), float(solver.sy_up), dtype=float)
                sx_lo_arr = np.full((nx,), float(solver.sx_lo), dtype=float)
                sy_lo_arr = np.full((nx,), float(solver.sy_lo), dtype=float)

            if float(alpha) >= 0.0:
                sx_w_arr, sy_w_arr = sx_lo_arr, sy_lo_arr
                sx_l_arr, sy_l_arr = sx_up_arr, sy_up_arr
            else:
                sx_w_arr, sy_w_arr = sx_up_arr, sy_up_arr
                sx_l_arr, sy_l_arr = sx_lo_arr, sy_lo_arr

            windward = _windward_intermediate_faceted3d(
                solver=solver,
                strip_idx=int(j),
                mach=float(mach),
                alpha_deg=float(alpha),
                chord_m=float(chord_eff),
                sx_arr=sx_w_arr,
                sy_arr=sy_w_arr,
            )
            windward_strips.append(
                {
                    "j": int(j),
                    "y_over_b": float(ybj),
                    "x_le_m": float(x_le),
                    "chord_m": float(chord),
                    "chord_eff_m": float(chord_eff),
                    "mask_x": _np_to_builtin(mask_x),
                    "windward_slopes": {"sx": _np_to_builtin(sx_w_arr), "sy": _np_to_builtin(sy_w_arr)},
                    "leeward_slopes": {"sx": _np_to_builtin(sx_l_arr), "sy": _np_to_builtin(sy_l_arr)},
                    "edge_conditions": windward,
                }
            )
            chord_for_leeward = float(chord_eff)
            h_wwd = None
            if Tw_w_2d is not None:
                h_wwd = np.array([float(solver.gas.h_from_T(float(v))) if np.isfinite(v) else float("nan") for v in Tw_w_2d[j, :]], dtype=float)
            elif Tw_l_2d is not None:
                h_wwd = np.array([float(solver.gas.h_from_T(float(v))) if np.isfinite(v) else float("nan") for v in Tw_l_2d[j, :]], dtype=float)
        else:
            chord = float(solver._chord_at_y(ybj))
            slope_w = solver._windward_slope(float(alpha))
            slope_l = solver._leeward_slope(float(alpha))
            windward = _windward_intermediate_2d(
                solver=solver,
                mach=float(mach),
                alpha_deg=float(alpha),
                chord_m=float(chord),
                slope_arr=np.asarray(slope_w, dtype=float),
            )
            windward_strips.append(
                {
                    "j": int(j),
                    "y_over_b": float(ybj),
                    "chord_m": float(chord),
                    "windward_slope": _np_to_builtin(slope_w),
                    "leeward_slope": _np_to_builtin(slope_l),
                    "edge_conditions": windward,
                }
            )
            chord_for_leeward = float(chord)
            h_wwd = None
            if Tw_w_2d is not None:
                h_wwd = np.array([float(solver.gas.h_from_T(float(v))) if np.isfinite(v) else float("nan") for v in Tw_w_2d[j, :]], dtype=float)
            elif Tw_l_2d is not None:
                h_wwd = np.array([float(solver.gas.h_from_T(float(v))) if np.isfinite(v) else float("nan") for v in Tw_l_2d[j, :]], dtype=float)

        h_s = float(h0)
        ratio_T = float(normal_shock_temperature_ratio(gamma=float(solver.case.gamma), mach=float(mach)))
        T_ns = float(T_inf) * float(ratio_T)
        mu_ns = float(solver.gas.mu(T_ns))
        R_ref = float(solver._leeward_R_ref(chord_m=float(chord_for_leeward)))
        Re_ns = float(leeward_re_ns(rho_inf=float(rho_inf), v_inf=float(v_inf), R_ref=float(R_ref), mu_ns=float(mu_ns)))

        if h_wwd is None:
            h_wwd = np.full((nx,), float("nan"), dtype=float)
        St_dist = leeward_stanton_distribution(Re_ns=float(Re_ns), h_wwd_dist=h_wwd, h_s=float(h_s))

        leeward_strips.append(
            {
                "j": int(j),
                "y_over_b": float(ybj),
                "chord_ref_m": float(chord_for_leeward),
                "R_ref_m": float(R_ref),
                "h_s_J_per_kg": float(h_s),
                "T_ns_K": float(T_ns),
                "mu_ns_Pa_s": float(mu_ns),
                "Re_ns": float(Re_ns),
                "h_wwd_J_per_kg": _np_to_builtin(h_wwd),
                "St": _np_to_builtin(St_dist),
            }
        )

    return {
        "geometry": {
            "nx": int(nx),
            "ny": int(ny),
            "xc_grid": _np_to_builtin(xc),
            "yb_grid": _np_to_builtin(yb),
        },
        "freestream": {
            "p_inf_Pa": float(p_inf),
            "rho_inf_kg_m3": float(rho_inf),
            "T_inf_K": float(T_inf),
            "V_inf_m_s": float(v_inf),
            "mu_inf_Pa_s": float(mu_inf),
            "h_inf_J_per_kg": float(h_inf),
            "h0_J_per_kg": float(h0),
        },
        "windward": {"strips": windward_strips},
        "leeward": {"strips": leeward_strips},
    }


def _monotonic_decrease_report(
    *,
    x_over_c: np.ndarray,
    y: np.ndarray,
    tol: float = 1.0,
    max_violations: int = 8,
) -> dict[str, Any]:
    """Check if y(x) is (approximately) monotonically decreasing.

    Returns a compact report of any increases (dy > tol).
    """

    x = np.asarray(x_over_c, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)
    if x.size != y.size or x.size < 2:
        return {"ok": False, "reason": "shape_mismatch_or_too_short"}

    dy = np.diff(y)
    inc_idx = np.where(dy > float(tol))[0]  # dy at i corresponds to segment i->i+1
    out: dict[str, Any] = {
        "ok": bool(inc_idx.size == 0),
        "tol": float(tol),
        "n": int(x.size),
        "n_increase_segments": int(inc_idx.size),
    }
    if inc_idx.size > 0:
        worst_i = int(inc_idx[np.argmax(dy[inc_idx])])
        out["worst_increase"] = {
            "i0": worst_i,
            "x0": float(x[worst_i]),
            "x1": float(x[worst_i + 1]),
            "y0": float(y[worst_i]),
            "y1": float(y[worst_i + 1]),
            "dy": float(dy[worst_i]),
        }
        segs: list[dict[str, Any]] = []
        for i in inc_idx[: max(int(max_violations), 1)].tolist():
            segs.append(
                {
                    "i0": int(i),
                    "x0": float(x[i]),
                    "x1": float(x[i + 1]),
                    "y0": float(y[i]),
                    "y1": float(y[i + 1]),
                    "dy": float(dy[i]),
                }
            )
        out["increase_segments_preview"] = segs
    return out


def _triangulate_structured(ny: int, nx: int) -> np.ndarray:
    """Triangulate a (ny,nx) structured grid for tricontourf."""
    triangles = np.empty((2 * (ny - 1) * (nx - 1), 3), dtype=np.int32)
    k = 0
    for j in range(ny - 1):
        row = j * nx
        row2 = (j + 1) * nx
        for i in range(nx - 1):
            p00 = row + i
            p01 = row + i + 1
            p10 = row2 + i
            p11 = row2 + i + 1
            triangles[k] = (p00, p01, p11)
            triangles[k + 1] = (p00, p11, p10)
            k += 2
    return triangles


def _try_save_plots(
    *,
    solver,
    out_dir: Path,
    fields: dict[str, np.ndarray],
    summary: dict[str, Any],
    plot_x_over_c_min: float = 0.0,
) -> list[str]:
    """Best-effort plotting. Returns created file paths (strings)."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.tri as mtri
    except Exception:
        # Keep runs working even if matplotlib isn't installed.
        print("note: matplotlib not available; skipping plot generation.")
        return []

    created: list[str] = []

    # Determine sampling mode from resolved sampling spec (more reliable than guessing).
    mode = str(getattr(solver.sampling, "mode", "")).strip()
    x_over_c_min = max(float(plot_x_over_c_min), 0.0)

    def _levels_from_minmax(vmin: float, vmax: float, n: int = 40) -> np.ndarray:
        """Robust contour levels even for constant fields."""
        if not (np.isfinite(vmin) and np.isfinite(vmax)):
            raise ValueError("non-finite min/max")
        if vmax <= vmin:
            eps = max(1e-6, 1e-6 * max(abs(vmin), abs(vmax), 1.0))
            vmin = vmin - eps
            vmax = vmax + eps
        return np.linspace(vmin, vmax, int(n))

    # 1D root chord line plots
    if mode == "root_windward_chord_line" and int(getattr(solver, "ny", 0)) == 1:
        xc = np.asarray(getattr(solver, "xc_grid"), dtype=float).reshape(-1)
        c_root = float(getattr(solver.vehicle, "c_root_m"))
        x_m = xc * c_root
        mask = xc >= x_over_c_min

        for side, key, ylabel, prefix in (
            ("windward", "Tw_w", "T / K", "Tw_root_chord"),
            ("leeward", "Tw_l", "T / K", "Tw_root_chord"),
            ("windward", "q_w", "q / W/m^2", "q_root_chord"),
            ("leeward", "q_l", "q / W/m^2", "q_root_chord"),
        ):
            if key not in fields:
                continue
            Tw = np.asarray(fields[key], dtype=float).reshape(-1)
            if Tw.size != x_m.size:
                continue
            fig, ax = plt.subplots(figsize=(7.6, 4.8), dpi=170)
            ax.plot(x_m[mask], Tw[mask], linewidth=1.6)
            ax.set_xlabel("x / m")
            ax.set_ylabel(str(ylabel))
            meta_mach = summary.get("inputs", {}).get("mach", None)
            meta_alpha = summary.get("inputs", {}).get("alpha_deg", None)
            h_m = summary.get("freestream", {}).get("h_m", summary.get("inputs", {}).get("h_m_override", None))
            h_km = (None if h_m is None else float(h_m) / 1000.0)
            h_text = ("h=?" if h_km is None else f"h={h_km:.2f} km")
            ax.set_title(f"{key} root chord ({side}) | {h_text}, M={meta_mach}, alpha={meta_alpha} deg")
            ax.grid(True, linestyle="--", linewidth=0.6, alpha=0.6)
            fig.tight_layout()
            p = out_dir / f"{prefix}_{side}.png"
            fig.savefig(p)
            plt.close(fig)
            created.append(str(p))

    # 2D half-wing surface temperature plots
    if mode == "full_wing_surface_grid" and int(getattr(solver, "ny", 0)) > 1:
        nx = int(getattr(solver, "nx"))
        ny = int(getattr(solver, "ny"))
        xc = np.asarray(getattr(solver, "xc_grid"), dtype=float).reshape(-1)
        yb = np.asarray(getattr(solver, "yb_grid"), dtype=float).reshape(-1)
        if xc.size == nx and yb.size == ny:
            # For visual comparison, optionally drop a small leading segment (x/c < x_over_c_min).
            col_mask = xc >= x_over_c_min
            if not np.any(col_mask):
                col_mask = np.ones_like(xc, dtype=bool)
            xc_plot = xc[col_mask]
            nx_plot = int(xc_plot.size)

            # Plot geometry:
            # - Default: trapezoid planform from VehicleSpec (baseline 2D solver behavior)
            # - Faceted3D: use solver's own strip geometry (outline/STL driven) if available
            is_faceted3d = bool(hasattr(solver, "_strip_xle_chord_mask"))
            b_half = float(getattr(getattr(solver, "vehicle", object()), "b_half_m", 0.0))
            if is_faceted3d and hasattr(solver, "planform_b_half_m"):
                try:
                    b_half = float(getattr(solver, "planform_b_half_m"))
                except Exception:
                    pass

            c_root = float(getattr(solver.vehicle, "c_root_m"))
            c_tip = float(getattr(solver.vehicle, "c_tip_m"))
            sweep_deg = float(getattr(solver.vehicle, "sweep_le_deg"))
            chi = float(np.deg2rad(sweep_deg))

            X = np.zeros((ny, nx_plot), dtype=float)
            Y = np.zeros((ny, nx_plot), dtype=float)
            for j in range(ny):
                y = float(yb[j]) * float(b_half)
                Y[j, :] = y
                if is_faceted3d:
                    try:
                        x_le, chord, _mask = solver._strip_xle_chord_mask(y_over_b=float(yb[j]))  # noqa: SLF001
                        x_le = float(x_le)
                        chord = float(chord)
                        if not (np.isfinite(x_le) and np.isfinite(chord) and chord > 0.0):
                            # keep coordinates finite; z-values will be masked out anyway
                            x_le, chord = 0.0, float(c_root)
                        X[j, :] = x_le + xc_plot * chord
                        continue
                    except Exception:
                        # fall back to baseline geometry
                        pass
                chord = float(c_root + (c_tip - c_root) * float(yb[j]))
                x_le = float(y) * float(np.tan(chi))
                X[j, :] = x_le + xc_plot * chord

            triangles = _triangulate_structured(ny, nx_plot)
            tri_x = X.reshape(-1)
            tri_y = Y.reshape(-1)

            for side, key, cbar_label, prefix in (
                ("windward", "Tw_w", "T / K", "Tw_surface"),
                ("leeward", "Tw_l", "T / K", "Tw_surface"),
                ("windward", "q_w", "q / W/m^2", "q_surface"),
                ("leeward", "q_l", "q / W/m^2", "q_surface"),
            ):
                if key not in fields:
                    continue
                z = np.asarray(fields[key], dtype=float).reshape(-1)
                if z.size != nx * ny:
                    continue
                z2 = z.reshape(ny, nx)[:, col_mask].reshape(-1)
                finite = np.isfinite(z2)
                if not np.any(finite):
                    continue

                # Matplotlib's tricontourf does not allow non-finite z at vertices
                # within the triangulation. Since we purposely set planform-outside
                # points to NaN, mask any triangle that touches a non-finite vertex.
                tri_mask = np.any(~finite[triangles], axis=1)
                tri = mtri.Triangulation(tri_x, tri_y, triangles, mask=tri_mask)

                vmin = float(np.nanmin(z2))
                vmax = float(np.nanmax(z2))
                if not (np.isfinite(vmin) and np.isfinite(vmax)):
                    continue

                fig, ax = plt.subplots(figsize=(7.8, 4.6), dpi=170)
                levels = _levels_from_minmax(vmin=vmin, vmax=vmax, n=40)
                im = ax.tricontourf(tri, z2, levels=levels, cmap="turbo")
                cbar = fig.colorbar(im, ax=ax, pad=0.02)
                cbar.set_label(str(cbar_label))

                # planform outline
                if is_faceted3d and hasattr(solver, "outline_x_m") and hasattr(solver, "outline_span_m"):
                    try:
                        ox = np.asarray(getattr(solver, "outline_x_m"), dtype=float).reshape(-1)
                        oy = np.asarray(getattr(solver, "outline_span_m"), dtype=float).reshape(-1)
                        ok = np.isfinite(ox) & np.isfinite(oy)
                        ox = ox[ok]
                        oy = oy[ok]
                        if ox.size >= 3:
                            # ensure closed polyline for display
                            if not (abs(float(ox[0]) - float(ox[-1])) < 1e-9 and abs(float(oy[0]) - float(oy[-1])) < 1e-9):
                                ox = np.concatenate([ox, ox[:1]])
                                oy = np.concatenate([oy, oy[:1]])
                            ax.plot(ox, oy, color="k", linewidth=1.0, alpha=0.85)
                    except Exception:
                        pass
                else:
                    y0 = 0.0
                    y1 = float(b_half)
                    x_le_root = 0.0
                    x_le_tip = y1 * float(np.tan(chi))
                    x_te_root = x_le_root + float(c_root)
                    x_te_tip = x_le_tip + float(c_tip)
                    ax.plot(
                        [x_le_root, x_le_tip, x_te_tip, x_te_root, x_le_root],
                        [y0, y1, y1, y0, y0],
                        color="k",
                        linewidth=1.0,
                        alpha=0.85,
                    )

                meta_mach = summary.get("inputs", {}).get("mach", None)
                meta_alpha = summary.get("inputs", {}).get("alpha_deg", None)
                h_m = summary.get("freestream", {}).get("h_m", summary.get("inputs", {}).get("h_m_override", None))
                h_km = (None if h_m is None else float(h_m) / 1000.0)
                h_text = ("h=?" if h_km is None else f"h={h_km:.2f} km")
                ax.set_title(f"{key} surface ({side}) | {h_text}, M={meta_mach}, alpha={meta_alpha} deg")
                ax.set_xlabel("x / m")
                ax.set_ylabel("y / m (half-span)")
                ax.set_aspect("equal", adjustable="box")
                ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.35)
                fig.tight_layout()

                p = out_dir / f"{prefix}_{side}.png"
                fig.savefig(p)
                plt.close(fig)
                created.append(str(p))

    return created


def main() -> int:
    _ensure_import_path()

    ap = argparse.ArgumentParser()
    ap.add_argument("--vehicle", default="specs/vehicles/htv2_faceted3d_0629.yaml")
    ap.add_argument("--case", default="specs/cases/doc_ma6_alpha5_h30km_faceted3d.yaml")
    ap.add_argument("--sampling", default="specs/sampling/engineering_full_wing_surface_grid_81x41.yaml")
    ap.add_argument("--run_dir", default="runs/trap_dw_t0034_ma5_h30km_a0_2d")
    ap.add_argument("--mach", type=float, default=5.0)
    ap.add_argument("--alpha", type=float, default=0.0, help="deg")
    ap.add_argument("--h_m", type=float, default=None, help="override flight altitude (meters)")
    ap.add_argument("--h_km", type=float, default=None, help="override flight altitude (kilometers)")
    ap.add_argument("--T_inf_K", type=float, default=None, help="explicit freestream static temperature override (K); requires --p_inf_Pa")
    ap.add_argument("--p_inf_Pa", type=float, default=None, help="explicit freestream static pressure override (Pa); requires --T_inf_K")
    ap.add_argument("--save_npz", action="store_true", default=True)
    ap.add_argument("--no_plots", action="store_true", help="do not generate plot images")
    ap.add_argument("--plot_x_over_c_min", type=float, default=0.0, help="plot only x/c >= this (default: 0.0)")
    ap.add_argument(
        "--transition",
        choices=["case", "on", "off"],
        default="case",
        help="override transition model: case=use YAML, on=enable Eq.(2.46), off=force fully laminar",
    )
    ap.add_argument(
        "--transition_weighting",
        choices=["step", "logistic", "smoothstep"],
        default=None,
        help="optional override for transition weighting/blending mode",
    )
    g3 = ap.add_mutually_exclusive_group()
    g3.add_argument(
        "--transition_x_over_c",
        type=float,
        default=None,
        help="override minimum x/c before transition is allowed",
    )
    g3.add_argument(
        "--no_transition_x_cutoff",
        action="store_true",
        help="clear transition_x_over_c so only Reynolds criterion controls transition",
    )
    g2 = ap.add_mutually_exclusive_group()
    g2.add_argument("--dump_intermediate", dest="dump_intermediate", action="store_true", default=True)
    g2.add_argument("--no_dump_intermediate", dest="dump_intermediate", action="store_false")
    ap.add_argument(
        "--f3_effective_alpha",
        choices=["case", "on", "off"],
        default="case",
        help="faceted3d only: override sweep-corrected alpha in the edge-state chain",
    )
    ap.add_argument(
        "--f3_effective_mach",
        choices=["case", "on", "off"],
        default="case",
        help="faceted3d only: override whether sweep-reduced Mach is used in the edge-state chain",
    )
    ap.add_argument(
        "--f3_x_length_mode",
        choices=["case", "local", "global", "streamline"],
        default="case",
        help="faceted3d only: override the windward development-length model",
    )
    args = ap.parse_args()

    # Select solver branch by vehicle spec content:
    # - default: 2D/strip-theory solver (`ref_enthalpy_method.solver.WingLowFidelitySolver`)
    # - faceted3d: enhanced solver with 3D facet normals (`ref_enthalpy_method.solver_faceted3d.WingLowFidelitySolverFaceted3D`)
    from ref_enthalpy_method.specs.loader import load_yaml  # runtime import

    veh_root = load_yaml(str(args.vehicle))
    veh_spec = veh_root.get("vehicle_spec", {}) if isinstance(veh_root, dict) else {}
    use_faceted3d = bool(isinstance(veh_spec, dict) and ("faceted3d" in veh_spec))

    # --- fail-fast: vehicle / cp_model / geometry integrity checks ---
    veh_id = str(veh_spec.get("vehicle_id", ""))
    is_htv2 = "htv2" in str(veh_id).lower()
    if not is_htv2:
        msg = (
            f"WARNING: vehicle_id='{veh_id}' does not appear to be HTV2. "
            f"Vehicle path: {args.vehicle}"
        )
        print(msg, file=sys.stderr)

    if use_faceted3d:
        f3_spec = veh_spec.get("faceted3d", {})
        if isinstance(f3_spec, dict):
            actual_cp_model = str(f3_spec.get("cp_model", "busemann")).strip().lower()
            actual_cp_A = float(f3_spec.get("cp_newtonian_A", 0.38))
            actual_cp_n = float(f3_spec.get("cp_newtonian_n", 1.15))

            if is_htv2 and actual_cp_model == "busemann":
                msg = (
                    f"ERROR: HTV2 vehicle requires cp_model='newtonian_like' (frozen baseline). "
                    f"Got cp_model='{actual_cp_model}' from {args.vehicle}"
                )
                print(msg, file=sys.stderr)
                raise SystemExit(1)

            if actual_cp_model != "newtonian_like":
                msg = (
                    f"WARNING: cp_model='{actual_cp_model}' is not the frozen newtonian_like baseline. "
                    f"Vehicle: {args.vehicle}"
                )
                print(msg, file=sys.stderr)

            stl_path = str(f3_spec.get("surface", {}).get("stl", "")) if isinstance(f3_spec.get("surface"), dict) else ""
            if is_htv2 and "htv2_0628.stl" not in stl_path:
                msg = (
                    f"WARNING: HTV2 vehicle does not reference htv2_0628.stl. "
                    f"resolved stl path: {stl_path}"
                )
                print(msg, file=sys.stderr)
    else:
        actual_cp_model = "busemann"
        actual_cp_A = float("nan")
        actual_cp_n = float("nan")

    if use_faceted3d:
        from ref_enthalpy_method.solver_faceted3d import WingLowFidelitySolverFaceted3D  # runtime import

        solver = WingLowFidelitySolverFaceted3D(
            vehicle_config=str(args.vehicle),
            case_config=str(args.case),
            sampling_config=str(args.sampling),
            run_dir=str(args.run_dir),
        )
    else:
        from ref_enthalpy_method.solver import WingLowFidelitySolver  # runtime import

        solver = WingLowFidelitySolver(
            vehicle_config=str(args.vehicle),
            case_config=str(args.case),
            sampling_config=str(args.sampling),
            run_dir=str(args.run_dir),
        )

    if (
        (str(args.f3_effective_alpha) != "case" or str(args.f3_effective_mach) != "case" or str(args.f3_x_length_mode) != "case")
        and not use_faceted3d
    ):
        raise ValueError("faceted3d runtime overrides require a vehicle spec with a faceted3d section")

    # Optional override: flight altitude.
    h_override = None
    if args.h_m is not None and args.h_km is not None:
        raise ValueError("Use only one of --h_m or --h_km")
    if args.h_m is not None:
        h_override = float(args.h_m)
    if args.h_km is not None:
        h_override = float(args.h_km) * 1000.0
    if h_override is not None:
        solver.case = replace(solver.case, fixed_h_m=float(h_override))

    # Optional override: explicit freestream T_inf / p_inf (must be paired)
    T_inf_override = None
    p_inf_override = None
    if (args.T_inf_K is not None) != (args.p_inf_Pa is not None):
        raise ValueError("--T_inf_K and --p_inf_Pa must be provided together or both omitted")
    if args.T_inf_K is not None and args.p_inf_Pa is not None:
        T_inf_override = float(args.T_inf_K)
        p_inf_override = float(args.p_inf_Pa)
        if T_inf_override <= 0.0 or p_inf_override <= 0.0:
            raise ValueError("T_inf_K and p_inf_Pa must be positive")
        solver.case = replace(solver.case, T_inf_override_K=T_inf_override, p_inf_override_Pa=p_inf_override)

    solver.case = _override_transition_case(
        solver.case,
        transition_mode=str(args.transition),
        transition_weighting=args.transition_weighting,
        transition_x_over_c=args.transition_x_over_c,
        no_transition_x_cutoff=bool(args.no_transition_x_cutoff),
    )
    from ref_enthalpy_method.config.lf_qw import LfQwConfig  # runtime import

    solver.lf_cfg = LfQwConfig.from_case(solver.case)
    _override_faceted3d_config(
        solver,
        effective_alpha_mode=str(args.f3_effective_alpha),
        effective_mach_mode=str(args.f3_effective_mach),
        x_length_mode=str(args.f3_x_length_mode),
    )

    _u = solver.compute_snapshot(mach=float(args.mach), alpha=float(args.alpha))
    fields = dict(solver.last_fields or {})

    out_dir = Path(solver.run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "inputs": {
            "vehicle_config": str(args.vehicle),
            "case_config": str(args.case),
            "sampling_config": str(args.sampling),
            "run_dir": str(args.run_dir),
            "mach": float(args.mach),
            "alpha_deg": float(args.alpha),
            "h_m_override": (None if h_override is None else float(h_override)),
            "T_inf_K_override": (None if T_inf_override is None else float(T_inf_override)),
            "p_inf_Pa_override": (None if p_inf_override is None else float(p_inf_override)),
            "transition_override": str(args.transition),
            "transition_weighting_override": (None if args.transition_weighting is None else str(args.transition_weighting)),
            "transition_x_over_c_override": (None if args.transition_x_over_c is None else float(args.transition_x_over_c)),
            "no_transition_x_cutoff": bool(args.no_transition_x_cutoff),
            "f3_effective_alpha_override": (None if str(args.f3_effective_alpha) == "case" else str(args.f3_effective_alpha)),
            "f3_effective_mach_override": (None if str(args.f3_effective_mach) == "case" else str(args.f3_effective_mach)),
            "f3_x_length_mode_override": (None if str(args.f3_x_length_mode) == "case" else str(args.f3_x_length_mode)),
            "thermo_model": "tpg",
        },
        "resolved_paths": {
            "project_root": str(solver.project_root),
            "vehicle_path": str(solver.veh_path),
            "case_path": str(solver.case_path),
            "sampling_path": str(solver.samp_path),
        },
        "vehicle": _np_to_builtin(solver.vehicle.__dict__),
        "case": _np_to_builtin(solver.case.__dict__),
        "sampling": _np_to_builtin(solver.sampling.__dict__),
        "outputs_available": list(fields.keys()),
    }
    summary["actual_cp_model"] = actual_cp_model
    summary["actual_cp_newtonian_A"] = actual_cp_A
    summary["actual_cp_newtonian_n"] = actual_cp_n
    if use_faceted3d:
        f3_spec = veh_spec.get("faceted3d", {})
        if isinstance(f3_spec, dict):
            summary["actual_outline_path"] = str(f3_spec.get("planform", {}).get("outline_csv", "")) if isinstance(f3_spec.get("planform"), dict) else ""
            summary["actual_stl_path"] = str(f3_spec.get("surface", {}).get("stl", "")) if isinstance(f3_spec.get("surface"), dict) else ""
    summary["actual_vehicle_path"] = str(args.vehicle)
    summary["actual_mach"] = float(args.mach)
    summary["actual_alpha"] = float(args.alpha)
    summary["actual_h_m"] = (None if h_override is None else float(h_override)) or float(solver.case.fixed_h_m)
    summary["transition_runtime"] = {
        "enable": bool(getattr(solver.lf_cfg.transition, "enable", True)),
        "weighting": str(getattr(solver.lf_cfg.transition, "weighting", "logistic")),
        "width_decades": float(getattr(solver.lf_cfg.transition, "width_decades", 0.25)),
        "transition_x_over_c": (None if solver.case.transition_x_over_c is None else float(solver.case.transition_x_over_c)),
    }
    if hasattr(solver, "f3_cfg"):
        summary["faceted3d"] = _np_to_builtin(getattr(solver, "f3_cfg").__dict__)
        try:
            from ref_enthalpy_method.aero.windward_cache_faceted3d import resolve_faceted3d_edge_inflow

            inflow = resolve_faceted3d_edge_inflow(
                mach=float(args.mach),
                alpha_deg=float(args.alpha),
                sweep_le_deg=float(getattr(solver.vehicle, "sweep_le_deg")),
                use_effective_alpha=bool(getattr(solver.f3_cfg, "edge_use_effective_alpha", True)),
                use_effective_mach=bool(getattr(solver.f3_cfg, "edge_use_effective_mach", False)),
            )
            summary["faceted3d_edge_state"] = {
                "alpha_input_deg": float(args.alpha),
                "alpha_eff_deg": float(np.rad2deg(float(inflow.alpha_effective_rad))),
                "alpha_edge_deg": float(np.rad2deg(float(inflow.alpha_edge_rad))),
                "mach_input": float(inflow.mach_input),
                "mach_eff": float(inflow.mach_effective),
                "mach_edge": float(inflow.mach_edge),
                "use_effective_alpha": bool(inflow.use_effective_alpha),
                "use_effective_mach": bool(inflow.use_effective_mach),
                "x_length_mode": str(getattr(solver.f3_cfg, "x_length_mode", "streamline")),
            }
        except Exception as e:
            summary["faceted3d_edge_state_error"] = str(e)
    # Warning summary
    try:
        warnings = list(getattr(solver, "warning_log").warnings)  # type: ignore[attr-defined]
        summary["warnings_count"] = int(len(warnings))
        summary["warnings_preview"] = warnings[:10]
        summary["warnings_log_path"] = str(Path(solver.run_dir) / "lf_warnings.log")
    except Exception:
        pass

    # Freestream summary (baseline-style)
    try:
        p_inf, rho_inf, T_inf, v_inf = solver._freestream(float(args.mach))  # noqa: SLF001
        summary["freestream"] = {
            "altitude_input_m": float(solver.case.fixed_h_m),
            "atmosphere_model": str(solver.case.atmosphere_model),
            "freestream_source": ("explicit_override" if T_inf_override is not None else "atmosphere"),
            "T_inf_K": float(T_inf),
            "p_inf_Pa": float(p_inf),
            "rho_inf_kg_m3": float(rho_inf),
            "Mach": float(args.mach),
            "alpha_deg": float(args.alpha),
            "gamma": float(solver.case.gamma),
            "R_J_per_kgK": float(solver.case.R_J_per_kgK),
            "V_inf_m_s": float(v_inf),
        }
    except Exception as e:
        summary["freestream_error"] = str(e)

    arrays_to_save: dict[str, np.ndarray] = {}
    for key in (
        "q_w",
        "q_l",
        "Tw_w",
        "Tw_l",
        "w_tr",
        "re_edge",
        "re_tri",
        "re_x_star",
        "re_x_over_re_tri",
        "t_s",
        "Tw_w_time",
        "q_w_time",
    ):
        if key in fields:
            arrays_to_save[key] = np.asarray(fields[key], dtype=float)
            summary[f"summary_{key}"] = _summarize_array(key, arrays_to_save[key])
    for key in (
        "x_w_m",
        "span_w_m",
        "x_l_m",
        "span_l_m",
        "xc_w",
        "yb_w",
        "xc_l",
        "yb_l",
        "mask_w",
        "mask_l",
        "xc_grid",
        "yb_grid",
        "T_e_w",
        "p_e_w",
        "rho_e_w",
        "ma_e_w",
        "v_e_w",
        "mu_e_w",
        "phi_w",
        "cp_w",
        "cp0_w",
        "h_e_w",
        "T_r_lam_w",
        "h_r_lam_w",
        "h_star_lam_w",
        "T_r_turb_w",
        "h_r_turb_w",
        "h_star_turb_w",
        "q_lam_w",
        "q_turb_w",
        "St_l",
        "Re_ns_l",
        "Taw_tpg_w",
    ):
        if key in fields:
            arrays_to_save[key] = np.asarray(fields[key], dtype=float)

    for key in (
        "normal_x_upper",
        "normal_y_upper",
        "normal_z_upper",
        "normal_x_lower",
        "normal_y_lower",
        "normal_z_lower",
        "incidence_s_upper",
        "incidence_s_lower",
    ):
        if key in fields:
            arrays_to_save[key] = np.asarray(fields[key], dtype=float)
    for key in ("surface_class_upper", "surface_class_lower", "normal_source_upper", "normal_source_lower"):
        if key in fields:
            arrays_to_save[key] = np.asarray(fields[key], dtype=np.int8)

    for key in (
        "mask_leeward_upper",
        "mask_leeward_lower",
    ):
        if key in fields:
            arrays_to_save[key] = np.asarray(fields[key])
    for key in (
        "T_e_leeward_upper",
        "T_e_leeward_lower",
        "p_e_leeward_upper",
        "p_e_leeward_lower",
        "rho_e_leeward_upper",
        "rho_e_leeward_lower",
        "V_e_leeward_upper",
        "V_e_leeward_lower",
        "Ma_e_leeward_upper",
        "Ma_e_leeward_lower",
        "h_e_leeward_upper",
        "h_e_leeward_lower",
        "mu_e_leeward_upper",
        "mu_e_leeward_lower",
        "Taw_tpg_leeward_upper",
        "Taw_tpg_leeward_lower",
    ):
        if key in fields:
            arrays_to_save[key] = np.asarray(fields[key], dtype=np.float64)

    if use_faceted3d:
        summary["local_incidence"] = {
            "diagnostic_only": True,
            "formal_solver_routing_unchanged": True,
            "body_axes": {"x": "nose_to_tail", "y": "spanwise", "z": "up"},
            "u_hat": "actual_gas_velocity_direction",
            "n_out": "sheet_identity_oriented_outward_unit_normal",
            "definition": "s = -dot(u_hat, n_out)",
            "epsilon": 0.05,
            "classification": {"1": "windward", "0": "near_tangent", "-1": "leeward", "-2": "invalid"},
            "normal_source": {
                "1": "stl_accepted_by_qchain_filter",
                "2": "stl_rejected_by_qchain_filter_but_used_for_classification",
                "3": "analytic_fallback_no_stl_coverage",
                "0": "invalid",
            },
            "outward_orientation": {"upper": "n_z > 0", "lower": "n_z < 0"},
        }

    if bool(args.dump_intermediate):
        summary["intermediate"] = _build_intermediate(solver=solver, fields=arrays_to_save, mach=float(args.mach), alpha=float(args.alpha))

    # Transition diagnostics
    if "w_tr" in arrays_to_save:
        w_tr = np.asarray(arrays_to_save["w_tr"], dtype=float).reshape(-1)
        finite = np.isfinite(w_tr)
        if np.any(finite):
            wf = w_tr[finite]
            summary["transition_stats"] = {
                "w_tr_max": float(np.max(wf)),
                "w_tr_mean": float(np.mean(wf)),
                "w_tr_frac_gt_0p5": float(np.mean(wf > 0.5)),
                "w_tr_frac_gt_0p1": float(np.mean(wf > 0.1)),
            }

    # Quick distribution samples for 1D root line runs
    if hasattr(solver, "xc_grid"):
        xc = np.asarray(solver.xc_grid, dtype=float).reshape(-1)
        if "q_w" in arrays_to_save and arrays_to_save["q_w"].reshape(-1).size == xc.size:
            summary["samples_q_w"] = _profile_samples(xc, arrays_to_save["q_w"])
        if "Tw_w" in arrays_to_save and arrays_to_save["Tw_w"].reshape(-1).size == xc.size:
            summary["samples_Tw_w"] = _profile_samples(xc, arrays_to_save["Tw_w"])
        if "q_l" in arrays_to_save and arrays_to_save["q_l"].reshape(-1).size == xc.size:
            summary["samples_q_l"] = _profile_samples(xc, arrays_to_save["q_l"])
        if "Tw_l" in arrays_to_save and arrays_to_save["Tw_l"].reshape(-1).size == xc.size:
            summary["samples_Tw_l"] = _profile_samples(xc, arrays_to_save["Tw_l"])

        # 2D mode diagnostics: chordwise monotonicity (root strip + spanwise mean).
        mode = str(getattr(solver.sampling, "mode", "")).strip()
        if mode == "full_wing_surface_grid":
            nx = int(getattr(solver, "nx", xc.size))
            ny = int(getattr(solver, "ny", 0))
            if nx > 1 and ny > 1:
                def _reshape2(a: np.ndarray) -> np.ndarray:
                    return np.asarray(a, dtype=float).reshape(ny, nx)

                if "Tw_w" in arrays_to_save and arrays_to_save["Tw_w"].size == nx * ny:
                    Tw2 = _reshape2(arrays_to_save["Tw_w"])
                    Tw_root = Tw2[0, :]
                    Tw_mean_y = np.nanmean(Tw2, axis=0)
                    summary["diagnostics_Tw_w_chordwise"] = {
                        "root_strip": {
                            "monotone_decrease_tol_1K": _monotonic_decrease_report(x_over_c=xc, y=Tw_root, tol=1.0),
                            "samples": _profile_samples(xc, Tw_root, n_points=10),
                        },
                        "spanwise_mean": {
                            "monotone_decrease_tol_1K": _monotonic_decrease_report(x_over_c=xc, y=Tw_mean_y, tol=1.0),
                            "samples": _profile_samples(xc, Tw_mean_y, n_points=10),
                        },
                    }

                # Also report w_tr chordwise trend so we can correlate with Tw rise.
                if "w_tr" in arrays_to_save and arrays_to_save["w_tr"].size == nx * ny:
                    w2 = _reshape2(arrays_to_save["w_tr"])
                    w_root = w2[0, :]
                    w_mean_y = np.nanmean(w2, axis=0)
                    summary["diagnostics_w_tr_chordwise"] = {
                        "root_strip": {"samples": _profile_samples(xc, w_root, n_points=10)},
                        "spanwise_mean": {"samples": _profile_samples(xc, w_mean_y, n_points=10)},
                    }
                if "q_w" in arrays_to_save and arrays_to_save["q_w"].size == nx * ny:
                    q2 = _reshape2(arrays_to_save["q_w"])
                    finite = np.isfinite(q2)
                    if np.any(finite):
                        yb = np.asarray(getattr(solver, "yb_grid"), dtype=float).reshape(-1)
                        X = np.zeros((ny, nx), dtype=float)
                        Y = np.zeros((ny, nx), dtype=float)
                        is_faceted3d = bool(hasattr(solver, "_strip_xle_chord_mask"))
                        b_half = float(getattr(getattr(solver, "vehicle", object()), "b_half_m", 0.0))
                        if is_faceted3d and hasattr(solver, "planform_b_half_m"):
                            try:
                                b_half = float(getattr(solver, "planform_b_half_m"))
                            except Exception:
                                pass
                        c_root = float(getattr(solver.vehicle, "c_root_m"))
                        c_tip = float(getattr(solver.vehicle, "c_tip_m"))
                        sweep_deg = float(getattr(solver.vehicle, "sweep_le_deg"))
                        chi = float(np.deg2rad(sweep_deg))
                        for j in range(ny):
                            y = float(yb[j]) * float(b_half)
                            Y[j, :] = y
                            if is_faceted3d:
                                try:
                                    x_le, chord, _mask = solver._strip_xle_chord_mask(y_over_b=float(yb[j]))  # noqa: SLF001
                                    x_le = float(x_le)
                                    chord = float(chord)
                                    if not (np.isfinite(x_le) and np.isfinite(chord) and chord > 0.0):
                                        x_le, chord = 0.0, float(c_root)
                                    X[j, :] = x_le + xc * chord
                                    continue
                                except Exception:
                                    pass
                            chord = float(c_root + (c_tip - c_root) * float(yb[j]))
                            x_le = float(y) * float(np.tan(chi))
                            X[j, :] = x_le + xc * chord
                        q2_masked = np.where(finite, q2, -np.inf)
                        idx_max = int(np.nanargmax(q2_masked))
                        j_max, i_max = divmod(idx_max, nx)
                        q2_masked_min = np.where(finite, q2, np.inf)
                        idx_min = int(np.nanargmin(q2_masked_min))
                        j_min, i_min = divmod(idx_min, nx)
                        summary["extrema_q_w"] = {
                            "max": {
                                "value": float(q2[j_max, i_max]),
                                "i": int(i_max),
                                "j": int(j_max),
                                "x_over_c": float(xc[i_max]),
                                "y_over_b": float(yb[j_max]),
                                "x_m": float(X[j_max, i_max]),
                                "y_m": float(Y[j_max, i_max]),
                            },
                            "min": {
                                "value": float(q2[j_min, i_min]),
                                "i": int(i_min),
                                "j": int(j_min),
                                "x_over_c": float(xc[i_min]),
                                "y_over_b": float(yb[j_min]),
                                "x_m": float(X[j_min, i_min]),
                                "y_m": float(Y[j_min, i_min]),
                            },
                        }
                        le_band = []
                        for j in range(ny):
                            qv = float(q2[j, 0])
                            if not np.isfinite(qv):
                                continue
                            le_band.append(
                                {
                                    "j": int(j),
                                    "x_over_c": 0.0,
                                    "y_over_b": float(yb[j]),
                                    "x_m": float(X[j, 0]),
                                    "y_m": float(Y[j, 0]),
                                    "value": qv,
                                }
                            )
                        summary["leading_edge_q_w"] = le_band

    # Radiative equilibrium residual check: q_a - eps*sigma*Tw^4 (should be ~0)
    eps = float(getattr(solver.vehicle, "emissivity", float("nan")))
    sigma = float(getattr(solver.case, "sigma_W_m2_K4", float("nan")))
    if np.isfinite(eps) and np.isfinite(sigma):
        if ("q_w" in arrays_to_save) and ("Tw_w" in arrays_to_save):
            q = np.asarray(arrays_to_save["q_w"], dtype=float).reshape(-1)
            Tw = np.asarray(arrays_to_save["Tw_w"], dtype=float).reshape(-1)
            if q.size == Tw.size:
                res = q - eps * sigma * (Tw**4)
                summary["radiative_balance_windward"] = {
                    "eps": eps,
                    "sigma": sigma,
                    "residual_abs_max": float(np.nanmax(np.abs(res))),
                    "residual_abs_mean": float(np.nanmean(np.abs(res))),
                    "residual_rel_max": float(np.nanmax(np.abs(res) / np.maximum(1.0, np.abs(q)))),
                }
        if ("q_l" in arrays_to_save) and ("Tw_l" in arrays_to_save):
            q = np.asarray(arrays_to_save["q_l"], dtype=float).reshape(-1)
            Tw = np.asarray(arrays_to_save["Tw_l"], dtype=float).reshape(-1)
            if q.size == Tw.size:
                res = q - eps * sigma * (Tw**4)
                summary["radiative_balance_leeward"] = {
                    "eps": eps,
                    "sigma": sigma,
                    "residual_abs_max": float(np.nanmax(np.abs(res))),
                    "residual_abs_mean": float(np.nanmean(np.abs(res))),
                    "residual_rel_max": float(np.nanmax(np.abs(res) / np.maximum(1.0, np.abs(q)))),
                }

    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    if bool(args.save_npz) and len(arrays_to_save) > 0:
        np.savez_compressed(out_dir / "fields.npz", **arrays_to_save)

    created_plots: list[str] = []
    if not bool(args.no_plots):
        created_plots = _try_save_plots(
            solver=solver,
            out_dir=out_dir,
            fields=arrays_to_save,
            summary=summary,
            plot_x_over_c_min=float(args.plot_x_over_c_min),
        )

    print("=== ref_enthalpy_method run_case ===")
    print(f"written: {out_dir / 'summary.json'}")
    if bool(args.save_npz):
        print(f"written: {out_dir / 'fields.npz'}")
    for p in created_plots:
        print(f"written: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
