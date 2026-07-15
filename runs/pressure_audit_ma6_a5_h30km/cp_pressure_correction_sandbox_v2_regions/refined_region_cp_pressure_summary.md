# Refined Region Cp/Pressure Summary

> Generated: 2026-06-29 00:46
> Mach=6.0, Alpha=5°, h=30km, Tw=300K

## Region definitions

| ID | Region | Rule | Rationale |
|----|--------|------|----------|
| 0 | true_nose_cap | x < 5*Rn (0.150m) AND span < 0.10m | Physical nose-cap region based on nose radius |
| 1 | forebody_center | x < 0.6m AND span < x/10 AND NOT nose_cap | Centerline behind cap, before main body expansion |
| 2 | leading_edge_near | span > x/6 AND NOT nose_cap | Points near the planform leading edge |
| 3 | wingtip | span > 85% max_span AND NOT nose_cap | Outermost wingtip region |
| 4 | aft_body | x > 2.4m AND NOT leading_edge AND NOT wingtip | Downstream body where pressure relaxation matters |
| 5 | windward_body | Everything else valid | Interior body points |

## Region-binned Cp / pressure error

| region | count | Cp_fluent | Cp_f3 | Cp_ratio | p_ratio | q_ratio | phi_deg |
|--------|-------|-----------|-------|----------|---------|---------|--------|
|      true_nose_cap |  3530 |    0.2045 |    0.4442 |     2.97 |    2.46 |    3.43 |  18.72 |
|  leading_edge_near |  5264 |    0.1082 |    0.4572 |     5.38 |    3.79 |    1.57 |  18.95 |
|           aft_body |   653 |    0.0566 |    0.4168 |     7.37 |    4.74 |    3.82 |  18.12 |
|      windward_body |   969 |    0.0583 |    0.4350 |     7.46 |    4.84 |    4.76 |  18.48 |

## Key answers

**true_nose_cap Cp ratio**: 2.97x — NO, less than 3x
  Fluent Cp=0.2045, Busemann Cp=0.4442
**leading_edge_near Cp ratio**: 5.38x
**windward_body Cp ratio**: 7.46x
**aft_body Cp ratio**: 7.37x

## Candidate model metrics (refined regions)

| Model | Cp RMSE | Cp MAE | Cp ratio | p RMSE | p MAE | p ratio |
|-------|---------|--------|----------|--------|-------|--------|
|    baseline_Busemann |  0.3381 |  0.3250 |    4.878 |    9980.6 |    9594.9 |   3.496 |
|       A_global_scale |  0.1090 |  0.0716 |    1.447 |    3216.8 |    2114.3 |   1.238 |
|       B_x_relaxation |  0.0918 |  0.0608 |    1.334 |    2709.1 |    1793.7 |   1.206 |
|       C_region_relax |  0.1007 |  0.0550 |    1.000 |    2971.9 |    1625.1 |   0.963 |
|      D_newtonian_fit |  0.1105 |  0.0682 |    1.179 |    3260.8 |    2013.8 |   1.060 |
|         E_linear_reg |  0.0923 |  0.0533 |    1.235 |    2725.3 |    1574.9 |   1.133 |

**Best Cp RMSE**: B_x_relaxation (0.0918)
**Best p_ratio**: C_region_relax (0.963)

Region-relax vs x-relax: C RMSE=0.1007 vs B RMSE=0.0918 → B better

## Newtonian fit parameters

`Cp = A * sin(phi)^n` → A=0.3748, n=1.099
