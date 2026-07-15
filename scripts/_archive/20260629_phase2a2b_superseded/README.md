# 20260629 Phase 2A/2B Historical Exploration Scripts

**Status: SUPERSEDED**

These scripts belong to the Phase 2A/2B engineering exploration phase.
Their conclusions have been revised by Phase 2D diagnostic findings:

- **Phase 2A (smoothstep transition)**: Implemented as experimental opt-in.
  Default remains `weighting: step`. Not a recommended default.

- **Phase 2A (Delta sweep)**: The original sweep analysis contained a
  `q_turb < q_lam` conclusion that was later corrected by the
  branch mixing audit. See `docs/...branch_mixing_audit_zh.md`.

- **Phase 2B-nose (x_eff floor)**: Audit showed max() selects q_cap
  (not q_flat). x_eff floor hypothesis is no-go.

- **Phase 2B-nose (max/q_cap comparison)**: The 11–13x q_cap/Fluent
  ratio was revised by Fluent alignment check (actual disparity vs
  cap_mask q_max is 1.2–1.3x).

**Do NOT use these scripts as current standard diagnostic tools.**
**Do NOT modify these scripts directly for ongoing work.**

For current standard diagnostics, see:
  `scripts/faceted3d_v2_phase2d_le_pressure_diagnostic.py`
  `scripts/faceted3d_v2_phase2d_capmask_nose_audit.py`

For region and metric standards:
  `docs/faceted3d_region_and_metric_standard_zh.md`
