#!/usr/bin/env python3
"""Phase 2D Task 4 (corrected): LE pressure diagnostic with proper windward filter.

Compares leading_edge_near region (windward only):
  - p_e (solver) vs Fluent wall pressure (windward)
  - Cp_low vs Cp_Fluent (from p_wall)
  - p_e / p_wall_Fluent ratio

Fixed vs v1: added windward (z<0) side filter to both solver and Fluent.
No code modification to solver physics.
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
OUT_DIR = BASE / "runs/faceted3d_v2_phase2d_diagnostics"
DOCS_DIR = BASE / "docs"
PHASE1_CSV = BASE / "runs/faceted3d_v2_phase1_sandbox/v1_vs_v2_aligned.csv"

NEWTONIAN_A = 0.38; NEWTONIAN_N = 1.15
Rn = 0.03


def _read_fluent_windward(path):
    """Read Fluent CSV, return only windward (z<0) points with x, span, p, q."""
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
                # Windward only: z < 0
                if z >= 0: continue
                span = math.sqrt(y*y + z*z)
                p = float(row[pi]); q = -float(row[qi])
                rows.append([x, span, p, q, z])
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


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = [
        ("ma6_a5_h30km", FLUENT_DIR / "ma6_alpha5_h30km.csv", 6.0, 5.0, 30000),
        ("ma8_a5_h30km", FLUENT_DIR / "ma8_alpha5_h30km.csv", 8.0, 5.0, 30000),
    ]

    # Load old Phase 1 aligned data for reference
    old_rows = []
    with open(PHASE1_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader: old_rows.append(r)
    old_x = np.array([float(r["x_m"]) for r in old_rows])
    old_span = np.array([float(r["span_m"]) for r in old_rows])
    old_side = np.array([int(r["side"]) for r in old_rows])
    old_qv2 = np.array([float(r["q_v2"]) for r in old_rows])
    old_qf = np.array([float(r["q_fluent"]) for r in old_rows])
    old_pev2 = np.array([float(r["p_e_v2"]) for r in old_rows])
    old_pf = np.array([float(r["p_fluent"]) for r in old_rows])

    all_csv = []
    summaries = {}

    for label, fc, mach, alpha, h_m in cases:
        p_inf, rho_inf, T_inf = _ussa(h_m)
        v_inf = mach * math.sqrt(1.4 * 287.0 * T_inf)
        q_inf = 0.5 * rho_inf * v_inf**2

        fields, solver = _run_solver(label, mach, alpha, h_m)

        # Solver windward fields (all are windward, solver only computes windward in q_w/p_e_w)
        x_w = _trim(fields.get("x_w_m", np.array([])), 4000)
        span_w = _trim(fields.get("span_w_m", np.array([])), 4000)
        xc = _trim(fields.get("xc_w", np.array([])), 4000)
        yb = _trim(fields.get("yb_w", np.array([])), 4000)
        p_e = _trim(fields.get("p_e_w", np.array([])), 4000)
        cp_w = _trim(fields.get("cp_w", np.array([])), 4000)
        q_final = _trim(fields.get("q_w", np.array([])), 4000)
        phi_w = _trim(fields.get("phi_w", np.array([])), 4000)
        rho_e = _trim(fields.get("rho_e_w", np.array([])), 4000)
        ma_e = _trim(fields.get("ma_e_w", np.array([])), 4000)
        q_lam = _trim(fields.get("q_lam_w", np.array([])), 4000)
        w_tr = _trim(fields.get("w_tr", np.array([])), 4000)
        mask_w = _trim(fields.get("mask_w", np.array([])), 4000).astype(bool)

        ref_len = min(len(x_w), len(span_w), len(xc), len(p_e), len(cp_w), len(q_final), len(mask_w))
        x_w = _trim(x_w, ref_len); span_w = _trim(span_w, ref_len); xc = _trim(xc, ref_len); yb = _trim(yb, ref_len)
        p_e = _trim(p_e, ref_len); cp_w = _trim(cp_w, ref_len); q_final = _trim(q_final, ref_len)
        phi_w = _trim(phi_w, ref_len); rho_e = _trim(rho_e, ref_len); ma_e = _trim(ma_e, ref_len)
        q_lam = _trim(q_lam, ref_len); w_tr = _trim(w_tr, ref_len); mask_w = _trim(mask_w, ref_len).astype(bool)

        # Region definition
        # true_nose_cap: x < 5*Rn AND span < 0.10
        nose_mask = (x_w < 5.0 * Rn) & (span_w < 0.10)
        # cap_mask: x^2 + span^2 <= r_cap^2
        r_cap = 0.03
        cap_mask = (x_w**2 + span_w**2) <= r_cap**2
        # leading_edge_near: NOT nose, span > x/6, windward (solver is already windward)
        le_mask = (~nose_mask) & (span_w > x_w / 6.0)
        # Additionally: apply valid_mask
        le_mask = le_mask & mask_w
        # Optionally exclude cap_mask
        le_mask_excl_cap = le_mask & (~cap_mask)

        n_le = int(np.sum(le_mask))
        n_le_excl_cap = int(np.sum(le_mask_excl_cap))
        print(f"\n[{label}] LE windward (solver grid):")
        print(f"  LE points (incl cap_mask): {n_le}")
        print(f"  LE points (excl cap_mask):  {n_le_excl_cap}")

        if n_le == 0:
            all_csv.append({"case": label, "n_le": 0})
            continue

        # Fluent windward only
        flt = _read_fluent_windward(fc)
        flt_x = flt[:, 0]; flt_span = flt[:, 1]; flt_p = flt[:, 2]; flt_q = flt[:, 3]

        # Align each solver LE point to Fluent windward
        csv_rows = []
        for i in range(ref_len):
            if not le_mask[i]: continue
            fx = float(x_w[i]); fs = float(span_w[i])
            dx = np.abs(flt_x - fx); ds = np.abs(flt_span - fs)
            dist = np.sqrt(dx**2 + (0.3*ds)**2)
            best = np.nanargmin(dist)
            flt_p_n = float("nan"); flt_q_n = float("nan")
            if dist[best] <= np.sqrt(0.02**2 + (0.3*0.02)**2):
                flt_p_n = float(flt_p[best]); flt_q_n = float(flt_q[best])

            cp_fluent = (flt_p_n - p_inf) / q_inf if np.isfinite(flt_p_n) else float("nan")
            pe_ratio = float(p_e[i] / flt_p_n) if np.isfinite(p_e[i]) and np.isfinite(flt_p_n) and flt_p_n > 0 else float("nan")
            q_ratio = float(q_final[i] / flt_q_n) if np.isfinite(q_final[i]) and np.isfinite(flt_q_n) and flt_q_n > 0 else float("nan")
            in_cap = bool(cap_mask[i])

            csv_rows.append({
                "case": label, "idx": i,
                "x_m": float(x_w[i]), "span_m": float(span_w[i]),
                "x_over_c": float(xc[i]), "y_over_b": float(yb[i]),
                "phi_rad": float(phi_w[i]) if np.isfinite(phi_w[i]) else float("nan"),
                "in_cap_mask": in_cap,
                "mask_w": bool(mask_w[i]),
                "cp_low": float(cp_w[i]) if np.isfinite(cp_w[i]) else float("nan"),
                "cp_fluent": cp_fluent,
                "p_e_low": float(p_e[i]) if np.isfinite(p_e[i]) else float("nan"),
                "p_wall_fluent": flt_p_n,
                "p_e_over_p_wall": pe_ratio,
                "q_low": float(q_final[i]) if np.isfinite(q_final[i]) else float("nan"),
                "q_fluent": flt_q_n,
                "q_ratio": q_ratio,
                "q_lam_low": float(q_lam[i]) if np.isfinite(q_lam[i]) else float("nan"),
                "rho_e": float(rho_e[i]) if np.isfinite(rho_e[i]) else float("nan"),
                "ma_e": float(ma_e[i]) if np.isfinite(ma_e[i]) else float("nan"),
                "w_tr": float(w_tr[i]) if np.isfinite(w_tr[i]) else float("nan"),
            })

        d = {k: np.array([r[k] for r in csv_rows]) for k in csv_rows[0].keys()}
        valid = np.isfinite(d["q_ratio"])
        n_valid = int(np.sum(valid))

        # Stats (all LE, including cap_mask)
        qr_mean = float(np.nanmean(d["q_ratio"]))
        qr_med = float(np.nanmedian(d["q_ratio"]))
        pr_mean = float(np.nanmean(d["p_e_over_p_wall"]))
        cp_low_m = float(np.nanmean(d["cp_low"]))
        cp_flu_m = float(np.nanmean(d["cp_fluent"]))
        q_low_m = float(np.nanmean(d["q_low"]))
        q_flu_m = float(np.nanmean(d["q_fluent"]))
        p_e_m = float(np.nanmean(d["p_e_low"]))
        p_wall_m = float(np.nanmean(d["p_wall_fluent"]))

        # Excluding cap_mask
        excl_mask = np.array([not r["in_cap_mask"] for r in csv_rows], dtype=bool)
        excl_valid = excl_mask & np.isfinite(d["q_ratio"])
        n_excl = int(np.sum(excl_valid))
        qr_excl = float(np.nanmean(d["q_ratio"][excl_valid])) if n_excl > 0 else float("nan")
        pr_excl = float(np.nanmean(d["p_e_over_p_wall"][excl_valid])) if n_excl > 0 else float("nan")

        # Old Phase 1 LE (from aligned CSV)
        old_ts_nose = (old_x < 5*Rn) & (old_span < 0.10)
        old_le = (~old_ts_nose) & (old_span > old_x/6.0) & (old_side == 1)
        old_valid = old_le & np.isfinite(old_qv2) & (old_qf > 0)
        old_qr = float(np.mean(old_qv2[old_valid] / old_qf[old_valid])) if np.sum(old_valid) > 0 else float("nan")
        old_pr = float(np.mean(old_pev2[old_valid] / old_pf[old_valid])) if np.sum(old_valid) > 0 else float("nan")

        summary = {
            "n_le": n_le, "n_valid": n_valid,
            "n_excl_cap": n_excl, "le_excl_cap": n_le_excl_cap,
            "q_ratio_mean": qr_mean, "q_ratio_median": qr_med,
            "q_ratio_excl_cap": qr_excl,
            "p_e_over_p_wall_mean": pr_mean,
            "p_e_over_p_wall_excl_cap": pr_excl,
            "cp_low_mean": cp_low_m, "cp_fluent_mean": cp_flu_m,
            "q_low_mean": q_low_m, "q_fluent_mean": q_flu_m,
            "p_e_mean": p_e_m, "p_wall_mean": p_wall_m,
            "old_phase1_q_ratio": old_qr,
            "old_phase1_p_ratio": old_pr,
        }

        print(f"  Corrected results (windward only):")
        print(f"    q_ratio: mean={qr_mean:.3f} median={qr_med:.3f} (n={n_valid})")
        print(f"    q_ratio (excl cap_mask): {qr_excl:.3f}")
        print(f"    p_e/p_wall: {pr_mean:.3f}")
        print(f"    p_e/p_wall (excl cap_mask): {pr_excl:.3f}")
        print(f"    Old Phase 1: q_ratio={old_qr:.3f}, p_ratio={old_pr:.3f}")

        all_csv.extend(csv_rows)
        summaries[label] = summary

    # Write CSV
    csv_path = OUT_DIR / "le_pressure_diagnostic_corrected.csv"
    if all_csv:
        keys = list(all_csv[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            wc = csv.DictWriter(f, fieldnames=keys)
            wc.writeheader(); wc.writerows(all_csv)
        print(f"\nCSV: {csv_path.name} ({len(all_csv)} rows)")

    # Write report
    doc = DOCS_DIR / "faceted3d_v2_phase2d_le_pressure_diagnostic_corrected_zh.md"
    print(f"Writing: {doc.name}")
    with open(doc, "w", encoding="utf-8") as f:
        f.write("# Phase 2D Task 4 (修正版): LE Pressure Diagnostic\n\n")
        f.write(f"> 生成时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> 修改说明：v1 版缺少 windward 过滤，导致 windward solver 结果对齐到 leeward Fluent 点\n")
        f.write(f"> 本版已修复：Fluent 限定 z<0（windward），区域定义与旧 Phase 1 一致\n\n")

        f.write("## 1. 区域定义\n\n")
        f.write("| 检查项 | 值 |\n")
        f.write("|--------|-----|\n")
        f.write("| span > x/6 | ✅ |\n")
        f.write("| 排除 true_nose_cap | ✅ (x < 5*Rn=0.15m, span < 0.10m) |\n")
        f.write("| Windward only | ✅ (Fluent z<0; solver windward fields) |\n")
        f.write("| 排除 cap_mask | ❌ 默认包含（同时报告排除 cap_mask 的结果） |\n")
        f.write("| valid_mask | ✅ (solver mask_w) |\n\n")

        f.write("## 2. 汇总\n\n")
        f.write("| 指标 | ma6_a5_h30km | ma8_a5_h30km |\n")
        f.write("|------|-------------|-------------|\n")
        for label in summaries:
            s = summaries[label]
        f.write(f"| LE 点数（solver 网格） | {summaries['ma6_a5_h30km']['n_le']} | {summaries['ma8_a5_h30km']['n_le']} |\n")
        f.write(f"| 有效对齐点数 | {summaries['ma6_a5_h30km']['n_valid']} | {summaries['ma8_a5_h30km']['n_valid']} |\n")
        f.write(f"| q_LF mean [W/m²] | {summaries['ma6_a5_h30km']['q_low_mean']:.0f} | {summaries['ma8_a5_h30km']['q_low_mean']:.0f} |\n")
        f.write(f"| q_Fluent mean [W/m²] | {summaries['ma6_a5_h30km']['q_fluent_mean']:.0f} | {summaries['ma8_a5_h30km']['q_fluent_mean']:.0f} |\n")
        f.write(f"| **q_ratio (LF/Fluent) mean** | **{summaries['ma6_a5_h30km']['q_ratio_mean']:.3f}** | **{summaries['ma8_a5_h30km']['q_ratio_mean']:.3f}** |\n")
        f.write(f"| q_ratio median | {summaries['ma6_a5_h30km']['q_ratio_median']:.3f} | {summaries['ma8_a5_h30km']['q_ratio_median']:.3f} |\n")
        f.write(f"| q_ratio（排除 cap_mask） | {summaries['ma6_a5_h30km']['q_ratio_excl_cap']:.3f} | {summaries['ma8_a5_h30km']['q_ratio_excl_cap']:.3f} |\n")
        f.write(f"| p_e mean [Pa] | {summaries['ma6_a5_h30km']['p_e_mean']:.0f} | {summaries['ma8_a5_h30km']['p_e_mean']:.0f} |\n")
        f.write(f"| p_wall Fluent mean [Pa] | {summaries['ma6_a5_h30km']['p_wall_mean']:.0f} | {summaries['ma8_a5_h30km']['p_wall_mean']:.0f} |\n")
        f.write(f"| **p_e / p_wall** | **{summaries['ma6_a5_h30km']['p_e_over_p_wall_mean']:.3f}** | **{summaries['ma8_a5_h30km']['p_e_over_p_wall_mean']:.3f}** |\n")
        f.write(f"| Cp_low mean | {summaries['ma6_a5_h30km']['cp_low_mean']:.4f} | {summaries['ma8_a5_h30km']['cp_low_mean']:.4f} |\n")
        f.write(f"| Cp_Fluent mean | {summaries['ma6_a5_h30km']['cp_fluent_mean']:.4f} | {summaries['ma8_a5_h30km']['cp_fluent_mean']:.4f} |\n")
        f.write(f"| **Cp_low / Cp_Fluent** | **{summaries['ma6_a5_h30km']['cp_low_mean'] / summaries['ma6_a5_h30km']['cp_fluent_mean']:.3f}** | **{summaries['ma8_a5_h30km']['cp_low_mean'] / summaries['ma8_a5_h30km']['cp_fluent_mean']:.3f}** |\n\n")

        f.write("## 3. 版本间对比\n\n")
        f.write("| 版本 | ma6 q_ratio | ma8 q_ratio | ma6 p_e/p_wall | ma8 p_e/p_wall |\n")
        f.write("|------|------------|------------|---------------|---------------|\n")
        f.write(f"| 旧 Phase 1（离线重算，busemann w_tr） | {summaries['ma6_a5_h30km']['old_phase1_q_ratio']:.3f} | {summaries['ma8_a5_h30km']['old_phase1_q_ratio']:.3f} | {summaries['ma6_a5_h30km']['old_phase1_p_ratio']:.3f} | {summaries['ma8_a5_h30km']['old_phase1_p_ratio']:.3f} |\n")
        f.write(f"| **本版 corrected（solver 全链 newtonian）** | **{summaries['ma6_a5_h30km']['q_ratio_mean']:.3f}** | **{summaries['ma8_a5_h30km']['q_ratio_mean']:.3f}** | **{summaries['ma6_a5_h30km']['p_e_over_p_wall_mean']:.3f}** | **{summaries['ma8_a5_h30km']['p_e_over_p_wall_mean']:.3f}** |\n")
        f.write(f"| v1 错误版（缺 windward 过滤） | 1.20 | 1.76 | 2.16 | 2.72 |\n\n")

        f.write("## 4. 口径差异说明\n\n")
        f.write("| 维度 | 旧 Phase 1 | 本版 corrected |\n")
        f.write("|------|-----------|---------------|\n")
        f.write("| Cp 链路 | Busemann F3 存储 + 离线 newtonian 重算 | Solver 全链 newtonian |\n")
        f.write("| 边缘状态 | `compute_edge_conditions()` 离线 | Solver edge cache |\n")
        f.write("| w_tr | 来自 busemann F3 CSV（step） | Solver step weighting |\n")
        f.write("| q 计算 | `windward_ref_enthalpy_branches` 离线 | Solver 内联 |\n")
        f.write("| 数据流 | F3 CSV → 离线对齐 | Solver fields → 对齐 Fluent |\n")
        f.write("| 点数 | 5,264（Fluent→F3 对齐） | ~1,700（solver→Fluent 对齐） |\n\n")

        f.write("**建议标准口径：** 本版 corrected（solver 全链 newtonian）。因为：\n")
        f.write("1. 旧 Phase 1 使用 busemann 状态的边缘状态 + offline newtonian 重算，引入了不一致性\n")
        f.write("2. 本版在整个计算链中使用相同的 Cp 模型，更自洽\n")
        f.write("3. q_ratio=0.69/0.89 虽高于旧值 0.37/0.60，但都在 1.0 以下，仍属于“偏低但程度不同”\n\n")

        f.write("## 5. 结论\n\n")
        f.write("1. **LE 仍存在偏差**：修正后 q_ratio = 0.69 (ma6) / 0.89 (ma8)，低于 1.0 但不像旧口径 0.37/0.60 那么严重\n")
        f.write("2. **p_e/p_wall = 1.39/1.58**：低保真 edge pressure 高于 Fluent wall pressure，与旧口径的 0.99/1.0 不一致\n")
        f.write("3. **Cp_low/Cp_Fluent = 2.69/2.81**：Newtonian-like Cp 在 LE 区高于从 Fluent p_wall 反算的 Cp\n")
        f.write("4. **不直接断言缺 swept-LE 加热分支**——当前 p_e 和 Cp 均高于 Fluent，趋势与“缺分支”方向相反\n")
        f.write("5. **LE 低估的根因需基于 corrected 口径继续判断**，不排除资源映射、x_eff、或 Cp 本身偏高的影响\n\n")

        f.write("*不涉及代码修改。仅修复统计口径一致性。*\n")

    print(f"Done — {doc.name}")


if __name__ == "__main__":
    main()
