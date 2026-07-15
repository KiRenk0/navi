# Faceted3D 文件索引

> 更新：2026-07-15（leeward freestream-recovery diagnostic 收口）

---

## 1. scripts/ 结构

顶层只保留正式运行入口：

| 文件 | 说明 |
|------|------|
| `scripts/run_case_rem.py` | official CLI，主运行入口，通过 `--mach --alpha --h_m` 显式指定工况 |
| `scripts/run_case_sweep.py` | sweep wrapper（多工况批量） |

分类子目录：

| 目录 | 内容 |
|------|------|
| `scripts/geometry/` | `prepare_geometry.py`（几何输入检查器）、`extract_outline_from_stl.py` |
| `scripts/viz/` | `viz_error_cloud_readonly.py`（3D 误差散点）、`plot_windward_error_vs_fluent.py`（迎风面 `Taw_tpg_w` vs Fluent 绝热壁 Tw 相对误差%云图半模投影，弦向-展向，只读 diagnostic visualization；Fluent 迎风面按 z<0 压缩侧筛选，映射沿用 LF(x_w_m,span_w_m)→Fluent(x,y) 最近邻；**不替代 P2R2 corrected comparison canon、不代表 validation complete、不涉及 leeward temperature error**）、`plot_root_chord_temperature_from_run_rem.py`、`plot_wing_surface_temperature_from_run_rem.py` |
| `scripts/pressure/` | `pressure_audit.py`、`pressure_audit_plots.py`、`edge_pressure_breakdown.py`、`cp_pressure_correction_sandbox.py`（pressure/Cp 审计） |
| `scripts/tools/` | `current_baseline_regression_check.py`（唯一 current regression harness，仅 TPG 两工况）、`local_incidence_raw_facet_qa.py`（local-incidence 数值 QA 工具）、`local_incidence_alpha_scan.py`（四攻角 alpha coverage 扫描工具）、`export_faceted3d_fields_to_table.py`（字段导出） |
| `scripts/_archive/20260709_scripts_top_prune/` | 已完成阶段的 diagnostic / audit / ablation 脚本（非 active） |

Route A-TPG 是**唯一正式且唯一可运行**的 thermodynamic baseline；CLI 无 thermo 选择。当前不声明 validation complete。

## 2. Vehicle

| 文件 | 说明 |
|------|------|
| `specs/vehicles/htv2_faceted3d_0629.yaml` | 当前主 vehicle，cp_model 已显式冻结 |

## 3. Case Template

| 文件 | 说明 |
|------|------|
| `specs/cases/doc_ma6_alpha5_h30km_faceted3d.yaml` | case 模板，工况参数由 CLI 覆盖 |

## 4. Sampling

| 文件 | 说明 |
|------|------|
| `specs/sampling/engineering_full_wing_surface_grid_81x41.yaml` | 81×41 维度不变；endpoint regularization 后 windward/leeward 各 3321 点有效；合法零弦长尖端 sliver 不采样 |

## 5. Geometry

| 文件 | 说明 |
|------|------|
| `new_spec/htv2_0628.stl` | HTV2 半模表面三角网格（ASCII STL，单位 mm） |
| `new_spec/outline_xz_right_0629.csv` | HTV2 半模 planform outline |

## 6. Fluent Adiabatic Wall CSV

| 文件 | 工况 |
|------|------|
| `fluent_export/adiabatic_wall_csv/30km_3alpha_6.5ma.csv` | h=30km, α=3°, Ma=6.5 |
| `fluent_export/adiabatic_wall_csv/30km_5alpha_6ma.csv` | h=30km, α=5°, Ma=6 |
| `fluent_export/adiabatic_wall_csv/30km_5alpha_8ma.csv` | h=30km, α=5°, Ma=8 |
| `fluent_export/adiabatic_wall_csv/35km_8alpha_6.5ma.csv` | h=35km, α=8°, Ma=6.5 |
| `fluent_export/adiabatic_wall_csv/35km_8alpha_9ma.csv` | h=35km, α=8°, Ma=9 |
| `fluent_export/adiabatic_wall_csv/40km_5alpha_8ma.csv` | h=40km, α=5°, Ma=8 |
| `fluent_export/adiabatic_wall_csv/40km_10alpha_8ma.csv` | h=40km, α=10°, Ma=8 |

所有 CSV: 21250 faces, 9 columns, adiabatic wall (heat-flux ≈ 0)。使用 corrected air transport property。这 7 个均为 corrected seven-case comparison 工况。`ma8_a10_h50km` 为独立文件 `fluent_export/ma8_alpha10_h50km.csv`（formal 域外 reserved legacy stress/reference case，不用于拟合）。

## 7. Thermodynamics / Taw Helper

| 文件 | 说明 |
|------|------|
| `src/ref_enthalpy_method/gas/thermo.py` | 唯一正式 TPG 热力学源：Cp(T) 表 h/s0/γ/a 单源 |
| `src/ref_enthalpy_method/aero/adiabatic_wall_temp.py` | Route A windward Taw 计算纯函数 |
| `src/ref_enthalpy_method/aero/leeward_recovery.py` | sheet-specific leeward freestream edge-state 与 TPG Taw diagnostic 纯 provider；raw class mask、mask 外 NaN |

## 8. 关键 src（不改）

| 文件 | 状态 |
|------|------|
| `src/ref_enthalpy_method/solver_faceted3d.py` | 可改 |
| `src/ref_enthalpy_method/aero/windward_cache_faceted3d.py` | 可改 |
| `src/ref_enthalpy_method/aero/busemann.py` | 可改（Cp 模型） |
| `src/ref_enthalpy_method/geometry/local_incidence.py` | local-incidence 分类核心库（normal/s/class/source） |
| `tests/test_local_incidence.py` | local-incidence 单元测试（9 tests） |
| `tests/test_leeward_freestream_recovery.py` | freestream provider、mask、NaN、TPG recovery 与 sheet isolation 单元合同 |
| `tests/test_faceted3d_leeward_recovery_integration.py` | solver 内 upper/lower 接线、18 字段与 legacy 解耦合同 |
| `tests/test_faceted3d_leeward_recovery_serialization.py` | official CLI 72 字段、dtype/shape/count、byte-exact serialization 合同 |
| `src/ref_enthalpy_method/aero/edge_conditions.py` | 禁止改 |
| `src/ref_enthalpy_method/heatflux/windward.py` | 禁止改 |
| `src/ref_enthalpy_method/heatflux/leeward.py` | 禁止改 |
| `src/ref_enthalpy_method/heatflux/leading_edge.py` | 禁止改 |
| `src/ref_enthalpy_method/aero/transition.py` | 禁止改 |

## 9. Regression Baseline

| 路径 | 状态 |
|------|------|
| `runs/current_baseline_snapshot/tpg/` | 唯一 current baseline：TPG `ma6_a5_h30km`、`ma8_a5_h40km`；schema `current-tpg-baseline-regression/v5`，Groups 1–8 PASS，72 fields |

## 10. Local-Incidence 最终资产

| 路径 | 说明 |
|------|------|
| `src/ref_enthalpy_method/geometry/local_incidence.py` | 分类核心库 |
| `tests/test_local_incidence.py` | 单元测试（9 tests） |
| `scripts/tools/local_incidence_raw_facet_qa.py` | 数值 QA 工具 |
| `scripts/tools/local_incidence_alpha_scan.py` | 四攻角扫描工具 |
| `runs/local_incidence_alpha_scan/local_incidence_alpha_scan.json` | 正式扫描结果 |
| `runs/local_incidence_alpha_scan/epsilon_comparison_summary.png` | 汇总图 |

## 11. Leeward Freestream-Recovery 最终资产

| 路径 | 说明 |
|------|------|
| `src/ref_enthalpy_method/aero/leeward_recovery.py` | upper/lower 可复用的纯 provider |
| `tests/test_leeward_freestream_recovery.py` | provider 单元合同 |
| `tests/test_faceted3d_leeward_recovery_integration.py` | solver 集成合同 |
| `tests/test_faceted3d_leeward_recovery_serialization.py` | official CLI 序列化与 baseline v5 合同 |
