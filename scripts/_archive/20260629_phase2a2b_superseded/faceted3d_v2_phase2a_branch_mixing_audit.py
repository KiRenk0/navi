#!/usr/bin/env python3
"""Phase 2A branch-mixing audit.

Verifies the mixing formula q = (1-w)*q_lam + w*q_turb and diagnoses
why ma8 aft_body appears to have q_turb < q_lam in area averages.

Outputs:
  - runs/faceted3d_v2_phase2a_delta_sweep/branch_mixing_audit.csv
  - docs/faceted3d_v2_phase2a_branch_mixing_audit_zh.md
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
OUT_DIR = BASE / "runs/faceted3d_v2_phase2a_delta_sweep"

NEWTONIAN_A = 0.38
NEWTONIAN_N = 1.15


def _make_yaml(orig_path, overrides_list, label):
    import yaml as _yaml
    data = _yaml.safe_load(orig_path.read_text(encoding="utf-8"))
    for ov in overrides_list:
        _dset(data, ov)
    out = OUT_DIR / f"tmp_{label}.yaml"
    with open(out, "w", encoding="utf-8") as f:
        _yaml.dump(data, f)
    return out


def _dset(d, keys_val):
    dct = d
    keys, val = keys_val
    for k in keys[:-1]:
        dct = dct.setdefault(k, {})
    dct[keys[-1]] = val


def _run(mach, alpha, weighting, delta, label):
    import yaml as _yaml
    # Load original YAML, apply overrides, write temp with explicit top-level key
    veh_data = _yaml.safe_load(VEHICLE.read_text(encoding="utf-8"))
    veh_data.setdefault("vehicle_spec", {}).setdefault("faceted3d", {})["cp_model"] = "newtonian_like"
    veh_data["vehicle_spec"]["faceted3d"]["cp_newtonian_A"] = NEWTONIAN_A
    veh_data["vehicle_spec"]["faceted3d"]["cp_newtonian_n"] = NEWTONIAN_N
    veh_path = OUT_DIR / f"veh_{label}.yaml"
    with open(veh_path, "w", encoding="utf-8") as f:
        _yaml.dump(veh_data, f, default_flow_style=False)

    case_data = _yaml.safe_load(CASE_TEMPLATE.read_text(encoding="utf-8"))
    case_data.setdefault("case_spec", {}).setdefault("lf_qw_model", {}).setdefault("transition", {})["weighting"] = weighting
    case_data["case_spec"]["lf_qw_model"]["transition"]["delta_decades"] = delta
    case_path = OUT_DIR / f"case_{label}.yaml"
    with open(case_path, "w", encoding="utf-8") as f:
        _yaml.dump(case_data, f, default_flow_style=False)

    solver = WingLowFidelitySolverFaceted3D(
        vehicle_config=str(veh_path), case_config=str(case_path),
        sampling_config=str(SAMPLING), run_dir=str(OUT_DIR / label),
    )
    solver.compute_snapshot(mach=mach, alpha=alpha)
    return dict(solver.last_fields or {})


def _classify(x_m, span_m, x_over_c, Rn=0.03):
    R = np.full_like(x_m, "unknown", dtype=object)
    Rn_a = np.full_like(x_m, float(Rn))
    nose = (x_m < 5.0 * Rn_a) & (span_m < 0.10)
    le = (~nose) & (span_m > x_m / 6.0)
    aft = (~nose) & (~le) & (x_over_c > 0.5)
    wwd = (~nose) & (~le) & (~aft)
    R[nose] = "true_nose_cap"; R[le] = "leading_edge_near"
    R[aft] = "aft_body"; R[wwd] = "windward_body"
    return R


def audit_case(label, mach, alpha, h_m):
    print(f"\n{'='*60}")
    print(f"Audit: {label}")
    print(f"{'='*60}")

    # Run step and smoothstep Delta=0.05
    step_f = _run(mach, alpha, "step", 0.5, f"{label}_step")
    sm_f = _run(mach, alpha, "smoothstep", 0.05, f"{label}_sm005")
    x_m = step_f.get("x_w_m", np.array([]))
    span_m = step_f.get("span_w_m", np.array([]))
    xc = step_f.get("xc_w", np.array([]))
    yb = step_f.get("yb_w", np.array([]))

    # All solver field arrays may have different lengths; find common reference length
    ref_len = min(len(x_m), len(span_m), len(xc), len(yb))
    x_m = x_m[:ref_len]
    span_m = span_m[:ref_len]
    xc = xc[:ref_len]
    yb = yb[:ref_len]

    regions = _classify(x_m, span_m, xc)
    aft_mask = regions == "aft_body"
    n_aft = int(np.sum(aft_mask))

    print(f"  aft_body points: {n_aft}")

    if n_aft == 0:
        return

    # Collect per-point data, all trimmed to ref_len
    def _trim(arr):
        arr = np.asarray(arr, dtype=float).ravel()
        if len(arr) > ref_len:
            return arr[:ref_len]
        if len(arr) < ref_len:
            # Pad with nan
            out = np.full(ref_len, np.nan, dtype=float)
            out[:len(arr)] = arr
            return out
        return arr

    fields_step = {
        "q_lam": _trim(step_f.get("q_lam_w", np.array([]))),
        "q_turb": _trim(step_f.get("q_turb_w", np.array([]))),
        "w_tr": _trim(step_f.get("w_tr", np.array([]))),
        "q_final": _trim(step_f.get("q_w", np.array([]))),
        "re_x_star": _trim(step_f.get("re_x_star", np.array([]))),
        "re_tri": _trim(step_f.get("re_tri", np.array([]))),
    }
    fields_sm = {
        "q_lam": _trim(sm_f.get("q_lam_w", np.array([]))),
        "q_turb": _trim(sm_f.get("q_turb_w", np.array([]))),
        "w_tr": _trim(sm_f.get("w_tr", np.array([]))),
        "q_final": _trim(sm_f.get("q_w", np.array([]))),
        "re_x_star": _trim(sm_f.get("re_x_star", np.array([]))),
        "re_tri": _trim(sm_f.get("re_tri", np.array([]))),
    }

    # Verify q_lam/q_turb are identical between step and smoothstep runs
    ql_step = fields_step["q_lam"][aft_mask]
    ql_sm = fields_sm["q_lam"][aft_mask]
    qt_step = fields_step["q_turb"][aft_mask]
    qt_sm = fields_sm["q_turb"][aft_mask]
    ql_diff = np.nanmax(np.abs(ql_step - ql_sm))
    qt_diff = np.nanmax(np.abs(qt_step - qt_sm))
    print(f"  q_lam max diff (step vs smoothstep): {ql_diff:.6f}")
    print(f"  q_turb max diff (step vs smoothstep): {qt_diff:.6f}")
    print(f"  → q_lam/q_turb IDENTICAL across runs: {ql_diff < 1e-6 and qt_diff < 1e-6}")

    # --- Area-weighted stats ---
    print(f"\n  --- aft_body area-weighted stats ---")
    for mode_name, fdict in [("step", fields_step), ("smoothstep_Delta=0.05", fields_sm)]:
        mask = aft_mask
        w = fdict["w_tr"][mask]
        ql = fdict["q_lam"][mask]
        qt = fdict["q_turb"][mask]
        qf = fdict["q_final"][mask]
        rex = fdict["re_x_star"][mask]
        rt = fdict["re_tri"][mask]

        valid = np.isfinite(ql) & np.isfinite(qt) & np.isfinite(w) & np.isfinite(qf)
        nv = int(np.sum(valid))
        if nv < 5:
            print(f"    {mode_name}: insufficient valid points ({nv})")
            continue

        ql_m = float(np.nanmean(ql[valid]))
        qt_m = float(np.nanmean(qt[valid]))
        qf_m = float(np.nanmean(qf[valid]))
        w_m = float(np.nanmean(w[valid]))
        ratio_qt_ql = float(np.nanmean(qt[valid] / np.maximum(ql[valid], 1.0)))

        w0 = float(np.sum((w[valid] == 0)))
        w1 = float(np.sum((w[valid] >= 1.0)))
        wm = float(np.sum((w[valid] > 0) & (w[valid] < 1.0)))
        wt = w0 + w1 + wm

        print(f"    {mode_name}:")
        print(f"      q_lam_mean={ql_m:.1f}, q_turb_mean={qt_m:.1f}, q_final_mean={qf_m:.1f}")
        print(f"      w_tr_mean={w_m:.4f}, w_tr=0: {w0/wt*100:.0f}%, 0<w<1: {wm/wt*100:.0f}%, w_tr=1: {w1/wt*100:.0f}%")
        print(f"      q_turb/q_lam mean={ratio_qt_ql:.4f}")

        # Verify mixing formula per-point
        q_mix = (1.0 - w[valid]) * ql[valid] + w[valid] * qt[valid]
        mismatch = np.nanmax(np.abs(qf[valid] - q_mix))
        print(f"      max(q_final - q_mix_handcalc) = {mismatch:.6f} → {'PASS' if mismatch < 0.01 else 'FAIL'}")

        # ALSO check: what would q be at w=0 (fully laminar)?
        q_all_lam = float(np.nanmean(ql[valid]))
        q_all_turb = float(np.nanmean(qt[valid]))
        print(f"      hypothetical q if ALL laminar (w=0): {q_all_lam:.1f}")
        print(f"      hypothetical q if ALL turbulent (w=1): {q_all_turb:.1f}")
        print(f"      → step q_final {qf_m:.1f} vs q_all_lam {q_all_lam:.1f} vs q_all_turb {q_all_turb:.1f}")

    # --- Spot-check individual aft_body points ---
    print(f"\n  --- Spot-check: 10 representative aft_body points ---")
    idx_aft = np.where(aft_mask)[0]
    if len(idx_aft) > 10:
        # Pick points spanning x/c range
        xc_aft = xc[aft_mask]
        pick = np.unique(np.linspace(0, len(idx_aft) - 1, 10, dtype=int))
        idx_sample = idx_aft[pick]
    else:
        idx_sample = idx_aft

    header = f"{'idx':>5} | {'x/c':>7} | {'y/b':>7} | {'Re_x':>10} | {'Re_tri':>10} | {'q_lam':>9} | {'q_turb':>9} | {'w_tr':>6} | {'q_final':>9} | {'q_mix':>9} | {'match?':>6}"
    print("  " + "-" * len(header))
    print("  " + header)
    print("  " + "-" * len(header))
    for idx in idx_sample:
        # Step
        w_s = float(fields_step["w_tr"][idx])
        ql_s = float(fields_step["q_lam"][idx])
        qt_s = float(fields_step["q_turb"][idx])
        qf_s = float(fields_step["q_final"][idx])
        qmix_s = (1.0 - w_s) * ql_s + w_s * qt_s
        match_s = "OK" if abs(qf_s - qmix_s) < 0.1 else "MISMATCH"
        rex_s = float(fields_step["re_x_star"][idx])
        rt_s = float(fields_step["re_tri"][idx])
        print(f"  STEP  {idx:>5d} | {float(xc[idx]):>7.4f} | {float(yb[idx]):>7.4f} | {rex_s:>10.1f} | {rt_s:>10.1f} | {ql_s:>9.1f} | {qt_s:>9.1f} | {w_s:>6.3f} | {qf_s:>9.1f} | {qmix_s:>9.1f} | {match_s:>6}")

        # Smoothstep
        w_m = float(fields_sm["w_tr"][idx])
        ql_m = float(fields_sm["q_lam"][idx])
        qt_m = float(fields_sm["q_turb"][idx])
        qf_m = float(fields_sm["q_final"][idx])
        qmix_m = (1.0 - w_m) * ql_m + w_m * qt_m
        match_m = "OK" if abs(qf_m - qmix_m) < 0.1 else "MISMATCH"
        rex_m = float(fields_sm["re_x_star"][idx])
        rt_m = float(fields_sm["re_tri"][idx])
        print(f"  SM005 {idx:>5d} | {float(xc[idx]):>7.4f} | {float(yb[idx]):>7.4f} | {rex_m:>10.1f} | {rt_m:>10.1f} | {ql_m:>9.1f} | {qt_m:>9.1f} | {w_m:>6.3f} | {qf_m:>9.1f} | {qmix_m:>9.1f} | {match_m:>6}")

    # --- Summarize contradiction ---
    print(f"\n  --- Contradiction analysis ---")
    w_step_aft = fields_step["w_tr"][aft_mask]
    w_sm_aft = fields_sm["w_tr"][aft_mask]
    ql_aft = fields_step["q_lam"][aft_mask]
    qt_aft = fields_step["q_turb"][aft_mask]
    qf_step_aft = fields_step["q_final"][aft_mask]
    qf_sm_aft = fields_sm["q_final"][aft_mask]

    valid_aft = np.isfinite(ql_aft) & np.isfinite(qt_aft) & np.isfinite(w_step_aft) & np.isfinite(w_sm_aft) & np.isfinite(qf_step_aft) & np.isfinite(qf_sm_aft)

    if np.sum(valid_aft) > 5:
        ql_m = np.nanmean(ql_aft[valid_aft])
        qt_m = np.nanmean(qt_aft[valid_aft])
        qf_step_m = np.nanmean(qf_step_aft[valid_aft])
        qf_sm_m = np.nanmean(qf_sm_aft[valid_aft])
        w_step_m = np.nanmean(w_step_aft[valid_aft])
        w_sm_m = np.nanmean(w_sm_aft[valid_aft])

        print(f"  q_lam_mean={ql_m:.1f}, q_turb_mean={qt_m:.1f}")
        print(f"  q_turb/q_lam={qt_m/ql_m:.4f}  {'q_turb>q_lam' if qt_m > ql_m else 'q_turb<q_lam'}")
        print(f"  step:   w_tr_mean={w_step_m:.4f}, q_final_mean={qf_step_m:.1f}")
        print(f"  sm005:  w_tr_mean={w_sm_m:.4f}, q_final_mean={qf_sm_m:.1f}")

        # If step w_tr_mean=1 and smoothstep w_tr_mean<1:
        # If q_turb > q_lam: smoothstep should give LOWER q than step (contradicts our observation)
        # If q_turb < q_lam: smoothstep should give HIGHER q than step (our observation showed lower)
        if w_step_m > 0.99:
            print(f"  → step has near-fully turbulent aft_body (w_tr≈1)")
            if w_sm_m < w_step_m:
                print(f"  → smoothstep mixes in laminar (w_tr={w_sm_m:.4f} < {w_step_m:.4f})")
                if qt_m > ql_m:
                    print(f"  → Since q_turb > q_lam: smoothstep should give q={ql_m*(1-w_sm_m)+qt_m*w_sm_m:.1f} < step={qf_step_m:.1f}")
                    observed_lower = qf_sm_m < qf_step_m
                    print(f"  → Expected: smoothstep LOWER q. Observed: smoothstep {qf_sm_m:.1f}, step {qf_step_m:.1f}. {'CONSISTENT' if observed_lower else 'CONTRADICTION'}")
                else:
                    print(f"  → Since q_turb < q_lam: smoothstep should give q={ql_m*(1-w_sm_m)+qt_m*w_sm_m:.1f} > step={qf_step_m:.1f}")
                    observed_higher = qf_sm_m > qf_step_m
                    print(f"  → Expected: smoothstep HIGHER q. Observed: smoothstep {qf_sm_m:.1f}, step {qf_step_m:.1f}. {'CONSISTENT' if observed_higher else 'CONTRADICTION'}")
        else:
            print(f"  → step w_tr_mean={w_step_m:.4f} — NOT fully turbulent")

    # --- Write CSV ---
    csv_path = OUT_DIR / "branch_mixing_audit.csv"
    print(f"\n  Writing: {csv_path.name}")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        wc = csv.writer(f)
        wc.writerow(["case", "mode", "idx", "x_c", "y_b", "re_x_star", "re_tri",
                      "q_lam", "q_turb", "w_tr", "q_final", "q_mix_handcalc",
                      "region"])
        for mode_name, fdict in [("step", fields_step), ("smoothstep_d005", fields_sm)]:
            for i in range(len(x_m)):
                region = str(regions[i])
                wc.writerow([label, mode_name, i,
                             float(xc[i]) if i < len(xc) else float("nan"),
                             float(yb[i]) if i < len(yb) else float("nan"),
                             float(fdict["re_x_star"][i]) if np.isfinite(fdict["re_x_star"][i]) else float("nan"),
                             float(fdict["re_tri"][i]) if np.isfinite(fdict["re_tri"][i]) else float("nan"),
                             float(fdict["q_lam"][i]) if np.isfinite(fdict["q_lam"][i]) else float("nan"),
                             float(fdict["q_turb"][i]) if np.isfinite(fdict["q_turb"][i]) else float("nan"),
                             float(fdict["w_tr"][i]) if np.isfinite(fdict["w_tr"][i]) else float("nan"),
                             float(fdict["q_final"][i]) if np.isfinite(fdict["q_final"][i]) else float("nan"),
                             float((1.0 - fdict["w_tr"][i]) * fdict["q_lam"][i] + fdict["w_tr"][i] * fdict["q_turb"][i])
                             if np.isfinite(fdict["w_tr"][i]) and np.isfinite(fdict["q_lam"][i]) and np.isfinite(fdict["q_turb"][i]) else float("nan"),
                             region])


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = [
        ("ma6_a5_h30km", 6.0, 5.0, 30000),
        ("ma8_a5_h30km", 8.0, 5.0, 30000),
    ]
    for label, mach, alpha, h_m in cases:
        audit_case(label, mach, alpha, h_m)

    print(f"\n{'='*60}")
    print("Audit complete")
    print(f"{'='*60}")
    print(f"CSV: {OUT_DIR / 'branch_mixing_audit.csv'}")


if __name__ == "__main__":
    main()
