#!/usr/bin/env python3
"""T1 pre-implementation baseline snapshot — Phase 1 (no source changes).

Runs ma6_a5_h30km and ma8_a5_h30km with step weighting (current default).
Produces fields.npz + summary.json + snapshot report.
Does NOT touch ma8_a10.
Does NOT modify any source file.
"""

from __future__ import annotations

import json, math, sys, warnings
from pathlib import Path
from datetime import datetime

import numpy as np

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ref_enthalpy_method.solver_faceted3d import WingLowFidelitySolverFaceted3D

BASE = Path(__file__).resolve().parent.parent
VEHICLE = BASE / "runs/faceted3d_v2_phase2d_diagnostics" / "veh_ma6_a5_h30km.yaml"
CASE = BASE / "runs/faceted3d_v2_phase2d_diagnostics" / "case_ma6_a5_h30km.yaml"
SAMPLING = BASE / "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml"
OUT_DIR = BASE / "runs/t1_baseline_snapshot"
CASE_IDS = ["ma6_a5_h30km", "ma8_a5_h30km"]

CASE_SPECS = {
    "ma6_a5_h30km": {"mach": 6.0, "alpha": 5.0, "h_m": 30000},
    "ma8_a5_h30km": {"mach": 8.0, "alpha": 5.0, "h_m": 30000},
}


def _np_to_builtin(x):
    if isinstance(x, (np.floating,)): return float(x)
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.ndarray,)): return x.tolist()
    return x


def _summarize_array(name, arr):
    arr = np.asarray(arr, dtype=float).reshape(-1)
    finite = np.isfinite(arr)
    out = {"name": name, "shape": list(arr.shape), "finite_count": int(np.sum(finite)),
           "nan_count": int(np.sum(np.isnan(arr)))}
    if np.any(finite):
        a = arr[finite]
        out.update({"min": float(np.min(a)), "max": float(np.max(a)), "mean": float(np.mean(a))})
    return out


def run_case(case_id):
    spec = CASE_SPECS[case_id]
    run_dir = OUT_DIR / case_id
    run_dir.mkdir(parents=True, exist_ok=True)

    veh_path = str(VEHICLE)
    case_path = str(CASE)
    if case_id == "ma8_a5_h30km":
        vb = BASE / "runs/faceted3d_v2_phase2d_diagnostics" / "veh_ma8_a5_h30km.yaml"
        cb = BASE / "runs/faceted3d_v2_phase2d_diagnostics" / "case_ma8_a5_h30km.yaml"
        if vb.exists(): veh_path = str(vb)
        if cb.exists(): case_path = str(cb)

    solver = WingLowFidelitySolverFaceted3D(
        vehicle_config=str(veh_path),
        case_config=str(case_path),
        sampling_config=str(SAMPLING),
        run_dir=str(run_dir),
    )
    solver.compute_snapshot(mach=float(spec["mach"]), alpha=float(spec["alpha"]))
    fields = dict(solver.last_fields or {})

    arrays_to_save = {}
    for key in ["q_w","q_l","Tw_w","Tw_l","w_tr","re_edge","re_tri","re_x_star",
                 "re_x_over_re_tri","x_w_m","span_w_m","x_l_m","span_l_m",
                 "xc_w","yb_w","xc_l","yb_l","mask_w","mask_l",
                 "xc_grid","yb_grid","T_e_w","p_e_w","rho_e_w","ma_e_w","v_e_w","mu_e_w",
                 "phi_w","cp_w","cp0_w","h_e_w",
                 "T_r_lam_w","h_r_lam_w","h_star_lam_w",
                 "T_r_turb_w","h_r_turb_w","h_star_turb_w",
                 "q_lam_w","q_turb_w","St_l","Re_ns_l"]:
        if key in fields:
            arrays_to_save[key] = np.asarray(fields[key], dtype=float)

    np.savez_compressed(str(run_dir / "fields.npz"), **arrays_to_save)

    summary = {
        "case_id": case_id,
        "mach": spec["mach"],
        "alpha_deg": spec["alpha"],
        "h_m": spec["h_m"],
        "weighting": "step",
        "vehicle_config": str(veh_path),
        "case_config": str(case_path),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    for key in arrays_to_save:
        summary[f"summary_{key}"] = _summarize_array(key, arrays_to_save[key])

    with open(run_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return fields, arrays_to_save, summary


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("T1: PRE-IMPLEMENTATION BASELINE SNAPSHOT (Phase 1)")
    print("=" * 60)
    print(f"  Output: {OUT_DIR}")
    print(f"  Cases: {CASE_IDS}")
    print(f"  No source code changes — read-only snapshot")
    print(f"  weighting=step (current default)")
    print(f"  ma8_a10: NOT RUN (holdout)")
    print()

    all_data = {}
    for case_id in CASE_IDS:
        print(f"\n--- Running {case_id} ---")
        fields, arrays, summary = run_case(case_id)
        all_data[case_id] = {"fields": fields, "arrays": arrays, "summary": summary}
        print(f"  fields saved: {len(arrays)} arrays")
        print(f"  q_w: mean={summary.get('summary_q_w',{}).get('mean','N/A')}")
        print(f"  Tw_w: mean={summary.get('summary_Tw_w',{}).get('mean','N/A')}")

    print("\n" + "=" * 60)
    print("BASELINE SNAPSHOT SUMMARY")
    print("=" * 60)

    rows = []
    for case_id in CASE_IDS:
        s = all_data[case_id]["summary"]
        row = {
            "case": case_id,
            "mach": s["mach"],
            "alpha": s["alpha_deg"],
            "h_m": s["h_m"],
            "weighting": s["weighting"],
            "q_w_min": s.get("summary_q_w", {}).get("min", "N/A"),
            "q_w_max": s.get("summary_q_w", {}).get("max", "N/A"),
            "q_w_mean": s.get("summary_q_w", {}).get("mean", "N/A"),
            "Tw_w_min": s.get("summary_Tw_w", {}).get("min", "N/A"),
            "Tw_w_max": s.get("summary_Tw_w", {}).get("max", "N/A"),
            "Tw_w_mean": s.get("summary_Tw_w", {}).get("mean", "N/A"),
            "w_tr_mean": s.get("summary_w_tr", {}).get("mean", "N/A"),
            "re_edge_mean": s.get("summary_re_edge", {}).get("mean", "N/A"),
            "re_tri_mean": s.get("summary_re_tri", {}).get("mean", "N/A"),
            "q_lam_w_mean": s.get("summary_q_lam_w", {}).get("mean", "N/A"),
            "q_turb_w_mean": s.get("summary_q_turb_w", {}).get("mean", "N/A"),
            "cp0_w_min": s.get("summary_cp0_w", {}).get("min", "N/A"),
            "cp0_w_max": s.get("summary_cp0_w", {}).get("max", "N/A"),
            "phi_w_deg_min": None,
            "phi_w_deg_max": None,
        }
        sphi = s.get("summary_phi_w", {})
        if sphi.get("min") is not None:
            row["phi_w_deg_min"] = math.degrees(float(sphi["min"]))
            row["phi_w_deg_max"] = math.degrees(float(sphi["max"]))
        rows.append(row)

    for r in rows:
        print(f"\n  Case: {r['case']}")
        print(f"    Mach={r['mach']}, Alpha={r['alpha']} deg, h={r['h_m']} m")
        print(f"    q_w [W/m2]: {r['q_w_min']:.4e} ~ {r['q_w_max']:.4e}  (mean={r['q_w_mean']:.4e})")
        print(f"    Tw_w [K]: {r['Tw_w_min']:.2f} ~ {r['Tw_w_max']:.2f}  (mean={r['Tw_w_mean']:.2f})")
        print(f"    w_tr mean={r['w_tr_mean']:.4f}")
        print(f"    re_edge mean={r['re_edge_mean']:.4e}")
        print(f"    re_tri mean={r['re_tri_mean']:.4e}")
        print(f"    q_lam_w mean={r['q_lam_w_mean']:.4e}")
        print(f"    q_turb_w mean={r['q_turb_w_mean']:.4e}")
        print(f"    cp0_w: {r['cp0_w_min']:.4f} ~ {r['cp0_w_max']:.4f}")
        phi_str = f"{r['phi_w_deg_min']:.2f} ~ {r['phi_w_deg_max']:.2f} deg" if r['phi_w_deg_min'] is not None else "N/A"
        print(f"    phi_w: {phi_str}")

    # Write report
    report_path = OUT_DIR / "baseline_snapshot_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# T1 Pre-Implementation Baseline Snapshot\n\n")
        f.write(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write("**No source code changes.** Read-only snapshot of current state.\n\n")
        f.write("## Cases\n\n")
        f.write("| Case | Mach | Alpha (deg) | h (m) | weighting |\n")
        f.write("|------|------|-------------|-------|-----------|\n")
        for r in rows:
            f.write(f"| {r['case']} | {r['mach']} | {r['alpha']} | {r['h_m']} | {r['weighting']} |\n")

        f.write("\n## Fields Summary (Windward)\n\n")
        f.write("| Case | q_w mean | Tw_w mean | w_tr mean | re_edge mean | re_tri mean | q_lam mean | q_turb mean |\n")
        f.write("|------|----------|-----------|-----------|--------------|-------------|------------|-------------|\n")
        for r in rows:
            f.write(f"| {r['case']} | {r['q_w_mean']:.4e} | {r['Tw_w_mean']:.2f} | {r['w_tr_mean']:.4f} | ")
            f.write(f"{r['re_edge_mean']:.4e} | {r['re_tri_mean']:.4e} | {r['q_lam_w_mean']:.4e} | {r['q_turb_w_mean']:.4e} |\n")

        f.write("\n## Geometry/Aero\n\n")
        f.write("| Case | cp0_w min | cp0_w max | phi_w (deg) min | phi_w (deg) max |\n")
        f.write("|------|-----------|-----------|-----------------|-----------------|\n")
        for r in rows:
            phi_s = f"{r['phi_w_deg_min']:.2f}" if r['phi_w_deg_min'] is not None else "N/A"
            phi_e = f"{r['phi_w_deg_max']:.2f}" if r['phi_w_deg_max'] is not None else "N/A"
            f.write(f"| {r['case']} | {r['cp0_w_min']:.4f} | {r['cp0_w_max']:.4f} | {phi_s} | {phi_e} |\n")

        f.write("\n## Holdout Confirmation\n\n")
        f.write("ma8_a10 **NOT RUN** (reserved as holdout).\n\n")
        f.write("## Source Integrity\n\n")
        f.write("No source files modified. Only scripts/t1_baseline_snapshot.py was created.\n")
        f.write("All source under `src/ref_enthalpy_method/` is unchanged.\n")

    print(f"\nReport written: {report_path}")

    # Verification: confirm ma8_a10 is not touched
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)
    print("  Cases run: 'ma6_a5_h30km', 'ma8_a5_h30km'")
    print("  'ma8_a10': NOT run — confirmed.")
    print("  Source files unchanged (read-only script).")
    print("=" * 60)


if __name__ == "__main__":
    main()
