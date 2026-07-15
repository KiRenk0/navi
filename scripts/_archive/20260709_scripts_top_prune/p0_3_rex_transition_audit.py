#!/usr/bin/env python3
"""P0.3 Task C: Re_x / transition diagnosis.
Read-only sandbox — no solver modifications.
"""

from __future__ import annotations

import csv, math, sys
from pathlib import Path
from datetime import datetime

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _read_csv(path: Path) -> dict[str, np.ndarray]:
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f); rows = list(reader)
    cols = {k: [] for k in rows[0].keys()}
    for r in rows:
        for k, v in r.items(): cols[k].append(v)
    return {k: np.array(v, dtype=float) for k, v in cols.items()}


def main():
    base = Path(__file__).resolve().parent.parent
    aligned_csv = base / "runs/pressure_audit_ma6_a5_h30km/aligned_pressure_points.csv"
    out_dir = base / "runs/pressure_audit_ma6_a5_h30km/rex_transition_audit"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading aligned CSV: {aligned_csv}")
    d = _read_csv(aligned_csv)

    w = d["side"] == 1
    x = d["x_m"][w]; s = d["span_m"][w]
    qf = d["q_fluent_W_m2"][w]; q3 = d["q_f3_W_m2"][w]
    pf = d["p_fluent_Pa"][w]; p3 = d["p_f3_Pa"][w]
    q_lam = d["q_lam"][w]; q_turb = d["q_turb"][w]
    w_tr = d["w_tr"][w]

    # re_edge might not be in aligned CSV — check
    re_edge = d.get("re_edge", d.get("re_edge", np.full_like(x, np.nan)))[w]
    
    q_ratio = q3 / np.maximum(qf, 1.0)
    p_ratio = p3 / np.maximum(pf, 1.0)

    print(f"Windward points: {int(np.sum(w))}")
    print(f"  q_lam range: [{float(np.nanmin(q_lam)):.1f}, {float(np.nanmax(q_lam)):.1f}]")
    print(f"  q_turb range: [{float(np.nanmin(q_turb)):.1f}, {float(np.nanmax(q_turb)):.1f}]")
    print(f"  w_tr mean: {float(np.nanmean(w_tr)):.3f}, range: [{float(np.nanmin(w_tr)):.1f}, {float(np.nanmax(w_tr)):.1f}]")
    print(f"  re_edge mean: {float(np.nanmean(re_edge)):.0f}")

    # ---- 1. X-binned Re_x / transition stats ----
    nbins = 15
    x_min, x_max = float(np.nanmin(x)), float(np.nanmax(x))
    bins = np.linspace(x_min, x_max, nbins + 1)
    bin_idx = np.digitize(x, bins)
    bin_stats = []
    for bi in range(1, nbins + 1):
        m = bin_idx == bi
        if np.sum(m) < 3: continue
        bin_stats.append({
            "x_mid": 0.5 * (bins[bi-1] + bins[bi]),
            "count": int(np.sum(m)),
            "re_edge_mean": float(np.nanmean(re_edge[m])),
            "w_tr_mean": float(np.nanmean(w_tr[m])),
            "q_lam_mean": float(np.nanmean(q_lam[m])),
            "q_turb_mean": float(np.nanmean(q_turb[m])),
            "q_low_mean": float(np.nanmean(q3[m])),
            "q_fluent_mean": float(np.nanmean(qf[m])),
            "q_ratio_mean": float(np.nanmean(q_ratio[m])),
            "p_ratio_mean": float(np.nanmean(p_ratio[m])),
        })

    print(f"\n--- X-binned Re_x / transition ---")
    print(f"{'x_mid':>6s} | {'count':>5s} | {'re_edge':>8s} | {'w_tr':>5s} | {'q_lam':>9s} | {'q_turb':>9s} | {'q_low':>9s} | {'q_flt':>9s} | {'q_ratio':>8s}")
    for b in bin_stats:
        print(f"{b['x_mid']:6.3f} | {b['count']:5d} | {b['re_edge_mean']:8.0f} | {b['w_tr_mean']:5.2f} | {b['q_lam_mean']:9.0f} | {b['q_turb_mean']:9.0f} | {b['q_low_mean']:9.0f} | {b['q_fluent_mean']:9.0f} | {b['q_ratio_mean']:8.2f}")

    bin_csv = out_dir / "x_binned_re_q_transition.csv"
    with open(bin_csv, "w", newline="", encoding="utf-8") as f:
        wc = csv.writer(f)
        wc.writerow(["x_mid","count","re_edge_mean","w_tr_mean","q_lam_mean","q_turb_mean",
                      "q_low_mean","q_fluent_mean","q_ratio_mean","p_ratio_mean"])
        for b in bin_stats:
            wc.writerow([b[k] for k in ["x_mid","count","re_edge_mean","w_tr_mean","q_lam_mean",
                                         "q_turb_mean","q_low_mean","q_fluent_mean","q_ratio_mean","p_ratio_mean"]])
    print(f"\n  written: {bin_csv}")

    # ---- 2. Maps ----
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    # q_lam
    sc = axes[0,0].scatter(x, s, c=q_lam, s=3, cmap="plasma")
    axes[0,0].set_title("q_lam (W/m²)"); axes[0,0].set_xlabel("x"); axes[0,0].set_ylabel("span")
    fig.colorbar(sc, ax=axes[0,0])
    # q_turb
    sc = axes[0,1].scatter(x, s, c=q_turb, s=3, cmap="plasma")
    axes[0,1].set_title("q_turb (W/m²)"); axes[0,1].set_xlabel("x"); axes[0,1].set_ylabel("span")
    fig.colorbar(sc, ax=axes[0,1])
    # w_tr
    sc = axes[1,0].scatter(x, s, c=w_tr, s=3, cmap="RdYlBu", vmin=0, vmax=1)
    axes[1,0].set_title("w_tr (0=lam, 1=turb)"); axes[1,0].set_xlabel("x"); axes[1,0].set_ylabel("span")
    fig.colorbar(sc, ax=axes[1,0])
    # q_low overall
    sc = axes[1,1].scatter(x, s, c=q3, s=3, cmap="plasma")
    axes[1,1].set_title("q_low (W/m²)"); axes[1,1].set_xlabel("x"); axes[1,1].set_ylabel("span")
    fig.colorbar(sc, ax=axes[1,1])
    fig.tight_layout()
    fig.savefig(out_dir / "q_lam_q_turb_wtr_maps.png", dpi=150)
    plt.close(fig)
    print("  saved: q_lam_q_turb_wtr_maps.png")

    # ---- 3. Centerline profiles ----
    cl = s < 0.05
    if np.any(cl):
        cl_x = x[cl]; order = np.argsort(cl_x)
        fig, axes = plt.subplots(2, 1, figsize=(8, 7))
        ax = axes[0]
        ax.plot(cl_x[order], qf[cl][order], "k-", lw=2, label="Fluent q")
        ax.plot(cl_x[order], q3[cl][order], "r--", lw=1.5, label="q_low")
        ax.plot(cl_x[order], q_lam[cl][order], "g:", lw=1, label="q_lam")
        ax.plot(cl_x[order], q_turb[cl][order], "b:", lw=1, label="q_turb")
        ax.set_ylabel("Heat flux (W/m²)"); ax.set_title("Centerline heat flux (span<0.05)")
        ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

        ax = axes[1]
        ax.plot(cl_x[order], w_tr[cl][order], "r-", lw=1.5, label="w_tr")
        ax2 = ax.twinx()
        ax2.plot(cl_x[order], re_edge[cl][order], "b--", lw=1, label="re_edge")
        ax.set_xlabel("x (m)"); ax.set_ylabel("w_tr (0=lam, 1=turb)")
        ax2.set_ylabel("Re_edge"); ax.grid(True, alpha=0.3)
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1+lines2, labels1+labels2, fontsize=8, loc="upper left")
        fig.tight_layout()
        fig.savefig(out_dir / "centerline_q_lam_q_turb_wtr.png", dpi=150)
        plt.close(fig)
        print("  saved: centerline_q_lam_q_turb_wtr.png")

    # ---- 4. Scatter: Re_edge vs q_ratio ----
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    valid_re = np.isfinite(re_edge) & np.isfinite(q_ratio)
    axes[0].scatter(re_edge[valid_re], q_ratio[valid_re], s=2, alpha=0.3, c=x[valid_re], cmap="viridis")
    axes[0].set_xlabel("Re_edge"); axes[0].set_ylabel("q_ratio (F3/Fluent)")
    axes[0].set_title("Re_edge vs q_ratio (color=x)"); axes[0].grid(True, alpha=0.3)
    
    valid_w = np.isfinite(w_tr) & np.isfinite(q_ratio)
    axes[1].scatter(w_tr[valid_w], q_ratio[valid_w], s=2, alpha=0.3, c=x[valid_w], cmap="viridis")
    axes[1].set_xlabel("w_tr"); axes[1].set_ylabel("q_ratio (F3/Fluent)")
    axes[1].set_title("w_tr vs q_ratio (color=x)"); axes[1].grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "re_edge_vs_q_ratio_scatter.png", dpi=150)
    plt.close(fig)
    print("  saved: re_edge_vs_q_ratio_scatter.png")

    # ---- 5. w_tr vs q_ratio (separate) ----
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(w_tr[valid_w], q_ratio[valid_w], s=3, alpha=0.4, c=s[valid_w], cmap="plasma")
    ax.set_xlabel("w_tr"); ax.set_ylabel("q_ratio (F3/Fluent)")
    ax.set_title("w_tr vs q_ratio (color=span)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "w_tr_vs_q_ratio_scatter.png", dpi=150)
    plt.close(fig)
    print("  saved: w_tr_vs_q_ratio_scatter.png")

    # ---- 6. Forced laminar / forced turbulent offline comparison ----
    q_lam_only = q_lam.copy()
    q_turb_only = q_turb.copy()
    
    # Compare q_lam vs q_f, q_turb vs q_f
    cl_m = s < 0.05
    if np.any(cl_m):
        cl_x = x[cl_m]; order = np.argsort(cl_x)
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(cl_x[order], qf[cl_m][order], "k-", lw=2, label="Fluent q")
        ax.plot(cl_x[order], q_lam[cl_m][order], "g--", lw=1.2, label="Forced laminar (q_lam)")
        ax.plot(cl_x[order], q_turb[cl_m][order], "b--", lw=1.2, label="Forced turbulent (q_turb)")
        ax.plot(cl_x[order], q3[cl_m][order], "r:", lw=1.2, label="Faceted3D q_low (blended)")
        ax.set_xlabel("x (m)"); ax.set_ylabel("Heat flux (W/m²)")
        ax.set_title("Centerline — forced laminar/turbulent vs Fluent")
        ax.legend(fontsize=8); ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(out_dir / "centerline_forced_lam_turb.png", dpi=150)
        plt.close(fig)
        print("  saved: centerline_forced_lam_turb.png")

    # ---- 7. MD report ----
    report_path = out_dir / "rex_transition_audit.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Re_x / Transition Diagnosis\n\n")
        f.write(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> Mach=6.0, Alpha=5°, h=30km, Tw=300K\n\n")

        f.write("## X-binned Re_x / transition / heat flux\n\n")
        f.write(f"| x_mid | count | Re_edge | w_tr | q_lam | q_turb | q_low | q_fluent | q_ratio | p_ratio |\n")
        f.write(f"|-------|-------|---------|------|-------|--------|-------|----------|---------|--------|\n")
        for b in bin_stats:
            f.write(f"| {b['x_mid']:6.3f} | {b['count']:5d} | {b['re_edge_mean']:8.0f} | {b['w_tr_mean']:5.2f} | {b['q_lam_mean']:8.0f} | {b['q_turb_mean']:8.0f} | {b['q_low_mean']:8.0f} | {b['q_fluent_mean']:8.0f} | {b['q_ratio_mean']:7.2f} | {b['p_ratio_mean']:7.2f} |\n")

        # Determine regime: is Fluent more lam, turb, or transitional?
        front_bins = bin_stats[:max(1, len(bin_stats)//3)]
        mid_bins = bin_stats[max(1, len(bin_stats)//3): 2*len(bin_stats)//3]
        rear_bins = bin_stats[2*len(bin_stats)//3:]
        
        front_qf = np.mean([b["q_fluent_mean"] for b in front_bins]) if front_bins else 0
        mid_qf = np.mean([b["q_fluent_mean"] for b in mid_bins]) if mid_bins else 0
        rear_qf = np.mean([b["q_fluent_mean"] for b in rear_bins]) if rear_bins else 0
        
        front_qlam = np.mean([b["q_lam_mean"] for b in front_bins]) if front_bins else 0
        front_qturb = np.mean([b["q_turb_mean"] for b in front_bins]) if front_bins else 0
        rear_qlam = np.mean([b["q_lam_mean"] for b in rear_bins]) if rear_bins else 0
        rear_qturb = np.mean([b["q_turb_mean"] for b in rear_bins]) if rear_bins else 0
        
        f.write("\n## Fluent regime classification\n\n")
        f.write(f"Front 1/3: q_fluent mean={front_qf:.0f}, q_lam mean={front_qlam:.0f}, q_turb mean={front_qturb:.0f}\n")
        f.write(f"Rear 1/3:  q_fluent mean={rear_qf:.0f}, q_lam mean={rear_qlam:.0f}, q_turb mean={rear_qturb:.0f}\n")
        
        # Compare with forced lam/turb
        if front_qlam > 0 and rear_qf > 0:
            lam_ratio = front_qlam / max(front_qf, 1)
            turb_ratio = rear_qturb / max(rear_qf, 1)
            f.write(f"\nFront: q_lam/q_fluent = {lam_ratio:.2f}\n")
            f.write(f"Rear:  q_turb/q_fluent = {turb_ratio:.2f}\n")
            
            if 0.7 < lam_ratio < 1.3 and front_qf > 0.5 * front_qturb:
                f.write("**Fluent appears closer to laminar in front section.**\n")
            elif 0.7 < turb_ratio < 1.3:
                f.write("**Fluent appears closer to turbulent in rear section.**\n")
            else:
                f.write("**Fluent does not match either forced lam or forced turb — transitional.**\n")

        # w_tr analysis
        f.write(f"\n## w_tr (transition weight) analysis\n\n")
        f.write(f"Overall w_tr mean: {float(np.nanmean(w_tr)):.3f}\n")
        f.write(f"Fraction w_tr=0 (fully laminar): {float(np.sum(w_tr < 0.01))/max(float(w_tr.size),1)*100:.1f}%\n")
        f.write(f"Fraction w_tr=1 (fully turbulent): {float(np.sum(w_tr > 0.99))/max(float(w_tr.size),1)*100:.1f}%\n")
        f.write(f"Fraction transitional (0.01<w_tr<0.99): {float(np.sum((w_tr>=0.01)&(w_tr<=0.99)))/max(float(w_tr.size),1)*100:.1f}%\n")
        
        front_wtr = np.mean([b["w_tr_mean"] for b in front_bins]) if front_bins else 0
        rear_wtr = np.mean([b["w_tr_mean"] for b in rear_bins]) if rear_bins else 0
        f.write(f"Front 1/3 w_tr mean: {front_wtr:.3f}\n")
        f.write(f"Rear 1/3 w_tr mean: {rear_wtr:.3f}\n")

        f.write("\n## q_ratio vs p_ratio correlation check\n\n")
        # Have we separated p and q effects?
        valid_pq = np.isfinite(p_ratio) & np.isfinite(q_ratio)
        if np.sum(valid_pq) > 10:
            from scipy.stats import pearsonr
            corr, _ = pearsonr(p_ratio[valid_pq], q_ratio[valid_pq])
            f.write(f"corr(p_ratio, q_ratio) = {corr:.4f}\n")
            
            # After controlling for pressure: look at residual
            # Simple linear model: q_ratio ~ a * p_ratio + b
            from numpy.polynomial import polynomial
            coeff = polynomial.polyfit(p_ratio[valid_pq], q_ratio[valid_pq], 1)
            q_pred_from_p = polynomial.polyval(p_ratio[valid_pq], coeff)
            q_resid_after_p = q_ratio[valid_pq] - q_pred_from_p
            f.write(f"After removing linear p_ratio effect, q_residual std={float(np.nanstd(q_resid_after_p)):.3f}\n")
            if corr > 0.3:
                f.write("p_ratio explains a meaningful fraction of q_ratio variance.\n")
            else:
                f.write("p_ratio explains little q_ratio variance — Re_x/transition is likely dominant.\n")

        # Final answers
        f.write("\n## Answers\n\n")
        f.write("### Q1: At 30km Ma=6, does Fluent look laminar, turbulent, or transitional?\n")
        # Check if Fluent q aligns more with q_lam or q_turb
        if front_qlam < front_qturb * 0.5:
            f.write("Fluent q is much lower than q_turb — more consistent with laminar.\n")
        elif front_qlam > front_qturb * 1.5:
            f.write("Fluent q is between lam and turb — transitional.\n")
        else:
            f.write("Fluent q is comparable to q_turb — more consistent with turbulent.\n")
        
        f.write("\n### Q2: Is Faceted3D w_tr compatible with Fluent heat flux?\n")
        if front_wtr < 0.3 and front_qlam > front_qf * 0.7:
            f.write("Faceted3D w_tr indicates laminar and Fluent matches laminar — compatible.\n")
        elif front_wtr > 0.7 and front_qlam < front_qf * 0.7:
            f.write("Faceted3D w_tr indicates turbulent but Fluent is lower — incompatible, w_tr too high.\n")
        else:
            f.write("Partially compatible — needs further investigation.\n")
        
        f.write("\n### Q3: If pressure correction still leaves q wrong, should we fix Re_x/transition next?\n")
        if corr > -0.3 and corr < 0.3:
            f.write("**YES.** p_ratio does not explain q_ratio. Re_x / transition is the next priority.\n")
        else:
            f.write("**YES but secondary.** p_ratio explains some q_ratio, but significant residual remains.\n")
        
        f.write("\n---\n")
        f.write("\n*Report auto-generated by `scripts/p0_3_rex_transition_audit.py`*\n")

    print(f"\n  written: {report_path}")
    print(f"\nTask C DONE — outputs in {out_dir}")


if __name__ == "__main__":
    main()
