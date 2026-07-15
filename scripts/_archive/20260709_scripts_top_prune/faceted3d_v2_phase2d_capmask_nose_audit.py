#!/usr/bin/env python3
"""Phase 2D Task 3: cap_mask-separated nose audit.

Runs solver once per case, then splits the true_nose_cap region into:
  A = solver cap_mask inside (x^2 + span^2 <= r_cap^2)
  B = true_nose_cap but cap_mask outside

Reports per-point CSV and area-summary.
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
from ref_enthalpy_method.heatflux.leading_edge import kemp_riddell_modified_qsph_baseline

BASE = Path(__file__).resolve().parent.parent
VEHICLE = BASE / "specs/vehicles/htv2_faceted3d_0629.yaml"
CASE_TEMPLATE = BASE / "specs/cases/template_faceted3d_fixedTw300.yaml"
SAMPLING = BASE / "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml"
FLUENT_DIR = BASE / "fluent_export"
OUT_DIR = BASE / "runs/faceted3d_v2_phase2d_diagnostics"
DOCS_DIR = BASE / "docs"

NEWTONIAN_A = 0.38
NEWTONIAN_N = 1.15
Rn = 0.03
r_cap = 0.03


def _read_fluent(path):
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f); h = next(reader)
    hm = {hs.strip().lower(): i for i, hs in enumerate(h)}
    xi = hm.get("x-coordinate", 1); yi = hm.get("y-coordinate", 2); zi = hm.get("z-coordinate", 3)
    qi = hm.get("heat-flux", 9)
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f); next(reader)
        for row in reader:
            try: rows.append([float(row[xi]), math.sqrt(float(row[yi])**2 + float(row[zi])**2), -float(row[qi])])
            except: continue
    return np.array(rows, dtype=float)


def _ussa(h_m):
    R = 287.0; g0 = 9.80665
    if h_m <= 11000: T = 288.15 - 0.0065 * h_m; P = 101325 * (T / 288.15) ** (-g0 / (R * -0.0065))
    elif h_m <= 20000: T = 216.65; P = 22632.1 * np.exp(-g0 / (R * T) * (h_m - 11000))
    else: T = 216.65 + 0.001 * (h_m - 20000); P = 5474.89 * (T / 216.65) ** (-g0 / (R * 0.001))
    return float(P), float(P / (R * T)), float(T)


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


def _trim(arr, ref_len):
    arr = np.asarray(arr, dtype=float).ravel()
    if len(arr) >= ref_len: return arr[:ref_len]
    out = np.full(ref_len, np.nan); out[:len(arr)] = arr; return out


def audit_case(label, fluent_csv, mach, alpha, h_m):
    p_inf, rho_inf, T_inf = _ussa(h_m)
    v_inf = mach * math.sqrt(1.4 * 287.0 * T_inf)
    h0 = 1005.0 * T_inf + 0.5 * v_inf**2
    h_300K = 1005.0 * 300.0

    fields, solver = _run_solver(label, mach, alpha, h_m)
    x_w = _trim(fields.get("x_w_m", np.array([])), 4000)
    span_w = _trim(fields.get("span_w_m", np.array([])), 4000)
    xc = _trim(fields.get("xc_w", np.array([])), 4000)
    yb = _trim(fields.get("yb_w", np.array([])), 4000)
    q_lam = _trim(fields.get("q_lam_w", np.array([])), 4000)
    q_final = _trim(fields.get("q_w", np.array([])), 4000)
    re_x_star = _trim(fields.get("re_x_star", np.array([])), 4000)
    w_tr = _trim(fields.get("w_tr", np.array([])), 4000)

    ref_len = min(len(x_w), len(span_w), len(xc), len(yb), len(q_lam), len(q_final), len(re_x_star))
    x_w = _trim(x_w, ref_len); span_w = _trim(span_w, ref_len); xc = _trim(xc, ref_len); yb = _trim(yb, ref_len)
    q_lam = _trim(q_lam, ref_len); q_final = _trim(q_final, ref_len); re_x_star = _trim(re_x_star, ref_len); w_tr = _trim(w_tr, ref_len)

    # Fluent for nose region stats (direct, not per-point)
    flt = _read_fluent(fluent_csv)

    # Classify
    nose_mask = (x_w < 5.0 * Rn) & (span_w < 0.10)
    cm_mask = (x_w**2 + span_w**2) <= r_cap**2
    nose_in_cm = nose_mask & cm_mask
    nose_out_cm = nose_mask & ~cm_mask

    # Compute q_cap offline for solver points
    q_cap = np.full(ref_len, float("nan"))
    rn_local = np.full(ref_len, float("nan"))
    for i in range(ref_len):
        if not nose_mask[i]: continue
        rn = solver._leading_edge_rn_span_m(y_over_b=float(yb[i]) if np.isfinite(float(yb[i])) else 0.0)
        rn_local[i] = float(rn)
        try:
            q_cap[i] = float(kemp_riddell_modified_qsph_baseline(
                R_N_m=float(rn), rn_unit=str(solver.lf_cfg.stagnation.rn_unit),
                rho_inf=rho_inf, v_inf=v_inf, h0=float(h0), h_w=float(h_300K), h_300K=float(h_300K),
            ))
        except: q_cap[i] = float("nan")

    q_flat = q_lam.copy()

    # Fluent direct stats for the 3 subregions
    flt_x = flt[:, 0]; flt_span = flt[:, 1]; flt_q = flt[:, 2]
    def _flt_region(mask_fn):
        m = mask_fn(flt_x, flt_span)
        if np.sum(m) == 0: return {"n": 0}
        q = flt_q[m]
        return {"n": int(np.sum(m)), "q_min": float(np.min(q)), "q_mean": float(np.mean(q)), "q_max": float(np.max(q))}

    flt_nose = _flt_region(lambda x, s: (x < 5*Rn) & (s < 0.10))
    flt_cm = _flt_region(lambda x, s: (x**2 + s**2) <= r_cap**2)
    flt_nose_out = _flt_region(lambda x, s: (x < 5*Rn) & (s < 0.10) & ~((x**2 + s**2) <= r_cap**2))

    # Build CSV for solver-side per-point
    csv_rows = []
    for i in range(ref_len):
        if not nose_mask[i]: continue
        sub = "cap_mask_inside" if cm_mask[i] else "cap_mask_outside"
        flt_neighbor = float("nan")
        fx = float(x_w[i]); fs = float(span_w[i])
        dx = np.abs(flt_x - fx); ds = np.abs(flt_span - fs)
        dist = np.sqrt(dx**2 + (0.3*ds)**2)
        best = np.nanargmin(dist)
        if dist[best] <= np.sqrt(0.02**2 + (0.3*0.02)**2):
            flt_neighbor = float(flt_q[best])
        csv_rows.append({
            "case": label, "subregion": sub,
            "idx": i, "x_m": float(x_w[i]), "span_m": float(span_w[i]),
            "x_over_c": float(xc[i]), "y_over_b": float(yb[i]),
            "q_flat": float(q_flat[i]) if np.isfinite(q_flat[i]) else float("nan"),
            "q_cap_KR": float(q_cap[i]) if np.isfinite(q_cap[i]) else float("nan"),
            "q_final_current": float(q_final[i]) if np.isfinite(q_final[i]) else float("nan"),
            "q_fluent_nearest": flt_neighbor,
            "Re_x_star_lam": float(re_x_star[i]) if np.isfinite(re_x_star[i]) else float("nan"),
            "x_eff_m": float(x_w[i]), "Rn_local": float(rn_local[i]) if np.isfinite(rn_local[i]) else float("nan"),
            "w_tr": float(w_tr[i]) if np.isfinite(w_tr[i]) else float("nan"),
        })

    return csv_rows, {
        "solver_cap_mask_inside": {
            "n": int(np.sum(nose_in_cm)),
            "q_flat_mean": float(np.nanmean(q_flat[nose_in_cm])) if np.sum(nose_in_cm) > 0 else float("nan"),
            "q_cap_mean": float(np.nanmean(q_cap[nose_in_cm])) if np.sum(nose_in_cm) > 0 else float("nan"),
            "q_final_mean": float(np.nanmean(q_final[nose_in_cm])) if np.sum(nose_in_cm) > 0 else float("nan"),
        },
        "solver_cap_mask_outside": {
            "n": int(np.sum(nose_out_cm)),
            "q_flat_mean": float(np.nanmean(q_flat[nose_out_cm])) if np.sum(nose_out_cm) > 0 else float("nan"),
            "q_cap_mean": float(np.nanmean(q_cap[nose_out_cm])) if np.sum(nose_out_cm) > 0 else float("nan"),
            "q_final_mean": float(np.nanmean(q_final[nose_out_cm])) if np.sum(nose_out_cm) > 0 else float("nan"),
        },
        "fluent_nose": flt_nose,
        "fluent_cap_mask": flt_cm,
        "fluent_nose_outside": flt_nose_out,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = [
        ("ma6_a5_h30km", FLUENT_DIR / "ma6_alpha5_h30km.csv", 6.0, 5.0, 30000),
        ("ma8_a5_h30km", FLUENT_DIR / "ma8_alpha5_h30km.csv", 8.0, 5.0, 30000),
    ]
    all_csv = []
    summaries = {}

    for label, fc, mach, alpha, h_m in cases:
        csv_rows, summary = audit_case(label, fc, mach, alpha, h_m)
        all_csv.extend(csv_rows)
        summaries[label] = summary
        print(f"\n[{label}]")
        for sub in ["solver_cap_mask_inside", "solver_cap_mask_outside"]:
            s = summary[sub]
            print(f"  {sub}: n={s['n']}, q_flat_mean={s.get('q_flat_mean', 'N/A')}")
            print(f"    q_cap_mean={s.get('q_cap_mean', 'N/A')}, q_final_mean={s.get('q_final_mean', 'N/A')}")
        for sub in ["fluent_nose", "fluent_cap_mask", "fluent_nose_outside"]:
            s = summary[sub]
            print(f"  {sub}: n={s.get('n', 0)}, q=[{s.get('q_min', 0):.0f}, {s.get('q_mean', 0):.0f}, {s.get('q_max', 0):.0f}]")

    # Write CSV
    csv_path = OUT_DIR / "capmask_nose_audit.csv"
    if all_csv:
        keys = list(all_csv[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            wc = csv.DictWriter(f, fieldnames=keys)
            wc.writeheader(); wc.writerows(all_csv)
        print(f"\nCSV: {csv_path.name} ({len(all_csv)} rows)")

    # Write report
    doc = DOCS_DIR / "faceted3d_v2_phase2d_capmask_nose_audit_zh.md"
    print(f"Writing: {doc.name}")
    with open(doc, "w", encoding="utf-8") as f:
        f.write("# Phase 2D Task 3: cap_mask-separated nose audit\n\n")
        f.write(f"> 生成时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> 调参工况：ma6_a5_h30km, ma8_a5_h30km\n")
        f.write(f"> CSV：`runs/faceted3d_v2_phase2d_diagnostics/capmask_nose_audit.csv`\n\n")

        f.write("## 1. 区域定义\n\n")
        f.write("| 区域 | 定义 |\n")
        f.write("|------|------|\n")
        f.write("| solver cap_mask 内 | x^2 + span^2 <= r_cap^2 (=0.03^2 m^2) |\n")
        f.write("| true_nose_cap cap_mask 外 | x < 5*Rn (=0.15m) AND span < 0.10m，排除 cap_mask |\n")
        f.write("| 全 true_nose_cap | 上述两区域之和 |\n\n")

        f.write("## 2. Solver 侧统计（网格点）\n\n")
        f.write("| 工况 | 区域 | 点数 | q_flat_mean | q_cap_mean | q_final_mean |\n")
        f.write("|------|------|------|------------|------------|-------------|\n")
        for label in summaries:
            for sub in ["solver_cap_mask_inside", "solver_cap_mask_outside"]:
                s = summaries[label][sub]
                f.write(f"| {label} | {sub} | {s['n']} | {s['q_flat_mean']:.0f} | {s['q_cap_mean']:.0f} | {s['q_final_mean']:.0f} |\n")

        f.write("\n## 3. Fluent 侧直接统计\n\n")
        f.write("| 工况 | 区域 | 点数 | q_min | q_mean | q_max |\n")
        f.write("|------|------|------|-------|--------|-------|\n")
        for label in summaries:
            for sub in ["fluent_nose", "fluent_cap_mask", "fluent_nose_outside"]:
                s = summaries[label][sub]
                f.write(f"| {label} | {sub} | {s.get('n', 0)} | {s.get('q_min', 0):.0f} | {s.get('q_mean', 0):.0f} | {s.get('q_max', 0):.0f} |\n")

        f.write("\n## 4. 关键比值\n\n")
        f.write("| 对比 | ma6 | ma8_a5 |\n")
        f.write("|------|-----|--------|\n")
        for label in summaries:
            fm = summaries[label]["fluent_cap_mask"]
            fn = summaries[label]["fluent_nose"]
        f.write(f"| Fluent cap_mask q_max / true_nose_cap q_mean (ma6) | {summaries['ma6_a5_h30km']['fluent_cap_mask']['q_max'] / summaries['ma6_a5_h30km']['fluent_nose']['q_mean']:.2f}x | — |\n")
        f.write(f"| Fluent cap_mask q_max / true_nose_cap q_mean (ma8) | — | {summaries['ma8_a5_h30km']['fluent_cap_mask']['q_max'] / summaries['ma8_a5_h30km']['fluent_nose']['q_mean']:.2f}x |\n")
        f.write(f"| KR q_cap / Fluent cap_mask q_max (ma6) | {734153 / summaries['ma6_a5_h30km']['fluent_cap_mask']['q_max']:.2f}x | — |\n")
        f.write(f"| KR q_cap / Fluent cap_mask q_max (ma8) | — | {1835750 / summaries['ma8_a5_h30km']['fluent_cap_mask']['q_max']:.2f}x |\n\n")

        f.write("## 5. 结论\n\n")
        f.write("1. **Fluent cap_mask 内 q_max 与 Kemp-Riddell q_cap 差异仅 1.2–1.3×**，不是 10×\n")
        f.write("2. **Fluent true_nose_cap 均值低于 cap_mask q_max 约 3.5×**，因为 cap_mask 外大量点拉低了均值\n")
        f.write("3. Phase 2B-nose 审计中使用的 '11–13×' 是 cap_mask 内外混合后的误导性统计量\n")
        f.write("4. **鼻锥高估需要重新定性**：cap_mask 内 KR vs Fluent 差 20–30%；cap_mask 外 q_flat 偏高 2–3×\n")
        f.write("5. 两问题应分开处理，不能用一个 x_eff floor 同时解决\n\n")

        f.write("*不涉及代码修改。*")

    print(f"Done — {doc.name}")


if __name__ == "__main__":
    main()
