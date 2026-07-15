"""Phase 5-A-P1 — Route A adiabatic wall temperature / Taw prototype.

Calculates Taw_lam, Taw_turb, Taw (recovery wall temperature)
from existing Faceted3D step baseline edge fields.

Sandbox-only, wrapper-only. No code modification to frozen src.
No Fluent adiabatic wall comparison. No temperature model validation.
"""
from __future__ import annotations

import json, hashlib, logging, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ref_enthalpy_method.aero.adiabatic_wall_temp import (
    compute_adiabatic_wall_temperature,
)

BASE = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = BASE / "runs/0630_phase2d_c1_dn/baseline_snapshot"
SANDBOX = BASE / "runs/_sandbox/phase5a_adiabatic_prototype"
LOG_DIR = SANDBOX / "logs"

CASES = ["ma6_a5_h30km", "ma8_a5_h30km"]

PR = 0.72
GAMMA_AIR = 1.4

FROZEN_SRC_MD5 = {
    "src/ref_enthalpy_method/aero/windward_cache_faceted3d.py":
        "04FE782AC474C0AFC5B556622B349095",
    "src/ref_enthalpy_method/solver_faceted3d.py":
        "54730252749E81ACD68B57A56FD6174A",
    "src/ref_enthalpy_method/config/lf_qw.py":
        "F222F44A0FC08527FB8998E7BF45CD39",
    "src/ref_enthalpy_method/aero/windward_cache.py":
        "A7EF876E36C1EB32481FE7ED6BBFA770",
    "src/ref_enthalpy_method/aero/transition.py":
        "53AC74516EAFB89E3FCF9280086510BB",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("phase5a_taw")


def md5_hex(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest().upper()


def compute_region_masks(xc: np.ndarray, mask: np.ndarray) -> dict[str, np.ndarray]:
    xc_f = np.asarray(xc, dtype=float).reshape(-1)
    m = np.asarray(mask, dtype=bool).reshape(-1)
    return {
        "leading_edge_near": m & (xc_f < 0.1),
        "windward_body": m & (xc_f >= 0.1) & (xc_f < 0.8),
        "aft_body": m & (xc_f >= 0.8),
        "global_valid_windward": m,
    }


def region_stats(name: str, mask: np.ndarray, d: np.ndarray) -> dict:
    v = np.asarray(d, dtype=float).reshape(-1)[mask]
    n = int(np.sum(mask))
    result: dict = {"region": name, "valid_count": n}
    if n == 0:
        return result
    result["mean"] = float(np.mean(v))
    result["min"] = float(np.min(v))
    result["max"] = float(np.max(v))
    return result


def process_case(case_name: str) -> dict:
    log.info("=" * 60)
    log.info("Processing case: %s", case_name)

    npz_path = SNAPSHOT_DIR / case_name / "fields.npz"
    if not npz_path.exists():
        raise FileNotFoundError(f"Baseline fields not found: {npz_path}")

    data = np.load(npz_path)

    T_e = data["T_e_w"].copy()
    M_e = data["ma_e_w"].copy()
    w_tr = data["w_tr"].copy()
    mask_w = data["mask_w"].copy().astype(bool)
    xc = data["xc_w"].copy()

    n_total = len(T_e)
    valid_count = int(np.sum(mask_w))

    log.info("  Total points: %d, valid (mask_w): %d", n_total, valid_count)
    log.info("  T_e range: [%.2f, %.2f] K", float(np.nanmin(T_e)), float(np.nanmax(T_e)))
    log.info("  M_e range: [%.4f, %.4f]", float(np.nanmin(M_e)), float(np.nanmax(M_e)))
    log.info("  w_tr range: [%.4f, %.4f]", float(np.nanmin(w_tr)), float(np.nanmax(w_tr)))

    result = compute_adiabatic_wall_temperature(
        T_e=T_e,
        M_e=M_e,
        Pr=PR,
        gamma_air=GAMMA_AIR,
        w_tr=w_tr,
        valid_mask=mask_w,
    )

    log.info("  Taw_lam range: [%.2f, %.2f] K",
             float(np.nanmin(result["Taw_lam"])), float(np.nanmax(result["Taw_lam"])))
    log.info("  Taw_turb range: [%.2f, %.2f] K",
             float(np.nanmin(result["Taw_turb"])), float(np.nanmax(result["Taw_turb"])))
    log.info("  Taw range: [%.2f, %.2f] K",
             float(np.nanmin(result["Taw"])), float(np.nanmax(result["Taw"])))
    log.info("  T0_edge range: [%.2f, %.2f] K",
             float(np.nanmin(result["T0_edge"])), float(np.nanmax(result["T0_edge"])))

    valid = result["valid_mask"]
    for check_name, check_val in result["checks"].items():
        status = "PASS" if check_val else "FAIL"
        log.info("  Check %s: %s", check_name, status)

    overall = result["all_pass"]
    log.info("  Overall range checks: %s", "PASS" if overall else "FAIL")

    case_dir = SANDBOX / "step_baseline" / case_name
    case_dir.mkdir(parents=True, exist_ok=True)

    taw_fields = {
        "Taw": result["Taw"],
        "Taw_lam": result["Taw_lam"],
        "Taw_turb": result["Taw_turb"],
        "r_eff": result["r_eff"],
        "r_lam": result["r_lam"],
        "r_turb": result["r_turb"],
        "T_e": T_e,
        "M_e": M_e,
        "T0_edge": result["T0_edge"],
        "w_tr": w_tr,
        "valid_mask": result["valid_mask"],
    }

    np.savez(case_dir / "taw_fields.npz", **taw_fields)
    log.info("  Saved taw_fields.npz")

    fv = valid

    summary = {
        "case": case_name,
        "input_fields": ["T_e_w", "ma_e_w", "w_tr", "mask_w"],
        "pr": PR,
        "gamma_air": GAMMA_AIR,
        "valid_count": int(np.sum(fv)),
        "nan_count": int(np.sum(~fv)),
        "T_e": {
            "min": float(np.min(T_e[fv])),
            "mean": float(np.mean(T_e[fv])),
            "max": float(np.max(T_e[fv])),
        },
        "M_e": {
            "min": float(np.min(M_e[fv])),
            "mean": float(np.mean(M_e[fv])),
            "max": float(np.max(M_e[fv])),
        },
        "Taw_lam": {
            "min": float(np.min(result["Taw_lam"][fv])),
            "mean": float(np.mean(result["Taw_lam"][fv])),
            "max": float(np.max(result["Taw_lam"][fv])),
        },
        "Taw_turb": {
            "min": float(np.min(result["Taw_turb"][fv])),
            "mean": float(np.mean(result["Taw_turb"][fv])),
            "max": float(np.max(result["Taw_turb"][fv])),
        },
        "Taw": {
            "min": float(np.min(result["Taw"][fv])),
            "mean": float(np.mean(result["Taw"][fv])),
            "max": float(np.max(result["Taw"][fv])),
        },
        "T0_edge": {
            "min": float(np.min(result["T0_edge"][fv])),
            "mean": float(np.mean(result["T0_edge"][fv])),
            "max": float(np.max(result["T0_edge"][fv])),
        },
        "r_eff": {
            "min": float(np.min(result["r_eff"][fv])),
            "mean": float(np.mean(result["r_eff"][fv])),
            "max": float(np.max(result["r_eff"][fv])),
        },
        "r_lam": float(np.sqrt(PR)),
        "r_turb": float(PR ** (1.0 / 3.0)),
        "range_check": result["checks"],
        "mask_consistency": result["checks"]["taw_nan_mask_matches_valid"],
        "final": "PASS" if overall else "FAIL",
    }

    with open(case_dir / "taw_summary.json", "w") as fp:
        json.dump(summary, fp, indent=2, ensure_ascii=False)
    log.info("  Saved taw_summary.json")

    rmasks = compute_region_masks(xc, valid)
    region_rows = []
    for rname, rm in rmasks.items():
        row: dict = {"region": rname}
        row["valid_count"] = int(np.sum(rm))
        for field_name, field_key in [
            ("Taw_lam_mean", "Taw_lam"),
            ("Taw_turb_mean", "Taw_turb"),
            ("Taw_mean", "Taw"),
            ("T0_edge_mean", "T0_edge"),
            ("r_eff_mean", "r_eff"),
        ]:
            vals = np.asarray(result[field_key], dtype=float).reshape(-1)[rm]
            row[field_name] = float(np.mean(vals)) if len(vals) > 0 else None
        region_rows.append(row)

    region_csv = SANDBOX / "step_baseline" / case_name / "region_taw_metrics.csv"
    import csv
    with open(region_csv, "w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=[
            "region", "valid_count",
            "Taw_lam_mean", "Taw_turb_mean", "Taw_mean",
            "T0_edge_mean", "r_eff_mean",
        ])
        writer.writeheader()
        writer.writerows(region_rows)
    log.info("  Saved region_taw_metrics.csv")

    return summary


def check_frozen_src() -> list[str]:
    failures = []
    for rel_path, expected in FROZEN_SRC_MD5.items():
        p = BASE / rel_path
        if not p.exists():
            failures.append(f"MISSING: {rel_path}")
            continue
        actual = md5_hex(p)
        if actual != expected:
            failures.append(
                f"MD5 MISMATCH: {rel_path}  expected={expected}  actual={actual}"
            )
    return failures


def main():
    log.info("=" * 60)
    log.info("Phase 5-A-P1: Taw prototype start")
    log.info("Sandbox: %s", SANDBOX)
    log.info("Baseline snapshot: %s", SNAPSHOT_DIR)
    log.info("")

    log.info("Preflight: frozen src MD5 check")
    src_failures = check_frozen_src()
    if src_failures:
        for f in src_failures:
            log.error("  %s", f)
        log.error("FROZEN SRC MD5 CHECK FAILED — STOP")
        sys.exit(1)
    log.info("  All frozen src MD5 match — PASS")

    log.info("Preflight: dhawan_narasimha in specs/")
    dhawan_files = list((BASE / "specs").rglob("*dhawan*narasimha*"))
    if dhawan_files:
        log.error("  dhawan_narasimha FOUND in specs: %s", dhawan_files)
        log.error("SPECS PURITY CHECK FAILED — STOP")
        sys.exit(1)
    log.info("  No dhawan_narasimha in specs/ — PASS")

    log.info("Preflight: ma8_a10_h50km NOT touched")
    log.info("  ma8_a10_h50km is holdout — not included in CASES list")
    log.info("  Holdout integrity — PASS")

    log.info("")
    log.info("Processing active cases: %s", CASES)
    log.info("")

    summaries = {}
    for case_name in CASES:
        s = process_case(case_name)
        summaries[case_name] = s

    log.info("")
    log.info("=" * 60)
    log.info("Phase 5-A-P1 Taw prototype — OVERALL SUMMARY")
    log.info("")

    all_pass = True
    for case_name, s in summaries.items():
        final_tag = s["final"]
        is_pass = final_tag == "PASS"
        if not is_pass:
            all_pass = False
        log.info("  %s: %s", case_name, final_tag)
        for ck, cv in s["range_check"].items():
            log.info("    %s: %s", ck, "PASS" if cv else "FAIL")

    log.info("")
    if all_pass:
        log.info("OVERALL: PASS")
    else:
        log.error("OVERALL: FAIL — see per-case range checks above")

    return 0 if all_pass else 1


if __name__ == "__main__":
    SANDBOX.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(LOG_DIR / "phase5a_adiabatic_taw_prototype.log", mode="w")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(fh)

    sys.exit(main())
