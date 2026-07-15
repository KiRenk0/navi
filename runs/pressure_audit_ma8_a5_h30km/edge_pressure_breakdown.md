# Edge Pressure Breakdown — Ma8_a5_h30km

Busemann Cp=0.4446, Fluent Cp=0.1301, ratio=3.42x
Newtonian: Cp=0.4014*sin(phi)^1.198
|Model|Cp RMSE|Cp ratio|p_ratio|
|baseline_Busemann|0.3380|5.167|4.092|
|A_global_scale|0.1093|1.512|1.337|
|B_x_relaxation|0.0918|1.373|1.270|
|C_region_relax|0.1008|1.000|0.970|
|D_newtonian_fit|0.1110|1.206|1.104|
|E_linear_reg|0.0916|1.267|1.183|
