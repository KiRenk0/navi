# Faceted3D 当前工程状态

> 更新：2026-07-19（Phase 5B2 Mapping Contract Audit 收口）

---

## 1. 正式工作区与源码身份

- 正式远端：`https://github.com/KiRenk0/navi.git`。
- 当前正式本地活动工作区：`E:\navi_clean`。
- GitHub `main` 是当前 source of truth。Phase 5B1 实现落地主线的代码提交为 `3a7922518cb05533c779a11eb0eb3a4d3f653f32`；后续 docs-only 提交不改变该实现身份或数值合同。
- `E:\Faceted3D_recovery_hold_20260715`、`E:\Faceted3D_recovery_work_20260715` 仅为只读恢复证据，`D:\ref\reference-enthalpy_03_12_26-main` 仅为历史资料；三者都不是活动工作区或正式来源。

活动 Python、Markdown、YAML 等文本按 `.gitattributes` 使用 LF。`runs/**`、`fluent_export/**`、CSV、STL、NPZ 与其他 binary artifact 保持原始字节，不执行无差别 normalization；未经单独授权不得执行全仓库 renormalize。

## 2. 当前正式模型

- 正式高度参数域：20–40 km；30、35、40 km 使用 1976 标准大气口径，CLI 输入几何高度并在内部换算位势高度。
- Route A-TPG 是唯一正式且唯一可运行的 thermodynamic baseline；CLI 不提供 thermodynamics 选择。
- TPG Taw 固定使用 fully turbulent `Pr^(1/3)` recovery，与 q-chain transition weighting 解耦。
- pressure closure 冻结为 `newtonian_like`，`A=0.38`、`n=1.15`；transition 默认 `step`；`chord_min_m=0.02 m`。
- 正式 alpha-sign windward/leeward routing 未改变；local-incidence 是 frozen additive diagnostic，不接管正式 routing。

## 3. Current baseline 与 regression

正式 baseline 位于 `runs/current_baseline_snapshot/tpg/`：

- schema：`current-tpg-baseline-regression/v5`；
- cases：`ma6_a5_h30km`、`ma8_a5_h40km`；
- `fields.npz`：72 fields；
- Groups 1–8：全部 PASS，全部 `max_abs_diff=0`；
- Group 8 semantic QA：PASS；
- endpoint/metadata：PASS；
- source identity：58/58 PASS；
- tests：107/107 PASS（另有 87 subtests PASS）；
- overall：`CURRENT REGRESSION OVERALL: PASS`。

唯一 current regression 命令为 `python scripts/tools/current_baseline_regression_check.py`。该 PASS 只证明 harness 实际执行的数值、字段、semantic QA、endpoint/metadata 与 58 项 source identity gate，不得扩大解释为未执行的 validation 或 artifact gate。

### 3.1 Source identity promotion

source identity promotion 只收口源码身份，不等于数值 baseline freeze。Phase 5A Fluent clean 与 Phase 5B1 LF clean 均属于 additive geometry/mapping infrastructure。`fluent_clean.py`、公开 `semantic_valid_mask()` 和 `lf_clean.py` 均不进入 `fields.npz`，不增加 72-field schema，不改变 Groups 1–8 数值。Phase 5B1 仅将 `lf_clean.py` 纳入 source identity；当前共 58 项 source identity PASS。

## 4. Group 8 能力与边界

Group 8 冻结了 18 个 sheet-specific leeward freestream-recovery 字段，upper/lower 分开输出 mask、freestream edge-state 与 TPG recovery temperature。provider 使用 freestream edge-state + TPG recovery；这是 zero-order diagnostic，而不是最终背风温度模型。

- raw mask 唯一定义为 `surface_class_<sheet> == -1`；local-incidence diagnostic 与正式 alpha-sign routing 相互独立。
- 当前正攻角 baseline/shakeout cases 的 formal lower mask 为 0；这是这些工况的分类结果，不表示 lower sheet 永远没有 leeward 区域。
- legacy `Tw_l`、`q_l`、`St_l`、`Re_ns_l` 仍是 fixed-wall legacy chain，与 Group 8 完全解耦。
- legacy `Tw_l` 不能用于对比 Fluent adiabatic `Tw`；不存在通用 `Taw_tpg_l`，只有 `Taw_tpg_leeward_upper/lower`。
- 尚未完成与 Fluent clean-leeward 的正式映射和误差验证；不得声称背风温度模型已经 CFD validated，不得报告 leeward temperature error。

## 5. `summary.json` 当前限制

当前 baseline `summary.json` 仍是 legacy provenance artifact：

- baseline summary 的 `outputs_available` 为 56 项；
- 当前 official CLI candidate summary 的 `outputs_available` 为 74 项；
- `fields.npz` 正式 schema 为 72 项；
- summary 仍可能保存旧绝对路径与旧 `run_dir` provenance；
- summary raw SHA-256 不进入当前 regression overall gate；
- endpoint/metadata PASS 不表示 baseline summary 与当前 candidate summary 在 raw 或 parsed 层面完全一致。

因此当前 summary 只用于 legacy provenance。summary v5 parsed-semantic promotion 尚未执行；后续应冻结 parsed semantic contract，而不是跨环境 candidate raw hash。本轮未修改 summary、manifest 或 regression harness。

## 6. Phase 4A projected-point geometry semantics

Phase 4A 已完成 projected-point geometry semantics 纯层，职责只覆盖投影点的 raw 几何语义：

- triangle-level sheet 编码冻结为 `INVALID=-1`、`OTHER=0`、`UPPER=1`、`LOWER=2`。
- sheet identity 来自正式 `SurfaceSlopeSampler` 的 triangle selection 语义；不使用 Fluent 原始 `z` 正负，不使用 triangle winding 或 raw-normal `n_z` 正负猜测 sheet。
- 原 `sample_upper_lower()` 六字段合同保持不变；新增采样方法额外返回 triangle ID。
- outward normal 与 incidence 复用 `local_incidence.py`；geometric sheet 和 aerodynamic incidence class 是独立字段，upper 不自动等于 leeward。
- q-chain acceptance 已统一到共享模块：`max normal angle=20°`、`min abs(n_z)=0.45`，两项均按闭区间接受。
- `x/c`、`y/b` 使用 projected point；outline 为优先正式 planform 来源，triangle planform 为 fallback。raw 参数不取绝对值、不裁剪。
- 输出数组 owned、C-order、read-only，并保持输入顺序。

当前验证为 107/107 tests PASS（另有 87 subtests PASS）、58/58 source identity PASS、schema v5、72 fields、Groups 1–8 全部 `max_abs_diff=0`、`CURRENT REGRESSION OVERALL: PASS`。

### 6.1 Phase 4B Fluent projected semantics integration

Phase 4B 已完成 `FluentSurfaceGeometry → FluentSurfaceProjection → Fluent projected-semantics adapter → deterministic geometry-only QA`。正式 QA 使用 21,250 个 Fluent canonical points、6,341 个 STL triangles 与闭区间 `distance <= 0.005 m` projection gate；gate pass=21,250，gate fail=0。

- geometric sheet：UPPER=7,325，LOWER=7,516，OTHER=5,703，INVALID=706。
- normal source：0 invalid=6,409，1 STL accepted by q-chain=10,006，2 STL rejected but used=4,835，3 analytic fallback=0。
- surface class：windward=13,971，leeward=186，near-tangent=684，invalid=6,409。
- semantic-valid=14,841，semantic-invalid=6,409；semantic-valid 只由 sheet、normal source、normal/incidence finite 与 surface class 定义，明确不包含 projection gate 或 planform validity。
- planform-invalid=10；这 10 个点没有并入 semantic-invalid。`x/c` finite=21,240/21,250、范围约 `[0.000282075, 0.999009290]`，`y/b` finite=21,250/21,250、范围约 `[0.000456603, 0.999003501]`，两者均无小于 0 或大于 1 的 finite 值。
- 正式 projection dataset count=1；exact kernel invocation count 等于运行时 projection chunk count（本次为 8）。第二工况仅在 canonical geometry exact identity 成立后复用 projection，未执行独立第二次 projection。

### 6.2 Phase 5A Fluent clean leeward contract

Phase 5A 已将 Fluent clean 冻结为 raw projected semantics 上的 geometry-only 只读派生 subset；保持 canonical ordering，不回写 raw semantics，也不读取温度。

- semantic-valid 公共单源为 `semantic_valid_mask()`：`normal_source in {1,2}`、geometric sheet 为 UPPER/LOWER、outward normal 与 incidence finite、surface class 非 INVALID；projection gate 与 planform validity 不属于 semantic-valid。
- `planform_domain_valid = planform_parameterization_valid AND finite(x_over_c) AND finite(y_over_b) AND 0 <= x_over_c <= 1 AND 0 <= y_over_b <= 1`，边界为闭区间。
- `clean_eligible = projection_gate_pass AND semantic_valid_mask AND planform_domain_valid`。
- upper/lower clean 分别在 `clean_eligible` 上要求对应 geometric sheet 与 `surface_class == LEEWARD`；clean any 为二者并集。
- `normal_source` 1 与 2 均 eligible，0 与 3 由 semantic-valid 排除。q-chain 的 20° / `abs(n_z)>=0.45` 合同保持不变，但 q-chain acceptance 不是 Fluent clean predicate。
- 正式 QA schema=`faceted3d-phase5a-fluent-clean-qa/v1`：point/projection-gate/semantic-valid/planform-domain-valid/clean-eligible=`21,250/21,250/14,841/21,240/14,841`；clean upper/lower/any=`186/0/186`；clean upper source 0/1/2/3=`0/15/171/0`；upper/lower overlap=0。
- formal projection dataset count=1；projection chunk count=8；exact kernel invocation count=8；canonical identity 后 projection reused=true，independent second projection=false；semantics adapter 与 clean builder invocation count 均为 2。
- 跨工况 canonical geometry exact identity PASS；七个 clean arrays byte-exact；排除 provenance 后 clean QA JSON byte-exact。
- `clean_upper == raw_upper_leeward` 仅是当前两个相同几何、相同 `alpha=5°` 正式 QA 工况的结果，不是所有攻角的普遍恒等式。
- 当前 clean 不含 edge buffer、temperature filter 或 pressure / y-plus / heat-flux / face-area hidden filter；未来 buffer 由 mapping 或物理误差证据另行裁决。

### 6.3 Phase 5B1 LF clean leeward contract

Phase 5B1 已将 LF clean 冻结为 canonical LF 点上的 geometry/semantics-only 只读派生 subset。数据流合同如下：

```text
构建前结构门禁：

canonical_coordinate_identity =
    x_w_m exact-equal x_l_m
    AND span_w_m exact-equal span_l_m
    AND xc_w exact-equal xc_l
    AND yb_w exact-equal yb_l

该门禁是整体 fail-closed 检查；失败直接抛出 ValueError，
不生成逐点 identity mask。

planform_domain_valid =
    finite(x_w_m)
    AND finite(span_w_m)
    AND finite(xc_w)
    AND finite(yb_w)
    AND 0 <= xc_w <= 1
    AND 0 <= yb_w <= 1

semantic_valid_<sheet> =
    normal_source_<sheet> in {1,2}
    AND normal finite
    AND incidence finite
    AND surface_class_<sheet> != INVALID

clean_eligible_<sheet> =
    planform_domain_valid
    AND semantic_valid_<sheet>

clean_leeward_<sheet> =
    clean_eligible_<sheet>
    AND surface_class_<sheet> == LEEWARD

clean_any = clean_upper OR clean_lower
```

- source policy：`normal_source` 1/2 eligible，0/3 excluded；canonical `w/l` coordinate identity 是 fail-closed 结构门禁。
- upper/lower 必须 disjoint，any 必须是 exact union；输出保持 canonical order，并是 owned、C-contiguous、read-only bool arrays。
- builder 不修改输入，不写保护输入，也不修改或污染 `solver.last_fields`。clean masks 不进入 `fields.npz`。
- predicate 不包含 `mask_w`、`mask_l`、`qchain_stl_accepted`、endpoint / row40 / tip filter、nose / LE / TE buffer、temperature、pressure、q、y-plus、face area 或任何新经验阈值。
- 两个正式 `alpha=+5°` case 均为 3,321 点：clean upper/lower/any=`256/0/256`，upper source 1/2/3=`22/234/0`，overlap=0；八个 masks 跨工况 byte-exact。
- 非 baseline `alpha=-5°` lower-sheet branch integration shakeout：clean upper/lower/any=`1/1443/1444`，upper source 1/2/3=`0/1/0`，lower source 1/2/3=`1443/0/0`，overlap=0，exact union PASS。它不进入 current baseline，也不构成新的正式物理 validation case；upper 的 1 个 source-2 点符合冻结 predicate，不是错误，不应强行删除。
- `solver.last_fields` runtime cache 仍为 74 项；正式 `fields.npz` 仍为 72-field schema。两者作用域不同，clean masks 均不进入其中。

### 6.4 Phase 5B2 mapping contract audit 与当前能力边界

Phase 5B2 是基于 `main@60e3473cc48d366671921ca246aaccf60f5a1fd1` 的只读 geometry/mapping contract audit，不是正式 mapping 实现。两正式工况 `ma6_a5_h30km`、`ma8_a5_h40km` 的几何 pairing 审计结果 byte-exact。

- Phase 5B2 mapping contract audit：完成。
- 正式 pairing implementation：未完成。
- mapping QA implementation：未完成。
- wall-temperature ingestion：未完成。
- leeward temperature error：未完成。
- direction：Fluent clean → LF clean。
- metric：exact-projected physical `(x, span)` 二维欧氏距离。
- duplicate policy：many-to-one allowed；target multiplicity 仅作 diagnostic。
- mutual nearest：diagnostic only，不是 acceptance condition。
- injective/Hungarian assignment：禁止用于正式 pairing。
- hard mapping-distance gate：未冻结；20 mm 与 30 mm 仅为观察统计。
- edge buffer：未冻结；nose / LE / TE / root / outer-span buffer 均未定义。
- mapping error domain：186 个 Fluent canonical source 点。

当前门禁保持 107/107 tests、87 subtests、58/58 source identities、runtime/formal=`74/72`、schema v5、Groups 1–8 zero drift，`CURRENT REGRESSION OVERALL: PASS`。下一阶段唯一入口为 Fluent clean → LF clean geometry pairing 正式实现；当前不能宣称 mapping implementation complete、temperature error 已可计算或 leeward model validated。

### 6.5 Repository hygiene（2026-07-18）

Phase 4A 后仓库卫生审计已完成：删除 3 份已被 canonical docs 替代、且无 active reference 的根目录旧文档，并清理本地 Python cache。正式 CLI、源码、tests、specs、Fluent 输入与 current baseline 入口均未变化；该阶段的 84/84 tests、55/55 source identity、schema v5、72 fields 与 Groups 1–8 零漂移均通过。本轮未修改物理链、数值 baseline、manifest、summary 或 artifact hash。

## 7. 当前禁止项

- 不进入 residual learning、GPR 或 MoE。
- 不扩展 45 km/50 km active domain；`ma8_a10_h50km` 仅为域外 reserved legacy stress/reference case。
- 不做大规模 pruning，不重构 Group 6，不修改 pressure、TPG 或正式 windward routing。
- 不调整冻结物理合同，不用 manifest 更新掩盖源码或数值漂移。
- 在 Fluent clean → LF clean geometry pairing 与 mapping QA 完成前不计算或发布背风温度误差。
