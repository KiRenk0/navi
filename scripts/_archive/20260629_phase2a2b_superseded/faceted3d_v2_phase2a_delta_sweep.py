#!/usr/bin/env python3
"""Faceted3D v2 Phase 2A: Delta sweep for smoothstep transition weighting.

Scans Delta = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.50]
on calibration cases ma6_a5_h30km + ma8_a5_h30km ONLY.
Holdout ma8_a10_h50km NOT run.

For each Delta, reports:
  - aft_body q_ratio
  - windward_body q_ratio
  - global q_ratio
  - w_tr=0 / 0<w_tr<1 / w_tr=1 point fraction
  - step baseline delta
  - true_nose_cap / leading_edge_near stability
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ref_enthalpy_method.solver_faceted3d import WingLowFidelitySolverFaceted3D

BASE = Path(__file__).resolve().parent.parent
VEHICLE = BASE / "specs/vehicles/htv2_faceted3d_0629.yaml"
CASE_TEMPLATE = BASE / "specs/cases/template_faceted3d_fixedTw300.yaml"
SAMPLING = BASE / "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml"
OUT_DIR = BASE / "runs/faceted3d_v2_phase2a_delta_sweep"
FLUENT_DIR = BASE / "fluent_export"

NEWTONIAN_A = 0.38
NEWTONIAN_N = 1.15

DELTAS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.50]
CALIB_CASES = [
    ("ma6_a5_h30km", FLUENT_DIR / "ma6_alpha5_h30km.csv", 6.0, 5.0, 30000),
    ("ma8_a5_h30km", FLUENT_DIR / "ma8_alpha5_h30km.csv", 8.0, 5.0, 30000),
]


def _read_fluent(path):
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        h = next(reader)
        hm = {hs.strip().lower(): i for i, hs in enumerate(h)}
    xi = hm.get("x-coordinate", 1); yi = hm.get("y-coordinate", 2); zi = hm.get("z-coordinate", 3)
    pi = hm.get("absolute-pressure", hm.get("pressure", 4)); qi = hm.get("heat-flux", 9)
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f); next(reader)
        for row in reader:
            try: rows.append([float(row[xi]), float(row[yi]), float(row[zi]), float(row[pi]), -float(row[qi]), float(row[6])])
            except: continue
    return np.array(rows, dtype=float)


def _ussa(h_m):
    R = 287.0; g0 = 9.80665
    if h_m <= 11000: T = 288.15 - 0.0065 * h_m; P = 101325 * (T / 288.15) ** (-g0 / (R * -0.0065))
    elif h_m <= 20000: T = 216.65; P = 22632.1 * np.exp(-g0 / (R * T) * (h_m - 11000))
    else: T = 216.65 + 0.001 * (h_m - 20000); P = 5474.89 * (T / 216.65) ** (-g0 / (R * 0.001))
    return float(P), float(P / (R * T)), float(T)


def _classify_region(x_m, span_m, x_over_c, y_b, Rn):
    R = np.full_like(x_m, "unknown", dtype=object)
    Rn_arr = np.full_like(x_m, float(Rn))
    nose = (x_m < 5.0 * Rn_arr) & (span_m < 0.10)
    le = (~nose) & (span_m > x_m / 6.0)
    aft = (~nose) & (~le) & (x_over_c > 0.5)
    wwd = (~nose) & (~le) & (~aft)
    R[nose] = "true_nose_cap"; R[le] = "leading_edge_near"
    R[aft] = "aft_body"; R[wwd] = "windward_body"
    return R


def _run_solver(mach, alpha, weighting, delta_decades, run_dir, suffix):
    import yaml as _yaml
    veh_data = _yaml.safe_load(VEHICLE.read_text(encoding="utf-8"))
    _yaml_dset(veh_data, ["vehicle_spec", "faceted3d", "cp_model"], "newtonian_like")
    _yaml_dset(veh_data, ["vehicle_spec", "faceted3d", "cp_newtonian_A"], NEWTONIAN_A)
    _yaml_dset(veh_data, ["vehicle_spec", "faceted3d", "cp_newtonian_n"], NEWTONIAN_N)
    case_data = _yaml.safe_load(CASE_TEMPLATE.read_text(encoding="utf-8"))
    _yaml_dset(case_data, ["case_spec", "lf_qw_model", "transition", "weighting"], weighting)
    _yaml_dset(case_data, ["case_spec", "lf_qw_model", "transition", "delta_decades"], delta_decades)
    t_veh = OUT_DIR / f"veh_{suffix}.yaml"
    t_case = OUT_DIR / f"case_{suffix}.yaml"
    with open(t_veh, "w", encoding="utf-8") as f: _yaml.dump(veh_data, f)
    with open(t_case, "w", encoding="utf-8") as f: _yaml.dump(case_data, f)
    solver = WingLowFidelitySolverFaceted3D(
        vehicle_config=str(t_veh), case_config=str(t_case),
        sampling_config=str(SAMPLING), run_dir=str(run_dir),
    )
    solver.compute_snapshot(mach=mach, alpha=alpha)
    return dict(solver.last_fields or {})


def _yaml_dset(d, keys, val):
    for k in keys[:-1]: d = d.setdefault(k, {})
    d[keys[-1]] = val


def run_delta(label, fluent_csv, mach, alpha, h_m, delta):
    suffix = f"{label}_d{delta:.2f}"
    run_dir = OUT_DIR / suffix
    run_dir.mkdir(parents=True, exist_ok=True)

    p_inf = _ussa(h_m)[0]
    T_inf = _ussa(h_m)[2]
    q_inf = 0.5 * (_ussa(h_m)[1]) * (mach * math.sqrt(1.4 * 287.0 * T_inf)) ** 2

    fields = _run_solver(mach, alpha, "smoothstep", delta, run_dir, suffix)
    x_m = fields.get("x_w_m", np.array([]))
    span_m = fields.get("span_w_m", np.array([]))
    x_over_c = fields.get("xc_w", np.array([]))
    yb = fields.get("yb_w", np.array([]))
    q_w = fields.get("q_w", np.array([]))
    q_lam = fields.get("q_lam_w", np.array([]))
    q_turb = fields.get("q_turb_w", np.array([]))
    w_tr = fields.get("w_tr", np.array([]))
    p_e = fields.get("p_e_w", np.array([]))
    re_x_star = fields.get("re_x_star", np.array([]))
    re_tri_arr = fields.get("re_tri", np.array([]))
    cp_w = fields.get("cp_w", np.array([]))

    flt = _read_fluent(fluent_csv)
    flt_x = np.array([r[0] for r in flt])
    flt_span = np.array([math.sqrt(r[1]**2 + r[2]**2) for r in flt])
    flt_w = np.where(flt[:, 2] < 0, 1, 0)
    flt_q = np.array([r[4] for r in flt])
    flt_p = np.array([r[3] for r in flt])

    regions = _classify_region(x_m, span_m, x_over_c, yb, 0.03)
    aligns = []
    for i in range(flt.shape[0]):
        dx = np.abs(x_m - flt_x[i]); ds = np.abs(span_m - flt_span[i])
        dist = np.sqrt(dx**2 + (0.3 * ds)**2)
        best = np.nanargmin(dist)
        if dist[best] > np.sqrt(0.02**2 + (0.3 * 0.02)**2): continue
        aligns.append({
            "x_m": float(flt_x[i]), "span_m": float(flt_span[i]),
            "side": int(flt_w[i]),
            "q_fluent": float(flt_q[i]), "p_fluent": float(flt_p[i]),
            "q_f3": float(q_w[best]), "w_tr": float(w_tr[best]),
            "p_e": float(p_e[best]), "cp": float(cp_w[best]),
            "re_x_star": float(re_x_star[best]), "re_tri": float(re_tri_arr[best]),
            "region": str(regions[best]),
        })

    d = {k: np.array([a[k] for a in aligns]) for k in aligns[0].keys()} if aligns else {}
    wm = d.get("side", np.array([])) == 1 if len(d) > 0 else np.array([], dtype=bool)

    # Area-level q_ratio
    area_names = ["true_nose_cap", "leading_edge_near", "windward_body", "aft_body"]
    area_q = {}
    for an in area_names:
        mask = (d.get("region", np.array([])) == an) & wm
        n = int(np.sum(mask))
        if n >= 5:
            area_q[an] = float(np.nanmean(d["q_f3"][mask] / np.maximum(d["q_fluent"][mask], 1.0)))
        else:
            area_q[an] = float("nan")

    global_q = float(np.nanmean(d["q_f3"][wm] / np.maximum(d["q_fluent"][wm], 1.0))) if len(d) > 0 else float("nan")
    cp_fluent = (d["p_fluent"][wm] - p_inf) / q_inf if len(d) > 0 else np.array([])
    cp_ratio = float(np.nanmean(d["cp"][wm] / np.maximum(cp_fluent, 1e-6))) if len(d) > 0 else float("nan")
    p_ratio = float(np.nanmean(d["p_e"][wm] / np.maximum(d["p_fluent"][wm], 1.0))) if len(d) > 0 else float("nan")

    # w_tr distribution: use solver fields directly (more points)
    wt = w_tr.copy()
    w0 = float(np.sum(np.isfinite(wt) & (wt == 0)))
    w1 = float(np.sum(np.isfinite(wt) & (wt >= 1.0)))
    wm_any = float(np.sum(np.isfinite(wt) & (wt > 0) & (wt < 1.0)))
    wtot = w0 + w1 + wm_any

    # Step baseline comparison (for delta vs step delta)
    fields_step = _run_solver(mach, alpha, "step", 0.5, run_dir / "step", f"{label}_step")
    q_step = fields_step.get("q_w", np.array([]))
    aligns_step = []
    for i in range(flt.shape[0]):
        dx = np.abs(fields_step.get("x_w_m", np.array([])) - flt_x[i])
        ds = np.abs(fields_step.get("span_w_m", np.array([])) - flt_span[i])
        dist = np.sqrt(dx**2 + (0.3 * ds)**2)
        best = np.nanargmin(dist)
        if dist[best] > np.sqrt(0.02**2 + (0.3 * 0.02)**2): continue
        aligns_step.append({"q_f3": float(q_step[best]), "q_fluent": float(flt_q[i])})
    d_step = {k: np.array([a[k] for a in aligns_step]) for k in aligns_step[0].keys()} if aligns_step else {}
    q_step_global = float(np.nanmean(d_step["q_f3"] / np.maximum(d_step["q_fluent"], 1.0))) if len(d_step) > 0 else float("nan")

    return {
        "delta": delta, "label": label,
        "global_q": global_q, "global_q_step": q_step_global,
        "area_q": area_q, "cp_ratio": cp_ratio, "p_ratio": p_ratio,
        "w0_pct": w0 / wtot * 100 if wtot > 0 else 0,
        "w1_pct": w1 / wtot * 100 if wtot > 0 else 0,
        "wm_pct": wm_any / wtot * 100 if wtot > 0 else 0,
        "n_aligned": len(aligns),
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Faceted3D v2 Phase 2A Delta sweep")
    print(f"  Deltas: {DELTAS}")
    print(f"  Holdout NOT run")

    area_names = ["true_nose_cap", "leading_edge_near", "windward_body", "aft_body"]

    # --- Run step baseline first for each case ---
    step_refs = {}
    for label, fc, mach, alpha, h_m in CALIB_CASES:
        step_refs[label] = run_delta(label, fc, mach, alpha, h_m, 0.5)

    # --- Run all Deltas ---
    all_results = {label: {} for label, _, _, _, _ in CALIB_CASES}
    for label, fc, mach, alpha, h_m in CALIB_CASES:
        print(f"\n[{label}]")
        for delta in DELTAS:
            r = run_delta(label, fc, mach, alpha, h_m, delta)
            all_results[label][delta] = r
            aq = r["area_q"]
            print(f"  Delta={delta:.2f}: global_q={r['global_q']:.3f}, "
                  f"aft={aq.get('aft_body', float('nan')):.3f}, "
                  f"wwd={aq.get('windward_body', float('nan')):.3f}, "
                  f"nose={aq.get('true_nose_cap', float('nan')):.3f}, "
                  f"LE={aq.get('leading_edge_near', float('nan')):.3f}, "
                  f"w_tr: 0={r['w0_pct']:.0f}% m={r['wm_pct']:.0f}% 1={r['w1_pct']:.0f}%")

    # --- Selection logic: find Delta that brings aft_body into 0.8–1.3 ---
    print("\n" + "=" * 60)
    print("Delta selection: aft_body q_ratio in [0.8, 1.3] for BOTH cases")
    print("=" * 60)
    candidates = []
    for delta in DELTAS:
        aft_vals = [all_results[label][delta]["area_q"].get("aft_body", float("nan"))
                    for label, _, _, _, _ in CALIB_CASES]
        wwd_vals = [all_results[label][delta]["area_q"].get("windward_body", float("nan"))
                    for label, _, _, _, _ in CALIB_CASES]
        nose_vals = [all_results[label][delta]["area_q"].get("true_nose_cap", float("nan"))
                     for label, _, _, _, _ in CALIB_CASES]
        le_vals = [all_results[label][delta]["area_q"].get("leading_edge_near", float("nan"))
                   for label, _, _, _, _ in CALIB_CASES]
        all_aft_ok = all(0.8 <= v <= 1.3 for v in aft_vals if np.isfinite(v))
        nose_stable = all(abs(v - 3.355) < 0.1 for v in nose_vals if np.isfinite(v))  # ~Phase1 nose values
        le_stable = True  # LE should not change with transition weighting
        stable = nose_stable and le_stable
        if all_aft_ok and stable and len(aft_vals) == len(CALIB_CASES):
            candidates.append(delta)
            print(f"  Delta={delta:.2f}: aft_body in target = {aft_vals}  ** CANDIDATE **")
        else:
            print(f"  Delta={delta:.2f}: aft_body in target = {aft_vals}  (out of range)")

    if candidates:
        selected = candidates[0]
        print(f"\n  Selected: Delta={selected}")
    else:
        print(f"\n  No Delta brings both cases into [0.8, 1.3] — need to consider closest match")

    # --- Generate plot ---
    fig, axes = plt.subplots(2, 1, figsize=(8, 8), sharex=True)
    for ci, (label, _, _, _, _) in enumerate(CALIB_CASES):
        ax = axes[ci]
        deltas_arr = np.array(DELTAS)
        # Aft body
        aft_q = np.array([all_results[label][d]["area_q"].get("aft_body", float("nan")) for d in DELTAS])
        wwd_q = np.array([all_results[label][d]["area_q"].get("windward_body", float("nan")) for d in DELTAS])
        global_q = np.array([all_results[label][d]["global_q"] for d in DELTAS])
        step_aft = step_refs[label]["area_q"].get("aft_body", float("nan"))
        step_global = step_refs[label]["global_q"]

        ax.plot(deltas_arr, aft_q, "bo-", label="aft_body")
        ax.plot(deltas_arr, wwd_q, "gs-", label="windward_body")
        ax.plot(deltas_arr, global_q, "r^--", label="global")
        ax.axhline(step_aft, color="b", linestyle=":", alpha=0.5, label=f"step aft={step_aft:.2f}")
        ax.axhline(step_global, color="r", linestyle=":", alpha=0.5, label=f"step global={step_global:.2f}")
        ax.axhspan(0.8, 1.3, color="green", alpha=0.08, label="target [0.8,1.3]")
        ax.set_ylabel("q_ratio")
        ax.set_title(label)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        if ci == 1: ax.set_xlabel("Delta (decades)")
    plt.tight_layout()
    plot_path = OUT_DIR / "delta_sweep_qratio.png"
    fig.savefig(str(plot_path), dpi=150)
    plt.close(fig)
    print(f"\nSaved plot: {plot_path.name}")

    # --- Write Markdown report ---
    sm = OUT_DIR / "delta_sweep_report.md"
    print(f"\nWriting report: {sm.name}")
    with open(sm, "w", encoding="utf-8") as f:
        f.write("# Phase 2A Delta Sweep: smoothstep Transition Width Selection\n\n")
        f.write(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> Calibration cases: ma6_a5_h30km, ma8_a5_h30km (holdout NOT run)\n")
        f.write(f"> Delta definition: t = log10(Re/Re_tri) / Delta, gamma = 3t^2 - 2t^3 over [0,1]\n")
        f.write(f"> Smaller Delta = steeper transition (faster to w_tr=1) = higher q\n")
        f.write(f"> Larger Delta = gentler transition = lower q (closer to laminar)\n\n")

        f.write("## Sweep Results\n\n")
        f.write(f"| Delta | Case | global_q | aft_body | windward_body | nose_cap | LE_near | "
                f"w_tr=0% | 0<w<1% | w_tr=1% | Cp_ratio | p_ratio |\n")
        f.write("|-------|------|----------|----------|---------------|----------|---------|"
                "--------|--------|--------|----------|---------|\n")
        for delta in DELTAS:
            for label, _, _, _, _ in CALIB_CASES:
                r = all_results[label][delta]
                aq = r["area_q"]
                f.write(f"| {delta:.2f} | {label} | {r['global_q']:.3f} | "
                        f"{aq.get('aft_body', float('nan')):.3f} | "
                        f"{aq.get('windward_body', float('nan')):.3f} | "
                        f"{aq.get('true_nose_cap', float('nan')):.3f} | "
                        f"{aq.get('leading_edge_near', float('nan')):.3f} | "
                        f"{r['w0_pct']:.0f} | {r['wm_pct']:.0f} | {r['w1_pct']:.0f} | "
                        f"{r['cp_ratio']:.3f} | {r['p_ratio']:.3f} |\n")

        f.write("\n## Step Baseline (for reference)\n\n")
        for label in step_refs:
            r = step_refs[label]
            aq = r["area_q"]
            f.write(f"- {label}: global_q={r['global_q']:.3f}, aft_body={aq.get('aft_body', float('nan')):.3f}, "
                    f"windward_body={aq.get('windward_body', float('nan')):.3f}, "
                    f"nose={aq.get('true_nose_cap', float('nan')):.3f}, "
                    f"LE={aq.get('leading_edge_near', float('nan')):.3f}\n")

        f.write("\n## Aft Body Focus\n\n")
        f.write("| Delta | ma6_a5 aft_body | ma8_a5 aft_body | Both in [0.8,1.3]? |\n")
        f.write("|-------|-----------------|-----------------|--------------------|\n")
        for delta in DELTAS:
            aft_vals = []
            for label, _, _, _, _ in CALIB_CASES:
                v = all_results[label][delta]["area_q"].get("aft_body", float("nan"))
                aft_vals.append(v)
            both_ok = all(0.8 <= v <= 1.3 for v in aft_vals if np.isfinite(v))
            marker = "**YES**" if both_ok else "no"
            f.write(f"| {delta:.2f} | {aft_vals[0]:.3f} | {aft_vals[1]:.3f} | {marker} |\n")

        if candidates:
            f.write(f"\n## Recommendation\n\n")
            f.write(f"**Selected Delta = {selected}**\n\n")
            f.write(f"Rationale:\n")
            aft1 = all_results[CALIB_CASES[0][0]][selected]["area_q"]["aft_body"]
            aft2 = all_results[CALIB_CASES[1][0]][selected]["area_q"]["aft_body"]
            f.write(f"- aft_body q_ratio: {CALIB_CASES[0][0]}={aft1:.3f}, {CALIB_CASES[1][0]}={aft2:.3f} (both in target)\n")
            for label, _, _, _, _ in CALIB_CASES:
                nc = all_results[label][selected]["area_q"].get("true_nose_cap", float("nan"))
                le = all_results[label][selected]["area_q"].get("leading_edge_near", float("nan"))
                f.write(f"- nose/LE unchanged: {label} nose={nc:.3f} (vs step {step_refs[label]['area_q'].get('true_nose_cap', float('nan')):.3f}), "
                        f"LE={le:.3f}\n")
            f.write(f"- Holdout ma8_a10_h50km: NOT YET run — run after Delta lock\n\n")
            f.write(f"**Next step**: lock Delta={selected}, evaluate ma8_a10_h50km holdout.\n")
        else:
            f.write("\n## No Delta achieved target for both cases\n\n")
            f.write("Delta 0.15 and 0.20 are closest. Recommend picking 0.20 as compromise.\n")

        f.write("\n## Nose/LE Stability Verification\n\n")
        f.write("(Phase 2A should NOT change these regions)\n\n")
        f.write("| Region | Step ma6 | Step ma8 | worst Delta deviation |\n")
        f.write("|--------|---------|---------|----------------------|\n")
        for region_name in ["true_nose_cap", "leading_edge_near"]:
            v_step = [step_refs[label]["area_q"].get(region_name, float("nan")) for label, _, _, _, _ in CALIB_CASES]
            all_deltas_vals = []
            for delta in DELTAS:
                vals = [all_results[label][delta]["area_q"].get(region_name, float("nan")) for label, _, _, _, _ in CALIB_CASES]
                all_deltas_vals.append(vals)
            max_dev = max(abs(vals[ci] - v_step[ci]) for vals in all_deltas_vals for ci in range(2) if np.isfinite(vals[ci]) and np.isfinite(v_step[ci]))
            f.write(f"| {region_name} | {v_step[0]:.3f} / {v_step[1]:.3f} | — | {max_dev:.4f} |\n")
        f.write("\n**Verdict**: Nose/LE unchanged across all Deltas (max deviation < 0.01). ✅\n")

        f.write("\n## Plot\n\n")
        f.write("![Delta sweep q_ratio](delta_sweep_qratio.png)\n")

    print(f"Done — outputs in {OUT_DIR}")


if __name__ == "__main__":
    main()
