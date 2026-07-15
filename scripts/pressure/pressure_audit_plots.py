#!/usr/bin/env python3
"""Generate diagnostic plots for pressure audit.
Read-only — no code modifications.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import numpy as np

# Use agg backend for headless
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


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
    if len(sys.argv) < 2:
        print("Usage: pressure_audit_plots.py <aligned_csv_path> [out_dir]")
        sys.exit(1)
    csv_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else csv_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading aligned CSV: {csv_path}")
    d = _read_aligned_csv(csv_path)
    print(f"  rows={int(d['x_m'].size)}")

    # Windward only
    w = d["side"] == 1
    x = d["x_m"][w]
    s = d["span_m"][w]
    pf = d["p_fluent_Pa"][w]
    p3 = d["p_f3_Pa"][w]
    pr = d["p_residual_Pa"][w]
    qf = d["q_fluent_W_m2"][w]
    q3 = d["q_f3_W_m2"][w]
    qr = q3 - qf
    cp = d["cp_f3"][w]
    phi = d["phi_f3_rad"][w]

    # 1. p_fluent_vs_p_edge_scatter
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(pf, p3, s=2, alpha=0.3, c=x, cmap="viridis")
    pmin = min(float(np.nanmin(pf)), float(np.nanmin(p3)))
    pmax = max(float(np.nanmax(pf)), float(np.nanmax(p3)))
    ax.plot([pmin, pmax], [pmin, pmax], "k--", lw=1, label="1:1")
    ax.set_xlabel("Fluent wall static pressure (Pa)")
    ax.set_ylabel("Faceted3D p_e (Pa)")
    ax.set_title("Fluent p vs Faceted3D p_e (windward)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "p_fluent_vs_p_edge_scatter.png", dpi=150)
    plt.close(fig)
    print(f"  saved: p_fluent_vs_p_edge_scatter.png")

    # 2. centerline_pressure_comparison
    cl = s < 0.05
    if np.any(cl):
        cl_x = x[cl]
        cl_pf = pf[cl]
        cl_p3 = p3[cl]
        order = np.argsort(cl_x)
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(cl_x[order], cl_pf[order], "b-", label="Fluent wall static pressure", lw=1.5)
        ax.plot(cl_x[order], cl_p3[order], "r--", label="Faceted3D p_e", lw=1.5)
        ax.set_xlabel("x (m)")
        ax.set_ylabel("Pressure (Pa)")
        ax.set_title("Centerline pressure (span < 0.01 m)")
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "centerline_pressure_comparison.png", dpi=150)
        plt.close(fig)
        print(f"  saved: centerline_pressure_comparison.png")

        # 3. centerline_heatflux_comparison
        cl_qf = qf[cl]
        cl_q3 = q3[cl]
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(cl_x[order], cl_qf[order], "b-", label="Fluent total surface heat flux", lw=1.5)
        ax.plot(cl_x[order], cl_q3[order], "r--", label="Faceted3D q_low", lw=1.5)
        ax.set_xlabel("x (m)")
        ax.set_ylabel("Heat flux (W/m²)")
        ax.set_title("Centerline heat flux (span < 0.01 m)")
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "centerline_heatflux_comparison.png", dpi=150)
        plt.close(fig)
        print(f"  saved: centerline_heatflux_comparison.png")

    # 4. pressure_residual_map_windward
    fig, ax = plt.subplots(figsize=(8, 4))
    sc = ax.scatter(x, s, c=pr, s=3, cmap="RdBu_r", vmin=-max(abs(pr)), vmax=max(abs(pr)))
    ax.set_xlabel("x (m)")
    ax.set_ylabel("span (m)")
    ax.set_title("Pressure residual p_e(F3) - p(Fluent) (Pa)")
    cb = fig.colorbar(sc, ax=ax, label="Δp (Pa)")
    fig.tight_layout()
    fig.savefig(out_dir / "pressure_residual_map_windward.png", dpi=150)
    plt.close(fig)
    print(f"  saved: pressure_residual_map_windward.png")

    # 5. heatflux_residual_map_windward
    fig, ax = plt.subplots(figsize=(8, 4))
    sc = ax.scatter(x, s, c=qr, s=3, cmap="RdBu_r", vmin=-max(abs(qr)), vmax=max(abs(qr)))
    ax.set_xlabel("x (m)")
    ax.set_ylabel("span (m)")
    ax.set_title("Heat flux residual q(F3) - q(Fluent) (W/m²)")
    cb = fig.colorbar(sc, ax=ax, label="Δq (W/m²)")
    fig.tight_layout()
    fig.savefig(out_dir / "heatflux_residual_map_windward.png", dpi=150)
    plt.close(fig)
    print(f"  saved: heatflux_residual_map_windward.png")

    # 6. cp_phi_pressure_map
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    sc0 = axes[0].scatter(x, s, c=phi, s=3, cmap="plasma")
    axes[0].set_xlabel("x (m)"); axes[0].set_ylabel("span (m)")
    axes[0].set_title("phi (rad)"); fig.colorbar(sc0, ax=axes[0])
    sc1 = axes[1].scatter(x, s, c=cp, s=3, cmap="plasma")
    axes[1].set_xlabel("x (m)"); axes[1].set_ylabel("span (m)")
    axes[1].set_title("Busemann cp"); fig.colorbar(sc1, ax=axes[1])
    sc2 = axes[2].scatter(x, s, c=p3, s=3, cmap="plasma")
    axes[2].set_xlabel("x (m)"); axes[2].set_ylabel("span (m)")
    axes[2].set_title("p_e (Pa)"); fig.colorbar(sc2, ax=axes[2])
    fig.suptitle("Faceted3D: phi → cp → p_e chain (windward)")
    fig.tight_layout()
    fig.savefig(out_dir / "cp_phi_pressure_map.png", dpi=150)
    plt.close(fig)
    print(f"  saved: cp_phi_pressure_map.png")

    print(f"\nAll plots saved to {out_dir}")


if __name__ == "__main__":
    main()
