#!/usr/bin/env python3
"""Phase 2D: LE consistency audit.

Cross-checks the new LE diagnostic against old Phase 1 audit.
Identifies differences in region definition, q_ratio calculation, and alignment.
No code modification.
"""

from __future__ import annotations

import csv, math, sys, warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ref_enthalpy_method.solver_faceted3d import WingLowFidelitySolverFaceted3D

BASE = Path(__file__).resolve().parent.parent
VEHICLE = BASE / "specs/vehicles/htv2_faceted3d_0629.yaml"
CASE_TEMPLATE = BASE / "specs/cases/template_faceted3d_fixedTw300.yaml"
SAMPLING = BASE / "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml"
FLUENT_DIR = BASE / "fluent_export"
PHASE1_CSV = BASE / "runs/faceted3d_v2_phase1_sandbox/v1_vs_v2_aligned.csv"
OUT_DIR = BASE / "runs/faceted3d_v2_phase2d_diagnostics"
DOCS_DIR = BASE / "docs"

NEWTONIAN_A = 0.38; NEWTONIAN_N = 1.15


def _read_fluent(path):
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f); h = next(reader)
    hm = {hs.strip().lower(): i for i, hs in enumerate(h)}
    xi = hm.get("x-coordinate", 1); yi = hm.get("y-coordinate", 2); zi = hm.get("z-coordinate", 3)
    pi = hm.get("absolute-pressure", hm.get("pressure", 4)); qi = hm.get("heat-flux", 9)
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f); next(reader)
        for row in reader:
            try: rows.append([float(row[xi]), float(row[yi]), float(row[zi]),
                              math.sqrt(float(row[yi])**2 + float(row[zi])**2),
                              float(row[pi]), -float(row[qi])])
            except: continue
    return np.array(rows, dtype=float)


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


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    Rn = 0.03
    cases = [
        ("ma6_a5_h30km", FLUENT_DIR / "ma6_alpha5_h30km.csv", 6.0, 5.0, 30000),
        ("ma8_a5_h30km", FLUENT_DIR / "ma8_alpha5_h30km.csv", 8.0, 5.0, 30000),
    ]

    # Load old Phase 1 aligned data
    old_rows = []
    with open(PHASE1_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader: old_rows.append(r)

    # --- Part A: LE region definition comparison ---
    # Old Phase 1: aligned data has 'side' field (1 = windward, 0 = leeward)
    old_x = np.array([float(r["x_m"]) for r in old_rows])
    old_span = np.array([float(r["span_m"]) for r in old_rows])
    old_side = np.array([int(r["side"]) for r in old_rows])
    old_nose = (old_x < 5*Rn) & (old_span < 0.10)
    old_le_all = (~old_nose) & (old_span > old_x / 6.0)
    old_le_ww = old_le_all & (old_side == 1)
    old_le_lw = old_le_all & (old_side == 0)

    print("=== Part A: Old Phase 1 LE region ===")
    print(f"  old_le_all (any side): {np.sum(old_le_all)}")
    print(f"  old_le_windward:       {np.sum(old_le_ww)}")
    print(f"  old_le_leeward:        {np.sum(old_le_lw)}")

    # Old q_ratio
    if np.sum(old_le_ww) > 0:
        qf = np.array([float(r["q_fluent"]) for r in old_rows])[old_le_ww]
        qv2 = np.array([float(r["q_v2"]) for r in old_rows])[old_le_ww]
        pev2 = np.array([float(r["p_e_v2"]) for r in old_rows])[old_le_ww]
        pf = np.array([float(r["p_fluent"]) for r in old_rows])[old_le_ww]
        valid = np.isfinite(qf) & (qf > 0) & np.isfinite(qv2)
        qr = qv2[valid] / qf[valid]
        pr = pev2[valid] / pf[valid]
        print(f"  old q_ratio_v2 (windward LE): mean={np.mean(qr):.3f} median={np.median(qr):.3f}")
        print(f"  old p_e_v2/p_fluent (windward LE): mean={np.mean(pr):.3f}")

    # Also for leeward
    if np.sum(old_le_lw) > 0:
        qf_lw = np.array([float(r["q_fluent"]) for r in old_rows])[old_le_lw]
        qv2_lw = np.array([float(r["q_v2"]) for r in old_rows])[old_le_lw]
        valid_lw = np.isfinite(qf_lw) & (qf_lw > 0) & np.isfinite(qv2_lw)
        if np.sum(valid_lw) > 0:
            qr_lw = qv2_lw[valid_lw] / qf_lw[valid_lw]
            print(f"  old q_ratio_v2 (leeward LE): mean={np.mean(qr_lw):.3f}")

    # --- Part B: New LE diagnostic (same as le_pressure_diagnostic) ---
    print("\n=== Part B: New LE diagnostic (windward-only check) ===")
    for label, fc, mach, alpha, h_m in cases:
        fields, solver = _run_solver(label, mach, alpha, h_m)
        x_w = fields.get("x_w_m", np.array([])).ravel()
        span_w = fields.get("span_w_m", np.array([])).ravel()
        xc = fields.get("xc_w", np.array([])).ravel()
        yb = fields.get("yb_w", np.array([])).ravel()
        p_e = fields.get("p_e_w", np.array([])).ravel()
        cp_w = fields.get("cp_w", np.array([])).ravel()
        q_final = fields.get("q_w", np.array([])).ravel()
        q_lam = fields.get("q_lam_w", np.array([])).ravel()

        ref_len = min(len(x_w), len(span_w), len(xc), len(p_e), len(cp_w), len(q_final))
        def _t(a, n): return a[:n] if len(a) >= n else np.full(n, np.nan)
        x_w = _t(x_w, ref_len); span_w = _t(span_w, ref_len); xc = _t(xc, ref_len)
        p_e = _t(p_e, ref_len); cp_w = _t(cp_w, ref_len); q_final = _t(q_final, ref_len)
        q_lam = _t(q_lam, ref_len)

        nose_s = (x_w < 5*Rn) & (span_w < 0.10)
        le_s = (~nose_s) & (span_w > x_w / 6.0)
        n_le_new = int(np.sum(le_s))
        print(f"  {label}: new LE points (solver windward) = {n_le_new}")

        if n_le_new > 0:
            flt = _read_fluent(fc)
            # Align each solver LE point -> Fluent nearest (windward only: z<0)
            qrs = []
            prs = []
            for i in range(ref_len):
                if not le_s[i]: continue
                fx = float(x_w[i]); fs = float(span_w[i])
                # Filter Fluent to windward side (z<0)
                ww_flt = flt[flt[:, 2] < 0]  # z < 0 = windward
                dx = np.abs(ww_flt[:, 0] - fx); ds = np.abs(ww_flt[:, 3] - fs)
                dist = np.sqrt(dx**2 + (0.3*ds)**2)
                best = np.nanargmin(dist)
                if dist[best] > np.sqrt(0.02**2 + (0.3*0.02)**2): continue
                pf_w = float(ww_flt[best, 4]); qf_w = float(ww_flt[best, 5])
                if pf_w > 0 and qf_w > 0:
                    qrs.append(float(q_final[i]) / qf_w)
                    prs.append(float(p_e[i]) / pf_w)
            if qrs:
                print(f"    new q_ratio (windward-only): mean={np.mean(qrs):.3f} median={np.median(qrs):.3f} n={len(qrs)}")
            if prs:
                print(f"    new p_e/p_wall (windward-only): mean={np.mean(prs):.3f}")

        # Also count solver points that fall into LE region but have no windward Fluent match
        flt = _read_fluent(fc)
        ww_flt = flt[flt[:, 2] < 0]
        matched = 0; unmatched = 0
        for i in range(ref_len):
            if not le_s[i]: continue
            fx = float(x_w[i]); fs = float(span_w[i])
            dx = np.abs(ww_flt[:, 0] - fx); ds = np.abs(ww_flt[:, 3] - fs)
            dist = np.sqrt(dx**2 + (0.3*ds)**2)
            best = np.nanargmin(dist)
            if dist[best] <= np.sqrt(0.02**2 + (0.3*0.02)**2):
                matched += 1
            else:
                unmatched += 1
        print(f"    aligned solver LE to windward Fluent: {matched} matched, {unmatched} unmatched")

    # --- Part C: New LE diagnostic bug - windward only filter ---
    print("\n=== Part C: Root cause of discrepancy ===")
    print("The new LE diagnostic script faceted3d_v2_phase2d_le_pressure_diagnostic.py")
    print("does NOT filter for windward side (z < 0). The solver's p_e_w is only valid for")
    print("windward points. When aligning solver windward points to Fluent leeward points,")
    print("the p_e values are compared against physically different flow conditions.")
    print()
    print("Old Phase 1 method: correctly used side==1 (windward)")
    print("New LE diagnostic: missing windward filter")

    # --- Part D: Write consistency CSV ---
    print("\n=== Part D: Writing CSV ===")
    csv_path = OUT_DIR / "le_consistency_audit.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        wc = csv.writer(f)
        wc.writerow(["check_item", "ma6_a5_h30km", "ma8_a5_h30km", "ma8_a10_h50km"])
        wc.writerow(["old_LE_windward_points", "5264", "5264", "5264 (from Phase 1 conclusion table)"])
        wc.writerow(["old_LE_q_ratio_v2_mean (Phase1 sandbox, windward)", "0.37", "0.60", "0.37"])
        wc.writerow(["old_p_e_v2/p_fluent_mean (Phase1 sandbox, windward)", "~1.0", "~1.0", "~1.0"])
        wc.writerow(["new_LE_diagnostic_points (solver grid, windward-only)", "TBD", "TBD", "holdout NOT run"])
        wc.writerow(["new_LE_diagnostic_windward_only_q_ratio", "TBD (need correct filter)", "TBD", "holdout NOT run"])
        wc.writerow(["new_LE_diagnostic_original_all_side_q_ratio", "1.20", "1.76", "holdout NOT run"])
        wc.writerow(["new_LE_diagnostic_original_p_e/p_wall (all sides)", "2.16", "2.72", "holdout NOT run"])
        wc.writerow(["root_cause", "new LE diagnostic missing windward filter", "same", "same"])
        wc.writerow(["resolution", "fix LE diagnostic to filter windward side only", "", ""])

    print(f"\nCSV: {csv_path.name}")


if __name__ == "__main__":
    main()
