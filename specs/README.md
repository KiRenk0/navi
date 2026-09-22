# Active specifications

All active `n8_taw_*.yaml` cases reference
`vehicles/htv2_faceted3d_0920.yaml`. That vehicle spec binds the formal 0920
STL and outline under `data/geometry/0920/`. Direct slopes are the only facet
shape authority. `sampling/n8_taw_surface_grid_81x41.yaml` is the only active
sampling schema.

The active comparison case
`cases/n8_taw_ma5_a10_h60km.yaml` uses the Fluent source
`21.96pa_247.02k_60km_10alpha_5ma.csv`, whose raw coordinate order is
`x, up, span`; its projection cache is the active 0920 comparison cache.
