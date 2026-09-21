# Current calculation chain

The only production contract is 0920 geometry, fully turbulent flow, and
adiabatic wall temperature (Taw).

```text
scripts/run_n8_taw_case.py
  -> specs/cases/n8_taw_*.yaml
  -> specs/vehicles/htv2_faceted3d_0920.yaml
  -> data/geometry/0920/htv2_0920_aligned_clean_ascii.stl
  -> data/geometry/0920/outline_xz_right_0920.csv
  -> baselines/0920_fully_turbulent_taw/projection_cache/
  -> src/ref_enthalpy_method/n8_taw_surface.py
  -> fully turbulent TPG Taw field
  -> summary.json / Taw_surface_fields.npz / plots
```
