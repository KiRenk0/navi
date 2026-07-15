# Edge Pressure Breakdown — Ma6_a5_h30km

Busemann Cp=0.4482, Fluent Cp=0.1330, ratio=3.37x
Newtonian: Cp=0.3748*sin(phi)^1.099
|Model|Cp RMSE|Cp ratio|p_ratio|
|baseline_Busemann|0.3381|4.878|3.496|
|A_global_scale|0.1090|1.447|1.238|
|B_x_relaxation|0.0918|1.334|1.206|
|C_region_relax|0.1007|1.000|0.963|
|D_newtonian_fit|0.1105|1.179|1.060|
|E_linear_reg|0.0923|1.235|1.133|
