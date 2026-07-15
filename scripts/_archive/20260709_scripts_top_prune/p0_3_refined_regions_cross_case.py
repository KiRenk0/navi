#!/usr/bin/env python3
"""P0.3 Task A + B: refined region definitions + cross-case Cp model validation.
Read-only sandbox.
"""

from __future__ import annotations

import csv, math, sys, warnings
from pathlib import Path
from datetime import datetime

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

# ---- Constants ----
P_INF_30KM = 1171.53
RHO_INF_30KM = 0.018010
T_INF_30KM = 226.65
Q_INF_30KM_MA6 = 0.5 * RHO_INF_30KM * (6.0 * math.sqrt(1.4 * 287.0 * T_INF_30KM)) ** 2

HTV2_RN_M = 0.03
HTV2_B_HALF = 1.031027
HTV2_C_ROOT = 3.6


def _read_csv(path: Path) -> dict[str, np.ndarray]:
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f); rows = list(reader)
    cols = {k: [] for k in rows[0].keys()}
    for r in rows:
        for k, v in r.items(): cols[k].append(v)
    result = {}
    for k, vlist in cols.items():
        if k in ("side",):
            result[k] = np.array(vlist, dtype=str)
        else:
            result[k] = np.array(vlist, dtype=float)
    return result


def _ussa_30km() -> tuple[float, float, float]:
    R = 287.0; g0 = 9.80665; L = 0.001
    h=20000; T_b=216.65; P_b=5474.89
    T20 = T_b + L*(h-20000); P20 = P_b*(T20/T_b)**(-g0/(R*L))
    h=30000; T=T20+L*(h-20000); P=P20*(T/T20)**(-g0/(R*L)); rho=P/(R*T)
    return float(P), float(rho), float(T)


def _freestream_q(h_m: float, mach: float) -> tuple[float, float, float, float, float]:
    """Return (p_inf, rho_inf, T_inf, v_inf, q_inf) for given altitude and Mach."""
    p_inf, rho_inf, T_inf = _ussa_30km()  # approximate for all altitudes — use case file ideally
    # We reuse USSA 30km values since we only have one Fluent case. For cross-case
    # we use stored Faceted3D fields with actual atmospheres.
    v_inf = mach * math.sqrt(1.4 * 287.0 * T_inf)
    q_inf = 0.5 * rho_inf * v_inf ** 2
    return p_inf, rho_inf, T_inf, v_inf, q_inf


def _assign_regions_v2(x: np.ndarray, span: np.ndarray) -> np.ndarray:
    """Refined region assignment for HTV2-like planform with Rn=0.03m.
    
    Regions (priority-ordered to avoid overlap):
      0: true_nose_cap    — x < 5*Rn (0.15m) AND span < 0.10m
      1: forebody_center  — x < 0.6m AND span < x/10 AND NOT nose_cap
      2: leading_edge_near — span > x/6 AND NOT nose_cap
      3: wingtip          — span > 0.85 * max(span) AND NOT nose_cap
      4: aft_body         — x > 2.4m AND NOT leading_edge AND NOT wingtip
      5: windward_body    — everything else valid
     -1: unknown
    """
    regions = np.full(x.shape, -1, dtype=int)
    max_span = float(np.nanmax(span))
    nose_x_max = min(5.0 * HTV2_RN_M, 0.15)
    nose_span_max = 0.10
    forebody_x_max = 0.6
    aft_x_min = 2.4
    wingtip_span_frac = 0.85
    le_span_ratio = 1.0 / 6.0
    
    for i in range(x.size):
        xi = float(x[i]); si = float(span[i])
        if not (np.isfinite(xi) and np.isfinite(si)): continue
        
        # Priority 1: nose cap
        if xi < nose_x_max and si < nose_span_max:
            regions[i] = 0; continue
        # Priority 2: leading edge (check before wingtip to catch inner LE)
        if si > xi * le_span_ratio:
            regions[i] = 2; continue
        # Priority 3: wingtip
        if si > max_span * wingtip_span_frac:
            regions[i] = 3; continue
        # Priority 4: forebody center
        if xi < forebody_x_max and si < xi * 0.1:
            regions[i] = 1; continue
        # Priority 5: aft body
        if xi > aft_x_min:
            regions[i] = 4; continue
        # Default: windward body
        regions[i] = 5
    
    return regions


_REGION_NAMES_V2 = {
    0: "true_nose_cap", 1: "forebody_center", 2: "leading_edge_near",
    3: "wingtip", 4: "aft_body", 5: "windward_body", -1: "unknown"
}


def _compute_pe_from_cp(cp: float, p_inf: float, ma_inf: float, gamma: float = 1.4) -> float:
    return p_inf * (1.0 + 0.5 * gamma * ma_inf ** 2 * cp)


def analysis_case(d: dict[str, np.ndarray], label: str, out_dir: Path, p_inf: float, q_inf: float, mach: float):
    """Run region analysis + Cp model evaluation for one case."""
    side_arr = d["side"]
    if side_arr.dtype.kind in ("U", "S"):
        w = (side_arr == "windward") | (side_arr == "1")
    else:
        w = side_arr == 1
    x = d["x_m"][w]; s = d["span_m"][w]
    pf = d["p_fluent_Pa"][w]; p3 = d["p_f3_Pa"][w]
    qf = d["q_fluent_W_m2"][w]; q3 = d["q_f3_W_m2"][w]
    cp_f3 = d["cp_f3"][w]; phi = d["phi_f3_rad"][w]
    w_tr = d.get("w_tr", np.zeros_like(x))[w] if "w_tr" in d else np.zeros_like(x)
    cp_fluent = (pf - p_inf) / q_inf

    regions = _assign_regions_v2(x, s)
    uniq = sorted(set(regions))

    # Region stats
    region_stats = []
    for r in uniq:
        if r < 0: continue
        m = regions == r
        if np.sum(m) < 3: continue
        region_stats.append({
            "region_id": r, "region": _REGION_NAMES_V2[r],
            "count": int(np.sum(m)),
            "cp_fluent_mean": float(np.nanmean(cp_fluent[m])),
            "cp_f3_mean": float(np.nanmean(cp_f3[m])),
            "cp_ratio_mean": float(np.nanmean(cp_f3[m] / np.maximum(cp_fluent[m], 1e-6))),
            "p_fluent_mean": float(np.nanmean(pf[m])),
            "p_f3_mean": float(np.nanmean(p3[m])),
            "p_ratio_mean": float(np.nanmean(p3[m] / np.maximum(pf[m], 1.0))),
            "q_fluent_mean": float(np.nanmean(qf[m])),
            "q_f3_mean": float(np.nanmean(q3[m])),
            "q_ratio_mean": float(np.nanmean(q3[m] / np.maximum(qf[m], 1.0))),
            "phi_mean_deg": float(math.degrees(np.nanmean(phi[m]))),
        })

    # Write region CSV
    rc = out_dir / f"{label}_region_binned_cp_error.csv"
    with open(rc, "w", newline="", encoding="utf-8") as f:
        wc = csv.writer(f)
        wc.writerow(["region_id","region","count","cp_fluent_mean","cp_f3_mean","cp_ratio_mean",
                      "p_fluent_mean","p_f3_mean","p_ratio_mean",
                      "q_fluent_mean","q_f3_mean","q_ratio_mean","phi_mean_deg"])
        for rs in region_stats:
            wc.writerow([rs[k] for k in ["region_id","region","count","cp_fluent_mean","cp_f3_mean",
                                          "cp_ratio_mean","p_fluent_mean","p_f3_mean","p_ratio_mean",
                                          "q_fluent_mean","q_f3_mean","q_ratio_mean","phi_mean_deg"]])
    print(f"  written: {rc}")

    # Candidate models (same as P0.2)
    nbins = 15
    x_min, x_max = float(np.nanmin(x)), float(np.nanmax(x))
    bins = np.linspace(x_min, x_max, nbins + 1)
    bin_idx = np.digitize(x, bins)
    xr_list, rr_list = [], []
    for bi in range(1, nbins + 1):
        m = bin_idx == bi
        if np.sum(m) < 3: continue
        xr_list.append(0.5*(bins[bi-1]+bins[bi]))
        rr_list.append(float(np.nanmean(cp_fluent[m] / np.maximum(cp_f3[m], 1e-6))))
    xr = np.array(xr_list); rr_arr = np.array(rr_list)
    from scipy.interpolate import PchipInterpolator
    r_func = PchipInterpolator(xr, rr_arr, extrapolate=True) if xr.size >= 4 else None

    # Models
    sin_phi = np.sin(phi)
    valid_fit = np.isfinite(cp_fluent) & np.isfinite(sin_phi) & (sin_phi > 0.01) & (cp_fluent > 0.001)
    if np.sum(valid_fit) > 10:
        log_cpf = np.log(cp_fluent[valid_fit])
        log_sin = np.log(sin_phi[valid_fit])
        coeffs_d = np.polyfit(log_sin, log_cpf, 1)
        A_ntn, n_ntn = float(np.exp(coeffs_d[1])), float(coeffs_d[0])
        cp_d = np.where(sin_phi > 0.01, A_ntn * sin_phi ** n_ntn, 0.0)
    else:
        A_ntn, n_ntn = 0.0, 0.0; cp_d = cp_f3.copy()
    
    cp_a = cp_f3 * float(np.nanmean(cp_fluent) / np.nanmean(cp_f3))
    cp_b = cp_f3 * np.clip(r_func(x), 0.05, 2.0) if r_func is not None else cp_f3 * 0.5

    region_ratio_map = {rs["region_id"]: float(rs["cp_ratio_mean"]) for rs in region_stats}
    cp_c = cp_f3.copy()
    for r in uniq:
        if r < 0: continue
        m = regions == r
        ratio = region_ratio_map.get(r, 1.0)
        if ratio > 0.01: cp_c[m] = cp_f3[m] / ratio

    valid_lr = np.isfinite(cp_fluent) & np.isfinite(phi) & np.isfinite(x) & (cp_fluent > 0.001)
    if np.sum(valid_lr) > 20:
        x_norm = (x[valid_lr] - np.nanmean(x[valid_lr])) / np.nanstd(x[valid_lr])
        p_norm = (phi[valid_lr] - np.nanmean(phi[valid_lr])) / np.nanstd(phi[valid_lr])
        A_mat = np.column_stack([np.ones(np.sum(valid_lr)), p_norm, x_norm, p_norm*x_norm])
        coeff_e = np.linalg.lstsq(A_mat, cp_fluent[valid_lr], rcond=None)[0]
        x_all_n = (x - np.nanmean(x[valid_lr])) / np.nanstd(x[valid_lr])
        p_all_n = (phi - np.nanmean(phi[valid_lr])) / np.nanstd(phi[valid_lr])
        cp_e = coeff_e[0] + coeff_e[1]*p_all_n + coeff_e[2]*x_all_n + coeff_e[3]*p_all_n*x_all_n
        cp_e = np.clip(cp_e, 0.001, 2.0)
    else:
        coeff_e = [0,0,0,0]; cp_e = cp_fluent.copy()

    models = {"baseline_Busemann": cp_f3, "A_global_scale": cp_a, "B_x_relaxation": cp_b,
              "C_region_relax": cp_c, "D_newtonian_fit": cp_d, "E_linear_reg": cp_e}

    # Metrics
    from scipy.stats import pearsonr
    model_metrics = []
    for mname, cp_pred in models.items():
        mask = np.isfinite(cp_fluent) & np.isfinite(cp_pred)
        if np.sum(mask) < 5: continue
        rmse = float(np.sqrt(np.nanmean((cp_fluent[mask] - cp_pred[mask])**2)))
        mae = float(np.nanmean(np.abs(cp_fluent[mask] - cp_pred[mask])))
        cp_ratio = float(np.nanmean(cp_pred[mask] / np.maximum(cp_fluent[mask], 1e-6)))
        p_pred = np.array([_compute_pe_from_cp(float(cp_pred[i]), p_inf, mach) for i in range(cp_pred.size)])
        pm = np.isfinite(pf) & np.isfinite(p_pred)
        p_rmse = float(np.sqrt(np.nanmean((pf[pm] - p_pred[pm])**2))) if np.sum(pm)>5 else float("nan")
        p_mae = float(np.nanmean(np.abs(pf[pm] - p_pred[pm]))) if np.sum(pm)>5 else float("nan")
        p_ratio = float(np.nanmean(p_pred[pm] / np.maximum(pf[pm], 1.0))) if np.sum(pm)>5 else float("nan")
        model_metrics.append({"model": mname, "cp_rmse": rmse, "cp_mae": mae, "cp_ratio": cp_ratio,
                              "p_rmse": p_rmse, "p_mae": p_mae, "p_ratio": p_ratio})

    mc = out_dir / f"{label}_candidate_model_metrics.csv"
    with open(mc, "w", newline="", encoding="utf-8") as f:
        wc = csv.writer(f)
        wc.writerow(["model","cp_rmse","cp_mae","cp_ratio","p_rmse","p_mae","p_ratio"])
        for mm in model_metrics:
            wc.writerow([mm["model"], mm["cp_rmse"], mm["cp_mae"], mm["cp_ratio"],
                         mm["p_rmse"], mm["p_mae"], mm["p_ratio"]])
    print(f"  written: {mc}")

    # Region map
    fig, ax = plt.subplots(figsize=(8, 4))
    colors_map = ["red","orange","yellow","green","blue","purple"]
    for r in uniq:
        if r < 0: continue
        m = regions == r
        ax.scatter(x[m], s[m], s=3, c=colors_map[r % len(colors_map)], label=_REGION_NAMES_V2[r], alpha=0.6)
    ax.set_xlabel("x (m)"); ax.set_ylabel("span (m)")
    ax.set_title(f"Refined regions — {label}")
    ax.legend(fontsize=6, markerscale=2); ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / f"{label}_refined_region_masks.png", dpi=150)
    plt.close(fig)
    print(f"  saved: {label}_refined_region_masks.png")

    return region_stats, model_metrics, models, {"A_ntn": A_ntn, "n_ntn": n_ntn, "coeff_e": coeff_e}


def main():
    base = Path(__file__).resolve().parent.parent
    aligned_csv = base / "runs/pressure_audit_ma6_a5_h30km/aligned_pressure_points.csv"
    out_v2 = base / "runs/pressure_audit_ma6_a5_h30km/cp_pressure_correction_sandbox_v2_regions"
    out_cross = base / "runs/cp_correction_cross_case_validation"
    out_v2.mkdir(parents=True, exist_ok=True)
    out_cross.mkdir(parents=True, exist_ok=True)
    (out_cross / "cross_case_pressure_maps").mkdir(parents=True, exist_ok=True)

    p_inf_30, rho_inf_30, T_inf_30 = _ussa_30km()
    v_inf_30_ma6 = 6.0 * math.sqrt(1.4 * 287.0 * T_inf_30)
    q_inf_30_ma6 = 0.5 * rho_inf_30 * v_inf_30_ma6 ** 2

    print("=" * 60)
    print("Task A: Refined region analysis (single case)")
    print("=" * 60)
    d = _read_csv(aligned_csv)
    print(f"  rows={int(d['x_m'].size)}")
    rs, mm, models, params = analysis_case(d, "ma6_a5_h30km", out_v2, p_inf_30, q_inf_30_ma6, 6.0)

    # Print key findings
    nose_rs = [r for r in rs if r["region"] == "true_nose_cap"]
    forebody_rs = [r for r in rs if r["region"] == "forebody_center"]
    le_rs = [r for r in rs if r["region"] == "leading_edge_near"]
    wt_rs = [r for r in rs if r["region"] == "wingtip"]
    body_rs = [r for r in rs if r["region"] == "windward_body"]
    aft_rs = [r for r in rs if r["region"] == "aft_body"]

    if nose_rs: print(f"  true_nose_cap Cp ratio: {nose_rs[0]['cp_ratio_mean']:.2f}x, count={nose_rs[0]['count']}")
    if forebody_rs: print(f"  forebody_center Cp ratio: {forebody_rs[0]['cp_ratio_mean']:.2f}x, count={forebody_rs[0]['count']}")
    if le_rs: print(f"  leading_edge_near Cp ratio: {le_rs[0]['cp_ratio_mean']:.2f}x, count={le_rs[0]['count']}")
    if wt_rs: print(f"  wingtip Cp ratio: {wt_rs[0]['cp_ratio_mean']:.2f}x, count={wt_rs[0]['count']}")
    if body_rs: print(f"  windward_body Cp ratio: {body_rs[0]['cp_ratio_mean']:.2f}x, count={body_rs[0]['count']}")
    if aft_rs: print(f"  aft_body Cp ratio: {aft_rs[0]['cp_ratio_mean']:.2f}x, count={aft_rs[0]['count']}")

    # V2 report
    report_v2 = out_v2 / "refined_region_cp_pressure_summary.md"
    with open(report_v2, "w", encoding="utf-8") as f:
        f.write("# Refined Region Cp/Pressure Summary\n\n")
        f.write(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> Mach=6.0, Alpha=5°, h=30km, Tw=300K\n\n")
        f.write("## Region definitions\n\n")
        f.write(f"| ID | Region | Rule | Rationale |\n")
        f.write(f"|----|--------|------|----------|\n")
        f.write(f"| 0 | true_nose_cap | x < 5*Rn ({min(5*HTV2_RN_M,0.15):.3f}m) AND span < 0.10m | Physical nose-cap region based on nose radius |\n")
        f.write(f"| 1 | forebody_center | x < 0.6m AND span < x/10 AND NOT nose_cap | Centerline behind cap, before main body expansion |\n")
        f.write(f"| 2 | leading_edge_near | span > x/6 AND NOT nose_cap | Points near the planform leading edge |\n")
        f.write(f"| 3 | wingtip | span > 85% max_span AND NOT nose_cap | Outermost wingtip region |\n")
        f.write(f"| 4 | aft_body | x > 2.4m AND NOT leading_edge AND NOT wingtip | Downstream body where pressure relaxation matters |\n")
        f.write(f"| 5 | windward_body | Everything else valid | Interior body points |\n\n")
        
        f.write("## Region-binned Cp / pressure error\n\n")
        f.write(f"| region | count | Cp_fluent | Cp_f3 | Cp_ratio | p_ratio | q_ratio | phi_deg |\n")
        f.write(f"|--------|-------|-----------|-------|----------|---------|---------|--------|\n")
        for rs2 in rs:
            f.write(f"| {rs2['region']:>18s} | {rs2['count']:5d} | {rs2['cp_fluent_mean']:9.4f} | {rs2['cp_f3_mean']:9.4f} | {rs2['cp_ratio_mean']:8.2f} | {rs2['p_ratio_mean']:7.2f} | {rs2['q_ratio_mean']:7.2f} | {rs2['phi_mean_deg']:6.2f} |\n")
        
        f.write("\n## Key answers\n\n")
        if nose_rs:
            nr = nose_rs[0]
            f.write(f"**true_nose_cap Cp ratio**: {nr['cp_ratio_mean']:.2f}x — {'YES, still ~4x' if nr['cp_ratio_mean'] > 3.0 else 'NO, less than 3x'}\n")
            f.write(f"  Fluent Cp={nr['cp_fluent_mean']:.4f}, Busemann Cp={nr['cp_f3_mean']:.4f}\n")
        if forebody_rs:
            fr = forebody_rs[0]
            f.write(f"**forebody_center Cp ratio**: {fr['cp_ratio_mean']:.2f}x — was this the main contributor to the old 'nose 4x'?\n")
        if le_rs:
            lr = le_rs[0]
            f.write(f"**leading_edge_near Cp ratio**: {lr['cp_ratio_mean']:.2f}x\n")
        if wt_rs:
            wr = wt_rs[0]
            f.write(f"**wingtip Cp ratio**: {wr['cp_ratio_mean']:.2f}x — {'still worst' if wr['cp_ratio_mean'] >= max(r['cp_ratio_mean'] for r in rs) else 'not the worst'}\n")
        if body_rs:
            br = body_rs[0]
            f.write(f"**windward_body Cp ratio**: {br['cp_ratio_mean']:.2f}x\n")
        if aft_rs:
            ar = aft_rs[0]
            f.write(f"**aft_body Cp ratio**: {ar['cp_ratio_mean']:.2f}x\n")
        
        # Model comparison
        f.write("\n## Candidate model metrics (refined regions)\n\n")
        f.write(f"| Model | Cp RMSE | Cp MAE | Cp ratio | p RMSE | p MAE | p ratio |\n")
        f.write(f"|-------|---------|--------|----------|--------|-------|--------|\n")
        for mm2 in mm:
            f.write(f"| {mm2['model']:>20s} | {mm2['cp_rmse']:7.4f} | {mm2['cp_mae']:7.4f} | {mm2['cp_ratio']:8.3f} | {mm2['p_rmse']:9.1f} | {mm2['p_mae']:9.1f} | {mm2['p_ratio']:7.3f} |\n")
        
        # Which is best
        best_cp = min(mm, key=lambda m: m["cp_rmse"])
        best_p = min(mm, key=lambda m: abs(m["p_ratio"] - 1.0))
        f.write(f"\n**Best Cp RMSE**: {best_cp['model']} ({best_cp['cp_rmse']:.4f})\n")
        f.write(f"**Best p_ratio**: {best_p['model']} ({best_p['p_ratio']:.3f})\n")
        
        c_better = next((m for m in mm if m["model"] == "C_region_relax"), None)
        b_better = next((m for m in mm if m["model"] == "B_x_relaxation"), None)
        if c_better and b_better:
            f.write(f"\nRegion-relax vs x-relax: C RMSE={c_better['cp_rmse']:.4f} vs B RMSE={b_better['cp_rmse']:.4f} → "
                    f"{'C better' if c_better['cp_rmse'] < b_better['cp_rmse'] else 'B better'}\n")
        
        # Newtonian params
        f.write(f"\n## Newtonian fit parameters\n\n")
        f.write(f"`Cp = A * sin(phi)^n` → A={params['A_ntn']:.4f}, n={params['n_ntn']:.3f}\n")
    
    print(f"  written: {report_v2}")

    # ===== Task B: Cross-case =====
    print("\n" + "=" * 60)
    print("Task B: Cross-case Cp model validation")
    print("=" * 60)
    print("NOTE: Only one Fluent case available (Ma=6, α=5°, h=30km).")
    print("Cross-case validation limited to Faceted3D-only comparison.")
    print("We can still extract Cp patterns across Faceted3D runs at different Ma/α/h.")

    # Look for other Faceted3D runs
    f3_runs = {
        "ma8_a5_h30km": base / "runs/ma8_alpha5_h30km_f3/low_fidelity_points_all_valid.csv",
        "ma8_a10_h50km": base / "runs/ma8_alpha10_h50km_f3/low_fidelity_points_all_valid.csv",
        "ma12_a10_h50km": base / "runs/ma12_alpha10_h50km_f3/low_fidelity_points_all_valid.csv",
        "ma8_a20_h70km": base / "runs/ma8_alpha20_h70km_f3/low_fidelity_points_all_valid.csv",
        "ma12_a20_h70km": base / "runs/ma12_alpha20_h70km_f3/low_fidelity_points_all_valid.csv",
    }
    
    # For cross-case without Fluent, we can only compare Cp_f3 to itself — not very useful.
    # Instead, build a summary of Busemann vs phi behavior across conditions.
    cross_metrics = []
    cross_region_summaries = []
    
    print("Building cross-case Cp profile summary...")
    for label, f3_path in f3_runs.items():
        if not f3_path.exists():
            print(f"  SKIP {label}: file not found")
            continue
        d_f3 = _read_csv(f3_path)
        w = d_f3["side_id"] == 1
        x_f3 = d_f3["x_m"][w]; s_f3 = d_f3["span_m"][w]
        cp_f3_ = d_f3["cp"][w]; phi_f3_ = d_f3["phi_rad"][w]
        regions = _assign_regions_v2(x_f3, s_f3)
        
        for r in sorted(set(r for r in regions if r >= 0)):
            m = regions == r
            if np.sum(m) < 5: continue
            cross_region_summaries.append({
                "case": label, "region_id": r, "region": _REGION_NAMES_V2[r],
                "count": int(np.sum(m)),
                "cp_f3_mean": float(np.nanmean(cp_f3_[m])),
                "phi_mean_deg": float(math.degrees(np.nanmean(phi_f3_[m]))),
            })
        
        cross_metrics.append({
            "case": label,
            "cp_f3_mean": float(np.nanmean(cp_f3_)),
            "phi_mean_deg": float(math.degrees(np.nanmean(phi_f3_))),
            "cp_f3_min": float(np.nanmin(cp_f3_)),
            "cp_f3_max": float(np.nanmax(cp_f3_)),
        })
        print(f"  {label}: cp_f3 mean={cross_metrics[-1]['cp_f3_mean']:.4f}, "
              f"phi={cross_metrics[-1]['phi_mean_deg']:.2f}°")

    # Write cross-case summaries
    cc_csv = out_cross / "cross_case_cp_model_metrics.csv"
    with open(cc_csv, "w", newline="", encoding="utf-8") as f:
        wc = csv.writer(f)
        wc.writerow(["case","cp_f3_mean","phi_mean_deg","cp_f3_min","cp_f3_max"])
        for cm in cross_metrics:
            wc.writerow([cm[k] for k in ["case","cp_f3_mean","phi_mean_deg","cp_f3_min","cp_f3_max"]])
    print(f"  written: {cc_csv}")

    cc_rc = out_cross / "cross_case_region_error_summary.csv"
    with open(cc_rc, "w", newline="", encoding="utf-8") as f:
        wc = csv.writer(f)
        wc.writerow(["case","region_id","region","count","cp_f3_mean","phi_mean_deg"])
        for crs in cross_region_summaries:
            wc.writerow([crs[k] for k in ["case","region_id","region","count","cp_f3_mean","phi_mean_deg"]])
    print(f"  written: {cc_rc}")

    # Cross-case validation report
    cc_report = out_cross / "cross_case_validation_report.md"
    with open(cc_report, "w", encoding="utf-8") as f:
        f.write("# Cross-Case Cp Model Validation\n\n")
        f.write(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> NOTE: Full cross-case validation requires Fluent data for each case. "
                f"This report summarizes available Faceted3D-only Cp/phi patterns.\n\n")
        f.write("## Available Fluent cases\n\n")
        f.write("| Case | Fluent available? |\n")
        f.write("|------|------------------|\n")
        f.write("| Ma=6, α=5°, h=30km | **YES** (single case) |\n")
        f.write("| Others | **NO** — needs Fluent export |\n\n")
        f.write("## Faceted3D Cp cross-case comparison (no Fluent ground truth)\n\n")
        f.write("| Case | Cp_f3 mean | phi mean (°) | Cp_f3 min | Cp_f3 max |\n")
        f.write("|------|------------|--------------|-----------|-----------|\n")
        for cm in cross_metrics:
            f.write(f"| {cm['case']:>16s} | {cm['cp_f3_mean']:10.4f} | {cm['phi_mean_deg']:12.2f} | {cm['cp_f3_min']:9.4f} | {cm['cp_f3_max']:9.4f} |\n")
        
        f.write("\n## Region Cp cross-case\n\n")
        f.write("| Case | Region | Cp_f3 mean | phi deg |\n")
        f.write("|------|--------|------------|--------|\n")
        for crs in cross_region_summaries:
            f.write(f"| {crs['case']:>16s} | {crs['region']:>18s} | {crs['cp_f3_mean']:10.4f} | {crs['phi_mean_deg']:7.2f} |\n")
        
        f.write("\n## Key answers\n\n")
        f.write("### Is Model C (region-relax) expected to be stable across cases?\n")
        f.write("**Cannot determine** without Fluent Cp ground truth at more conditions.\n")
        f.write("Faceted3D Cp values are purely Busemann-based and scale with phi uniformly.\n")
        f.write("The variation across cases is purely a phi-distribution change, not a Cp-model change.\n\n")
        f.write("### Do Newtonian A, n parameters vary with case?\n")
        f.write("**Unknown** — requires Fluent Cp for each case. The Faceted3D-only Cp is identical\n")
        f.write("Busemann(phi) regardless of case. Only the phi distribution shifts.\n\n")
        f.write("### What is needed for proper cross-case validation?\n")
        f.write("1. Fluent wall static pressure CSV for each case (same format as ma6_alpha5_h30km.csv)\n")
        f.write("2. At minimum: one low-altitude + one high-altitude case with Fluent\n")
        f.write("3. Then repeat P0.1→P0.2→P0.3 chain for each Fluent case\n")
        f.write("4. Verify that Cp_ratio(region, Ma, α) patterns are stable\n\n")
        f.write("### Immediate recommendation\n")
        f.write("**Export 2-3 more Fluent cases** before finalizing the correction model.\n")
    
    print(f"  written: {cc_report}")
    print(f"\nTask A+B DONE — outputs in {out_v2} and {out_cross}")


if __name__ == "__main__":
    main()
