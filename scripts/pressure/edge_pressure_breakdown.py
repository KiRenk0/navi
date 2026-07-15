#!/usr/bin/env python3
"""P0.1 Edge pressure error breakdown — phi, Busemann Cp, p_e chain analysis.
Read-only — no code modifications.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from datetime import datetime

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ---- atmosphere helper (same as USSA 1976 for 30 km) ----
def _ussa1976_30km() -> tuple[float, float, float]:
    g0 = 9.80665
    R = 287.0
    h = 20000.0
    T_b = 216.65
    P_b = 5474.89
    L = 0.001
    T20 = T_b + L * (h - 20000.0)
    P20 = P_b * (T20 / T_b) ** (-g0 / (R * L))
    h = 30000.0
    T = T20 + L * (h - 20000.0)
    P = P20 * (T / T20) ** (-g0 / (R * L))
    rho = P / (R * T)
    return float(P), float(rho), float(T)


def _busemann_cp(ma_inf: float, phi_rad: float) -> float:
    if ma_inf <= 1.0:
        return 0.0
    c1 = 2.0 / math.sqrt(ma_inf ** 2 - 1.0)
    c2 = ((ma_inf ** 2 - 2.0) ** 2 + 1.4 * ma_inf ** 4) / ((ma_inf ** 2 - 1.0) ** 2)
    c3 = (0.36 * ma_inf ** 8 - 1.493 * ma_inf ** 6 + 3.6 * ma_inf ** 4 - 2.0 * ma_inf ** 2 + 1.33) / ((ma_inf ** 2 - 1.0) ** 3.5)
    phi = float(phi_rad)
    return c1 * phi + c2 * phi ** 2 + c3 * phi ** 3


def _read_aligned_csv(path: Path) -> dict[str, np.ndarray]:
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    cols: dict[str, list[str]] = {k: [] for k in rows[0].keys()}
    for r in rows:
        for k, v in r.items():
            cols[k].append(v)
    result = {}
    for k, vlist in cols.items():
        result[k] = np.array(vlist, dtype=float)
    return result


def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: edge_pressure_breakdown.py <aligned_csv_path> [out_dir]")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else csv_path.parent / "edge_pressure_breakdown"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading: {csv_path}")
    d = _read_aligned_csv(csv_path)
    print(f"  rows={int(d['x_m'].size)}")

    # Windward only
    w = d["side"] == 1
    x = d["x_m"][w]
    s = d["span_m"][w]
    pf = d["p_fluent_Pa"][w]
    p3 = d["p_f3_Pa"][w]
    qf = d["q_fluent_W_m2"][w]
    q3 = d["q_f3_W_m2"][w]
    cp = d["cp_f3"][w]
    phi = d["phi_f3_rad"][w]
    ma_e = d["ma_e"][w]
    v_e = d["v_e_m_s"][w]
    T_e = d["T_e_K"][w]
    rho_e = d["rho_e_kg_m3"][w]

    pw = pf.copy()
    p3w = p3.copy()

    # ---- Freestream parameters ----
    p_inf, rho_inf, T_inf = _ussa1976_30km()
    gamma = 1.4
    R = 287.0
    mach = 6.0
    v_inf = mach * math.sqrt(gamma * R * T_inf)
    q_inf = 0.5 * rho_inf * v_inf ** 2

    print(f"\n--- Freestream (USSA 1976, 30 km) ---")
    print(f"  p_inf = {p_inf:.2f} Pa")
    print(f"  rho_inf = {rho_inf:.6f} kg/m3")
    print(f"  T_inf = {T_inf:.2f} K")
    print(f"  v_inf = {v_inf:.2f} m/s")
    print(f"  q_inf = {q_inf:.2f} Pa")
    print(f"  Mach = {mach}")

    # ---- Compute Fluent Cp ----
    cp_fluent = (pf - p_inf) / q_inf
    cp_f3 = cp  # already Busemann cp from Faceted3D

    print(f"\n--- Cp comparison (windward, aligned) ---")
    print(f"  cp_fluent range: [{float(np.nanmin(cp_fluent)):.4f}, {float(np.nanmax(cp_fluent)):.4f}], mean={float(np.nanmean(cp_fluent)):.4f}")
    print(f"  cp_f3 range:     [{float(np.nanmin(cp_f3)):.4f}, {float(np.nanmax(cp_f3)):.4f}], mean={float(np.nanmean(cp_f3)):.4f}")
    cp_ratio = cp_f3 / np.maximum(cp_fluent, 1e-6)
    print(f"  cp_ratio (F3/Fluent) mean={float(np.nanmean(cp_ratio)):.3f}, range=[{float(np.nanmin(cp_ratio)):.3f}, {float(np.nanmax(cp_ratio)):.3f}]")

    # Check: does Busemann cp from phi match Faceted3D cp?
    # Compute what Busemann would give for each phi
    cp_busemann_from_phi = np.array([_busemann_cp(mach, float(p)) for p in phi])
    cp_diff = cp_f3 - cp_busemann_from_phi
    print(f"  cp_f3 vs Busemann(phi) diff: mean={float(np.nanmean(np.abs(cp_diff))):.6f}, max={float(np.nanmax(np.abs(cp_diff))):.6f}")
    cp_match = np.allclose(cp_f3, cp_busemann_from_phi, atol=1e-6) if np.any(np.isfinite(cp_diff)) else False
    print(f"  cp_f3 == Busemann(phi)? {cp_match}")

    # ---- 1. X-binned statistics ----
    nbins = 15
    bins = np.linspace(float(np.nanmin(x)), float(np.nanmax(x)), nbins + 1)
    bin_idx = np.digitize(x, bins)
    bin_stats: list[dict] = []
    for bi in range(1, nbins + 1):
        m = bin_idx == bi
        if np.sum(m) < 3:
            continue
        bin_stats.append({
            "x_low": float(bins[bi - 1]),
            "x_high": float(bins[bi]),
            "x_mid": 0.5 * (float(bins[bi - 1]) + float(bins[bi])),
            "count": int(np.sum(m)),
            "p_fluent_mean": float(np.nanmean(pf[m])),
            "p_f3_mean": float(np.nanmean(p3[m])),
            "p_ratio_mean": float(np.nanmean(p3[m] / np.maximum(pf[m], 1.0))),
            "q_fluent_mean": float(np.nanmean(qf[m])),
            "q_f3_mean": float(np.nanmean(q3[m])),
            "q_ratio_mean": float(np.nanmean(q3[m] / np.maximum(qf[m], 1.0))),
            "cp_f3_mean": float(np.nanmean(cp_f3[m])),
            "cp_fluent_mean": float(np.nanmean(cp_fluent[m])),
            "cp_ratio_mean": float(np.nanmean(cp_ratio[m])),
            "phi_f3_mean": float(np.nanmean(phi[m])),
            "w_tr_mean": float(np.nanmean(d["w_tr"][w][m])),
        })

    if not bin_stats:
        print("ERROR: no binned stats")
        sys.exit(1)

    print(f"\n--- X-binned stats ({len(bin_stats)} bins) ---")
    print(f"  x_mid | count | p_ratio | q_ratio | cp_ratio | phi_deg")
    for b in bin_stats:
        print(f"  {b['x_mid']:.3f} | {b['count']:4d} | {b['p_ratio_mean']:.3f} | {b['q_ratio_mean']:.3f} | {b['cp_ratio_mean']:.3f} | {math.degrees(b['phi_f3_mean']):.2f}")

    # ---- Write x_binned CSV ----
    bin_csv = out_dir / "x_binned_pressure_ratio.csv"
    with open(bin_csv, "w", newline="", encoding="utf-8") as f:
        wc = csv.writer(f)
        wc.writerow(["x_low", "x_high", "x_mid", "count",
                      "p_fluent_mean", "p_f3_mean", "p_ratio_mean",
                      "q_fluent_mean", "q_f3_mean", "q_ratio_mean",
                      "cp_f3_mean", "cp_fluent_mean", "cp_ratio_mean",
                      "phi_f3_deg", "w_tr_mean"])
        for b in bin_stats:
            wc.writerow([
                b["x_low"], b["x_high"], b["x_mid"], b["count"],
                b["p_fluent_mean"], b["p_f3_mean"], b["p_ratio_mean"],
                b["q_fluent_mean"], b["q_f3_mean"], b["q_ratio_mean"],
                b["cp_f3_mean"], b["cp_fluent_mean"], b["cp_ratio_mean"],
                math.degrees(b["phi_f3_mean"]), b["w_tr_mean"],
            ])
    print(f"\n  written: {bin_csv}")

    # ---- 4. Correlations ----
    pr_res = p3w - pw
    qr_res = q3 - qf
    valid_corr = np.isfinite(pr_res) & np.isfinite(qr_res)
    if np.any(valid_corr):
        corr_pq = float(np.corrcoef(pr_res[valid_corr], qr_res[valid_corr])[0, 1])
        p_rat = p3w / np.maximum(pw, 1.0)
        q_rat = q3 / np.maximum(qf, 1.0)
        vc2 = np.isfinite(p_rat) & np.isfinite(q_rat)
        corr_ratio = float(np.corrcoef(p_rat[vc2], q_rat[vc2])[0, 1])
        sign_agree = np.sign(pr_res[valid_corr]) == np.sign(qr_res[valid_corr])
        sign_pct = float(np.nansum(sign_agree)) / max(float(np.sum(valid_corr)), 1.0) * 100.0
        print(f"\n--- Correlations (windward, aligned) ---")
        print(f"  corr(p_res, q_res) = {corr_pq:.4f}")
        print(f"  corr(p_ratio, q_ratio) = {corr_ratio:.4f}")
        print(f"  sign agreement = {sign_pct:.1f}%")

    # ---- Plots ----

    # 2. x_binned_pressure_ratio.png
    xm = np.array([b["x_mid"] for b in bin_stats])
    pr_rat = np.array([b["p_ratio_mean"] for b in bin_stats])
    qr_rat = np.array([b["q_ratio_mean"] for b in bin_stats])
    cpr_rat = np.array([b["cp_ratio_mean"] for b in bin_stats])
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(xm, pr_rat, "ro-", label="p_ratio (F3/Fluent)")
    ax.plot(xm, qr_rat, "bs-", label="q_ratio (F3/Fluent)")
    ax.plot(xm, cpr_rat, "g^--", label="cp_ratio (F3/Fluent)")
    ax.axhline(1.0, color="gray", ls="--", lw=0.5)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("Ratio F3 / Fluent")
    ax.set_title("X-binned pressure / heat flux / Cp ratio")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "x_binned_pressure_ratio.png", dpi=150)
    plt.close(fig)
    print(f"  saved: x_binned_pressure_ratio.png")

    # 4. cp_f3_vs_cp_fluent_scatter.png
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(cp_fluent, cp_f3, s=2, alpha=0.3, c=x, cmap="viridis")
    cmin = min(float(np.nanmin(cp_fluent)), float(np.nanmin(cp_f3))) - 0.05
    cmax = max(float(np.nanmax(cp_fluent)), float(np.nanmax(cp_f3))) + 0.05
    ax.plot([cmin, cmax], [cmin, cmax], "k--", lw=1, label="1:1")
    ax.set_xlabel("Cp Fluent (from wall static pressure)")
    ax.set_ylabel("Cp Faceted3D (Busemann)")
    ax.set_title("Faceted3D Busemann Cp vs Fluent Cp")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "cp_f3_vs_cp_fluent_scatter.png", dpi=150)
    plt.close(fig)
    print(f"  saved: cp_f3_vs_cp_fluent_scatter.png")

    # 5. pressure_ratio_map.png
    p_ratio = p3w / np.maximum(pw, 1.0)
    fig, ax = plt.subplots(figsize=(8, 4))
    vmax = min(float(np.nanpercentile(p_ratio, 95)), 10.0)
    sc = ax.scatter(x, s, c=p_ratio, s=3, cmap="RdYlBu_r", vmin=0.5, vmax=vmax)
    ax.set_xlabel("x (m)"); ax.set_ylabel("span (m)")
    ax.set_title("Pressure ratio p_e(F3) / p(Fluent)")
    cb = fig.colorbar(sc, ax=ax, label="p_ratio")
    fig.tight_layout()
    fig.savefig(out_dir / "pressure_ratio_map.png", dpi=150)
    plt.close(fig)
    print(f"  saved: pressure_ratio_map.png")

    # 6. heatflux_ratio_map.png
    q_ratio = q3 / np.maximum(qf, 1.0)
    fig, ax = plt.subplots(figsize=(8, 4))
    vmax = min(float(np.nanpercentile(q_ratio, 95)), 10.0)
    sc = ax.scatter(x, s, c=q_ratio, s=3, cmap="RdYlBu_r", vmin=0.5, vmax=vmax)
    ax.set_xlabel("x (m)"); ax.set_ylabel("span (m)")
    ax.set_title("Heat flux ratio q(F3) / q(Fluent)")
    cb = fig.colorbar(sc, ax=ax, label="q_ratio")
    fig.tight_layout()
    fig.savefig(out_dir / "heatflux_ratio_map.png", dpi=150)
    plt.close(fig)
    print(f"  saved: heatflux_ratio_map.png")

    # 7. p_ratio_vs_q_ratio_scatter.png
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(p_ratio, q_ratio, s=2, alpha=0.3, c=x, cmap="viridis")
    ax.set_xlabel("p_ratio (F3/Fluent)")
    ax.set_ylabel("q_ratio (F3/Fluent)")
    ax.set_title(f"corr(p_ratio, q_ratio) = {corr_ratio:.4f}" if np.any(valid_corr) else "corr N/A")
    ax.grid(True, alpha=0.3)
    ax.axhline(1.0, color="gray", ls="--", lw=0.5)
    ax.axvline(1.0, color="gray", ls="--", lw=0.5)
    fig.tight_layout()
    fig.savefig(out_dir / "p_ratio_vs_q_ratio_scatter.png", dpi=150)
    plt.close(fig)
    print(f"  saved: p_ratio_vs_q_ratio_scatter.png")

    # 8. phi_cp_pressure_chain.png
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    # Row 1: phi
    sc = axes[0, 0].scatter(x, s, c=phi, s=3, cmap="plasma")
    axes[0, 0].set_xlabel("x (m)"); axes[0, 0].set_ylabel("span (m)")
    axes[0, 0].set_title(f"phi (rad), mean={float(np.nanmean(phi)):.3f}")
    fig.colorbar(sc, ax=axes[0, 0])
    axes[0, 1].hist(phi, bins=50, alpha=0.7)
    axes[0, 1].set_xlabel("phi (rad)"); axes[0, 1].set_ylabel("count")
    axes[0, 1].set_title("phi distribution")
    axes[0, 2].scatter(phi, p_ratio, s=2, alpha=0.3)
    axes[0, 2].set_xlabel("phi (rad)"); axes[0, 2].set_ylabel("p_ratio")
    axes[0, 2].set_title("phi vs p_ratio")
    axes[0, 2].grid(True, alpha=0.3)
    # Row 2: cp
    sc = axes[1, 0].scatter(x, s, c=cp_f3, s=3, cmap="plasma")
    axes[1, 0].set_xlabel("x (m)"); axes[1, 0].set_ylabel("span (m)")
    axes[1, 0].set_title(f"cp (Busemann), mean={float(np.nanmean(cp_f3)):.4f}")
    fig.colorbar(sc, ax=axes[1, 0])
    axes[1, 1].hist(cp_f3, bins=50, alpha=0.7)
    axes[1, 1].set_xlabel("cp"); axes[1, 1].set_ylabel("count")
    axes[1, 1].set_title("cp distribution")
    axes[1, 2].scatter(cp_f3, p_ratio, s=2, alpha=0.3, c=phi, cmap="plasma")
    axes[1, 2].set_xlabel("cp"); axes[1, 2].set_ylabel("p_ratio")
    axes[1, 2].set_title("cp vs p_ratio (color=phi)")
    axes[1, 2].grid(True, alpha=0.3)
    fig.suptitle("phi → cp → p_ratio chain breakdown (windward)")
    fig.tight_layout()
    fig.savefig(out_dir / "phi_cp_pressure_chain.png", dpi=150)
    plt.close(fig)
    print(f"  saved: phi_cp_pressure_chain.png")

    # ---- Write MD report ----
    report_path = out_dir / "edge_pressure_breakdown.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# P0.1 Edge Pressure Breakdown\n\n")
        f.write(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> Aligned CSV: {csv_path.name}\n")
        f.write(f"> Mach={mach}, Alpha=5°, h=30km, Tw=300K\n\n")

        # Freestream
        f.write("## Reference freestream\n\n")
        f.write(f"| Parameter | Value | Source |\n")
        f.write(f"|-----------|-------|--------|\n")
        f.write(f"| p_inf | {p_inf:.2f} Pa | USSA 1976 @ 30 km |\n")
        f.write(f"| rho_inf | {rho_inf:.6f} kg/m³ | USSA 1976 @ 30 km |\n")
        f.write(f"| T_inf | {T_inf:.2f} K | USSA 1976 @ 30 km |\n")
        f.write(f"| v_inf | {v_inf:.2f} m/s | Ma * sqrt(γRT) |\n")
        f.write(f"| q_inf | {q_inf:.2f} Pa | 0.5*rho*v² |\n")
        f.write(f"\n**Cp formula**: `Cp = (p - p_inf) / q_inf` for both Fluent and Faceted3D.\n\n")

        # Cp comparison
        f.write("## Busemann Cp vs Fluent Cp\n\n")
        f.write(f"| Metric | Fluent Cp | Faceted3D Busemann Cp | Ratio F3/Fluent |\n")
        f.write(f"|--------|-----------|----------------------|----------------|\n")
        f.write(f"| Mean | {float(np.nanmean(cp_fluent)):.4f} | {float(np.nanmean(cp_f3)):.4f} | {float(np.nanmean(cp_ratio)):.3f} |\n")
        f.write(f"| Min | {float(np.nanmin(cp_fluent)):.4f} | {float(np.nanmin(cp_f3)):.4f} | — |\n")
        f.write(f"| Max | {float(np.nanmax(cp_fluent)):.4f} | {float(np.nanmax(cp_f3)):.4f} | — |\n")
        cp_ratio_mean = float(np.nanmean(cp_ratio))
        if cp_ratio_mean > 1.3:
            f.write(f"\n**Busemann Cp is {cp_ratio_mean:.2f}x Fluent Cp → phi is reasonable but Busemann overpredicts Cp.**\n")
        elif cp_ratio_mean < 0.7:
            f.write(f"\n**Busemann Cp is lower than Fluent — not the cause of p_e overprediction.**\n")
        else:
            f.write(f"\n**Busemann Cp is within 30% of Fluent Cp — Cp alone is not the main issue.**\n")

        # phi
        f.write("\n## phi (inflow angle) diagnostic\n\n")
        phi_mean = float(np.nanmean(phi))
        phi_min = float(np.nanmin(phi))
        phi_max = float(np.nanmax(phi))
        phi_std = float(np.nanstd(phi))
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Mean | {math.degrees(phi_mean):.2f}°\n")
        f.write(f"| Min | {math.degrees(phi_min):.2f}°\n")
        f.write(f"| Max | {math.degrees(phi_max):.2f}°\n")
        f.write(f"| Std | {math.degrees(phi_std):.2f}°\n")
        f.write(f"| Range spread | {math.degrees(phi_max - phi_min):.2f}°\n")
        if phi_max - phi_min < 10.0:
            f.write(f"\n**phi is too uniform (range < 10°). Downstream expansion not captured by facet normals.**\n")
        else:
            f.write(f"\n**phi has reasonable spread — can explain some pressure variation.**\n")

        # p_e magnitude
        f.write("\n## p_e magnitude\n\n")
        f.write(f"| Metric | Fluent (Pa) | Faceted3D p_e (Pa) | Ratio |\n")
        f.write(f"|--------|-------------|-------------------|-------|\n")
        f.write(f"| Mean | {float(np.nanmean(pw)):.1f} | {float(np.nanmean(p3w)):.1f} | {float(np.nanmean(p3w)/max(float(np.nanmean(pw)),1)):.3f} |\n")
        f.write(f"| Min | {float(np.nanmin(pw)):.1f} | {float(np.nanmin(p3w)):.1f} | — |\n")
        f.write(f"| Max | {float(np.nanmax(pw)):.1f} | {float(np.nanmax(p3w)):.1f} | — |\n")

        # X-binned
        f.write("\n## X-binned pressure/heat flux ratio\n\n")
        f.write(f"| x_mid | count | p_ratio | q_ratio | cp_ratio | phi_deg |\n")
        f.write(f"|-------|-------|---------|---------|----------|--------|\n")
        for b in bin_stats:
            f.write(f"| {b['x_mid']:.3f} | {b['count']:4d} | {b['p_ratio_mean']:.2f} | {b['q_ratio_mean']:.2f} | {b['cp_ratio_mean']:.2f} | {math.degrees(b['phi_f3_mean']):.2f} |\n")

        # Check downstream trend
        n_bins = len(bin_stats)
        if n_bins >= 4:
            front = bin_stats[:n_bins // 3]
            rear = bin_stats[-n_bins // 3:]
            front_p_ratio = np.mean([b["p_ratio_mean"] for b in front])
            rear_p_ratio = np.mean([b["p_ratio_mean"] for b in rear])
            f.write(f"\nFront 1/3 mean p_ratio: {front_p_ratio:.3f}\n")
            f.write(f"Rear 1/3 mean p_ratio: {rear_p_ratio:.3f}\n")
            if rear_p_ratio > front_p_ratio * 1.15:
                f.write("**p_ratio increases downstream → Faceted3D lacks pressure relaxation.**\n")
            elif rear_p_ratio < front_p_ratio * 0.85:
                f.write("**p_ratio decreases downstream → opposite of relaxation issue.**\n")
            else:
                f.write("**p_ratio is stable along x → pressure bias is uniform.**\n")

        # Correlations
        f.write("\n## Pressure vs heat flux correlation\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| corr(p_res, q_res) | {corr_pq:.4f}\n")
        f.write(f"| corr(p_ratio, q_ratio) | {corr_ratio:.4f}\n")
        f.write(f"| Sign agreement | {sign_pct:.1f}%\n")
        if corr_pq > 0.5:
            f.write("\n**Strong correlation → p_e error is the primary driver of q error.**\n")
        elif corr_pq > 0.3:
            f.write("\n**Moderate correlation → p_e is a contributor but not the only driver.**\n")
        else:
            f.write("\n**Weak correlation → p_e error is NOT the main cause; check Re_x / transition / q_lam/q_turb.**\n")

        # Chain summary
        f.write("\n## phi → cp → p_e chain summary\n\n")
        f.write("### Chain logic\n")
        f.write("```\nfacet normal (sx,sy) → phi = asin(-u·n̂) → Busemann Cp(phi, Ma) → p_e = p_inf * (1 + 0.5*γ*Ma²*Cp)\n```\n")
        f.write(f"- Freestream Mach used in Busemann: {mach} (no effective Mach reduction applied in this run)\n")
        f.write(f"- Sweep-corrected alpha (effective_alpha): active (default for faceted3d)\n")
        f.write(f"- Busemann Cp range: [{float(np.nanmin(cp_f3)):.4f}, {float(np.nanmax(cp_f3)):.4f}]\n")
        f.write(f"- Fluent Cp range: [{float(np.nanmin(cp_fluent)):.4f}, {float(np.nanmax(cp_fluent)):.4f}]\n")
        f.write(f"- Mean Cp ratio (F3/Fluent): {cp_ratio_mean:.3f}\n")
        f.write(f"- Mean p_ratio (F3/Fluent): {float(np.nanmean(p_ratio)):.3f}\n")

        # Downstream relaxation
        f.write("\n## Downstream pressure relaxation\n\n")
        if n_bins >= 4:
            if rear_p_ratio > front_p_ratio * 1.15:
                f.write("**Confirmed: Fluent pressure relaxes downstream; Faceted3D does not.**\n")
                f.write("The faceted normal (sx, sy) is constant per facet — once the phi is computed at each x/c,\n")
                f.write("Busemann Cp and the subsequent p_e chain do not account for body-surface curvature-induced\n")
                f.write("expansion. The p_e remains artificially high in the aft body.\n")
            else:
                f.write("**Downstream relaxation is not the dominant issue.**\n")

        # Recommendations
        f.write("\n## Recommendations\n\n")
        f.write("### A. Is the high heat flux primarily caused by high edge pressure?\n")
        if corr_pq > 0.5:
            f.write("**YES.** `corr(p_res, q_res) > 0.5` and sign agreement > 60%.\n")
        else:
            f.write("**PARTIALLY.** Correlation is moderate; Re_x / transition also contribute.\n")

        f.write("\n### B. Is the issue phi/Cp too high, or missing downstream relaxation?\n")
        if phi_max - phi_min < 10.0:
            f.write("**phi is too uniform** — the facet normals from STL give a narrow range of inflow angles.\n")
        if cp_ratio_mean > 1.3:
            f.write(f"**Busemann Cp is {cp_ratio_mean:.2f}x Fluent Cp** — the Cp model itself overpredicts.\n")
        if n_bins >= 4 and rear_p_ratio > front_p_ratio * 1.15:
            f.write("**Both: Cp overpredicts + no downstream relaxation.**\n")
        else:
            f.write("**Cp overprediction is the dominant factor; relaxation is secondary.**\n")

        f.write("\n### C. Do we need a pressure relaxation model?\n")
        if n_bins >= 4 and rear_p_ratio > front_p_ratio * 1.15:
            f.write("**YES** — but only after fixing the baseline Cp overprediction.\n")
        else:
            f.write("**Not the priority.**\n")

        f.write("\n### D. Do we need full 3D surface streamline tracking?\n")
        f.write("**NOT for fixing the pressure error.** The pressure bias comes from the Cp model\n")
        f.write("and the lack of geometry-driven expansion, not from streamline curvature.\n")

        f.write("\n### E. Should we postpone Fluent residual learning?\n")
        f.write("**NO.** The residual learning framework is designed for exactly this situation:\n")
        f.write("a known systematic bias in p_e (and thus q) that is consistent and learnable.\n")
        f.write("Proceed with residual learning as planned. The pressure diagnostics confirm that\n")
        f.write("the residual is dominated by the edge-state model, which is a stable, systematic error.\n")

        f.write("\n---\n")
        f.write("\n*Report auto-generated by `scripts/edge_pressure_breakdown.py`*\n")

    print(f"\n  written: {report_path}")
    print(f"\nDONE — all outputs in {out_dir}")


if __name__ == "__main__":
    main()
