# Edge Pressure Breakdown — Ma8_a10_h50km

Busemann Cp=1.4300, Fluent Cp=0.2290, ratio=6.24x
Newtonian: Cp=0.9406*sin(phi)^2.419
|Model|Cp RMSE|Cp ratio|p_ratio|
|baseline_Busemann|1.2120|7.416|6.662|
|A_global_scale|0.1317|1.188|1.153|
|B_x_relaxation|0.1173|1.163|1.139|
|C_region_relax|0.1265|1.000|0.990|
|D_newtonian_fit|0.1332|1.078|1.056|
|E_linear_reg|0.1163|1.113|1.094|
