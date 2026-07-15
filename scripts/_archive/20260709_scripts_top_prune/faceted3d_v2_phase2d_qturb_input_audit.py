#!/usr/bin/env python3
"""Phase 2D q_turb-input audit — read-only decomposition of q_turb branch.

Extracts per-point:
  - q_lam, q_turb, q_LF (solver blended), q_Fluent (aligned)
  - Re_x_star_lam, Re_x_star_turb, re_tri, re_x_over_re_tri, w_tr
  - h_r_lam - h_w, h_r_turb - h_w
  - rho*_lam / rho_e, mu*_lam / mu_e  (laminar star ratios)
  - rho*_turb / rho_e, mu*_turb / mu_e  (turbulent star ratios)
  - q_turb / q_lam ratio
  - turb_branch_active (true if re_edge > re_tri)
  - distance_from_transition (x_phys - x_phys_at_transition)

No solver code modification. No configuration changes. Only read-only diagnostics.
"""

from __future__ import annotations

import csv, math, sys, warnings
from pathlib import Path
from copy import deepcopy

import numpy as np

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except:
    HAS_MPL = False

from ref_enthalpy_method.solver_faceted3d import WingLowFidelitySolverFaceted3D
from ref_enthalpy_method.heatflux.windward import windward_ref_enthalpy_branches, WindwardBranches
from ref_enthalpy_method.aero.transition import transition_reynolds, transition_weight
from ref_enthalpy_method.config.lf_qw import LfQwConfig

BASE = Path(__file__).resolve().parent.parent
VEHICLE_TEMPLATE = BASE / "specs/vehicles/htv2_faceted3d_0629.yaml"
CASE_TEMPLATE = BASE / "specs/cases/template_faceted3d_fixedTw300.yaml"
SAMPLING = BASE / "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml"
FLUENT_DIR = BASE / "fluent_export"
OUT_DIR = BASE / "runs/faceted3d_v2_phase2d_qturb_input_audit"
DOCS_DIR = BASE / "docs"
FIG_DIR = OUT_DIR / "figures"

NEWTONIAN_A = 0.38
NEWTONIAN_N = 1.15
Rn = 0.03
r_cap = 0.03
C_ROOT_M = 3.6

FORBIDDEN = ("ma8_a10",)


def _ussa(h_m):
    R = 287.0; g0 = 9.80665
    if h_m <= 11000: T = 288.15 - 0.0065 * h_m; P = 101325 * (T / 288.15) ** (-g0 / (R * -0.0065))
    elif h_m <= 20000: T = 216.65; P = 22632.1 * np.exp(-g0 / (R * T) * (h_m - 11000))
    else: T = 216.65 + 0.001 * (h_m - 20000); P = 5474.89 * (T / 216.65) ** (-g0 / (R * 0.001))
    return float(P), float(P / (R * T)), float(T)

def _freestream_v(mach, T_inf):
    return mach * math.sqrt(1.4 * 287.0 * T_inf)


def _read_fluent_windward(path):
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f); h = next(reader)
    hm = {hs.strip().lower(): i for i, hs in enumerate(h)}
    xi = hm.get("x-coordinate", 1); yi = hm.get("y-coordinate", 2); zi = hm.get("z-coordinate", 3)
    pi = hm.get("absolute-pressure", hm.get("pressure", 4)); qi = hm.get("heat-flux", 9)
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f); next(reader)
        for row in reader:
            try:
                x = float(row[xi]); y = float(row[yi]); z = float(row[zi])
                if z >= 0: continue
                span = math.sqrt(y*y + z*z)
                p = float(row[pi]); q = -float(row[qi])
                rows.append([x, span, z, p, q, y])
            except: continue
    return np.array(rows, dtype=float)


def _assign_region_windward(x, span, xc, mask_w):
    n = len(x)
    regions = np.full(n, "unknown", dtype=object)
    for i in range(n):
        if not (np.isfinite(x[i]) and np.isfinite(span[i]) and mask_w[i]):
            continue
        xi = float(x[i]); si = float(span[i]); xci = float(xc[i])
        if xi**2 + si**2 <= r_cap**2:
            regions[i] = "cap_mask"
        elif xi < 5.0 * Rn and si < 0.10:
            regions[i] = "true_nose_cap"
        elif si > xi / 6.0:
            regions[i] = "leading_edge_near"
        elif xci > 0.5:
            regions[i] = "aft_body"
        else:
            regions[i] = "windward_body"
    return regions


def _nearest_match(solver_x, solver_span, flt_x, flt_span, flt_q, flt_p=None):
    n = len(solver_x)
    matched_q = np.full(n, np.nan)
    matched_p = np.full(n, np.nan) if flt_p is not None else None
    for i in range(n):
        fx = float(solver_x[i]); fs = float(solver_span[i])
        if not (np.isfinite(fx) and np.isfinite(fs)):
            continue
        dx = np.abs(flt_x - fx); ds = np.abs(flt_span - fs)
        dist = np.sqrt(dx**2 + (0.3*ds)**2)
        best = np.nanargmin(dist)
        if dist[best] <= np.sqrt(0.02**2 + (0.3*0.02)**2):
            matched_q[i] = float(flt_q[best])
            if matched_p is not None:
                matched_p[i] = float(flt_p[best])
    return matched_q, matched_p


def _trim(arr, ref_len):
    arr = np.asarray(arr, dtype=float).ravel()
    if len(arr) >= ref_len: return arr[:ref_len]
    out = np.full(ref_len, np.nan); out[:len(arr)] = arr; return out


def run_and_audit(label, fluent_csv, mach, alpha, h_m):
    """Run solver (baseline config), then decompose q_turb input chain per point."""
    import yaml as _yaml
    
    for fb in FORBIDDEN:
        if fb in label.lower():
            raise ValueError(f"BLOCKED: case {label!r} contains {fb!r}")
    
    # Build baseline config
    veh = _yaml.safe_load(VEHICLE_TEMPLATE.read_text(encoding="utf-8"))
    f3 = veh["vehicle_spec"]["faceted3d"]
    f3["cp_model"] = "newtonian_like"
    f3["cp_newtonian_A"] = NEWTONIAN_A
    f3["cp_newtonian_n"] = NEWTONIAN_N
    
    vp = OUT_DIR / f"veh_{label}.yaml"
    with open(vp, "w", encoding="utf-8") as f:
        _yaml.dump(veh, f, default_flow_style=False)
    
    case_data = _yaml.safe_load(CASE_TEMPLATE.read_text(encoding="utf-8"))
    case_data["case_spec"]["lf_qw_model"]["transition"]["weighting"] = "step"
    cp = OUT_DIR / f"case_{label}.yaml"
    with open(cp, "w", encoding="utf-8") as f:
        _yaml.dump(case_data, f, default_flow_style=False)
    
    solver = WingLowFidelitySolverFaceted3D(
        vehicle_config=str(vp), case_config=str(cp),
        sampling_config=str(SAMPLING), run_dir=str(OUT_DIR / label),
    )
    solver.compute_snapshot(mach=mach, alpha=alpha)
    fields = dict(solver.last_fields or {})
    
    p_inf, rho_inf, T_inf = _ussa(h_m)
    v_inf = _freestream_v(mach, T_inf)
    q_inf = 0.5 * rho_inf * v_inf**2
    
    # Extract fields
    x_w = _trim(fields.get("x_w_m", np.array([])), 4000)
    span_w = _trim(fields.get("span_w_m", np.array([])), 4000)
    xc_w = _trim(fields.get("xc_w", np.array([])), 4000)
    q_w = _trim(fields.get("q_w", np.array([])), 4000)
    p_e_w = _trim(fields.get("p_e_w", np.array([])), 4000)
    cp_w = _trim(fields.get("cp_w", np.array([])), 4000)
    w_tr = _trim(fields.get("w_tr", np.array([])), 4000)
    mask_w = _trim(fields.get("mask_w", np.array([])), 4000).astype(bool)
    q_lam_w = _trim(fields.get("q_lam_w", np.array([])), 4000)
    q_turb_w = _trim(fields.get("q_turb_w", np.array([])), 4000)
    h_r_lam_w = _trim(fields.get("h_r_lam_w", np.array([])), 4000)
    h_r_turb_w = _trim(fields.get("h_r_turb_w", np.array([])), 4000)
    h_star_lam_w = _trim(fields.get("h_star_lam_w", np.array([])), 4000)
    h_star_turb_w = _trim(fields.get("h_star_turb_w", np.array([])), 4000)
    T_r_lam_w = _trim(fields.get("T_r_lam_w", np.array([])), 4000)
    T_r_turb_w = _trim(fields.get("T_r_turb_w", np.array([])), 4000)
    re_tri = _trim(fields.get("re_tri", np.array([])), 4000)
    re_x_star = _trim(fields.get("re_x_star", np.array([])), 4000)
    re_x_over_re_tri = _trim(fields.get("re_x_over_re_tri", np.array([])), 4000)
    re_edge = _trim(fields.get("re_edge", np.array([])), 4000)
    T_e_w = _trim(fields.get("T_e_w", np.array([])), 4000)
    ma_e_w = _trim(fields.get("ma_e_w", np.array([])), 4000)
    v_e_w = _trim(fields.get("v_e_w", np.array([])), 4000)
    rho_e_w = _trim(fields.get("rho_e_w", np.array([])), 4000)
    mu_e_w = _trim(fields.get("mu_e_w", np.array([])), 4000)
    Tw_w = _trim(fields.get("Tw_w", np.array([])), 4000)
    h_e_w = _trim(fields.get("h_e_w", np.array([])), 4000)
    
    # Region assignment
    w_regions = _assign_region_windward(x_w, span_w, xc_w, mask_w)
    
    # Trim
    ref_w = min(len(x_w), len(span_w), len(xc_w), len(q_w), len(p_e_w),
                len(cp_w), len(mask_w), len(w_tr), len(q_lam_w), len(q_turb_w),
                len(h_r_lam_w), len(h_r_turb_w), len(re_tri), len(T_e_w),
                len(ma_e_w), len(v_e_w), len(rho_e_w), len(mu_e_w), len(h_e_w),
                len(w_regions))
    x_w = x_w[:ref_w]; span_w = span_w[:ref_w]; xc_w = xc_w[:ref_w]
    q_w = q_w[:ref_w]; p_e_w = p_e_w[:ref_w]; cp_w = cp_w[:ref_w]
    w_tr = w_tr[:ref_w]; mask_w = mask_w[:ref_w].astype(bool)
    q_lam_w = q_lam_w[:ref_w]; q_turb_w = q_turb_w[:ref_w]
    h_r_lam_w = h_r_lam_w[:ref_w]; h_r_turb_w = h_r_turb_w[:ref_w]
    h_star_lam_w = h_star_lam_w[:ref_w]; h_star_turb_w = h_star_turb_w[:ref_w]
    T_r_lam_w = T_r_lam_w[:ref_w]; T_r_turb_w = T_r_turb_w[:ref_w]
    re_tri = re_tri[:ref_w]; re_x_star = re_x_star[:ref_w]
    re_x_over_re_tri = re_x_over_re_tri[:ref_w]; re_edge = re_edge[:ref_w]
    T_e_w = T_e_w[:ref_w]; ma_e_w = ma_e_w[:ref_w]; v_e_w = v_e_w[:ref_w]
    rho_e_w = rho_e_w[:ref_w]; mu_e_w = mu_e_w[:ref_w]; h_e_w = h_e_w[:ref_w]
    Tw_w = Tw_w[:ref_w]; w_regions = w_regions[:ref_w]
    
    # Fluent alignment
    flt_w = _read_fluent_windward(fluent_csv)
    flt_w_x = flt_w[:, 0]; flt_w_span = flt_w[:, 1]; flt_w_q = flt_w[:, 4]; flt_w_p = flt_w[:, 3]
    matched_q_w, matched_p_w = _nearest_match(x_w, span_w, flt_w_x, flt_w_span, flt_w_q, flt_w_p)
    
    # For each point, decompose q_turb input chain
    per_point_rows = []
    
    gas = solver.gas
    R_gas = float(gas.R)
    Pr = float(gas.prandtl)
    
    for i in range(ref_w):
        if not (mask_w[i] and np.isfinite(q_w[i]) and np.isfinite(matched_q_w[i]) and matched_q_w[i] > 0):
            continue
        
        reg = w_regions[i] if i < len(w_regions) else "unknown"
        
        # Reynolds numbers from solver fields
        re_tri_val = float(re_tri[i]) if np.isfinite(re_tri[i]) else float("nan")
        re_edge_val = float(re_edge[i]) if np.isfinite(re_edge[i]) else float("nan")
        re_x_star_lam = float(re_x_star[i]) if np.isfinite(re_x_star[i]) else float("nan")
        re_x_star_turb = float("nan")  # not directly stored
        re_x_over_re_tri_val = float(re_x_over_re_tri[i]) if np.isfinite(re_x_over_re_tri[i]) else float("nan")
        
        w_tr_val = float(w_tr[i]) if np.isfinite(w_tr[i]) else float("nan")
        
        # q values from solver
        q_LF = float(q_w[i])
        q_Fluent = float(matched_q_w[i])
        q_ratio = q_LF / q_Fluent
        q_lam = float(q_lam_w[i]) if np.isfinite(q_lam_w[i]) else float("nan")
        q_turb = float(q_turb_w[i]) if np.isfinite(q_turb_w[i]) else float("nan")
        q_turb_over_q_lam = q_turb / q_lam if (np.isfinite(q_turb) and np.isfinite(q_lam) and abs(q_lam) > 1e-12) else float("nan")
        
        # h_r - h_w
        h_w = float(gas.h_from_T(float(Tw_w[i]))) if np.isfinite(Tw_w[i]) else float("nan")
        h_r_lam = float(h_r_lam_w[i]) if np.isfinite(h_r_lam_w[i]) else float("nan")
        h_r_turb = float(h_r_turb_w[i]) if np.isfinite(h_r_turb_w[i]) else float("nan")
        h_r_lam_minus_h_w = h_r_lam - h_w if (np.isfinite(h_r_lam) and np.isfinite(h_w)) else float("nan")
        h_r_turb_minus_h_w = h_r_turb - h_w if (np.isfinite(h_r_turb) and np.isfinite(h_w)) else float("nan")
        
        # Star ratios: recompute from scratch using the same formulas as windward_ref_enthalpy_branches
        # We need edge conditions. The solver stores per-point edge values.
        rho_star_lam_over_rho_e = float("nan")
        mu_star_lam_over_mu_e = float("nan")
        rho_star_turb_over_rho_e = float("nan")
        mu_star_turb_over_mu_e = float("nan")
        
        T_e = float(T_e_w[i]) if np.isfinite(T_e_w[i]) else float("nan")
        ma_e = float(ma_e_w[i]) if np.isfinite(ma_e_w[i]) else float("nan")
        v_e = float(v_e_w[i]) if np.isfinite(v_e_w[i]) else float("nan")
        rho_e = float(rho_e_w[i]) if np.isfinite(rho_e_w[i]) else float("nan")
        mu_e = float(mu_e_w[i]) if np.isfinite(mu_e_w[i]) else float("nan")
        p_e = float(p_e_w[i]) if np.isfinite(p_e_w[i]) else float("nan")
        h_e = float(h_e_w[i]) if np.isfinite(h_e_w[i]) else float("nan")
        x_phys = float(xc_w[i]) * C_ROOT_M  # approximate x_phys
        
        if np.isfinite(T_e) and np.isfinite(h_w) and np.isfinite(ma_e):
            try:
                # Laminar star props
                T_r_lam = float(T_r_lam_w[i]) if np.isfinite(T_r_lam_w[i]) else float("nan")
                if np.isfinite(T_r_lam) and not np.isfinite(T_r_lam):
                    T_r_lam = T_e * (1.0 + math.sqrt(Pr) * (gas.gamma - 1.0) / 2.0 * ma_e**2)
                if np.isfinite(h_e):
                    h_r_lam_recalc = float(gas.h_from_T(T_r_lam)) if np.isfinite(T_r_lam) else float("nan")
                    if np.isfinite(h_r_lam_recalc) and np.isfinite(h_w):
                        h_star_lam = h_e + 0.5 * (h_w - h_e) + 0.22 * (h_r_lam_recalc - h_e)
                        if np.isfinite(h_star_lam):
                            T_star_lam = float(gas.T_from_h(h_star_lam))
                            if np.isfinite(p_e) and np.isfinite(T_star_lam) and T_star_lam > 0:
                                rho_star_lam = p_e / (R_gas * T_star_lam)
                                mu_star_lam = float(gas.mu(T_star_lam))
                                rho_star_lam_over_rho_e = rho_star_lam / rho_e if rho_e > 0 else float("nan")
                                mu_star_lam_over_mu_e = mu_star_lam / mu_e if mu_e > 0 else float("nan")
                
                # Turbulent star props
                T_r_turb = float(T_r_turb_w[i]) if np.isfinite(T_r_turb_w[i]) else float("nan")
                if np.isfinite(T_r_turb) and not np.isfinite(T_r_turb):
                    T_r_turb = T_e * (1.0 + (Pr**(1/3)) * (gas.gamma - 1.0) / 2.0 * ma_e**2)
                if np.isfinite(h_e):
                    h_r_turb_recalc = float(gas.h_from_T(T_r_turb)) if np.isfinite(T_r_turb) else float("nan")
                    if np.isfinite(h_r_turb_recalc) and np.isfinite(h_w):
                        h_star_turb = h_e + 0.5 * (h_w - h_e) + 0.22 * (h_r_turb_recalc - h_e)
                        if np.isfinite(h_star_turb):
                            T_star_turb = float(gas.T_from_h(h_star_turb))
                            if np.isfinite(p_e) and np.isfinite(T_star_turb) and T_star_turb > 0:
                                rho_star_turb = p_e / (R_gas * T_star_turb)
                                mu_star_turb = float(gas.mu(T_star_turb))
                                rho_star_turb_over_rho_e = rho_star_turb / rho_e if rho_e > 0 else float("nan")
                                mu_star_turb_over_mu_e = mu_star_turb / mu_e if mu_e > 0 else float("nan")
            except Exception:
                pass
        
        # turb_branch_active: True if Re_x > Re_tri (fully turbulent branch)
        # The solver uses w_tr for blending, but the "turbulent branch" is active
        # when Re_x_star > re_tri (before transition weighting).
        # re_x_over_re_tri > 1 means Re_x > Re_tri
        turb_branch_active = bool(np.isfinite(re_x_over_re_tri_val) and re_x_over_re_tri_val >= 1.0)
        
        # distance_from_transition: x_phys - x_phys_at_transition
        # Not directly available from last_fields. The transition x_phys depends on
        # where Re_x == Re_tri, which we don't know without scanning.
        # Mark as NA.
        distance_from_transition = float("nan")
        
        # p_ratio
        p_ratio = p_e / float(matched_p_w[i]) if (np.isfinite(p_e) and np.isfinite(matched_p_w[i]) and matched_p_w[i] > 0) else float("nan")
        
        per_point_rows.append({
            "case": label, "region": reg, "side": "windward",
            "x_m": float(x_w[i]), "x_over_c": float(xc_w[i]), "span_m": float(span_w[i]),
            "x_phys_used": x_phys,
            "Re_x_star_lam": re_x_star_lam, "Re_x_star_turb": re_x_star_turb,
            "re_tri": re_tri_val,
            "re_x_over_re_tri": re_x_over_re_tri_val,
            "w_tr": w_tr_val,
            "q_lam": q_lam, "q_turb": q_turb,
            "q_LF": q_LF, "q_Fluent": q_Fluent, "q_ratio": q_ratio,
            "p_e": p_e, "p_ratio": p_ratio,
            "h_r_lam_minus_h_w": h_r_lam_minus_h_w,
            "h_r_turb_minus_h_w": h_r_turb_minus_h_w,
            "rho_star_lam_over_rho_e": rho_star_lam_over_rho_e,
            "mu_star_lam_over_mu_e": mu_star_lam_over_mu_e,
            "rho_star_turb_over_rho_e": rho_star_turb_over_rho_e,
            "mu_star_turb_over_mu_e": mu_star_turb_over_mu_e,
            "q_turb_over_q_lam": q_turb_over_q_lam,
            "turb_branch_active": int(turb_branch_active),
            "distance_from_transition": distance_from_transition,
        })
    
    return per_point_rows


def build_region_summary(per_point_rows):
    """Build region summary from per-point data."""
    regions_order = ["cap_mask", "true_nose_cap", "leading_edge_near", "windward_body", "aft_body"]
    cases = sorted(set(r["case"] for r in per_point_rows))
    rows = []
    
    for case_name in cases:
        case_rows = [r for r in per_point_rows if r["case"] == case_name]
        for rname in regions_order:
            m = [r for r in case_rows if r["region"] == rname]
            if not m:
                continue
            n = len(m)
            
            q_ratio_vals = np.array([r["q_ratio"] for r in m if np.isfinite(r["q_ratio"])])
            q_turb_vals = np.array([r["q_turb"] for r in m if np.isfinite(r["q_turb"])])
            q_lam_vals = np.array([r["q_lam"] for r in m if np.isfinite(r["q_lam"])])
            q_turb_over_q_lam_vals = np.array([r["q_turb_over_q_lam"] for r in m if np.isfinite(r["q_turb_over_q_lam"])])
            h_r_turb_minus_h_w = np.array([r["h_r_turb_minus_h_w"] for r in m if np.isfinite(r["h_r_turb_minus_h_w"])])
            h_r_lam_minus_h_w = np.array([r["h_r_lam_minus_h_w"] for r in m if np.isfinite(r["h_r_lam_minus_h_w"])])
            rho_star_turb_over_rho_e = np.array([r["rho_star_turb_over_rho_e"] for r in m if np.isfinite(r["rho_star_turb_over_rho_e"])])
            mu_star_turb_over_mu_e = np.array([r["mu_star_turb_over_mu_e"] for r in m if np.isfinite(r["mu_star_turb_over_mu_e"])])
            
            turb_active_count = sum(1 for r in m if r["turb_branch_active"])
            w_tr_vals = np.array([r["w_tr"] for r in m if np.isfinite(r["w_tr"])])
            turb_fraction = float(np.nanmean(w_tr_vals >= 0.5)) if len(w_tr_vals) > 0 else float("nan")
            
            rows.append({
                "case": case_name, "region": rname, "side": "windward",
                "n_aligned": n,
                "q_ratio_mean": float(np.nanmean(q_ratio_vals)) if len(q_ratio_vals) > 0 else float("nan"),
                "q_turb_mean": float(np.nanmean(q_turb_vals)) if len(q_turb_vals) > 0 else float("nan"),
                "q_lam_mean": float(np.nanmean(q_lam_vals)) if len(q_lam_vals) > 0 else float("nan"),
                "q_turb_over_q_lam_mean": float(np.nanmean(q_turb_over_q_lam_vals)) if len(q_turb_over_q_lam_vals) > 0 else float("nan"),
                "h_r_turb_minus_h_w_mean": float(np.nanmean(h_r_turb_minus_h_w)) if len(h_r_turb_minus_h_w) > 0 else float("nan"),
                "h_r_lam_minus_h_w_mean": float(np.nanmean(h_r_lam_minus_h_w)) if len(h_r_lam_minus_h_w) > 0 else float("nan"),
                "rho_star_turb_over_rho_e_mean": float(np.nanmean(rho_star_turb_over_rho_e)) if len(rho_star_turb_over_rho_e) > 0 else float("nan"),
                "mu_star_turb_over_mu_e_mean": float(np.nanmean(mu_star_turb_over_mu_e)) if len(mu_star_turb_over_mu_e) > 0 else float("nan"),
                "turb_fraction": turb_fraction,
                "turb_branch_active_count": turb_active_count,
            })
    return rows


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    
    cases = [
        ("ma6_a5_h30km", FLUENT_DIR / "ma6_alpha5_h30km.csv", 6.0, 5.0, 30000),
        ("ma8_a5_h30km", FLUENT_DIR / "ma8_alpha5_h30km.csv", 8.0, 5.0, 30000),
    ]
    
    all_per_point = []
    all_region_summary = []
    
    for label, fc, mach, alpha, h_m in cases:
        print(f"\nProcessing: {label}")
        pp = run_and_audit(label, fc, mach, alpha, h_m)
        all_per_point.extend(pp)
        print(f"  {len(pp)} aligned points")
    
    # Write per-point CSV
    point_keys = [
        "case", "region", "side", "x_m", "x_over_c", "span_m",
        "x_phys_used",
        "Re_x_star_lam", "Re_x_star_turb",
        "re_tri", "re_x_over_re_tri", "w_tr",
        "q_lam", "q_turb", "q_LF", "q_Fluent", "q_ratio",
        "p_e", "p_ratio",
        "h_r_lam_minus_h_w", "h_r_turb_minus_h_w",
        "rho_star_lam_over_rho_e", "mu_star_lam_over_mu_e",
        "rho_star_turb_over_rho_e", "mu_star_turb_over_mu_e",
        "q_turb_over_q_lam",
        "turb_branch_active",
        "distance_from_transition",
    ]
    pp_path = OUT_DIR / "qturb_input_points.csv"
    with open(pp_path, "w", newline="", encoding="utf-8") as f:
        wc = csv.DictWriter(f, fieldnames=point_keys, extrasaction="ignore")
        wc.writeheader()
        for row in all_per_point:
            out = {k: row.get(k, float("nan")) for k in point_keys}
            wc.writerow(out)
    print(f"\nWrote: {pp_path} ({len(all_per_point)} rows)")
    
    # Build and write region summary
    region_rows = build_region_summary(all_per_point)
    rs_keys = [
        "case", "region", "side", "n_aligned",
        "q_ratio_mean", "q_turb_mean", "q_lam_mean",
        "q_turb_over_q_lam_mean",
        "h_r_turb_minus_h_w_mean", "h_r_lam_minus_h_w_mean",
        "rho_star_turb_over_rho_e_mean", "mu_star_turb_over_mu_e_mean",
        "turb_fraction", "turb_branch_active_count",
    ]
    rs_path = OUT_DIR / "qturb_input_region_summary.csv"
    with open(rs_path, "w", newline="", encoding="utf-8") as f:
        wc = csv.DictWriter(f, fieldnames=rs_keys, extrasaction="ignore")
        wc.writeheader()
        for row in region_rows:
            out = {k: row.get(k, float("nan")) for k in rs_keys}
            wc.writerow(out)
    print(f"Wrote: {rs_path} ({len(region_rows)} rows)")
    
    # Print region summary
    print("\nRegion summary:")
    for r in region_rows:
        print(f"  {r['case']:20s} {r['region']:20s} n={r['n_aligned']:4d} "
              f"q_ratio_mean={r.get('q_ratio_mean', float('nan')):.4f} "
              f"q_turb_mean={r.get('q_turb_mean', float('nan')):.2f} "
              f"q_turb_over_q_lam={r.get('q_turb_over_q_lam_mean', float('nan')):.2f} "
              f"turb_frac={r.get('turb_fraction', float('nan')):.3f} "
              f"turb_active={r.get('turb_branch_active_count', 0)}")


if __name__ == "__main__":
    main()
