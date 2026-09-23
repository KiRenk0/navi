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

The active comparison case
`cases/n8_taw_ma5_a10_h60km.yaml` uses the Fluent source
`21.96pa_247.02k_60km_10alpha_5ma.csv`, whose raw coordinate order is
`x, up, span`; its projection cache is the active 0920 comparison cache. Plot
ranges are derived from valid comparison data and therefore are not case-spec
inputs.
