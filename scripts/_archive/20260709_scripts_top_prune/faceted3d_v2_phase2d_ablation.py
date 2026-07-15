#!/usr/bin/env python3
"""Phase 2D windward q-chain ablation: A(C D E G).

Per the task order in docs/faceted3d_v2_phase2d_ds_ablation_task_order_zh.md.

Arms:
  A - baseline (all defaults, Cp=newtonian_like A0.38 n1.15, weighting=step, x_length=streamline)
  C - intermittency-only (transition.weighting = smoothstep/logistic)
  D - x_phys-only (faceted3d.x_length_mode = local/global)
  E - q_turb-input audit (read-only diagnostic: swaps q_lam/q_turb in final q blending)
  G - negative-control (windward.q_scale_lam/turb fitted, temporary only)

All arms are opt-in via YAML; default = baseline.
Switch off an arm and it reverts to baseline.
"""

from __future__ import annotations

import csv, math, sys, warnings, json
from pathlib import Path
from datetime import datetime
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
from ref_enthalpy_method.heatflux.windward import windward_ref_enthalpy_branches

# --- Paths ---
BASE = Path(__file__).resolve().parent.parent
VEHICLE_TEMPLATE = BASE / "specs/vehicles/htv2_faceted3d_0629.yaml"
CASE_TEMPLATE = BASE / "specs/cases/template_faceted3d_fixedTw300.yaml"
SAMPLING = BASE / "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml"
FLUENT_DIR = BASE / "fluent_export"
OUT_DIR = BASE / "runs/faceted3d_v2_phase2d_ablation"
DOCS_DIR = BASE / "docs"
FIG_DIR = OUT_DIR / "figures"
REPORT_DIR = OUT_DIR / "reports"

NEWTONIAN_A = 0.38
NEWTONIAN_N = 1.15
Rn = 0.03
r_cap = 0.03
chord_min_m = 0.02
C_ROOT_M = 3.6  # from vehicle spec

# --- ma8_a10 protection ---
FORBIDDEN_CASE_IDS = ("ma8_a10",)


# --- Atmosphere helpers ---
def _ussa(h_m):
    R = 287.0; g0 = 9.80665
    if h_m <= 11000: T = 288.15 - 0.0065 * h_m; P = 101325 * (T / 288.15) ** (-g0 / (R * -0.0065))
    elif h_m <= 20000: T = 216.65; P = 22632.1 * np.exp(-g0 / (R * T) * (h_m - 11000))
    else: T = 216.65 + 0.001 * (h_m - 20000); P = 5474.89 * (T / 216.65) ** (-g0 / (R * 0.001))
    return float(P), float(P / (R * T)), float(T)

def _freestream_v(mach, T_inf):
    return mach * math.sqrt(1.4 * 287.0 * T_inf)


# --- Fluent readers ---
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

def _read_fluent_leeward(path):
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
                if z <= 0: continue
                span = math.sqrt(y*y + z*z)
                p = float(row[pi]); q = -float(row[qi])
                rows.append([x, span, z, p, q, y])
            except: continue
    return np.array(rows, dtype=float)


# --- Region assignment (spec 3.3 check order) ---
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


# --- Nearest-neighbor alignment ---
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


# --- Trim helper ---
def _trim(arr, ref_len):
    arr = np.asarray(arr, dtype=float).ravel()
    if len(arr) >= ref_len: return arr[:ref_len]
    out = np.full(ref_len, np.nan); out[:len(arr)] = arr; return out


# --- Ablation arm definitions ---
# Each arm returns a dict of "override_key": override_value
# The runner will apply these as YAML modifications.

def arm_A_baseline():
    """A: baseline — all defaults, no override."""
    return {}

def arm_C_intermittency(weighting="smoothstep"):
    """C: intermittency-only — change transition.weighting from step to smoothstep/logistic."""
    return {"transition.weighting": weighting}

def arm_D_xphys(mode="local"):
    """D: x_phys-only — change x_length_mode from streamline to local/global."""
    return {"faceted3d.x_length_mode": mode}

def arm_E_qturb_audit():
    """E: q_turb-input audit — swap blending: test q = q_lam (w_tr=0) or q = q_turb (w_tr=1).
    
    This is read-only: we recompute q_blended = (1-w_tr)*q_lam + w_tr*q_turb
    but also output diagnostic rows showing what would happen if we ONLY used
    q_lam or ONLY used q_turb. No changes to solver config.
    """
    return {}

def arm_G_negative_control(q_scale_lam=0.8, q_scale_turb=1.2):
    """G: negative-control — apply temporary q_scale multipliers.
    
    These are NOT written to any default config. Only used in this sandbox run.
    """
    return {"q_scale_lam": q_scale_lam, "q_scale_turb": q_scale_turb}


# --- Solver runner with config overrides ---
def _validate_case_id(label):
    """Reject any case containing forbidden IDs."""
    for fb in FORBIDDEN_CASE_IDS:
        if fb in label.lower():
            raise ValueError(f"ma8_a10 PROTECTION: case label {label!r} contains forbidden ID {fb!r}. Aborting.")


def _run_solver(label, mach, alpha, h_m, arm_name, arm_overrides):
    """Run solver with given arm overrides applied to the vehicle/case YAML.
    
    arm_overrides: dict of dotted keys to values.
    Supported keys:
      - "transition.weighting" -> case yaml lf_qw_model.transition.weighting
      - "faceted3d.x_length_mode" -> vehicle yaml faceted3d.x_length_mode
      - "q_scale_lam", "q_scale_turb" -> passed to post-processing, NOT to YAML
    """
    import yaml as _yaml
    
    _validate_case_id(label)
    
    # Load and modify vehicle
    veh = _yaml.safe_load(VEHICLE_TEMPLATE.read_text(encoding="utf-8"))
    f3 = veh["vehicle_spec"]["faceted3d"]
    f3["cp_model"] = "newtonian_like"
    f3["cp_newtonian_A"] = NEWTONIAN_A
    f3["cp_newtonian_n"] = NEWTONIAN_N
    
    x_length_mode = arm_overrides.get("faceted3d.x_length_mode", None)
    if x_length_mode is not None:
        f3["x_length_mode"] = x_length_mode
    
    vp = OUT_DIR / f"veh_{arm_name}_{label}.yaml"
    with open(vp, "w", encoding="utf-8") as f:
        _yaml.dump(veh, f, default_flow_style=False)
    
    # Load and modify case
    case_data = _yaml.safe_load(CASE_TEMPLATE.read_text(encoding="utf-8"))
    tr = case_data["case_spec"]["lf_qw_model"]["transition"]
    tr["weighting"] = "step"  # baseline default
    
    tr_weighting = arm_overrides.get("transition.weighting", None)
    if tr_weighting is not None:
        tr["weighting"] = tr_weighting
    
    cp = OUT_DIR / f"case_{arm_name}_{label}.yaml"
    with open(cp, "w", encoding="utf-8") as f:
        _yaml.dump(case_data, f, default_flow_style=False)
    
    solver = WingLowFidelitySolverFaceted3D(
        vehicle_config=str(vp), case_config=str(cp),
        sampling_config=str(SAMPLING), run_dir=str(OUT_DIR / f"{arm_name}_{label}"),
    )
    solver.compute_snapshot(mach=mach, alpha=alpha)
    fields = dict(solver.last_fields or {})
    
    # Extract q_scale overrides from arm_overrides (not stored in YAML)
    q_scale_lam_override = arm_overrides.get("q_scale_lam", None)
    q_scale_turb_override = arm_overrides.get("q_scale_turb", None)
    
    return fields, solver, q_scale_lam_override, q_scale_turb_override


# --- Per-point ablation table builder ---
def build_per_point_rows(label, arm_name, region_labels,
                         x_w, span_w, xc_w, yb_w,
                         q_w, q_lam_w, q_turb_w, p_e_w, cp_w,
                         mask_w, w_tr,
                         h_r_lam_w, h_r_turb_w, h_w_all,
                         matched_q_w, matched_p_w,
                         q_scale_lam, q_scale_turb,
                         p_inf, q_inf):
    """Build per-point rows for ablation_points.csv.
    
    Includes both original q_w and debiased audit columns.
    If q_scale_lam/q_scale_turb is not None, q_lam/q_turb are rescaled.
    """
    rows = []
    n = len(x_w)
    for i in range(n):
        if not (mask_w[i] and np.isfinite(q_w[i]) and np.isfinite(matched_q_w[i]) and matched_q_w[i] > 0):
            continue
        reg = region_labels[i] if i < len(region_labels) else "unknown"
        # x_phys: this is the x_eff_over_c * chord used internally
        x_phys_used = float(xc_w[i]) * C_ROOT_M  # approximate; real x_phys from cache
        # For accurate x_phys, we'd need cache.x_phys per point — approximate from x_w,span_w
        h_r_lam = float(h_r_lam_w[i]) if np.isfinite(h_r_lam_w[i]) else float("nan")
        h_r_turb = float(h_r_turb_w[i]) if np.isfinite(h_r_turb_w[i]) else float("nan")
        h_w = float(h_w_all[i]) if np.isfinite(h_w_all[i]) else float("nan")
        h_r_lam_minus_h_w = h_r_lam - h_w if (np.isfinite(h_r_lam) and np.isfinite(h_w)) else float("nan")
        h_r_turb_minus_h_w = h_r_turb - h_w if (np.isfinite(h_r_turb) and np.isfinite(h_w)) else float("nan")
        
        # q_LF as reported by solver (q_w)
        q_LF = float(q_w[i])
        q_Fluent = float(matched_q_w[i])
        q_ratio = q_LF / q_Fluent
        
        p_e = float(p_e_w[i]) if np.isfinite(p_e_w[i]) else float("nan")
        p_wall_fluent = float(matched_p_w[i]) if matched_p_w is not None and np.isfinite(matched_p_w[i]) else float("nan")
        p_ratio = p_e / p_wall_fluent if (np.isfinite(p_e) and np.isfinite(p_wall_fluent) and p_wall_fluent > 0) else float("nan")
        
        # Cp: Cp_LF from solver, Cp_Fluent = (p_wall - p_inf)/q_inf
        cp_lf = float(cp_w[i]) if np.isfinite(cp_w[i]) else float("nan")
        cp_fl = (p_wall_fluent - p_inf) / q_inf if (np.isfinite(p_wall_fluent) and q_inf > 0) else float("nan")
        cp_ratio = cp_lf / cp_fl if (np.isfinite(cp_lf) and np.isfinite(cp_fl) and cp_fl > 1e-10) else float("nan")
        
        # Reynolds numbers
        re_x_star_lam = float("nan")  # not stored in fields; computed internally
        re_x_star_turb = float("nan")
        re_tri = float("nan")
        
        rows.append({
            "case": label, "arm": arm_name, "region": reg, "side": "windward",
            "x_m": float(x_w[i]), "x_over_c": float(xc_w[i]), "span_m": float(span_w[i]),
            "x_phys_used": x_phys_used,
            "re_x_star_lam": re_x_star_lam, "re_x_star_turb": re_x_star_turb,
            "re_tri": re_tri, "re_x_over_re_tri": float("nan"), "w_tr": float(w_tr[i]),
            "q_lam": float(q_lam_w[i]) if np.isfinite(q_lam_w[i]) else float("nan"),
            "q_turb": float(q_turb_w[i]) if np.isfinite(q_turb_w[i]) else float("nan"),
            "q_LF": q_LF, "q_Fluent": q_Fluent, "q_ratio": q_ratio,
            "p_e": p_e, "p_wall_fluent": p_wall_fluent, "p_ratio": p_ratio,
            "Cp_LF": cp_lf, "Cp_ratio": cp_ratio,
            "h_r_lam_minus_h_w": h_r_lam_minus_h_w,
            "h_r_turb_minus_h_w": h_r_turb_minus_h_w,
        })
    return rows


# --- Region stats builder ---
def build_region_summary(label, arm_name, region_labels, per_point_rows,
                         x_w, span_w, mask_w, q_w, matched_q_w, w_tr, q_lam_w, q_turb_w,
                         p_e_w, matched_p_w, p_inf, q_inf):
    """Build region summary rows from per-point data."""
    w_region_names = ["cap_mask", "true_nose_cap", "leading_edge_near", "windward_body", "aft_body"]
    
    q_ratio_arr = np.full(len(x_w), np.nan)
    valid_arr = np.isfinite(q_w) & np.isfinite(matched_q_w) & (matched_q_w > 0)
    q_ratio_arr[valid_arr] = q_w[valid_arr] / matched_q_w[valid_arr]
    
    p_ratio_arr = np.full(len(x_w), np.nan)
    if matched_p_w is not None:
        pvalid = np.isfinite(p_e_w) & np.isfinite(matched_p_w) & (matched_p_w > 0)
        p_ratio_arr[pvalid] = p_e_w[pvalid] / matched_p_w[pvalid]
    
    rows = []
    for rname in w_region_names:
        m = region_labels == rname
        n_aligned = int(np.sum(m & valid_arr))
        if n_aligned == 0:
            rows.append({
                "case": label, "arm": arm_name, "region": rname, "side": "windward",
                "n_aligned": 0, "lam_count": 0, "turb_count": 0, "turb_fraction": float("nan"),
                "q_ratio_mean": float("nan"), "q_ratio_median": float("nan"),
                "q_ratio_std": float("nan"), "q_ratio_iqr": float("nan"),
                "lam_q_ratio_mean": float("nan"), "turb_q_ratio_mean": float("nan"),
                "p_ratio_mean": float("nan"), "spearman_x_qratio": float("nan"),
            })
            continue
        
        qr_vals = q_ratio_arr[m & valid_arr]
        qr_mean = float(np.nanmean(qr_vals))
        qr_med = float(np.nanmedian(qr_vals))
        qr_std = float(np.nanstd(qr_vals))
        qr_iqr = float(np.subtract(*np.percentile(qr_vals, [75, 25]))) if len(qr_vals) >= 2 else 0.0
        
        # Laminar/turbulent categories
        w_tr_vals = w_tr[m]
        lam_m = (w_tr_vals < 0.5)
        turb_m = (w_tr_vals >= 0.5)
        lam_count = int(np.sum(lam_m))
        turb_count = int(np.sum(turb_m))
        turb_frac = turb_count / max(lam_count + turb_count, 1)
        
        # For lam_qr / turb_qr, filter q_ratio_arr by both region membership, valid alignment, AND w_tr threshold
        lam_valid_mask = m & valid_arr & (w_tr < 0.5)
        turb_valid_mask = m & valid_arr & (w_tr >= 0.5)
        lam_qr = float(np.nanmean(q_ratio_arr[lam_valid_mask])) if np.sum(lam_valid_mask) > 0 else float("nan")
        turb_qr = float(np.nanmean(q_ratio_arr[turb_valid_mask])) if np.sum(turb_valid_mask) > 0 else float("nan")
        
        # p_ratio
        pr_vals = p_ratio_arr[m & pvalid] if matched_p_w is not None else np.array([np.nan])
        pr_mean = float(np.nanmean(pr_vals)) if np.any(np.isfinite(pr_vals)) else float("nan")
        
        # Spearman correlation between x_m and q_ratio
        x_vals = x_w[m & valid_arr]
        if len(x_vals) >= 5:
            from scipy.stats import spearmanr
            sr, _ = spearmanr(x_vals, qr_vals)
            sr = float(sr) if np.isfinite(sr) else float("nan")
        else:
            sr = float("nan")
        
        rows.append({
            "case": label, "arm": arm_name, "region": rname, "side": "windward",
            "n_aligned": n_aligned,
            "lam_count": lam_count, "turb_count": turb_count,
            "turb_fraction": turb_frac,
            "q_ratio_mean": qr_mean, "q_ratio_median": qr_med,
            "q_ratio_std": qr_std, "q_ratio_iqr": qr_iqr,
            "lam_q_ratio_mean": lam_qr, "turb_q_ratio_mean": turb_qr,
            "p_ratio_mean": pr_mean, "spearman_x_qratio": sr,
        })
    
    # Leeward (single region)
    return rows


# --- Process one arm+case ---
def process_arm_case(label, fluent_csv, mach, alpha, h_m, arm_name, arm_overrides):
    """Run solver with arm_overrides, produce per-point and region stats."""
    
    p_inf, rho_inf, T_inf = _ussa(h_m)
    v_inf = _freestream_v(mach, T_inf)
    q_inf = 0.5 * rho_inf * v_inf**2
    
    fields, solver, q_scl_lam, q_scl_turb = _run_solver(
        label, mach, alpha, h_m, arm_name, arm_overrides
    )
    
    # Solver windward fields
    x_w = _trim(fields.get("x_w_m", np.array([])), 4000)
    span_w = _trim(fields.get("span_w_m", np.array([])), 4000)
    xc_w = _trim(fields.get("xc_w", np.array([])), 4000)
    yb_w = _trim(fields.get("yb_w", np.array([])), 4000)
    q_w = _trim(fields.get("q_w", np.array([])), 4000)
    p_e_w = _trim(fields.get("p_e_w", np.array([])), 4000)
    cp_w = _trim(fields.get("cp_w", np.array([])), 4000)
    w_tr = _trim(fields.get("w_tr", np.array([])), 4000)
    mask_w = _trim(fields.get("mask_w", np.array([])), 4000).astype(bool)
    q_lam_w = _trim(fields.get("q_lam_w", np.array([])), 4000)
    q_turb_w = _trim(fields.get("q_turb_w", np.array([])), 4000)
    h_r_lam_w = _trim(fields.get("h_r_lam_w", np.array([])), 4000)
    h_r_turb_w = _trim(fields.get("h_r_turb_w", np.array([])), 4000)
    
    # For h_w we need Tw_w
    Tw_w = _trim(fields.get("Tw_w", np.array([])), 4000)
    h_w_all = np.full_like(Tw_w, float("nan"))
    for i in range(len(Tw_w)):
        if np.isfinite(Tw_w[i]):
            h_w_all[i] = float(solver.gas.h_from_T(float(Tw_w[i])))
    
    # For E arm: reblend q_w from q_lam and q_turb with different w_tr scenarios
    # But also keep original q_w for baseline comparison
    if arm_name.startswith("E_"):
        # For E audit, we keep q_w as-is but add diagnostic columns in report.
        # No changes to solver config.
        pass
    
    # For G arm: apply q_scale post-hoc to q_lam_w / q_turb_w for reblended q
    # NOTE: q_w comes from solver's internal w_tr blending of q_lam_w, q_turb_w
    # which uses the *original* q_scale=1.0. For negative control we need to
    # reblend with scaled q_lam/q_turb.
    if arm_name.startswith("G_") and (q_scl_lam is not None or q_scl_turb is not None):
        q_scl_lam = q_scl_lam if q_scl_lam is not None else 1.0
        q_scl_turb = q_scl_turb if q_scl_turb is not None else 1.0
        # Reblend: q_w_blended = (1-w_tr)*q_lam*q_scl_lam + w_tr*q_turb*q_scl_turb
        q_lam_scaled = q_lam_w * q_scl_lam
        q_turb_scaled = q_turb_w * q_scl_turb
        w_tr_filled = np.where(np.isfinite(w_tr), w_tr, 0.0)
        q_w_new = (1.0 - w_tr_filled) * q_lam_scaled + w_tr_filled * q_turb_scaled
        q_w = _trim(q_w_new, 4000)
        # Also store the scaled q_lam/q_turb back for reporting
        q_lam_w = _trim(q_lam_scaled, 4000)
        q_turb_w = _trim(q_turb_scaled, 4000)
    
    # Assign regions BEFORE trimming (w_regions per original point set)
    w_regions = _assign_region_windward(x_w, span_w, xc_w, mask_w)
    
    # Trim to common length
    ref_w = min(len(x_w), len(span_w), len(xc_w), len(q_w), len(p_e_w),
                len(cp_w), len(mask_w), len(w_tr), len(q_lam_w), len(q_turb_w),
                len(w_regions))
    x_w = x_w[:ref_w]; span_w = span_w[:ref_w]; xc_w = xc_w[:ref_w]
    yb_w = yb_w[:ref_w]; q_w = q_w[:ref_w]; p_e_w = p_e_w[:ref_w]
    cp_w = cp_w[:ref_w]; w_tr = w_tr[:ref_w]; mask_w = mask_w[:ref_w].astype(bool)
    q_lam_w = q_lam_w[:ref_w]; q_turb_w = q_turb_w[:ref_w]
    h_r_lam_w = h_r_lam_w[:ref_w]; h_r_turb_w = h_r_turb_w[:ref_w]
    h_w_all = h_w_all[:ref_w]
    w_regions = w_regions[:ref_w]
    
    # Read Fluent
    flt_w = _read_fluent_windward(fluent_csv)
    flt_w_x = flt_w[:, 0]; flt_w_span = flt_w[:, 1]; flt_w_q = flt_w[:, 4]; flt_w_p = flt_w[:, 3]
    
    # Align
    matched_q_w, matched_p_w = _nearest_match(x_w, span_w, flt_w_x, flt_w_span, flt_w_q, flt_w_p)
    
    # Build per-point rows
    per_point = build_per_point_rows(
        label, arm_name, w_regions,
        x_w, span_w, xc_w, yb_w,
        q_w, q_lam_w, q_turb_w, p_e_w, cp_w,
        mask_w, w_tr,
        h_r_lam_w, h_r_turb_w, h_w_all,
        matched_q_w, matched_p_w,
        q_scl_lam, q_scl_turb,
        p_inf, q_inf,
    )
    
    # Build region summary
    region_summary = build_region_summary(
        label, arm_name, w_regions, per_point,
        x_w, span_w, mask_w, q_w, matched_q_w, w_tr, q_lam_w, q_turb_w,
        p_e_w, matched_p_w, p_inf, q_inf,
    )
    
    # Diagnostic: laminar-only and turbulent-only q_ratio means (for E arm)
    lam_only_qr_mean = float("nan")
    turb_only_qr_mean = float("nan")
    if arm_name.startswith("E_"):
        q_lam_only = q_lam_w.copy()
        q_turb_only = q_turb_w.copy()
        # laminar-only: assume w_tr=0 everywhere
        w_tr_lam = np.zeros_like(w_tr)
        mask_lam = mask_w & np.isfinite(q_lam_only) & np.isfinite(matched_q_w) & (matched_q_w > 0)
        if np.any(mask_lam):
            lam_only_qr_mean = float(np.nanmean(q_lam_only[mask_lam] / matched_q_w[mask_lam]))
        # turbulent-only: assume w_tr=1 everywhere
        mask_turb = mask_w & np.isfinite(q_turb_only) & np.isfinite(matched_q_w) & (matched_q_w > 0)
        if np.any(mask_turb):
            turb_only_qr_mean = float(np.nanmean(q_turb_only[mask_turb] / matched_q_w[mask_turb]))
    
    return {
        "per_point": per_point,
        "region_summary": region_summary,
        "lam_only_qr_mean": lam_only_qr_mean,
        "turb_only_qr_mean": turb_only_qr_mean,
    }


# --- Figures ---
def _plot_qratio_vs_x(per_point_data, save_path, label, arm_name):
    """q_ratio vs x_m, colored by region."""
    if not HAS_MPL or not per_point_data:
        return
    region_colors = {
        "cap_mask": "red", "true_nose_cap": "orange",
        "leading_edge_near": "gold", "windward_body": "green",
        "aft_body": "blue",
    }
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for rname, color in region_colors.items():
        pts = [p for p in per_point_data if p["region"] == rname and np.isfinite(p["q_ratio"])]
        if not pts:
            continue
        x = [p["x_m"] for p in pts]
        qr = [p["q_ratio"] for p in pts]
        ax.scatter(x, qr, c=color, s=3, alpha=0.5, label=rname, edgecolors="none")
    ax.axhline(1.0, color="k", ls="--", lw=0.8)
    ax.set_xlabel("x (m)"); ax.set_ylabel("q_ratio (LF/Fluent)")
    ax.set_title(f"{arm_name} | {label}")
    ax.legend(markerscale=4, fontsize=7)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  saved: {save_path}")

def _plot_qratio_vs_wtr(per_point_data, save_path, label, arm_name):
    """q_ratio vs w_tr, colored by region."""
    if not HAS_MPL or not per_point_data:
        return
    region_colors = {
        "cap_mask": "red", "true_nose_cap": "orange",
        "leading_edge_near": "gold", "windward_body": "green",
        "aft_body": "blue",
    }
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for rname, color in region_colors.items():
        pts = [p for p in per_point_data if p["region"] == rname
               and np.isfinite(p["q_ratio"]) and np.isfinite(p["w_tr"])]
        if not pts:
            continue
        w = [p["w_tr"] for p in pts]
        qr = [p["q_ratio"] for p in pts]
        ax.scatter(w, qr, c=color, s=3, alpha=0.5, label=rname, edgecolors="none")
    ax.axhline(1.0, color="k", ls="--", lw=0.8)
    ax.set_xlabel("w_tr"); ax.set_ylabel("q_ratio (LF/Fluent)")
    ax.set_title(f"{arm_name} | {label}")
    ax.legend(markerscale=4, fontsize=7)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  saved: {save_path}")

def _plot_qratio_box(per_point_data, save_path, label, arm_name):
    """Per-region q_ratio boxplot."""
    if not HAS_MPL or not per_point_data:
        return
    regions_order = ["cap_mask", "true_nose_cap", "leading_edge_near", "windward_body", "aft_body"]
    all_data = []
    region_labels = []
    for rname in regions_order:
        vals = [p["q_ratio"] for p in per_point_data
                if p["region"] == rname and np.isfinite(p["q_ratio"])]
        if len(vals) > 0:
            all_data.append(vals)
            region_labels.append(rname)
    if not all_data:
        return
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bp = ax.boxplot(all_data, labels=region_labels, showfliers=False, patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_alpha(0.7)
    ax.axhline(1.0, color="k", ls="--", lw=0.8)
    ax.set_ylabel("q_ratio (LF/Fluent)")
    ax.set_title(f"{arm_name} | {label}")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  saved: {save_path}")

def _plot_qratio_mean_by_arm(all_region_data, save_path, case_name):
    """Bar chart: q_ratio_mean per region, grouped by arm."""
    if not HAS_MPL:
        return
    regions_order = ["cap_mask", "true_nose_cap", "leading_edge_near", "windward_body", "aft_body"]
    arms = sorted(set(r["arm"] for r in all_region_data if r["case"] == case_name))
    if not arms:
        return
    x = np.arange(len(regions_order))
    w = 0.8 / max(len(arms), 1)
    fig, ax = plt.subplots(figsize=(10, 5))
    for i, arm in enumerate(arms):
        vals = []
        for rname in regions_order:
            matches = [r for r in all_region_data
                       if r["case"] == case_name and r["arm"] == arm and r["region"] == rname
                       and np.isfinite(r["q_ratio_mean"])]
            vals.append(matches[0]["q_ratio_mean"] if matches else float("nan"))
        ax.bar(x + (i - len(arms)/2 + 0.5)*w, vals, w, label=arm, alpha=0.85)
    ax.axhline(1.0, color="k", ls="--", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(regions_order, rotation=30, ha="right")
    ax.set_ylabel("q_ratio_mean (LF/Fluent)")
    ax.set_title(f"Per-arm q_ratio_mean: {case_name}")
    ax.legend(fontsize=7); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  saved: {save_path}")

def _plot_lam_turb_qratio_by_arm(all_region_data, save_path, case_name):
    """Line chart: lam_q_ratio_mean and turb_q_ratio_mean per region across arms."""
    if not HAS_MPL:
        return
    regions_order = ["cap_mask", "true_nose_cap", "leading_edge_near", "windward_body", "aft_body"]
    arms = sorted(set(r["arm"] for r in all_region_data if r["case"] == case_name))
    if not arms:
        return
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    for idx, (metric, ylabel) in enumerate([
        ("lam_q_ratio_mean", "Laminar q_ratio_mean"),
        ("turb_q_ratio_mean", "Turbulent q_ratio_mean"),
    ]):
        ax = axes[idx]
        for rname in regions_order:
            vals = []
            for arm in arms:
                matches = [r for r in all_region_data
                           if r["case"] == case_name and r["arm"] == arm
                           and r["region"] == rname and np.isfinite(r.get(metric, float("nan")))]
                vals.append(matches[0][metric] if matches else float("nan"))
            ax.plot(range(len(arms)), vals, marker="o", label=rname, linewidth=1.5)
        ax.axhline(1.0, color="k", ls="--", lw=0.8)
        ax.set_xticks(range(len(arms))); ax.set_xticklabels(arms, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel(ylabel)
        ax.set_title(f"{ylabel} | {case_name}")
        ax.legend(fontsize=7); ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  saved: {save_path}")


# --- CSV writers ---
def write_ablation_points(all_per_point, out_dir):
    path = out_dir / "ablation_points.csv"
    if not all_per_point:
        return
    keys = ["case", "arm", "region", "side", "x_m", "x_over_c", "span_m",
            "x_phys_used", "re_x_star_lam", "re_x_star_turb", "re_tri",
            "re_x_over_re_tri", "w_tr",
            "q_lam", "q_turb", "q_LF", "q_Fluent", "q_ratio",
            "p_e", "p_wall_fluent", "p_ratio", "Cp_LF", "Cp_ratio",
            "h_r_lam_minus_h_w", "h_r_turb_minus_h_w"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        wc = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        wc.writeheader()
        for row in all_per_point:
            # Ensure all float fields are float
            out = {k: (float(row[k]) if isinstance(row[k], (np.floating,)) else row[k])
                   for k in keys if k in row}
            # Fill missing numeric keys with nan
            for k in keys:
                if k not in out:
                    out[k] = float("nan")
            wc.writerow(out)
    print(f"  Wrote: {path} ({len(all_per_point)} rows)")

def write_ablation_region_summary(all_region_data, out_dir):
    path = out_dir / "ablation_region_summary.csv"
    if not all_region_data:
        return
    keys = ["case", "arm", "region", "side", "n_aligned",
            "lam_count", "turb_count", "turb_fraction",
            "q_ratio_mean", "q_ratio_median", "q_ratio_std", "q_ratio_iqr",
            "lam_q_ratio_mean", "turb_q_ratio_mean",
            "p_ratio_mean", "spearman_x_qratio"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        wc = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        wc.writeheader()
        for row in all_region_data:
            out = {k: (float(row[k]) if isinstance(row[k], (np.floating,)) else row[k])
                   for k in keys if k in row}
            for k in keys:
                if k not in out:
                    out[k] = float("nan")
            wc.writerow(out)
    print(f"  Wrote: {path} ({len(all_region_data)} rows)")


# --- Markdown report writers ---
def write_arm_report(arm_name, arm_desc, overrides_str, all_per_point_arm,
                     all_region_data_arm, fig_paths, out_dir):
    """Write per-arm markdown report."""
    report_dir = out_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"ablation_{arm_name}.md"
    
    # Filter data for this arm
    arm_pp = [p for p in all_per_point_arm if p["arm"] == arm_name]
    arm_rs = [r for r in all_region_data_arm if r["arm"] == arm_name]
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Ablation Report: {arm_name}\n\n")
        f.write(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"## Description\n\n{arm_desc}\n\n")
        f.write(f"## Overrides\n\n{overrides_str}\n\n")
        
        # Baseline consistency check for A arm
        if arm_name == "A_baseline":
            f.write("## Baseline Consistency Check\n\n")
            f.write("A-baseline numbers compared against Phase 2D diagnostics master table.\n\n")
            # This will be filled after cross-check
        
        f.write("## Region Summary\n\n")
        keys = ["case", "region", "n_aligned", "turb_fraction",
                "q_ratio_mean", "q_ratio_std", "q_ratio_iqr",
                "lam_q_ratio_mean", "turb_q_ratio_mean", "p_ratio_mean"]
        f.write("| " + " | ".join(keys) + " |\n")
        f.write("|" + "|".join(["---"]*len(keys)) + "|\n")
        for r in arm_rs:
            vals = []
            for k in keys:
                v = r.get(k, float("nan"))
                if isinstance(v, float) and np.isfinite(v):
                    vals.append(f"{v:.4f}")
                else:
                    vals.append("N/A")
            f.write("| " + " | ".join(vals) + " |\n")
        f.write("\n")
        
        f.write("## Figures\n\n")
        for fp in fig_paths:
            if arm_name in fp.name:
                f.write(f"- `{fp.name}`\n")
        f.write("\n")
        
        f.write("## Observations (evidence only, no physical conclusions)\n\n")
        
        # Check for anomalies
        for r in arm_rs:
            if np.isfinite(r.get("q_ratio_mean", float("nan"))):
                qrm = r["q_ratio_mean"]
                bias = "overestimate" if qrm > 1.05 else ("underestimate" if qrm < 0.95 else "neutral")
                f.write(f"- {r['case']} / {r['region']}: q_ratio_mean={qrm:.4f} ({bias}), "
                       f"std={r.get('q_ratio_std', float('nan')):.4f}, "
                       f"n_aligned={r.get('n_aligned', 0)}\n")
            # Check p_ratio anomaly
            pr = r.get("p_ratio_mean", float("nan"))
            if np.isfinite(pr) and abs(pr - 1.0) > 0.01:
                f.write(f"  - p_ratio_mean={pr:.4f} (deviation from 1.0 = {pr-1.0:+.4f})\n")
            # Check Spearman
            sr = r.get("spearman_x_qratio", float("nan"))
            if np.isfinite(sr) and abs(sr) > 0.5:
                f.write(f"  - spearman_x_qratio={sr:.4f} (strong x-trend in q_ratio)\n")
        
        f.write("\n---\n")
        f.write("*Evidence-only report. No physical conclusions or route changes.*\n")
    
    print(f"  Wrote: {path}")
    return path


# --- Main ---
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Case definitions (two active cases, ma8_a10 is frozen holdout)
    cases = [
        ("ma6_a5_h30km", FLUENT_DIR / "ma6_alpha5_h30km.csv", 6.0, 5.0, 30000),
        ("ma8_a5_h30km", FLUENT_DIR / "ma8_alpha5_h30km.csv", 8.0, 5.0, 30000),
    ]
    
    # Ablation arm definitions
    # A: baseline
    # C: intermittency-only (smoothstep)
    # D: x_phys-only (local)
    # E: q_turb-input audit (read-only)
    # G: negative-control (q_scale_lam=0.8, q_scale_turb=1.2)
    arms = [
        ("A_baseline", "Baseline (all defaults: step weighting, streamline x_length, q_scale=1)", arm_A_baseline()),
        ("C_smoothstep", "Intermittency-only: transition.weighting = smoothstep", arm_C_intermittency("smoothstep")),
        ("C_logistic", "Intermittency-only: transition.weighting = logistic", arm_C_intermittency("logistic")),
        ("D_local", "x_phys-only: x_length_mode = local", arm_D_xphys("local")),
        ("D_global", "x_phys-only: x_length_mode = global", arm_D_xphys("global")),
        ("E_qturb_audit", "q_turb-input audit (read-only diagnostic)", arm_E_qturb_audit()),
        ("G_qscale08_12", "Negative-control: q_scale_lam=0.8, q_scale_turb=1.2", arm_G_negative_control(0.8, 1.2)),
        ("G_qscale09_11", "Negative-control: q_scale_lam=0.9, q_scale_turb=1.1", arm_G_negative_control(0.9, 1.1)),
        ("G_qscale10_10", "Negative-control: q_scale_lam=1.0, q_scale_turb=1.0 (should match baseline)", arm_G_negative_control(1.0, 1.0)),
    ]
    
    all_per_point = []
    all_region_data = []
    all_results = {}
    fig_paths = []
    
    for arm_name, arm_desc, arm_overrides in arms:
        print(f"\n{'='*70}")
        print(f"ARM: {arm_name} — {arm_desc}")
        print(f"{'='*70}")
        
        for label, fc, mach, alpha, h_m in cases:
            print(f"\n  Processing: {label}")
            
            result = process_arm_case(label, fc, mach, alpha, h_m, arm_name, arm_overrides)
            all_results[(arm_name, label)] = result
            
            all_per_point.extend(result["per_point"])
            all_region_data.extend(result["region_summary"])
            
            # Generate per-case, per-arm figures
            arm_label_short = arm_name.replace(" ", "_")
            per_point_data = result["per_point"]
            
            f1 = FIG_DIR / f"{arm_label_short}_{label}_qratio_vs_x.png"
            _plot_qratio_vs_x(per_point_data, f1, label, arm_name)
            fig_paths.append(f1)
            
            f2 = FIG_DIR / f"{arm_label_short}_{label}_qratio_vs_wtr.png"
            _plot_qratio_vs_wtr(per_point_data, f2, label, arm_name)
            fig_paths.append(f2)
            
            f3 = FIG_DIR / f"{arm_label_short}_{label}_qratio_box.png"
            _plot_qratio_box(per_point_data, f3, label, arm_name)
            fig_paths.append(f3)
        
        # Write arm report
        write_arm_report(
            arm_name, arm_desc,
            f"```\n{json.dumps(arm_overrides, indent=2)}\n```",
            all_per_point, all_region_data,
            [fp for fp in fig_paths if arm_name.replace(" ","_") in fp.name],
            OUT_DIR,
        )
    
    # Cross-arm figures (per-case)
    for case_name, _, _, _, _ in cases:
        c_label = case_name.replace(" ", "_")
        
        f4 = FIG_DIR / f"qratio_mean_by_arm_region_{c_label}.png"
        _plot_qratio_mean_by_arm(all_region_data, f4, case_name)
        fig_paths.append(f4)
        
        f5 = FIG_DIR / f"lam_turb_qratio_by_arm_{c_label}.png"
        _plot_lam_turb_qratio_by_arm(all_region_data, f5, case_name)
        fig_paths.append(f5)
    
    # Write CSVs
    write_ablation_points(all_per_point, OUT_DIR)
    write_ablation_region_summary(all_region_data, OUT_DIR)
    
    # Baseline consistency check (A_baseline vs Phase 2D diagnostics CSV)
    print("\n" + "="*70)
    print("BASELINE CONSISTENCY CHECK (A_baseline vs Phase 2D master table)")
    print("="*70)
    diag_csv = BASE / "runs/faceted3d_v2_phase2d_diagnostics/phase2d_region_master_table.csv"
    if diag_csv.exists():
        with open(diag_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            diag_rows = {}
            for row in reader:
                diag_rows[(row["case"], row["region"])] = float(row["q_ratio_mean"])
        
        max_diff = 0.0
        for r in all_region_data:
            if r["arm"] != "A_baseline":
                continue
            key = (r["case"], r["region"])
            if key in diag_rows and np.isfinite(r["q_ratio_mean"]):
                diff = abs(r["q_ratio_mean"] - diag_rows[key])
                max_diff = max(max_diff, diff)
                if diff > 1e-6:
                    print(f"  WARNING: {key[0]}/{key[1]} diff={diff:.4e}")
        
        if max_diff < 1e-9:
            print(f"  PASS: A_baseline matches Phase 2D master table (max_diff={max_diff:.4e})")
        else:
            print(f"  FAIL: A_baseline differs from Phase 2D master table (max_diff={max_diff:.4e})")
            print(f"  WARNING: Check config consistency before proceeding.")
    
    print(f"\nAll outputs in: {OUT_DIR}")
    print(f"  CSV: ablation_points.csv, ablation_region_summary.csv")
    print(f"  Figures: figures/")
    print(f"  Reports: reports/")


if __name__ == "__main__":
    main()
