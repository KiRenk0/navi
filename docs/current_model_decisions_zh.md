# 当前 Faceted3D 冻结模型决策

> 更新：2026-07-19（Phase 5B2 Mapping Contract Audit 收口）

---

## 0. 仓库、字节身份与 artifact 语义（冻结）

- `https://github.com/KiRenk0/navi.git` 的 GitHub `main` 是 source of truth；正式本地活动工作区为 `E:\navi_clean`。恢复证据目录和历史目录不是活动开发入口。
- Git 当前 LF 字节身份是活动 Python、Markdown、YAML 等文本的正式源码合同；manifest source hash 绑定 Git 当前字节身份。Phase 5B1 implementation landing SHA 为 `3a7922518cb05533c779a11eb0eb3a4d3f653f32`；GitHub `main` 始终是当前 source of truth。
- `runs/**`、`fluent_export/**`、CSV、STL、NPZ 与其他 binary artifact 保持原始字节；不得无授权执行全仓库 renormalize。
- raw artifact hash、parsed semantic contract、数值与字段合同、provenance path 必须分别表述，不能相互替代。
- baseline `summary.json` 当前只作为 legacy provenance；其 raw SHA-256 不进入 current regression overall gate。未来 summary v5 promotion 应冻结 parsed semantic contract，而不是跨环境 candidate raw hash。
- source identity promotion 只管理源码身份，不等于数值 baseline freeze；当前 58 项 source hash 全部 PASS。STL parsed geometry、CSV parsed numeric arrays、`local_incidence.py` AST/executable semantics、`fields.npz`、summary、schema、artifact hashes 与 Groups 1–8 数值均未改变。

## 1. 压力 baseline（冻结）

- cp_model = `newtonian_like`
- cp_newtonian_A = 0.38
- cp_newtonian_n = 1.15
- 已在 `specs/vehicles/htv2_faceted3d_0629.yaml` 显式写入

## 2. Transition（冻结）

- 默认 weighting = `step`
- logistic / smoothstep 为 opt-in
- Dhawan-Narasimha 为 experimental opt-in，默认不启用，未写入正式 case YAML

## 3. 热流计算链（冻结）

- reference enthalpy core 冻结
- Kemp-Riddell 驻点热流冻结
- chord_min_m = 0.02 冻结
- windward / leeward / leading_edge 热流公式冻结

## 4. 禁止事项

- q_scale / multiplier 禁止
- `ma8_a10_h50km` 为 formal 域外 reserved legacy stress/reference case
- 不进入 residual learning / GPR / MoE
## 5. Taw Recovery Factor（冻结）

- Route A-TPG Taw 固定使用 fully turbulent recovery：`r_aw = Pr^(1/3)`，`Pr = 0.72`
- Taw 与 q-chain transition weighting 彻底解耦；Taw 不使用 `w_tr`
- q-chain 仍保留自己的 transition 逻辑（`w_tr`），不受 Taw 影响
- 不再使用层流/湍流混合恢复因子 `(1-w_tr)·sqrt(Pr) + w_tr·Pr^(1/3)`（历史实现，已被覆盖）
- Taw 为 adiabatic wall / recovery temperature candidate，不是 TPS material temperature
- Taw 是 prototype comparison，不是 validated temperature model
- validation complete 未声明
- Fluent heat-flux 在 adiabatic wall 中只作为 zero-heat-flux sanity，不是主误差量

## 6. 背风面

- legacy `Tw_l` / `q_l` / `St_l` / `Re_ns_l` 保持 fixed-wall chain；其常值结构是工程模型限制，不是 bug
- sheet-specific leeward freestream-recovery TPG Taw diagnostic 为独立链，不修改或接管 legacy fixed-wall q-chain
- 首轮唯一 edge-state provider 为 freestream；这是零阶 diagnostic baseline，不是最终背风模型
- recovery 与 windward Taw 使用同一 TPG enthalpy form：`h_aw = h_e + Pr^(1/3)·V_e²/2`，`Taw = T_from_h(h_aw)`，`Pr=0.72`
- 新 diagnostic 不接管 pressure、windward edge-state、windward Taw 或 q-chain
- 后续是否升级 local-expansion provider，只能由完成正式 mapping 后的误差证据裁决

## 7. Fluent 对比

- Corrected mapping: LF `(x_w_m, span_w_m)` → Fluent `(x-coordinate, y-coordinate)`
- Fluent y 是 spanwise 轴（范围 [0, 1.030] = b_half），z 是厚度方向
- Fluent adiabatic wall CSV：用户确认为 **density=ideal gas, Cp(T)=piecewise-polynomial, k(T)=piecewise-polynomial, μ=Sutherland, species/chemistry/dissociation=off, energy=on**
- heat-flux 仅用于 adiabatic sanity check
- 当前 comparison 基准为 corrected Fluent CSV
- pressure/Cp audit 与 recovery/thermo audit 分支处理，不混调

## 8. 默认 thermodynamic model: Route A-TPG（Phase 2E-P4 生效）

Route A-TPG 是唯一正式且唯一可运行的 thermodynamic baseline；CLI 无 thermodynamics 选择。历史 CPG→TPG 对比仅保留为 thermodynamic-architecture 改善证据。

- TPG 是唯一正式且唯一可运行模型；CLI 无 thermo 选择
- 历史 CPG→TPG 改善证据表明切换改变 Taw 与 enthalpy-based q-chain fields；这是物理一致性改变，不是 empirical tuning
- Reference-enthalpy core formulas（Eckert, Kemp-Riddell, r_eff, Pr, pressure closure, transition）全部冻结，未因切换而修改
- 不是 validation complete

## 9. Windward / Leeward Classification（2026-07-15 更新）

- 默认 `alpha-sign + upper/lower` classification 暂不修改，仍是正式 solver routing
- local-incidence normal-dot classification 已冻结为 additive diagnostic（`s = -dot(u_hat, n_out)`，geometric alpha，epsilon=0.05）
- upper/lower 是 geometric sheet identity；windward/leeward/near-tangent 是逐点 aerodynamic class；upper 不等于 leeward，lower 不等于 windward
- near-tangent（|s| <= 0.05）是模型有效性缓冲区；raw STL outward normal 优先，analytic fallback 仅无 STL 覆盖时使用
- `mask_leeward_<sheet>` 唯一由 raw `surface_class_<sheet> == -1` 产生；clean filtering 不进入物理字段合同
- 正式 alpha-sign routing 尚未切换；新 diagnostic 不改变正式 pressure、edge-state、windward Taw 或 q-chain routing

## 10. Fluent Geometry Exact Projection（2026-07-17 冻结）

- 正式几何投影真值是 exhaustive all-triangle exact point-to-triangle closest-point，完整覆盖 interior、edge、vertex 与 degenerate triangle，并使用 deterministic triangle-index tie-break；禁止固定有限 `k` centroid shortlist 作为正式真值。
- Fluent → solver 坐标合同为 `(x + 0.030, y, z) m`；`0.030 m` 是调用方必须显式传入的 nominal nose-radius origin offset，不得自动拟合。
- Fluent geometry parser 只按列名读取 `cellnumber` 与三坐标；canonical identity 基于变换后 `(x, span, up)` 稳定排序，不依赖 CSV row ordering 或非唯一 `cellnumber`；完全重复坐标拒绝。
- exact projection adapter 保持 canonical/source ordering 显式可逆，输出 projected point、triangle ID、distance、raw normal 与 gate mask。
- projection gate 为闭区间 `distance <= 0.005 m`。共享 canonical geometry 的 21,250 个 Fluent 点对 6,341 个 STL 三角面执行全量 exact projection，21,250/21,250 finite、triangle ID 有效且 gate PASS，gate fail=0。
- 本 exact-projection 合同只覆盖 Fluent geometry input、坐标合同、canonical identity 与 exact STL projection；Phase 4A projected-point raw geometry semantics、Phase 4B 真实 21,250 点 projected semantics integration、Phase 5A Fluent clean 与 Phase 5B1 LF clean 均已另行冻结。Phase 5B2 只读 mapping contract audit 已完成；正式 Fluent clean → LF clean geometry pairing 与 temperature error 尚未完成。
- 当前禁止报告 leeward temperature error，不能声明 clean-leeward mapping complete 或 leeward model validated；freestream provider 仍是零阶 diagnostic baseline。

## 11. Projected Geometry Semantics（2026-07-17 冻结）

- geometric sheet 与 aerodynamic incidence class 是两个独立字段；upper 不自动等于 leeward。sheet identity 由正式 `SurfaceSlopeSampler` 的 triangle geometry selection 决定，不使用 Fluent 原始 `z` 正负，也不依据 triangle winding 或 raw-normal `n_z` 正负猜测。
- windward/leeward/near-tangent 由 outward normal、geometric alpha 与 `epsilon=0.05` 决定，并复用 `local_incidence.py`。
- q-chain acceptance 判据在共享模块单源维护：normal angle `<=20°` 且 `abs(n_z)>=0.45`，两项边界均接受。
- projected STL point 的 normal source 只能是 `0=INVALID`、`1=STL_ACCEPTED` 或 `2=STL_REJECTED_BUT_USED`；不得为 projected point 伪造 `3=ANALYTIC_FALLBACK`。
- raw `x/c`、`y/b` 基于 projected point；outline 是优先正式 planform 来源，triangle planform 仅作 fallback。raw 参数不取绝对值、不裁剪，clean 裁剪不进入本层。
- Phase 4B adapter 保持 canonical ordering，并对 projection identity、shape、dtype、finite domain、gate mask 与 triangle identity fail-closed；projected arrays 必须 owned、C-order、read-only。
- semantic-valid 定义为：normal source 属于 1/2、geometric sheet 属于 UPPER/LOWER、outward normal 与 incidence finite、surface class 非 invalid。projection gate、planform validity 与 semantic validity 是三个独立合同；planform-invalid 不得自动并入 semantic-invalid。
- projected STL 路径禁止出现 source 3。跨工况仅在 canonical geometry exact identity 成立后允许 projection reuse；正式合同是 exact kernel invocation count 等于 projection chunk count，不要求机器相关 chunk 数固定，也不把 reuse 表述为独立第二次 projection。

## 12. Windward Error Cloud Visualization（2026-07-10）

- `scripts/viz/plot_windward_error_vs_fluent.py` 为只读 diagnostic visualization 工具
- 不替代 P2R2 corrected comparison canon
- 不代表 validation complete
- 不涉及 leeward temperature error

## 13. 45 km（已退出 active 参数域）

- 45 km 使用的 241.65 K / 131 Pa 不是标准 ISA/USSA 1976 大气，而是 prescribed/off-standard freestream（+1 K/km simplified model）
- 原始 Fluent CSV、LF runs、PNG、JSON 等已从项目中彻底删除
- 45 km 不参与 residual learning、模型选择、标准高度趋势、holdout 或泛化评价
- 不再称为 `FREESTREAM QA FAIL`

## 14. 正式高度参数域（2026-07-12）

- 正式高度参数域：20–40 km
- 30、35、40 km 属于正式标准大气工况
- 45 km、50 km 不属于 active formal domain

## 15. 正式默认大气（2026-07-12）

- CLI 输入 `h_m` 为几何高度
- 内部换算为位势高度，按 1976 标准大气分层计算
- `isa1976.py` 是唯一正式计算实现
- `ussa1976.py` 仅为薄兼容 alias，不再维护独立简化公式
- explicit `T_inf / p_inf` override 保留（必须成对提供），可用于复现 Fluent 实际输入

## 16. 50 km（2026-07-12）

- `ma8_a10_h50km` 为 formal 20–40 km 域外的 reserved legacy stress/reference case
- 本轮未运行，不参与当前训练或模型选择，也不作为完全盲的端到端外推证据
- 不删除其文件，不运行，不重新分析

## 17. Endpoint 与 regression governance（2026-07-13）

- 81×41 sampling 维度冻结；row 40 动态移动到最外侧 `chord>=chord_min_m` 的有效站位
- 当前 `n_valid=3321`；`chord_min_m=0.02 m` 不变；约 3.50 mm 合法退化尖端 sliver 保持空白
- 唯一 current regression 命令：`python scripts/tools/current_baseline_regression_check.py`
- baseline 仅含 TPG 两 case：`ma6_a5_h30km`、`ma8_a5_h40km`
- CPG runtime、current compatibility baseline 与 phase4a0 replay 已删除；历史 CPG→TPG 改善仅作历史证据
- `src_snapshots` 已移出主工程；`ds_plan` 已删除

## 18. 当前状态（2026-07-18）

- residual learning 尚未启动，也不是当前下一阶段。
- Phase 5A Fluent clean 与 Phase 5B1 LF clean 均已完成；两者都是 geometry/semantics-only 只读派生 subset，不回写 raw semantic fields，也不读取温度。
- Phase 5B2 只读 mapping contract audit 已完成；正式 Fluent clean → LF clean geometry pairing、mapping QA、wall-temperature ingestion 与 leeward temperature error 均未完成。
- 下一阶段唯一入口为 Fluent clean → LF clean geometry pairing 正式实现。
- 只有未来另行重启 residual learning 时，才需要单独冻结 residual-label mapping、dataset schema 和 case-level validation protocol。
- windward TPG 基线、大气、pressure 和 edge-state 已冻结；baseline schema=`current-tpg-baseline-regression/v5`，正式 `fields.npz` 为 72 fields，runtime `solver.last_fields` 为 74 项，Groups 1–8 零漂移，107 tests、87 subtests 与 58 项 source identity 全部 PASS，`CURRENT REGRESSION OVERALL: PASS`。

## 19. Local-Incidence Classification（2026-07-14 冻结）

- **分类公式：** `s = -dot(u_hat, n_out)`，`u_hat = (cos(alpha), 0, sin(alpha))`
- **alpha basis：** geometric alpha（不使用 `alpha_e`）
- **epsilon：** 0.05（0.03/0.08 仅 sensitivity）
- **法线优先级：** raw STL facet → analytic fallback；upper `n_z>0`，lower `n_z<0`
- **normal source 编码：** 0=INVALID, 1=STL_ACCEPTED, 2=STL_REJECTED_BUT_USED, 3=ANALYTIC_FALLBACK
- **不继承 q-chain 20° reference-cone rejection**
- **正式 routing：** 当前仍为 alpha-sign；local-incidence 与 sheet-specific leeward recovery 是 additive diagnostic，不切换正式 pressure/edge-state/windward Taw/q-chain 路由
- **Leeward recovery mask：** `mask_leeward_<sheet> = (surface_class_<sheet> == -1)`；clean filtering 不进入字段合同
- **Leeward recovery fields：** upper/lower 分开的 freestream edge-state 与 `Taw_tpg_leeward_upper/lower` 已冻结；不存在 generic `Taw_tpg_l` 字段

## 20. Fluent Clean Leeward Contract（2026-07-18 冻结）

- semantic-valid 公共单源为 `semantic_valid_mask()`：`normal_source in {1,2}` AND `geometric_sheet in {UPPER,LOWER}` AND outward normal finite AND incidence_s finite AND `surface_class != INVALID`。projection gate 与 planform validity 不属于 semantic-valid。
- `planform_domain_valid = planform_parameterization_valid AND finite(x_over_c) AND finite(y_over_b) AND 0 <= x_over_c <= 1 AND 0 <= y_over_b <= 1`，两个归一化坐标均使用闭区间。
- `clean_eligible = projection_gate_pass AND semantic_valid_mask AND planform_domain_valid`。
- `clean_leeward_upper = clean_eligible AND geometric_sheet == UPPER AND surface_class == LEEWARD`；lower 公式将 sheet 替换为 LOWER；`clean_leeward_any = clean_leeward_upper OR clean_leeward_lower`。
- `normal_source` 1 与 2 均可进入 clean，0 与 3 由 semantic-valid 排除。q-chain 的 20° / `abs(n_z)>=0.45` 合同保持不变，但 `qchain_stl_accepted` 不属于 Fluent clean eligibility，也不是 clean predicate。
- 当前正式 Fluent clean 不含 nose cutoff、finite-width leading-edge buffer、exact trailing-edge exclusion、finite-width trailing-edge buffer、temperature filter，以及 pressure / y-plus / heat-flux / face-area filter。未来 buffer 只能由 mapping 或物理误差证据另行裁决。
- 正式 QA schema=`faceted3d-phase5a-fluent-clean-qa/v1`：point/projection-gate/semantic-valid/planform-domain-valid/clean-eligible=`21,250/21,250/14,841/21,240/14,841`；clean upper/lower/any=`186/0/186`；clean upper source 0/1/2/3=`0/15/171/0`；upper/lower overlap=0。
- 执行口径：formal projection dataset count=1；projection chunk count=8；exact kernel invocation count=8；canonical identity 后 projection reused=true，independent second projection=false；semantics adapter invocation count=2；clean builder invocation count=2。
- 跨工况 canonical geometry exact identity PASS；七个 clean arrays byte-exact；排除 provenance 后 clean QA JSON byte-exact。
- `clean_upper == raw_upper_leeward` 仅是当前两个相同几何、相同 `alpha=5°` 正式 QA 工况的结果，不是所有攻角的普遍恒等式。
- 本节只冻结 Fluent subset，不涉及 LF clean 或 LF→Fluent mapping；clean 不读取温度。

## 21. LF Clean Leeward Contract（2026-07-18 冻结）

- 构建前结构门禁为 `canonical_coordinate_identity = x_w_m exact-equal x_l_m AND span_w_m exact-equal span_l_m AND xc_w exact-equal xc_l AND yb_w exact-equal yb_l`。该门禁是整体 fail-closed 检查；失败直接抛出 `ValueError`，不生成逐点 identity mask。
- 逐点 `planform_domain_valid = finite(x_w_m) AND finite(span_w_m) AND finite(xc_w) AND finite(yb_w) AND 0 <= xc_w <= 1 AND 0 <= yb_w <= 1`。
- `semantic_valid_<sheet> = normal_source_<sheet> in {1,2} AND normal finite AND incidence finite AND surface_class_<sheet> != INVALID`。
- `clean_eligible_<sheet> = planform_domain_valid AND semantic_valid_<sheet>`。
- `clean_leeward_<sheet> = clean_eligible_<sheet> AND surface_class_<sheet> == LEEWARD`；`clean_any = clean_upper OR clean_lower`。
- LF clean predicate 不使用 `mask_w`、`mask_l`、`qchain_stl_accepted`；不增加 endpoint / row40 / tip filter、nose / LE / TE buffer、temperature、pressure、q、y-plus、face area 或任何新经验阈值。
- upper/lower 必须 disjoint，any 必须是 exact union；输出保持 canonical ordering，并是 owned、C-contiguous、read-only bool arrays。builder 不修改输入，不写保护输入，也不修改或污染 `solver.last_fields`。
- 两个正式 `alpha=+5°` case 均为 3,321 点：clean upper/lower/any=`256/0/256`，upper source 1/2/3=`22/234/0`，overlap=0；八个 masks 跨工况 byte-exact。
- 非 baseline `alpha=-5°` lower-sheet branch integration shakeout：clean upper/lower/any=`1/1443/1444`，upper source 1/2/3=`0/1/0`，lower source 1/2/3=`1443/0/0`，overlap=0，exact union PASS。它不进入 current baseline，不构成新的正式物理 validation case；upper 的 1 个 source-2 点符合冻结 predicate，不得描述为错误或强行删除。
- clean masks 不进入正式 72-field `fields.npz` schema，也不进入 74 项 runtime `solver.last_fields` cache；74 与 72 是不同作用域的合同，不得混写。
- Fluent clean 与 LF clean 均已完成；Phase 5B2 只读 mapping contract audit 已完成。正式 Fluent clean → LF clean geometry pairing、mapping QA、wall-temperature ingestion 与 leeward temperature error 均未完成。下一阶段唯一入口为 Fluent clean → LF clean geometry pairing 正式实现。

## 22. Fluent Clean → LF Clean Mapping Audit Decision

- 审计作用域：基于 `main@60e3473cc48d366671921ca246aaccf60f5a1fd1` 的只读 geometry/mapping contract audit；两正式工况 `ma6_a5_h30km` 与 `ma8_a5_h40km` 结果 byte-exact。该结论不是 mapping implementation、temperature ingestion、temperature comparison 或 model validation。
- 正式方向冻结为 Fluent clean → LF clean：每个 Fluent clean canonical source 查询一个 LF clean canonical target；mapping error domain 是 186 个 Fluent canonical source 点。
- 正式 metric 冻结为 P：exact-projected physical `(x, span)` metres 上的二维欧氏距离。推荐方向中 P 与 R assignment=`186/186` 相同，P 与 U assignment=`47/186` 相同；normalized metric 会实质重写 mapping topology，不因 collision 较低而自动更正确。
- Candidate P fingerprint：source/target=`186/256`，unique LF targets=`80`，target coverage=`31.25%`，collision excess=`106`，duplicate LF targets=`60`，maximum multiplicity=`4`，mutual nearest pairs=`80`，nearest exact ties=`0`；distance min/mean/median/p95/max=`0.323/8.180/7.349/17.752/21.042 mm`；within 20 mm=`183/186`，within 30 mm=`186/186`。这些是 geometry audit fingerprint，不是 acceptance gate；31.25% 不是失败，因为 LF 是更密的 target 网格。
- many-to-one allowed；LF target multiplicity 保留为 diagnostic。mutual nearest 仅作 diagnostic，不是 acceptance condition。禁止通过 injective/Hungarian assignment 强制改派；未来若要把 Fluent-side error 汇总到 LF 点集，另建 LF-side local aggregation layer。
- 当前不冻结 hard mapping-distance gate；20 mm、30 mm 与旧迎风 0.3 m gate 均不得成为正式 acceptance gate。当前不冻结 nose、LE、TE、root 或 outer-span edge buffer。
- `accepted` / acceptance mask 尚未定义；不得生成 `accepted=True` 等伪合同。temperature comparison 尚未开始，wall-temperature ingestion 与 leeward temperature error 均未完成。
- 架构边界保持：geometry pairing → mapping diagnostics → future acceptance policy → physical comparison。下一阶段只实现 Fluent clean → LF clean geometry pairing，不越级进入后续层。
