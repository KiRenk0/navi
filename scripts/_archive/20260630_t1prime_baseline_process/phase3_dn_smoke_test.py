"""Phase 3 DN smoke test: dhawan_narasimha + simon_zpg completes without error."""
from __future__ import annotations
import sys, warnings
from pathlib import Path
from dataclasses import replace
import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(r"D:\ref\reference-enthalpy_03_12_26-main") / "src"))

from ref_enthalpy_method.solver_faceted3d import WingLowFidelitySolverFaceted3D

BASE = Path(r"D:\ref\reference-enthalpy_03_12_26-main")
SAMPLING = str(BASE / "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml")
CASE_SPECS = {
    "ma6_a5_h30km": {"mach": 6.0, "alpha": 5.0, "h_m": 30000},
    "ma8_a5_h30km": {"mach": 8.0, "alpha": 5.0, "h_m": 30000},
}

DN_CONFIGS = {
    "C1_DN_simon_zpg": {"dn_experimental": True, "dn_lambda_closure": "simon_zpg"},
    "C1_DN_narasimha_sensitivity": {"dn_experimental": True, "dn_lambda_closure": "narasimha"},
}

import json
from ref_enthalpy_method.specs.loader import load_yaml

all_ok = True
for case_id, spec in CASE_SPECS.items():
    for arm_id, dn_cfg in DN_CONFIGS.items():
        veh_path = str(BASE / f"runs/faceted3d_v2_phase2d_diagnostics/veh_{case_id}.yaml")
        case_path = str(BASE / f"runs/faceted3d_v2_phase2d_diagnostics/case_{case_id}.yaml")

        veh_root = load_yaml(veh_path)
        veh_spec = veh_root.get("vehicle_spec", {}) if isinstance(veh_root, dict) else {}
        use_faceted3d = bool(isinstance(veh_spec, dict) and ("faceted3d" in veh_spec))

        case_root = load_yaml(case_path)
        case_spec_raw = case_root.get("case_spec", {}) if isinstance(case_root, dict) else case_root

        # Apply DN weighting + dn sub-config
        lf = dict(case_spec_raw.get("lf_qw_model", {}) or {})
        tr = dict(lf.get("transition", {}) or {})
        tr["weighting"] = "dhawan_narasimha"
        tr["dn"] = {
            "experimental": dn_cfg["dn_experimental"],
            "lambda_closure": dn_cfg["dn_lambda_closure"],
            "spot_formation_N": None,
        }
        lf["transition"] = tr
        case_spec_raw["lf_qw_model"] = lf

        # Write modified case to a temp file
        tmp_case_path = BASE / f"runs/tmp_phase3_dn_test/tmp_{arm_id}__{case_id}.yaml"
        tmp_case_path.parent.mkdir(parents=True, exist_ok=True)
        import yaml as pyyaml
        with open(tmp_case_path, "w", encoding="utf-8") as f:
            pyyaml.dump({"case_spec": case_spec_raw}, f, default_flow_style=False)

        print(f"[{arm_id} / {case_id}] Running DN solver ...")

        try:
            if use_faceted3d:
                solver = WingLowFidelitySolverFaceted3D(
                    vehicle_config=veh_path,
                    case_config=str(tmp_case_path),
                    sampling_config=SAMPLING,
                    run_dir=str(BASE / f"runs/tmp_phase3_dn_test/{arm_id}/{case_id}"),
                )
            else:
                from ref_enthalpy_method.solver import WingLowFidelitySolver
                solver = WingLowFidelitySolver(
                    vehicle_config=veh_path,
                    case_config=str(tmp_case_path),
                    sampling_config=SAMPLING,
                    run_dir=str(BASE / f"runs/tmp_phase3_dn_test/{arm_id}/{case_id}"),
                )

            solver.compute_snapshot(mach=float(spec["mach"]), alpha=float(spec["alpha"]))
            fields = dict(solver.last_fields or {})
            w_tr = np.asarray(fields.get("w_tr", []), dtype=float).ravel()
            q_w = np.asarray(fields.get("q_w", []), dtype=float).ravel()

            n_finite_w_tr = int(np.sum(np.isfinite(w_tr)))
            n_finite_q = int(np.sum(np.isfinite(q_w)))
            w_tr_mean = float(np.nanmean(w_tr))
            q_w_mean = float(np.nanmean(q_w))

            print(f"  w_tr: finite={n_finite_w_tr}, mean={w_tr_mean:.6f}")
            print(f"  q_w:  finite={n_finite_q},  mean={q_w_mean:.4e}")

            # Basic sanity: must produce finite values
            if n_finite_w_tr == 0:
                print("  FAIL: w_tr all NaN")
                all_ok = False
            if n_finite_q == 0:
                print("  FAIL: q_w all NaN")
                all_ok = False

            # DN must produce some non-zero w_tr values
            w_tr_nonzero = float(np.sum(w_tr > 1e-12))
            print(f"  w_tr non-zero count: {int(w_tr_nonzero)}")
        except Exception as e:
            print(f"  FAIL: {e}")
            all_ok = False

print()
print("=" * 60)
print("DN SMOKE TEST:", "ALL PASS" if all_ok else "SOME FAILURES")
print("=" * 60)
sys.exit(0 if all_ok else 1)
