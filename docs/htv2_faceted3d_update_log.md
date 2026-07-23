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
- 45 km 全部原始 CSV / runs / fields / summary / PNG / JSON 从项目中彻底删除（不归档）；不属于当前正式参数域
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
- 尚未进行 Fluent mapping、clean filtering 或 temperature-error calculation；后续入口已更新为集成已裁决的 Fluent clean-leeward exact geometry mapping 合同

---

## 2026-07-17: Fluent Geometry Exact-Projection Foundation 正式收口

- exact point-to-triangle kernel 以 exhaustive all-triangle search 作为正式真值，覆盖 interior、edge、vertex、degenerate triangle 与 deterministic triangle-index tie-break；不使用固定 `k` centroid shortlist、近似 KD-tree、BVH 或 cache
- strict Fluent geometry contract 只读取 `cellnumber` 与三坐标，冻结 Fluent → solver 为 `(x+0.030, y, z) m`；`+30 mm` 是调用方显式传入的 nominal nose-radius origin offset
- canonical identity 基于变换后的 coordinate triple，不依赖 CSV row ordering 或非唯一 `cellnumber`；两个正式 Fluent case 的 canonical coordinate bytes 完全相同
- exact projection adapter 保持 canonical/source ordering 显式可逆；21,250 个点对 6,341 个三角面全量投影，21,250/21,250 finite、valid triangle ID 且通过闭区间 5 mm gate，gate fail=0
- 74/74 tests PASS；schema v5、72/72 fields、Groups 1–8 `max_abs_diff=0`、53 项 source identity 与 current regression overall 全部 PASS
- 本阶段未进入 Fluent/LF clean、LF→Fluent mapping 或 temperature error，不构成 leeward model validation

---

## 2026-07-17: Phase 4A Projected Geometry Semantics 正式收口

- 提交 `7077aceac6d4d5ff92c63ca3ddaf987e5baaf6fe` 与 `6934b64c5ab33c29577b8d3071e453c5358d4e40` 完成 Phase 4A pure semantics foundation。
- projected-point sheet、outward normal、incidence、共享 q-chain acceptance 与 projected planform 参数化合同已冻结；正式热流数值链未改变。
- 84/84 tests PASS；55/55 source identity PASS；schema v5、72 fields、Groups 1–8 `max_abs_diff=0`，current regression overall PASS。
- 尚未进入真实 21,250 点 semantics integration，也未构造 Fluent clean 或 LF clean。

---

## 2026-07-18: Phase 4A 后 Repository Hygiene 收口

- 完成 tracked、untracked、ignored、近期阶段文件与 active reference 审计；删除 3 份已由 canonical docs 替代且无 code/test/config/CLI/manifest/docs active reference 的根目录旧文档：背风温度可比性临时诊断、旧 CLI 速查、旧流程说明。
- 清理本地 11 个 `__pycache__` 目录、43 个 `.pyc`；现有 `.gitignore` 已覆盖该类产物，无需扩展。
- 历史 archive/runs、`新翼型.md`、AI 辅助资料、三维调研、pressure sandbox 与历史源码快照存在历史证据、用户资料或替代关系疑义，保留待裁决。
- 84/84 tests PASS；55/55 source identity PASS；schema v5、72 fields、Groups 1–8 `max_abs_diff=0`，current regression overall PASS。
- 未修改正式源码、manifest、fields、summary、artifact hash、物理链或数值 baseline；下一阶段仍为 Phase 4B。

---

## 2026-07-18: Phase 4B Fluent Projected Semantics Integration 正式收口

- 提交 `46964f330b6c8a8f30d3e6e0917f7bc3735f6b05` 与 `a67b307fe46ea2a276a819f25791a4fda3b2c587` 完成 adapter、integration test 与正式 geometry-only QA runner。
- 21,250 个 Fluent points 对 6,341 个 STL triangles 的闭区间 5 mm gate 全通过；sheet UPPER/LOWER/OTHER/INVALID=7,325/7,516/5,703/706，normal source 0/1/2/3=6,409/10,006/4,835/0，surface class windward/leeward/near-tangent/invalid=13,971/186/684/6,409，semantic-valid/invalid=14,841/6,409，另有 10 个独立的 planform-invalid。
- 正式 projection dataset count=1，exact kernel invocation count 等于 projection chunk count；第二工况在 canonical geometry exact identity 后复用 projection，未执行独立第二次 projection。
- 93 tests 与 59 subtests、56 source identities、schema v5、72 fields、Groups 1–8 零漂移及 current regression overall 全部 PASS。
- 本阶段未构造 Fluent/LF clean，未执行 LF clean → Fluent clean mapping，未读取 wall-temperature 或计算 temperature error；下一阶段仅为 Fluent clean。

---

## 2026-07-18: Phase 5A Fluent Clean Leeward Contract 正式收口

- 提交 `61e73b343f1a2251c8860664a2534eee06735186` 冻结 Phase 5A Fluent clean：`clean_eligible = projection_gate_pass AND semantic_valid_mask AND planform_domain_valid`，upper/lower 再分别要求对应 geometric sheet 与 `surface_class == LEEWARD`，any 为 upper/lower 并集。
- `normal_source` 1 与 2 均可进入 clean，0 与 3 由 semantic-valid 排除；q-chain 的 20° / `abs(n_z)>=0.45` 合同保持不变，但 `qchain_stl_accepted` 不是 Fluent clean predicate。
- 正式 geometry-only QA：clean upper/lower/any=`186/0/186`；clean upper 中 source 1/2=`15/171`，source 0/3=`0/0`；upper/lower overlap=0。
- 当前验证为 97 tests、77 subtests、57 source identities 全部 PASS；schema v5、72 fields、Groups 1–8 全部 zero drift，current regression overall PASS。
- 本阶段尚未进入 LF clean、LF clean → Fluent clean mapping、wall-temperature ingestion 或 leeward temperature error；下一阶段唯一入口为 LF clean。

---

## 2026-07-18: Phase 5B1 LF Clean Leeward Contract 正式收口

- Phase 5B1 implementation landing SHA=`3a7922518cb05533c779a11eb0eb3a4d3f653f32`；三个实现提交依次为：`f4e09944` 实现 LF clean 背风子集合同，`eb4c65a0` 完成 source identity promotion，`3a792251` 校正 deterministic order / EOF hygiene。
- 构建前以 canonical identity 作为整体结构门禁；逐点 frozen predicate 使用 planform-domain、sheet-specific semantic validity 和 `surface_class == LEEWARD`。source 1/2 eligible，0/3 excluded，不引入 q-chain acceptance 或 hidden geometry/physics filters。
- 两个正式 `alpha=+5°` case 均为 3,321 点，clean upper/lower/any=`256/0/256`，upper source 1/2/3=`22/234/0`，overlap=0，八个 masks 跨工况 byte-exact。
- 非 baseline `alpha=-5°` lower-sheet integration shakeout 为 clean upper/lower/any=`1/1443/1444`，exact union 与 overlap=0 PASS；它不是新的正式物理 validation case。
- 当前门禁为 107 tests、87 subtests、58 source identities 全部 PASS；schema `current-tpg-baseline-regression/v5`、正式 72 fields、Groups 1–8 zero drift，runtime `last_fields` 仍为 74 项。
- 本阶段未进入 LF clean → Fluent clean mapping、mapping QA、wall-temperature ingestion 或 leeward temperature error；下一阶段唯一入口为 LF clean → Fluent clean mapping contract audit / implementation。

---

## 2026-07-18: Phase 5B2 Mapping Contract Audit

- 在 `main@60e3473cc48d366671921ca246aaccf60f5a1fd1` 上完成只读 geometry/mapping contract audit；审计过程零仓库写入，两正式工况结果 byte-exact，未读取温度、未计算误差。
- 比较 P（exact-projected physical）、R（raw Fluent centroid physical）与 U（projected normalized）双向最近邻；正式推荐 Fluent clean → LF clean + P。推荐方向中 P/R assignment=`186/186` 相同，P/U=`47/186` 相同。
- Candidate P Fluent→LF：source/target=`186/256`，unique targets=`80`，coverage=`31.25%`，collision excess=`106`，duplicate targets=`60`，maximum multiplicity=`4`；distance min/mean/median/p95/max=`0.323/8.180/7.349/17.752/21.042 mm`。
- many-to-one allowed；target multiplicity 与 mutual nearest 只保留为 diagnostic；不采用 injective/Hungarian assignment。
- 本轮不冻结 hard distance gate，不冻结 edge buffer；20 mm 与 30 mm 仅是观察统计。该条目的“尚未开始”状态已由后续 Phase 5C/5D/5E 正式收口取代。

---

## 2026-07-20: Phase 5C–5E Source-level Leeward Comparison 正式收口

- Phase 5C Fluent clean → LF clean pairing 与 Phase 5D Fluent wall-temperature ingestion 均已通过 formal QA；pairing metric 保持 exact-projected physical `(x, span)` 二维欧氏距离。
- Phase 5E 冻结唯一 source-level comparison：一行对应一个 Fluent clean-leeward source；upper 完整保留 `186` 行与 `80` 个 unique LF full-canonical targets 的 many-to-one 关系，不去重、不聚合。
- observation 使用 `wall-temperature`，prediction 唯一使用 Group 8 `Taw_tpg_leeward_<sheet>` full-canonical field并按 `target_canonical_index` 直接索引；legacy `Tw_l=300 K` 不是 adiabatic prediction。
- signed/absolute K 与 percent error 公式、lower typed-empty、metadata/provenance 及 owned/C-contiguous/read-only arrays 已通过两个正式 case 的 Phase 5E QA。
- 本阶段未设置性能 gate、threshold、accepted mask 或 area weighting，未输出第一轮正式性能误差结论；freestream-recovery provider 仍是 diagnostic，是否升级等待下一轮正式误差证据。

---

## 2026-07-20: Chapter 3.1 正式 Evidence 入口审计收口

- Chapter 3.1 正式 evidence 入口审计已完成。审计严格只读，起始与结束均为 `main@066fd41`、工作树 clean；未运行 tests、formal QA 或 current regression，未生成正式 evidence，也未修改 provider、comparison、pairing 或 ingestion。未运行测试是本只读入口审计的任务边界，不是验证失败。
- 正式裁决为结论 2：已有部分入口但不完整，不能直接承担 Chapter 3 正式 evidence。已有正式内存 comparison API、unit tests、Phase 5E formal QA、内存 source identity 与基础 provenance metadata；尚无正式 source-level raw evidence exporter、case-level descriptive summary、leeward spatial/statistical visualization、完整 evidence CLI/reporter、持久化 evidence manifest 或正式 evidence artifact-hash 登记。
- 当前仅 `ma6_a5_h30km` 与 `ma8_a5_h40km` 具备可信 Fluent wall-temperature CSV、正式 ingestion、Fluent→LF pairing、comparison、current baseline manifest、CSV SHA-256、provider/pairing metric 与 source/target identity provenance 的完整可构造链。两 case 均为 `alpha=+5°`，upper=`186` Fluent source rows、`80` unique LF targets，lower=typed-empty；`186 → 80` 是当前 case 事实，不是未来 case 的永久计数合同。
- 两 case 攻角、几何与 clean/pairing topology 相同，不能泛化到其他攻角、lower-sheet branch 或尚未进入 Phase 5C–5E 正式链的 Fluent cases。source-level 统计继续按 Fluent source rows 计数，全部 source rows 保留；many-to-one 不按 unique target 去重，target multiplicity 仅作 diagnostic。
- 现有 windward diagnostic 与 leeward source-level comparison 在 row identity、mapping direction、统计母体、repeated-target weighting、relative-error representation 与 provenance 完整性方面不一致，现有 windward summary 不能直接作为同口径正式对照。已发现建议评估 N3c 的触发证据，但本轮未进入 N3c、未设计 windward 新合同，也未修改 leeward comparison 合同。
- 当前没有用户批准的统一性能阈值；缺少性能 PASS/FAIL 不是 evidence consumer 的实现缺口。任何 PASS 只表示程序、合同、QA 或资产生成成功，不表示模型性能合格。
- 阶段状态（该审计收口时点）：3.1 已完成；3.2 与 3.3 当时未开始；Chapter 3 尚未完成；GATE A 尚未进入。该状态已由后续 Chapter 3.2/3.3 收口条目更新。

---

## 2026-07-20: Chapter 3.2/3.3 Source-level Evidence 合同与实现收口

- Chapter 3.2 Evidence 合同与资产边界已完成；合同达到 unique / complete / internally consistent / directly implementable。Chapter 3.3 由 `scripts/tools/generate_leeward_source_evidence.py`、`scripts/tools/faceted3d_chapter3_leeward_source_evidence_qa.py` 与 `tests/test_leeward_source_evidence.py` 实现并完成验证。
- evidence consumer 使用显式 two-case registry，仅覆盖 `ma6_a5_h30km` 与 `ma8_a5_h40km`。它保持现有 comparison 合同，只做 evidence materialization，不重新执行 ingestion、pairing、nearest 或 error calculation。
- 正式统计母体为等权 Fluent source rows；source-level many-to-one 行完整保留且不按 target 去重，target multiplicity 仅作 diagnostic。空间坐标使用 authoritative projected coordinates；两个正式 case 当前均为 upper=`186` source rows、`80` unique LF targets，lower=typed-empty。
- 每个 case 独立输出 deterministic NPZ raw evidence、JSON case summary 与 PNG visualization；独立 manifest 登记 provenance、source hashes 与 artifact hashes。发布采用原子落盘与防覆盖约束，不向项目 `runs/` 发布正式长期 evidence run。
- 本阶段没有 schema、Groups 1–8、72-field contract 或 baseline promotion；provider、comparison、pairing 与 ingestion 均未修改。
- 验证证据：targeted tests=`17 passed`；comparison dependency=`9 passed, 11 subtests passed`；formal QA=`PASS`，run id=`20260719T213343Z_6766cb3e3bd0`，manifest SHA-256=`53c8198c82cb0dba6d445f0eca32e9e0246b3fe51a0c86ac165b62ac8be53314`；full pytest=`162 passed, 117 subtests passed`；current regression=`PASS`；72/72 fields=`PASS`；Groups 1–8=`zero drift`；source hashes=`PASS`；artifact hashes=`PASS`；`git diff --check=PASS`；independent evidence integrity=`PASS`。
- formal QA 的 PASS 仅表示程序、合同、资产生成与完整性成功，不表示模型性能合格；本阶段没有进行模型性能阈值判断，也没有把 fixed plotting range 解释为性能阈值。
- 阶段状态（该条目收口时点）：Chapter 3.1、3.2 已完成，Chapter 3.3 技术实现与验证已完成；Chapter 3.4 尚未开始。该状态已由后续 Chapter 3.4/3.5 正式结果收口更新；N3c 尚未正式启动，GATE A 尚未进入，strategy v1.0 保持冻结。

---

## 2026-07-20: Chapter 3.4/3.5 Canonical Evidence 结果收口

### 3.4A 正式运行与母体

- 正式 evidence run=`20260720T055647Z_af1f1f5395a9`，Git SHA=`af1f1f5395a992bf8b9f439cf824376c209ab19b`，manifest raw SHA-256 与 detached value 均为 `4db8b71bf79602ffdae12a71a345c251711b0b791ae7405b97105cffef4f0b90`。
- registry 为 `ma6_a5_h30km`、`ma8_a5_h40km`。每个 case 的 upper=`186` Fluent source rows / `80` unique LF targets，lower=typed-empty；正式 population=`fluent_source_rows_equal_weight`。
- many-to-one source rows 全部保留，未按 target 去重，未使用 inverse-multiplicity weighting，未生成 target-level error aggregation。display limits 不是性能 threshold；integrity PASS 不是性能 PASS。
- 正式 run 位于 ignored `runs/leeward_source_evidence/`，作为长期保留的运行证据，不是 tracked baseline。此前仅 CRLF 工作树差异已恢复为干净字节身份；本次没有修改 evidence、baseline 或行尾合同。

### 3.4B Case-level 描述性事实

- Case A `ma6_a5_h30km`：prediction constant=`1550.4342365955222 K`；mean signed error=`14.859391 K`；mean absolute error=`17.536308 K`；mean signed relative error=`0.986416%`；mean absolute relative error=`1.158281%`；positive / negative / zero=`136 / 50 / 0`。
- Case B `ma8_a5_h40km`：prediction constant=`2699.7814815610645 K`；mean signed error=`97.725420 K`；mean absolute error=`97.725420 K`；mean signed relative error=`3.756995%`；mean absolute relative error=`3.756995%`；positive / negative / zero=`186 / 0 / 0`。
- 上述数值仅描述等权 source-row population，不构成 target-level 统计、性能阈值判断或 provider 路线裁决。

### 3.5A Cross-case 直接事实与排除性结论

- 两正式 upper 资产中，`source_canonical_index`、authoritative projected coordinates、`target_canonical_index`、pairing distance、pairing dx、pairing dspan、target multiplicity 均逐元素相等。
- 因此，本次 cross-case 差异不能归因于上述 recorded structures 在两资产之间发生变化。该排除性结论不证明 mapping、geometry 或 pairing 绝对正确，也不排除两个 case 共享的 mapping/geometry bias。
- B−A：mean signed error=`82.866029 K`；mean absolute error=`80.189112 K`；mean signed relative error=`2.770578 percentage points`；mean absolute relative error=`2.598714 percentage points`。
- positive rows 从 A 的 `136/186` 变为 B 的 `186/186`，差值=`+50 rows / +26.881720 percentage points`。
- Case A 同时为 Mach 6 / 30 km，Case B 同时为 Mach 8 / 40 km；Mach 与高度混杂，不能单独归因于 Mach，也不能单独归因于高度。

### 3.5B 有限归因与证据类型

- 正式资产直接事实：每个 case 内 prediction 为 source-row constant；A 的 prediction 位于 observation range 内，故同时存在正、负 signed-error rows；B 的 prediction 高于全部 observation rows，故 `186` 行 signed error 全为正。
- 独立重算事实：两个 case 的 direction counts、observation range、cross-case recorded-array equality 与严格 row alignment 均从现有 NPZ 只读复核。
- 精确代数推论：`signed_error_i = constant_prediction - observation_i`；因此 `centered_signed_error = -centered_observation`。严格 row alignment 下，`Δsigned_error = Δprediction - Δobservation`。
- 排除性结论仅限于“两资产之间 recorded structures 未变化”不能解释本次差异；不扩张为 mapping、geometry 或 pairing 正确性证明。
- 尚未证明：Mach 独立作用、高度独立作用、provider 物理正确性或修改必要性、Fluent observation 质量或因果责任、mapping/pairing 绝对正确性、共同 mapping/geometry bias 不存在、windward/leeward 联合结论、模型性能接受性，以及任何物理因果或机制归因。

### 验证、冻结边界与章节状态

- 对既有正式 run 直接调用只读 `validate_run`：PASS；artifact count=`12`，formal evidence assets=`10`，diagnostic-only assets=`2`，detached verified=`True`。两个 upper 均为 `186/80`，两个 lower 均为 typed-empty。
- 未生成第二个 run，未修改 provider、comparison、pairing、ingestion、源码、测试、配置、baseline 或正式 evidence。pressure、edge-state、TPG、Taw recovery、geometry、clean、mapping 与 Groups 1–8 冻结合同保持不变。
- Chapter 3.4 与 Chapter 3.5 技术范围已完成；N3c 触发证据继续保留但 N3c 未正式启动；GATE A 未进入；provider 未修改；未建立性能 threshold 或模型性能 PASS/FAIL。

---

## 2026-07-20: Chapter 3.6 Evidence Package 收口

### 3.6A Readiness Audit

- 完成 N3 exit-condition / GATE A evidence-package readiness audit，结论=`READY_FOR_3_6B`。现有 formal leeward 与 diagnostic windward 可按 evidence tier 分层并列；windward 明确为 `DIAGNOSTIC CONTEXT ONLY`、`NOT FORMAL SOURCE-LEVEL EVIDENCE`。
- 本阶段未生成新 run，未修改 provider、comparison、pairing 或 ingestion，未启动 N3c，未进入 GATE A。

### 3.6B Package Assembly 与 QA

- 完成 GATE A evidence package assembly；Package 0–12 共 13 项完整，submission status=`PACKAGE_READY_FOR_GATE_A_REVIEW`。
- Package completeness QA=`13/13 PASS`；Package provenance QA=`PASS`；Evidence-tier QA=`PASS`；Population QA=`PASS`；Decision-boundary QA=`PASS`；N3c boundary QA=`PASS`；Internal consistency QA=`PASS`。
- package readiness 只表示材料完整、可追溯且推论边界明确，不表示 GATE A 已开始或已裁决，不表示 provider 路线或模型性能 PASS/FAIL。

### 正式身份与未完成边界

- current docs source HEAD=`dccd5b4677d98086fbd0689f078c36be6927c1a3`；formal run=`20260720T055647Z_af1f1f5395a9`；run source=`af1f1f5395a992bf8b9f439cf824376c209ab19b`；manifest raw SHA-256=`4db8b71bf79602ffdae12a71a345c251711b0b791ae7405b97105cffef4f0b90`。
- 该收口时点 Chapter 3.7 尚未开始；此状态已由后续 Chapter 3.7A 收口条目更新。GATE A 未开始；未执行 A0/A1/A2/A3 裁决；未修改 provider；未扩充正式 case；未进入 N4/N5/N6/N8。
- 证据数量不足、case 覆盖不足、变量混杂、需要新增可信 case 或补充正式诊断时，可能进入 N3a；只有发现 identity、data、geometry、mapping 或 evidence-chain 的具体错误时，才可能进入 N3b。本次未决定进入 N3a 或 N3b。

---

## 2026-07-20: Chapter 3.7A N3 技术退出认证收口

- 任务为 `N3 Final Exit Certification and GATE A Entry Eligibility Audit` 只读审计；未修改项目技术资产。
- 审计认证 Git/Python/commit identity、formal run manifest 与 detached hash、`validate_run=PASS`、`12 assets = 10 formal + 2 diagnostic-only`、two-case registry、每 case upper=`186` Fluent source rows / `80` unique LF targets、lower=typed-empty、formal run ignored、Chapter 3 final evidence index、N3 exit matrix 与 N3c interpretation boundary。
- 结论为 N3 technical exit conditions=`CERTIFIED SATISFIED`，entry eligibility=`READY_TO_REQUEST_GATE_A_ENTRY`。该结论仅建立提交用户批准的资格；用户尚未批准，GATE A 尚未开始，A0/A1/A2/A3 未选择。
- 本审计未修改 provider，未建立性能 threshold，未重算 windward，未生成新 run，未修改 baseline、manifest 或 artifact hashes；formal leeward 与 diagnostic windward 继续分层隔离。
- 下一正式动作是将 entry request 提交用户批准；建议后续由 Opus 主持独立 GATE A review。

---

## 2026-07-20: GATE A=A0 与 N3a 入口文档收口

- 本次 docs-only 收口起点为 Git `0d3fa5d066e33d4daf7207e2bc92798ef37ac4b4`。GATE A review 已完成；Package 0–12 completeness=`13/13 PASS`，provenance、evidence tier、population、decision boundary、N3c boundary 与 internal consistency 均为 PASS；final branch=`A0`。
- 战略迁移正式记录为 `N3 completed → GATE A completed / A0 → N3a current`。A0 表示当前 case coverage 与变量控制不足，不表示 provider 失败、被否决、必须升级或模型性能 FAIL；没有用户批准的统一性能 threshold。
- 正式 evidence run 保持 `20260720T055647Z_af1f1f5395a9`，source SHA=`af1f1f5395a992bf8b9f439cf824376c209ab19b`，manifest raw SHA-256 与 detached hash 均保持 `4db8b71bf79602ffdae12a71a345c251711b0b791ae7405b97105cffef4f0b90`。正式 registry 仍仅含 `ma6_a5_h30km` 与 `ma8_a5_h40km`；每 case upper=`186` Fluent source rows / `80` unique LF targets，lower=typed-empty。
- `README_INDEX.md` 中 Chapter 3 仅到 3.3、3.4 尚未开始、N3 尚未完成等陈旧当前状态已改写。N3a 第一项工作仅为候选 case 数据可用性、Fluent adiabatic-wall observation 与 provenance 入口只读审计，不是 case 扩充施工。
- provider、comparison、pairing、ingestion、schema、72-field baseline、Groups 1–8 与正式 run 均未改变；未新增 case，未修改 registry，未生成 N3a evidence。

---

## 2026-07-21: N3a.3c Candidate Manifest Tooling 正式收口

- Opus 裁决=`DECISION_C_NEW_CANDIDATE_SCHEMA`，用户批准=`GRANTED`；新增未注册 TPG candidate 专用身份 schema `tpg-candidate-manifest/v1`。
- `current-tpg-baseline-regression/v5` 保持冻结且完全不变；`CASES`、正式 registry、两个正式 baseline 与 formal evidence 均未改变。candidate manifest 不是 baseline、formal evidence、registry admission 或 promotion。
- `scripts/tools/current_baseline_regression_check.py` 新增严格隔离的 candidate API/CLI，复用既有 source/artifact hash 核心；`tests/test_tpg_candidate_manifest.py` 覆盖 schema/case identity、hash 复用、路径隔离、拒绝覆盖、原子发布、v5 零漂移及 freeze/check/solver 隔离。
- candidate targeted tests=`38 passed`；full pytest=`195 passed, 117 subtests passed`，无 failed、skipped、xfail 或 warnings。
- 两个正式 baseline `ma6_a5_h30km`、`ma8_a5_h40km` 的 72 fields、Groups 1–8、source integrity、artifact integrity 与 current regression overall 均为 PASS；六个正式 baseline 资产 SHA-256 保持不变。
- 正式 evidence run 未修改，manifest SHA-256 仍为 `4db8b71bf79602ffdae12a71a345c251711b0b791ae7405b97105cffef4f0b90`。
- 本阶段未运行 M8/30，未生成真实 candidate run 或 manifest，未修改 strategy v1.2。strategy v1.2 保持 frozen，当前战略节点仍为 N3a，不退出 N3a，也不返回 GATE A。

---

## 2026-07-21: N3a.4d/e Candidate Explicit-Freestream Provenance 修复与独立 QA

- `tpg-candidate-manifest/v1` 已补齐 candidate-only 显式 freestream provenance。candidate manifest CLI 新增成对可选 `--t-inf-k` / `--p-inf-pa`，要求同时提供或同时省略，并拒绝非有限、零值或负值。
- runner 原有显式 freestream 能力未变；manifest 的复现命令使用正式 runner 参数 `--T_inf_K` / `--p_inf_Pa` 并保留真实值。explicit 路径交叉校验 summary 中的 override pair、freestream source 与实际温压；source 必须为 `explicit_override`，并记录 `atmosphere.explicit_freestream_override=true`。显式 summary 缺少 provenance pair 时 fail-closed。
- 非显式 candidate 路径保持 `explicit_freestream_override=false`；candidate manifest 顶层字段集合不变。正式 v5 baseline、`CASES`、registry、freeze/check、source inventory、Groups 1–8、72-field contract、provider 与 formal evidence 均未改变。
- 独立 QA：candidate 专项=`73 passed`；full suite=`235 passed, 117 subtests passed`；两个正式 baseline regression、72 fields、Groups 1–8、source integrity 与 artifact integrity 均为 PASS。六个正式 baseline 资产、两个生产 v5 manifest、14 个正式 evidence 文件与 33 个历史 pyc 均为 zero drift。
- 下一次唯一 M8/30 candidate generation 的用户批准显式 override 为 `Mach=8`、`alpha=+5 deg`、几何高度 `30000 m`、`T_inf_K=226.509 K`、`p_inf_Pa=1197.0 Pa`；本阶段未执行 candidate generation，未生成 production candidate manifest，未 admission/promotion，也未进入 formal comparison/evidence。
- provider 保持 unchanged；N3a 尚未退出；GATE A 未重新开启。上述 QA 只证明修复、合同与冻结资产完整性，不表示 M8/30 数值结果已生成或验证。

---

## 2026-07-22: N3a.5b–N3a.5e Exact Projection Accelerator / Cache 技术链收口

- 工作分支=`feat/n3a-exact-projection-cache`，base SHA=`0bd59480c14be2769ffca081318f84b29b2049b5`。修改范围严格限定为 `exact_bvh.py`、`projection_cache.py`、`fluent_projection.py`、两个对应测试和两个 canonical docs；原 brute-force exact triangle kernel 与 tie-break 语义未改变。
- 新增 array-based exact BVH 与 geometry-identity fail-closed cache。BVH 使用三维 Euclidean AABB 真下界；exact/near-tie 继续使用 `_distances_equivalent`，canonical triangle index 最小者胜出；仅内部 `RuntimeError` 可回退，输入合同错误 fail closed。cache 仅保存 geometry-derived projection，不包含 wall-temperature。
- CRLF 污染事件中，33 个范围外文件仅发生 LF→CRLF raw 表示变化，normalized content 与 HEAD 一致；已定向恢复，未发生语义修改。
- M8/30 full projection QA：21,250 canonical points、6,341 STL triangles、gate=`0.005 m`；brute-force/BVH runtime=`718.270169500/83.302107300 s`，speedup=`8.6224729815×`；kernel calls=`134,746,250/2,904,162`，visited fraction=`2.1552822435%`，reduction=`97.8447177565%`，fallback=`0`。triangle ID、projected XYZ、distance、raw normal、gate、canonical/source identity 的逐字段 mismatch 均为 `0`，第二次完整 BVH deterministic rerun PASS。
- reference 与 accelerated 的 formal projection、projected semantics、Fluent clean、LF clean、upper/lower pairing 和 upper/lower observation 均等价；冻结 counts 保持 Fluent semantic valid/invalid=`14,841/6,409`、planform valid=`21,240`、gate pass=`21,250`，Fluent clean upper/lower/any=`186/0/186`（source 1/2=`15/171`），LF points=`3,321`、clean upper/lower/any=`256/0/256`，pairing upper source/target=`186/256`、lower=`0/0`，observation upper/lower=`186/0`、unit=`K`。
- 同一实现身份下 projection/BVH regression=`76/76 PASS`、cache regression=`29/29 PASS`，合计 `105/105 PASS`；failed/errors/skipped/xfail/warnings 均为 `0`。
- 正式 cache=`runs/fluent_projection_cache/f8e831b08dd86283bb69dc2f5be5fdb636e160a801ce97ec4d9382098b611c23/projection_cache.npz`，size=`786,521 bytes`，SHA-256=`a82d7d56b01aaae8067cdfa2c3ba439f4d3cc7fcd537c0dedbb573cf4d6be3a7`，schema=`exact-projection-cache/v1`，algorithm=`n3a.5b-exact-bvh/v1`。
- 两个独立冷启动 Python 进程均 cache hit，BVH/brute-force/compute fallback/cache writer calls 全为 `0`；formal projection validator、semantics、Fluent/LF clean、upper/lower pairing 与 observation 全部 PASS；两个进程的 deterministic result JSON SHA-256 均为 `709405e8871f0eb08625e404a58b8725db1b526bdf8963764a2fe499bfc31b44`。
- 正式 cache 治理冻结为 ignored external frozen run artifact：不 tracked、不随普通 clone 分发、不绑定 CASE_REGISTRY、不 promotion 到 baseline/evidence，也不是 canonical source data、观测数据或 baseline；缺失时可由冻结输入与已提交实现重建，identity mismatch/corruption 必须 fail closed。
- 本链未执行 comparison、未生成新 evidence、未处理 45 km、未 admission/promotion。下一步不是继续修改 projection，而是在独立 Git fast-forward merge closeout 后返回原 N3a 资格/治理主线。

---

## 2026-07-23: N3a.6 M8/30 Observation Binding 技术链收口

- N3a.6a 完成 minimal-design read-only audit；N3a.6b 完成 exact CSV 与用户确认 case/custom-freestream 事实的 minimal tracked binding implementation。
- formal QA 发现并修正 bool-as-number、negative altitude、Windows/POSIX/mixed path、source inventory closure 与 current canonical builder golden sync；final formal re-QA=`N3A_M8H30_BINDING_FINAL_FORMAL_REQA_PASS`。
- unified tests=`167 passed`；inline validator adversarial matrix=`74 PASS / 0 FAIL`。current source count=`64`，source paths hash=`2e69d8a851e47418fd988063acf6a0ed5d6b1777477b4a43567cc62d303ec9e8`。
- current canonical hashes：`ma6_a5_h30km`=`50ea18fb56556b46fcef57fe5043c70f1770d7b36d7301fb11d9041a94f2d7c8`；`ma8_a5_h40km`=`00531b7ac10bdaef11638d80104705b96515f03ad8f4d910ef632905fc6a4698`。protected assets、baseline 与 existing evidence 均为 zero drift；historical candidate 未被改写。
- N3a.6 已关闭 N3a.5a 所识别的 exact-CSV tracked binding 缺口；新的 comparison eligibility 决策尚未执行，comparison/evidence 仍未开始。没有执行 admission/promotion；M8/30 candidate 仍为 `unregistered_candidate`，N3a 尚未完成，M6/40 exact observation 仍缺失。
- 三个 45 km CSV 仍未获准进入身份、comparison、evidence 或出图流程。prior `NOT_ELIGIBLE_PROVENANCE_INSUFFICIENT` 未被直接改写为 `ELIGIBLE`。

---

## 2026-07-23: N3a.7 M8/30 Comparison-Input Preparation 实现与独立 Formal QA

- 新增正式 registry-free、fail-closed preparation entry `ref_enthalpy_method.mapping.build_m8h30_comparison_inputs`；公开 bundle 为 `M8H30ComparisonInputs`、`FluentLfTawComparisonInputs`，identity types 为 `M8H30CandidateIdentity`、`M8H30ProjectionCacheIdentity`。该入口只准备 comparison 输入，不调用 production comparison builder，不执行 comparison，不生成 evidence。
- 输入链强制验证 exact observation binding 及 CSV path/size/raw SHA/header/row count，Mach=`8`、alpha=`+5 deg`、altitude=`30000 m`、`T_inf_K=226.509`、`p_inf_Pa=1197.0`、user-confirmed custom project input、adiabatic wall-temperature `K`、Fluent coordinate semantics 与 `x+0.030` transform；同时验证 candidate manifest 与四文件 identity、status=`unregistered_candidate`、existing exact projection cache identity，并固定 `write_cache=False`。
- preparation 继续构造并核对 Fluent observation、Fluent clean、LF clean、Fluent→LF many-to-one pairing、canonical index 与 `Taw_tpg_leeward_<sheet>` prediction identity。upper source rows=`186`；lower source rows=`0` 且为正式 typed-empty；`Tw_l=300 K` 禁止作为 adiabatic prediction fallback。
- formal QA 发现 cache identity 对外审计字段不完整并在批准范围内闭合：identity 直接绑定正式 `build_geometry_identity` 结果，没有复制第二套 geometry identity 算法。focused QA=`154/154 passed`，final full regression=`395/395 passed`，public import 与 `git diff --check` 均 PASS，production comparison calls=`0`。
- current production source count=`65`；唯一新增 source=`src/ref_enthalpy_method/mapping/m8h30_comparison_inputs.py`；source path-list SHA-256=`81f50d9015c3df397923352d3adb5b0d45dd85e01f3e9a66685c49a3fbf6a428`。current v5 identities 为 `ma6_a5_h30km=71d86a8402b57665167e9cd1c47cdb40e5acefb6dff47317e9d8d0cb74806a2c`、`ma8_a5_h40km=e28f4b3710775f8b2536a9fa0b626c3f22ce8e1f24389f8f21b8c528a931d698`；变化仅来自新增 production source identity。
- eligibility=`ELIGIBLE_TO_REQUEST_PRODUCTION_COMPARISON` 只允许申请后续独立 production comparison，不等于 comparison/evidence 已完成。本阶段未修改 `CASES` / registry 或 provider，未 admission/promotion，未进入 formal baseline，未执行 production comparison 或 formal evidence；N3a 未完成，GATE A 未重新裁决。
- historical 61-source candidate manifest、exact M8/30 CSV、candidate 四文件、exact projection cache、formal baseline artifacts、historical formal evidence、Groups 1–8 与 72-field serialization contract 均为 zero drift。

---

## 2026-07-23: N3b Git HEAD-tree / Blob Source Identity 技术闭环

- 在 current-v5 source identity pipeline defect 被确认后，正式合同冻结为：authority=`committed Git HEAD tree`；canonical source bytes=`production path 对应 Git blob bytes`；per-source digest=`SHA-256(blob bytes)`；path=`repo-relative POSIX path`；schema=`git-head-tree-source-identity/v1`。commit SHA、whole-tree OID 与 branch 只作 provenance，不是 canonical identity 等值字段。
- implementation checkpoint=`2ee3481b49a15aa7852c9793749edf05c560152d`；source-only migration commit=`6081f3ac6f0b9bcda5223d5c8fbed20a08c966ce`。两个 current-v5 manifest 从 legacy 61-source map 迁移为相同的 65-source Git blob identity。
- 当前正式 source identity：inventory count=`65`；`inventory_paths_sha256=81f50d9015c3df397923352d3adb5b0d45dd85e01f3e9a66685c49a3fbf6a428`；`aggregate_sha256=221f9fc7926dcaf634410674681708847dc34f96c70e626fe1b4789061f99527`。
- staged、unstaged、deleted、renamed 与 inventory-matching untracked production source 的 adversarial tests 均验证 fail closed；Git 语义 clean 的 Windows CRLF / Linux LF checkout materialization identity neutral；无关 ordinary untracked 不进入 source identity。source-only migration 只能来自 clean committed `HEAD`，不得写入 raw worktree 或 index-only hash。
- focused source-identity suite=`106 passed, 11 subtests passed`；authoritative full pytest=`419 passed, 125 subtests passed, 0 failed`；official current regression 中 `ma6_a5_h30km` 与 `ma8_a5_h40km` 均 PASS，`CURRENT TPG OFFICIAL: PASS`，`CURRENT REGRESSION OVERALL: PASS`。
- Windows 上过长 pytest basetemp 可能使 evidence PNG 完整输出路径超过传统路径长度边界；正式 full QA 使用短系统临时根后全部通过。未修改 evidence generator 或测试；该现象是既有 Windows QA/path-length 环境限制，不是 source identity、evidence generator 或 evidence publication defect。
- source-only migration 的顶层语义变化仅限 `source_hashes_sha256` 与 `source_identity`；`fields.npz`、`summary.json`、`artifact_hashes_sha256`、provider、comparison、Groups 1–8、72-field arrays 与数值资产均为 zero drift。
- 历史 30、35、40、45 km Fluent 对比工况继续只代表各自精确自定义来流，高度是 nominal / historical label，不属于任何已验证大气模型；45 km 与 30/35/40 km 在证据资格上同类。本 N3b 未处理 case 扩展或大气模型归属。
- N3b 技术闭环完成；task branch 尚未合并 `main`，Git closeout 尚未完成。下一原子任务是独立 fast-forward merge closeout；完成后返回 N3a.8，不自动进入 GATE A、provider 修改、production comparison 或 formal evidence。
