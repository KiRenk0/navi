#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迎风面壁温误差半模投影图（算法 Taw vs Fluent 绝热壁温）—— 双色标版。

只读脚本：不修改 src / specs / YAML / docs / Fluent CSV / 模型 / 公式。
沿用项目既有口径：
  - Taw 取 fields.npz 的 Taw_tpg_w（Route A-TPG 默认；缺失或全 NaN 直接报错）。
  - 迎风面映射: LF (x_w_m, span_w_m) -> Fluent (x-coordinate, y-coordinate)，KD-tree 最近邻。
  - Fluent CSV 含整个 3D 壁面，z-coordinate 为厚度/垂向；迎风面(压缩侧)为低 z (高压)侧，
    默认用 z<0 过滤出迎风面。可用 --windward_z_sign 覆盖。

上色量：相对误差 (%) = (Taw_LF - Tw_fluent) / Tw_fluent * 100
发散色标 (RdBu_r)：红=算法偏高，蓝=算法偏低。

每次运行同时输出两张图：
  1. 固定 ±10% 色标图（跨工况横向比较）
  2. 工况自适应色标图（按该工况实际误差 min/max 缩放）

投影方式与 scripts/viz/plot_wing_surface_temperature_from_run_rem.py 完全一致
(半模，x 弦向 / y 展向，真实坐标)。

口径声明（Scope / Caveats）:
  - diagnostic visualization only —— 仅诊断可视化，不产生任何 baseline / 模型。
  - does NOT replace P2R2 corrected comparison canon —— 用 P4 式 KD-tree 最近邻映射，
    Fluent mapped Tw 未复现 P2R2 canon 映射方法（无 0.3m 阈值剔除），正式 corrected
    comparison canon 仍以 P2R2 表为准，本图不得当作 canon replacement。
  - NOT validation complete —— 不代表 validation 完成。
  - windward-only —— 仅迎风面；不涉及 leeward temperature error。

用法:
  python scripts/viz/plot_windward_error_vs_fluent.py \
    --lf_npz runs/ma6.5_a3_h30km_tpg/fields.npz \
    --fluent_csv fluent_export/adiabatic_wall_csv/30km_3alpha_6.5ma.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# 固定色标上下限（百分比）
# ---------------------------------------------------------------------------
FIXED_CLIM = 10.0  # ±10%

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT = _THIS_DIR.parents[1]


def _ensure_import_path() -> None:
    repo_root = _PROJECT
    src_root = repo_root / "src"
    for p in (str(repo_root), str(src_root)):
        if p not in sys.path:
            sys.path.insert(0, p)


def _load_json(p: Path) -> dict:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_yaml(p: Path) -> dict:
    _ensure_import_path()
    from ref_enthalpy_method.specs.loader import load_yaml  # noqa: WPS433

    return load_yaml(p)


def _parse_fluent_csv(csv_path: Path) -> dict:
    """读取 Fluent 壁面 CSV，识别坐标/温度列。"""
    with open(csv_path, "r", newline="") as fh:
        reader = csv.reader(fh)
        header = [h.strip() for h in next(reader)]
        rows = list(reader)

    col_map = {h: i for i, h in enumerate(header)}
    x_col = y_col = z_col = tw_col = None
    for h in header:
        hl = h.lower().replace(" ", "").replace("_", "-")
        if "x-coordinate" in hl:
            x_col = h
        elif "y-coordinate" in hl:
            y_col = h
        elif "z-coordinate" in hl:
            z_col = h
        elif "wall-temperature" in hl:
            tw_col = h
        elif "temperature" in hl and tw_col is None:
            tw_col = h

    if None in (x_col, y_col, z_col, tw_col):
        raise RuntimeError(f"无法识别 Fluent CSV 列。header={header}")

    data = np.array([[float(v) for v in row] for row in rows], dtype=np.float64)
    return {
        "x": data[:, col_map[x_col]],
        "y": data[:, col_map[y_col]],
        "z": data[:, col_map[z_col]],
        "Tw": data[:, col_map[tw_col]],
        "header": header,
        "n_points": data.shape[0],
        "fluent_path": str(csv_path),
        "x_col": x_col, "y_col": y_col, "z_col": z_col, "tw_col": tw_col,
    }


def _triangulate_structured(ny: int, nx: int) -> np.ndarray:
    triangles = np.empty((2 * (ny - 1) * (nx - 1), 3), dtype=np.int32)
    k = 0
    for j in range(ny - 1):
        row = j * nx
        row2 = (j + 1) * nx
        for i in range(nx - 1):
            p00 = row + i
            p01 = row + i + 1
            p10 = row2 + i
            p11 = row2 + i + 1
            triangles[k] = (p00, p01, p11)
            triangles[k + 1] = (p00, p11, p10)
            k += 2
    return triangles


# ========================= 自适应色标构建 =========================

def _build_adaptive_scale(err_v: np.ndarray):
    """
    根据工况实际有限误差构建自适应色标。

    Parameters
    ----------
    err_v : 1D ndarray
        所有有效点的 signed relative error (%)。

    Returns
    -------
    case_min : float       实际 finite min（JSON 记录用）
    case_max : float       实际 finite max（JSON 记录用）
    adaptive_class : str   "cross_zero" | "positive_only" | "negative_only" | "all_zero"
    norm : Normalize subclass
    cmap : Colormap
    levels : ndarray       41 levels for tricontourf
    extend : str           "neither" | "both"
    """
    from matplotlib.colors import TwoSlopeNorm, Normalize, LinearSegmentedColormap
    from matplotlib import cm

    finite = err_v[np.isfinite(err_v)]
    if len(finite) == 0:
        raise RuntimeError("adaptive scale: 无有限误差点，无法构建色标。")

    case_min = float(np.min(finite))
    case_max = float(np.max(finite))

    # ---- 分类 ----
    if case_min == 0.0 and case_max == 0.0:
        adaptive_class = "all_zero"
    elif case_min < 0 and case_max > 0:
        adaptive_class = "cross_zero"
    elif case_min >= 0:
        adaptive_class = "positive_only"
    else:
        adaptive_class = "negative_only"

    # ---- 处理零宽色标 ----
    base_cmap = cm.RdBu_r
    N_LEVELS = 41

    if case_min == case_max:
        # 所有有效误差相同 → 加极小 padding 避免零宽
        val = case_min
        eps = max(abs(val) * 1e-3, 1e-6)
        if val == 0.0:
            plot_min, plot_max = -eps, eps
        else:
            plot_min, plot_max = val - eps, val + eps
    else:
        plot_min, plot_max = case_min, case_max

    # ---- 按分类构建 norm / cmap / levels ----
    if adaptive_class in ("cross_zero", "all_zero"):
        norm = TwoSlopeNorm(vmin=plot_min, vcenter=0.0, vmax=plot_max)
        cmap = base_cmap
        levels = np.linspace(plot_min, plot_max, N_LEVELS)
        extend = "neither"

    elif adaptive_class == "positive_only":
        norm = Normalize(vmin=plot_min, vmax=plot_max)
        # 截取 RdBu_r 红色半区 [0.5, 1.0]：白/浅红 → 深红
        n_colors = 256
        red_half = base_cmap(np.linspace(0.5, 1.0, n_colors))
        cmap = LinearSegmentedColormap.from_list("RdBu_r_red_half", red_half)
        levels = np.linspace(plot_min, plot_max, N_LEVELS)
        extend = "neither"

    else:  # negative_only
        norm = Normalize(vmin=plot_min, vmax=plot_max)
        # 截取 RdBu_r 蓝色半区 [0.0, 0.5]：深蓝 → 白/浅蓝
        n_colors = 256
        blue_half = base_cmap(np.linspace(0.0, 0.5, n_colors))
        cmap = LinearSegmentedColormap.from_list("RdBu_r_blue_half", blue_half)
        levels = np.linspace(plot_min, plot_max, N_LEVELS)
        extend = "neither"

    return case_min, case_max, adaptive_class, norm, cmap, levels, extend


# ========================= 单图出图函数 =========================

def _plot_one(X, Y, Z, tri, lf_valid, nx, ny, Xg, Yg, Vg,
              norm, cmap, levels, extend,
              title_line2, stats, h_km, mach, alpha, out_path):
    """绘制单张迎风面误差半模投影图。"""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.8, 4.6), dpi=170)
    Zc = np.where(np.isfinite(Z), Z, 0.0)
    im = ax.tricontourf(tri, Zc, levels=levels, cmap=cmap, norm=norm, extend=extend)
    cbar = fig.colorbar(im, ax=ax, pad=0.02)
    cbar.set_label("relative error (%)  =  (Taw_LF - Tw_Fluent)/Tw_Fluent x 100")

    # ---- 外形轮廓 ----
    def _edge(xs, ys, vs):
        m = np.isfinite(xs) & np.isfinite(ys) & vs
        return xs[m], ys[m]

    ex, ey = [], []
    for xs, ys, vs in [
        (Xg[0, :], Yg[0, :], Vg[0, :]),               # root
        (Xg[:, -1], Yg[:, -1], Vg[:, -1]),            # tip 侧后缘方向
        (Xg[-1, ::-1], Yg[-1, ::-1], Vg[-1, ::-1]),   # tip
        (Xg[::-1, 0], Yg[::-1, 0], Vg[::-1, 0]),      # 前缘
    ]:
        px, py = _edge(xs, ys, vs)
        ex.append(px)
        ey.append(py)
    ex = np.concatenate(ex)
    ey = np.concatenate(ey)
    if ex.size > 2:
        ax.plot(np.append(ex, ex[0]), np.append(ey, ey[0]),
                color="k", linewidth=1.0, alpha=0.85)

    h_text = "h=?" if h_km is None else f"h={h_km:.1f} km"
    ax.set_title(f"Windward Taw error vs Fluent | {h_text}, M={mach}, alpha={alpha} deg\n"
                 f"{title_line2}\n"
                 f"mean|err|={stats['mean_abs_rel_err_pct']:.2f}%  "
                 f"p95={stats['p95_abs_rel_err_pct']:.2f}%  "
                 f"over={stats['over_fraction']*100:.0f}%", fontsize=10)
    ax.set_xlabel("x / m")
    ax.set_ylabel("y / m (half-span)")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.35)
    fig.tight_layout()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


# ========================= 主流程 =========================

def main() -> int:
    ap = argparse.ArgumentParser(description="迎风面壁温误差半模投影图 (算法 Taw vs Fluent) —— 双色标版")
    ap.add_argument("--lf_npz", default="runs/htv2_p5_corrected_tpg/fields.npz",
                    help="LF fields.npz（含 Taw_tpg_w / x_w_m / span_w_m / mask_w）")
    ap.add_argument("--summary", default=None,
                    help="summary.json 路径（默认取 lf_npz 同目录）")
    ap.add_argument("--fluent_csv",
                    default="fluent_export/adiabatic_wall_csv/30km_5alpha_6ma.csv",
                    help="Fluent 绝热壁面 CSV")
    ap.add_argument("--windward_z_sign", choices=["neg", "pos"], default="neg",
                    help="迎风面所在 z 半空间；neg=z<0 (默认，压缩侧)")
    ap.add_argument("--cmap", default="RdBu_r")
    ap.add_argument("--out_dir", default=None,
                    help="输出目录（默认写到 lf_npz 同目录）")
    args = ap.parse_args()

    lf_npz = (Path(args.lf_npz) if Path(args.lf_npz).is_absolute()
              else _PROJECT / args.lf_npz).resolve()
    fluent_csv = (Path(args.fluent_csv) if Path(args.fluent_csv).is_absolute()
                  else _PROJECT / args.fluent_csv).resolve()
    summary_path = (Path(args.summary).resolve() if args.summary
                    else lf_npz.parent / "summary.json")
    out_dir = (Path(args.out_dir).resolve() if args.out_dir
               else lf_npz.parent)

    for p in (lf_npz, fluent_csv, summary_path):
        if not p.exists():
            print(f"ERROR: 文件不存在: {p}", file=sys.stderr)
            return 1

    # ---- 1. LF 场 ----
    fields = np.load(lf_npz, allow_pickle=True)
    for k in ("Taw_tpg_w", "x_w_m", "span_w_m", "mask_w"):
        if k not in fields:
            print(f"ERROR: fields.npz 缺少 {k}", file=sys.stderr)
            return 1
    Taw = np.asarray(fields["Taw_tpg_w"], dtype=float).reshape(-1)
    x_w = np.asarray(fields["x_w_m"], dtype=float).reshape(-1)
    span_w = np.asarray(fields["span_w_m"], dtype=float).reshape(-1)
    mask_w = np.asarray(fields["mask_w"], dtype=float).reshape(-1)
    if not np.any(np.isfinite(Taw)):
        print("ERROR: Taw_tpg_w 全为 NaN，无法出图。", file=sys.stderr)
        return 1

    # ---- 2. summary / sampling / vehicle ----
    summary = _load_json(summary_path)
    sampling_path = Path(summary["resolved_paths"]["sampling_path"])
    vehicle_path = Path(summary["resolved_paths"]["vehicle_path"])
    sampling = _load_yaml(sampling_path)["canonical_sampling_spec"]
    vehicle = _load_yaml(vehicle_path)["vehicle_spec"]

    if str(sampling.get("mode", "")).strip() != "full_wing_surface_grid":
        print("ERROR: sampling.mode 不是 full_wing_surface_grid。", file=sys.stderr)
        return 1
    nx = int(sampling["x_over_c"]["n"])
    ny = int(sampling["y_over_b"]["n"])
    if Taw.size != nx * ny:
        print(f"ERROR: Taw.size={Taw.size} != nx*ny={nx*ny}", file=sys.stderr)
        return 1

    mach = summary.get("inputs", {}).get("mach")
    alpha = summary.get("inputs", {}).get("alpha_deg")
    h_m = summary.get("freestream", {}).get("h_m",
                                            summary.get("inputs", {}).get("h_m_override"))
    h_km = None if h_m is None else float(h_m) / 1000.0
    case_id = lf_npz.parent.name
    thermo_model = str(summary.get("inputs", {}).get("thermo_model", "tpg"))
    error_type = "signed_relpct"

    # ---- 3. Fluent 迎风面子集 ----
    fluent = _parse_fluent_csv(fluent_csv)
    if args.windward_z_sign == "neg":
        wsel = fluent["z"] < 0.0
    else:
        wsel = fluent["z"] >= 0.0
    fx = fluent["x"][wsel]
    fy = fluent["y"][wsel]
    ftw = fluent["Tw"][wsel]
    if fx.size == 0:
        print("ERROR: Fluent 迎风面子集为空。", file=sys.stderr)
        return 1

    # ---- 4. 最近邻映射 LF(x,span) -> Fluent(x,y) ----
    from scipy.spatial import cKDTree
    lf_valid = np.isfinite(x_w) & np.isfinite(span_w) & np.isfinite(Taw) & (mask_w > 0.5)
    kd = cKDTree(np.column_stack([fx, fy]))
    dist, idx = kd.query(np.column_stack([x_w, span_w]), k=1)
    tw_mapped = ftw[idx]

    # ---- 5. 相对误差 (%) ----
    with np.errstate(divide="ignore", invalid="ignore"):
        rel_err = np.where(np.abs(tw_mapped) > 1e-9,
                           (Taw - tw_mapped) / tw_mapped * 100.0, np.nan)
    rel_err = np.where(lf_valid, rel_err, np.nan)

    valid = np.isfinite(rel_err)
    n_valid = int(valid.sum())
    if n_valid == 0:
        print("ERROR: 无有效误差点。", file=sys.stderr)
        return 1
    err_v = rel_err[valid]

    # ---- 自适应色标参数 ----
    (case_min, case_max, adaptive_class,
     adapt_norm, adapt_cmap, adapt_levels, adapt_extend) = _build_adaptive_scale(err_v)

    # ---- 统计值 ----
    stats = {
        # --- 原有字段 ---
        "mean_signed_rel_err_pct": float(np.mean(err_v)),
        "mean_abs_rel_err_pct": float(np.mean(np.abs(err_v))),
        "p95_abs_rel_err_pct": float(np.percentile(np.abs(err_v), 95)),
        "max_abs_rel_err_pct": float(np.max(np.abs(err_v))),
        "over_fraction": float(np.mean(err_v > 0)),
        "n_valid": n_valid,
        "Taw_lf_mean_K": float(np.mean(Taw[valid])),
        "fluent_windward_Tw_mean_K": float(np.mean(tw_mapped[valid])),
        "nn_median_dist_m": float(np.median(dist[valid])),
        "nn_p95_dist_m": float(np.percentile(dist[valid], 95)),
        "nn_max_dist_m": float(np.max(dist[valid])),
        "windward_z_sign": args.windward_z_sign,
        "fluent_windward_faces": int(fx.size),
        # --- 新增字段 ---
        "signed_rel_error_min": case_min,
        "signed_rel_error_max": case_max,
        "under_fraction": float(np.mean(err_v < 0)),
        "zero_fraction": float(np.mean(np.abs(err_v) < 1e-12)),
        "fixed_scale_vmin": -FIXED_CLIM,
        "fixed_scale_vmax": FIXED_CLIM,
        "adaptive_scale_vmin": case_min,
        "adaptive_scale_vmax": case_max,
        "adaptive_scale_class": adaptive_class,
    }

    # 诊断软告警：NN 距离偏大只提示，不剔除、不改变 mapping 结果（本图仍是 diagnostic）。
    _NN_WARN_M = 0.3
    if stats["nn_p95_dist_m"] > _NN_WARN_M or stats["nn_max_dist_m"] > _NN_WARN_M:
        print(f"WARNING: NN mapping distance 偏大 (p95={stats['nn_p95_dist_m']*1000:.1f}mm "
              f"max={stats['nn_max_dist_m']*1000:.1f}mm > {_NN_WARN_M*1000:.0f}mm); "
              "diagnostic only, 不替代 P2R2 canon。", file=sys.stderr)

    # ---- 6. 出图准备 ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.tri as mtri
        from matplotlib.colors import TwoSlopeNorm
    except Exception as e:  # pragma: no cover
        raise RuntimeError("缺少 matplotlib，请先 pip install -r requirements.txt") from e

    X = x_w
    Y = span_w
    Z = rel_err
    tri = mtri.Triangulation(X, Y, _triangulate_structured(ny, nx))
    # 屏蔽含无效顶点的三角形
    tri_mask = np.any(~np.isfinite(Z[tri.triangles]), axis=1)
    tri.set_mask(tri_mask)

    Xg = X.reshape(ny, nx)
    Yg = Y.reshape(ny, nx)
    Vg = lf_valid.reshape(ny, nx)

    # ---- 固定色标 ±10% ----
    fixed_norm = TwoSlopeNorm(vmin=-FIXED_CLIM, vcenter=0.0, vmax=FIXED_CLIM)
    fixed_levels = np.linspace(-FIXED_CLIM, FIXED_CLIM, 41)
    fixed_cmap = plt.cm.RdBu_r
    fixed_title2 = "Color scale: fixed [-10%, +10%]"
    fixed_out = out_dir / f"{case_id}_windward_tpg_signed_rel_error_fixed_pm10.png"

    # ---- 自适应色标 ----
    if case_min == case_max:
        adapt_title2 = (f"Color scale: adaptive [{case_min:+.4f}%, {case_max:+.4f}%]"
                        f"  (class: {adaptive_class}, padded for display)")
    else:
        adapt_title2 = f"Color scale: adaptive [{case_min:+.4f}%, {case_max:+.4f}%]"
    adapt_out = out_dir / f"{case_id}_windward_tpg_signed_rel_error_adaptive.png"

    # ---- 绘制两张图 ----
    fixed_path = _plot_one(X, Y, Z, tri, lf_valid, nx, ny, Xg, Yg, Vg,
                           fixed_norm, fixed_cmap, fixed_levels, "both",
                           fixed_title2, stats, h_km, mach, alpha, fixed_out)
    adapt_path = _plot_one(X, Y, Z, tri, lf_valid, nx, ny, Xg, Yg, Vg,
                           adapt_norm, adapt_cmap, adapt_levels, adapt_extend,
                           adapt_title2, stats, h_km, mach, alpha, adapt_out)

    # ---- JSON 输出（一份 JSON 记录两种 scale） ----
    json_out = out_dir / f"{case_id}_windward_tpg_error_stats.json"
    with open(json_out, "w", encoding="utf-8") as fh:
        json.dump({
            "case": {"case_id": case_id, "mach": mach, "alpha_deg": alpha, "h_m": h_m},
            "thermo_model": thermo_model,
            "error_type": error_type,
            "inputs": {"lf_npz": str(lf_npz), "fluent_csv": str(fluent_csv)},
            "metric": "signed relative error (%) = (Taw_LF - Tw_Fluent)/Tw_Fluent*100",
            "mapping": "LF (x_w_m, span_w_m) -> Fluent (x-coordinate, y-coordinate), KD-tree NN; "
                       "Fluent windward subset by z sign",
            "scales": {
                "fixed": {
                    "vmin_pct": -FIXED_CLIM,
                    "vmax_pct": FIXED_CLIM,
                    "output_png": str(fixed_path),
                },
                "adaptive": {
                    "vmin_pct": stats["adaptive_scale_vmin"],
                    "vmax_pct": stats["adaptive_scale_vmax"],
                    "class": adaptive_class,
                    "output_png": str(adapt_path),
                },
            },
            "stats": stats,
            "output_json": str(json_out),
            "note": ("diagnostic visualization only; windward-only (no leeward temperature "
                     "error); does NOT replace P2R2 corrected comparison canon; "
                     "NOT validation complete"),
        }, fh, indent=2, ensure_ascii=False)

    # ---- 终端摘要 ----
    print("=" * 60)
    print("迎风面误差图已生成（双色标版）")
    print(f"  Fixed   : {fixed_path}")
    print(f"  Adaptive: {adapt_path}")
    print(f"  JSON    : {json_out}")
    print(f"  n_valid={n_valid}  Taw_LF_mean={stats['Taw_lf_mean_K']:.1f}K  "
          f"Fluent_wind_mean={stats['fluent_windward_Tw_mean_K']:.1f}K")
    print(f"  mean signed={stats['mean_signed_rel_err_pct']:+.2f}%  "
          f"mean|err|={stats['mean_abs_rel_err_pct']:.2f}%  "
          f"p95={stats['p95_abs_rel_err_pct']:.2f}%  max={stats['max_abs_rel_err_pct']:.2f}%")
    print(f"  min={case_min:+.4f}%  max={case_max:+.4f}%  adaptive_class={adaptive_class}")
    print(f"  NN dist median={stats['nn_median_dist_m']*1000:.1f}mm "
          f"p95={stats['nn_p95_dist_m']*1000:.1f}mm "
          f"max={stats['nn_max_dist_m']*1000:.1f}mm  "
          f"Fluent windward faces={stats['fluent_windward_faces']}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())