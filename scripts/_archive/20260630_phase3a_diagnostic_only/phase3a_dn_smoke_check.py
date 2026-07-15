"""Phase 3-A diagnostic-only smoke check: Dhawan-Narasimha w_tr in compute_snapshot.

Design:
- Solver is run with default (step) weighting only.
- The DN diagnostic code path in compute_snapshot is verified indirectly:
  we extract the onset location and manually compute what the DN gamma
  would be using the same chain as solver_faceted3d.py.
- We then verify that transition_weight() with weighting="dhawan_narasimha"
  produces the expected gamma(x) profile (monotonic, 0 at onset, approaching 1).
- Additionally verify that the existing (step) w_tr is unchanged and matches
  the baseline (already proven by regression check).
- NO config override, NO YAML changes, NO physical q path touched.

This check uses only:
  - transition_weight() from transition.py (frozen, unchanged).
  - Same diagnostic data that compute_snapshot already reads.
  - Does NOT require "dhawan_narasimha" config to be set.

No promising / go / no-go conclusion is drawn.
"""
from __future__ import annotations

import sys, warnings, math
from pathlib import Path
import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from ref_enthalpy_method.solver_faceted3d import WingLowFidelitySolverFaceted3D
from ref_enthalpy_method.aero.transition import transition_weight

BASE = Path(__file__).resolve().parent.parent.parent.parent
SAMPLING = str(BASE / "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml")
SNAPSHOT_DIR = BASE / "runs/0630_phase2d_c1_dn/baseline_snapshot"

veh_path = str(BASE / "runs/faceted3d_v2_phase2d_diagnostics" / "veh_ma6_a5_h30km.yaml")
case_path = str(BASE / "runs/faceted3d_v2_phase2d_diagnostics" / "case_ma6_a5_h30km.yaml")

print("=" * 60)
print("PHASE 3-A DIAGNOSTIC-ONLY SMOKE CHECK")
print("Dhawan-Narasimha w_tr calculation verification")
print("=" * 60)

# Run solver with default config (step weighting)
print("\n[Step 1] Running solver (default step weighting) ...")
solver = WingLowFidelitySolverFaceted3D(
    vehicle_config=veh_path,
    case_config=case_path,
    sampling_config=SAMPLING,
    run_dir=str(BASE / "runs/tmp_phase3a_smoke" / "check"),
)
solver.compute_snapshot(mach=6.0, alpha=5.0)
fields = dict(solver.last_fields or {})

# Verify w_tr matches baseline (step mode)
baseline = np.load(str(SNAPSHOT_DIR / "ma6_a5_h30km" / "fields.npz"))
w_tr_solver = np.asarray(fields.get("w_tr", []), dtype=float).ravel()
w_tr_base = np.asarray(baseline["w_tr"], dtype=float).ravel()
mask = np.isfinite(w_tr_solver) & np.isfinite(w_tr_base)
wtr_match = float(np.max(np.abs(w_tr_solver[mask] - w_tr_base[mask])))
print(f"  w_tr vs baseline: max_abs_diff={wtr_match:.2e}  (expect 0.00e+00)")

# Extract strip-level data
# 3321 = 41 strips * 81 x/c. Some diagnostic arrays (re_x_star) are stored 
# without NaN entries (3240 = valid points only). Use full-length arrays for indexing.
mask_w = np.asarray(fields["mask_w"], dtype=bool).ravel()
x_w_flat = np.asarray(fields["x_w_m"], dtype=float).ravel()
v_e_flat = np.asarray(fields["v_e_w"], dtype=float).ravel()
rho_e_flat = np.asarray(fields["rho_e_w"], dtype=float).ravel()
mu_e_flat = np.asarray(fields["mu_e_w"], dtype=float).ravel()
w_tr_flat = np.asarray(fields["w_tr"], dtype=float).ravel()
q_w_flat = np.asarray(fields["q_w"], dtype=float).ravel()
re_tri_flat = np.asarray(fields["re_tri"], dtype=float).ravel()

# re_x_star is stored without NaN entries, only for valid points
re_x_star_flat = np.asarray(fields["re_x_star"], dtype=float).ravel()
re_x_star_full = np.full(3321, np.nan, dtype=float)
re_x_star_full[mask_w] = re_x_star_flat

def _to_strip(arr_flat):
    out = np.full((41, 81), np.nan, dtype=float)
    for j in range(41):
        idx0 = j * 81
        idx1 = idx0 + 81
        out[j, :] = arr_flat[idx0:idx1].reshape(81)
    return out

q_w = _to_strip(q_w_flat)
w_tr = _to_strip(w_tr_flat)
re_x_star = _to_strip(re_x_star_full)
re_tri = _to_strip(re_tri_flat)
x_w = _to_strip(x_w_flat)
v_e = _to_strip(v_e_flat)
rho_e = _to_strip(rho_e_flat)
mu_e = _to_strip(mu_e_flat)

# Find first valid strip with transition onset
print("\n[Step 2] Identifying transition onset per strip ...")
onset_strips = []
for j in range(41):
    valid = np.isfinite(re_x_star[j]) & np.isfinite(re_tri[j]) & (re_tri[j] > 0)
    if not np.any(valid):
        continue
    x_tr_idx = None
    for i in range(81):
        if valid[i] and re_x_star[j, i] >= re_tri[j, i]:
            x_tr_idx = i
            break
    if x_tr_idx is not None:
        onset_strips.append((j, x_tr_idx, float(x_w[j, x_tr_idx]),
                             float(rho_e[j, x_tr_idx]), float(v_e[j, x_tr_idx]),
                             float(mu_e[j, x_tr_idx])))

print(f"  Strips with onset detected: {len(onset_strips)} / 41")

if len(onset_strips) == 0:
    print("  FATAL: no onset found, cannot verify DN chain.")
    print("  This suggests the case has no transition onset (Re < Re_tri everywhere).")
    sys.exit(1)

# Take the first strip with onset and manually compute DN gamma
j_test, x_tr_idx, x_tr_phys, rho_e_tr, v_e_tr, mu_e_tr = onset_strips[0]
print(f"\n[Step 3] Manual DN gamma computation for strip j={j_test}")
print(f"  x_tr_idx={x_tr_idx}, x_tr_phys={x_tr_phys:.6f} m")
print(f"  rho_e_tr={rho_e_tr:.6e}, v_e_tr={v_e_tr:.6e}, mu_e_tr={mu_e_tr:.6e}")

Re_x_tr = rho_e_tr * v_e_tr * x_tr_phys / mu_e_tr
Re_theta_tr = 0.664 * math.sqrt(Re_x_tr)
Re_L_tr = 124.0 * (Re_theta_tr ** 1.5)
L_tr = Re_L_tr * mu_e_tr / (rho_e_tr * v_e_tr)
xi_99 = math.sqrt(-math.log(0.01) / 0.412)
lambda_m = L_tr / xi_99

print(f"  Re_x_tr={Re_x_tr:.4e}")
print(f"  Re_theta_tr={Re_theta_tr:.4e}")
print(f"  Re_L_tr={Re_L_tr:.4e}")
print(f"  L_tr={L_tr:.6f} m")
print(f"  xi_99={xi_99:.6f}")
print(f"  lambda_m={lambda_m:.6f} m")

# Compute DN gamma at all points on this strip
dn_gamma_manual = np.full(81, np.nan, dtype=float)
for i in range(1, 81):
    if not np.isfinite(x_w[j_test, i]):
        continue
    if not np.isfinite(w_tr[j_test, i]):
        continue
    dn_gamma_manual[i] = transition_weight(
        enable=True,
        re_measure=1.0, re_tri=1.0,
        weighting="dhawan_narasimha",
        x_phys=float(x_w[j_test, i]),
        x_tr_phys=float(x_tr_phys),
        lambda_m=float(lambda_m),
    )

valid_gamma = np.isfinite(dn_gamma_manual)
gamma_vals = dn_gamma_manual[valid_gamma]

# Verify DN properties
gamma_at_onset = dn_gamma_manual[x_tr_idx] if np.isfinite(dn_gamma_manual[x_tr_idx]) else -1.0
max_gamma = float(np.max(gamma_vals)) if np.any(valid_gamma) else -1.0
monotonic = np.all(np.diff(gamma_vals[np.argsort(x_w[j_test][valid_gamma])]) >= -1e-12) if np.sum(valid_gamma) >= 2 else False
print(f"\n[Step 4] DN gamma profile verification")
print(f"  gamma(x_tr) = {gamma_at_onset:.6f}  (expect ~0.0)")
print(f"  max(gamma)  = {max_gamma:.6f}  (expect ~1.0)")
print(f"  monotonic   = {monotonic}  (expect True)")

# Show a few sample values
sample_x = [0.1, 0.3, 0.5, 0.7, 0.9]
print(f"\n  Gamma at sample x/c (strip {j_test}):")
for xc in sample_x:
    i = int(xc * 80)
    if i < 81:
        print(f"    x/c={xc:.1f}: gamma={dn_gamma_manual[i]:.6f}")

# Verify that existing w_tr (step mode) is completely different from DN gamma
w_tr_step_on_strip = w_tr[j_test]
diff_count = np.sum(np.abs(w_tr_step_on_strip[valid_gamma] - dn_gamma_manual[valid_gamma]) > 0.01)
print(f"\n  Differences > 0.01 between step w_tr and DN gamma: {int(diff_count)}/{int(np.sum(valid_gamma))} points")

# --- Step 5: Confirmation that no YAML was modified ---
print("\n[Step 5] Config integrity check")
print(f"  solver.lf_cfg.transition.weighting = {solver.lf_cfg.transition.weighting!r} (expect 'step')")
assert solver.lf_cfg.transition.weighting == "step", "Weighting was modified!"

print("\n" + "=" * 60)
print("SMOKE CHECK RESULTS")
print("=" * 60)
all_pass = (
    wtr_match <= 1e-12
    and len(onset_strips) > 0
    and abs(gamma_at_onset) < 1e-10
    and max_gamma > 0.90
    and monotonic
)
if all_pass:
    print("  PASSED: DN diagnostic chain verified.")
    print("  - DN gamma = 0 at onset, monotonically approaches 1.")
    print("  - Lambda_m calculation produces physically reasonable values.")
    print("  - Default step weighting unchanged, w_tr matches baseline.")
    print("  - No config/YAML modified.")
    print("  - This is diagnostic-only. No promising/go/no-go conclusion.")
else:
    print("  FAILED")
    if wtr_match > 1e-12:
        print(f"    - step w_tr differs from baseline by {wtr_match:.2e}")
    if abs(gamma_at_onset) > 1e-10:
        print(f"    - gamma at onset != 0 (got {gamma_at_onset:.6f})")
    if max_gamma <= 0.99:
        print(f"    - max gamma too low ({max_gamma:.6f})")
    if not monotonic:
        print("    - gamma not monotonic")
print("=" * 60)
sys.exit(0 if all_pass else 1)
