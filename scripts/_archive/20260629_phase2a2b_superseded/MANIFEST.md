# Archive Manifest: 20260629_phase2a2b_superseded (Scripts)

Archive date: 2026-06-29
Previous location: `scripts/`
Operation: COPY (originals preserved for reference, not deleted)
Reason: Phase 2A/2B conclusions superseded by Phase 2D diagnostic findings.

| Original Path | Archived Path | Type | Status | Comment |
|---|---|---|---|---|
| `scripts/faceted3d_v2_phase2a_sandbox.py` | `scripts/_archive/20260629_phase2a2b_superseded/faceted3d_v2_phase2a_sandbox.py` | exploration_script | superseded | Phase 2A sandbox. smoothstep experimental, not default. |
| `scripts/faceted3d_v2_phase2a_delta_sweep.py` | `scripts/_archive/20260629_phase2a2b_superseded/faceted3d_v2_phase2a_delta_sweep.py` | exploration_script | superseded | Delta sweep. Contains q_turb<q_lam error (corrected by branch_mixing_audit). |
| `scripts/faceted3d_v2_phase2a_branch_mixing_audit.py` | `scripts/_archive/20260629_phase2a2b_superseded/faceted3d_v2_phase2a_branch_mixing_audit.py` | exploration_script | superseded | Branch mixing audit. Verified q = (1-w)*q_lam + w*q_turb is correct. |
| `scripts/faceted3d_v2_phase2b_nose_audit.py` | `scripts/_archive/20260629_phase2a2b_superseded/faceted3d_v2_phase2b_nose_audit.py` | exploration_script | superseded | Nose branch audit. x_eff floor hypothesis rejected. |

Active Phase 2D scripts (NOT archived):
- `scripts/faceted3d_v2_phase2d_le_pressure_diagnostic.py`
- `scripts/faceted3d_v2_phase2d_capmask_nose_audit.py`
