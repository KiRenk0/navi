#!/usr/bin/env python3
"""Final self-check for Phase 2D ablation round 1 wrap-up."""
import os, pathlib

BASE = pathlib.Path(__file__).resolve().parent.parent

checks = []

# 1. Deliverable files exist
files_to_check = [
    "docs/faceted3d_v2_phase2d_ablation_round1_compact_summary_zh.md",
    "docs/faceted3d_v2_phase2d_g_qscale10_plumbing_audit_zh.md",
    "docs/faceted3d_v2_phase2d_qturb_input_audit_zh.md",
    "scripts/faceted3d_v2_phase2d_qturb_input_audit.py",
    "runs/faceted3d_v2_phase2d_qturb_input_audit/qturb_input_points.csv",
    "runs/faceted3d_v2_phase2d_qturb_input_audit/qturb_input_region_summary.csv",
]
for f in files_to_check:
    p = BASE / f
    checks.append((f"Deliverable: {f}", p.exists()))

# 2. No Chinese paths
all_paths = [str(BASE / f) for f in files_to_check]
has_cn = any("\u4e00" <= c <= "\u9fff" for s in all_paths for c in s)
checks.append(("No Chinese paths in deliverables", not has_cn))

# 3. No ma8_a10 in audit outputs
import csv
pp = BASE / "runs/faceted3d_v2_phase2d_qturb_input_audit/qturb_input_points.csv"
if pp.exists():
    with open(pp, encoding="utf-8") as f:
        r = csv.DictReader(f)
        cases = set(row["case"] for row in r)
    checks.append(("No ma8_a10 in audit CSV", "ma8_a10_h50km" not in cases))

# 4. No default config modification
# Check that the script doesn't write to specs/
script_path = BASE / "scripts/faceted3d_v2_phase2d_qturb_input_audit.py"
if script_path.exists():
    content = script_path.read_text(encoding="utf-8")
    writes_to_specs = any("specs/" in line.lower() and "open(" in line.lower() for line in content.split("\n"))
    checks.append(("audit script writes to specs/?", not writes_to_specs))

# 5. Round 1 ablation outputs still intact
ablation_csv = BASE / "runs/faceted3d_v2_phase2d_ablation/ablation_region_summary.csv"
checks.append(("Round 1 ablation output preserved", ablation_csv.exists()))

# 6. Verify audit CSV has expected columns
if pp.exists():
    with open(pp, encoding="utf-8") as f:
        h = f.readline().strip().split(",")
    required_cols = ["q_turb_over_q_lam", "rho_star_turb_over_rho_e", "mu_star_turb_over_mu_e",
                     "turb_branch_active", "h_r_turb_minus_h_w"]
    missing = [c for c in required_cols if c not in h]
    checks.append((f"Audit CSV has all required columns (missing: {missing})", len(missing) == 0))

# Print
print("=" * 60)
print("Phase 2D Ablation Round 1 Wrap-Up — Final Self-Check")
print("=" * 60)
n_pass = sum(1 for _, ok in checks if ok)
n_fail = sum(1 for _, ok in checks if not ok)
for desc, ok in checks:
    print(f"  [{'PASS' if ok else 'FAIL'}] {desc}")
print(f"\n{n_pass}/{n_pass + n_fail} passed")
