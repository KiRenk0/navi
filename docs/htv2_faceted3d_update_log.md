# HTV2 Faceted3D 主线历史

---

## 初始：2D/2.5D → Faceted3D

- 从 2D strip-theory 升级到 STL 三角片法向采样 + outline planform mask
- 引入 streamline x 发展长度模型替代 local x
- 关闭 effective_mach（避免 sweep 重复减弱），保留 effective_alpha

## Pressure Closure: Busemann → frozen newtonian_like

- Busemann Cp 在 HTV2 上高估 4.9–7.4×
- v2 Phase 1 实现可开关 `newtonian_like` Cp: `Cp = 0.38 * sin(phi)^1.15`
- 三工况验证通过；默认仍为 busemann，HTV2 vehicle YAML 显式设为 newtonian_like

## DN Transition

- Phase 2: transition.py 新增 Dhawan-Narasimha 分支
- Phase 3-A: solver_faceted3d.py DN diagnostic-only 接线（w_tr only）
- Phase 3-B: windward_cache DN physical-q 接线（Simon ZPG closure）
- DN 始终为 experimental opt-in，未写入正式 YAML

## Phase 4-A: Baseline Provenance

- Phase 4-A0: 自包含 baseline 复现验证通过（39×2 arrays max_abs_diff=0；这是 2026-07-09 对 0630 CPG-era snapshot 的 historical PASS，post-2026-07-12 不再是 current-src gate）
- Phase 4-A: DN 2-arm sandbox ablation（Arm 0 step control zero-drift PASS; Arm 1 DN-Simon observation only）

## Phase 5-A: Route A Taw

- P1: Taw prototype 完成（公式架构，sandbox-only）。Route A Taw 口径：`r_lam=sqrt(Pr)`，`r_turb=Pr^(1/3)`，`r_eff=(1-w_tr)r_lam+w_tr·r_turb`，`Taw=T_e[1+r_eff(γ-1)M_e^2/2]`，`T0_edge=T_e[1+(γ-1)M_e^2/2]`。
- P2: Fluent adiabatic wall ingestion plan 完成（规划文档）
- P3: four-case official CLI check + corrected comparison 完成

## Geometry / CLI 排雷

- root `new_spec/htv2_0628.stl` + `new_spec/outline_xz_right_0629.csv` 确认为唯一正式几何源
- official CLI 必须通过 `--mach / --alpha / --h_m` 显式指定工况
- Fluent CSV mapping 排雷：`y-coordinate` 是 spanwise 轴，`z-coordinate` 是厚度方向

## Corrected Four-Case Comparison

NN: mean=12.6mm, p95=30.8mm, max=41.2mm (2D KDTree)

Fluent 侧使用 corrected air transport property CSV。

| case_id | h_m | α | Ma | LF Taw [K] | Fluent T [K] | dT [K] | abs_err mean [K] | abs_err p95 [K] | rel_err |
|---|---|---|---|---|---|---|---|---|---|---|
| h30km_a3deg_ma6p5 | 30000 | 3 | 6.5 | 1867 | 1713 | +154 | 154 | 176 | 9.0% |
| h30km_a5deg_ma6 | 30000 | 5 | 6 | 1640 | 1514 | +126 | 126 | 188 | 8.3% |
| h30km_a5deg_ma8 | 30000 | 5 | 8 | 2726 | 2392 | +334 | 334 | 403 | 14.0% |
| h35km_a8deg_ma6p5 | 35000 | 8 | 6.5 | 1926 | 1777 | +149 | 149 | 208 | 8.4% |

Route A Taw 系统性高估 corrected Fluent wall temperature（+126–334 K，8%–14%）。

## Phase 5-A-P5: High-Bias + Pressure + Recovery Audit

- Corrected comparison: Route A Taw 8%–14% high-bias vs corrected Fluent
- P5 (high-bias): `r_eff≈0.85` > `r_F_eq≈0.73–0.77`；Taw bias 完全可由 `(r_eff - r_F_eq)*(T0-Te)` 解释
- P5B (pressure/edge-state): newtonian_like Cp 对 Fluent wall pressure 系统性偏高 44–242%；pressure mismatch 对 r_F_eq 的数值耦合较弱，不影响 recovery audit 方向
- P5C (recovery literature/architecture): `sqrt(Pr)` / `Pr^(1/3)` 应标记为 flat-plate recovery baseline assumption，在 HTV2 3D hypersonic windward surface 上偏高是有物理基础的
- DN default off；当前 step 已偏热，DN 无进入默认路线证据
- pressure/Cp 偏高作为 independent fidelity gap 保留
- Ma9 corrected case pending
- no model tuning / no residual learning

## Docs Governance

docs 已压缩为 9 个 canonical docs；后续常规诊断只更新现有 canonical docs，不再新增 closeout / manifest / audit / handoff md。

下一步：Ma9 append-only comparison / recovery architecture diagnostic。

## Phase 5-A-P6/P7: Ma9 + 40km Two-Case Append + Regional Error Audit

- P6: Ma9 corrected case (h35km_a8deg_ma9) append-only comparison 完成；LF CPG Taw +457 K vs Fluent Tw 3015 K，rel_err 15.2%
- P6R: T_inf consistency audit（USSA1976 @ 35km = 231.65K 确认正确）；raw/mapped/area-weighted Fluent mean consistency verified；pressure statistics verified（5231 Pa raw mean 非 copy-paste error）
- P7: 40km two-case（h40km_a5deg_ma8, h40km_a10deg_ma8）append-only comparison 完成
  - h40km_a5deg_ma8: rel_err 8.8%（altitude 缓解 bias）
  - h40km_a10deg_ma8: rel_err 10.1%（alpha 温和恶化 bias）
- P7R: 7-case regional error distribution audit
  - 22680 mapped points（7 cases × 3240，pre-tip-regularization historical diagnostic）100% LF Taw > Fluent Tw（全局单侧偏热）
  - Taw error 空间分布基本 flat（x/span 分区变幅 1-3pp）
  - pressure ratio 空间梯度明显（nose→aft, inner→outer）但 Taw error 不跟随 → pressure/Cp 是 independent fidelity gap
  - recovery_excess 空间分布平坦 → recovery architecture 是全局偏置而非局部效应

## Phase 2E-P1: Cp(T)-Based CPG-vs-TPG Thermodynamic Audit

- 用户确认 Fluent 使用 variable-Cp(T) + variable-k(T)（density=ideal gas, chemistry=off）
- LF 确认全程 CPG（γ=1.4 constant, cp=1005 constant, Pr=0.72 constant）
- edge_conditions.py M_e 公式 hardcoded γ=1.4（`5.0` 和 `0.2` 不读 gas.gamma）
- Cp(T)-based enthalpy table 构造（21 点用户提供 Cp(T) 表，piecewise-linear 积分，零参数）
- 7-case CPG-vs-TPG audit：
  - CPG rel_err 8.3–15.2% → TPG audit rel_err **0.85–5.05%**
  - TPG mean bias: CPG +126–457 K → TPG **-132 to -4 K**（bias reduction 130–497 K）
  - 5/7 cases TPG rel_err < 2.1%；40km cases 4–5%（possible fidelity boundary）
- Variable-Pr sanity：Pr(T) 在 300–3500 K 全程 ≈ 0.72（变幅 < 0.2%）→ recovery factor 公式自洽
- **H1 strongly supported**：Taw high-bias 一阶来源是 CPG 温度式与 variable-Cp 焓转换的热力学错配
- **Route A-TPG approved as opt-in candidate**；CPG baseline 不被覆盖
- 40km residual (4–5%) 保留为 possible fidelity boundary，不补丁修正
- no model tuning / no residual learning / no validation complete


## Phase 2E-P2/P2R2: Route A-TPG Opt-In Candidate Implemented & Verified (2026-07-07)

- Route A-TPG implemented as opt-in candidate: variable-Cp thermodynamic path with Fluent Cp(T) table
- CLI: --thermo_model tpg (default cpg unchanged)
- Default CPG baseline verified not drifted (7 cases canonical Taw match < 1K)
- --thermo_model cpg bitwise identical to default
- P2R2 corrected mapping comparison (LF x_w/span_w -> Fluent x/y, threshold 0.3m):

| Case | Fluent mapped Tw | CPG Taw | TPG Taw | CPG bias | TPG bias | CPG rel_err | TPG abs_rel_err |
|---|---|---|---|---|---|---|---|
| h30_a3_ma6.5 | 1713 | 1867 | 1767 | +154 | +54 | 9.00% | 3.18% |
| h30_a5_ma6 | 1514 | 1640 | 1561 | +126 | +47 | 8.33% | 3.15% |
| h30_a5_ma8 | 2392 | 2726 | 2484 | +334 | +91 | 13.97% | 3.84% |
| h35_a8_ma6.5 | 1777 | 1926 | 1811 | +149 | +34 | 8.37% | 2.02% |
| h35_a8_ma9 | 3015 | 3472 | 3098 | +457 | +82 | 15.19% | 2.84% |
| h40_a5_ma8 | 2607 | 2837 | 2582 | +230 | -25 | 8.84% | 0.98% |
| h40_a10_ma8 | 2599 | 2860 | 2595 | +261 | -4 | 10.09% | 1.23% |

- Route A-CPG: 8.3-15.2% Taw high-bias, 100% overprediction
- Route A-TPG opt-in: abs_rel_err 0.98-3.84%
- 30-35km cases small positive bias; 40km cases mild underprediction
- 40km residual recorded as fidelity boundary; no patch applied
- Route A-TPG remains opt-in candidate; not validation complete
- 历史证据当时由源码快照支撑；快照现已移出主工程，本文不保留已删除路径。


## Phase 2E-P4: Switch Default Thermo Baseline to TPG (2026-07-08)

- Default thermodynamic model switched from CPG to Route A-TPG
- CPG preserved as --thermo_model cpg legacy opt-in
- Regression completed:
  - Default TPG vs explicit --thermo_model tpg: bitwise identical (all 42 fields)
  - Explicit --thermo_model cpg vs old default CPG: bitwise identical; CPG path unpolluted
  - 7-case regression (kd-tree mapping): TPG Taw matches P2R2 canon within 1K for all cases; Fluent mapped Tw not fully reproduced (1-3% deviation from P2R2 interpolation methodology); formal corrected comparison canon remains P2R2 table
  - q-chain delta documented: q_w +8.7%, q_lam_w +15.2%, q_turb_w +10.8% vs CPG (Cp(T) physics change, not tuning)
- TPG default switch changes Taw and enthalpy-based q-chain default outputs via Cp(T) thermodynamic baseline; this is physical consistency, not empirical tuning
- Reference-enthalpy core frozen; pressure, transition, r_eff unchanged
- Not validation complete
- 历史证据当时由源码快照支撑；快照现已移出主工程，本文不保留已删除路径。


## Engineering cleanup (2026-07-09)

Engineering cleanup completed after Phase 2E-P4/P4R. 该段只记录当时状态：Route A-TPG 当时成为默认线，CPG 尚作为 legacy opt-in；当时的 historical CPG-era replay 仅用于 provenance。相关 CPG runtime、replay 与源码快照后来均已移出或删除，不构成当前可运行能力。No holdout use; no validation-complete claim.


## Phase 2E 后续: Classification / Leeward Capability / 12-Case Error Cloud Diagnostic (2026-07-10)

- Windward/leeward classification 只读审计完成：当前实际口径为 `alpha-sign + upper/lower` surface，在单调主翼面 acreage 区可作为工程近似；normal-dot classification 保留为 diagnostic / sensitivity audit 候选，不进入默认主线
- 2026-07-10 的 leeward capability 审计已由 2026-07-15 sheet-specific freestream-recovery diagnostic 最终状态取代；legacy fixed-wall 字段仍保持独立
- Windward error cloud visualization 脚本 `plot_windward_error_vs_fluent.py` 收口：使用 LF `Taw_tpg_w` + `(x_w_m, span_w_m)` → Fluent `(x-coordinate, y-coordinate)` KD-tree NN；Fluent `z-coordinate` 仅用于 windward side filtering；每个图点表示局部 signed relative error；标为 diagnostic visualization only
- 12-case windward TPG diagnostic error cloud 批量生成
- 30–40 km 九工况作为有效 diagnostic 保留（signed rel err ≈ -1.5% to +3.7%，与 P2R2 总体方向一致）
- 45 km 三工况标记为 `FREESTREAM QA FAIL`：40 km LF 使用 `ussa1976` atmosphere，45 km LF 使用 `isa1976` atmosphere，两组输入口径不统一；45 km 异常强烈指向 LF–Fluent freestream/input inconsistency，但 Fluent 实际 `T_inf/p_inf` 未在工程记录中找到可靠证据
- P2R2 corrected comparison canon 未被替代；不声明 validation complete；holdout 未触碰

---

## 2026-07-12: Formal Domain Freeze + Taw Cleanup + 45 km Exit + Docs Consistency

- Route A-TPG Taw 删除伪转捩死逻辑（hard-coded `re_measure=1e7`/`re_tri=1e6`/`transition_weight`）；改为显式 `r_aw = Pr^(1/3)` fully turbulent recovery
- 大气模型统一：`isa1976.py` 新增几何高度→位势高度内部换算，成为唯一正式实现；`ussa1976.py` 改为薄 alias
- 正式高度参数域冻结为 20–40 km；30/35/40 km 采用标准 USSA 1976 大气口径（几何输入、内部位势换算）
- 45 km 全部原始 CSV / runs / fields / summary / PNG / JSON 从项目中彻底删除（不归档）；仅在 `faceted3d_current_status_zh.md` §13.2 保留唯一 off-standard 验证表
- 50 km 降级为 formal 域外的 reserved legacy stress/reference case
- canonical docs 一致性收口：`current_model_decisions_zh.md` 补齐正式域/大气/Taw 口径；`README_INDEX.md`、`faceted3d_official_cli_run_guide_zh.md`、`functional_baseline_contract.md`、`faceted3d_file_index_zh.md` 同步更新
- 无模型公式修改，无 pressure/DN/residual/holdout 变化

---

## 2026-07-13: Current Regression Baseline + Runtime 收口

- 翼尖 endpoint regularization 状态冻结：81×41 不变；row 40 动态移动到最外侧 `chord>=chord_min_m` 的有效站位；`n_valid=3321`；`chord_min_m=0.02 m` 不变；约 3.50 mm 合法退化尖端 sliver 保持空白
- 唯一 current regression 命令：`python scripts/tools/current_baseline_regression_check.py`
- baseline 仅含 TPG 两 case：`ma6_a5_h30km`、`ma8_a5_h40km`
- 六组字段合同、mandatory-field、shape、NaN mask、row 40、endpoint metadata 与 source hashes 均通过独立复现；全部 `max_abs_diff=0`
- CPG runtime、current compatibility baseline 与 phase4a0 replay 删除；旧 CPG→TPG 改善表仅保留为历史 thermodynamic-architecture evidence
- `src_snapshots` 已移出主工程；`ds_plan` 已删除
- 未修改 TPG、Cp(T)、Taw recovery、大气、pressure、edge-state、chord_min、endpoint 算法、geometry 或 Fluent CSV

---

## 2026-07-14: Local-Incidence Classification 正式收口

- 新增 local-incidence additive diagnostic：`s = -dot(u_hat, n_out)`，geometric alpha，epsilon=0.05
- classification 与 q-chain filtered slope 解耦；raw STL facet normal 优先，analytic fallback 仅无 STL 时使用
- 四攻角覆盖扫描（3°/5°/8°/10°），clean-leeward 区域识别完成
- 12 个 local-incidence 字段（normal_x/y/z_upper/lower、incidence_s_upper/lower、surface_class_upper/lower、normal_source_upper/lower）正式进入 current numeric regression
- 旧物理字段零漂移验证通过（两 baseline case 全部 `max_abs_diff=0`，Taw_tpg_w/q-chain/legacy leeward bitwise 不变，3321 点与 row 40 合同不变）
- 正式 alpha-sign routing 未切换；sheet-specific leeward diagnostic 的最终状态见 2026-07-15 收口条目
- QA 工具 `local_incidence_raw_facet_qa.py` 与 `local_incidence_alpha_scan.py` 已从旧 runs 资产解耦，可独立复现
- 废弃临时诊断资产已清理（`runs/local_incidence_qa_png/`、`runs/local_incidence_audit_sections/`、`runs/local_incidence_qa_raw_facet/`）

---

## 2026-07-15: Leeward Freestream-Recovery TPG Taw Diagnostic 正式收口

- sheet-specific diagnostic 已冻结：upper/lower 各自使用 raw `surface_class_<sheet> == -1` mask，freestream edge-state 与 TPG enthalpy recovery，mask 外连续字段为 NaN；与 legacy fixed-wall q-chain 完全解耦
- official CLI 已序列化 18 个 Group 8 字段；`fields.npz` 共 72 字段，current baseline schema 为 `current-tpg-baseline-regression/v5`
- 两个 current baseline Groups 1–8 全部 PASS；Groups 1–7 所有既有字段 `max_abs_diff=0`
- 三工况 shakeout PASS：Ma8/alpha10°/40km raw upper/lower=848/0、Taw=2699.7814815610645 K；Ma6.5/alpha8°/35km=611/0、1828.7434539198769 K；Ma9/alpha8°/35km=611/0、3126.4252493860427 K；同 alpha=8° 的 class/mask exact equal
- 尚未进行 Fluent mapping、clean filtering 或 temperature-error calculation；下一阶段独立冻结 Fluent clean-leeward filtering / mapping contract
