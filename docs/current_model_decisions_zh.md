# 当前 Faceted3D 冻结模型决策

> 更新：2026-07-20（Chapter 3.7A N3 技术退出认证收口）

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
- 本 exact-projection 合同只覆盖 Fluent geometry input、坐标合同、canonical identity 与 exact STL projection；Phase 4A projected-point raw geometry semantics、Phase 4B 真实 21,250 点 projected semantics integration、Phase 5A Fluent clean、Phase 5B1 LF clean、Phase 5C pairing、Phase 5D wall-temperature ingestion 与 Phase 5E source-level comparison 均已另行冻结并通过 formal QA。
- Phase 5E 只完成合同、identity、direct indexing、array semantics 与误差公式验证，未输出第一轮正式性能误差结论，不能声明 leeward model validated；freestream provider 仍是零阶 diagnostic baseline。

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
- Phase 5C Fluent clean → LF clean pairing QA、Phase 5D wall-temperature ingestion QA 与 Phase 5E source-level comparison QA 均已完成并 PASS。
- Phase 5E upper 以一个 Fluent source 为一行，完整保留 `186` 行与 `80` 个 unique LF targets 的 many-to-one 关系；不执行 target aggregation。lower 返回完整 typed-empty comparison。当前未形成第一轮正式性能误差证据。
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
- Fluent clean、LF clean、Phase 5C pairing QA、Phase 5D wall-temperature ingestion QA 与 Phase 5E source-level comparison QA 均已完成。comparison prediction 唯一使用 Group 8 `Taw_tpg_leeward_<sheet>` full-canonical field；`Tw_l=300 K` 不作为 prediction。

## 22. Fluent Clean → LF Clean Mapping Audit Decision

- 审计作用域：基于 `main@60e3473cc48d366671921ca246aaccf60f5a1fd1` 的只读 geometry/mapping contract audit；两正式工况 `ma6_a5_h30km` 与 `ma8_a5_h40km` 结果 byte-exact。该结论不是 mapping implementation、temperature ingestion、temperature comparison 或 model validation。
- 正式方向冻结为 Fluent clean → LF clean：每个 Fluent clean canonical source 查询一个 LF clean canonical target；mapping error domain 是 186 个 Fluent canonical source 点。
- 正式 metric 冻结为 P：exact-projected physical `(x, span)` metres 上的二维欧氏距离。推荐方向中 P 与 R assignment=`186/186` 相同，P 与 U assignment=`47/186` 相同；normalized metric 会实质重写 mapping topology，不因 collision 较低而自动更正确。
- Candidate P fingerprint：source/target=`186/256`，unique LF targets=`80`，target coverage=`31.25%`，collision excess=`106`，duplicate LF targets=`60`，maximum multiplicity=`4`，mutual nearest pairs=`80`，nearest exact ties=`0`；distance min/mean/median/p95/max=`0.323/8.180/7.349/17.752/21.042 mm`；within 20 mm=`183/186`，within 30 mm=`186/186`。这些是 geometry audit fingerprint，不是 acceptance gate；31.25% 不是失败，因为 LF 是更密的 target 网格。
- many-to-one allowed；LF target multiplicity 保留为 diagnostic。mutual nearest 仅作 diagnostic，不是 acceptance condition。禁止通过 injective/Hungarian assignment 强制改派；未来若要把 Fluent-side error 汇总到 LF 点集，另建 LF-side local aggregation layer。
- 当前不冻结 hard mapping-distance gate；20 mm、30 mm 与旧迎风 0.3 m gate 均不得成为正式 acceptance gate。当前不冻结 nose、LE、TE、root 或 outer-span edge buffer。
- `accepted` / acceptance mask 仍未定义；不得生成 `accepted=True` 等伪合同。Phase 5D wall-temperature ingestion 与 Phase 5E source-level comparison 已完成；comparison 不引入 gate、threshold、accepted mask、area weighting 或 target aggregation。
- 架构边界保持：geometry pairing → mapping diagnostics → physical comparison。当前 comparison 只冻结 source identity、direct indexing 与误差公式；freestream-recovery provider 仍是 diagnostic，是否升级等待后续独立裁决。

## 23. Chapter 3.4 / 3.5 正式 Evidence 决策（2026-07-20）

- 正式运行证据为 `runs/leeward_source_evidence/20260720T055647Z_af1f1f5395a9`，对应 Git SHA=`af1f1f5395a992bf8b9f439cf824376c209ab19b`，manifest raw SHA-256=`4db8b71bf79602ffdae12a71a345c251711b0b791ae7405b97105cffef4f0b90`；detached hash 验证通过。该目录是 ignored、长期保留的运行证据，不是 tracked baseline。
- 正式 registry 仅含 `ma6_a5_h30km` 与 `ma8_a5_h40km`。每个 case 的 upper 均为 `186` 个等权 Fluent source rows、`80` 个 unique LF targets，lower 均为 typed-empty；统计母体固定为 `fluent_source_rows_equal_weight`，many-to-one 行不按 target 去重，不使用 inverse-multiplicity weighting，也未生成 target-level error aggregation。
- signed error 方向固定为 `prediction - observation`。两个 case 内 prediction 均为 source-row constant；因此误差的行间中心化变化与 observation 的中心化变化符号相反。Case A 同时存在正、负误差行，Case B 的 `186` 行误差全部为正。
- 两个正式资产的 source canonical identity、authoritative projected coordinates、target canonical identity、pairing distance / dx / dspan 与 target multiplicity 逐元素相等。因此，本次 cross-case 差异不能归因于这些 recorded structures 在两资产之间发生变化；这不证明 mapping、geometry 或 pairing 绝对正确，也不排除共同 mapping/geometry bias。
- Chapter 3.4 与 Chapter 3.5 技术范围已完成。Case A 同时为 Mach 6 / 30 km，Case B 同时为 Mach 8 / 40 km，Mach 与高度混杂；不得把差异单独归因于 Mach 或高度。provider 物理正确性、provider 是否应修改、Fluent observation 质量或因果责任、windward/leeward 联合结论、模型性能接受性及物理机制均未证明。
- 正式 QA 的 integrity PASS 只表示程序、合同与资产完整性通过；display limits 不是 performance threshold，未建立模型性能 PASS/FAIL。N3c 触发证据继续保留，但 N3c 未正式启动；GATE A 未进入；provider 未修改。

## 24. Chapter 3.6 Evidence Package 决策边界（2026-07-20）

- Chapter 3.6A N3 exit-condition / GATE A evidence-package readiness audit 已完成，readiness=`READY_FOR_3_6B`。其含义仅为现有 formal leeward evidence 足以与 diagnostic windward context 在证据分层明确的 package 中并列，不需修改冻结合同、混合不可比数值或先启动 N3c，可以进入 3.6B package assembly；不表示 N3 已退出、Chapter 3 已完成或 GATE A 已开始。
- Chapter 3.6B evidence package assembly 与 boundary QA 已完成，Package 0–12 完整，package status=`PACKAGE_READY_FOR_GATE_A_REVIEW`。该状态只表示材料完整、可追溯、内部 identity 与数值无冲突且推论边界明确；不表示 GATE A 已开始或已裁决，不表示 A0/A1/A2/A3 已裁决，不表示 provider 应修改，也不表示模型性能 PASS/FAIL。
- evidence tier 冻结为：formal leeward evidence 属于正式 source-row evidence tier；windward evidence 为 `DIAGNOSTIC CONTEXT ONLY`、`NOT FORMAL SOURCE-LEVEL EVIDENCE`。两侧 signed relative error 的代数方向与 percent 单位可以对应，但 row identity、mapping direction、population、repeated-target weighting、provenance/integrity、registry/alignment 及 figure/display contract 不同。
- formal leeward 与 diagnostic windward 可以分层并列，但不得形成联合 population 或联合统计，不得直接数值排名，也不得通过图中颜色、面积或 fixed scale 进行跨表面性能比较。source-row population 不等于 unique-target population；package submission readiness 不等于 provider route decision；integrity PASS 不等于 performance PASS。
- 当前 Chapter 3.6 package 路径不要求启动 N3c；N3c 未启动，也未被永久取消。若未来要求同 identity、同 population、同 weighting、同 provenance 的跨表面联合数值比较，必须重新裁决是否正式启动 N3c。
- N3a / N3b 边界冻结为：证据数量不足、case 覆盖不足、变量混杂、需要新增可信 case 或补充正式诊断时，可能进入 N3a；只有发现 identity、data、geometry、mapping 或 evidence-chain 的具体错误时，才可能进入 N3b。当前不决定进入 N3a 或 N3b。

## 25. Chapter 3.7A N3 技术退出认证决定（2026-07-20）

- Chapter 3.7A `N3 Final Exit Certification and GATE A Entry Eligibility Audit` 只读审计已完成；N3 technical exit conditions=`CERTIFIED SATISFIED`，entry eligibility=`READY_TO_REQUEST_GATE_A_ENTRY`。
- 该资格只表示 Package 0–12 可以提交用户批准，并建议由 Opus 主持后续独立 GATE A review；用户尚未批准进入 GATE A，GATE A 尚未开始。当前战略节点继续保持 N3，在用户明确批准前不得改写为 GATE A。
- A0/A1/A2/A3 均未选择，provider 路线未裁决且 provider 未修改，模型性能没有 PASS/FAIL 结论；不得将 integrity PASS 或误差大小改写为 provider 足够、失败、必须升级或模型性能结论。
- N3c 当前采用“不可直接比较，但差异作为已知局限明确记录”。当前 package path 不要求先启动 N3c，N3c 未被永久取消；未来若提出跨表面同 identity、population、weighting、provenance 的联合数值比较、排名或统一统计，必须重新裁决是否启动 N3c。
- formal leeward 继续属于正式 source-row evidence tier；windward 继续为 `DIAGNOSTIC CONTEXT ONLY`、`NOT FORMAL SOURCE-LEVEL EVIDENCE`。两者必须保持 evidence-tier 隔离，禁止联合 population、联合统计、直接排名或通过颜色、面积与 fixed scale 作视觉性能比较。
