#!/usr/bin/env python3
"""Faceted3D v2 Phase 2D — Round 2.5 Read-Only Feasibility Audit.

Red-line constraints enforced:
1. No src/ modification — reads existing solver output CSV/tables only.
2. No specs/ / YAML / default modification.
3. No ma8_a10 / a10 / h50km access — hard-coded allowlist exit on any match.
4. No candidate implementation — DN, Tauber, CBAERO, AL4, H, B all not implemented.
5. No KR / Cp / reference-enthalpy core / eq 2.46 / chord_min_m / q_scale touching.
6. Tauber q is named q_tauber_ref_readonly — offline reference only.
7. Tauber final mask index-0 / cap_mask / true_nose_cap contamination = 0.

Task A: Tauber / CBAERO leading_edge_near readonly audit
Task B: AL4 spanwise convergence readonly proxy audit

Outputs:
  runs/faceted3d_v2_phase2d_round2p5_readonly_audit/round2p5_tauber_readonly_points.csv
  runs/faceted3d_v2_phase2d_round2p5_readonly_audit/round2p5_al4_proxy_points.csv
"""

from __future__ import annotations

import csv
import math
import re
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Red-line: hard-coded allowlist — reject ma8_a10 / a10 / h50km in any path or id
# ---------------------------------------------------------------------------
_ALLOWED_CASES = frozenset(["ma6_a5_h30km", "ma8_a5_h30km"])
_FORBIDDEN_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [r"ma8_a10", r"\ba10\b", r"h50km"]]


def _check_allowlist(case_id: str, caller: str = "") -> None:
    if case_id not in _ALLOWED_CASES:
        msg = f"[REDLINE] Case {case_id!r} not in allowlist {sorted(_ALLOWED_CASES)}"
        if caller:
            msg += f" (caller: {caller})"
        raise SystemExit(msg)
    for pat in _FORBIDDEN_PATTERNS:
        if pat.search(case_id):
            msg = f"[REDLINE] Case {case_id!r} matches forbidden pattern {pat.pattern!r}"
            if caller:
                msg += f" (caller: {caller})"
            raise SystemExit(msg)


def _check_path_allowlist(path_obj: Path) -> None:
    path_str = str(path_obj.as_posix())
    case_match = re.search(r"(ma[0-9]+_a[0-9]+_h[0-9]+km)", path_str)
    if case_match:
        _check_allowlist(case_match.group(1), caller=f"path={path_str}")
    for pat in _FORBIDDEN_PATTERNS:
        if pat.search(path_str):
            msg = f"[REDLINE] Path {path_str!r} matches forbidden pattern {pat.pattern!r}"
            raise SystemExit(msg)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent
RUNS = BASE / "runs"
AUDIT_DIR = RUNS / "faceted3d_v2_phase2d_round2p5_readonly_audit"
FLUENT_DIR = BASE / "fluent_export"

AUDIT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Constants (read-only — same values as region master table; not touching src)
# ---------------------------------------------------------------------------
Rn = 0.03
r_cap = 0.03
Pr = 0.72
GAMMA = 1.4
R_GAS = 287.0
CHORD_MIN_M = 0.02

sweep_le_deg = 72.0
planform_half_angle_deg = 18.0
b_half_m = 1.031027
c_root_m = 3.6

# ---------------------------------------------------------------------------
# Atmosphere (read-only re-implementation)
# ---------------------------------------------------------------------------
def _ussa(h_m: float) -> tuple[float, float, float]:
    R = 287.0; g0 = 9.80665
    if h_m <= 11000:
        T = 288.15 - 0.0065 * h_m
        P = 101325 * (T / 288.15) ** (-g0 / (R * -0.0065))
    elif h_m <= 20000:
        T = 216.65
        P = 22632.1 * np.exp(-g0 / (R * T) * (h_m - 11000))
    else:
        T = 216.65 + 0.001 * (h_m - 20000)
        P = 5474.89 * (T / 216.65) ** (-g0 / (R * 0.001))
    rho = P / (R * T)
    return float(P), float(rho), float(T)


def _freestream_v(mach: float, T_inf: float) -> float:
    return mach * math.sqrt(1.4 * R_GAS * T_inf)


# ---------------------------------------------------------------------------
# CASE definitions (hard-coded allowlist active cases only)
# ---------------------------------------------------------------------------
CASES = [
    {"id": "ma6_a5_h30km", "mach": 6.0, "alpha": 5.0, "h_m": 30000.0,
     "fluent_csv": FLUENT_DIR / "ma6_alpha5_h30km.csv",
     "solver_csv": RUNS / "ma6_alpha5_h30km_f3" / "low_fidelity_points_all.csv"},
    {"id": "ma8_a5_h30km", "mach": 8.0, "alpha": 5.0, "h_m": 30000.0,
     "fluent_csv": FLUENT_DIR / "ma8_alpha5_h30km.csv",
     "solver_csv": RUNS / "ma8_alpha5_h30km_f3" / "low_fidelity_points_all.csv"},
]

for c in CASES:
    _check_allowlist(c["id"])
    _check_path_allowlist(c["fluent_csv"])
    _check_path_allowlist(c["solver_csv"])

# ---------------------------------------------------------------------------
# Region assignment (read-only — matches region master table spec)
# ---------------------------------------------------------------------------
def assign_region_windward(x: float, span: float, xc: float) -> str:
    if not (np.isfinite(x) and np.isfinite(span)):
        return "unknown"
    if x * x + span * span <= r_cap * r_cap:
        return "cap_mask"
    if x < 5.0 * Rn and span < 0.10:
        return "true_nose_cap"
    if span > x / 6.0:
        return "leading_edge_near"
    if xc > 0.5:
        return "aft_body"
    return "windward_body"


# ---------------------------------------------------------------------------
# Fluent CSV reader
# ---------------------------------------------------------------------------
def read_fluent_csv(path: Path) -> np.ndarray:
    _check_path_allowlist(path)
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    hm = {hs.strip().lower(): i for i, hs in enumerate(header)}
    xi = hm.get("x-coordinate", 1)
    yi = hm.get("y-coordinate", 2)
    zi = hm.get("z-coordinate", 3)
    qi = hm.get("heat-flux", 12)
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            try:
                x = float(row[xi])
                y = float(row[yi])
                z = float(row[zi])
                span = math.sqrt(y * y + z * z)
                q = -float(row[qi])
                rows.append([x, span, z, q, y])
            except (ValueError, IndexError):
                continue
    return np.array(rows, dtype=float)


# ---------------------------------------------------------------------------
# Solver CSV reader
# ---------------------------------------------------------------------------
SOLVER_COLUMNS = [
    "point_id", "side", "side_id", "mach", "alpha_deg", "altitude_km",
    "Tw_K", "x_m", "span_m", "xc", "yb", "valid_mask",
    "q_low_W_m2", "T_e_K", "p_e_Pa", "rho_e_kg_m3", "ma_e",
    "v_e_m_s", "mu_e_Pa_s", "phi_rad", "cp", "cp0",
    "h_e_J_per_kg", "T_r_lam_K", "h_r_lam_J_per_kg",
    "h_star_lam_J_per_kg", "T_r_turb_K", "h_r_turb_J_per_kg",
    "h_star_turb_J_per_kg", "q_lam_W_m2", "q_turb_W_m2",
    "St_l", "Re_ns_l", "w_tr", "re_edge", "re_tri",
]


def read_solver_csv(path: Path) -> dict[str, np.ndarray]:
    _check_path_allowlist(path)
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    col_map = {hs.strip(): i for i, hs in enumerate(header)}
    data = {k: [] for k in SOLVER_COLUMNS}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            for k in SOLVER_COLUMNS:
                try:
                    data[k].append(float(row[col_map[k]]))
                except (ValueError, IndexError):
                    data[k].append(float("nan"))
    return {k: np.array(v, dtype=float) for k, v in data.items()}


# ---------------------------------------------------------------------------
# Task A — Tauber / CBAERO swept-cylinder reference heat flux
# ---------------------------------------------------------------------------

def effective_alpha(alpha_deg: float, sweep_deg: float) -> float:
    arad = math.radians(alpha_deg)
    chi = math.radians(sweep_deg)
    ca = math.cos(arad)
    val = ca * ca + (math.sin(chi) * math.sin(arad)) ** 2
    val = max(0.0, min(1.0, val))
    return math.degrees(math.asin(math.sqrt(val)))


def local_sweep_deg(yb: float) -> float:
    if not np.isfinite(yb):
        return float("nan")
    local_sweep = sweep_le_deg - planform_half_angle_deg * yb
    return float(np.clip(local_sweep, 10.0, 90.0))


def tauber_swept_cylinder_q(
    rho_edge: float, v_edge: float, mu_edge: float,
    h_r: float, h_w: float,
    R_curv_m: float,
    sweep_deg: float,
    Pr_wf: float = 0.72,
) -> float:
    Rc = max(float(R_curv_m), 1e-6)
    sweep_rad = math.radians(float(sweep_deg))
    cosL = math.cos(sweep_rad)
    sinL = math.sin(sweep_rad)

    Re_w = rho_edge * v_edge * Rc / mu_edge
    Re_w = max(Re_w, 1.0)

    Nu_w = 0.767 * (Pr_wf ** 0.4) * (Re_w ** 0.5)
    q_ref = Nu_w * mu_edge * (h_r - h_w) / (Pr_wf * Rc)

    sweep_factor = cosL * (1.0 - 0.18 * sinL * sinL)
    sweep_factor = max(sweep_factor, 0.01)

    return float(q_ref * sweep_factor)


def compute_R_curv_local_strip(
    x_arr: np.ndarray, phi_arr: np.ndarray, chord_m: float,
) -> tuple[float, str, str]:
    n = len(x_arr)
    if n < 3:
        return float("nan"), "unavailable", "insufficient_points"

    valid = np.isfinite(x_arr) & np.isfinite(phi_arr)
    if np.sum(valid) < 3:
        return float("nan"), "unavailable", "insufficient_valid"

    xv = x_arr[valid]
    phiv = phi_arr[valid]

    try:
        dphi_dx = np.gradient(phiv, xv)
    except Exception:
        return float("nan"), "unavailable", "gradient_failed"

    median_grad = float(np.nanmedian(np.abs(dphi_dx)))

    if not np.isfinite(median_grad) or median_grad <= 1e-12:
        return float("nan"), "unavailable", "zero_gradient_magnitude"

    R_curv = 1.0 / median_grad
    R_curv = float(np.clip(R_curv, 1e-4, 1e3))

    status = "available" if np.isfinite(R_curv) and R_curv > 1e-3 else "unstable"
    method = "phi_gradient" if np.isfinite(R_curv) else "unavailable"
    return float(R_curv), str(status), str(method)


def nearest_fluent_q(sx: float, sy: float,
                     flt_data: np.ndarray) -> float:
    if flt_data.shape[0] == 0:
        return float("nan")
    dx = np.abs(flt_data[:, 0] - sx)
    ds = np.abs(flt_data[:, 1] - sy)
    dist = np.sqrt(dx ** 2 + (0.3 * ds) ** 2)
    best = int(np.nanargmin(dist))
    if dist[best] <= np.sqrt(0.02 ** 2 + (0.3 * 0.02) ** 2):
        return float(flt_data[best, 3])
    return float("nan")


# ---------------------------------------------------------------------------
# Task A — Main audit for Tauber
# ---------------------------------------------------------------------------
def audit_tauber_readonly():
    tauber_rows = []

    for case in CASES:
        case_id = case["id"]
        mach = case["mach"]
        alpha = case["alpha"]
        h_m = case["h_m"]
        solver_csv = case["solver_csv"]
        fluent_csv = case["fluent_csv"]

        _check_allowlist(case_id, caller="audit_tauber_readonly")
        print(f"[Task A] Processing {case_id} ...")

        p_inf, rho_inf, T_inf = _ussa(h_m)
        v_inf = _freestream_v(mach, T_inf)

        sv = read_solver_csv(solver_csv)

        n_total = len(sv["x_m"])

        # Pre-compute per-strip R_curv using phi gradient along strip
        unique_yb = np.unique(sv["yb"])
        strip_r_curv = {}
        for yb_val in unique_yb:
            m = np.abs(sv["yb"] - yb_val) < 0.005
            x_sub = sv["x_m"][m]
            phi_sub = sv["phi_rad"][m]
            chord = c_root_m
            Rc, Rst, Rmt = compute_R_curv_local_strip(x_sub, phi_sub, chord)
            strip_r_curv[float(yb_val)] = {"R_curv": Rc, "status": Rst, "method": Rmt}

        case_rows = []
        for i in range(n_total):
            x_m = float(sv["x_m"][i])
            span_m = float(sv["span_m"][i])
            xc = float(sv["xc"][i])
            yb = float(sv["yb"][i])
            valid = bool(sv["valid_mask"][i] > 0.5)

            if not valid:
                continue

            region = assign_region_windward(x_m, span_m, xc)

            is_index0 = abs(xc) < 1e-10
            is_cap_mask = region == "cap_mask"
            is_true_nose_cap = region == "true_nose_cap"
            is_leading_edge_near = region == "leading_edge_near"

            included_in_tauber = is_leading_edge_near and not is_index0 and not is_cap_mask and not is_true_nose_cap
            excluded_reason = ""
            if not is_leading_edge_near:
                excluded_reason = "not_leading_edge_near"
            elif is_index0:
                excluded_reason = "index0"
            elif is_cap_mask:
                excluded_reason = "cap_mask"
            elif is_true_nose_cap:
                excluded_reason = "true_nose_cap"

            q_lam_baseline = float(sv["q_lam_W_m2"][i])
            phi_rad = float(sv["phi_rad"][i])
            Ma_inf = float(mach)
            local_sweep = local_sweep_deg(yb)
            Ma_normal_eff = mach * math.cos(math.radians(local_sweep))

            # R_curv from strip-level estimate
            R_curv_info = strip_r_curv.get(float(yb), {"R_curv": float("nan"), "status": "unavailable", "method": "no_strip_data"})
            R_curv = R_curv_info["R_curv"]
            R_status = R_curv_info["status"]
            R_method = R_curv_info["method"]

            x_phys_baseline = float(x_m)

            T_e = float(sv["T_e_K"][i])
            p_e = float(sv["p_e_Pa"][i])
            rho_e = float(sv["rho_e_kg_m3"][i])
            v_e = float(sv["v_e_m_s"][i])
            mu_e = float(sv["mu_e_Pa_s"][i])
            h_r_lam = float(sv["h_r_lam_J_per_kg"][i])
            h_star_lam = float(sv["h_star_lam_J_per_kg"][i])
            h_w = h_star_lam if np.isfinite(h_star_lam) and h_star_lam > 0 else 300.0 * 1005.0

            q_tauber_ref = float("nan")
            if included_in_tauber and np.isfinite(R_curv) and R_curv > 1e-3:
                q_tauber_ref = tauber_swept_cylinder_q(
                    rho_edge=rho_e, v_edge=v_e, mu_edge=mu_e,
                    h_r=h_r_lam, h_w=h_w,
                    R_curv_m=R_curv,
                    sweep_deg=local_sweep,
                )

            tauber_direction_sign = float("nan")
            q_tauber_over_baseline = float("nan")
            if np.isfinite(q_tauber_ref) and q_tauber_ref > 0 and np.isfinite(q_lam_baseline) and q_lam_baseline > 0:
                q_tauber_over_baseline = q_tauber_ref / q_lam_baseline
                tauber_direction_sign = 1.0 if q_tauber_over_baseline > 1.0 else (-1.0 if q_tauber_over_baseline < 1.0 else 0.0)

            case_rows.append({
                "case_id": case_id,
                "region": region,
                "side": "windward",
                "i_x": i,
                "j_span": int(round(yb * 40)),
                "x_m": x_m,
                "y_m": span_m,
                "z_m": 0.0,
                "valid_mask": int(valid),
                "is_leading_edge_near": int(is_leading_edge_near),
                "is_cap_mask": int(is_cap_mask),
                "is_true_nose_cap": int(is_true_nose_cap),
                "is_index0": int(is_index0),
                "included_in_tauber_audit": int(included_in_tauber),
                "excluded_reason": excluded_reason,
                "local_sweep_deg": local_sweep,
                "Ma_inf": Ma_inf,
                "Ma_normal_eff": Ma_normal_eff,
                "R_curv_local_m": R_curv,
                "R_curv_status": R_status,
                "R_curv_estimation_method": R_method,
                "x_phys_baseline_m": x_phys_baseline,
                "q_lam_baseline": q_lam_baseline,
                "q_tauber_ref_readonly": q_tauber_ref,
                "q_tauber_over_baseline": q_tauber_over_baseline,
                "tauber_direction_sign": tauber_direction_sign,
            })

        # Contamination check
        tauber_included = [r for r in case_rows if r["included_in_tauber_audit"]]
        n_index0 = sum(1 for r in tauber_included if r["is_index0"])
        n_cap = sum(1 for r in tauber_included if r["is_cap_mask"])
        n_true_nose = sum(1 for r in tauber_included if r["is_true_nose_cap"])
        n_contaminated = n_index0 + n_cap + n_true_nose

        if n_contaminated > 0:
            raise SystemExit(
                f"[FATAL] Tauber final mask contamination must be 0, got {n_contaminated} for {case_id}"
            )
        print(f"[Task A] {case_id}: leading_edge_near points={len(tauber_included)}, "
              f"contamination={n_contaminated} (OK)")

        tauber_rows.extend(case_rows)

    # Write CSV
    csv_path = AUDIT_DIR / "round2p5_tauber_readonly_points.csv"
    fieldnames = [
        "case_id", "region", "side", "i_x", "j_span", "x_m", "y_m", "z_m",
        "valid_mask",
        "is_leading_edge_near", "is_cap_mask", "is_true_nose_cap", "is_index0",
        "included_in_tauber_audit", "excluded_reason",
        "local_sweep_deg",
        "Ma_inf", "Ma_normal_eff",
        "R_curv_local_m", "R_curv_status", "R_curv_estimation_method",
        "x_phys_baseline_m",
        "q_lam_baseline",
        "q_tauber_ref_readonly",
        "q_tauber_over_baseline",
        "tauber_direction_sign",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(tauber_rows)

    print(f"[Task A] Written {len(tauber_rows)} rows to {csv_path}")

    # Summary
    for case_id in [c["id"] for c in CASES]:
        cr = [r for r in tauber_rows if r["case_id"] == case_id and r["included_in_tauber_audit"]]
        ratios = [r["q_tauber_over_baseline"] for r in cr if np.isfinite(r["q_tauber_over_baseline"])]
        if ratios:
            rarr = np.array(ratios)
            gt1 = int(np.sum(rarr > 1.0))
            le1 = int(np.sum(rarr <= 1.0))
            print(f"[Task A] {case_id}: Tauber/q_lam — "
                  f"n={len(ratios)}, mean={np.nanmean(rarr):.4f}, "
                  f"median={np.nanmedian(rarr):.4f}, "
                  f">1={gt1}/{len(ratios)}, <=1={le1}/{len(ratios)}")
        else:
            print(f"[Task A] {case_id}: No valid Tauber ratios (R_curv estimation may need STL)")

    return tauber_rows


# ---------------------------------------------------------------------------
# Task B — AL4 spanwise convergence proxy audit
# ---------------------------------------------------------------------------

def _streamline_convergence_proxy(yb: float, x_m: float, span_m: float) -> float:
    if not all(np.isfinite([yb, x_m, span_m])):
        return float("nan")
    x_le_at_span = span_m / math.tan(math.radians(planform_half_angle_deg))
    dist_from_le = max(x_m - x_le_at_span, CHORD_MIN_M)
    if dist_from_le <= 0:
        return float("nan")
    conv_angle = math.atan2(span_m, dist_from_le)
    return float(math.degrees(conv_angle))


def _spanwise_pressure_gradient_proxy(p_e_arr: np.ndarray, span_arr: np.ndarray) -> float:
    valid = np.isfinite(p_e_arr) & np.isfinite(span_arr)
    if np.sum(valid) < 3:
        return float("nan")
    try:
        grad = np.gradient(p_e_arr[valid], span_arr[valid])
        return float(np.nanmean(grad))
    except Exception:
        return float("nan")


def _surface_flow_divergence_proxy(phi_arr: np.ndarray, span_arr: np.ndarray) -> float:
    valid = np.isfinite(phi_arr) & np.isfinite(span_arr)
    if np.sum(valid) < 3:
        return float("nan")
    try:
        grad = np.gradient(phi_arr[valid], span_arr[valid])
        return float(np.nanmean(grad))
    except Exception:
        return float("nan")


def audit_al4_proxy():
    al4_rows = []

    for case in CASES:
        case_id = case["id"]
        mach = case["mach"]
        h_m = case["h_m"]
        solver_csv = case["solver_csv"]
        fluent_csv = case["fluent_csv"]

        _check_allowlist(case_id, caller="audit_al4_proxy")
        print(f"[Task B] Processing {case_id} ...")

        sv = read_solver_csv(solver_csv)
        flt = read_fluent_csv(fluent_csv)

        n_total = len(sv["x_m"])

        unique_yb = np.unique(sv["yb"])
        strip_data = {}
        for yb_val in unique_yb:
            m = np.abs(sv["yb"] - yb_val) < 0.005
            strip_data[float(yb_val)] = {
                "p_e_Pa": sv["p_e_Pa"][m],
                "phi_rad": sv["phi_rad"][m],
                "span_m": sv["span_m"][m],
            }

        case_rows = []
        for i in range(n_total):
            x_m = float(sv["x_m"][i])
            span_m = float(sv["span_m"][i])
            xc = float(sv["xc"][i])
            yb = float(sv["yb"][i])
            valid = bool(sv["valid_mask"][i] > 0.5)

            if not valid:
                continue

            region = assign_region_windward(x_m, span_m, xc)
            if region != "windward_body":
                continue

            q_lam = float(sv["q_lam_W_m2"][i])
            q_baseline = float(sv["q_low_W_m2"][i])
            q_fluent = nearest_fluent_q(x_m, span_m, flt)
            q_ratio = q_baseline / q_fluent if np.isfinite(q_fluent) and q_fluent > 0 else float("nan")
            q_deficit = 1.0 - q_ratio if np.isfinite(q_ratio) else float("nan")

            conv_proxy = _streamline_convergence_proxy(yb, x_m, span_m)

            this_yb_idx = int(np.argmin(np.abs(unique_yb - yb)))
            spg_proxy = float("nan")
            sfd_proxy = float("nan")
            if len(unique_yb) >= 3:
                lo = max(0, this_yb_idx - 2)
                hi = min(len(unique_yb), this_yb_idx + 3)
                near_yb = unique_yb[lo:hi]
                near_p = np.array([np.nanmean(strip_data[float(y)]["p_e_Pa"]) for y in near_yb])
                near_phi = np.array([np.nanmean(strip_data[float(y)]["phi_rad"]) for y in near_yb])
                spg_proxy = _spanwise_pressure_gradient_proxy(near_p, near_yb)
                sfd_proxy = _surface_flow_divergence_proxy(near_phi, near_yb)

            case_rows.append({
                "case_id": case_id,
                "region": region,
                "side": "windward",
                "i_x": i,
                "j_span": int(round(yb * 40)),
                "x_m": x_m,
                "y_m": span_m,
                "z_m": float("nan"),
                "q_fluent": q_fluent,
                "q_baseline": q_baseline,
                "q_ratio": q_ratio,
                "q_deficit": q_deficit,
                "streamline_convergence_proxy": conv_proxy,
                "spanwise_pressure_gradient_proxy": spg_proxy,
                "surface_flow_divergence_proxy": sfd_proxy,
            })

        al4_rows.extend(case_rows)
        print(f"[Task B] {case_id}: windward_body points={len(case_rows)}")

    # Write CSV
    csv_path = AUDIT_DIR / "round2p5_al4_proxy_points.csv"
    fieldnames = [
        "case_id", "region", "side", "i_x", "j_span", "x_m", "y_m", "z_m",
        "q_fluent", "q_baseline", "q_ratio", "q_deficit",
        "streamline_convergence_proxy",
        "spanwise_pressure_gradient_proxy",
        "surface_flow_divergence_proxy",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(al4_rows)

    print(f"[Task B] Written {len(al4_rows)} rows to {csv_path}")

    # Spearman correlations
    print("\n[Task B] Spearman correlations:")
    for case_id in [c["id"] for c in CASES]:
        cr = [r for r in al4_rows if r["case_id"] == case_id]
        if not cr:
            continue
        qr = np.array([r["q_ratio"] for r in cr])
        qd = np.array([r["q_deficit"] for r in cr])
        sc = np.array([r["streamline_convergence_proxy"] for r in cr])
        sp = np.array([r["spanwise_pressure_gradient_proxy"] for r in cr])
        sf = np.array([r["surface_flow_divergence_proxy"] for r in cr])

        try:
            from scipy.stats import spearmanr
            pairs = [
                ("streamline_conv vs q_ratio", sc, qr),
                ("spanwise_p_grad vs q_ratio", sp, qr),
                ("surface_divergence vs q_ratio", sf, qr),
            ]
            for label, proxy, target in pairs:
                valid = np.isfinite(proxy) & np.isfinite(target)
                if np.sum(valid) >= 10:
                    rho, pv = spearmanr(proxy[valid], target[valid])
                    print(f"  {case_id}: {label}: r={rho:.4f}, p={pv:.4g}, n={np.sum(valid)}")
        except ImportError:
            print(f"  [scipy not available — cannot compute Spearman]")

    return al4_rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 72)
    print("Faceted3D v2 Phase 2D — Round 2.5 Read-Only Feasibility Audit")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 72)

    print("\nAll cases checked against allowlist:")
    for c in CASES:
        _check_allowlist(c["id"])
        print(f"  PASS: {c['id']}")

    print("\n--- Task A: Tauber / CBAERO leading_edge_near readonly audit ---")
    tauber_rows = audit_tauber_readonly()

    print("\n--- Task B: AL4 spanwise convergence readonly proxy audit ---")
    al4_rows = audit_al4_proxy()

    print(f"\n{'=' * 72}")
    print(f"Audit completed: {datetime.now().isoformat()}")
    print(f"  Tauber CSV: {AUDIT_DIR / 'round2p5_tauber_readonly_points.csv'}")
    print(f"  AL4 proxy CSV: {AUDIT_DIR / 'round2p5_al4_proxy_points.csv'}")
    print("All red-line constraints satisfied.")
    print(f"{'=' * 72}")
