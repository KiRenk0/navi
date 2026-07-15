"""Phase 3 regression check: default (step) vs T1 baseline snapshot."""
from __future__ import annotations
import sys, warnings
from pathlib import Path
import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(r"D:\ref\reference-enthalpy_03_12_26-main") / "src"))

from ref_enthalpy_method.solver_faceted3d import WingLowFidelitySolverFaceted3D

BASE = Path(r"D:\ref\reference-enthalpy_03_12_26-main")
SAMPLING = str(BASE / "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml")
SNAPSHOT_DIR = BASE / "runs/0630_phase2d_c1_dn/baseline_snapshot"
CASE_SPECS = {
    "ma6_a5_h30km": {"mach": 6.0, "alpha": 5.0, "h_m": 30000},
    "ma8_a5_h30km": {"mach": 8.0, "alpha": 5.0, "h_m": 30000},
}

TARGET_FIELDS = [
    "q_w", "w_tr", "q_lam_w", "q_turb_w",
    "re_edge", "re_tri", "re_x_star",
    "p_e_w", "ma_e_w", "v_e_w", "mu_e_w",
    "phi_w", "cp_w", "cp0_w",
]

all_ok = True
for case_id, spec in CASE_SPECS.items():
    veh_path = str(BASE / f"runs/faceted3d_v2_phase2d_diagnostics/veh_{case_id}.yaml")
    case_path = str(BASE / f"runs/faceted3d_v2_phase2d_diagnostics/case_{case_id}.yaml")

    print(f"[{case_id}] Running default step solver ...")
    solver = WingLowFidelitySolverFaceted3D(
        vehicle_config=veh_path,
        case_config=case_path,
        sampling_config=SAMPLING,
        run_dir=str(BASE / "runs/tmp_phase3_regression"),
    )
    solver.compute_snapshot(mach=float(spec["mach"]), alpha=float(spec["alpha"]))
    fields = dict(solver.last_fields or {})

    baseline = np.load(str(SNAPSHOT_DIR / case_id / "fields.npz"))

    for key in TARGET_FIELDS:
        if key not in fields or key not in baseline:
            print(f"  SKIP: {key} not in both")
            continue
        a = np.asarray(fields[key], dtype=float).ravel()
        b = np.asarray(baseline[key], dtype=float).ravel()
        mask = np.isfinite(a) & np.isfinite(b)
        if not np.any(mask):
            print(f"  {key}: no finite values to compare")
            continue
        diff = np.abs(a[mask] - b[mask])
        max_diff = float(np.max(diff))
        mean_diff = float(np.mean(diff))
        ok = max_diff <= 1e-9
        if not ok:
            all_ok = False
        label = "OK" if ok else "FAIL"
        print(f"  {key}: max_diff={max_diff:.2e}, mean_diff={mean_diff:.2e} [{label}]")

print()
print("=" * 60)
print("REGRESSION: ALL PASS" if all_ok else "REGRESSION: SOME FAILURES")
print("=" * 60)
sys.exit(0 if all_ok else 1)
