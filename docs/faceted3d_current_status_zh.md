# Faceted3D 当前工程状态

> 更新：2026-07-15（leeward freestream-recovery diagnostic 正式收口）

---

## 1. 当前阶段

Faceted3D v2。**正式高度参数域冻结为 20–40 km**。30、35、40 km 属于正式标准大气工况（USSA 1976，几何高度输入，内部位势高度换算）。7-case corrected Fluent comparison 与历史 CPG→TPG thermodynamic audit 已完成；Route A-TPG 是唯一正式且唯一可运行的 low-fidelity thermodynamic baseline，CLI 无 thermo 选择。

## 2. 冻结 baseline

- **vehicle**: `specs/vehicles/htv2_faceted3d_0629.yaml`
- **geometry**: `new_spec/htv2_0628.stl` + `new_spec/outline_xz_right_0629.csv`
- **cp_model**: `newtonian_like`, A=0.38, n=1.15（已在 vehicle YAML 显式冻结）
- **transition**: `weighting=step` 默认
- **x_length_mode**: `streamline`
- **effective_alpha**: on; **effective_mach**: off
- **DN**: experimental opt-in，默认不启用

## 3. Official CLI

`scripts/run_case_rem.py`，必须通过 `--mach / --alpha / --h_m` 显式指定工况。默认 geometry 来自 root `new_spec/`。

输出 `summary.json` 必须检查 `actual_mach` / `actual_alpha` / `actual_h_m` / `actual_cp_model` / `actual geometry paths`。

## 4. 七工况 Fluent 绝热壁面 CSV

`fluent_export/adiabatic_wall_csv/` 已有 7 个文件，使用 corrected air transport property（thermal conductivity 与 Sutherland viscosity + constant Cp 形成自洽空气热输运闭合），全部通过 adiabatic wall sanity（heat-flux 为 machine zero，wall temperature 均低于对应 perfect-gas freestream T0_inf）：

- `30km_3alpha_6.5ma.csv`
- `30km_5alpha_6ma.csv`
- `30km_5alpha_8ma.csv`
- `35km_8alpha_6.5ma.csv`
- `35km_8alpha_9ma.csv`
- `40km_5alpha_8ma.csv`
- `40km_10alpha_8ma.csv`

## 5. Corrected Mapping

**Fluent CSV 的 `y-coordinate` 是 spanwise 轴**（范围 [0, 1.030] ≈ b_half=1.031），`z-coordinate` 是厚度方向。之前误用 `(x,z)` 匹配 span 是错误的。

正确 mapping: LF `(x_w_m, span_w_m)` → Fluent `(x-coordinate, y-coordinate)`

## 6. Corrected Seven-Case Comparison

NN: KDTree 2D, mean=12.6mm, p95=30.8mm, max=41.2mm

Fluent 侧使用 corrected air transport property CSV（用户确认 Cp(T) 为 temperature-dependent piecewise-polynomial，k(T) 同理）。mapping: LF `(x_w_m, span_w_m)` → Fluent `(x-coordinate, y-coordinate)`。

### 6.1 Route A-CPG Taw（历史对照，已不可运行）

| case_id | h_m | alpha | mach | LF Taw [K] | Fluent T [K] | dT [K] | rel_err mean |
|---|---|---|---|---|---|---|---|
| h30km_a3deg_ma6p5 | 30000 | 3 | 6.5 | 1867 | 1713 | +154 | 9.0% |
| h30km_a5deg_ma6 | 30000 | 5 | 6 | 1640 | 1514 | +126 | 8.3% |
| h30km_a5deg_ma8 | 30000 | 5 | 8 | 2726 | 2392 | +334 | 14.0% |
| h35km_a8deg_ma6p5 | 35000 | 8 | 6.5 | 1926 | 1777 | +149 | 8.4% |
| h35km_a8deg_ma9 | 35000 | 8 | 9 | 3472 | 3015 | +457 | 15.2% |
| h40km_a5deg_ma8 | 40000 | 5 | 8 | 2837 | 2607 | +230 | 8.8% |
| h40km_a10deg_ma8 | 40000 | 10 | 8 | 2860 | 2599 | +261 | 10.1% |

### 6.2 Route A-TPG audit Taw（Cp(T)-based enthalpy formula，零参数）

| case_id | Fluent T [K] | TPG audit Taw [K] | TPG bias [K] | TPG rel_err |
|---|---|---|---|---|
| h30km_a3deg_ma6p5 | 1713 | 1697 | -16 | 1.06% |
| h30km_a5deg_ma6 | 1514 | 1510 | -4 | 1.15% |
| h30km_a5deg_ma8 | 2392 | 2388 | -5 | 0.85% |
| h35km_a8deg_ma6p5 | 1777 | 1746 | -32 | 2.01% |
| h35km_a8deg_ma9 | 3015 | 2976 | -40 | 1.64% |
| h40km_a5deg_ma8 | 2607 | 2475 | -132 | 5.05% |
| h40km_a10deg_ma8 | 2599 | 2497 | -102 | 3.92% |

## 7. 当前结论

### CPG high-bias
- Route A-CPG Taw 对 corrected Fluent adiabatic wall temperature 呈系统性高估（+126–457 K，8%–15%）
- 7 cases × 3240 pts = 22680 points, **100% LF Taw > Fluent Tw**（pre-tip-regularization historical diagnostic；不得改写为当前 3321 点口径）
- bias 随 Mach 单调增长（Ma6 8.3% → Ma8 14.0% → Ma9 15.2%）

### Regional error distribution
- x_norm / span_norm 分区误差基本平坦（各 bin 内 rel_err 变幅 1-3pp）
- Taw error 没有跟随 pressure ratio 空间梯度（pr 从 nose 1.5× 到 outer/aft 7–8×，但 rel_err 基本 flat）
- pressure/Cp 是 **independent fidelity gap**，不是 Taw high-bias 的空间驱动

### Cp(T)-based thermodynamic audit（Phase 2E-P1）
- H1 strongly supported：CPG 温度式 `Taw = T_e [1 + r(γ-1)M_e²/2]` 与 Fluent variable-Cp enthalpy treatment 的热力学错配是 Taw high-bias 的**一阶来源**
- 零参数 Cp(T)-based enthalpy formula `h_aw = h(T_e) + r_eff·v_e²/2` 可使 rel_err 从 8–15% 降至 **0.85–5.05%**
- Pr(T) 在 300–3500 K 全程 ≈ 0.72 → recovery factor 公式 `sqrt(Pr)/Pr^(1/3)` 在此范围内是自洽的
- 之前 "recovery factor 偏高" 的诊断被重新定位：问题是**焓-温转换用错了热力学**，不是 r_eff 值不对
- 40km cases 的 TPG residual 偏大（4–5%）提示 edge-condition M_e 公式的 γ=1.4 硬编码可能是二级问题

### 其他
- pressure/Cp 作为独立 fidelity gap 保留，不混调
- DN 默认关闭
- residual learning 未启动
- validation complete 未声明
- ma8_a10_h50km 仍为 holdout

## 8. 历史下一步（已完成并被当前 TPG-only 治理取代）

以下条目只记录 Phase 2E-P1 当时的决策，不是当前待办：TPG 曾以 opt-in candidate 进入实现，并保留 CPG 极限回归；随后 TPG 成为正式主线，CPG runtime、CLI 选择与相关回归现已完整删除。pressure closure、r_eff、transition、geometry/mapping 在该阶段保持冻结；40km residual (4–5%) 当时作为 possible fidelity boundary，未做补丁修正，也未进入 residual learning / GPR / MoE。
## 9. Phase 2E-P2/P2R2: Route A-TPG 实现并验证 (2026-07-07)

以下为 2026-07-07 的历史实现状态：Route A-TPG 当时已实现为默认 thermodynamic baseline，CLI 当时仍保留 CPG legacy opt-in，并验证其与旧默认 CPG bitwise identical。该 CPG CLI 与运行链现已完整删除，不再可运行。

### 9.1 Route A-TPG 实现内容

- TPGThermo class: variable-Cp thermodynamic path
- Cp(T) 来自用户提供的 Fluent material table（21 点，200-6000 K）
- 梯形积分构造 h(T)、s0(T)、gamma(T)、a(T) 表
- Edge-state 使用 shock-density chain + TPG isentropic expansion from stagnation
- Taw 使用焓基形式: h_aw = h(T_e) + r_eff * Ve^2 / 2, Taw = h^-1(h_aw)
- r_eff、Pr=0.72、pressure closure、transition、geometry/mapping 全部冻结
- pressure closure 仍为 newtonian_like, A=0.38, n=1.15
- DN off, no q_scale / multiplier
- 通过 CPG-limit regression（constant Cp 还原旧 CPG 结果，偏差 < 1K）

### 9.2 P2R2 Corrected Mapping TPG Comparison（最终有效表）

Corrected mapping: LF (x_w_m, span_w_m) -> Fluent (x-coordinate, y-coordinate), threshold 0.3m.

| Case | Fluent mapped Tw | CPG Taw | TPG Taw | CPG bias | TPG bias | CPG rel_err | TPG signed rel_err | TPG abs_rel_err |
|---|---|---|---|---|---|---|---|---|
| h30_a3_ma6.5 | 1713 | 1867 | 1767 | +154 | +54 | 9.00% | +3.14% | 3.18% |
| h30_a5_ma6 | 1514 | 1640 | 1561 | +126 | +47 | 8.33% | +3.12% | 3.15% |
| h30_a5_ma8 | 2392 | 2726 | 2484 | +334 | +91 | 13.97% | +3.82% | 3.84% |
| h35_a8_ma6.5 | 1777 | 1926 | 1811 | +149 | +34 | 8.37% | +1.95% | 2.02% |
| h35_a8_ma9 | 3015 | 3472 | 3098 | +457 | +82 | 15.19% | +2.75% | 2.84% |
| h40_a5_ma8 | 2607 | 2837 | 2582 | +230 | -25 | 8.84% | -0.95% | 0.98% |
| h40_a10_ma8 | 2599 | 2860 | 2595 | +261 | -4 | 10.09% | -0.12% | 1.23% |

### 9.3 状态声明（历史实现描述）

- Route A-CPG: corrected mapping 下 8.3%-15.2% Taw high-bias, 100% overprediction
- Route A-TPG opt-in: abs_rel_err 0.98%-3.84%（历史值，基于 pre-freestream-closure LF 来流）
- 30-35km cases 有小幅 positive bias (+1.9%-3.8%)
- 40km cases 转为轻微 underprediction (-0.95%, -0.12%)（历史值；来流闭合后为小正偏）
- 40km residual 当时暂记录为 possible fidelity boundary；来流闭合后该结论不再成立
- Route A-TPG 已通过 P3/P3R freeze consideration 和 P4 regression，作为新的默认 low-fidelity thermodynamic baseline
- 不是 validation complete

### 9.4 历史源码快照说明

当时用于验证的源码快照现已移出主工程；本文只保留历史结论，不依赖其路径。

### 9.5 Phase 2E-P4: Switch Default Thermo Baseline to TPG (2026-07-08)

以下为 2026-07-08 的历史切换记录；其中模型选择 CLI 与 CPG legacy opt-in 现已删除。

- 当时默认模型由 CPG 切换为 TPG
- 当时 default TPG 与显式 TPG 选择 bitwise identical
- 当时保留的 CPG legacy opt-in 与旧默认 CPG bitwise identical；该运行路径现已删除
- TPG default switch 使 Taw 与 enthalpy-based q-chain fields（q_w, q_lam_w, q_turb_w, h_e_w, h_r_*, h_star_*）的默认输出随 Cp(T) thermodynamic baseline 改变；这是物理一致性改变，非 empirical tuning
- 7-case TPG Taw 与 P2R2 canon 一致（全部 <1K）；P4 使用 kd-tree nearest-neighbor mapping，Fluent mapped Tw 口径未完全复现 P2R2 canon mapping；当时正式 corrected comparison canon 以 P2R2 表为准（该声明已过期；P2R2 现为历史 evidence，非当前来流对齐 canon）
- 不是 validation complete
- 当时的源码快照现已移出主工程；本文只保留历史结论，不依赖其路径。

### 9.6 历史 CPG-era provenance（2026-07-09）

- 当时对 pre-2026-07-12 CPG-era baseline 的复现曾获得 PASS；这是历史事实，不是当前 gate
- 该历史 baseline 使用旧大气口径、row 40 invalid、fixed wall 300 K 且不含 `Taw_tpg_w`
- 相关 runtime replay、脚本与工程内路径均已删除；当前不得执行或依赖
- 历史结果：ma6_a5_h30km / ma8_a5_h30km 各 39 数组 `max_abs_diff=0.00e+00`；不代表当前代码状态
- `scripts/run_case_rem.py` 的工况仍须由 `--mach/--alpha/--h_m` 显式指定
- 仍不是 validation complete；holdout 未触碰

## 10. Windward / Leeward Classification 审计 (2026-07-10，2026-07-14 更新)

只读审计结论：

- 当前代码不是按 `local outward normal · incoming flow direction` 逐面分类；
- 当前 legacy routing 不是逐点 aerodynamic classifier：`alpha >= 0` 时选择 lower sheet 进入 windward 主链、upper sheet 进入 legacy leeward 主链；`alpha < 0` 时反向选择。该 routing 选择不表示 geometric sheet 与 aerodynamic class 恒等；
- `mask_w / mask_l` 是 `q_w / q_l` 是否 finite 的计算有效性 mask，不是独立 aerodynamic-side classifier；
- normal-dot 只读审计未发现正攻角下当前 windward 高热流/高 Taw 主结果存在明显错分；
- 当前分类在单调主翼面 acreage 区可继续作为工程近似；
- 鼻尖、圆弧前缘和 near-tangent 上表面仍属于分类粗化区域；

**2026-07-14 更新：** local-incidence additive diagnostic 已正式冻结（见 §16）。默认 alpha-sign classification 暂不修改；local-incidence 保留为已冻结 diagnostic，尚未接管正式 solver routing。

## 11. Leeward 当前能力边界（2026-07-15）

- legacy `Tw_l`、`q_l`、`St_l`、`Re_ns_l` 仍为 fixed-wall q-chain；其定义和字段未改变。
- 已实现并冻结独立的 sheet-specific leeward freestream-recovery TPG Taw diagnostic，upper/lower geometric sheet 分开输出；不存在 generic `Taw_tpg_l` 字段。
- raw leeward mask 唯一定义为 `mask_leeward_<sheet> = (surface_class_<sheet> == -1)`；它表示 aerodynamic class，不把 upper/lower geometric sheet 等同于 leeward/windward。
- 首轮 provider 为 freestream：`T_e/p_e/rho_e/V_e/Ma_e = T_inf/p_inf/rho_inf/V_inf/Ma_inf`，`h_e=h(T_inf)`，`mu_e=mu(T_inf)`；其空间常数是零阶 diagnostic baseline 的结构预期，不是最终背风模型。
- recovery 使用 TPG 焓形式：`h_aw = h_e + Pr^(1/3)·V_e²/2`，`Taw = T_from_h(h_aw)`，`Pr=0.72`；mask 外所有连续字段为 NaN。
- 新 diagnostic 与 legacy fixed-wall q-chain 完全解耦，不接管 pressure、windward edge-state、windward Taw 或 q-chain；正式 alpha-sign routing 尚未切换。
- 新 Taw 在物理定义层面可与 Fluent adiabatic Tw 对应，但 Fluent clean-leeward filtering / mapping contract 尚未冻结，因此当前仍禁止报告 leeward temperature error，也不能声明 leeward model validated。

## 12. Windward Error Cloud Visualization 工具 (2026-07-10 收口)

脚本：`scripts/viz/plot_windward_error_vs_fluent.py`

当前最终状态：
- 使用 LF `Taw_tpg_w`；缺失时 hard-fail
- 使用 LF `(x_w_m, span_w_m)` → Fluent `(x-coordinate, y-coordinate)` KD-tree nearest-neighbor
- Fluent `z-coordinate` 只用于 windward side filtering，不作为 spanwise
- 每个图点表示该 LF 点与其 Fluent 最近邻点之间的局部 signed relative error，不是区域平均值
- 红色 = LF hotter，蓝色 = LF colder
- 输出文件名含 case / thermo model / error type；stats JSON 含 NN median / p95 / max
- 口径声明：diagnostic visualization only；windward-only；不替代 P2R2 corrected comparison canon；不代表 validation complete；不涉及 leeward temperature error

## 13. 12-Case Windward TPG Diagnostic Visualization (2026-07-10)

### 13.1 30–40 km 九工况（有效 diagnostic）

- 30 km / 3° / Ma6.5
- 30 km / 5° / Ma6
- 30 km / 5° / Ma8
- 35 km / 8° / Ma6.5
- 35 km / 8° / Ma9
- 40 km / 5° / Ma6.5
- 40 km / 5° / Ma8
- 40 km / 5° / Ma9
- 40 km / 10° / Ma8

总体 diagnostic 结果（历史 pre-freestream-closure）：
- 30 km：LF 轻微偏高；35 km：偏差进一步收窄；40 km：LF 轻微偏低（旧来流）
- 总体 signed relative error 约在 -1.5% 到 +3.7%
- 空间误差以低幅、较平滑的全场偏移为主；outer-span 常有轻微更大误差
- 局部最大误差可能受 NN mapping distance / edge 区域影响
- 这些结果与 P2R2 的总体方向一致，但不替代 P2R2 canon
- **注：来流闭合后（`runs/fluent_freestream_v2/`）30–40 km 九工况为 ~3%–5% 低幅正偏差**

### 13.2 45 km 三工况 — prescribed/off-standard freestream 一次性验证（已退出正式参数域）

以下表格来自 2026-07-12 explicit freestream override run（T_inf=241.65 K, p_inf=131.0 Pa, +1 K/km simplified model）。该 45 km 来流**不是**标准 ISA/USSA 1976 大气，而是 prescribed/off-standard freestream。该组工况只用于一次性验证：当 LF 与 Fluent 使用相同指定来流时，Route A-TPG 仍能保持约 3%–5% 的温度误差。

Mapping: KD-tree NN diagnostic mapping（LF `(x_w_m, span_w_m)` → Fluent `(x-coordinate, y-coordinate)`，windward `z<0`）。**这不是 P2R2 canon mapping，不可替代 canon。**

| Case | Ma | α | T∞ [K] | p∞ [Pa] | Fluent Tw mean [K] | LF Taw mean [K] | signed error [K] | mean abs rel | p95 abs rel |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ma8_a5_h45km | 8 | 5° | 241.65 | 131.0 | 2511.1 | 2631.5 | +120.5 | 4.81% | 5.94% |
| ma9_a5_h45km | 9 | 5° | 241.65 | 131.0 | 3049.5 | 3208.5 | +159.0 | 5.22% | 6.30% |
| ma8_a10_h45km | 8 | 10° | 241.65 | 131.0 | 2600.3 | 2644.4 | +44.2 | 2.90% | 4.92% |

**45 km 不属于 20–40 km 正式参数域，不参与 residual learning、模型选择、标准高度趋势、holdout 或泛化评价。** 该工况的原始 CSV、runs、fields、summary、PNG、JSON 和所有派生产物已在写完此表后从项目中彻底删除（不归档）。此表为 45 km 唯一保留记录。

## 14. 当前声明

- **正式高度参数域：20–40 km。** 30/35/40 km 采用标准 USSA 1976 大气口径（几何高度输入，内部位势高度换算）。标准回归：30 km T≈226.5 K/p≈1197 Pa，35 km T≈236.5 K/p≈574.6 Pa，40 km T≈250.35 K/p≈286.8 Pa。
- **40 km Fluent 历史输入 251 K / 287 Pa** 由 explicit override 精确复现；该值为用户确认的取整输入（exact ISA1976: 250.350 K / 286.8 Pa）。
- **45 km 已退出 active dataset。** 唯一保留记录为本 doc section 13.2 中的 off-standard 验证表。45 km 不得进入 residual learning、validation、模型选择、超参数选择、标准高度趋势、holdout 或正式参数域。
- **Route A-TPG Taw 固定使用 fully turbulent recovery factor：r_aw = Pr^(1/3)。** Taw 与 q-chain transition weighting 彻底解耦；Taw 不使用 w_tr。
- **pressure 和 edge-state 冻结。** Cp 模型（newtonian_like, A=0.38, n=1.15）未改。
- **q-chain 保留**，但当前不属于 Taw/residual scope。q-chain 中 w_tr 正常存在、未修改。
- **residual learning 尚未启动。**
- **P2R2 corrected comparison 表** 保留为 Route A-TPG 相对 CPG 改善的历史 thermodynamic-architecture evidence；其 35/40 km LF 来流不属于当前 freestream-aligned 口径，因此不再是当前正式 comparison canon。
- 当前 `runs/fluent_freestream_v2/comparison_table.json`（9 工况 30–40 km）是来流闭合后的 KD-tree NN diagnostic comparison；当前不得冒充 P2R2 mapping canon 或 validation-complete 结果。在正式 mapping 口径另行冻结前，两者都不要称为当前唯一 canon。
- 当前不是 validation complete；sheet-specific leeward diagnostic 也尚未完成 Fluent mapping/filtering 或 error audit，不能声明 leeward model validated。
- `ma8_a10_h50km` 为 formal 20–40 km 域外的 reserved legacy stress/reference case；本轮未运行，不参与训练或模型选择，也不作为完全盲的端到端外推证据。
- pressure baseline、DN、CPG 均未改变。
- leeward temperature error 当前禁止报告。

## 15. Current regression 与翼尖 endpoint 状态（2026-07-15）

- 81×41 维度保持不变；row 40 动态移动到最外侧 `chord>=chord_min_m` 的有效站位，当前迎风有效点 `n_valid=3321`
- `chord_min_m=0.02 m` 未修改；最外侧约 3.50 mm 合法零弦长尖端 sliver 保持空白
- 唯一 current baseline：`runs/current_baseline_snapshot/tpg/`，case 为 `ma6_a5_h30km` 与 `ma8_a5_h40km`
- baseline schema：`current-tpg-baseline-regression/v5`；official CLI `fields.npz` 共 72 字段
- 唯一命令：`python scripts/tools/current_baseline_regression_check.py`
- Groups 1–8 均独立复现 PASS；Group 8 为 18 个 sheet-specific leeward freestream-recovery 字段；Groups 1–7 所有既有字段 `max_abs_diff=0`
- 两个 current baseline 的 raw leeward mask 均为 upper=256、lower=0；这是当前工况逐 sheet 分类结果，不是 geometric sheet 与 aerodynamic class 的恒等关系
- mandatory fields、field parity、dtype/shape、NaN mask、semantic QA、row 40、endpoint metadata 与 source hashes 均已纳入 gate；无字段静默跳过
- CPG runtime、current compatibility baseline 与 phase4a0 replay 已删除；历史 CPG→TPG 改善只作为历史证据
- `src_snapshots` 已移出主工程；`ds_plan` 已删除

## 16. Local-Incidence Classification（2026-07-14 正式收口）

- **local-incidence 已作为 additive diagnostic 正式冻结。** 当前正式 solver routing 仍为 alpha-sign windward/leeward；local-incidence 尚未接管正式路由。
- **分类公式：** `s = -dot(u_hat, n_out)`，其中 `u_hat = (cos(alpha), 0, sin(alpha))`，alpha 使用 geometric alpha，不使用 `alpha_e`。
- **阈值：** `epsilon = 0.05`（`0.03` 与 `0.08` 仅作为 sensitivity）。
- **法线来源：** raw STL facet normal 优先；upper 强制定向 `n_z>0`，lower `n_z<0`；无 STL 覆盖时使用 analytic fallback。
- **几何身份与气动身份分离：** upper/lower 是几何 sheet identity；windward/leeward/near-tangent 是逐点气动分类。upper 不等于 leeward，lower 不等于 windward。同一 sheet 可包含三种气动分类。
- **12 个字段已纳入 current baseline：** `normal_x/y/z_upper/lower`、`incidence_s_upper/lower`、`surface_class_upper/lower`、`normal_source_upper/lower`。
- **alpha=5° headline：** upper 2085 windward / 980 near-tangent / 256 leeward；lower 3321/0/0。Upper leeward 255/256 点构成单一连续区域，主要位于外翼。
- **四攻角历史 clean-leeward 扫描：** alpha=3°/5°/8°/10°，epsilon=0.05；其中 alpha=8° clean=535、alpha=10° clean=754。该 clean filtering 尚未成为正式 mapping contract，不得与 raw counts 混写。
- **Sheet-specific Taw diagnostic 已冻结：** `Taw_tpg_leeward_upper/lower` 使用 raw `surface_class_<sheet> == -1` mask 与 freestream provider；不存在 generic `Taw_tpg_l` 字段。
- **三工况 shakeout：** Ma8/alpha10°/40km raw upper/lower=848/0，Taw=2699.7814815610645 K；Ma6.5/alpha8°/35km raw upper/lower=611/0，Taw=1828.7434539198769 K；Ma9/alpha8°/35km raw upper/lower=611/0，Taw=3126.4252493860427 K。同一 alpha=8° 下 Ma6.5 与 Ma9 的 class/mask exact equal。
- **当前限制：** 未进行 Fluent mapping、clean filtering 或 temperature-error calculation；当前不得报告 leeward temperature error，也不能声明 leeward model validated。
- **下一阶段：** 独立冻结 Fluent clean-leeward filtering / mapping contract。
