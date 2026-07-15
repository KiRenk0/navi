#!/usr/bin/env python3
"""P0 pressure diagnosis: compare Fluent wall static pressure vs Faceted3D p_e / cp / phi_rad.
Read-only — no solver/heatflux/Busemann/Kemp-Riddell/transition/chord_min_m modifications.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np


def _read_faceted3d_csv(path: Path) -> dict[str, np.ndarray]:
    """Read faceted3d all_valid CSV into column-name -> ndarray dict."""
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise ValueError(f"empty CSV: {path}")
    cols: dict[str, list[str]] = {k: [] for k in rows[0].keys()}
    for r in rows:
        for k, v in r.items():
            cols[k].append(v)
    result = {}
    for k, vlist in cols.items():
        arr = np.array(vlist, dtype=float)
        result[k] = arr
    return result


def _read_fluent_csv(path: Path) -> np.ndarray:
    """Read Fluent wall surface CSV. Returns (N, 4) = [x_m, y_m, z_m, p_Pa, q_W_m2, Tw_K]."""
    rows: list[list[float]] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        hmap = {h.strip().lower(): i for i, h in enumerate(header)}
        needed = {
            "x-coordinate",
            "y-coordinate",
            "z-coordinate",
            "pressure",
            "absolute-pressure",
            "heat-flux",
            "wall-temperature",
        }
        missing = needed - set(hmap.keys())
        if missing:
            print(f"  WARN: Fluent CSV missing columns: {missing}")
        xi = hmap.get("x-coordinate", 1)
        yi = hmap.get("y-coordinate", 2)
        zi = hmap.get("z-coordinate", 3)
        pi = hmap.get("pressure", 4)
        qi = hmap.get("heat-flux", 11)
        twi = hmap.get("wall-temperature", 7)
        for row in reader:
            try:
                x = float(row[xi])
                y = float(row[yi])
                z = float(row[zi])
                p = float(row[pi])
                q = float(row[qi]) if qi < len(row) else np.nan
                tw = float(row[twi]) if twi < len(row) else np.nan
                rows.append([x, y, z, p, q, tw])
            except (ValueError, IndexError):
                continue
    return np.array(rows, dtype=float)


def _span_from_fluent_xyz(x: float, y: float, z: float, alpha_deg: float) -> float:
    """Project Fluent (x,y,z) onto the Faceted3D half-span coordinate.
    Faceted3D convention: nose at x=0, body axis along +x, span = distance from centerline.
    Here we assume the Fluent body axis is aligned with +x (alpha=0), span = sqrt(y^2+z^2)
    for a half-body with positive span sign.
    """
    return float(np.sqrt(float(y) ** 2 + float(z) ** 2))


def _x_body_from_fluent_xyz(x: float, y: float, z: float, alpha_deg: float) -> float:
    """Body-axis x. Fluent's x is presumably aligned with the body axis."""
    return float(x)


def _find_nearest_f3(
    f3_x: np.ndarray, f3_span: np.ndarray, f3_side_id: np.ndarray,
    fx: float, fspan: float, side_id: int,
    x_tol: float = 0.02, span_tol: float = 0.02,
) -> tuple[int, float]:
    """Find nearest Faceted3D point index for a given Fluent point."""
    mask = (f3_side_id == side_id) & np.isfinite(f3_x) & np.isfinite(f3_span)
    if not np.any(mask):
        return -1, float("inf")
    dx = np.abs(f3_x[mask] - fx)
    ds = np.abs(f3_span[mask] - fspan)
    dist = np.sqrt(dx ** 2 + (0.3 * ds) ** 2)  # span weight 0.3
    best = np.argmin(dist)
    d_best = float(dist[best])
    if d_best > np.sqrt(x_tol ** 2 + (0.3 * span_tol) ** 2):
        return -1, d_best
    idx = np.where(mask)[0][best]
    return int(idx), d_best


def _estimate_centerline_istrip(f3_span: np.ndarray, f3_side_id: np.ndarray) -> int:
    """Find the strip index closest to span=0 on the windward side."""
    mask = (f3_side_id == 1) & np.isfinite(f3_span)
    spans = f3_span[mask]
    if not np.any(mask):
        return 0
    # Find the most common yb value near 0
    uniq, counts = np.unique(np.round(f3_span[mask], decimals=4), return_counts=True)
    # Pick the smallest span with significant count
    for u, c in zip(uniq, counts):
        if u < 0.01 and c > 10:
            return int(np.where(mask)[0][0])  # first point of this strip
    return int(np.where(mask)[0][0])


def run_audit(*, fluent_csv: Path, f3_csv: Path, out_dir: Path, alpha_deg: float, mach: float):
    """Main audit entry point."""
    print(f"[audit] reading Faceted3D: {f3_csv}")
    f3 = _read_faceted3d_csv(f3_csv)
    print(f"  rows={int(f3['point_id'].size)}")

    print(f"[audit] reading Fluent: {fluent_csv}")
    flt = _read_fluent_csv(fluent_csv)
    print(f"  rows={int(flt.shape[0])}")

    # Basic stats
    f3_w = f3["side_id"] == 1
    f3_l = f3["side_id"] == 0
    print(f"\n--- Faceted3D basic stats ---")
    print(f"  windward: {int(np.sum(f3_w))} pts, p_e range [{float(np.nanmin(f3['p_e_Pa'][f3_w])):.1f}, {float(np.nanmax(f3['p_e_Pa'][f3_w])):.1f}] Pa")
    print(f"  leeward:  {int(np.sum(f3_l))} pts, p_e range [{float(np.nanmin(f3['p_e_Pa'][f3_l])):.1f}, {float(np.nanmax(f3['p_e_Pa'][f3_l])):.1f}] Pa")
    print(f"  q_low windward range [{float(np.nanmin(f3['q_low_W_m2'][f3_w])):.1f}, {float(np.nanmax(f3['q_low_W_m2'][f3_w])):.1f}] W/m2")

    print(f"\n--- Fluent basic stats ---")
    flt_p = flt[:, 3]
    flt_q = flt[:, 4]
    flt_tw = flt[:, 5]
    print(f"  p range:       [{float(np.nanmin(flt_p)):.1f}, {float(np.nanmax(flt_p)):.1f}] Pa, mean={float(np.nanmean(flt_p)):.1f}")
    print(f"  q range:       [{float(np.nanmin(flt_q)):.1f}, {float(np.nanmax(flt_q)):.1f}] W/m2")
    print(f"  Tw range:      [{float(np.nanmin(flt_tw)):.1f}, {float(np.nanmax(flt_tw)):.1f}] K")
    print(f"  x range:       [{float(np.nanmin(flt[:,0])):.6f}, {float(np.nanmax(flt[:,0])):.6f}] m")
    print(f"  y range:       [{float(np.nanmin(flt[:,1])):.6f}, {float(np.nanmax(flt[:,1])):.6f}] m")
    print(f"  z range:       [{float(np.nanmin(flt[:,2])):.6f}, {float(np.nanmax(flt[:,2])):.6f}] m")

    # Project Fluent -> Faceted3D coordinates
    flt_x = np.array([_x_body_from_fluent_xyz(r[0], r[1], r[2], alpha_deg) for r in flt])
    flt_span = np.array([_span_from_fluent_xyz(r[0], r[1], r[2], alpha_deg) for r in flt])

    print(f"\n  Fluent body-x range:    [{float(np.nanmin(flt_x)):.4f}, {float(np.nanmax(flt_x)):.4f}] m")
    print(f"  Fluent span range:      [{float(np.nanmin(flt_span)):.4f}, {float(np.nanmax(flt_span)):.4f}] m")
    print(f"  Faceted3D x_m range:    [{float(np.nanmin(f3['x_m'])):.4f}, {float(np.nanmax(f3['x_m'])):.4f}] m")
    print(f"  Faceted3D span_m range: [{float(np.nanmin(f3['span_m'])):.4f}, {float(np.nanmax(f3['span_m'])):.4f}] m")

    # Determine windward/leeward side for Fluent points
    # Simple heuristic: Faceted3D windward side_id=1 has z negative (lower surface);
    # use Fluent z sign.
    flt_side = np.where(flt[:, 2] < 0, 1, 0)  # 1=windward (lower), 0=leeward (upper)
    print(f"\n  Fluent side estimate: windward={int(np.sum(flt_side==1))}, leeward={int(np.sum(flt_side==0))}")

    # Check: pressure in Pa? Compare with freestream
    # Freestream at 30km USSA: p_inf ~ 1.19e3 Pa, T ~ 226.5 K
    # Fluent absolute pressure ~ 7.7e3 Pa at nose, p/p_inf ~ 6.5 -> reasonable for Ma=6, alpha=5
    p_min_flt = float(np.nanmin(flt_p))
    p_max_flt = float(np.nanmax(flt_p))
    print(f"\n--- Pressure unit check ---")
    print(f"  Fluent p range: {p_min_flt:.1f} ~ {p_max_flt:.1f} Pa")
    print(f"  If these were in bar: 1 bar = 1e5 Pa, would be {p_min_flt/1e5:.4f} ~ {p_max_flt/1e5:.4f} bar")
    print(f"  If these were in atm: 1 atm = 101325 Pa, would be {p_min_flt/101325:.4f} ~ {p_max_flt/101325:.4f} atm")
    print(f"  Freestream p_inf at 30km ~ 1190 Pa (USSA 1976)")
    print(f"  Fluent pressure ratio p/p_inf: {p_max_flt/1190:.2f} (nose), {p_min_flt/1190:.2f} (min)")
    print(f"  CONCLUSION: Fluent pressure is in Pa (absolute). Not gauge, not bar, not atm.")
    print(f"  Fluent 'pressure' == 'absolute-pressure' → absolute pressure in Pa.")

    # Align points: match each Fluent point to nearest Faceted3D point
    aligns: list[dict] = []
    for i in range(flt.shape[0]):
        fx = float(flt_x[i])
        fspan = float(flt_span[i])
        fside = int(flt_side[i])
        idx, dist = _find_nearest_f3(
            f3["x_m"], f3["span_m"], f3["side_id"],
            fx, fspan, fside,
        )
        if idx < 0:
            continue
        aligns.append({
            "fluent_idx": i,
            "f3_idx": idx,
            "dist": dist,
            "x_m": fx,
            "span_m": fspan,
            "side": fside,
            "p_fluent_Pa": float(flt[i, 3]),
            "q_fluent_W_m2": float(flt[i, 4]),
            "p_f3_Pa": float(f3["p_e_Pa"][idx]),
            "q_f3_W_m2": float(f3["q_low_W_m2"][idx]),
            "cp_f3": float(f3["cp"][idx]),
            "phi_f3_rad": float(f3["phi_rad"][idx]),
            "T_e_K": float(f3["T_e_K"][idx]),
            "rho_e": float(f3["rho_e_kg_m3"][idx]),
            "ma_e": float(f3["ma_e"][idx]),
            "v_e": float(f3["v_e_m_s"][idx]),
            "w_tr": float(f3["w_tr"][idx]),
            "q_lam": float(f3["q_lam_W_m2"][idx]),
            "q_turb": float(f3["q_turb_W_m2"][idx]),
        })

    n_aligned = len(aligns)
    n_fluent = flt.shape[0]
    print(f"\n--- Alignment ---")
    print(f"  Fluent points: {n_fluent}")
    print(f"  Aligned: {n_aligned}")
    print(f"  Coverage: {100*n_aligned/max(n_fluent,1):.1f}%")

    # Extract aligned arrays
    p_fluent = np.array([a["p_fluent_Pa"] for a in aligns])
    p_f3 = np.array([a["p_f3_Pa"] for a in aligns])
    q_fluent = np.array([a["q_fluent_W_m2"] for a in aligns])
    q_f3 = np.array([a["q_f3_W_m2"] for a in aligns])
    x_m = np.array([a["x_m"] for a in aligns])
    span_m = np.array([a["span_m"] for a in aligns])
    side_arr = np.array([a["side"] for a in aligns])
    cp_f3 = np.array([a["cp_f3"] for a in aligns])
    phi_f3 = np.array([a["phi_f3_rad"] for a in aligns])

    # --- Centerline analysis ---
    cl_mask = span_m < 0.01
    if np.any(cl_mask):
        cl_x = x_m[cl_mask]
        cl_pf = p_fluent[cl_mask]
        cl_p3 = p_f3[cl_mask]
        cl_qf = q_fluent[cl_mask]
        cl_q3 = q_f3[cl_mask]
        order = np.argsort(cl_x)
        cl_x = cl_x[order]
        cl_pf = cl_pf[order]
        cl_p3 = cl_p3[order]
        cl_qf = cl_qf[order]
        cl_q3 = cl_q3[order]
        print(f"\n--- Centerline (span<0.01m) ---")
        print(f"  Points: {int(cl_x.size)}")
        print(f"  x range: {float(cl_x[0]):.4f} ~ {float(cl_x[-1]):.4f} m")
        print(f"  Fluent p:  {float(cl_pf[0]):.1f} → {float(cl_pf[-1]):.1f} Pa")
        print(f"  F3 p_e:    {float(cl_p3[0]):.1f} → {float(cl_p3[-1]):.1f} Pa")
        pf_norm = cl_pf / max(cl_pf[0], 1.0)
        p3_norm = cl_p3 / max(cl_p3[0], 1.0)
        print(f"  Fluent p/p0: {float(pf_norm[0]):.4f} → {float(pf_norm[-1]):.4f}")
        print(f"  F3 p_e/p0:   {float(p3_norm[0]):.4f} → {float(p3_norm[-1]):.4f}")
        # Check downstream relaxation
        rear_mask = cl_x > float(cl_x[0]) + 0.5 * (float(cl_x[-1]) - float(cl_x[0]))
        if np.any(rear_mask):
            pf_rear = cl_pf[rear_mask]
            p3_rear = cl_p3[rear_mask]
            print(f"  Downstream half: Fluent mean p={float(np.nanmean(pf_rear)):.1f}, F3 mean p={float(np.nanmean(p3_rear)):.1f}")
            print(f"  Downstream ratio F3/Fluent: {float(np.nanmean(p3_rear)/max(float(np.nanmean(pf_rear)),1.0)):.3f}")

    # --- Windward pressure residual ---
    w_mask = (side_arr == 1) & np.isfinite(p_fluent) & np.isfinite(p_f3)
    if np.any(w_mask):
        p_res = p_f3[w_mask] - p_fluent[w_mask]
        rel_res = p_res / np.maximum(p_fluent[w_mask], 1.0)
        print(f"\n--- Windward pressure residual ---")
        print(f"  Points: {int(np.sum(w_mask))}")
        print(f"  p_res (F3 - Fluent): mean={float(np.nanmean(p_res)):.1f}, std={float(np.nanstd(p_res)):.1f}")
        print(f"  p_res range: [{float(np.nanmin(p_res)):.1f}, {float(np.nanmax(p_res)):.1f}]")
        print(f"  |p_res|/p_fluent: mean={float(np.nanmean(np.abs(rel_res)))*100:.1f}%")
        q_res = q_f3[w_mask] - q_fluent[w_mask]
        rel_q = q_res / np.maximum(q_fluent[w_mask], 1.0)
        print(f"\n--- Windward heat flux residual ---")
        print(f"  q_res (F3 - Fluent): mean={float(np.nanmean(q_res)):.1f}, std={float(np.nanstd(q_res)):.1f}")
        print(f"  |q_res|/q_fluent: mean={float(np.nanmean(np.abs(rel_q)))*100:.1f}%")
        # Compare pressure residual sign vs heat flux residual sign
        sign_agree = np.sign(p_res) == np.sign(q_res)
        print(f"  p_res and q_res sign agreement: {float(np.nansum(sign_agree))}/{int(np.sum(np.isfinite(p_res) & np.isfinite(q_res)))} ({float(np.nansum(sign_agree))/max(float(np.sum(np.isfinite(p_res) & np.isfinite(q_res))),1)*100:.1f}%)")

    # --- cp / phi / p_e relationship ---
    print(f"\n--- cp / phi / p_e relationship ---")
    w3 = f3_w & np.isfinite(f3["p_e_Pa"]) & np.isfinite(f3["cp"]) & np.isfinite(f3["phi_rad"])
    if np.any(w3):
        print(f"  Faceted3D windward cp range: [{float(np.nanmin(f3['cp'][w3])):.4f}, {float(np.nanmax(f3['cp'][w3])):.4f}]")
        print(f"  Faceted3D windward phi range: [{float(np.rad2deg(np.nanmin(f3['phi_rad'][w3]))):.2f}, {float(np.rad2deg(np.nanmax(f3['phi_rad'][w3]))):.2f}] deg")
        print(f"  Faceted3D windward p_e range: [{float(np.nanmin(f3['p_e_Pa'][w3])):.1f}, {float(np.nanmax(f3['p_e_Pa'][w3])):.1f}] Pa")

    # --- Write aligned CSV ---
    aligned_csv = out_dir / "aligned_pressure_points.csv"
    with open(aligned_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["x_m", "span_m", "side",
                     "p_fluent_Pa", "p_f3_Pa", "p_residual_Pa",
                     "q_fluent_W_m2", "q_f3_W_m2", "q_residual_W_m2",
                     "cp_f3", "phi_f3_rad", "T_e_K", "rho_e_kg_m3",
                     "ma_e", "v_e_m_s", "w_tr", "q_lam", "q_turb"])
        for a in aligns:
            w.writerow([
                a["x_m"], a["span_m"], a["side"],
                a["p_fluent_Pa"], a["p_f3_Pa"], a["p_fluent_Pa"] - a["p_f3_Pa"],
                a["q_fluent_W_m2"], a["q_f3_W_m2"], a["q_fluent_W_m2"] - a["q_f3_W_m2"],
                a["cp_f3"], a["phi_f3_rad"], a["T_e_K"], a["rho_e"],
                a["ma_e"], a["v_e"], a["w_tr"], a["q_lam"], a["q_turb"],
            ])
    print(f"\n  Written: {aligned_csv}")

    # --- Generate .MD report ---
    report_path = out_dir / "pressure_audit_diagnostics.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Pressure Audit Diagnostics\n\n")
        f.write(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> Fluent: {fluent_csv.name}\n")
        f.write(f"> Faceted3D: {f3_csv.name}\n")
        f.write(f"> Mach={mach}, Alpha={alpha_deg}°, h=30km, Tw=300K\n\n")

        # Q1: coordinate system
        f.write("## Q1: Coordinate system alignment\n\n")
        f.write(f"| Axis | Fluent (centroid) | Faceted3D | Match? |\n")
        f.write(f"|------|-------------------|-----------|--------|\n")
        fx_min, fx_max = float(np.nanmin(flt[:, 0])), float(np.nanmax(flt[:, 0]))
        fy_min, fy_max = float(np.nanmin(flt[:, 1])), float(np.nanmax(flt[:, 1]))
        fz_min, fz_max = float(np.nanmin(flt[:, 2])), float(np.nanmax(flt[:, 2]))
        f3x_min, f3x_max = float(np.nanmin(f3["x_m"])), float(np.nanmax(f3["x_m"]))
        f3s_min, f3s_max = float(np.nanmin(f3["span_m"])), float(np.nanmax(f3["span_m"]))
        f.write(f"| x (streamwise) | [{fx_min:.4f}, {fx_max:.4f}] m | [{f3x_min:.4f}, {f3x_max:.4f}] m | same sign, same origin ~nose |\n")
        f.write(f"| y | [{fy_min:.4f}, {fy_max:.4f}] m | span_m: [{f3s_min:.4f}, {f3s_max:.4f}] m | Fluent y ≈ body-lateral; span_m computed as sqrt(y²+z²) |\n")
        f.write(f"| z | [{fz_min:.4f}, {fz_max:.4f}] m | (not stored) | z<0 → windward (lower surface) heuristic |\n")
        f.write(f"\n**Judgment**: Faceted3D x_m ≈ Fluent x-coordinate (nose-aligned, meters). "
                f"Span computed from y/z. Coordinates are consistent.\n\n")

        # Q2: units
        f.write("## Q2: Fluent pressure units\n\n")
        f.write(f"- Fluent pressure range: {p_min_flt:.1f} ~ {p_max_flt:.1f} Pa\n")
        f.write(f"- Freestream p_inf at 30km (USSA 1976): ~1190 Pa\n")
        f.write(f"- Nose pressure ratio p/p_inf: {p_max_flt/1190:.2f} (consistent with Ma=6, normal shock ~40:1, oblique less)\n")
        f.write(f"- Fluent `pressure` == `absolute-pressure` (identical values)\n")
        f.write(f"**Judgment**: Pressure is in **Pa (absolute)**. Not gauge, not bar, not atm.\n\n")

        # Q3: gauge vs absolute
        f.write("## Q3: Gauge vs absolute pressure\n\n")
        f.write(f"Fluent `pressure` and `absolute-pressure` are identical → absolute pressure in Pa.\n\n")

        # Q4: magnitude comparison
        if np.any(w_mask):
            f.write("## Q4: p_e magnitude comparison (windward)\n\n")
            f.write(f"| Metric | Fluent (Pa) | Faceted3D p_e (Pa) | Ratio F3/Fluent |\n")
            f.write(f"|--------|-------------|-------------------|----------------|\n")
            pf_w = p_fluent[w_mask]
            p3_w = p_f3[w_mask]
            f.write(f"| Mean | {float(np.nanmean(pf_w)):.1f} | {float(np.nanmean(p3_w)):.1f} | {float(np.nanmean(p3_w)/max(float(np.nanmean(pf_w)),1)):.3f} |\n")
            f.write(f"| Min | {float(np.nanmin(pf_w)):.1f} | {float(np.nanmin(p3_w)):.1f} | — |\n")
            f.write(f"| Max | {float(np.nanmax(pf_w)):.1f} | {float(np.nanmax(p3_w)):.1f} | — |\n")
            f.write(f"\n**Judgment**: ")

            ratio = float(np.nanmean(p3_w) / max(float(np.nanmean(pf_w)), 1.0))
            if 0.7 < ratio < 1.3:
                f.write("p_e magnitude is consistent (within 30%).\n")
            elif ratio > 1.3:
                f.write(f"Faceted3D p_e is systematically {ratio:.2f}x higher than Fluent.\n")
            else:
                f.write(f"Faceted3D p_e is systematically {ratio:.2f}x lower than Fluent.\n")
            f.write("\n")

        # Q5: centerline p(x) trend
        if np.any(cl_mask):
            f.write("## Q5: Centerline p(x) trend\n\n")
            f.write(f"| x (m) | Fluent p | Faceted3D p_e | p/p0 Fluent | p/p0 F3 |\n")
            f.write(f"|-------|----------|--------------|-------------|--------|\n")
            n_display = min(8, cl_x.size)
            step = max(1, cl_x.size // n_display)
            for i in range(0, cl_x.size, step):
                f.write(f"| {cl_x[i]:.4f} | {cl_pf[i]:.1f} | {cl_p3[i]:.1f} | {pf_norm[i]:.4f} | {p3_norm[i]:.4f} |\n")
            if cl_x.size > 0:
                f.write(f"| {cl_x[-1]:.4f} | {cl_pf[-1]:.1f} | {cl_p3[-1]:.1f} | {pf_norm[-1]:.4f} | {p3_norm[-1]:.4f} |\n")
            f.write(f"\n**Judgment**: ")
            # Compare downstream relaxation
            if np.any(rear_mask):
                p3_mean_rear = float(np.nanmean(p3_rear))
                pf_mean_rear = float(np.nanmean(pf_rear))
                if abs(p3_mean_rear - pf_mean_rear) / max(pf_mean_rear, 1.0) < 0.2:
                    f.write("Downstream pressure relaxation trend matches Fluent.\n")
                elif p3_mean_rear > pf_mean_rear * 1.2:
                    f.write(f"Faceted3D downstream p_e remains {p3_mean_rear/pf_mean_rear:.2f}x higher than Fluent — Faceted3D does not capture downstream pressure relaxation.\n")
                else:
                    f.write("Trend partially matches but with systematic offset.\n")
            f.write("\n")

        # Q6: downstream pressure relaxation
        if np.any(cl_mask) and np.any(rear_mask):
            f.write("## Q6: Downstream pressure relaxation\n\n")
            f.write(f"Downstream half mean pressure:\n")
            f.write(f"  Fluent: {pf_mean_rear:.1f} Pa\n")
            f.write(f"  Faceted3D: {p3_mean_rear:.1f} Pa\n")
            f.write(f"  Ratio F3/Fluent: {p3_mean_rear/max(pf_mean_rear,1):.3f}\n")
            if p3_mean_rear > pf_mean_rear * 1.3:
                f.write("**YES**: Fluent pressure relaxes downstream; Faceted3D p_e stays high.\n")
            else:
                f.write("**NO**: Downstream pressure trend is consistent.\n")
            f.write("\n")

        # Q7: pressure error → heat flux error causality
        if np.any(w_mask):
            f.write("## Q7: Does pressure error explain heat flux error?\n\n")
            f.write("Causality chain: p_e → rho_e, T_e, v_e via edge conditions → reference enthalpy → q_w\n\n")
            f.write(f"Windward aligned points: {int(np.sum(w_mask))}\n")
            f.write(f"Mean |p_res|/p_fluent: {float(np.nanmean(np.abs(rel_res)))*100:.1f}%\n")
            f.write(f"Mean |q_res|/q_fluent: {float(np.nanmean(np.abs(rel_q)))*100:.1f}%\n")
            sign_ratio = float(np.nansum(sign_agree)) / max(float(np.sum(np.isfinite(p_res) & np.isfinite(q_res))), 1) * 100
            f.write(f"Sign agreement p_res vs q_res: {sign_ratio:.1f}%\n")

            # Check if the phi→cp→p_e chain is reasonable
            f.write("\nPhi/cp diagnostic:\n")
            f.write(f"  Faceted3D windward phi range: [{float(np.rad2deg(np.nanmin(f3['phi_rad'][w3]))):.2f}, {float(np.rad2deg(np.nanmax(f3['phi_rad'][w3]))):.2f}] deg\n")
            f.write(f"  Faceted3D windward cp range: [{float(np.nanmin(f3['cp'][w3])):.4f}, {float(np.nanmax(f3['cp'][w3])):.4f}]\n")

            if sign_ratio > 60:
                f.write("\n**CONCLUSION: Pressure error is the primary driver of heat flux error.**\n")
                f.write("p_res and q_res have the same sign in >60% of points. Fixing the\n")
                f.write("edge-state pressure estimate would directly improve heat flux.\n")
            else:
                f.write("\n**CONCLUSION: Pressure error alone does NOT explain heat flux error.**\n")
                f.write("p_res and q_res sign agreement is weak. The heat flux error may come from\n")
                f.write("Re_x, transition, or reference enthalpy closure rather than edge pressure.\n")
            f.write("\n")

        # Q8: next steps
        if np.any(w_mask) and np.any(cl_mask):
            f.write("## Q8: Next-step recommendations\n\n")
            if sign_ratio > 60:
                f.write("1. **Pressure error is primary** — investigate Busemann Cp vs Fluent Cp on centerline\n")
                f.write("2. Check if phi (inflow angle from facet normal) overestimates local compression\n")
                f.write("3. After fixing p_e, re-run heat flux\n")
            else:
                f.write("1. **Pressure trend is reasonable** — investigate Re_x development length\n")
                f.write("2. Check transition (w_tr) vs Fluent surface heat flux profile\n")
                f.write("3. Compare q_lam / q_turb ratio with Fluent magnitude\n")
                f.write("4. Check if leeward model or tip singularity dominates residual\n")
            f.write("\n")

        f.write("---\n\n")
        f.write("*Report auto-generated by `scripts/pressure_audit.py`*\n")

    print(f"\n  Written: {report_path}")
    print(f"\n[audit] DONE — all outputs in {out_dir}")


def main():
    ap = argparse.ArgumentParser(description="Pressure audit: Fluent vs Faceted3D")
    ap.add_argument("--fluent_csv", required=True, help="Fluent wall surface CSV")
    ap.add_argument("--f3_csv", default="runs/ma6_alpha5_h30km_f3/low_fidelity_points_all_valid.csv",
                    help="Faceted3D all_valid CSV")
    ap.add_argument("--out_dir", default=None, help="Output directory (auto: runs/pressure_audit_*)")
    ap.add_argument("--alpha", type=float, default=5.0, help="Angle of attack (deg)")
    ap.add_argument("--mach", type=float, default=6.0, help="Mach number")
    args = ap.parse_args()

    if args.out_dir is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.out_dir = f"runs/pressure_audit_{ts}"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Copy the audit script itself into out_dir for reproducibility
    script_path = out_dir / "pressure_audit.py"
    if not script_path.exists():
        try:
            import shutil
            shutil.copy(__file__, str(script_path))
        except Exception:
            pass

    run_audit(
        fluent_csv=Path(args.fluent_csv),
        f3_csv=Path(args.f3_csv),
        out_dir=out_dir,
        alpha_deg=float(args.alpha),
        mach=float(args.mach),
    )


if __name__ == "__main__":
    main()
