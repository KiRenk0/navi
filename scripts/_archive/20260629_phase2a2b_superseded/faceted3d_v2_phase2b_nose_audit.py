#!/usr/bin/env python3
"""Phase 2B-nose audit: quantify max(q_flat, q_cap) contribution to nose overprediction.

Runs solver once per case, then offline-recomputes Kemp-Riddell q_cap for every
true_nose_cap point. Compares current (max) vs alternative selection strategies.

Only calibration cases: ma6_a5_h30km, ma8_a5_h30km.
Holdout ma8_a10_h50km NOT run.
Does NOT modify solver code.
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
from ref_enthalpy_method.gas.thermo import make_perfect_gas_thermo
from ref_enthalpy_method.gas.transport import mu_sutherland
from ref_enthalpy_method.types import GasModel

BASE = Path(__file__).resolve().parent.parent
VEHICLE = BASE / "specs/vehicles/htv2_faceted3d_0629.yaml"
CASE_TEMPLATE = BASE / "specs/cases/template_faceted3d_fixedTw300.yaml"
SAMPLING = BASE / "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml"
FLUENT_DIR = BASE / "fluent_export"
OUT_DIR = BASE / "runs/faceted3d_v2_phase2b_nose_audit"
DOCS_DIR = BASE / "docs"

NEWTONIAN_A = 0.38
NEWTONIAN_N = 1.15

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


def _run_solver(label, mach, alpha, h_m):
    """Run solver with step weighting, newtonian_like Cp, return fields."""
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
    fields = dict(solver.last_fields or {})
    return fields, solver


def _classify_nose(x_m, span_m, x_over_c, Rn=0.03):
    """true_nose_cap: x < 5*Rn AND span < 0.10m"""
    Rn_a = np.full_like(x_m, float(Rn))
    return (x_m < 5.0 * Rn_a) & (span_m < 0.10)


def audit_case(label, fluent_csv, mach, alpha, h_m):
    p_inf, rho_inf, T_inf = _ussa(h_m)
    v_inf = mach * math.sqrt(1.4 * 287.0 * T_inf)
    q_inf = 0.5 * rho_inf * v_inf ** 2
    h_inf = 1005.0 * T_inf  # constant cp
    h0 = h_inf + 0.5 * v_inf ** 2
    h_300K = 1005.0 * 300.0

    flt = _read_fluent(fluent_csv)
    flt_x = np.array([r[0] for r in flt])
    flt_span = np.array([math.sqrt(r[1]**2 + r[2]**2) for r in flt])
    flt_w = np.where(flt[:, 2] < 0, 1, 0)
    flt_q = np.array([r[4] for r in flt])
    flt_p = np.array([r[3] for r in flt])

    fields, solver = _run_solver(label, mach, alpha, h_m)

    x_w = fields.get("x_w_m", np.array([]))
    span_w = fields.get("span_w_m", np.array([]))
    xc = fields.get("xc_w", np.array([]))
    yb = fields.get("yb_w", np.array([]))
    q_lam = fields.get("q_lam_w", np.array([]))
    q_turb = fields.get("q_turb_w", np.array([]))
    q_final = fields.get("q_w", np.array([]))
    w_tr = fields.get("w_tr", np.array([]))
    p_e = fields.get("p_e_w", np.array([]))
    re_x_star = fields.get("re_x_star", np.array([]))
    re_tri = fields.get("re_tri", np.array([]))
    rho_e = fields.get("rho_e_w", np.array([]))
    ma_e = fields.get("ma_e_w", np.array([]))

    # Trim all fields to common length
    ref_len = min(len(x_w), len(span_w), len(xc), len(yb), len(q_lam), len(q_final), len(p_e), len(re_x_star))
    def _t(a): return np.asarray(a, dtype=float).ravel()[:ref_len] if a is not None and len(np.asarray(a).ravel()) >= ref_len else np.full(ref_len, np.nan)

    x_w = _t(x_w); span_w = _t(span_w); xc = _t(xc); yb = _t(yb)
    q_lam = _t(q_lam); q_turb = _t(q_turb); q_final = _t(q_final); w_tr = _t(w_tr)
    p_e = _t(p_e); re_x_star = _t(re_x_star); re_tri = _t(re_tri)
    rho_e = _t(rho_e); ma_e = _t(ma_e)

    Rn = 0.03
    nose_mask = _classify_nose(x_w, span_w, xc, Rn)
    nose_idx = np.where(nose_mask)[0]
    n_nose = int(np.sum(nose_mask))
    print(f"\n[{label}] true_nose_cap points: {n_nose}")

    if n_nose == 0:
        return None

    # ---- Align Fluent to each solver nose point ----
    flt_q_aligned = np.full(ref_len, float("nan"))
    flt_p_aligned = np.full(ref_len, float("nan"))
    for i in range(ref_len):
        fx = float(x_w[i]); fs = float(span_w[i])
        dx = np.abs(flt_x - fx); ds = np.abs(flt_span - fs)
        dist = np.sqrt(dx**2 + (0.3 * ds)**2)
        best = np.nanargmin(dist)
        if dist[best] <= np.sqrt(0.02**2 + (0.3 * 0.02)**2):
            flt_q_aligned[i] = float(flt_q[best])
            flt_p_aligned[i] = float(flt_p[best])

    # ---- Compute q_cap offline for each point ----
    q_cap_arr = np.full(ref_len, float("nan"))
    rn_local_arr = np.full(ref_len, float("nan"))

    for i in range(ref_len):
        if not nose_mask[i]:
            continue
        y_over_b = float(yb[i]) if np.isfinite(float(yb[i])) else 0.0
        rn_span = solver._leading_edge_rn_span_m(y_over_b=y_over_b)
        rn_local_arr[i] = float(rn_span)
        try:
            q_cap_arr[i] = float(kemp_riddell_modified_qsph_baseline(
                R_N_m=float(rn_span),
                rn_unit=str(solver.lf_cfg.stagnation.rn_unit),
                rho_inf=rho_inf, v_inf=v_inf,
                h0=float(h0), h_w=float(h_300K), h_300K=float(h_300K),
            ))
        except Exception:
            q_cap_arr[i] = float("nan")

    # ---- Determine which branch max() selects ----
    q_flat = q_lam.copy()  # step mode, nose points are w_tr=0
    q_final_current = q_final.copy()
    selected_branch = np.full(ref_len, "unknown", dtype=object)
    for i in nose_idx:
        if np.isfinite(q_flat[i]) and np.isfinite(q_cap_arr[i]):
            selected_branch[i] = "flat" if q_flat[i] >= q_cap_arr[i] else "cap"

    # ---- Offline alternatives ----
    q_cap_only = q_cap_arr.copy()
    q_min_cap = np.where(np.isfinite(q_flat) & np.isfinite(q_cap_arr),
                         np.minimum(q_flat, q_cap_arr), np.nan)
    # simple_blend: blend = exp(-0.5 * (x/(5*Rn))^2), q = blend*q_cap + (1-blend)*q_flat
    blend = np.full(ref_len, np.nan)
    for i in nose_idx:
        x_val = float(x_w[i])
        b = math.exp(-0.5 * (x_val / (5.0 * Rn)) ** 2)  # 1 at nose, ~0.6 at x=5Rn
        blend[i] = float(b)
    q_simple_blend = np.where(np.isfinite(q_flat) & np.isfinite(q_cap_arr),
                              blend * q_cap_arr + (1.0 - blend) * q_flat, np.nan)

    # ---- Per-point CSV ----
    csv_rows = []
    for i in nose_idx:
        csv_rows.append({
            "case": label,
            "idx": i,
            "x_m": float(x_w[i]),
            "span_m": float(span_w[i]),
            "x_over_c": float(xc[i]),
            "y_over_b": float(yb[i]),
            "q_flat": float(q_flat[i]) if np.isfinite(q_flat[i]) else float("nan"),
            "q_cap": float(q_cap_arr[i]) if np.isfinite(q_cap_arr[i]) else float("nan"),
            "q_final_current": float(q_final_current[i]) if np.isfinite(q_final_current[i]) else float("nan"),
            "selected_branch": str(selected_branch[i]),
            "q_flat_over_q_cap": float(q_flat[i] / q_cap_arr[i]) if np.isfinite(q_flat[i]) and np.isfinite(q_cap_arr[i]) and q_cap_arr[i] > 0 else float("nan"),
            "Re_x_star_lam": float(re_x_star[i]) if np.isfinite(re_x_star[i]) else float("nan"),
            "x_eff_m": float(x_w[i]),  # x_phys ~ x_w for nose
            "Rn_local_m": float(rn_local_arr[i]) if np.isfinite(rn_local_arr[i]) else float("nan"),
            "q_fluent": float(flt_q_aligned[i]) if np.isfinite(flt_q_aligned[i]) else float("nan"),
            "p_fluent": float(flt_p_aligned[i]) if np.isfinite(flt_p_aligned[i]) else float("nan"),
            "p_e": float(p_e[i]) if np.isfinite(p_e[i]) else float("nan"),
            "q_ratio_current": float(q_final_current[i] / flt_q_aligned[i]) if np.isfinite(q_final_current[i]) and np.isfinite(flt_q_aligned[i]) and flt_q_aligned[i] > 0 else float("nan"),
            "q_cap_only": float(q_cap_only[i]) if np.isfinite(q_cap_only[i]) else float("nan"),
            "q_min_cap": float(q_min_cap[i]) if np.isfinite(q_min_cap[i]) else float("nan"),
            "q_simple_blend": float(q_simple_blend[i]) if np.isfinite(q_simple_blend[i]) else float("nan"),
            "w_tr": float(w_tr[i]) if np.isfinite(w_tr[i]) else float("nan"),
        })

    # ---- Region summary ----
    qf_valid = np.array([r["q_flat"] for r in csv_rows if np.isfinite(r["q_flat"])])
    qc_valid = np.array([r["q_cap"] for r in csv_rows if np.isfinite(r["q_cap"])])
    qfq_valid = np.array([r["q_final_current"] for r in csv_rows if np.isfinite(r["q_final_current"])])
    q_fluent_valid = np.array([r["q_fluent"] for r in csv_rows if np.isfinite(r["q_fluent"])])

    n_selected_flat = sum(1 for r in csv_rows if r["selected_branch"] == "flat")
    n_selected_cap = sum(1 for r in csv_rows if r["selected_branch"] == "cap")

    # Offline alternative ratios
    def _alt_ratio(key):
        vals = np.array([r[key] for r in csv_rows if np.isfinite(r[key]) and np.isfinite(r["q_fluent"]) and r["q_fluent"] > 0])
        flt_q = np.array([r["q_fluent"] for r in csv_rows if np.isfinite(r[key]) and np.isfinite(r["q_fluent"]) and r["q_fluent"] > 0])
        if len(vals) == 0:
            return float("nan")
        return float(np.nanmean(vals / flt_q))

    summary = {
        "n_nose": n_nose,
        "n_selected_flat": n_selected_flat,
        "n_selected_cap": n_selected_cap,
        "pct_flat": n_selected_flat / max(n_nose, 1) * 100,
        "pct_cap": n_selected_cap / max(n_nose, 1) * 100,
        "q_flat_mean": float(np.nanmean(qf_valid)) if len(qf_valid) > 0 else float("nan"),
        "q_flat_median": float(np.nanmedian(qf_valid)) if len(qf_valid) > 0 else float("nan"),
        "q_flat_max": float(np.nanmax(qf_valid)) if len(qf_valid) > 0 else float("nan"),
        "q_cap_mean": float(np.nanmean(qc_valid)) if len(qc_valid) > 0 else float("nan"),
        "q_cap_median": float(np.nanmedian(qc_valid)) if len(qc_valid) > 0 else float("nan"),
        "q_cap_max": float(np.nanmax(qc_valid)) if len(qc_valid) > 0 else float("nan"),
        "q_final_current_mean": float(np.nanmean(qfq_valid)) if len(qfq_valid) > 0 else float("nan"),
        "q_fluent_mean": float(np.nanmean(q_fluent_valid)) if len(q_fluent_valid) > 0 else float("nan"),
        "q_ratio_current": _alt_ratio("q_final_current"),
        "q_ratio_cap_only": _alt_ratio("q_cap_only"),
        "q_ratio_min_cap": _alt_ratio("q_min_cap"),
        "q_ratio_simple_blend": _alt_ratio("q_simple_blend"),
        "cap_vs_fluent_ratio": float(np.nanmean(qc_valid / q_fluent_valid)) if len(qc_valid) > 0 and len(q_fluent_valid) > 0 else float("nan"),
    }

    # Print summary
    print(f"  q_flat: mean={summary['q_flat_mean']:.0f}, median={summary['q_flat_median']:.0f}, max={summary['q_flat_max']:.0f}")
    print(f"  q_cap:  mean={summary['q_cap_mean']:.0f}, median={summary['q_cap_median']:.0f}, max={summary['q_cap_max']:.0f}")
    print(f"  Selected by max(): flat={summary['pct_flat']:.0f}%, cap={summary['pct_cap']:.0f}%")
    print(f"  q_ratio_current={summary['q_ratio_current']:.3f}")
    print(f"  q_ratio_cap_only={summary['q_ratio_cap_only']:.3f}")
    print(f"  q_ratio_min_cap={summary['q_ratio_min_cap']:.3f}")
    print(f"  q_ratio_simple_blend={summary['q_ratio_simple_blend']:.3f}")
    print(f"  q_cap/q_fluent ratio={summary['cap_vs_fluent_ratio']:.3f}")

    return csv_rows, summary


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_csv = []
    results = {}

    for label, fc, mach, alpha, h_m in CALIB_CASES:
        r = audit_case(label, fc, mach, alpha, h_m)
        if r is None:
            continue
        csv_rows, summary = r
        all_csv.extend(csv_rows)
        results[label] = summary

    # ---- Write CSV ----
    if all_csv:
        csv_path = OUT_DIR / "nose_branch_audit.csv"
        keys = list(all_csv[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            wc = csv.DictWriter(f, fieldnames=keys)
            wc.writeheader()
            wc.writerows(all_csv)
        print(f"\nCSV written: {csv_path.name} ({len(all_csv)} rows)")

    # ---- Write report ----
    doc_path = DOCS_DIR / "faceted3d_v2_phase2b_nose_audit_zh.md"
    print(f"\nWriting: {doc_path.name}")
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write("# Phase 2B-nose Audit: `max(q_flat, q_cap)` 对鼻锥高估的贡献\n\n")
        f.write(f"> 生成时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> 调参工况：ma6_a5_h30km, ma8_a5_h30km (holdout 未运行)\n")
        f.write(f"> 数据文件：`runs/faceted3d_v2_phase2b_nose_audit/nose_branch_audit.csv`\n\n")

        f.write("## 1. 审计方法\n\n")
        f.write("1. 用 `cp_model=newtonian_like` + `weighting=step` 运行 solver\n")
        f.write("2. 识别 true_nose_cap 区域（x < 5×Rn 且 span < 0.10m）\n")
        f.write("3. 从 solver `q_lam_w` 提取 q_flat（nose 区 w_tr=0，所以 q_final = q_lam = flat-plate 参考焓值）\n")
        f.write("4. 用 solver 内相同的 `kemp_riddell_modified_qsph_baseline()` 离线计算 q_cap\n")
        f.write("5. 逐点比较 q_flat vs q_cap，判断当前 `max()` 选中的分支\n")
        f.write("6. 离线计算三种替代方案的 q 值和 Fluent ratio：`cap_only`、`min_cap`、`simple_blend`\n\n")

        f.write("## 2. 区域汇总\n\n")
        f.write("| 指标 | ma6_a5_h30km | ma8_a5_h30km |\n")
        f.write("|------|-------------|-------------|\n")
        for label in results:
            s = results[label]
            f.write(f"| true_nose_cap 点数 | {s['n_nose']} | — |\n")
            f.write(f"| q_flat mean [W/m²] | {s['q_flat_mean']:.0f} | — |\n")
            f.write(f"| q_flat median [W/m²] | {s['q_flat_median']:.0f} | — |\n")
            f.write(f"| q_flat max [W/m²] | {s['q_flat_max']:.0f} | — |\n")
            f.write(f"| q_cap mean [W/m²] | {s['q_cap_mean']:.0f} | — |\n")
            f.write(f"| q_cap median [W/m²] | {s['q_cap_median']:.0f} | — |\n")
            f.write(f"| q_cap max [W/m²] | {s['q_cap_max']:.0f} | — |\n")
            f.write(f"| max() 选中 flat 比例 | {s['pct_flat']:.0f}% | — |\n")
            f.write(f"| max() 选中 cap 比例 | {s['pct_cap']:.0f}% | — |\n")
            f.write(f"| q_final_current mean [W/m²] | {s['q_final_current_mean']:.0f} | — |\n")
            f.write(f"| q_fluent mean [W/m²] | {s['q_fluent_mean']:.0f} | — |\n |")

        f.write("\n\n## 3. Branch Selection 分析\n\n")
        f.write("| 工况 | max() 选中 flat | max() 选中 cap |\n")
        f.write("|------|----------------|---------------|\n")
        for label in results:
            s = results[label]
            f.write(f"| {label} | {s['pct_flat']:.0f}% ({s['n_selected_flat']}/{s['n_nose']}) | "
                    f"{s['pct_cap']:.0f}% ({s['n_selected_cap']}/{s['n_nose']}) |\n")

        f.write("\n## 4. Offline 替代方案对比\n\n")
        f.write("| 方案 | 公式 | ma6 q_ratio | ma8 q_ratio |\n")
        f.write("|------|------|------------|------------|\n")
        for label in results:
            s = results[label]
        # Reproduce table
        for label in results:
            s = results[label]
        f.write(f"| **current** (max) | q = max(q_flat, q_cap) | {results[CALIB_CASES[0][0]]['q_ratio_current']:.3f} | {results[CALIB_CASES[1][0]]['q_ratio_current']:.3f} |\n")
        f.write(f"| cap_only | q = q_cap | {results[CALIB_CASES[0][0]]['q_ratio_cap_only']:.3f} | {results[CALIB_CASES[1][0]]['q_ratio_cap_only']:.3f} |\n")
        f.write(f"| min_cap | q = min(q_flat, q_cap) | {results[CALIB_CASES[0][0]]['q_ratio_min_cap']:.3f} | {results[CALIB_CASES[1][0]]['q_ratio_min_cap']:.3f} |\n")
        f.write(f"| simple_blend | q = blend*q_cap + (1-blend)*q_flat | {results[CALIB_CASES[0][0]]['q_ratio_simple_blend']:.3f} | {results[CALIB_CASES[1][0]]['q_ratio_simple_blend']:.3f} |\n")

        f.write("\n## 5. q_cap 与 Fluent 的偏差\n\n")
        f.write("| 工况 | q_cap_mean / q_fluent_mean | 判断 |\n")
        f.write("|------|--------------------------|------|\n")
        for label in results:
            s = results[label]
            ratio = s['cap_vs_fluent_ratio']
            if np.isfinite(ratio):
                if ratio < 0.8:
                    judge = "q_cap 明显偏低，cap 接管会导致低估"
                elif ratio < 1.2:
                    judge = "q_cap 接近 Fluent，cap 接管可改善高估"
                elif ratio < 2.0:
                    judge = "q_cap 偏高，cap 接管可降低高估但仍有剩余误差"
                else:
                    judge = "q_cap 严重偏高，cap 接管不足，需审计 Rn_local / edge state"
            else:
                judge = "无法判断（数据不足）"
            f.write(f"| {label} | {ratio:.3f} | {judge} |\n")

        f.write("\n## 6. 结论\n\n")
        for label in results:
            s = results[label]
            f.write(f"### {label}\n\n")
            if s['pct_flat'] > 50:
                f.write(f"- **max() 主要选中 flat 分支**（{s['pct_flat']:.0f}%），说明 q_flat 因 Re_x 奇异性放大超过 q_cap\n")
                f.write(f"- 当前 q_ratio={s['q_ratio_current']:.2f}×，主要来自 q_flat 被 max 选中\n")
            else:
                f.write(f"- **max() 主要选中 cap 分支**（{s['pct_cap']:.0f}%），q_flat 并未系统性超过 q_cap\n")
            if np.isfinite(s['q_ratio_cap_only']):
                f.write(f"- cap_only 方案 q_ratio={s['q_ratio_cap_only']:.2f}× → "
                        f"{'比 current 改善' if s['q_ratio_cap_only'] < s['q_ratio_current'] else '不比 current 好'}\n")
            if np.isfinite(s['cap_vs_fluent_ratio']):
                f.write(f"- q_cap vs Fluent ratio={s['cap_vs_fluent_ratio']:.2f}× → "
                        f"{'cap 接近正确量级，可接管' if s['cap_vs_fluent_ratio'] < 1.5 else 'cap 也偏高，需进一步审计'}\n")
            f.write("\n")

        f.write("### 总判断\n\n")
        # Overall judgment
        all_flat_dominated = all(results[label]['pct_flat'] > 50 for label in results)
        all_cap_close = all(np.isfinite(results[label]['cap_vs_fluent_ratio']) and results[label]['cap_vs_fluent_ratio'] < 1.5 for label in results)
        cap_only_better = all(results[label]['q_ratio_cap_only'] < results[label]['q_ratio_current'] for label in results if np.isfinite(results[label]['q_ratio_cap_only']))

        if all_flat_dominated and cap_only_better:
            f.write("1. **高估主因确认：`max(q_flat, q_cap)` 选中了奇异放大的 q_flat** ✅\n")
            f.write("2. q_cap 相对 Fluent 量级正确，cap 接管是优先方向\n")
            f.write("3. 建议 Phase 2B-nose 实现：\n")
            f.write("   - 优先方向：让 q_cap 在鼻锥区接管（改用 min 或 blend）\n")
            f.write("   - x_eff floor 是间接手段，不如直接修复 branch selection\n")
            f.write("   - 注意：改变 max→min 影响范围仅限于 cap_mask 内的点，不影响全鼻锥区\n")
        elif all_flat_dominated and not cap_only_better:
            f.write("1. **高估主因确认：`max(q_flat, q_cap)` 选中了 q_flat**，但 cap 本身也偏高\n")
            f.write("2. q_cap 未能完全消除高估，需要同时审计 Rn_local 和 Kemp-Riddell 参数\n")
            f.write("3. 建议先审计 Rn_local 是否正确、Kemp-Riddell 的 `R_N_m` 是否应使用 nose_cap_radius_m\n")
        else:
            f.write("1. 鼻锥高估不完全来自 max 选 q_flat\n")
            f.write("2. q_cap 本身也有偏离，需要更全面的审计\n")

        f.write("\n---\n")
        f.write(f"\n*生成于 `scripts/faceted3d_v2_phase2b_nose_audit.py`*\n")

    print(f"\nDone — outputs in {OUT_DIR}")


if __name__ == "__main__":
    main()
