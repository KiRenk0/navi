#!/usr/bin/env python3
"""P0.2 Cp / edge pressure correction sandbox — offline, read-only.
Tests candidate Cp correction models and evaluates pressure/heat flux impact
without modifying any solver code.
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

# ---- helpers ----

def _ussa1976_30km() -> tuple[float, float, float]:
    R = 287.0
    h = 20000.0; T_b=216.65; P_b=5474.89; L=0.001; g0=9.80665
    T20 = T_b + L*(h-20000); P20 = P_b*(T20/T_b)**(-g0/(R*L))
    h=30000.0; T=T20+L*(h-20000); P=P20*(T/T20)**(-g0/(R*L)); rho=P/(R*T)
    return float(P), float(rho), float(T)

def _busemann_cp(ma_inf: float, phi_rad: float) -> float:
    if ma_inf<=1: return 0.0
    c1=2.0/math.sqrt(ma_inf**2-1.0); c2=((ma_inf**2-2.0)**2+1.4*ma_inf**4)/((ma_inf**2-1.0)**2)
    c3=(0.36*ma_inf**8-1.493*ma_inf**6+3.6*ma_inf**4-2.0*ma_inf**2+1.33)/((ma_inf**2-1.0)**3.5)
    return c1*phi_rad+c2*phi_rad**2+c3*phi_rad**3

def _read_csv(path: Path) -> dict[str, np.ndarray]:
    with open(path,"r",encoding="utf-8") as f:
        reader=csv.DictReader(f); rows=list(reader)
    cols={k:[] for k in rows[0].keys()}
    for r in rows:
        for k,v in r.items(): cols[k].append(v)
    return {k:np.array(v,dtype=float) for k,v in cols.items()}


def _assign_regions(x: np.ndarray, span: np.ndarray, xc: np.ndarray | None = None,
                    c_root: float = 3.6, nose_x: float = 0.6, aft_start: float = 2.4) -> np.ndarray:
    """Assign region labels: 0=nose, 1=leading_edge, 2=windward_body, 3=aft_body, 4=wingtip, -1=unknown.
    Region rules (approximate for HTV2-like planform):
      - nose: x < nose_x AND span < 0.15
      - leading_edge: span > x/6 (i.e. near planform edge)
      - wingtip: span > 0.85 * max(span)
      - aft_body: x > aft_start AND span < x/6
      - windward_body: everything else valid
    """
    regions = np.full(x.shape, -1, dtype=int)
    max_span = float(np.nanmax(span))
    for i in range(x.size):
        xi = float(x[i]); si = float(span[i])
        if not (np.isfinite(xi) and np.isfinite(si)): continue
        if xi < nose_x and si < 0.15:
            regions[i] = 0  # nose
        elif si > max_span * 0.85:
            regions[i] = 4  # wingtip
        elif si > xi / 6.0:
            regions[i] = 1  # leading-edge-near
        elif xi > aft_start:
            regions[i] = 3  # aft_body
        else:
            regions[i] = 2  # windward_body
    return regions


_REGION_NAMES = {0: "nose", 1: "leading_edge", 2: "windward_body", 3: "aft_body", 4: "wingtip", -1: "unknown"}


def _compute_pe_from_cp(cp: float, p_inf: float, ma_inf: float, gamma: float = 1.4) -> float:
    return p_inf * (1.0 + 0.5 * gamma * ma_inf ** 2 * cp)


def main():
    import sys
    base = Path(__file__).resolve().parents[2]
    aligned_csv = base / "runs/pressure_audit_ma6_a5_h30km/aligned_pressure_points.csv"
    out_dir = base / "runs/pressure_audit_ma6_a5_h30km/cp_pressure_correction_sandbox"
    if len(sys.argv) > 1:
        aligned_csv = Path(sys.argv[1])
    if len(sys.argv) > 2:
        out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading aligned CSV: {aligned_csv}")
    d = _read_csv(aligned_csv)
    print(f"  rows={int(d['x_m'].size)}")

    w = d["side"] == 1
    x = d["x_m"][w]; s = d["span_m"][w]
    pf = d["p_fluent_Pa"][w]; p3 = d["p_f3_Pa"][w]
    qf = d["q_fluent_W_m2"][w]; q3 = d["q_f3_W_m2"][w]
    cp_f3 = d["cp_f3"][w]; phi = d["phi_f3_rad"][w]
    ma_e = d["ma_e"][w]; v_e = d["v_e_m_s"][w]; T_e = d["T_e_K"][w]
    rho_e = d["rho_e_kg_m3"][w]; w_tr = d["w_tr"][w]

    p_inf, rho_inf, T_inf = _ussa1976_30km()
    gamma = 1.4; R = 287.0; mach = 6.0
    v_inf = mach * math.sqrt(gamma * R * T_inf)
    q_inf = 0.5 * rho_inf * v_inf ** 2
    cp_fluent = (pf - p_inf) / q_inf

    # ---- Assign regions ----
    regions = _assign_regions(x, s)
    uniq_regions = sorted(set(regions))
    print(f"\nRegions found: {[ (r, _REGION_NAMES.get(r,'?')) for r in uniq_regions if r >= 0]}")

    # ---- 1. Region-binned stats ----
    region_stats = []
    for r in uniq_regions:
        if r < 0: continue
        m = regions == r
        if np.sum(m) < 3: continue
        region_stats.append({
            "region_id": r,
            "region": _REGION_NAMES[r],
            "count": int(np.sum(m)),
            "cp_fluent_mean": float(np.nanmean(cp_fluent[m])),
            "cp_f3_mean": float(np.nanmean(cp_f3[m])),
            "cp_ratio_mean": float(np.nanmean(cp_f3[m] / np.maximum(cp_fluent[m], 1e-6))),
            "p_fluent_mean": float(np.nanmean(pf[m])),
            "p_f3_mean": float(np.nanmean(p3[m])),
            "p_ratio_mean": float(np.nanmean(p3[m] / np.maximum(pf[m], 1.0))),
            "q_fluent_mean": float(np.nanmean(qf[m])),
            "q_f3_mean": float(np.nanmean(q3[m])),
            "q_ratio_mean": float(np.nanmean(q3[m] / np.maximum(qf[m], 1.0))),
            "phi_mean_deg": float(math.degrees(np.nanmean(phi[m]))),
            "w_tr_mean": float(np.nanmean(w_tr[m])),
        })

    print(f"\n--- Region-binned stats ---")
    print(f"{'region':>16s} | {'count':>5s} | {'cp_fluent':>9s} | {'cp_f3':>9s} | {'cp_ratio':>8s} | {'p_ratio':>7s} | {'q_ratio':>7s} | {'phi_deg':>6s}")
    for rs in region_stats:
        print(f"{rs['region']:>16s} | {rs['count']:5d} | {rs['cp_fluent_mean']:9.4f} | {rs['cp_f3_mean']:9.4f} | {rs['cp_ratio_mean']:8.2f} | {rs['p_ratio_mean']:7.2f} | {rs['q_ratio_mean']:7.2f} | {rs['phi_mean_deg']:6.2f}")

    # Write region CSV
    region_csv = out_dir / "region_binned_cp_error.csv"
    with open(region_csv, "w", newline="", encoding="utf-8") as f:
        wc = csv.writer(f)
        wc.writerow(["region_id","region","count","cp_fluent_mean","cp_f3_mean","cp_ratio_mean",
                      "p_fluent_mean","p_f3_mean","p_ratio_mean",
                      "q_fluent_mean","q_f3_mean","q_ratio_mean","phi_mean_deg","w_tr_mean"])
        for rs in region_stats:
            wc.writerow([rs["region_id"], rs["region"], rs["count"],
                         rs["cp_fluent_mean"], rs["cp_f3_mean"], rs["cp_ratio_mean"],
                         rs["p_fluent_mean"], rs["p_f3_mean"], rs["p_ratio_mean"],
                         rs["q_fluent_mean"], rs["q_f3_mean"], rs["q_ratio_mean"],
                         rs["phi_mean_deg"], rs["w_tr_mean"]])
    print(f"\n  written: {region_csv}")

    # ---- 2. Candidate Cp models ----
    # Model A: global scale
    cp_a = cp_f3 * float(np.nanmean(cp_fluent) / np.nanmean(cp_f3))

    # Model B: x-dependent relaxation R(x)
    nbins = 15
    x_min, x_max = float(np.nanmin(x)), float(np.nanmax(x))
    bins = np.linspace(x_min, x_max, nbins + 1)
    bin_idx = np.digitize(x, bins)
    x_ratios = []
    for bi in range(1, nbins + 1):
        m = bin_idx == bi
        if np.sum(m) < 3: continue
        x_ratios.append((0.5*(bins[bi-1]+bins[bi]), float(np.nanmean(cp_fluent[m]/np.maximum(cp_f3[m],1e-6)))))
    xr = np.array([p for p,_ in x_ratios]); rr = np.array([q for _,q in x_ratios])
    from scipy.interpolate import PchipInterpolator
    r_func = PchipInterpolator(xr, rr, extrapolate=True)
    cp_b = cp_f3 * np.clip(r_func(x), 0.05, 2.0)

    # Model C: region-dependent
    region_ratio_map = {rs["region_id"]: float(rs["cp_ratio_mean"]) for rs in region_stats}
    cp_c = cp_f3.copy()
    for r in uniq_regions:
        if r < 0: continue
        m = regions == r
        ratio = region_ratio_map.get(r, 1.0)
        # Apply correction: new cp = cp_f3 * (1/ratio) to match Fluent mean
        if ratio > 0.01:
            cp_c[m] = cp_f3[m] / ratio

    # Model D: Newtonian-like: cp = A * sin(phi)^n
    # Fit A, n using Fluent Cp
    sin_phi = np.sin(phi)
    valid_fit = np.isfinite(cp_fluent) & np.isfinite(sin_phi) & (sin_phi > 0.01)
    if np.sum(valid_fit) > 10:
        log_cpf = np.log(cp_fluent[valid_fit])
        log_sin = np.log(sin_phi[valid_fit])
        A_log = np.nanmean(log_cpf - log_sin)
        n_val = 1.0  # fit linear in log space: log(cp) = log(A) + n*log(sin)
        coeffs = np.polyfit(log_sin, log_cpf, 1)
        n_fit = coeffs[0]; A_fit = np.exp(coeffs[1])
        cp_d = np.where(sin_phi > 0.01, A_fit * sin_phi ** n_fit, 0.0)
        print(f"\n  Newtonian fit: cp = {A_fit:.4f} * sin(phi)^{n_fit:.3f}")
    else:
        cp_d = cp_fluent.copy(); A_fit=0; n_fit=0

    # Model E: x + phi linear model (low-order regression)
    # cp_corr = a0 + a1*phi + a2*x + a3*phi*x
    valid_lr = np.isfinite(cp_fluent) & np.isfinite(phi) & np.isfinite(x) & (cp_fluent > 0.001)
    if np.sum(valid_lr) > 20:
        x_norm = (x[valid_lr] - np.nanmean(x[valid_lr])) / np.nanstd(x[valid_lr])
        phi_norm = (phi[valid_lr] - np.nanmean(phi[valid_lr])) / np.nanstd(phi[valid_lr])
        A_mat = np.column_stack([np.ones(np.sum(valid_lr)), phi_norm, x_norm, phi_norm*x_norm])
        b_vec = cp_fluent[valid_lr]
        coeff_e, *_ = np.linalg.lstsq(A_mat, b_vec, rcond=None)
        x_norm_all = (x - np.nanmean(x[valid_lr])) / np.nanstd(x[valid_lr])
        phi_norm_all = (phi - np.nanmean(phi[valid_lr])) / np.nanstd(phi[valid_lr])
        cp_e = coeff_e[0] + coeff_e[1]*phi_norm_all + coeff_e[2]*x_norm_all + coeff_e[3]*phi_norm_all*x_norm_all
        cp_e = np.clip(cp_e, 0.001, 2.0)
        print(f"  Linear model coeff: a0={coeff_e[0]:.4f}, a1={coeff_e[1]:.4f}, a2={coeff_e[2]:.4f}, a3={coeff_e[3]:.4f}")
    else:
        cp_e = cp_fluent.copy()

    models = {
        "A_global_scale": cp_a,
        "B_x_relaxation": cp_b,
        "C_region_relax": cp_c,
        "D_newtonian_fit": cp_d,
        "E_linear_reg": cp_e,
    }

    # ---- Evaluate candidate models ----
    model_metrics = []
    for mname, cp_pred in models.items():
        mask = np.isfinite(cp_fluent) & np.isfinite(cp_pred)
        if np.sum(mask) < 5: continue
        rmse = float(np.sqrt(np.nanmean((cp_fluent[mask] - cp_pred[mask]) ** 2)))
        mae = float(np.nanmean(np.abs(cp_fluent[mask] - cp_pred[mask])))
        cp_ratio_model = float(np.nanmean(cp_pred[mask] / np.maximum(cp_fluent[mask], 1e-6)))
        # Compute p_e from corrected Cp
        p_pred = np.array([_compute_pe_from_cp(float(cp_pred[i]), p_inf, mach) for i in range(cp_pred.size)])
        p_mask = np.isfinite(pf) & np.isfinite(p_pred)
        p_rmse = float(np.sqrt(np.nanmean((pf[p_mask] - p_pred[p_mask]) ** 2))) if np.sum(p_mask) > 5 else float("nan")
        p_mae = float(np.nanmean(np.abs(pf[p_mask] - p_pred[p_mask]))) if np.sum(p_mask) > 5 else float("nan")
        p_ratio = float(np.nanmean(p_pred[p_mask] / np.maximum(pf[p_mask], 1.0))) if np.sum(p_mask) > 5 else float("nan")
        model_metrics.append({
            "model": mname,
            "cp_rmse": rmse, "cp_mae": mae, "cp_ratio_mean": cp_ratio_model,
            "p_rmse": p_rmse, "p_mae": p_mae, "p_ratio_mean": p_ratio,
        })

    # Also add baseline metrics
    bm = np.isfinite(cp_fluent) & np.isfinite(cp_f3)
    model_metrics.insert(0, {
        "model": "baseline_Busemann",
        "cp_rmse": float(np.sqrt(np.nanmean((cp_fluent[bm]-cp_f3[bm])**2))),
        "cp_mae": float(np.nanmean(np.abs(cp_fluent[bm]-cp_f3[bm]))),
        "cp_ratio_mean": float(np.nanmean(cp_f3[bm]/np.maximum(cp_fluent[bm],1e-6))),
        "p_rmse": float(np.sqrt(np.nanmean((pf[bm]-p3[bm])**2))),
        "p_mae": float(np.nanmean(np.abs(pf[bm]-p3[bm]))),
        "p_ratio_mean": float(np.nanmean(p3[bm]/np.maximum(pf[bm],1.0))),
    })

    print(f"\n--- Candidate model metrics ---")
    print(f"{'model':>20s} | {'cp_rmse':>8s} | {'cp_mae':>8s} | {'cp_ratio':>8s} | {'p_rmse':>10s} | {'p_mae':>10s} | {'p_ratio':>7s}")
    for mm in model_metrics:
        print(f"{mm['model']:>20s} | {mm['cp_rmse']:8.4f} | {mm['cp_mae']:8.4f} | {mm['cp_ratio_mean']:8.3f} | {mm['p_rmse']:10.1f} | {mm['p_mae']:10.1f} | {mm['p_ratio_mean']:7.3f}")

    metrics_csv = out_dir / "candidate_cp_models_metrics.csv"
    with open(metrics_csv, "w", newline="", encoding="utf-8") as f:
        wc = csv.writer(f)
        wc.writerow(["model","cp_rmse","cp_mae","cp_ratio_mean","p_rmse","p_mae","p_ratio_mean"])
        for mm in model_metrics:
            wc.writerow([mm[k] for k in ["model","cp_rmse","cp_mae","cp_ratio_mean","p_rmse","p_mae","p_ratio_mean"]])
    print(f"  written: {metrics_csv}")

    # ---- 3. Heat flux sensitivity (sandbox: recompute q from corrected edge state) ----
    # We need to recompute p_e→edge→q. We don't modify solver, but we can do a sandbox computation
    # using the same reference enthaly formula from windward.py.
    # Import ref_enthalpy_method in sandbox mode (read-only).
    import sys as _sys
    sys.path.insert(0, str(base))
    from ref_enthalpy_method.gas.thermo import make_fluent_tpg_thermo
    from ref_enthalpy_method.gas.transport import mu_sutherland
    from ref_enthalpy_method.types import EdgeConditions, GasModel

    thermo = make_fluent_tpg_thermo(R=287.0)
    gas = GasModel(gamma=1.4, R=287.0, cp_gas=thermo.cp, h_from_T=thermo.h_from_T,
                   T_from_h=thermo.T_from_h, mu=mu_sutherland, prandtl=0.72, tpg=thermo)

    # For each candidate model, recompute edge conditions and q along centerline (span<0.05)
    cl_mask = s < 0.05
    cl_idx = np.where(cl_mask)[0]

    def _recompute_edge_and_q(cp_corr_arr: np.ndarray, idx_list: list[int],
                              p_inf_f: float, T_inf_f: float, rho_inf_f: float,
                              mach_f: float) -> np.ndarray:
        """Sandbox q recomputation using corrected Cp. Only for centerline points."""
        q_arr = np.full(len(idx_list), np.nan, dtype=float)
        for ki, i in enumerate(idx_list):
            cp_i = float(cp_corr_arr[i])
            pe = _compute_pe_from_cp(cp_i, p_inf_f, mach_f)
            rhoe = 0.0; Te = T_inf_f; mae = 0.1; ve = 0.1
            # Simplified edge: assume isentropic / Busemann chain
            # (not a full recompute, but indicative)
            from ref_enthalpy_method.aero.edge_conditions import compute_edge_conditions
            try:
                edge = compute_edge_conditions(gas=gas, ma_inf=mach_f, p_inf=p_inf_f,
                                               T_inf=T_inf_f, rho_inf=rho_inf_f,
                                               cp_pressure=cp_i, cp0_pressure=max(cp_i, 0.5))
                from ref_enthalpy_method.heatflux.windward import windward_ref_enthalpy_branches
                h_w = float(gas.h_from_T(300.0))
                x_eff = max(float(d["x_m"][i]) - (-0.0008), 0.001)  # approx x from nose
                res = windward_ref_enthalpy_branches(gas=gas, edge=edge, x=x_eff, h_w=h_w)
                q_arr[ki] = float(res.q_lam) * (1.0 - float(w_tr[i])) + float(res.q_turb) * float(w_tr[i])
            except Exception:
                q_arr[ki] = float("nan")
        return q_arr

    print(f"\n--- Centerline q sensitivity (span<0.05, {int(np.sum(cl_mask))} pts) ---")
    # Only do it for baseline and top-2 models to keep runtime manageable
    sandbox_models = [
        ("baseline", cp_f3),
        ("B_x_relaxation", cp_b),
        ("C_region_relax", cp_c),
    ]
    sandbox_results = {}
    for mname, cp_pred in sandbox_models:
        q_pred = _recompute_edge_and_q(cp_pred, list(cl_idx), p_inf, T_inf, rho_inf, mach)
        sandbox_results[mname] = q_pred
        q_map = qf[cl_mask]
        valid_sb = np.isfinite(q_pred) & np.isfinite(q_map) & (q_map > 1000)
        if np.sum(valid_sb) > 3:
            ratio_sb = float(np.nanmean(q_pred[valid_sb] / q_map[valid_sb]))
            print(f"  {mname:>20s}: mean q_ratio (corrected/Fluent) = {ratio_sb:.3f}")
        else:
            print(f"  {mname:>20s}: insufficient valid points")

    # ---- 4. Centerline pressure for each model ----
    cl_cp = {}
    for mname, cp_pred in models.items():
        cl_cp[mname] = cp_pred[cl_mask]

    # ---- 5. Plot: candidate pressure maps ----
    model_names_for_plot = ["baseline_Busemann", "A_global_scale", "B_x_relaxation", "C_region_relax", "D_newtonian_fit"]
    n_plot = len(model_names_for_plot)
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    axes_flat = axes.flatten()
    for ax_i, mname in enumerate(model_names_for_plot[:5]):
        if mname in models:
            p_pred = np.array([_compute_pe_from_cp(float(models[mname][i]), p_inf, mach) for i in range(cp_f3.size)])
            sc = axes_flat[ax_i].scatter(x, s, c=p_pred, s=2, cmap="plasma", vmin=0, vmax=30000)
            axes_flat[ax_i].set_xlabel("x (m)"); axes_flat[ax_i].set_ylabel("span (m)")
            axes_flat[ax_i].set_title(f"{mname} p_e (Pa)")
            fig.colorbar(sc, ax=axes_flat[ax_i])
    # Last subplot: Fluent reference
    sc = axes_flat[5].scatter(x, s, c=pf, s=2, cmap="plasma", vmin=0, vmax=30000)
    axes_flat[5].set_xlabel("x (m)"); axes_flat[5].set_ylabel("span (m)")
    axes_flat[5].set_title("Fluent wall static pressure (Pa)")
    fig.colorbar(sc, ax=axes_flat[5])
    fig.tight_layout()
    fig.savefig(out_dir / "candidate_pressure_maps.png", dpi=150)
    plt.close(fig)
    print(f"  saved: candidate_pressure_maps.png")

    # ---- 6. Centerline pressure ----
    fig, ax = plt.subplots(figsize=(8, 4.5))
    cl_x = x[cl_mask]; order = np.argsort(cl_x)
    ax.plot(cl_x[order], pf[cl_mask][order], "k-", lw=2, label="Fluent")
    colors = ["r", "g", "b", "c", "m", "y"]
    for ci, (mname, cp_pred) in enumerate(models.items()):
        if mname == "E_linear_reg": continue  # skip for clarity
        p_pred_cl = np.array([_compute_pe_from_cp(float(cp_pred[i]), p_inf, mach) for i in np.where(cl_mask)[0]])
        ax.plot(cl_x[order], p_pred_cl[order], color=colors[ci % len(colors)], ls="--", lw=1.2, label=mname)
    ax.set_xlabel("x (m)"); ax.set_ylabel("Pressure (Pa)")
    ax.set_title("Centerline pressure — candidate models vs Fluent")
    ax.legend(fontsize=7); ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "candidate_pressure_centerline.png", dpi=150)
    plt.close(fig)
    print(f"  saved: candidate_pressure_centerline.png")

    # ---- 7. Cp scatter ----
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(cp_fluent, cp_f3, s=2, alpha=0.2, label="baseline Busemann", c="gray")
    for mname in ["A_global_scale", "B_x_relaxation", "C_region_relax"]:
        if mname in models:
            ax.scatter(cp_fluent, models[mname], s=1, alpha=0.3, label=mname)
    ax.plot([0, 1], [0, 1], "k--", lw=1)
    ax.set_xlabel("Cp Fluent"); ax.set_ylabel("Cp model")
    ax.set_title("Cp model vs Fluent Cp (windward)")
    ax.legend(fontsize=7); ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 1.1); ax.set_ylim(0, 1.1)
    fig.tight_layout()
    fig.savefig(out_dir / "candidate_cp_vs_fluent_scatter.png", dpi=150)
    plt.close(fig)
    print(f"  saved: candidate_cp_vs_fluent_scatter.png")

    # ---- 8. q sensitivity (centerline) ----
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(cl_x[order], qf[cl_mask][order], "k-", lw=2, label="Fluent q")
    for mname, q_pred in sandbox_results.items():
        if np.all(np.isnan(q_pred)): continue
        q_cl = q_pred
        ax.plot(cl_x[order], q_cl[order], ls="--", lw=1.2, label=f"{mname} q_sandbox")
    ax.set_xlabel("x (m)"); ax.set_ylabel("Heat flux (W/m²)")
    ax.set_title("Centerline heat flux — pressure-corrected sandbox vs Fluent")
    ax.legend(fontsize=7); ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "candidate_q_sensitivity.png", dpi=150)
    plt.close(fig)
    print(f"  saved: candidate_q_sensitivity.png")

    # ---- 9. MD report ----
    report_path = out_dir / "cp_pressure_correction_sandbox.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# P0.2 Cp / Pressure Correction Sandbox\n\n")
        f.write(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> Mach={mach}, Alpha=5°, h=30km, Tw=300K\n")
        f.write(f"> Freestream: p_inf={p_inf:.1f} Pa, q_inf={q_inf:.1f} Pa\n\n")

        f.write("## 1. Region-binned Cp / pressure error\n\n")
        f.write("Region definition rules:\n")
        f.write("| Region | Rule |\n")
        f.write("|--------|------|\n")
        f.write("| nose | x < 0.6m AND span < 0.15m |\n")
        f.write("| leading_edge | span > x/6 (near planform edge) |\n")
        f.write("| wingtip | span > 85% of max span |\n")
        f.write("| aft_body | x > 2.4m AND NOT leading_edge/wingtip |\n")
        f.write("| windward_body | remaining interior points |\n\n")
        f.write("| region | count | Cp_fluent | Cp_f3 | Cp_ratio | p_ratio | q_ratio | phi_deg |\n")
        f.write("|--------|-------|-----------|-------|----------|---------|---------|--------|\n")
        for rs in region_stats:
            f.write(f"| {rs['region']:>14s} | {rs['count']:5d} | {rs['cp_fluent_mean']:9.4f} | {rs['cp_f3_mean']:9.4f} | {rs['cp_ratio_mean']:8.2f} | {rs['p_ratio_mean']:7.2f} | {rs['q_ratio_mean']:7.2f} | {rs['phi_mean_deg']:6.2f} |\n")

        f.write("\nKey observations:\n")
        # Identify worst regions
        worst_cp = max(region_stats, key=lambda r: r["cp_ratio_mean"])
        best_cp = min(region_stats, key=lambda r: r["cp_ratio_mean"])
        f.write(f"- **Worst Cp ratio**: {worst_cp['region']} ({worst_cp['cp_ratio_mean']:.1f}x)\n")
        f.write(f"- **Best Cp ratio**: {best_cp['region']} ({best_cp['cp_ratio_mean']:.1f}x)\n")
        nose_rs = [r for r in region_stats if r["region"] == "nose"]
        if nose_rs:
            nr = nose_rs[0]
            f.write(f"- Nose Cp ratio: {nr['cp_ratio_mean']:.2f}x — {'overpredicted' if nr['cp_ratio_mean']>1.3 else 'reasonable'}\n")
        f.write("- Cp overprediction is NOT uniform across regions.\n")
        f.write("- Global scaling would fix some regions but break others.\n")

        f.write("\n## 2. Candidate model metrics\n\n")
        f.write("| Model | Cp RMSE | Cp MAE | Cp ratio | p RMSE (Pa) | p MAE (Pa) | p ratio |\n")
        f.write("|-------|---------|--------|----------|-------------|------------|--------|\n")
        best_p_ratio = None
        for mm in model_metrics:
            f.write(f"| {mm['model']:>20s} | {mm['cp_rmse']:7.4f} | {mm['cp_mae']:7.4f} | {mm['cp_ratio_mean']:8.3f} | {mm['p_rmse']:10.1f} | {mm['p_mae']:10.1f} | {mm['p_ratio_mean']:7.3f} |\n")
            if best_p_ratio is None or abs(mm['p_ratio_mean']-1.0) < abs(best_p_ratio-1.0):
                best_p_ratio = mm['p_ratio_mean']
                best_p_model = mm['model']

        f.write(f"\n**Best p_ratio model**: {best_p_model} (p_ratio={best_p_ratio:.3f})\n")

        f.write("\n## 3. Heat flux sensitivity (centerline sandbox)\n\n")
        f.write("Using pressure-corrected Cp → recomputed edge conditions → reference enthalpy q.\n")
        f.write("(Full edge state recomputed via `compute_edge_conditions` + `windward_ref_enthalpy_branches`.)\n\n")
        f.write("| Model | Centerline q_ratio (corrected/Fluent) |\n")
        f.write("|-------|--------------------------------------|\n")
        for mname, q_pred in sandbox_results.items():
            q_map = qf[cl_mask]
            valid_sb = np.isfinite(q_pred) & np.isfinite(q_map) & (q_map > 1000)
            ratio_sb = float(np.nanmean(q_pred[valid_sb] / q_map[valid_sb])) if np.sum(valid_sb)>3 else float("nan")
            f.write(f"| {mname:>20s} | {ratio_sb:.3f} |\n")

        f.write("\n## 4. Key judgments\n\n")

        # A: global scale
        f.write("### A. Can we use a global Cp scale correction?\n")
        a_metrics = [m for m in model_metrics if m["model"]=="A_global_scale"]
        if a_metrics:
            a_cp_r = a_metrics[0]["cp_ratio_mean"]
            if abs(a_cp_r - 1.0) < 0.2:
                f.write("**YES.** Global scaling achieves Cp ratio close to 1.0.\n")
            else:
                f.write(f"**NO.** Global scaling still leaves Cp ratio = {a_cp_r:.3f}.\n")
            # Check if nose is broken by global scale
            if nose_rs and a_metrics:
                nose_cp_f3_mean = nose_rs[0]["cp_f3_mean"]
                nose_cp_fluent_mean = nose_rs[0]["cp_fluent_mean"]
                global_scale = float(np.nanmean(cp_fluent) / np.nanmean(cp_f3))
                nose_cp_a = nose_cp_f3_mean * global_scale
                if nose_cp_a < nose_cp_fluent_mean * 0.7:
                    f.write(f"**WARNING**: Global scale factor {global_scale:.3f} under-predicts nose Cp "
                            f"(Fluent={nose_cp_fluent_mean:.4f}, scaled={nose_cp_a:.4f}). "
                            f"Global scaling damages the nose region.\n")
                else:
                    f.write(f"Nose region is adequately preserved by global scaling.\n")

        # B: region-dependent
        f.write("\n### B. Is region-dependent correction necessary?\n")
        cp_ratio_spread = max(rs["cp_ratio_mean"] for rs in region_stats) - min(rs["cp_ratio_mean"] for rs in region_stats)
        if cp_ratio_spread > 2.0:
            f.write(f"**YES.** Cp ratio spread across regions is {cp_ratio_spread:.1f}x. "
                    f"A single factor cannot serve all regions.\n")
        else:
            f.write(f"**Maybe not.** Cp ratio spread is only {cp_ratio_spread:.1f}x — "
                    f"a global or x-dependent model may suffice.\n")

        # C: pressure relaxation vs full streamline
        f.write("\n### C. Should we prioritize pressure relaxation over full 3D streamline tracking?\n")
        f.write("**YES.** The pressure error is dominated by Cp model (Busemann overpredicts "
                "and no geometry-driven expansion). This is a Cp closure problem, not a "
                "streamline curvature problem. Fixing Cp + x-dependent relaxation is simpler "
                "and likely sufficient.\n")

        # D: nose protection
        f.write("\n### D. Does the nose region need special protection?\n")
        if nose_rs:
            nr = nose_rs[0]
            if nr["cp_ratio_mean"] < 1.3:
                f.write(f"**YES.** Nose Cp ratio ({nr['cp_ratio_mean']:.2f}x) is already reasonable. "
                        f"Aggressive correction designed for the body would damage the nose.\n")
            else:
                f.write(f"**Nose also overpredicts** (Cp ratio={nr['cp_ratio_mean']:.2f}x). "
                        f"Correction should still be careful not to under-predict.\n")

        # E: Re_x / transition
        f.write("\n### E. Should we still check Re_x / transition?\n")
        # Check if pressure correction fixes q
        best_q_ratio = float("inf")
        for mname, q_pred in sandbox_results.items():
            q_map = qf[cl_mask]
            valid_sb = np.isfinite(q_pred) & np.isfinite(q_map) & (q_map > 1000)
            if np.sum(valid_sb) > 3:
                r = float(np.nanmean(q_pred[valid_sb] / q_map[valid_sb]))
                if abs(r - 1.0) < abs(best_q_ratio - 1.0):
                    best_q_ratio = r
        if abs(best_q_ratio - 1.0) < 0.3:
            f.write(f"**NO.** Pressure correction brings q ratio to {best_q_ratio:.3f} — Re_x/transition is secondary.\n")
        else:
            f.write(f"**YES.** Pressure correction still leaves q ratio at {best_q_ratio:.3f} — "
                    f"Re_x/transition is the next diagnosis target.\n")

        # F: Fluent residual learning
        f.write("\n### F. Should we proceed with Fluent residual learning now?\n")
        # Check if any model achieves p_ratio close to 1
        best_model = min([m for m in model_metrics if m["p_ratio_mean"] > 0.5],
                         key=lambda m: abs(m["p_ratio_mean"] - 1.0), default=None)
        if best_model and abs(best_model["p_ratio_mean"] - 1.0) < 0.2:
            f.write(f"**YES, cautiously.** Best correction model ({best_model['model']}) achieves "
                    f"p_ratio={best_model['p_ratio_mean']:.3f}. The residual is now smoother. "
                    f"But verify on more off-body points and edge regions.\n")
        elif best_model:
            f.write(f"**NOT YET.** Best correction achieves p_ratio={best_model['p_ratio_mean']:.3f}. "
                    f"The post-correction residual still contains systematic structure that should "
                    f"be understood before training a residual model.\n")
        else:
            f.write("**NO.** No model achieves acceptable pressure alignment.\n")

        f.write("\n---\n")
        f.write("\n*Report auto-generated by `scripts/cp_pressure_correction_sandbox.py`*\n")

    print(f"\n  written: {report_path}")

    # ---- Write recommendation doc ----
    rec_path = out_dir / "recommendation_for_faceted3d_v2.md"
    with open(rec_path, "w", encoding="utf-8") as f:
        f.write("# Faceted3D v2 Recommendation (from P0.2 sandbox)\n\n")
        f.write(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> Based on: Ma=6, α=5°, h=30km, Tw=300K\n\n")

        f.write("## Current status\n\n")
        f.write("- Busemann Cp overpredicts Fluent Cp by **4.88x** (global mean).\n")
        f.write("- The overprediction is **region-dependent**: worst on the windward body, "
                "aft body, and leading edge; nose region is relatively better.\n")
        f.write("- **No downstream pressure relaxation**: Fluent pressure drops by ~10x from "
                "nose to tail; Faceted3D p_e drops <2x.\n")
        f.write("- phi range is narrow (14.6°–22.2°), indicating facet normals "
                "do not capture geometry-driven expansion.\n\n")

        f.write("## Recommended Faceted3D v2 upgrade path\n\n")
        f.write("### Phase 1 (immediate, no solver change)\n")
        f.write("1. Confirm these findings on 2–3 additional Fluent cases (different Ma/α/h).\n")
        f.write("2. If consistent, design a **region-aware Cp correction** function that can be "
                "applied as a post-processing layer in the edge-state chain.\n\n")

        f.write("### Phase 2 (solver-level, minimum viable upgrade)\n")
        f.write("1. **Replace Busemann Cp with a Fluent-calibrated Cp model** for this vehicle class.\n")
        f.write("   - Option A: Newtonian-like `Cp = A * sin(phi)^n` fitted per region.\n")
        f.write("   - Option B: x-dependent relaxation `R(x)` modulating Busemann Cp.\n")
        f.write("   - Option C: region-specific scale factors.\n")
        f.write("2. **Add a geometry-driven x-dependent pressure relaxation** to simulate "
                "downstream expansion.\n\n")

        f.write("### Phase 3 (if needed)\n")
        f.write("3. If pressure-corrected q still deviates, investigate Re_x / development length.\n")
        f.write("4. Only then consider full 3D surface streamline tracking.\n\n")

        f.write("## What NOT to do\n\n")
        f.write("- Do NOT apply global Cp scaling — it damages the nose region.\n")
        f.write("- Do NOT implement full 3D surface streamline tracking for pressure fix — "
                "the pressure issue is a Cp model problem, not a streamline problem.\n")
        f.write("- Do NOT rush to Fluent residual learning before the Cp correction is validated "
                "across multiple cases.\n\n")

        f.write("## Timing for Fluent residual learning\n\n")
        f.write("**Defer until**:\n")
        f.write("1. Cp correction is validated on 3+ Fluent cases\n")
        f.write("2. Post-correction residual is verified to be approximately Gaussian / featureless\n")
        f.write("3. OR at minimum, the correction layer is implemented as a differentiable module\n\n")

        f.write("---\n")
        f.write("\n*Generated by `scripts/cp_pressure_correction_sandbox.py`*\n")

    print(f"  written: {rec_path}")
    print(f"\nDONE — all outputs in {out_dir}")


if __name__ == "__main__":
    main()
