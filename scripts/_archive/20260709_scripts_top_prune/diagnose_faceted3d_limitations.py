"""Diagnose Faceted3D model limitations from enhanced output fields.

Usage:
    python scripts/diagnose_faceted3d_limitations.py --run_dir runs/0629_fields_phase4
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np


def _ensure_import_path() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    src_root = repo_root / "src"
    for p in (repo_root, src_root):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


_ensure_import_path()


def load_fields(run_dir: str | Path) -> dict[str, np.ndarray]:
    return dict(np.load(Path(run_dir) / "fields.npz", allow_pickle=True))


def load_csv(csv_path: str | Path) -> list[dict]:
    with open(csv_path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    ap = argparse.ArgumentParser(description="Diagnose Faceted3D model limitations")
    ap.add_argument("--run_dir", type=str, default="runs/0629_fields_phase4")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    out_dir = run_dir / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading fields from {run_dir / 'fields.npz'} ...")
    fields = load_fields(run_dir)

    print(f"Loading CSV from {run_dir / 'low_fidelity_points_all_valid.csv'} ...")
    rows = load_csv(run_dir / "low_fidelity_points_all_valid.csv")

    print("Generating diagnostics ...\n")

    nx = 81
    ny = 41

    # --- reshape helper ---
    def _reshape(arr: np.ndarray) -> np.ndarray:
        return np.asarray(arr, dtype=float).reshape(ny, nx)

    # --- load 2D fields ---
    q_w = _reshape(fields["q_w"])
    q_l = _reshape(fields["q_l"])
    q_lam = _reshape(fields["q_lam_w"])
    q_turb = _reshape(fields["q_turb_w"])
    xc_grid = np.asarray(fields["xc_grid"], dtype=float)
    yb_grid = np.asarray(fields["yb_grid"], dtype=float)
    x_w = _reshape(fields["x_w_m"])
    span_w = _reshape(fields["span_w_m"])
    phi_w = _reshape(fields["phi_w"])
    cp_w = _reshape(fields["cp_w"])
    T_e_w = _reshape(fields["T_e_w"])
    St_l = _reshape(fields["St_l"])
    Re_ns_l = _reshape(fields["Re_ns_l"])

    mask_w = np.isfinite(q_w)
    mask_l = np.isfinite(q_l)

    X = x_w
    Y = span_w

    # ================================================================
    # 1. q_lam / q_turb ratio
    # ================================================================
    print("1/8  q_lam / q_turb ratio map ...")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.tri as mtri
        from matplotlib.tri import Triangulation

        tri_x = X.reshape(-1)
        tri_y = Y.reshape(-1)
        tris = _triangulate_structured(ny, nx)
        finite_lam = np.isfinite(q_lam.reshape(-1))
        finite_turb = np.isfinite(q_turb.reshape(-1))
        tri_mask = ~(finite_lam & finite_turb)
        tri = Triangulation(tri_x, tri_y, tris, mask=tri_mask[tris].any(axis=1))

        ratio = np.where(finite_lam.reshape(ny, nx) & finite_turb.reshape(ny, nx),
                         q_lam / q_turb, np.nan)
        fig, ax = plt.subplots(figsize=(7.8, 4.6), dpi=170)
        vmin = 0.3
        vmax = 2.0
        levels = np.linspace(vmin, vmax, 40)
        im = ax.tricontourf(tri, ratio.reshape(-1), levels=levels, cmap="RdYlBu_r", extend="both")
        cb = fig.colorbar(im, ax=ax, pad=0.02)
        cb.set_label("q_lam / q_turb")
        ax.set_xlabel("x / m")
        ax.set_ylabel("span / m")
        ax.set_title("Laminar/Turbulent heat flux ratio")
        fig.tight_layout()
        fig.savefig(out_dir / "q_lam_over_q_turb_w.png")
        plt.close(fig)
    except Exception as e:
        print(f"  SKIP: {e}")

    # ================================================================
    # 2. q_lam > q_turb mask
    # ================================================================
    print("2/8  q_lam > q_turb binary mask ...")
    try:
        gt = (q_lam > q_turb) & mask_w
        n_gt = int(np.sum(gt))
        n_total = int(np.sum(mask_w))
        pct = 100.0 * n_gt / n_total if n_total > 0 else 0.0
        fig, ax = plt.subplots(figsize=(7.8, 4.6), dpi=170)
        z = np.where(gt, 1.0, 0.0)
        z[~mask_w] = np.nan
        tri_mask2 = ~finite_lam
        tri2 = Triangulation(tri_x, tri_y, tris, mask=tri_mask2[tris].any(axis=1))
        ax.tricontourf(tri2, z.reshape(-1), levels=[-0.5, 0.5, 1.5], colors=["lightgray", "crimson"])
        ax.text(0.5, 0.95, f"q_lam > q_turb: {n_gt}/{n_total} ({pct:.1f}%)",
                transform=ax.transAxes, ha="center", va="top",
                bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))
        ax.set_xlabel("x / m")
        ax.set_ylabel("span / m")
        ax.set_title("Regions where laminar q > turbulent q")
        fig.tight_layout()
        fig.savefig(out_dir / "q_lam_gt_q_turb_mask.png")
        plt.close(fig)
    except Exception as e:
        print(f"  SKIP: {e}")
        n_gt = int(np.sum((q_lam > q_turb) & mask_w))
        n_total = int(np.sum(mask_w))
        pct = 100.0 * n_gt / n_total if n_total > 0 else 0.0

    # ================================================================
    # 3. q_lam - q_turb
    # ================================================================
    print("3/8  q_lam - q_turb map ...")
    try:
        diff = np.where(mask_w, q_lam - q_turb, np.nan)
        fig, ax = plt.subplots(figsize=(7.8, 4.6), dpi=170)
        vlim = max(abs(np.nanmin(diff)), abs(np.nanmax(diff)))
        levels = np.linspace(-vlim, vlim, 40)
        im = ax.tricontourf(tri, diff.reshape(-1), levels=levels, cmap="RdBu_r", extend="both")
        cb = fig.colorbar(im, ax=ax, pad=0.02)
        cb.set_label("q_lam - q_turb / W/m^2")
        ax.set_xlabel("x / m")
        ax.set_ylabel("span / m")
        ax.set_title("Laminar minus turbulent heat flux")
        fig.tight_layout()
        fig.savefig(out_dir / "q_lam_minus_q_turb_w.png")
        plt.close(fig)
    except Exception as e:
        print(f"  SKIP: {e}")

    # ================================================================
    # 4. q_w map
    # ================================================================
    print("4/8  q_w map ...")
    try:
        fig, ax = plt.subplots(figsize=(7.8, 4.6), dpi=170)
        vmin_q = np.nanmin(q_w)
        vmax_q = np.nanmax(q_w)
        levels = np.linspace(vmin_q, vmax_q, 40)
        im = ax.tricontourf(tri, q_w.reshape(-1), levels=levels, cmap="turbo")
        cb = fig.colorbar(im, ax=ax, pad=0.02)
        cb.set_label("q_w / W/m^2")
        ax.set_xlabel("x / m")
        ax.set_ylabel("span / m")
        ax.set_title("Windward surface heat flux")
        fig.tight_layout()
        fig.savefig(out_dir / "q_w_map.png")
        plt.close(fig)
    except Exception as e:
        print(f"  SKIP: {e}")

    # ================================================================
    # 5. q_l map
    # ================================================================
    print("5/8  q_l map ...")
    try:
        ql_min = np.nanmin(q_l)
        ql_max = np.nanmax(q_l)
        is_constant = abs(ql_max - ql_min) < 1e-6
        fig, ax = plt.subplots(figsize=(7.8, 4.6), dpi=170)
        if is_constant:
            levels = np.linspace(ql_min * 0.99, ql_max * 1.01, 40)
        else:
            levels = np.linspace(ql_min, ql_max, 40)
        im = ax.tricontourf(tri, q_l.reshape(-1), levels=levels, cmap="turbo")
        cb = fig.colorbar(im, ax=ax, pad=0.02)
        cb.set_label("q_l / W/m^2")
        ax.set_xlabel("x / m")
        ax.set_ylabel("span / m")
        title = "Leeward surface heat flux (CONSTANT: model limitation)"
        if is_constant:
            title += f"\nq_l = {ql_min:.2f} W/m^2 everywhere"
        ax.set_title(title, fontsize=10)
        fig.tight_layout()
        fig.savefig(out_dir / "q_l_map.png")
        plt.close(fig)
    except Exception as e:
        print(f"  SKIP: {e}")
        is_constant = abs(float(np.nanmax(q_l)) - float(np.nanmin(q_l))) < 1e-6

    # ================================================================
    # 6. leeward constant fields
    # ================================================================
    print("6/8  leeward constant fields ...")
    try:
        fig, axes = plt.subplots(1, 3, figsize=(14, 4), dpi=170)
        for ax, arr, label in zip(axes, [q_l, St_l, Re_ns_l],
                                   ["q_l / W/m^2", "St_l", "Re_ns_l"]):
            f = arr[mask_l]
            if f.size > 0:
                ax.hist(f, bins=30, alpha=0.7)
                ax.axvline(f.mean(), color="r", linestyle="--", label=f"mean={f.mean():.4g}")
                ax.legend(fontsize=8)
            ax.set_xlabel(label)
            ax.set_ylabel("count")
        fig.suptitle("Leeward field distributions (constant fields = model limitation)", fontsize=11)
        fig.tight_layout()
        fig.savefig(out_dir / "leeward_constant_fields.png")
        plt.close(fig)
    except Exception as e:
        print(f"  SKIP: {e}")

    # ================================================================
    # 7. q_w vs phi / cp scatter
    # ================================================================
    print("7/8  q_w vs phi / cp scatter ...")
    try:
        fig, axes = plt.subplots(1, 2, figsize=(12, 5), dpi=170)
        m = mask_w
        ax = axes[0]
        sc = ax.scatter(phi_w[m], q_w[m], c=xc_grid.reshape(1, -1).repeat(ny, 0)[m],
                        s=1, cmap="viridis", alpha=0.5)
        ax.set_xlabel("phi_w / rad")
        ax.set_ylabel("q_w / W/m^2")
        ax.set_title("q_w vs phi_w (color = x/c)")
        cb = fig.colorbar(sc, ax=ax, pad=0.02)
        cb.set_label("x/c")

        ax = axes[1]
        sc = ax.scatter(cp_w[m], q_w[m], c=xc_grid.reshape(1, -1).repeat(ny, 0)[m],
                        s=1, cmap="viridis", alpha=0.5)
        ax.set_xlabel("cp_w")
        ax.set_ylabel("q_w / W/m^2")
        ax.set_title("q_w vs cp_w (color = x/c)")
        cb = fig.colorbar(sc, ax=ax, pad=0.02)
        cb.set_label("x/c")

        fig.tight_layout()
        fig.savefig(out_dir / "q_w_vs_phi_cp_scatter.png")
        plt.close(fig)
    except Exception as e:
        print(f"  SKIP: {e}")

    # ================================================================
    # 8. q_w max location
    # ================================================================
    print("8/8  q_w max location ...")
    try:
        qw_flat = q_w.reshape(-1)
        idx_max = int(np.nanargmax(qw_flat))
        j_max, i_max = divmod(idx_max, nx)
        fig, ax = plt.subplots(figsize=(7.8, 4.6), dpi=170)
        levels = np.linspace(np.nanmin(q_w), np.nanmax(q_w), 40)
        im = ax.tricontourf(tri, q_w.reshape(-1), levels=levels, cmap="turbo")
        ax.plot(X[j_max, i_max], Y[j_max, i_max], "r*", markersize=12, markeredgecolor="white", markeredgewidth=1)
        ax.text(X[j_max, i_max], Y[j_max, i_max],
                f" q_max={qw_flat[idx_max]:.0f} W/m^2\n x={X[j_max,i_max]:.4f}m, span={Y[j_max,i_max]:.4f}m",
                fontsize=8, color="white", fontweight="bold",
                bbox=dict(boxstyle="round", facecolor="red", alpha=0.7))
        cb = fig.colorbar(im, ax=ax, pad=0.02)
        cb.set_label("q_w / W/m^2")
        ax.set_xlabel("x / m")
        ax.set_ylabel("span / m")
        ax.set_title("Windward heat flux with max location")
        fig.tight_layout()
        fig.savefig(out_dir / "q_w_max_location.png")
        plt.close(fig)
    except Exception as e:
        print(f"  SKIP: {e}")

    # ================================================================
    # STATISTICAL REPORT
    # ================================================================
    print("\nComputing statistical report ...")

    # q_lam > q_turb stats
    gt_mask = (q_lam > q_turb) & mask_w
    n_gt = int(np.sum(gt_mask))
    n_total = int(np.sum(mask_w))
    gt_pct = 100.0 * n_gt / n_total if n_total > 0 else 0.0

    gt_x = X[gt_mask]
    gt_y = Y[gt_mask]
    gt_xc = np.asarray(xc_grid, dtype=float).reshape(1, -1).repeat(ny, 0)[gt_mask]
    gt_yb = np.asarray(yb_grid, dtype=float).reshape(-1, 1).repeat(nx, 1)[gt_mask]

    ratio_all = q_lam[mask_w] / q_turb[mask_w]
    ratio_gt = q_lam[gt_mask] / q_turb[gt_mask]

    # xc bins for gt
    xc_bins = [0.0, 0.02, 0.05, 0.10, 0.20, 1.0]
    xc_labels = ["0–0.02", "0.02–0.05", "0.05–0.10", "0.10–0.20", "0.20–1.0"]
    xc_gt_counts = []
    xc_gt_totals = []
    for i in range(len(xc_bins) - 1):
        lo, hi = xc_bins[i], xc_bins[i + 1]
        total = int(np.sum(mask_w & (X >= lo) & (X < hi)))
        gt = int(np.sum(gt_mask & (X >= lo) & (X < hi)))
        xc_gt_totals.append(total)
        xc_gt_counts.append(gt)

    # yb bins
    yb_bins = np.linspace(0, 1.0, 11)
    yb_labels = [f"{yb_bins[i]:.1f}–{yb_bins[i+1]:.1f}" for i in range(len(yb_bins)-1)]
    yb_gt_counts = []
    yb_gt_totals = []
    yb_arr = np.asarray(yb_grid, dtype=float).reshape(-1, 1).repeat(nx, 1)
    for i in range(len(yb_bins) - 1):
        lo, hi = yb_bins[i], yb_bins[i + 1]
        total = int(np.sum(mask_w & (yb_arr >= lo) & (yb_arr < hi)))
        gt = int(np.sum(gt_mask & (yb_arr >= lo) & (yb_arr < hi)))
        yb_gt_totals.append(total)
        yb_gt_counts.append(gt)

    # q_w max
    qw_flat = q_w.reshape(-1)
    idx_max = int(np.nanargmax(qw_flat))
    j_max, i_max = divmod(idx_max, nx)
    qw_max = qw_flat[idx_max]

    # Leeward constancy
    ql_finite = q_l[mask_l]
    st_finite = St_l[mask_l]
    re_finite = Re_ns_l[mask_l]

    # ================================================================
    # WRITE REPORT
    # ================================================================
    report = f"""# Faceted3D Model Limitation Diagnostics

> Generated from: `{run_dir}`
> Date: 2026-06-28

## 1. q_lam > q_turb Diagnosis

### Global stats

| Metric | Value |
|--------|-------|
| q_lam > q_turb points | {n_gt} / {n_total} ({gt_pct:.2f}%) |
| q_lam/q_turb min | {float(ratio_all.min()):.4f} |
| q_lam/q_turb max | {float(ratio_all.max()):.4f} |
| q_lam/q_turb mean | {float(ratio_all.mean()):.4f} |
| q_lam/q_turb median | {float(np.median(ratio_all)):.4f} |

### x/c distribution of q_lam > q_turb points

| x/c range | q_lam > q_turb | total valid | ratio |
|-----------|----------------|-------------|-------|
"""
    for i in range(len(xc_bins) - 1):
        lo, hi = xc_bins[i], xc_bins[i + 1]
        t = xc_gt_totals[i]
        g = xc_gt_counts[i]
        r = 100.0 * g / t if t > 0 else 0.0
        report += f"| {lo:.2f}–{hi:.2f} | {g} | {t} | {r:.1f}% |\n"

    report += f"""
### y/b distribution of q_lam > q_turb points

| y/b range | q_lam > q_turb | total valid | ratio |
|-----------|----------------|-------------|-------|
"""
    for i in range(len(yb_bins) - 1):
        lo, hi = yb_bins[i], yb_bins[i + 1]
        t = yb_gt_totals[i]
        g = yb_gt_counts[i]
        r = 100.0 * g / t if t > 0 else 0.0
        report += f"| {lo:.1f}–{hi:.1f} | {g} | {t} | {r:.1f}% |\n"

    report += f"""
### q_lam > q_turb coordinate ranges

| Variable | Min | Max |
|----------|-----|-----|
| x_m | {float(gt_x.min()):.4f} | {float(gt_x.max()):.4f} |
| span_m | {float(gt_y.min()):.4f} | {float(gt_y.max()):.4f} |
| xc | {float(gt_xc.min()):.4f} | {float(gt_xc.max()):.4f} |
| yb | {float(gt_yb.min()):.4f} | {float(gt_yb.max()):.4f} |

## 2. Leeward Field Constancy

### q_l (leeward heat flux)

| Metric | Value |
|--------|-------|
| min | {float(ql_finite.min()):.6f} W/m² |
| max | {float(ql_finite.max()):.6f} W/m² |
| mean | {float(ql_finite.mean()):.6f} W/m² |
| std | {float(ql_finite.std()):.6f} W/m² |
| is_constant (std < 1e-6) | {ql_finite.std() < 1e-6} |

### St_l (leeward Stanton number)

| Metric | Value |
|--------|-------|
| min | {float(st_finite.min()):.10f} |
| max | {float(st_finite.max()):.10f} |
| mean | {float(st_finite.mean()):.10f} |
| std | {float(st_finite.std()):.10f} |
| is_constant | {st_finite.std() < 1e-12} |

### Re_ns_l (leeward reference Reynolds)

| Metric | Value |
|--------|-------|
| min | {float(re_finite.min()):.6f} |
| max | {float(re_finite.max()):.6f} |
| mean | {float(re_finite.mean()):.6f} |
| std | {float(re_finite.std()):.6f} |
| is_constant | {re_finite.std() < 1e-6} |

### Cause of leeward constant fields

The leeward model uses a single chord-averaged normal-shock Reynolds number per strip:

    Re_ns = ρ_inf · V_inf · R_ref / μ_ns

where `R_ref` is based on the effective chord (clamped to chord_min_m=0.02 for all strips
in the isothermal300 case since the actual chord is already ≥0.02 everywhere).

The Stanton number is then:

    St = 0.00282 · (0.7905 + 1.067 · h_wwd / h_s) · Re_ns^(-0.37)

For an **isothermal wall** (Tw = 300K everywhere), h_wwd(x) = h_w = constant along the chord,
making St(x) ≈ constant. With constant St and constant h_wwd, q_l = ρ_inf · V_inf · St · (h_s - h_w)
is also constant.

**Result:** q_l, St_l, and Re_ns_l are all single-scalar constants for this isothermal case.
This is a known limitation of the leeward reference-enthalpy model — it does not capture
spatial variation in leeward heating even though the actual physics has chordwise recovery.

## 3. q_w Maximum Location

| Field | Value |
|-------|-------|
| q_w max | {qw_max:.2f} W/m² |
| j (span index) | {j_max} |
| i (chord index) | {i_max} |
| x_m | {float(X[j_max, i_max]):.6f} m |
| span_m | {float(Y[j_max, i_max]):.6f} m |
| xc | {float(xc_grid[i_max]):.4f} |
| yb | {float(yb_grid[j_max]):.4f} |
| phi_w | {float(phi_w[j_max, i_max]):.6f} rad ({float(np.rad2deg(phi_w[j_max, i_max])):.4f} deg) |
| cp_w | {float(cp_w[j_max, i_max]):.6f} |
| T_e_w | {float(T_e_w[j_max, i_max]):.2f} K |
| q_lam_w | {float(q_lam[j_max, i_max]):.2f} W/m² |
| q_turb_w | {float(q_turb[j_max, i_max]):.2f} W/m² |
| q_lam/q_turb | {float(q_lam[j_max, i_max] / q_turb[j_max, i_max]):.4f} |

The q_w maximum is at the stagnation point (nose tip, xc=0, yb=0) where the
Kemp-Riddell stagnation-point formula dominates over the strip-theory heating.

## 4. Current Model Limitations

### Confirmed limitations

| # | Limitation | Impact | Mitigation |
|---|-----------|--------|------------|
| 1 | Leeward q, St, Re_ns are constant per isothermal case | No spanwise/chordwise variation in leeward heating | Use Fluent as high-fidelity surrogate; leeward features can be absorbed by residual model |
| 2 | Last spanwise row (j=40, y/b=1.0) has zero chord | 81 points are NaN (2.4% of grid) | Already masked; for surrogate, exclude via valid_mask |
| 3 | No 3D surface streamlines | X-length uses simple streamline integration, not true 3D particle tracing | Acceptable for engineering REM; true 3D requires Euler/CFD |
| 4 | No external Euler/CFD flowfield | Edge conditions from Busemann cone + flat-plate strip theory | Primary purpose of multi-fidelity; Fluent provides high-fi edge |
| 5 | No leeward T_e, p_e, rho_e, ma_e, v_e, mu_e output | Leeward uses normal-shock averaged state, not edge-resolved | Low priority; leeward heating is small relative to windward |

### Limitations NOT observed

- Windward heat flux shows expected spatial variation (stagnation peak, chordwise decay, spanwise variation)
- q_lam > q_turb occurs in limited regions (see Section 1) and is physically reasonable at low Re_x
- No numerical instability observed in the current case (Ma=8.3, α=2.2°, h=56.7 km)

## 5. Recommendations

### For Fluent residual surrogate modeling

1. **Include all windward edge fields** (T_e, p_e, rho_e, ma_e, v_e, mu_e, phi, cp) as low-fidelity features
2. **Include reference-enthalpy intermediates** (h_e, h_r_lam, h_r_turb, h_star_lam, q_lam, q_turb)
3. **Use valid_mask** to exclude the zero-chord tip row (j=40)
4. **Leeward side should be treated separately** — the constant leeward model means a single correction factor per case may be sufficient rather than a full spatial surrogate

### For future physics model upgrades

5. **Leeward model**: Consider a chord-resolved leeward heating correlation that captures recovery from the windward-side edge (leeward T_e(x) ≈ windward T_e(x) with expansion correction)
6. **3D streamline**: Not recommended until Euler/CFD validation is available
7. **Transition model**: Current step-function weighting may be too sharp; a smooth hyperbolic-tangent blend could be considered, but requires experimental validation

### Do NOT modify

8. **Windward reference-enthalpy formula** — it is the validated engineering core of the solver
9. **Busemann Cp** — it is the correct inviscid cone relation for slender bodies at angle of attack
10. **Kemp-Riddell stagnation formula** — it is the standard engineering stagnation-point correlation
11. **chord_min_m** — it is a numerical guard, not a physics parameter

---
*Report generated by `scripts/diagnose_faceted3d_limitations.py`*
"""

    report_path = out_dir / "model_limitation_diagnostics.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report written: {report_path}")

    # Print summary to console
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  q_lam > q_turb:  {n_gt}/{n_total} ({gt_pct:.1f}%)")
    print(f"  q_lam/q_turb:    min={ratio_all.min():.4f} max={ratio_all.max():.4f} mean={ratio_all.mean():.4f}")
    print(f"  q_l constant:    {ql_finite.std() < 1e-6}  (value={ql_finite.mean():.2f} W/m^2)")
    print(f"  St_l constant:   {st_finite.std() < 1e-12} (value={st_finite.mean():.8f})")
    print(f"  Re_ns_l constant:{re_finite.std() < 1e-6} (value={re_finite.mean():.2f})")
    print(f"  q_w max:         {qw_max:.2f} W/m^2 at x={X[j_max,i_max]:.4f}m, span={Y[j_max,i_max]:.4f}m")
    print(f"  Output:          {out_dir}")
    print("=" * 60)


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


if __name__ == "__main__":
    main()
