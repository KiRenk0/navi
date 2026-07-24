# Faceted3D 文件索引

> 更新：2026-07-21（N3a candidate explicit-freestream provenance 工具与测试索引）

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
| `scripts/tools/` | `current_baseline_regression_check.py`（两套严格隔离职责：formal baseline v5 freeze/check 与 candidate manifest v1 generation）、`faceted3d_phase4b_geometry_qa.py`（正式双工况 geometry-only QA；第二工况在 canonical identity 后复用 projection）、`faceted3d_phase5a_fluent_clean_qa.py`（Phase 5A Fluent clean 正式 geometry-only QA）、`local_incidence_raw_facet_qa.py`（local-incidence 数值 QA 工具）、`local_incidence_alpha_scan.py`（四攻角 alpha coverage 扫描工具）、`export_faceted3d_fields_to_table.py`（字段导出） |
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

| 文件 | Filename identity |
|------|-------------------|
| `fluent_export/adiabatic_wall_csv/1197pa_226.509k_30km_3alpha_6.5ma.csv` | p=1197 Pa, T=226.509 K, nominal h=30 km, α=3°, Ma=6.5 |
| `fluent_export/adiabatic_wall_csv/1197pa_226.509k_30km_5alpha_6ma.csv` | p=1197 Pa, T=226.509 K, nominal h=30 km, α=5°, Ma=6；approved formal binding |
| `fluent_export/adiabatic_wall_csv/1197pa_226.509k_30km_5alpha_8ma.csv` | p=1197 Pa, T=226.509 K, nominal h=30 km, α=5°, Ma=8；supplemental-only |
| `fluent_export/adiabatic_wall_csv/558.9pa_237k_35km_8alpha_6.5ma.csv` | p=558.9 Pa, T=237 K, nominal h=35 km, α=8°, Ma=6.5 |
| `fluent_export/adiabatic_wall_csv/558.9pa_237k_35km_8alpha_9ma.csv` | p=558.9 Pa, T=237 K, nominal h=35 km, α=8°, Ma=9 |
| `fluent_export/adiabatic_wall_csv/287pa_251k_40km_10alpha_8ma.csv` | p=287 Pa, T=251 K, nominal h=40 km, α=10°, Ma=8 |
| `fluent_export/adiabatic_wall_csv/287pa_251k_40km_5alpha_6.5ma.csv` | p=287 Pa, T=251 K, nominal h=40 km, α=5°, Ma=6.5 |
| `fluent_export/adiabatic_wall_csv/287pa_251k_40km_5alpha_8ma.csv` | p=287 Pa, T=251 K, nominal h=40 km, α=5°, Ma=8；approved formal binding |
| `fluent_export/adiabatic_wall_csv/287pa_251k_40km_5alpha_9ma.csv` | p=287 Pa, T=251 K, nominal h=40 km, α=5°, Ma=9 |
| `fluent_export/adiabatic_wall_csv/131pa_241.65k_45km_10alpha_8ma.csv` | p=131 Pa, T=241.65 K, nominal h=45 km, α=10°, Ma=8；unregistered candidate |
| `fluent_export/adiabatic_wall_csv/131pa_241.65k_45km_5alpha_8ma.csv` | p=131 Pa, T=241.65 K, nominal h=45 km, α=5°, Ma=8；unregistered candidate |
| `fluent_export/adiabatic_wall_csv/131pa_241.65k_45km_5alpha_9ma.csv` | p=131 Pa, T=241.65 K, nominal h=45 km, α=5°, Ma=9；unregistered candidate |

Filename 中的 P/T 是 historical user-defined comparison input；nominal altitude 仅为历史标签，`atmosphere_model=none / unverified`，不得由高度替换 P/T。Parser 成功只证明当前 filename schema 可解析，不产生 formal admission。正式 registry 仅显式包含 M6/30 与 M8/40；M8/30 仅 supplemental，三个 45 km 输入仅获准做 filename/raw identity 审计，不自动进入 N6.1 matrix 或 formal registry。N6.2 formal package 尚未执行。`ma8_a10_h50km` 仍为独立 legacy stress/reference 文件。

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
| `tests/test_tpg_candidate_manifest.py` | candidate schema identity、显式 case identity、hash 核心复用、路径隔离、拒绝覆盖、原子发布、v5 零漂移及 freeze/check/solver 隔离合同 |
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

## 11. Phase 4A Projected Geometry Semantics 最终资产

| 路径 | 说明 |
|------|------|
| `src/ref_enthalpy_method/geometry/projected_semantics.py` | projected-point raw semantics 纯层；组合 sheet、outward normal、incidence 与 projected `x/c`、`y/b`，保持输入顺序并返回 owned、C-order、read-only 数组 |
| `src/ref_enthalpy_method/geometry/qchain_surface.py` | q-chain surface acceptance 单源；闭区间接受 `normal angle<=20°` 且 `abs(n_z)>=0.45` |
| `src/ref_enthalpy_method/geometry/stl_surface.py` | `SurfaceSlopeSampler` 正式 triangle selection 与 sheet identity；保留 `sample_upper_lower()` 六字段合同，新方法额外返回 triangle ID |
| `src/ref_enthalpy_method/geometry/faceted3d.py` | outline 优先、triangle fallback 的共享 planform 参数化语义 |
| `tests/test_projected_geometry_semantics.py` | sheet、normal source、incidence、q-chain 边界、raw 参数和数组所有权/顺序合同 |
| `src/ref_enthalpy_method/solver_faceted3d.py` | 复用共享 q-chain acceptance 与 planform 语义；正式 pressure、edge-state、Taw 与热流数值链未改变 |

## 12. Fluent Geometry Exact-Projection 最终资产

| 路径 | 说明 |
|------|------|
| `src/ref_enthalpy_method/geometry/exact_projection.py` | exhaustive exact point-to-triangle 投影真值；覆盖 interior/edge/vertex/degenerate 与 deterministic tie-break |
| `src/ref_enthalpy_method/mapping/__init__.py` | mapping 包的正式公开入口 |
| `src/ref_enthalpy_method/mapping/fluent_surface.py` | strict Fluent geometry parser、显式 `+0.030 m` x-origin 与 canonical coordinate identity |
| `src/ref_enthalpy_method/mapping/fluent_projection.py` | canonical/source ordering 可逆的 exact projection adapter 与闭区间 5 mm gate |
| `tests/test_exact_surface_projection.py` | exact kernel 与 tie-break 单元合同 |
| `tests/test_fluent_surface_contract.py` | parser、坐标变换、identity 与重复坐标合同 |
| `tests/test_fluent_surface_projection.py` | adapter ordering、输出与 gate 合同 |

已删除 root `_analysis.py`、`_analysis2.py`：二者是包含旧绝对路径、固定 `k` centroid shortlist、cache 和 clean/temperature prototype 的历史实现，不是 active mapping implementation；内容仍可从 Git 历史恢复。

## 13. Phase 4B Fluent Projected Semantics Integration 最终资产

| 路径 | 说明 |
|------|------|
| `src/ref_enthalpy_method/mapping/fluent_semantics.py` | adapter：连接既有 exact projection 与既有 projected semantics，冻结 canonical ordering、projection identity fail-closed 与 raw geometry QA 合同 |
| `tests/test_fluent_projected_semantics_integration.py` | integration、ordering、fail-closed、array ownership 与 execution metadata 合同测试 |
| `scripts/tools/faceted3d_phase4b_geometry_qa.py` | 正式双工况 geometry-only QA runner；第二工况在 canonical geometry exact identity 后复用 projection，不执行温度 comparison，也不构造 clean |

## 14. Phase 5A Fluent Clean Leeward Contract 最终资产

| 路径 | 说明 |
|------|------|
| `src/ref_enthalpy_method/mapping/fluent_clean.py` | raw projected semantics 的只读派生 subset builder；保持 canonical ordering，输出 bool、owned、C-order、read-only arrays，并对输入合同 fail-closed；不读取温度，不执行 LF mapping |
| `src/ref_enthalpy_method/mapping/fluent_semantics.py` | projected semantics adapter 与公开 `semantic_valid_mask()` 单源；projection gate 与 planform validity 保持为独立合同 |
| `tests/test_fluent_clean.py` | semantic-valid、planform 闭区间、clean eligibility、sheet-specific masks、数组所有权与 fail-closed 合同测试 |
| `scripts/tools/faceted3d_phase5a_fluent_clean_qa.py` | Phase 5A 正式双工况 geometry-only QA；验证 canonical identity、projection reuse、clean arrays 与去 provenance JSON 的确定性 |

## 15. Phase 5B1 LF Clean Leeward Contract 最终资产

| 路径 | 说明 |
|------|------|
| `src/ref_enthalpy_method/mapping/lf_clean.py` | canonical LF 点上的 geometry/semantics-only 只读派生 subset；canonical coordinate identity fail-closed，不读取温度 |
| `tests/test_lf_clean.py` | LF clean predicate、结构门禁、sheet disjoint/union、数组所有权与 solver cache 隔离测试 |
| `scripts/tools/faceted3d_phase5b_lf_clean_qa.py` | Phase 5B1 正式双工况 geometry-only QA 与 lower-sheet branch shakeout |

## 16. Phase 5B2 Mapping Contract Audit

| 路径 | 说明 |
|------|------|
| `docs/audits/faceted3d_phase5b2_mapping_contract_audit_20260718.md` | 基于 `main@60e3473cc48d366671921ca246aaccf60f5a1fd1` 的关键结论与主要定量证据；包含 P/R/U 压缩统计、全部非空 4×4 bins、P/U 观察 gate curves 与双向各 20 条原画布现有 worst-point records，并明确未落库字段 |

Phase 5B2 当前只有只读 audit 结论：正式方向为 Fluent clean → LF clean，metric 为 exact-projected physical `(x, span)`，many-to-one allowed，不冻结 gate 或 edge buffer。尚无正式 pairing module、pairing tests 或 Phase 5B2 mapping QA runner；不得预写不存在的实现入口。

## 17. Canonical 文档入口收口

根目录旧诊断、旧 CLI 速查与旧流程说明已退出仓库；对应当前事实分别由 `docs/faceted3d_current_status_zh.md` / `docs/current_model_decisions_zh.md`、`docs/faceted3d_official_cli_run_guide_zh.md`、`README.md` / `docs/functional_baseline_contract.md` 单源维护。正式代码、CLI、baseline 与数据入口不变。

## 18. N3a Candidate Manifest Tooling

| 路径 | 说明 |
|------|------|
| `scripts/tools/current_baseline_regression_check.py` | formal baseline `current-tpg-baseline-regression/v5` freeze/check 与未注册 candidate `tpg-candidate-manifest/v1` generation 的共用工具；candidate-only 显式 freestream provenance 由成对可选参数接入，两种 manifest 身份与运行模式严格隔离 |
| `tests/test_tpg_candidate_manifest.py` | candidate schema/case identity、显式 freestream pair/summary/runner command provenance、非显式兼容、hash 复用、路径隔离、拒绝覆盖、原子发布、v5 零漂移及 freeze/check/solver 隔离测试 |

candidate CLI 必选参数为 `--candidate-manifest`、`--case-id`、`--mach`、`--alpha`、`--h-m`、`--run-dir`；成对可选 provenance 参数为 `--t-inf-k`、`--p-inf-pa`。两项必须同时提供或同时省略，且必须为有限正值。显式路径的 runner 复现命令使用正式 `--T_inf_K`、`--p_inf_Pa`，交叉校验 summary override/freestream/source 并记录 `atmosphere.explicit_freestream_override=true`；非显式路径保持 `false`。candidate 模式不运行 solver，不修改 `CASES`，不触碰 `current_baseline_snapshot` 或 `leeward_source_evidence`；只处理已存在 run，并拒绝覆盖既有 `manifest.json`。candidate 顶层字段与正式 v5 baseline、Groups 1–8、72-field contract 均未改变。
