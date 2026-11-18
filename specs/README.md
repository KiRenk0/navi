# Active specifications

All active `n8_taw_*.yaml` cases reference
`vehicles/htv2_faceted3d_0920.yaml`. That vehicle spec binds the formal 0920
STL and outline under `data/geometry/0920/`. The STL owns surface geometry and
the outline owns the planform boundary/chord. The direct upper/lower slopes are
retained only as explicit reference/fallback normals. Duplicate root-chord and
sweep metadata are intentionally absent.

The vehicle spec contains no pressure-model selector or empirical Cp constants.
The production chain always uses the code-owned modified-Newtonian closure with
the actual Mach number and signed 3D outward-normal incidence. Retired
`cp_model`, `cp_newtonian_A`, `cp_newtonian_n`, and `edge_state` fields are
schema errors rather than compatibility options.

Case gas fields contain only `gamma` and `R_J_per_kgK`. `Cp(T)`, viscosity, and
conductivity are fixed by the Fluent-aligned material implementation, and the
local Prandtl number is derived from those properties. A constant `prandtl`
field is not accepted because it would not control the active recovery model.

`sampling/n8_taw_surface_grid_81x41.yaml` is the only active sampling schema.
It defines an `81 x 41` structured parameter grid for each geometric sheet;
the domain-conforming product then adds explicit skin/cap boundary nodes while
retaining source and interpolation identities.

`cases/n8_taw_c01.yaml` is the regression case (C01: 20 km, M10.983,
6.06 deg, T_inf 216.65 K, p_inf 5529.31 Pa). It reads the Fluent export
`fluent_export/adiabatic_wall_csv/fenqu1/fenqu1.csv` in place; the flow
condition comes from the case file, not from the export filename. Its raw
coordinate order is `x, up, span`, and its 76,892-point wall geometry matches
projection cache `14bd50b8...`. Batch runs (`scripts/build_lf_hf_baseline.py`)
use this file only as a template and need no per-case spec files.
Plot ranges are derived from valid comparison data and therefore are not
case-spec inputs.
