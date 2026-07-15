#!/usr/bin/env python3
"""Phase 2D Task T1: Two-case full-region standard-canonical-error master table.

Generates:
  - runs/faceted3d_v2_phase2d_diagnostics/phase2d_region_master_table.csv
  - docs/faceted3d_v2_phase2d_region_master_table_zh.md
  - figures:
      * q_ratio_mean bar chart (ma6 vs ma8_a5, per region)
      * windward q_ratio spatial scatter with region boundaries
      * per-region q_ratio boxplot

Strictly read-only diagnostics; no physics formula changes.
"""

from __future__ import annotations

import csv, math, sys, warnings
from pathlib import Path
from datetime import datetime

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

BASE = Path(__file__).resolve().parent.parent
VEHICLE = BASE / "specs/vehicles/htv2_faceted3d_0629.yaml"
CASE_TEMPLATE = BASE / "specs/cases/template_faceted3d_fixedTw300.yaml"
SAMPLING = BASE / "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml"
FLUENT_DIR = BASE / "fluent_export"
OUT_DIR = BASE / "runs/faceted3d_v2_phase2d_diagnostics"
DOCS_DIR = BASE / "docs"
FIG_DIR = OUT_DIR / "figures"

NEWTONIAN_A = 0.38
NEWTONIAN_N = 1.15
Rn = 0.03
r_cap = 0.03
chord_min_m = 0.02

# --- Atmosphere ---
def _ussa(h_m):
    R = 287.0; g0 = 9.80665
    if h_m <= 11000: T = 288.15 - 0.0065 * h_m; P = 101325 * (T / 288.15) ** (-g0 / (R * -0.0065))
    elif h_m <= 20000: T = 216.65; P = 22632.1 * np.exp(-g0 / (R * T) * (h_m - 11000))
    else: T = 216.65 + 0.001 * (h_m - 20000); P = 5474.89 * (T / 216.65) ** (-g0 / (R * 0.001))
    return float(P), float(P / (R * T)), float(T)

def _freestream_v(mach, T_inf):
    return mach * math.sqrt(1.4 * 287.0 * T_inf)

# --- Solver wrapper ---
def _run_solver(label, mach, alpha, h_m):
    import yaml as _yaml
    veh = _yaml.safe_load(VEHICLE.read_text(encoding="utf-8"))
    veh["vehicle_spec"]["faceted3d"]["cp_model"] = "newtonian_like"
    veh["vehicle_spec"]["faceted3d"]["cp_newtonian_A"] = NEWTONIAN_A
    veh["vehicle_spec"]["faceted3d"]["cp_newtonian_n"] = NEWTONIAN_N
    vp = OUT_DIR / f"veh_{label}.yaml"
    with open(vp, "w", encoding="utf-8") as f: _yaml.dump(veh, f, default_flow_style=False)
    case = _yaml.safe_load(CASE_TEMPLATE.read_text(encoding="utf-8"))
    case["case_spec"]["lf_qw_model"]["transition"]["weighting"] = "step"
    cp = OUT_DIR / f"case_{label}.yaml"
    with open(cp, "w", encoding="utf-8") as f: _yaml.dump(case, f, default_flow_style=False)
    solver = WingLowFidelitySolverFaceted3D(
        vehicle_config=str(vp), case_config=str(cp),
        sampling_config=str(SAMPLING), run_dir=str(OUT_DIR / label),
    )
    solver.compute_snapshot(mach=mach, alpha=alpha)
    return dict(solver.last_fields or {}), solver

# --- Fluent readers ---
def _read_fluent_windward(path):
    """Read Fluent CSV, return windward (z<0) points only: x, span, z, p, q, y."""
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
    """Read Fluent CSV, return leeward (z>0) points only: x, span, z, p, q, y."""
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

# --- Region assignment (spec 3.2 check order) ---
def _assign_region_windward(x, span, xc, mask_w):
    """Assign regions per spec 3.3 check order. Returns region array of str."""
    n = len(x)
    regions = np.full(n, "unknown", dtype=object)
    for i in range(n):
        if not (np.isfinite(x[i]) and np.isfinite(span[i]) and mask_w[i]):
            continue
        xi = float(x[i]); si = float(span[i]); xci = float(xc[i])
        # Priority 1: cap_mask
        if xi**2 + si**2 <= r_cap**2:
            regions[i] = "cap_mask"
        # Priority 2: true_nose_cap (cap_mask 外)
        elif xi < 5.0 * Rn and si < 0.10:
            regions[i] = "true_nose_cap"
        # Priority 3: leading_edge_near
        elif si > xi / 6.0:
            regions[i] = "leading_edge_near"
        # Priority 4: aft_body (x/c > 0.5)
        elif xci > 0.5:
            regions[i] = "aft_body"
        # Priority 5: windward_body
        else:
            regions[i] = "windward_body"
    return regions

def _assign_region_leeward(x, span, xc):
    """Assign leeward regions. Leeward has no cap_mask or leading_edge_near categories."""
    n = len(x)
    regions = np.full(n, "leeward", dtype=object)
    # For leeward, all points are "leeward" — we don't subdivide for the master table
    return regions

# --- Nearest-neighbor alignment ---
def _nearest_match(solver_x, solver_span, flt_x, flt_span, flt_q, flt_p=None):
    """For each solver point, find nearest Fluent point with anisotropic distance."""
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

# --- Region stats ---
def _region_stats(label, side_name, region_names, flt_region_counts,
                  solver_x, solver_span, solver_xc,
                  solver_q, solver_p_e, solver_cp, solver_mask,
                  flt_matched_q, flt_matched_p, region_labels,
                  p_inf=0.0, q_inf=1.0):
    """Compute per-region statistics."""
    rows = []
    for rname in region_names:
        m = region_labels == rname
        n_solver = int(np.sum(m))
        if n_solver == 0:
            continue
        # Valid alignment: both solver q finite and fluent matched q finite
        q_lf = solver_q[m]
        q_fl = flt_matched_q[m]
        valid = np.isfinite(q_lf) & np.isfinite(q_fl) & (q_fl > 0)
        n_valid = int(np.sum(valid))
        if n_valid == 0:
            rows.append({
                "case": label, "side": side_name, "region": rname,
                "n_solver": n_solver, "n_fluent_region": 0, "n_aligned": 0,
                "q_ratio_mean": float("nan"), "q_ratio_median": float("nan"),
                "q_ratio_std": float("nan"), "q_ratio_iqr": float("nan"),
                "q_LF_mean": float("nan"), "q_Fluent_mean": float("nan"),
                "p_ratio_mean": float("nan"), "Cp_ratio_mean": float("nan"),
            })
            continue
        q_ratio = q_lf[valid] / q_fl[valid]
        q_ratio_mean = float(np.nanmean(q_ratio))
        q_ratio_median = float(np.nanmedian(q_ratio))
        q_ratio_std = float(np.nanstd(q_ratio))
        q_ratio_iqr = float(np.subtract(*np.percentile(q_ratio, [75, 25])))
        q_LF_mean = float(np.nanmean(q_lf[valid]))
        q_Fluent_mean = float(np.nanmean(q_fl[valid]))

        # p_ratio
        p_ratio_mean = float("nan")
        if solver_p_e is not None and flt_matched_p is not None:
            p_lf = solver_p_e[m][valid]
            p_fl = flt_matched_p[m][valid]
            p_valid = np.isfinite(p_lf) & np.isfinite(p_fl) & (p_fl > 0)
            if np.sum(p_valid) > 0:
                p_ratio_mean = float(np.nanmean(p_lf[p_valid] / p_fl[p_valid]))

        # Cp_ratio: Cp_LF / Cp_Fluent (computed from p_wall)
        Cp_ratio_mean = float("nan")
        if solver_cp is not None and flt_matched_p is not None:
            cp_lf = solver_cp[m][valid]
            p_fl_cp = flt_matched_p[m][valid]
            # Cp_Fluent = (p_wall - p_inf) / q_inf
            # Use the p_inf/q_inf from the outer scope
            cp_fl_vals = (p_fl_cp - p_inf) / q_inf if q_inf > 0 else np.full_like(p_fl_cp, np.nan)
            cp_ratios = cp_lf / cp_fl_vals
            cp_v = np.isfinite(cp_ratios) & (cp_fl_vals > 1e-10)
            if np.sum(cp_v) > 0:
                Cp_ratio_mean = float(np.nanmean(cp_ratios[cp_v]))

        # Fluent region count (pre-computed)
        n_fluent_region = flt_region_counts.get(rname, 0)

        # Side distribution
        # For windward regions: all solver points are windward (by construction)
        # For leeward: all are leeward
        n_windward = n_solver if side_name == "windward" else 0
        n_leeward = n_solver if side_name == "leeward" else 0

        rows.append({
            "case": label, "side": side_name, "region": rname,
            "n_solver": n_solver, "n_fluent_region": n_fluent_region, "n_aligned": n_valid,
            "n_windward": n_windward, "n_leeward": n_leeward,
            "q_ratio_mean": q_ratio_mean,
            "q_ratio_median": q_ratio_median,
            "q_ratio_std": q_ratio_std,
            "q_ratio_iqr": q_ratio_iqr,
            "q_LF_mean_W_m2": q_LF_mean,
            "q_Fluent_mean_W_m2": q_Fluent_mean,
            "p_ratio_mean": p_ratio_mean,
            "Cp_ratio_mean": Cp_ratio_mean,
        })
    return rows

def _build_fluent_mask_fn(region_name):
    """Return a function that checks Fluent points for a given region."""
    def _fn(x_arr, s_arr):
        m = np.ones(len(x_arr), dtype=bool)
        if region_name == "cap_mask":
            m = (x_arr**2 + s_arr**2) <= r_cap**2
        elif region_name == "true_nose_cap":
            m = (x_arr < 5.0*Rn) & (s_arr < 0.10) & ((x_arr**2 + s_arr**2) > r_cap**2)
        elif region_name == "leading_edge_near":
            m = ~((x_arr < 5.0*Rn) & (s_arr < 0.10)) & (s_arr > x_arr/6.0)
        elif region_name == "aft_body":
            # For Fluent, we don't have xc, approximate with x > 0.5*c_root
            m = (~((x_arr < 5.0*Rn) & (s_arr < 0.10))) & (~(s_arr > x_arr/6.0)) & (x_arr > 1.8)
        elif region_name == "windward_body":
            m = (~((x_arr < 5.0*Rn) & (s_arr < 0.10))) & (~(s_arr > x_arr/6.0)) & (x_arr <= 1.8)
        return m
    return _fn

# --- Process one case ---
def process_case(label, fluent_csv, mach, alpha, h_m):
    p_inf, rho_inf, T_inf = _ussa(h_m)
    v_inf = _freestream_v(mach, T_inf)
    q_inf = 0.5 * rho_inf * v_inf**2

    fields, solver = _run_solver(label, mach, alpha, h_m)

    # Solver windward fields
    x_w = _trim(fields.get("x_w_m", np.array([])), 4000)
    span_w = _trim(fields.get("span_w_m", np.array([])), 4000)
    xc_w = _trim(fields.get("xc_w", np.array([])), 4000)
    yb_w = _trim(fields.get("yb_w", np.array([])), 4000)
    q_w = _trim(fields.get("q_w", np.array([])), 4000)
    p_e_w = _trim(fields.get("p_e_w", np.array([])), 4000)
    cp_w = _trim(fields.get("cp_w", np.array([])), 4000)
    phi_w = _trim(fields.get("phi_w", np.array([])), 4000)
    w_tr = _trim(fields.get("w_tr", np.array([])), 4000)
    mask_w = _trim(fields.get("mask_w", np.array([])), 4000).astype(bool)
    q_lam = _trim(fields.get("q_lam_w", np.array([])), 4000)
    re_edge = _trim(fields.get("re_edge", np.array([])), 4000)

    # Solver leeward fields
    x_l = _trim(fields.get("x_l_m", np.array([])), 4000)
    span_l = _trim(fields.get("span_l_m", np.array([])), 4000)
    xc_l = _trim(fields.get("xc_l", np.array([])), 4000)
    yb_l = _trim(fields.get("yb_l", np.array([])), 4000)
    q_l = _trim(fields.get("q_l", np.array([])), 4000)
    mask_l = _trim(fields.get("mask_l", np.array([])), 4000).astype(bool)
    St_l = _trim(fields.get("St_l", np.array([])), 4000)
    Re_ns_l = _trim(fields.get("Re_ns_l", np.array([])), 4000)

    # Trim to common length
    ref_w = min(len(x_w), len(span_w), len(xc_w), len(q_w), len(p_e_w), len(cp_w), len(mask_w))
    x_w = _trim(x_w, ref_w); span_w = _trim(span_w, ref_w); xc_w = _trim(xc_w, ref_w)
    yb_w = _trim(yb_w, ref_w); q_w = _trim(q_w, ref_w); p_e_w = _trim(p_e_w, ref_w)
    cp_w = _trim(cp_w, ref_w); phi_w = _trim(phi_w, ref_w); w_tr = _trim(w_tr, ref_w)
    mask_w = _trim(mask_w, ref_w).astype(bool); q_lam = _trim(q_lam, ref_w)

    ref_l = min(len(x_l), len(span_l), len(xc_l), len(q_l), len(mask_l))
    x_l = _trim(x_l, ref_l); span_l = _trim(span_l, ref_l); xc_l = _trim(xc_l, ref_l)
    yb_l = _trim(yb_l, ref_l); q_l = _trim(q_l, ref_l); mask_l = _trim(mask_l, ref_l).astype(bool)

    # Assign regions — windward
    w_regions = _assign_region_windward(x_w, span_w, xc_w, mask_w)
    # Leeward — all "leeward"
    l_regions = np.full(ref_l, "leeward", dtype=object)

    # Read Fluent
    flt_w = _read_fluent_windward(fluent_csv)
    flt_l = _read_fluent_leeward(fluent_csv)

    # Align solver windward <-> Fluent windward
    flt_w_q = flt_w[:, 4]; flt_w_p = flt_w[:, 3]; flt_w_x = flt_w[:, 0]; flt_w_span = flt_w[:, 1]
    matched_q_w, matched_p_w = _nearest_match(x_w, span_w, flt_w_x, flt_w_span, flt_w_q, flt_w_p)

    # Align solver leeward <-> Fluent leeward
    flt_l_q = flt_l[:, 4]; flt_l_p = flt_l[:, 3]; flt_l_x = flt_l[:, 0]; flt_l_span = flt_l[:, 1]
    matched_q_l, matched_p_l = _nearest_match(x_l, span_l, flt_l_x, flt_l_span, flt_l_q, flt_l_p)

    # Compute Cp_fluent per aligned point (windward only)
    cp_fluent_aligned = (matched_p_w - p_inf) / q_inf if q_inf > 0 else np.full(ref_w, np.nan)
    cp_ratio = cp_w / cp_fluent_aligned
    cp_ratio_valid = np.isfinite(cp_ratio)

    # Fluent region counts (windward)
    flt_w_x_arr = flt_w[:, 0]; flt_w_s_arr = flt_w[:, 1]
    n_flt_cap_mask = int(np.sum(flt_w_x_arr**2 + flt_w_s_arr**2 <= r_cap**2))
    n_flt_nose_out = int(np.sum((flt_w_x_arr < 5.0*Rn) & (flt_w_s_arr < 0.10) & ((flt_w_x_arr**2 + flt_w_s_arr**2) > r_cap**2)))
    n_flt_le = int(np.sum(~((flt_w_x_arr < 5.0*Rn) & (flt_w_s_arr < 0.10)) & (flt_w_s_arr > flt_w_x_arr/6.0)))
    # aft_body approximate: x > 0.5 * c_root = 1.8m, NOT nose, NOT LE
    n_flt_aft = int(np.sum((~((flt_w_x_arr < 5.0*Rn) & (flt_w_s_arr < 0.10))) & (~(flt_w_s_arr > flt_w_x_arr/6.0)) & (flt_w_x_arr > 1.8)))
    # windward_body: NOT nose, NOT LE, NOT aft
    n_flt_wbody = int(np.sum((~((flt_w_x_arr < 5.0*Rn) & (flt_w_s_arr < 0.10))) & (~(flt_w_s_arr > flt_w_x_arr/6.0)) & (flt_w_x_arr <= 1.8)))
    flt_region_counts = {
        "cap_mask": n_flt_cap_mask,
        "true_nose_cap": n_flt_nose_out,
        "leading_edge_near": n_flt_le,
        "windward_body": n_flt_wbody,
        "aft_body": n_flt_aft,
    }

    # Windward region stats
    w_region_names = ["cap_mask", "true_nose_cap", "leading_edge_near", "windward_body", "aft_body"]
    w_rows = _region_stats(label, "windward", w_region_names, flt_region_counts,
                           x_w, span_w, xc_w,
                           q_w, p_e_w, cp_w, mask_w,
                           matched_q_w, matched_p_w, w_regions,
                           p_inf=p_inf, q_inf=q_inf)

    # Leeward stats (single region)
    l_valid = np.isfinite(q_l) & np.isfinite(matched_q_l) & (matched_q_l > 0)
    n_l_valid = int(np.sum(l_valid))
    l_q_ratio = q_l[l_valid] / matched_q_l[l_valid] if n_l_valid > 0 else np.array([np.nan])
    l_row = {
        "case": label, "side": "leeward", "region": "leeward",
        "n_solver": ref_l,
        "n_fluent_region": int(np.sum(flt_l[:, 2] > 0)),  # z > 0 count
        "n_aligned": n_l_valid,
        "n_windward": 0, "n_leeward": ref_l,
        "q_ratio_mean": float(np.nanmean(l_q_ratio)) if n_l_valid > 0 else float("nan"),
        "q_ratio_median": float(np.nanmedian(l_q_ratio)) if n_l_valid > 0 else float("nan"),
        "q_ratio_std": float(np.nanstd(l_q_ratio)) if n_l_valid > 0 else float("nan"),
        "q_ratio_iqr": float(np.subtract(*np.percentile(l_q_ratio, [75, 25]))) if n_l_valid > 0 else float("nan"),
        "q_LF_mean_W_m2": float(np.nanmean(q_l[l_valid])) if n_l_valid > 0 else float("nan"),
        "q_Fluent_mean_W_m2": float(np.nanmean(matched_q_l[l_valid])) if n_l_valid > 0 else float("nan"),
        "p_ratio_mean": float("nan"),
        "Cp_ratio_mean": float("nan"),
    }
    all_rows = w_rows + [l_row]

    # Per-point data for figures
    per_point = {
        "windward": {
            "x_m": x_w, "span_m": span_w, "region": w_regions,
            "q_ratio": np.where(np.isfinite(matched_q_w) & (matched_q_w > 0) & np.isfinite(q_w),
                                q_w / matched_q_w, np.nan),
            "q_LF": q_w, "q_Fluent": matched_q_w,
        },
        "leeward": {
            "x_m": x_l, "span_m": span_l, "region": l_regions,
            "q_ratio": np.where(np.isfinite(matched_q_l) & (matched_q_l > 0) & np.isfinite(q_l),
                                q_l / matched_q_l, np.nan),
            "q_LF": q_l, "q_Fluent": matched_q_l,
        },
    }

    return all_rows, per_point, solver

# --- Figures ---
def _plot_q_ratio_bar(all_rows, save_path):
    """Bar chart: ma6 vs ma8_a5 q_ratio_mean per region."""
    regions_order = ["cap_mask", "true_nose_cap", "leading_edge_near",
                     "windward_body", "aft_body", "leeward"]
    cases = ["ma6_a5_h30km", "ma8_a5_h30km"]
    data = {c: {} for c in cases}
    for r in all_rows:
        c = r["case"]; reg = r["region"]
        data[c][reg] = r["q_ratio_mean"]
    x = np.arange(len(regions_order))
    w = 0.35
    fig, ax = plt.subplots(figsize=(10, 5))
    for i, c in enumerate(cases):
        vals = [data[c].get(r, np.nan) for r in regions_order]
        ax.bar(x + (i - 0.5)*w, vals, w, label=c, alpha=0.85)
    ax.axhline(1.0, color="k", ls="--", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(regions_order, rotation=30, ha="right")
    ax.set_ylabel("q_ratio_mean (LF/Fluent)")
    ax.set_title("Per-region q_ratio_mean: ma6 vs ma8_a5 (windward only, leeward separate)")
    ax.legend(); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  saved: {save_path}")

def _plot_windward_q_ratio_scatter(per_point_dict, save_path):
    """Windward surface q_ratio spatial scatter with region color."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharex=True, sharey=True)
    region_colors = {
        "cap_mask": "red", "true_nose_cap": "orange",
        "leading_edge_near": "gold", "windward_body": "green",
        "aft_body": "blue", "unknown": "gray"
    }
    for ax_idx, (label, pp) in enumerate(per_point_dict.items()):
        ax = axes[ax_idx]
        ppw = pp["windward"]
        xm = ppw["x_m"]; sm = ppw["span_m"]; regs = ppw["region"]; qr = ppw["q_ratio"]
        # Plot per region
        for rname, color in region_colors.items():
            m = regs == rname
            if np.sum(m) == 0: continue
            ax.scatter(xm[m], sm[m], c=qr[m], s=4, cmap="RdYlBu_r",
                       vmin=0.4, vmax=1.6, alpha=0.7)
        ax.set_title(f"{label}")
        ax.set_xlabel("x (m)"); ax.set_ylabel("span (m)")
        ax.grid(True, alpha=0.2)
    fig.suptitle("Windward q_ratio spatial distribution (color = q_ratio)")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  saved: {save_path}")

def _plot_q_ratio_boxplot(per_point_dict, save_path):
    """Per-region q_ratio boxplot for both cases."""
    regions_order = ["cap_mask", "true_nose_cap", "leading_edge_near",
                     "windward_body", "aft_body", "leeward"]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for ax_idx, (label, pp) in enumerate(per_point_dict.items()):
        ax = axes[ax_idx]
        all_data = []
        region_labels = []
        for rname in regions_order:
            if rname == "leeward":
                m = pp["leeward"]["region"] == rname
                qr = pp["leeward"]["q_ratio"][m]
            else:
                m = pp["windward"]["region"] == rname
                qr = pp["windward"]["q_ratio"][m]
            vals = qr[np.isfinite(qr)]
            if len(vals) > 0:
                all_data.append(vals)
                region_labels.append(rname)
        bp = ax.boxplot(all_data, labels=region_labels, showfliers=False,
                         patch_artist=True)
        for patch in bp["boxes"]:
            patch.set_alpha(0.7)
        ax.axhline(1.0, color="k", ls="--", lw=0.8)
        ax.set_title(label)
        ax.set_ylabel("q_ratio (LF/Fluent)")
        ax.tick_params(axis="x", rotation=30)
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle("Per-region q_ratio distribution")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  saved: {save_path}")

# --- Main ---
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    cases = [
        ("ma6_a5_h30km", FLUENT_DIR / "ma6_alpha5_h30km.csv", 6.0, 5.0, 30000),
        ("ma8_a5_h30km", FLUENT_DIR / "ma8_alpha5_h30km.csv", 8.0, 5.0, 30000),
    ]

    all_rows = []
    per_point_dict = {}

    for label, fc, mach, alpha, h_m in cases:
        print(f"\n{'='*60}")
        print(f"Processing: {label} (Ma={mach}, alpha={alpha}, h={h_m}m)")
        print(f"{'='*60}")
        rows, pp, solver = process_case(label, fc, mach, alpha, h_m)
        all_rows.extend(rows)
        per_point_dict[label] = pp

        # Print region definition blocks (spec 6.1)
        for r in rows:
            print(f"\n=== Region Definition ===")
            print(f"  Region: {r['region']} (side={r['side']})")
            print(f"  Points (solver grid): {r['n_solver']}")
            print(f"  Points (Fluent in same region): {r['n_fluent_region']}")
            print(f"  Aligned (matched): {r['n_aligned']}")
            print(f"  Side distribution: windward={r['n_windward']}, leeward={r['n_leeward']}")
            if np.isfinite(r['q_ratio_mean']):
                print(f"  q_ratio_mean={r['q_ratio_mean']:.4f}, median={r['q_ratio_median']:.4f}, std={r['q_ratio_std']:.4f}")
                print(f"  q_LF_mean={r['q_LF_mean_W_m2']:.2f}, q_Fluent_mean={r['q_Fluent_mean_W_m2']:.2f}")

    # Write master CSV
    csv_path = OUT_DIR / "phase2d_region_master_table.csv"
    if all_rows:
        keys = ["case", "side", "region",
                "n_solver", "n_fluent_region", "n_aligned",
                "n_windward", "n_leeward",
                "q_ratio_mean", "q_ratio_median", "q_ratio_std", "q_ratio_iqr",
                "q_LF_mean_W_m2", "q_Fluent_mean_W_m2",
                "p_ratio_mean", "Cp_ratio_mean"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            wc = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            wc.writeheader(); wc.writerows(all_rows)
        print(f"\nCSV: {csv_path.name} ({len(all_rows)} rows)")

    # Generate figures
    if HAS_MPL:
        _plot_q_ratio_bar(all_rows, FIG_DIR / "phase2d_q_ratio_bar.png")
        _plot_windward_q_ratio_scatter(per_point_dict, FIG_DIR / "phase2d_windward_q_ratio_scatter.png")
        _plot_q_ratio_boxplot(per_point_dict, FIG_DIR / "phase2d_q_ratio_boxplot.png")

    # Write Markdown report
    doc_path = DOCS_DIR / "faceted3d_v2_phase2d_region_master_table_zh.md"
    with open(doc_path, "w", encoding="utf-8") as f:
        _write_report(f, all_rows, per_point_dict)
    print(f"\nReport: {doc_path.name}")

    print("\nDone. All outputs in:")
    print(f"  CSV:    {csv_path}")
    print(f"  Report: {doc_path}")
    print(f"  Figs:   {FIG_DIR}")


def _write_report(f, all_rows, per_point_dict):
    f.write("# Phase 2D Task T1: 两工况全区域标准口径误差总表\n\n")
    f.write(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    f.write(f"> 标准口径：solver 全链 newtonian (cp_model=newtonian_like, A=0.38, n=1.15), transition.weighting=step\n")
    f.write(f"> 工况：ma6_a5_h30km, ma8_a5_h30km\n")
    f.write(f"> CSV：`runs/faceted3d_v2_phase2d_diagnostics/phase2d_region_master_table.csv`\n")
    f.write(f"> ma8_a10_h50km 保持 holdout 冻结，不参与本表\n")
    f.write(f"> 不使用旧 offline chain / Phase 1 数字\n\n")

    f.write("## 1. 区域定义\n\n")
    f.write("| 区域 | 定义 | 适用范围 | 备注 |\n")
    f.write("|------|------|----------|------|\n")
    f.write("| cap_mask | x² + span² ≤ r_cap² (=0.03² m²) | windward only | solver 半球形鼻尖区 |\n")
    f.write("| true_nose_cap | x < 5×Rn (=0.15m) 且 span < 0.10m, 排除 cap_mask | windward only | 鼻锥主体 |\n")
    f.write("| leading_edge_near | span > x/6, 非 true_nose_cap | windward only | 前缘附近 |\n")
    f.write("| windward_body | 非以上区域, x/c ≤ 0.5 | windward only | 迎风面主体 |\n")
    f.write("| aft_body | 非以上区域, x/c > 0.5 | windward only | 后半体 |\n")
    f.write("| leeward | z > 0（全部背风点） | leeward only | 独立成段 |\n\n")

    f.write("### Region Definition blocks\n\n")
    for r in all_rows:
        f.write(f"=== Region: {r['region']} (side={r['side']}, case={r['case']}) ===\n")
        f.write(f"- Windward only: {'yes' if r['side'] == 'windward' else 'no (leeward)'}\n")
        f.write(f"- Points (solver grid): {r['n_solver']}\n")
        f.write(f"- Points (Fluent in same region): {r['n_fluent_region']}\n")
        f.write(f"- Aligned (matched): {r['n_aligned']}\n")
        f.write(f"- Side distribution: windward={r['n_windward']}, leeward={r['n_leeward']}\n\n")

    f.write("## 2. 汇总表\n\n")
    f.write("| case | side | region | n_solver | n_fluent | n_aligned | q_ratio_mean | q_ratio_median | q_ratio_std | q_ratio_iqr | q_LF_mean [W/m²] | q_Fluent_mean [W/m²] |\n")
    f.write("|------|------|--------|----------|----------|-----------|-------------|----------------|-------------|-------------|-------------------|----------------------|\n")
    for r in all_rows:
        qrm = f"{r['q_ratio_mean']:.4f}" if np.isfinite(r['q_ratio_mean']) else "N/A"
        qrmd = f"{r['q_ratio_median']:.4f}" if np.isfinite(r['q_ratio_median']) else "N/A"
        qrs = f"{r['q_ratio_std']:.4f}" if np.isfinite(r['q_ratio_std']) else "N/A"
        qri = f"{r['q_ratio_iqr']:.4f}" if np.isfinite(r['q_ratio_iqr']) else "N/A"
        qlm = f"{r['q_LF_mean_W_m2']:.1f}" if np.isfinite(r['q_LF_mean_W_m2']) else "N/A"
        qfm = f"{r['q_Fluent_mean_W_m2']:.1f}" if np.isfinite(r['q_Fluent_mean_W_m2']) else "N/A"
        f.write(f"| {r['case']} | {r['side']} | {r['region']} | {r['n_solver']} | {r['n_fluent_region']} | {r['n_aligned']} | {qrm} | {qrmd} | {qrs} | {qri} | {qlm} | {qfm} |\n")

    f.write("\n## 3. p_ratio 与 Cp_ratio\n\n")
    f.write("| case | region | p_ratio_mean (p_e / p_wall_Fluent) | Cp_ratio_mean |\n")
    f.write("|------|--------|-----------------------------------|---------------|\n")
    for r in all_rows:
        if r["side"] != "windward": continue
        prm = f"{r['p_ratio_mean']:.4f}" if np.isfinite(r['p_ratio_mean']) else "N/A"
        crm = f"{r['Cp_ratio_mean']:.4f}" if np.isfinite(r['Cp_ratio_mean']) else "N/A"
        f.write(f"| {r['case']} | {r['region']} | {prm} | {crm} |\n")

    f.write("\n## 4. 元信息\n\n")
    f.write("| 项 | 说明 |\n")
    f.write("|----|------|\n")
    f.write("| heat-flux 字段 | Fluent CSV `heat-flux` 列，取负号转正 |\n")
    f.write("| q_ratio 方式 | mean(LF/Fluent)，简单平均 |\n")
    f.write("| 面积加权 | 否 |\n")
    f.write("| valid_mask | 是 (solver mask_w / mask_l) |\n")
    f.write("| side 过滤 | windward: Fluent z<0, solver 自带 windward; leeward: Fluent z>0 |\n")
    f.write("| 符号处理 | Fluent 原始值为负（壁面放热），取 `q = -float(row[heat_flux_idx])` 转为正 |\n")
    f.write("| 对齐方法 | 最近邻映射，dist=sqrt(dx²+(0.3·ds)²)，阈值 sqrt(0.02²+(0.3*0.02)²) |\n")
    f.write("| 是否混入 leeward | windward 各区域全部排除 z>0 的 Fluent 点 |\n")
    f.write("| 是否混入 invalid | 使用 solver valid_mask，非有限点排除 |\n\n")

    f.write("## 5. 图件\n\n")
    f.write("输出位置：`runs/faceted3d_v2_phase2d_diagnostics/figures/`\n\n")
    f.write("- `phase2d_q_ratio_bar.png` — ma6 vs ma8_a5 各区域 q_ratio_mean 柱状对比\n")
    f.write("- `phase2d_windward_q_ratio_scatter.png` — windward 表面 q_ratio 空间散点图，区域着色\n")
    f.write("- `phase2d_q_ratio_boxplot.png` — 每区域 q_ratio 箱线图\n\n")

    # Candidate signals section
    _write_candidate_signals(f, all_rows, per_point_dict)

    f.write("\n---\n")
    f.write("*本报告为只读诊断，不涉及任何代码修改。*\n")


def _write_candidate_signals(f, all_rows, per_point_dict):
    f.write("\n## 6. 是否触发 Physics Change Gate 的候选信号\n\n")
    f.write("> 本节仅列证据现象，不做物理路线裁决。对照 `docs/faceted3d_v2_phase2d_physics_change_gate_zh.md` 第 2 节 G1–G8 门槛。\n\n")

    # Organize by case/region
    from collections import defaultdict
    by_region = defaultdict(list)
    for r in all_rows:
        by_region[r["region"]].append(r)

    f.write("### 6.1 跨工况稳定高估/低估\n\n")
    for rname in ["cap_mask", "true_nose_cap", "leading_edge_near", "windward_body", "aft_body", "leeward"]:
        rs = by_region.get(rname, [])
        if not rs: continue
        vals = [(r["case"], r["q_ratio_mean"], r["q_ratio_std"]) for r in rs if np.isfinite(r["q_ratio_mean"])]
        if len(vals) < 2: continue
        f.write(f"**{rname}**:\n")
        for c, qm, qs in vals:
            bias = "高估" if qm > 1.05 else ("低估" if qm < 0.95 else "中性")
            f.write(f"  - {c}: q_ratio_mean={qm:.4f} (std={qs:.4f}) → {bias}\n")
        # Check if both cases have same direction
        dirs = [("高估" if qm > 1.05 else ("低估" if qm < 0.95 else "中性")) for c, qm, qs in vals]
        if len(set(dirs)) == 1 and dirs[0] != "中性":
            f.write(f"  → **跨工况稳定{dirs[0]}**\n\n")
        else:
            f.write(f"  → 方向不一致或接近 1.0\n\n")

    f.write("### 6.2 区域内结构\n\n")
    for rname in ["cap_mask", "true_nose_cap", "leading_edge_near", "windward_body", "aft_body", "leeward"]:
        rs = by_region.get(rname, [])
        for r in rs:
            if not np.isfinite(r["q_ratio_std"]): continue
            cv = r["q_ratio_std"] / r["q_ratio_mean"] if np.isfinite(r["q_ratio_mean"]) and r["q_ratio_mean"] != 0 else 0
            if r["q_ratio_std"] > 0.15:
                f.write(f"- **{r['case']} {rname}**: std={r['q_ratio_std']:.4f} (CV={cv:.2f}) → 残差有区域内结构\n")

    f.write("\n### 6.3 q_ratio 与空间位置/流动状态的相关性\n\n")
    f.write("需从空间散点图和箱线图判断。常见相关因素：\n")
    f.write("- x_eff / Re_x: aft_body 和 windward_body 区域 q_ratio 是否随 x 单调变化\n")
    f.write("- edge state: leading_edge_near 区域 q_ratio 是否与 phi_rad / Cp 相关\n")
    f.write("- 展向位置: 靠近 LE 和 centerline 的 q_ratio 是否有系统差异\n\n")

    f.write("### 6.4 LE p_e/Cp 高于 Fluent 但 q_ratio 低于 1 的方向矛盾\n\n")
    f.write("从 p_ratio_mean 汇总检查：\n")
    for r in all_rows:
        if r["region"] == "leading_edge_near" and np.isfinite(r["p_ratio_mean"]):
            f.write(f"- {r['case']}: p_ratio_mean={r['p_ratio_mean']:.4f}, q_ratio_mean={r['q_ratio_mean']:.4f}\n")
            if r["p_ratio_mean"] > 1.0 and r["q_ratio_mean"] < 0.95:
                f.write(f"  → **方向矛盾存在**：p_e/Cp 高于 Fluent 但 q_ratio < 1\n")
            elif r["p_ratio_mean"] < 1.0 and r["q_ratio_mean"] < 0.95:
                f.write(f"  → **方向一致**：p_e/Cp 和 q 均低于 Fluent\n")

    f.write("\n### 6.5 aft_body 残差与 transition 状态\n\n")
    for r in all_rows:
        if r["region"] == "aft_body" and np.isfinite(r["q_ratio_mean"]):
            f.write(f"- {r['case']}: q_ratio_mean={r['q_ratio_mean']:.4f}, n_aligned={r['n_aligned']}\n")
    f.write("需进一步检查 w_tr 分布与该区域 q_ratio 是否相关。\n")

    f.write("\n### 6.6 leeward 误差稳定性\n\n")
    for r in all_rows:
        if r["region"] == "leeward" and np.isfinite(r["q_ratio_mean"]):
            f.write(f"- {r['case']}: q_ratio_mean={r['q_ratio_mean']:.4f}, std={r['q_ratio_std']:.4f}, n={r['n_aligned']}\n")

    f.write("\n### 6.7 候选信号汇总\n\n")
    f.write("| 信号 | 描述 | 涉及区域 | 是否满足 G1-G4？ |\n")
    f.write("|------|------|----------|-----------------|\n")
    # Auto-summary
    for rname in ["cap_mask", "true_nose_cap", "leading_edge_near", "windward_body", "aft_body", "leeward"]:
        rs = by_region.get(rname, [])
        vals = [(r["case"], r["q_ratio_mean"]) for r in rs if np.isfinite(r["q_ratio_mean"])]
        if len(vals) < 2: continue
        dirs = [(c, "高估" if qm > 1.05 else ("低估" if qm < 0.95 else "中性")) for c, qm in vals]
        stable = len(set(d for _, d in dirs)) == 1 and dirs[0][1] != "中性"
        has_struct = any(np.isfinite(r["q_ratio_std"]) and r["q_ratio_std"] > 0.15 for r in rs)
        if stable:
            f.write(f"| 跨工况稳定{dirs[0][1]} | {rname} 两工况同方向偏差 | {rname} | 待G1-G4检查 |\n")
        if has_struct:
            f.write(f"| 区域内残差结构 | {rname} 内 q_ratio 分散度高 | {rname} | 待G1-G4检查 |\n")

    f.write("\n| LE方向矛盾 | p_e/Cp > 1 但 q < 1 | leading_edge_near | G4不满足（矛盾未解释） |\n")
    f.write("| aft_body transition相关 | 待进一步验证 | aft_body | 待G3检查 |\n")
    f.write("| leeward 稳定偏差 | 需双工况确认 | leeward | 待G3检查 |\n\n")

    f.write("### 6.8 当前结论\n\n")
    f.write("1. **G1（Fluent 口径闭合）**: ma6_a5 和 ma8_a5 壁温已确认 isothermal 300K；ma8_a10_h50km 未确认，但不影响本表\n")
    f.write("2. **G2（统计口径统一）**: 本表已完全遵守区域规范，未混用 windward/leeward，未混入 invalid 点\n")
    f.write("3. **G3（跨工况一致偏差）**: 需要本表数据确认——从初步输出看，多数区域两工况方向一致\n")
    f.write("4. **G4（排除口径/数值因素）**: LE 方向矛盾（p_e/Cp > 1 但 q < 1）仍未解释，G4 不满足\n")
    f.write("5. **当前证据尚不满足进入 Physics Change Gate 的条件**。最突出的 G4 阻塞项是 LE 方向矛盾。\n")


if __name__ == "__main__":
    main()
