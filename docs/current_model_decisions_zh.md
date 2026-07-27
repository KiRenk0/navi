# 当前 Faceted3D 冻结模型决策

> 更新：2026-07-25（N7 bounded engineering-freeze candidate decision）

---

## 0. 仓库、production source identity 与 artifact 语义（冻结）

- `https://github.com/KiRenk0/navi.git` 的 GitHub `main` 是仓库 source of truth；正式活动工作区必须是该仓库经 Git 身份认证的 checkout root，恢复证据目录和历史目录不是活动开发入口。
- Production source identity authority 冻结为 committed Git `HEAD` tree；canonical source bytes 是 production path 在该 tree 中对应的 Git blob bytes，逐源 digest 为 `SHA-256(blob bytes)`，path 为 repo-relative POSIX path，schema=`git-head-tree-source-identity/v1`。
- commit SHA、whole-tree OID 与 branch 只用于 provenance/定位，不是 canonical source identity 的等值字段，也不得替代逐源 blob identity、inventory path identity 或 aggregate identity。
- Git 语义 clean 时，Windows CRLF 与 Linux LF checkout materialization 对 identity 中性；identity 读取 Git blob bytes，而不是 raw worktree bytes。
- staged、unstaged、deleted、renamed 或 inventory-matching untracked production source 均 fail closed；无关 ordinary untracked 不进入 source identity。
- source-only migration 只能来自 clean committed `HEAD`；禁止把 raw worktree hash 或 index-only hash 写入 baseline。
- 当前正式 source identity：inventory count=`69`；`inventory_paths_sha256=0cb3a5aa592256807a9e975e9213867c2b6b8337902450209a5421845e37edf8`；`aggregate_sha256=92114f8e2d798d3f6e574a68a710233463c0d30a4396a8839bf190dcb21cf38d`。
- 两个 current-v5 manifest 已完成 66→68 source-only migration；新增仅 `src/ref_enthalpy_method/analysis/__init__.py` 与 `src/ref_enthalpy_method/analysis/n6_3_layered_error_portrait.py`。provider、comparison、fields、summary、Groups 1–8、72-field arrays、numerical assets 与 `artifact_hashes_sha256` 均未改变。
- `runs/**`、`fluent_export/**`、CSV、STL、NPZ 与其他 binary artifact 保持原始字节；不得无授权执行全仓库 renormalize。
- raw artifact hash、parsed semantic contract、数值与字段合同、provenance path 必须分别表述，不能相互替代。
- baseline `summary.json` 当前只作为 legacy provenance；其 raw SHA-256 不参与 72-field numerical comparison，也不构成 model-performance assessment 或 physical-accuracy gate。current-v5 manifest 仍将该 raw SHA-256 作为 required artifact-integrity input：hash mismatch、artifact missing 或 invalid digest 会导致 artifact-integrity failure，并经 case FAIL 传播为 current regression overall FAIL。未来 summary v5 parsed-semantic promotion 是独立合同，与当前 raw-byte integrity gate 分离；artifact-integrity PASS 不得改写为 physical/model performance PASS。
- source identity promotion 只管理源码身份，不等于数值 baseline freeze。

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

## 13. 历史自定义来流对比工况

- 历史 30、35、40、45 km Fluent 对比工况均使用各自冻结的精确自定义来流；高度数字只是 nominal / historical label，不表示它们属于任何已验证大气模型。
- 这些工况只允许用于相同精确来流输入下的代码—Fluent 误差对比，不得写成标准大气验证或真实高度性能验证。
- 45 km 与 30/35/40 km 在证据资格上同类；资格取决于 exact input、observation 与 provenance，不取决于高度标签。
- 本 N3b 未处理任何 case 扩展或大气模型归属，也未改变 provider、comparison 或正式 registry。

## 14. 正式 CLI 高度参数域（2026-07-12）

- 正式 CLI 高度参数域：20–40 km；该运行配置不得反向解释历史 Fluent 自定义来流对比工况的证据资格。
- 未提供 explicit override 时，高度输入使用 USSA1976；提供 explicit `T_inf / p_inf` override 时，以成对记录的精确来流为准，即使同时给出高度也不再调用大气模型。

## 15. 正式默认大气（2026-07-12）

- CLI 输入 `h_m` 为几何高度
- 内部换算为位势高度，按 USSA 1976 标准大气分层计算
- `ussa1976.py` 是唯一活动计算实现；`isa1976.py` 已按用户 2026-07-26 裁决从活动树删除，不再存在 ISA fallback
- explicit `T_inf / p_inf` override 保留且必须成对提供；完整温压对的优先级高于高度，可用于复现 Fluent 实际输入；一旦使用 override，不得再把 nominal 高度标签表述为已验证大气模型

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

## 18. 2026-07-18 状态快照

- residual learning 在该时点尚未启动。
- Phase 5A Fluent clean 与 Phase 5B1 LF clean 均已完成；两者都是 geometry/semantics-only 只读派生 subset，不回写 raw semantic fields，也不读取温度。
- Phase 5C Fluent clean → LF clean pairing QA、Phase 5D wall-temperature ingestion QA 与 Phase 5E source-level comparison QA 均已完成并 PASS。
- Phase 5E upper 以一个 Fluent source 为一行，完整保留 `186` 行与 `80` 个 unique LF targets 的 many-to-one 关系；不执行 target aggregation。lower 返回完整 typed-empty comparison。该时点尚未形成第一轮正式性能误差证据。
- 只有未来另行重启 residual learning 时，才需要单独冻结 residual-label mapping、dataset schema 和 case-level validation protocol。
- 该时点 windward TPG 基线、大气、pressure 和 edge-state 已冻结；baseline schema=`current-tpg-baseline-regression/v5`，正式 `fields.npz` 为 72 fields，runtime `solver.last_fields` 为 74 项，Groups 1–8 零漂移，107 tests、87 subtests 与当时的 58 项 source identity 全部 PASS，`CURRENT REGRESSION OVERALL: PASS`。当前 source identity 由第 0 节的 65-source Git blob identity 取代。

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

## 26. GATE A=A0 与 N3a 当前决策（2026-07-20）

- GATE A 已完成，final branch=`A0`；N3 已完成，当前战略节点为 N3a。现有 formal evidence chain 完整且通过 Package 0–12 的 `13/13 PASS` 完整性认证。
- A1 未选择：未发现 identity、data、geometry、mapping、comparison 或 evidence pipeline 的具体错误。A2 未选择：没有用户批准的统一工程性能接受标准。A3 未选择：两个 formal cases 同时改变 Mach 与高度，无法证明稳定、可解释、受控的跨 case provider 系统偏差。
- A0 表示 case coverage 与变量控制不足，不等于 provider 失败、被否决、必须升级或模型性能 FAIL。当前 provider 保持 unchanged；没有建立性能 PASS/FAIL 或统一 threshold。
- N3a 只补可信 case 或必要诊断，复用冻结的 ingestion、pairing 与 comparison，不降低 provenance，不修改 provider；当前不返回 GATE A，任何后续 GATE A 动作都需要独立裁决与授权。
- 候选 M6/40 km、M8/30 km 只构成候选 2×2 Mach/高度控制设计，不是已批准 registry，也不表示已有可信 Fluent observation。第一步必须只读认证数据可用性、Fluent adiabatic-wall observation 与 provenance；认证失败时不得为凑矩阵降低标准。

## 27. N3a Candidate Manifest Schema 决策（2026-07-21）

- Opus decision=`DECISION_C_NEW_CANDIDATE_SCHEMA`；user approval=`GRANTED`；approved schema=`tpg-candidate-manifest/v1`。
- 排除方案 A：会为未注册 candidate 制造 false baseline / official identity。
- 排除方案 B：会扩展或重新解释冻结 v5 字段语义，使 baseline identifier 与 candidate identity 形成长期歧义。
- 排除方案 D：无法为未注册 candidate 提供正式的 source/artifact provenance。
- 选择方案 C：identifier 层身份真实；`current-tpg-baseline-regression/v5`、freeze/check 与两个正式 baseline 完全不变；改动纯增量、可回退，并复用既有 hash 核心。
- 本决定不是 provider change、baseline admission、registry admission、performance decision、N3a exit 或 strategy 节点变化。strategy v1.2 保持冻结，当前战略节点仍为 N3a。

## 28. N3a Candidate Explicit-Freestream Provenance 决策（2026-07-21）

- `tpg-candidate-manifest/v1` 已实现 candidate-only 显式 freestream provenance；candidate manifest CLI 以成对可选的 `--t-inf-k` / `--p-inf-pa` 接收 provenance，二者必须同时提供或同时省略，且必须为有限正值。
- runner 原本已支持显式 freestream；本次修复只保证复现命令使用正式 `--T_inf_K` / `--p_inf_Pa` 参数并记录真实值，不是 solver 物理能力或 v5 schema 变更。
- explicit candidate manifest 必须交叉校验 summary 的 `inputs.T_inf_K_override`、`inputs.p_inf_Pa_override`、`freestream.freestream_source`、`freestream.T_inf_K` 与 `freestream.p_inf_Pa`；source 必须为 `explicit_override`，并记录 `atmosphere.explicit_freestream_override=true`。显式 summary 缺少对应 provenance pair 时 fail-closed。
- 非显式 candidate 路径继续记录 `explicit_freestream_override=false`；candidate manifest 顶层字段集合不变。正式 v5 baseline、`CASES`、registry、freeze/check、source inventory、Groups 1–8 与 72-field contract 均未改变。
- 下一次唯一 M8/30 candidate generation 的用户批准显式输入为 `Mach=8`、`alpha=+5 deg`、几何高度 `30000 m`、`T_inf_K=226.509 K`、`p_inf_Pa=1197.0 Pa`；不得用仅按高度推导的大气值替代该 override。
- 修复已实现且独立 QA 已完成；M8/30 candidate generation 与 production candidate manifest 尚未执行，未 admission、未 promotion、未进入 formal comparison/evidence。provider 保持 unchanged，N3a 尚未退出，GATE A 未重新开启。

## 29. Exact Fluent Projection Accelerator 与 Geometry-Identity Cache（2026-07-22 冻结）

### Exact Fluent projection accelerator

- 原 brute-force exact point-to-triangle kernel、完整 closest-point 语义与 deterministic tie-break 均未改变；新增 array-based exact BVH 仅作为加速层，三维 AABB distance 是 Euclidean 真下界。
- exact/near-tie 继续使用 `_distances_equivalent`；等价距离候选由最小 canonical triangle index 获胜。fallback 仅限 BVH 内部 `RuntimeError`，输入 shape、dtype、finite domain、mesh identity 等合同错误 fail closed，不得进入 fallback。
- M8/30 目标 mesh（21,250 canonical points、6,341 triangles、gate=`0.005 m`）全量 accelerated-vs-reference differential PASS：triangle ID、projected XYZ、projection distance、raw normal、gate 与 canonical/source identity mismatch 全为 `0`；第二次完整 BVH deterministic rerun PASS。
- 同一目标 mesh brute-force/BVH runtime=`718.270169500/83.302107300 s`，完整投影 speedup=`8.6224729815×`（约 `8.62×`）；kernel calls 从 `134,746,250` 降至 `2,904,162`，visited fraction=`2.1552822435%`、reduction=`97.8447177565%`、fallback=`0`。

### Geometry-identity projection cache

- cache 只包含 `projected_xyz`、`triangle_id`、`raw_normal`、`projection_distance_m` 与 `projection_gate_pass` 等 geometry-derived projection payload，不包含 wall-temperature。geometry-only identity 与完整 CSV raw identity 必须分开表述：temperature-only CSV 值变化不改变 geometry identity；任一 geometry 字段发生 bit 变化必须拒绝复用。
- 正式 identity 冻结为：schema=`exact-projection-cache/v1`；algorithm=`n3a.5b-exact-bvh/v1`；Fluent geometry-only SHA-256=`a449b2367c10631eac7161c84393318911e1f21554429a6f69092d2c877b6c0b`；canonical geometry SHA-256=`f8e831b08dd86283bb69dc2f5be5fdb636e160a801ce97ec4d9382098b611c23`；STL raw SHA-256=`ac50ebee3f061080914128eb34fa59d1220fb20fec07b7f02ef649bcec4d728c`；triangle canonical SHA-256=`cdd2b4bb0d7a9e9dd423d56eb951b139c0cdcd1f0ebae3da1e535b2c65c9ba3f`；vehicle spec raw SHA-256=`877c1994fbaa7eef570a89b9fae36e8cda6ef1b6072e733b3a6a51578b7074cf`；sampling spec raw SHA-256=`39bed4302c18d67acb5b2b4184ea84a5201b1b877da093d515933cca4ede624f`；outline SHA-256=`a89155aa876e450741547d246f8206c7f0d9e0d1345d0c39a3b1320ca5165f78`。
- identity 还冻结 point count=`21,250`、loader triangle count=`6,341`、x offset=`0.03 m`、projection gate=`0.005 m`、coordinate convention=`solver-(x,span,up)-metres`、tie-break=`smallest-triangle-index-among-equivalent-distances;tie_abs_tol=1e-12;tie_rel_tol=1e-12` 以及各 payload 的 dtype、shape 与 content hash。
- file missing 是普通 cache miss；identity mismatch 抛 `CacheIdentityMismatchError`；manifest、array、hash、finite domain、gate consistency 或 triangle bounds corruption 抛 `CacheIntegrityError`。mismatch/corruption 不得静默 recompute 或覆盖。
- 公开 generation entry 为 `project_fluent_surface_with_cache(..., cache_path=..., geometry_identity_kwargs=..., write_cache=True)`；公开 load entry 为同一 orchestration API 在 cache 存在时的 fail-closed load path，底层严格 loader 为 `load_projection_cache(...)`。默认 `write_cache=False`，正式写入必须显式指定 `write_cache=True`。
- 正式再生输入为 `fluent_export/adiabatic_wall_csv/1197pa_226.509k_30km_5alpha_8ma.csv` 的 geometry fields、`new_spec/htv2_0628.stl`、`new_spec/outline_xz_right_0629.csv`、`specs/vehicles/htv2_faceted3d_0629.yaml`、`specs/sampling/engineering_full_wing_surface_grid_81x41.yaml`，以及冻结的 x offset、projection gate、schema、algorithm、coordinate convention 与 tie-break。cache 缺失时可由这些冻结输入和已提交实现重新生成。
- 正式 cache 路径=`runs/fluent_projection_cache/f8e831b08dd86283bb69dc2f5be5fdb636e160a801ce97ec4d9382098b611c23/projection_cache.npz`，size=`786,521 bytes`，SHA-256=`a82d7d56b01aaae8067cdfa2c3ba439f4d3cc7fcd537c0dedbb573cf4d6be3a7`。治理方式为 ignored external frozen run artifact：不 tracked、不执行 `git add -f`、不随普通 clone 分发、不绑定 CASE_REGISTRY、不 promotion 到 baseline/evidence，也不属于 canonical source data。

### Validation status 与边界

- full 21,250-point differential PASS；reference 与 accelerated 的 formal projection object、全部 projected semantics、Fluent clean、LF clean、upper/lower pairing、upper/lower wall-temperature observation downstream equivalence PASS。
- projection/BVH regression=`76/76 PASS`，cache regression=`29/29 PASS`，合计 `105/105 PASS`；failed/errors/skipped/xfail/warnings 均为 `0`。formal cache freeze PASS；two-process independent cache-load QA PASS，两个冷启动进程均 cache hit，BVH/brute-force/compute fallback/cache writer calls 全为 `0`，deterministic result JSON SHA-256 均为 `709405e8871f0eb08625e404a58b8725db1b526bdf8963764a2fe499bfc31b44`。
- 本节点未生成 comparison、未生成新 evidence、未进行 CASE_REGISTRY binding、未进行 candidate admission/promotion、未开展 45 km 结果处理。正式 cache 只是 projection 性能优化资产，不能解释为观测数据、正式 evidence 或 baseline。

## 30. M8/30 Exact Fluent Observation Binding（2026-07-23 冻结）

- M8/30 exact Fluent observation 已建立 tracked binding：CSV=`fluent_export/adiabatic_wall_csv/1197pa_226.509k_30km_5alpha_8ma.csv`，raw SHA-256=`5dc84e2dea4dc49a5f6ce777e71b8121c148b9490afeb83c98bd5ce022b3b865`，byte size=`3,123,901`，data rows=`21,250`，field=`wall-temperature`，unit=`K`。
- case identity 冻结为 Mach=`8.0`、alpha=`+5 deg`、geometric altitude=`30000 m`；custom freestream 为 `T_inf_K=226.509`、`p_inf_Pa=1197.0`，provenance=`user-confirmed custom project input`。上述 30 km 来流是用户自定义项目输入，不得使用标准大气 lookup、推算值或默认值覆盖。
- wall/coordinate semantics 冻结为 `adiabatic`、Fluent source convention=`(x,y,z)`、solver transform=`(x+0.030, span=y, up=z)`。
- public API 为 `FluentObservationBinding`、`build_m8h30_observation_binding`、`validate_observation_binding`。validator 按 fail-closed 边界校验 schema、required/unknown fields、严格类型（包括拒绝 bool-as-number）、有限值、路径与 repo containment、raw SHA、size、header、row count，以及 case、freestream、boundary、field/unit、coordinate/transform。
- binding 固定的是 exact CSV 与用户确认 case/custom-input 事实的 tracked association；它不自动证明完整 `.cas/.dat`、journal、transcript 或 Fluent project archive，也不表示 comparison eligibility、formal evidence、admission/promotion 或 N3a exit 已完成。
- current source identity 为 source count=`65`、source paths hash=`81f50d9015c3df397923352d3adb5b0d45dd85e01f3e9a66685c49a3fbf6a428`；唯一新增 production source 为 `src/ref_enthalpy_method/mapping/m8h30_comparison_inputs.py`。current v5 builder identity 为 `ma6_a5_h30km=71d86a8402b57665167e9cd1c47cdb40e5acefb6dff47317e9d8d0cb74806a2c`、`ma8_a5_h40km=e28f4b3710775f8b2536a9fa0b626c3f22ce8e1f24389f8f21b8c528a931d698`；变化仅来自新增 production source identity。historical 61-source candidate 未被改写。

## 31. M8/30 Comparison-Input Preparation（2026-07-23 冻结）

- 正式 registry-free preparation API 由 `ref_enthalpy_method.mapping` 公开导出：builder=`build_m8h30_comparison_inputs`，top-level bundle=`M8H30ComparisonInputs`，per-sheet bundle=`FluentLfTawComparisonInputs`，identity types=`M8H30CandidateIdentity` 与 `M8H30ProjectionCacheIdentity`。其唯一职责是准备 M8/30 production comparison 所需输入；不调用 production comparison builder，不执行 comparison，不生成 evidence。
- preparation 以 fail-closed 方式强制消费并验证 exact `FluentObservationBinding`：CSV path/size/raw SHA-256/header/row count，Mach=`8`、alpha=`+5 deg`、geometric altitude=`30000 m`，custom freestream `T_inf_K=226.509`、`p_inf_Pa=1197.0`、provenance=`user-confirmed custom project input`，wall condition=`adiabatic`、field=`wall-temperature`、unit=`K`，Fluent coordinate semantics 与 `(x+0.030, span=y, up=z)` transform 均必须精确匹配。
- candidate 链必须验证 `tpg-candidate-manifest/v1`、四文件 path/size/raw identity、case/custom-freestream identity 与 status=`unregistered_candidate`；projection 链必须消费 existing exact cache 并校验正式 geometry identity，固定 `write_cache=False`。随后继续验证 Fluent observation、Fluent clean、LF clean、Fluent→LF many-to-one pairing、observation/pairing canonical index identity，以及 `Taw_tpg_leeward_<sheet>` prediction identity。
- upper source rows=`186`；lower source rows=`0`，lower 为正式 typed-empty，upper/lower object 与 identity 严格分离。`Tw_l=300 K` 不得作为 adiabatic prediction fallback；缺少或错用 `Taw_tpg_leeward_upper` / `Taw_tpg_leeward_lower` 必须 fail closed。
- 独立 formal QA 结果为 focused=`154/154 passed`、full regression=`395/395 passed`、public import=`PASS`、`git diff --check=PASS`、production comparison calls=`0`。QA 内定向修正使 cache identity 直接绑定正式 `build_geometry_identity` 结果，没有复制第二套 geometry identity 算法。
- eligibility=`ELIGIBLE_TO_REQUEST_PRODUCTION_COMPARISON` 只表示后续可申请独立 production comparison；不表示 comparison 已执行、evidence 已生成、candidate 已 admission/promotion、M8/30 已进入 formal baseline、N3a 已完成或 GATE A 已重新裁决。
- 本入口未修改 `CASES` / registry，M8/30 继续为 `unregistered_candidate`；没有 admission/promotion、formal baseline 变更、production comparison 或 formal evidence。provider 保持 unchanged；historical candidate、exact CSV、candidate 四文件、exact projection cache、formal baseline/evidence、Groups 1–8 与 72-field serialization contract 均保持零漂移。

## 32. M8/30 Production Comparison 解释口径（2026-07-23 冻结）

- comparison unit 固定为 Fluent source row。upper 为 `186` 个 comparison source rows 映射到 `80` 个 unique LF primary targets；`186 → 80` 表示保留 many-to-one target multiplicity，不表示只有 80 个 comparison rows。source rows 不去重、不聚合，LF targets 也不去重。
- mutual nearest 只作 diagnostic，不得参与过滤。comparison 不使用 accepted mask 或 distance gate。lower 为正式 typed-empty comparison；六个正式数值数组均为 `shape=(0,)`、`dtype=float64`，不是 comparison failure。
- prediction 唯一使用 `Taw_tpg_leeward_upper`；不存在 `Tw_l` fallback。upper prediction=`2466.390470233011 K`，observation mean=`2419.6771732741936 K`。
- signed error 方向固定为 `prediction - observation`，mean=`+46.71329695881745 K`；signed relative error 固定为 `100 * signed_error_K / observation`，mean=`+1.953465971180283 %`。
- “30 km”仅为 historical / nominal label；`atmosphere_model=none / unverified`。本 comparison 只描述指定历史自定义来流输入下当前代码 prediction 与 Fluent observation 的 numerical difference，不构成 30 km 标准大气验证、真实飞行高度性能验证、大气恢复准确性验证或真实高度趋势。
- 当前没有用户批准的统一性能 threshold；上述数值仅为 descriptive facts，不能直接形成 provider PASS / FAIL。comparison 只产生内存对象，未生成 formal evidence 或持久 comparison asset，也不构成 registered candidate、promoted baseline 或 provider 裁决。

## 33. N6.1 正式覆盖矩阵、排除理由与 evidence tier（已冻结）

本节是 Formal core、Supplemental diagnostic、Windward diagnostic、Current-matrix excluded、historical ignored evidence 边界与 N6.2 execution gates 的唯一 tracked canonical authority；同一矩阵不得复制到其他文档。

### 33.1 Formal core

- `cases = ma6_a5_h30km, ma8_a5_h40km`；两个 case 保持既有正式 registry / formal-core 身份。
- `population = upper / leeward Fluent source rows`；`row identity = one Fluent source row per row`；many-to-one target multiplicity 完整保留，不按 LF target 去重或聚合。
- 覆盖只限 upper / leeward source-row population；`lower = typed-empty known limitation`，不得将 typed-empty 解释为零误差、性能 PASS 或覆盖完成。
- `atmosphere qualification = none / unverified`。nominal altitude label 不构成真实高度大气资格；runtime `isa1976` metadata 不得升级为 Fluent comparison 已验证大气模型的证明。

### 33.2 Supplemental diagnostic

- `case = ma8_a5_h30km`；`status = unregistered_candidate`；`role = upper / leeward supplemental diagnostic only`。
- `formal admission = no`；`baseline identity = no`；`formal-core aggregation = prohibited`；`persistent formal evidence = no`；`lower = typed-empty`。
- M8/30 不得自动 admission，不得升级为 registered baseline 或 formal evidence package，也不得与 Formal core 聚合为联合正式统计。
- M8/30 的既有身份仅为 historical in-memory production comparison 和 supplemental diagnostic。

### 33.3 Windward diagnostic

- `role = independent diagnostic context only`。
- `joint population with leeward = prohibited`；`joint statistics = prohibited`；`direct ranking = prohibited`；`unified performance PASS/FAIL = prohibited`。
- Windward 与 leeward 始终分层：不联合 population、不联合统计、不直接排名，也不产生统一性能 PASS/FAIL。

### 33.4 Current-matrix excluded

以下四类 case 不进入当前 N6.1 唯一最小覆盖矩阵：

1. 三个未授权 45 km cases；
2. M6/40；
3. A2 三工况之外的其他 Mach / alpha / nominal-altitude combinations；
4. 所有没有 approved registry、tracked observation provenance 和现有工程入口的 cases。

- `excluded` 只表示不进入当前 N6.1 最小覆盖矩阵，不表示永久失去证据资格。
- 45 km 与 30/35/40 km 属于同一 historical user-defined freestream 资格类别，不得因 nominal altitude label 将 45 km 永久失格。
- 45 km 当前排除仅因为未获读取授权、未进入 approved engineering inventory，且尚无可核验的 observation、ingestion、exact freestream binding 和 provenance 链。

### 33.5 Historical ignored evidence 边界

- historical formal evidence run 是 ignored、长期保留的运行证据，不是 tracked baseline。
- package 不在当前 HEAD tree 不自动构成 evidence-chain defect，也不得据此否定既有 historical evidence tier。
- 未来复用现存 package bytes 前，必须重新认证 provenance / hash。
- 未来生成新的 N6 formal package，必须绑定届时的 clean committed HEAD。

### 33.6 N6.2 execution gates

N6.2 official execution 前必须逐项满足以下七项门槛：

1. 恢复并认证 Git semantic clean 与 official porcelain hygiene；tracked porcelain、staged、unmerged、Git operation 和额外 worktree 必须为空；若保留治理链明确批准的 ordinary untracked 例外，它们必须逐项符合届时批准清单，且不得包含来源不明或 inventory-matching untracked；
2. M6/30、M8/40 的 observation-side 与 LF-side exact freestream binding provenance 可复现；
3. N6.2 开始前明确选择：认证复用 historical ignored evidence，或从 clean committed HEAD 生成新的 formal package；
4. 若 M8/30 需要重建 supplemental 数值，先认证 candidate / cache 正式来源，但不得自动 admission；
5. 不引入 performance threshold，不作 model performance PASS/FAIL；
6. Windward 与 leeward 始终分层；
7. lower typed-empty 不得解释为零误差、性能 PASS 或覆盖完成。

- exact freestream binding 是 N6.2 execution gate，不是追溯性否定既有 historical formal evidence 的 defect。
- 在该门满足前，不得生成新的 N6 formal comparison，也不得进行跨 case 物理归因。

### 33.7 明确非目标

- `provider = unchanged`
- `performance threshold = none`
- `N6.2 = not executed at this N6.1 freeze snapshot`；当前完成状态以第 35 节为准。
- `formal registry = unchanged`
- `baseline/manifest/summary/fields/hash = unchanged`
- `new comparison/evidence = none`
- 本节不作真实高度性能声明、标准大气验证声明、物理高度趋势声明或 provider performance PASS 声明。

## 34. N6.2a CSV Filename Identity 与 Exact Freestream Gate（2026-07-24）

- 当前 9 个既有 Fluent CSV 已迁移为带 historical custom P/T 的 filename identity；另有 3 个 45 km unregistered candidate CSV。CSV bytes 不因路径迁移而改变。
- 唯一 observation-side authority 是严格 basename parser 产生的不可变 identity：保留 basename、原始 numeric token、`Decimal` 数值和 case key。P/T 表示 historical user-defined comparison input；nominal altitude 只是历史标签，`atmosphere_model=none / unverified`，不得从高度或表面 `absolute-pressure` 替换 P/T。
- Parser 与 admission 分离。Approved formal observation registry 仅显式包含 `ma6_a5_h30km` 和 `ma8_a5_h40km`；`ma8_a5_h30km` 保持 `unregistered_candidate`、supplemental-only；三个 45 km filename 可解析并可做 raw identity 审计，但不自动进入 formal registry 或 N6.1 matrix。
- 正式命令必须从 binding 输出成对的 `--T_inf_K` / `--p_inf_Pa` 原始十进制 token：M6/30=`226.509 K / 1197 Pa`，M8/40=`251 K / 287 Pa`。命令构造前、summary/manifest 接收前均执行 exact、无 tolerance 的 pair/source gate；缺字段、非 `explicit_override` 或 pair 不一致一律 fail closed。
- Historical/current-v5 的旧 atmosphere/ISA 数值及其 artifact/path/hash 保持历史事实，不被迁移改写；但这些旧 pair 不能通过新的 exact custom-pair evidence gate。N6.2 formal package 在本历史时点尚未执行；当前完成状态以第 35 节为准。

## 35. N6.3 Canonical 分层误差画像（2026-07-25）

### 35.1 N6.3 完成时的历史状态快照（已由第 37 节 supersede）

以下状态仅记录 N6.3 完成、GATE C 尚未裁决时的历史现场；当前权威状态以第 37 节为准。

- `N6.0 = completed`；`N6.1 = completed`；`N6.2a = completed`；`N6.2b = completed`；`N6.3 = completed`；`N6.4 = completed`。
- `N6 strategic exit = signed / complete`；`N6 final sign-off = issued`；`GATE C = not decided`；`N7 = not entered`。N6 的完成含义以第 36 节的 bounded scope 为准。
- 正式入口为 `scripts/tools/n6_3_layered_error_portrait.py`，互斥模式为 `--execute` 与 `--validate-existing`。
- canonical validation：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
$env:PYTHONDONTWRITEBYTECODE = "1"

python -B scripts/tools/n6_3_layered_error_portrait.py `
  --validate-existing `
  --analysis-root runs/n6_3_layered_error_portrait/20260724T151247Z_e279af25b509_n6_3_layered_error_portrait
```

- 现有 canonical run 不得重复执行或覆盖；任何新 `--execute` 必须使用新的 run ID，且不得 overwrite 已存在目录。

### 35.2 Package identity

- canonical source package：`runs/n6_exact_custom_formal/20260724T111443Z_79ed536fc8c1_n6_exact_custom`；generation SHA=`79ed536fc8c1c7e19811ca744a14b78a732ff71a`；package manifest SHA-256=`dffd989a057c4481446482e0543e935209e8673f1a4468b343f1dfa5785bc314`；evidence manifest SHA-256=`b161086640e0e1c922fd2c02670f7e43f9b01363a797dfabb39c195f34157ac3`。
- canonical analysis package：`runs/n6_3_layered_error_portrait/20260724T151247Z_e279af25b509_n6_3_layered_error_portrait`；run ID=`20260724T151247Z_e279af25b509_n6_3_layered_error_portrait`；generation SHA=`e279af25b5090c0b95f04dfe9ccc9a16f7e43529`；analysis manifest SHA-256=`d425a3532ac87e5d4f571330ebecee18f733fa191d8fb511fd55bf2af09cc5f8`。
- analysis package 含 8 项 artifact inventory 与 1 个 manifest，共 9 files；`runs/n6_3_layered_error_portrait/` 下唯一 canonical run count=`1`。

### 35.3 Population、误差合同与描述性结果

- `formal_core` 仅含 `ma6_a5_h30km`、`ma8_a5_h40km` 的 upper/leeward Fluent source rows；每 case `186` rows、`80` unique LF primary targets、one Fluent source row equal weight；many-to-one 保留，lower typed-empty。
- `signed_error_K = Taw_tpg_leeward_K - wall_temperature_K`；`signed_relative_error_pct = 100 * signed_error_K / wall_temperature_K`；absolute metrics 取对应绝对值；standard deviation 使用 population `ddof=0`，quantile 使用 NumPy linear。
- M6/30：mean signed error=`14.858881266621484 K`，MAE=`17.53607206396338 K`，RMSE=`25.524606371024667 K`，over/under/exact=`136/50/0`。
- M8/40：mean signed error=`104.03134241675608 K`，MAE=`104.03134241675608 K`，RMSE=`104.4345380531835 K`，over/under/exact=`186/0/0`。
- bounded case2-minus-case1：MAE=`86.49527035279269 K`，RMSE=`78.90993168215883 K`，mean signed error=`89.1724611501346 K`，mean signed relative error=`3.0129585504982304 %`。
- 以上仅是指定 historical custom input bundles 下的 descriptive numerical and spatial facts，不是性能 PASS/FAIL，也不支持因果归因。
- physical x 与 span 各 5 bins；edges 来自两个 formal upper populations 的 union，并在两个 case 复用；区间 left-closed/right-open，最后一 bin right-inclusive，out-of-range fail closed。x counts=`[14, 20, 29, 35, 88]`，span counts=`[8, 24, 34, 58, 62]`。

### 35.4 Evidence tiers 与 canonical assets

- `formal_core` machine-readable assets：`formal_core/source_profiles.json`、`formal_core/spatial_bin_profiles.json`、`formal_core/bounded_case_comparison.json`。
- `formal_core` figures：`formal_core/figures/source_error_maps_fixed.png`、`formal_core/figures/error_distributions.png`、`formal_core/figures/coordinate_bin_profiles.png`。
- `diagnostic_only`：`diagnostic_only/multiplicity_profiles.json`。每 case multiplicity 1/2/3/4 分别为 `20/52/66/48` source rows 与 `20/26/22/12` targets，总计 `186` source rows → `80` targets；`acceptance_gate=false`，`formal_core_aggregation=prohibited`。
- formal source-row population 不去重；unique-target/multiplicity 仅作 diagnostic，不得以 unique-target weighting 替代 formal source-row weighting。
- `diagnostic_context`：`diagnostic_context/tier_references.json`。M8/30 保持 `unregistered_candidate`、upper/leeward supplemental diagnostic only，不 admission、不进入 baseline identity、不聚合进 formal core、不形成 persistent formal evidence。Windward 仅为 independent diagnostic context；禁止与 leeward 联合 population、联合统计或直接排名。

### 35.5 Source identity migration 与 QA

- production source inventory 完成 `66 → 68` source-only migration；新增仅两个 N6.3 analysis library paths。correction commit=`3187d56ab6ea2ed22ca80ec6925d95dfa81348a6`，migration commit=`4f616c654138bb9823f756576ede05f7e527a264`。
- current identity：count=`68`；`inventory_paths_sha256=31b47f1998348b9e82d702b517e14e1a2d2828596c665fb79af3466f0e7fd2f0`；`aggregate_sha256=fb9f8cb3a7c641cd526113c88bce465299ced8cd1e3b86b604e7e91f8cf5b609`。
- fields、summary、Groups 1–8、72 fields、numerical assets 与 artifact hashes 零漂移。
- independent QA：N6.3 `--validate-existing` PASS；160 focused tests + 11 subtests PASS；460 full pytest + 125 subtests PASS；failed/skipped/xfailed/xpassed/warnings 均为 0；CURRENT TPG OFFICIAL PASS；CURRENT REGRESSION OVERALL PASS；68/68 source identity PASS。统一裁决为 `N6_3_POST_MIGRATION_INDEPENDENT_QA_AND_FULL_REGRESSION_PASS`。
- QA/regression PASS 仅表示 program、contract、asset 与 regression integrity 通过，不等于 model performance PASS。

### 35.6 冻结解释与 known limitations

- `provider = unchanged`；`performance threshold = none`；`model_performance_assessment = not_performed`；`causal_attribution = not_supported`；`provider_systematic_bias_conclusion = not_established`。
- formal core 仅两个 case；freestream 为 historical user-defined comparison inputs；30/35/40/45 km 仅为 nominal / historical labels；`atmosphere_model = none / unverified`。
- Mach 与 P/T bundle 同时变化，不能单独归因于 Mach、pressure、temperature 或 nominal altitude，不能作真实高度趋势、标准大气验证、跨高度外推或 provider performance PASS。
- lower typed-empty；M8/30 supplemental-only；windward 是 independent diagnostic tier；无 performance threshold、无 causal attribution，provider systematic bias 未建立。
- N6.3 合法结论仅为：在两个指定 exact-custom historical input bundles 下，当前 Faceted3D baseline 与 Fluent upper/leeward observations 之间的 source-row 描述性误差、空间结构、many-to-one mapping diagnostic 和可复现回归事实。

## 36. N6.4 Final Canonical Certification 与战略出口历史状态（2026-07-25；已由第 37 节 supersede）

- `N6.0–N6.4 = complete`；`N6 strategic exit = signed / complete`；`N6 final sign-off = issued`。formal bounded scope 已接受为 completed N6 evidence scope，GATE C entry evidence index 已完成。
- provider unchanged；formal-core scope unchanged：仅 `ma6_a5_h30km` 与 `ma8_a5_h40km` 的 upper/leeward Fluent source-row populations；每 case `186` rows → `80` unique LF targets，many-to-one 保留。M8/30 supplemental-only、45 km tracked candidates、windward independent diagnostic context、lower typed-empty 与 external projection cache exclusion/reproducibility boundary 均不变。
- known limitations retained：formal cases only 2、formal surface only upper/leeward、lower typed-empty、historical custom freestream / atmosphere none-unverified、变量混杂、performance threshold none、causal attribution not supported、provider systematic bias conclusion not established。
- `GATE C decision = NOT DECIDED`；`GATE C approval = NOT ISSUED`；`engineering freeze = NOT APPROVED`；`N7 = NOT ENTERED`；`release/tag = NOT CREATED`。
- 下一项允许的战略动作仅为在独立授权下 request / conduct GATE C review；N6 exit 不自动开始 GATE C，不自动批准 engineering freeze，也不自动进入 N7。
- 包含最终认证文档的 main SHA 不在文档中自引用；其权威身份由 Git ref、真实远端认证、N6.4 Git closeout report 与后续 current handoff 固定。
- 本节保留 N6 closeout 当时的 GATE C/N7 状态作为历史事实；current GATE C/N7 authority 已由第 37 节 supersede，不得继续把本节的历史“下一步”解释为 current action。

## 37. N7 OPTION 3 Bounded Engineering-Freeze Candidate 决策（2026-07-25）

- technical base=`e3ad9d51482c5ddfb085c9c06cd3345f54a964ed`；`GATE C = COMPLETE`；selected branch=`OPTION 3 bounded/degraded freeze`；bounded engineering-freeze scope=`APPROVED`；`N7 entry = AUTHORIZED`。
- 第 33 节继续作为 detailed evidence-tier authority，任何 tier、case allocation、population、mapping topology、exclusion 或 non-admission 状态均不在本节复制或重裁。本节只新增 superseding governance state 与 N7 candidate 门禁。
- Approved bounded scope 仅覆盖 `ma6_a5_h30km`、`ma8_a5_h40km`，alpha=`+5°`、surface/region=`upper/leeward`；每 case formal population 为 `186` 个等权 Fluent source rows，映射到 `80` 个 unique LF primary targets。many-to-one 保留；80 targets 只表示 mapping topology，不是等权 formal population。
- freestream 继续是 historical exact-custom comparison inputs；`atmosphere_model=none / unverified`；nominal altitude 不构成 validated atmosphere 或真实高度性能证据。
- Formal core、M8/30 supplemental diagnostic、windward independent diagnostic context、three 45 km tracked candidates、formal lower typed-empty known limitation 与 external projection cache distribution/replay exclusion boundary 均保持第 33 节既有身份，不得自动提升、降级、合并或重命名。
- provider unchanged；performance threshold none；physical-accuracy gate none；formal registry/bindings、baseline、manifests、Groups 1–8、72-field contract、solver/API/comparison identity、source/artifact hashes 与 numerical/binary assets unchanged。
- `N7 candidate implementation = COMPLETE`；`independent QA = NOT YET COMPLETED`；`engineering freeze completion = NOT YET CERTIFIED`；`user final freeze approval = NOT YET GRANTED`；`main closeout = NOT YET COMPLETED`；annotated tag 与 GitHub release 均未创建。
- 本 candidate 是 exact 7-path docs/governance-only change。integrity/regression/focused validation PASS 只证明 program、contract、asset 与 candidate governance consistency，不等于 model performance PASS、physical-accuracy validation、independent QA 或 final engineering-freeze completion。
- N7 tracked certification/change-gate authority 为 `docs/n7_bounded_engineering_freeze_certification_zh.md`。后续仅可在独立授权下执行 read-only independent QA；不得从本 candidate 自动进入 final approval、main closeout、tag、release 或 N8。

## 38. N8 Taw Surface v3 法向与投影缓存决策（2026-07-27）

### 38.1 法向责任

- 设计上应连续的 N8 Taw surface 不能继续用 piecewise-constant STL face normal 作为局部入射和 windward slope 的最终输入；N8 必须使用连续法向。
- 当前权威几何没有完整解析曲面方程。常量 faceted reference slope 会抹掉鼻部/前缘曲率，因此不能冒充解析法向或替代 STL 局部几何。
- 正式实现是 `stl-angle-weighted-continuous-normal/v1`：sheet 隔离、角度加权顶点法向、三角形内重心插值、20° crease preservation。它是连续工程重建，不宣称 exact CAD analytic recovery。
- `normal_out` 驱动 N8 incidence、surface class 和 `sx=-nx/nz`、`sy=-ny/nz`；`stl_face_normal_out`、`stl_face_incidence_s`、`normal_smoothing_angle_deg` 与 `triangle_id` 是强制审计字段。
- 冻结 Group 8、正式 solver alpha-sign routing、current-v5、N6/N7 历史产品不回算。N8 v3 是 additive surface-product contract。

### 38.2 Provider 与显示

- dispatch schema=`n8-taw-dispatch/v3`；`s<=0` recovery，`0<s<0.05` 为 C1 smoothstep enthalpy blend，`s>=0.05` windward。
- 数学零线附近可因真实曲率出现极小符号闭区；`s=0` 处权重和一阶导数均为零，不产生旧式 Taw 交替跳变。不得用 provider 色块数量代替 Taw 连续性校验。
- flat original-triangle rendering、geometry reason、candidate fields 和 blend weight 继续为强制合同。

### 38.3 Canonical projection reuse

- 精确投影只依赖 canonical solver coordinates、STL triangles、坐标合同和 gate，不依赖 CSV source-row order 或 cellnumber。
- `project_fluent_surface_with_cache` 默认仍用 `source_geometry` 严格作用域；N8 显式使用 `cache_identity_scope=canonical_geometry`，作用域写入 cache manifest，scope mismatch fail closed。
- 12 份 N8 CSV 的 canonical coordinate SHA-256 均为 `f8e831b08dd86283bb69dc2f5be5fdb636e160a801ce97ec4d9382098b611c23`，因此只执行一次 exact projection；各 CSV 的 source-row mapping 与 temperature ingestion 仍独立执行。

### 38.4 任务边界

- 已完成任务 3、4、5、6：首次异常层、根因、全链修复设计、实现/测试/12 工况产品验证。
- 下一任不得把旧任务 5/6 解释为待办。除非输入身份或合同发生新变化，也不得重做任务 3/4。
- 任务 7 中 Git 暂存、提交、推送、合并、tag、release 仍未授权；测试 PASS 不自动授权这些动作。

## 39. N8 Geometry-Domain v4 闭合决策（2026-07-27）

### 39.1 域定义

- N8 current product 由 `n8-taw-domain-topology/v1` 定义，不再把 legacy 81x41 结构网格的 quad-validity 当作最终表面边界。
- product node table 只包含 authoritative graph-skin nodes；legacy phase9 geometry failures 保留为 typed exclusion audit。
- `triangle_node_ids` 是渲染、sheet isolation 和 local mapping support 的共同连接合同；不得重新引入 reshape 或任一坏点遮整个 quad 的边界语义。

### 39.2 当前发布

- summary schema 升为 `n8-taw-run-summary/v4`；dispatch/normal schema 保持 `n8-taw-dispatch/v3` 与 `stl-angle-weighted-continuous-normal/v1`。
- 当前目录唯一指向 `runs/n8_taw_surface/*_phase13_geometry_domain_v4`。
- 12/12 工况均为 9,663 nodes、18,110 triangles、333 typed exclusions、9,663/9,663 provider-valid。
- 每工况产物合同为 13 件：原 11 件加 upper/lower actual-range signed-relative-error PNG。
- 固定误差图保持 ±10%；auto-range 只使用有效有限 comparison rows，并把实际 min/max 写入 summary contract。

### 39.3 闭合与冻结边界

- G1、G2、G3、G4 全部 PASS；最近全量回归 `508 passed, 137 subtests passed`。
- frozen Group 8、current-v5、N6/N7 history、provider、registry、performance threshold 和正式 baseline 均未改变。
- v4 supersede v3 作为 N8 current product 入口；v3/phase9 和 phase10-phase12 只保留历史诊断意义，不得在当前文档中继续称为最终产品。
