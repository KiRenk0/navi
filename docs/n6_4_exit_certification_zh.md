# Faceted3D v2 N6.4 最终退出认证

> 文档类型：tracked final canonical N6 exit certification
> implementation base：`main@5c6e0b56f20a33d431ec1e94e3aa216667983452`
> initial certification commit：`3f818aa93c05baf79bc6e83d42b2610f375c9df9`
> independently audited corrected HEAD：`f088d88eb409a5462451b81d27beac92bce528ae`
> independent QA result：`N6_4_INDEPENDENT_QA_AND_FULL_REGRESSION_PASS`
> 当前状态：`N6.4 COMPLETE`；`N6 strategic exit SIGNED / COMPLETE`

## 1. 文档身份与职责

```text
document role = N6.4 tracked final canonical coverage / exclusion / limitations / reproducibility / exit certification
implementation base SHA = 5c6e0b56f20a33d431ec1e94e3aa216667983452
initial certification commit = 3f818aa93c05baf79bc6e83d42b2610f375c9df9
independently audited corrected HEAD = f088d88eb409a5462451b81d27beac92bce528ae
independent QA result = N6_4_INDEPENDENT_QA_AND_FULL_REGRESSION_PASS
N6.4 status = COMPLETE
N6 strategic exit = SIGNED / COMPLETE
N6 final sign-off = ISSUED
formal bounded scope = ACCEPTED AS THE COMPLETED N6 EVIDENCE SCOPE
GATE C entry evidence index = COMPLETE
eligibility = ELIGIBLE_TO_REQUEST_GATE_C_REVIEW
GATE C decision = NOT DECIDED
GATE C approval = NOT ISSUED
engineering freeze = NOT APPROVED
N7 = NOT ENTERED
release/tag = NOT CREATED
final main identity = the Git commit containing this final certification,
                      authenticated by the N6.4 Git closeout report
                      and the subsequent current handoff
```

本文是 N6.4 coverage、evidence tier、exclusion / non-admission、engineering limitations、third-party reproducibility 与 N6 exit-condition 的统一 tracked canonical 载体。本文绑定已有 N6.1、N6.2b、N6.3、current-v5 baseline、M8/30 supplemental、45 km candidates、windward diagnostic 与 formal lower typed-empty 事实，不生成新的数值证据、package、baseline、validator 或 generator。

本文签发 bounded scope 下的 N6 final canonical certification。它不作 GATE C 裁决，不批准 engineering freeze 或 release，不进入 N7，也不作模型性能裁决。最终 main SHA 不作为本文自引用字段；其权威身份由 Git ref、真实远端认证、N6.4 Git closeout report 与后续 current handoff 固定。

## 2. 冻结范围与禁止边界

```text
provider = unchanged
solver = unchanged
observation = unchanged
clean = unchanged
pairing = unchanged
comparison contract = unchanged
N6.1 approved matrix = unchanged
performance threshold = none
model performance assessment = not performed
provider systematic bias conclusion = not established
causal attribution = not supported
```

冻结解释边界：

- formal leeward population 以 Fluent source row 为统计行；many-to-one LF target multiplicity 必须完整保留，不得按 unique LF target 去重或聚合。
- Windward 与 leeward 的 population、mapping identity、weighting 和 provenance 合同不同；二者不得合成同一母体、同一统计或直接性能排名。
- M8/30 与三个 45 km candidates 不因已有文件、运行结果或 nominal label 自动获得 formal admission。
- lower typed-empty 表示 formal clean lower observation rows 为 `0`；它不表示存在数值为零的 lower error，也不表示 lower coverage 完整。
- 30/35/40/45 km 都只是 nominal / historical label；标签不证明真实物理高度，也不证明已验证大气工况。
- QA 或 regression 的完整性通过只证明被执行的 program、contract、identity 与 asset gate；不得改写为模型性能结论。

## 3. Authority 与 package identity

### 3.1 N6.1 / N6.2b / N6.3 authority chain

- N6.1 approved matrix authority：`docs/current_model_decisions_zh.md` 第 33 节；formal registry 仅含 `ma6_a5_h30km` 与 `ma8_a5_h40km`。
- N6.2b package path：`runs/n6_exact_custom_formal/20260724T111443Z_79ed536fc8c1_n6_exact_custom`。
- N6.2b generation SHA：`79ed536fc8c1c7e19811ca744a14b78a732ff71a`。
- N6.2b package manifest SHA-256：`dffd989a057c4481446482e0543e935209e8673f1a4468b343f1dfa5785bc314`。
- N6.2b evidence manifest SHA-256：`b161086640e0e1c922fd2c02670f7e43f9b01363a797dfabb39c195f34157ac3`。
- N6.3 package path：`runs/n6_3_layered_error_portrait/20260724T151247Z_e279af25b509_n6_3_layered_error_portrait`。
- N6.3 generation SHA：`e279af25b5090c0b95f04dfe9ccc9a16f7e43529`。
- N6.3 analysis manifest SHA-256：`909436a7f96588ac35d9b8220ba984af07f3958a6194e3cf2c931e696bfb207d`。
- N6.3 artifact inventory：`8 artifacts + 1 manifest`。
- N6.3 canonical run count：`1`。

### 3.2 Current official production source identity

```text
schema = git-head-tree-source-identity/v1
source count = 68
inventory_paths_sha256 = 31b47f1998348b9e82d702b517e14e1a2d2828596c665fb79af3466f0e7fd2f0
aggregate_sha256 = fb9f8cb3a7c641cd526113c88bce465299ced8cd1e3b86b604e7e91f8cf5b609
```

Current-v5 baseline 位于 `runs/current_baseline_snapshot/tpg/`，正式 cases 为 `ma6_a5_h30km` 与 `ma8_a5_h40km`，schema 为 `current-tpg-baseline-regression/v5`，正式 `fields.npz` 为 72 fields。本文只引用其既有 identity，不修改 baseline、manifest、summary、fields 或 artifact hash。

### 3.3 不得合并的 inventory 口径

以下四项属于不同作用域，任何 count 或 hash 都不得相加、替换或互证：

1. **N6.2b package inventory**：source package 内 LF bundle、evidence artifacts 与 package manifest 的持久资产登记。
2. **N6.3 artifact inventory**：分析 package 的 8 个 artifacts；manifest 另计 1 个文件。
3. **N6.3 generation source inventory**：N6.3 生成时 Git tree 的 production source identity，属于历史生成 provenance。
4. **current official production source identity**：当前 official committed Git HEAD tree 下的 68-source identity。

raw artifact hash、parsed semantic contract、数值与字段合同、provenance path 同样必须分别陈述，不得互相替代。

## 4. Formal coverage and evidence-tier matrix

### 4.1 Tier 定义

| Tier | 冻结含义 |
|---|---|
| `formal_core` | N6.1 approved registry 中、由 N6.2b persistent package 与 N6.3 formal portrait 支撑的 upper/leeward source-row evidence |
| `supplemental_diagnostic` | 已有独立运行事实但未获 formal admission、baseline identity 或 persistent formal evidence package |
| `independent_diagnostic_context` | 具有独立 population / mapping / weighting / provenance 合同，只能作分层背景 |
| `tracked_candidate` | tracked observation candidate；可以审计 identity，但未获 formal qualification / admission |
| `typed_empty_known_limitation` | 合同内有类型和身份、但当前 observation rows 为 0 的已知局限 |
| `excluded / not_applicable` | 当前 formal-core 合同不适用或明确不纳入的关系，不表示永久失去未来资格 |

### 4.2 Case identity matrix

后续状态矩阵通过 `row` 键与本表一一对应；两表合起来构成完整 coverage matrix。

| row | case ID | nominal label | Mach | alpha | surface/sheet | evidence tier | observation identity | freestream identity | freestream semantics | atmosphere qualification |
|---|---|---:|---:|---:|---|---|---|---|---|---|
| FC1 | `ma6_a5_h30km` | 30 km | 6 | +5° | upper/leeward | `formal_core` | CSV `1197pa_226.509k_30km_5alpha_6ma.csv`; raw SHA-256 `210b4a94fae57d6b7701ed76d2c07a9e9a3d276bf94c330f7ae363fcc8cb2000` | exact bundle `T=226.509 K`, `P=1197 Pa`, `explicit_override` | historical user-defined comparison input | none / unverified |
| FC2 | `ma8_a5_h40km` | 40 km | 8 | +5° | upper/leeward | `formal_core` | CSV `287pa_251k_40km_5alpha_8ma.csv`; raw SHA-256 `74d7097f8bb5bbca500f7ffd3e091f77899920bc1ef4c2074706fbb848e31e62` | exact bundle `T=251 K`, `P=287 Pa`, `explicit_override` | historical user-defined comparison input | none / unverified |
| SD1 | `ma8_a5_h30km` | 30 km | 8 | +5° | upper/leeward | `supplemental_diagnostic` | CSV `1197pa_226.509k_30km_5alpha_8ma.csv`; raw SHA-256 `5dc84e2dea4dc49a5f6ce777e71b8121c148b9490afeb83c98bd5ce022b3b865` | exact bundle `T=226.509 K`, `P=1197 Pa`, `explicit_override` | historical user-defined comparison input | none / unverified |
| TC1 | `ma8_a10_h45km` | 45 km | 8 | +10° | observation candidate; no formal sheet admission | `tracked_candidate` | CSV `131pa_241.65k_45km_10alpha_8ma.csv`; raw SHA-256 `dc668e37de020ae283254a199340e64542d67475b031f46caced8b2abd27acb0` | filename identity `T=241.65 K`, `P=131 Pa`; no approved exact binding | historical user-defined comparison input | none / unverified |
| TC2 | `ma8_a5_h45km` | 45 km | 8 | +5° | observation candidate; no formal sheet admission | `tracked_candidate` | CSV `131pa_241.65k_45km_5alpha_8ma.csv`; raw SHA-256 `ef2c24f40df63ddf74da86c75888253373be6f02da6295a377b16a995a9f7a0c` | filename identity `T=241.65 K`, `P=131 Pa`; no approved exact binding | historical user-defined comparison input | none / unverified |
| TC3 | `ma9_a5_h45km` | 45 km | 9 | +5° | observation candidate; no formal sheet admission | `tracked_candidate` | CSV `131pa_241.65k_45km_5alpha_9ma.csv`; raw SHA-256 `667e998ce184388c99ca08b3df39528c738bc00fbf7af0d0adf90e6f7df86428` | filename identity `T=241.65 K`, `P=131 Pa`; no approved exact binding | historical user-defined comparison input | none / unverified |
| WD1 | `ma6.5_a3_h30km` | 30 km | 6.5 | +3° | windward diagnostic | `independent_diagnostic_context` | 12-case windward summary; SHA-256 `85a9fe4c4231f07f02b498b174f88fb96bd41e7d6c9bfc2b6d8f20fa012b8d38` | diagnostic-run metadata only | historical comparison metadata; not N6 formal exact binding | none / unverified |
| WD2 | `ma6_a5_h30km` | 30 km | 6 | +5° | windward diagnostic | `independent_diagnostic_context` | same 12-case summary identity | diagnostic-run metadata only | historical comparison metadata; not N6 formal exact binding | none / unverified |
| WD3 | `ma8_a5_h30km` | 30 km | 8 | +5° | windward diagnostic | `independent_diagnostic_context` | same summary; per-case stats SHA-256 `8d81bc1c7929288329fc6e4e7b05aa005a4574c754614cb15c6e77e310f03f66` | diagnostic-run metadata only | historical comparison metadata; not N6 formal exact binding | none / unverified |
| WD4 | `ma6.5_a8_h35km` | 35 km | 6.5 | +8° | windward diagnostic | `independent_diagnostic_context` | same 12-case summary identity | diagnostic-run metadata only | historical comparison metadata; not N6 formal exact binding | none / unverified |
| WD5 | `ma9_a8_h35km` | 35 km | 9 | +8° | windward diagnostic | `independent_diagnostic_context` | same 12-case summary identity | diagnostic-run metadata only | historical comparison metadata; not N6 formal exact binding | none / unverified |
| WD6 | `ma6.5_a5_h40km` | 40 km | 6.5 | +5° | windward diagnostic | `independent_diagnostic_context` | same 12-case summary identity | diagnostic-run metadata only | historical comparison metadata; not N6 formal exact binding | none / unverified |
| WD7 | `ma8_a5_h40km` | 40 km | 8 | +5° | windward diagnostic | `independent_diagnostic_context` | same 12-case summary identity | diagnostic-run metadata only | historical comparison metadata; not N6 formal exact binding | none / unverified |
| WD8 | `ma9_a5_h40km` | 40 km | 9 | +5° | windward diagnostic | `independent_diagnostic_context` | same 12-case summary identity | diagnostic-run metadata only | historical comparison metadata; not N6 formal exact binding | none / unverified |
| WD9 | `ma8_a10_h40km` | 40 km | 8 | +10° | windward diagnostic | `independent_diagnostic_context` | same 12-case summary identity | diagnostic-run metadata only | historical comparison metadata; not N6 formal exact binding | none / unverified |
| WD10 | `ma8_a5_h45km` | 45 km | 8 | +5° | windward diagnostic | `independent_diagnostic_context` | same 12-case summary identity | historical diagnostic metadata is insufficient for N6 qualification | historical user-defined / inconsistent diagnostic metadata | none / unverified |
| WD11 | `ma9_a5_h45km` | 45 km | 9 | +5° | windward diagnostic | `independent_diagnostic_context` | same 12-case summary identity | historical diagnostic metadata is insufficient for N6 qualification | historical user-defined / inconsistent diagnostic metadata | none / unverified |
| WD12 | `ma8_a10_h45km` | 45 km | 8 | +10° | windward diagnostic | `independent_diagnostic_context` | same 12-case summary identity | historical diagnostic metadata is insufficient for N6 qualification | historical user-defined / inconsistent diagnostic metadata | none / unverified |
| TE1 | `ma6_a5_h30km` | 30 km | 6 | +5° | lower/leeward | `typed_empty_known_limitation` | N6.2b lower `raw_evidence.npz`; formal clean observation rows `0` | same approved exact bundle as FC1 | historical user-defined comparison input | none / unverified |
| TE2 | `ma8_a5_h40km` | 40 km | 8 | +5° | lower/leeward | `typed_empty_known_limitation` | N6.2b lower `raw_evidence.npz`; formal clean observation rows `0` | same approved exact bundle as FC2 | historical user-defined comparison input | none / unverified |

### 4.3 Evidence and conclusion matrix

| row(s) | ingestion / comparison status | persistent package status | analysis portrait status | reproducibility status | inclusion / exclusion | exclusion reason | allowed conclusions | prohibited conclusions |
|---|---|---|---|---|---|---|---|---|
| FC1, FC2 | formal ingestion and source-row comparison PASS | N6.2b package present | N6.3 formal portrait present | PASS | included in formal core | not excluded | bounded descriptive upper/leeward source-row errors、spatial structure、many-to-one diagnostics | performance acceptance、single-variable cause、real-altitude or validated-atmosphere claim、provider bias conclusion |
| SD1 | production comparison runtime fact = yes；final formal QA of that production comparison = yes | no persistent formal evidence package | no N6.3 formal portrait membership | PARTIAL | supplemental only；excluded from formal core | unregistered；no persistent formal evidence package | specified-input descriptive runtime comparison fact | third formal trend point、baseline identity、formal admission、formal-core aggregation |
| TC1–TC3 | filename/raw identity auditable；formal leeward ingestion/comparison not approved | none | no formal portrait; WD10–WD12 are separate historical windward context | PARTIAL | tracked candidates；not admitted | unregistered；exact freestream/provenance qualification not approved；historical atmosphere semantics inconsistent | candidate identity and future qualification eligibility | automatic admission、permanent invalidity、validated atmosphere、formal trend use |
| WD1–WD12 | historical diagnostic comparison assets exist；not formal leeward ingestion/comparison | no N6 formal package | N6.3 metadata reference only；not formal portrait membership | PARTIAL | retained as independent diagnostic context | population、mapping identity、weighting and statistics contract differ from formal leeward source-row evidence | independent windward diagnostic facts within their own contract | merged population、merged statistics、direct cross-surface ranking、formal-core substitution |
| TE1, TE2 | formal typed-empty comparison PASS；rows `0` | N6.2b typed-empty assets present | limitation recorded；no numerical lower portrait | PASS for typed-empty identity | included as known limitation；not included in numerical trend | formal clean lower observation rows = 0 | existence、type、empty-row count and limitation boundary | zero-error claim、lower performance claim、manufactured observations、coverage-complete claim |

### 4.4 M8/30 atmosphere metadata correction

M8/30 candidate manifest contains `atmosphere.model = isa1976` while also recording `explicit_freestream_override = true` and `freestream.source = explicit_override`。该 atmosphere 字段不是当前 evidence qualification authority；exact `P/T` 来自显式 override，不得据此认定该 case 属于已验证 ISA1976 工况。

N6.4 统一口径为：

```text
freestream_semantics = historical user-defined comparison input
atmosphere qualification = none / unverified
```

同一原则适用于当前 30/35/40/45 km nominal labels。current-v5 baseline manifest 的 default-atmosphere runtime identity 与 N6 exact-custom Fluent comparison qualification 是两个不同合同；前者不能替代后者。

## 5. Exclusion / non-admission register

| subject | reason | classification | defect | future release condition | N6.4 required action |
|---|---|---|---|---|---|
| M8/30 | unregistered；no persistent formal evidence package | governance boundary | no | separate approved admission、binding and formal package process | record boundary only；do not admit |
| 45 km candidates | unregistered；exact freestream/provenance qualification not approved；historical atmosphere semantics inconsistent | governance boundary / future evidence qualification | no | reliable exact-input provenance、approved binding、admission and formal package process | record exclusion；do not repair or admit |
| Windward diagnostic | population、mapping identity、weighting and statistics contract differ from formal leeward source-row evidence | governance boundary | no | separate source-level formal contract and qualification | keep independent tier；do not merge |
| Lower typed-empty | formal clean lower observation rows = 0 | known limitation | no | obtain qualified formal lower observations through a separately approved evidence process | record limitation；do not manufacture data |
| external candidate artifacts / projection cache | ignored external frozen run artifact；不随 clean checkout 构成正式可分发 evidence；不属于 formal-core package，也不得作为 source identity 或 baseline identity | third-party reproducibility boundary | formal-core defect = no；evidence-chain defect = no | tracked immutable artifact，或经批准的可重复生成合同；并明确 input identity、generation entry、hash / provenance，完成独立资格审查 | record exclusion / reproducibility boundary；do not supplement package、recompute or admit |

### External candidate artifacts / projection cache

- **Identity**：schema=`exact-projection-cache/v1`；authority 记录的正式 cache 位置为 `runs/fluent_projection_cache/f8e831b08dd86283bb69dc2f5be5fdb636e160a801ce97ec4d9382098b611c23/projection_cache.npz`，size=`786,521 bytes`，SHA-256=`a82d7d56b01aaae8067cdfa2c3ba439f4d3cc7fcd537c0dedbb573cf4d6be3a7`；该位置是 ignored external frozen run artifact identity，不是 tracked formal package、baseline、formal registry、N6.3 formal portrait 或 current official source identity。
- **Evidence tier**：`excluded / not_applicable`。
- **Exclusion / non-admission reason**：该 cache 是外部或 ignored candidate artifact，不随 clean checkout 构成正式可分发 evidence，不属于 formal-core package，不得作为 source identity 或 baseline identity。
- **Classification**：`third-party reproducibility boundary`；`formal-core defect = no`；`evidence-chain defect = no`。
- **Future release condition**：若未来升级为 supplemental replay 资产或申请正式资格，必须提供 tracked immutable artifact，或经批准的可重复生成合同；同时明确 input identity、generation entry、hash / provenance，并完成独立资格审查。本轮不实现这些条件。
- **Required N6.4 action**：记录 exclusion / reproducibility boundary；不要求补包、不要求重算、不要求 admission。
- **Allowed conclusion**：可以说明该 external/ignored artifact 的治理位置、它不属于 clean-checkout formal-core evidence，以及 formal core 不依赖该 cache 才能复核。
- **Prohibited conclusion**：不得将其解释为 formal package、baseline identity 或 clean-checkout 必须存在的 source；不得因其未跟踪而判定 formal-core evidence defect；不得用其替代正式 package 或 manifest。

三个 45 km cases 不是因为数字标签而永久排除。未来若建立可靠 exact-input provenance、approved observation binding 与正式 package，它们可以作为新的资格工作包重新审查；本轮不修复、不 admission。

## 6. Engineering limitation register

| status | limitation / applicability boundary | effect on current N6 scope | future release condition |
|---|---|---|---|
| KNOWN_LIMITATION | formal cases only 2 | 只支持两个指定 exact-custom bundles 的 bounded 描述 | 新增 case 必须独立完成 observation、binding、admission、package 与 QA |
| KNOWN_LIMITATION | formal surface only upper/leeward | 不支持全表面性能或 lower 结论 | 建立新的正式 surface evidence contract |
| KNOWN_LIMITATION | lower typed-empty | lower 无可计算正式误差母体 | 获得 qualified formal lower observations |
| NOT_APPLICABLE | cross-surface combined population under current contract | 现有两类证据合同不可合并 | 先建立同 identity、population、weighting、provenance 的新合同 |
| KNOWN_LIMITATION | M8/30 supplemental-only | 不构成第三个 formal-core trend point | 独立 admission、binding 与 formal package |
| FUTURE_PROJECT | 45 km qualification/admission | 当前只保留 tracked candidate identity | 可靠 exact-input provenance 与正式 qualification work package |
| KNOWN_LIMITATION | historical user-defined freestream | 只允许 specified-input comparison | 建立并批准新的物理工况身份 |
| KNOWN_LIMITATION | `atmosphere_model` none/unverified | nominal label 不支持大气验证 | validated-atmosphere case identity 与证据链 |
| KNOWN_LIMITATION | Mach、P、T 和 nominal label cannot be isolated as single variables in the two formal cases | 不支持单变量趋势或机制归因 | 受控 case matrix 与独立资格证据 |
| KNOWN_LIMITATION | performance threshold none | 不作性能接受/拒绝裁决 | 用户批准独立工程阈值合同 |
| KNOWN_LIMITATION | causal attribution not supported | 仅能陈述描述性与排除性事实 | 受控设计与独立因果证据 |
| NOT_APPLICABLE | provider systematic bias conclusion not established | 当前不选择 provider 路线 | 需要更充分、受控且可解释的正式证据 |

`KNOWN_LIMITATION` 可以允许 N6 在 bounded formal scope 内退出，前提是适用边界、禁止性解释和未来解除条件均已明确。它不等于缺陷已被隐藏，也不自动扩大 formal coverage。

## 7. Third-party reproducibility matrix

本节状态只使用 `PASS`、`PARTIAL`、`BLOCKED`、`NOT_APPLICABLE`。

| item | status | authority / replay basis | boundary |
|---|---|---|---|
| repo / commit 定位 | PASS | `https://github.com/KiRenk0/navi.git`；audit base `5c6e0b56f20a33d431ec1e94e3aa216667983452` | final main identity 待后续 closeout |
| Python import | PASS | `PYTHONPATH=<repo>/src`；`ref_enthalpy_method` 必须解析到当前 repo | 环境必须先通过 import gate |
| formal registry | PASS | `APPROVED_FORMAL_OBSERVATION_REGISTRY` 仅含 M6/30、M8/40 | M8/30 和 45 km 不在 formal registry |
| approved bindings | PASS | `observation_binding.py` approved registry + strict filename identity | parser success 不产生 admission |
| formal observation CSV identity | PASS | N6.2b evidence manifest 的 path、raw SHA、size | 只覆盖两个 formal cases |
| exact formal P/T bundle | PASS | M6/30=`226.509 K / 1197 Pa`；M8/40=`251 K / 287 Pa`；explicit bundle gate | nominal label 不替代 exact pair |
| atmosphere qualification | PARTIAL | freestream semantics 已明确，qualification 仍为 none / unverified | 不能复现为 validated-atmosphere claim |
| N6.2b package | PASS | canonical path、package manifest 与 evidence manifest identity | package generation identity 与 current source identity 不合并 |
| N6.3 package | PASS | canonical analysis path、manifest、8-artifact inventory | 仅一个 canonical run |
| official CLI | PASS | `scripts/run_case_rem.py`；官方指南已记录参数与 explicit override | 本轮不重跑 solver |
| validators | PASS | N6.3 `--validate-existing` 与 package内 integrity contract | 本轮只运行既有 validation，不新增 validator |
| source identity | PASS | `git-head-tree-source-identity/v1`，68 sources，两项 aggregate identity | Git blob identity 不等于 artifact identity |
| artifact identity | PASS | package/analysis manifests 登记 raw SHA-256 | parsed semantics 与 raw bytes 分开 |
| error direction | PASS | `prediction - observation`；relative=`100 * error / observation` | 不得反转符号解释 |
| source-row weighting | PASS | one Fluent source row equal weight | 不按 unique target 去重 |
| many-to-one semantics | PASS | formal rows `186` → `80` unique targets；multiplicity diagnostic only | no injective reassignment / target aggregation |
| limitations | PASS | 本文 engineering limitation register；认证候选待 independent QA | future questions 不改写成当前 defect |
| prohibited interpretations | PASS | 本文冻结边界、coverage matrix 与 limitation register | 不作性能、因果、真实高度或 provider 裁决 |
| M8/30 supplemental replay | PARTIAL | exact observation/binding、candidate、production runtime fact 与 final formal QA 可定位 | 无 persistent formal comparison/evidence package；不要求本轮重算 |
| Windward numerical zero-recompute replay | PARTIAL | 12-case summary、per-case metadata 与 plotting implementation 可定位 | provenance/population 不等同 formal leeward；本轮不重算 |
| 45 km qualification | PARTIAL | 三个 tracked CSV 的 filename/raw identity 可审计 | exact-input provenance 与 admission 未批准 |
| projection cache external artifact | PARTIAL | tracked authority 记录 frozen cache identity、正式输入 identity、generation/load entry 与 hash / provenance | ignored external frozen run artifact；不随 clean checkout 分发、不属于 formal-core evidence；formal core 的复核不依赖该 cache |
| unified N6 limitations register | PASS | 本文为 final tracked canonical authority | independent QA 已通过；final authority 已签发 |

```text
formal-core reproducibility = PASS
supplemental/diagnostic reproducibility = PARTIAL
```

Supplemental/diagnostic 的 `PARTIAL` 不构成 formal-core identity 或 evidence-chain defect，也不要求本轮重算。它表示第三方可以定位已有事实和边界，但不能从现有资产重建与 formal core 等价的完整资格链。

## 8. N6 exit-condition final matrix

本节状态只使用 `PASS`、`KNOWN_LIMITATION`、`NOT_APPLICABLE`、`BLOCKED`。

| exit condition | status | certification basis / boundary |
|---|---|---|
| formal observation identity | PASS | 两个 formal CSV path/raw identity 已绑定 |
| formal ingestion | PASS | 两 case upper source-row ingestion 与 lower typed-empty 合同已持久化 |
| exact formal input binding | PASS | 两个 exact custom P/T bundles 通过正式 binding/gate |
| formal provenance | PASS | N6.2b package、generation SHA 与 manifests 可独立定位 |
| historical-custom / validated-atmosphere separation | PASS | freestream semantics 与 atmosphere qualification 已明确分离 |
| leeward error portrait | PASS | N6.3 formal source profiles、spatial bins、bounded comparison 与 figures |
| windward evidence-tier status | PASS | independent diagnostic context 已明确，禁止跨 tier 合并 |
| cross-case structure | PASS | 两 formal assets 的 recorded structure 与 bounded comparison 已登记 |
| Mach/alpha/surface coverage | KNOWN_LIMITATION | 两 case、alpha +5°、upper/leeward；不能泛化 |
| causal attribution | KNOWN_LIMITATION | 当前 bounded descriptive contract 不承担因果识别；causal attribution not supported |
| formal CLI/assets/docs reproducibility | PASS | official CLI、N6.2b/N6.3 assets、本文索引与 validator 可定位 |
| third-party formal-core reproducibility | PASS | clean checkout 可由 tracked source、formal packages、manifests 与 official validators 复核；不依赖 external projection cache |
| formal coverage | PASS | N6.1 approved bounded matrix已完整映射到本文 |
| exclusion reasons | PASS | M8/30、45 km、windward、lower 已登记分类与解除条件 |
| engineering limitations | PASS | 本文统一 register 已建立 |
| new evidence-chain defect | PASS | 当前审计输入未发现新的 identity/data/package-chain defect |
| major provider systematic evidence | NOT_APPLICABLE | provider systematic bias conclusion = not established；无适用裁决 |
| consolidated canonical certification | PASS | final canonical document issued；independent QA result=`N6_4_INDEPENDENT_QA_AND_FULL_REGRESSION_PASS` |
| independent QA | PASS | independently audited corrected HEAD=`f088d88eb409a5462451b81d27beac92bce528ae` |
| full pytest | PASS | independent QA=`460 passed + 125 subtests`；final closeout rerun required |
| current regression | PASS | independent QA current TPG/regression PASS；final closeout rerun required |
| production source identity | PASS | `git-head-tree-source-identity/v1`；68/68 PASS |
| final N6 sign-off | PASS | ISSUED；bounded N6 strategic exit signed |

```text
formal observation identity = PASS
formal ingestion = PASS
exact formal input identity = PASS
formal provenance = PASS
historical-custom / validated-atmosphere separation = PASS
leeward formal error portrait = PASS
windward evidence-tier separation = PASS
exclusion reasons = PASS
engineering limitations register = PASS
third-party formal-core reproducibility = PASS
canonical certification = PASS
independent QA = PASS
full pytest = PASS
current regression = PASS
production source identity = PASS
new evidence-chain defect = none
major provider systematic evidence = not established / NOT_APPLICABLE
formal cases only 2 = KNOWN_LIMITATION
formal surface only upper/leeward = KNOWN_LIMITATION
lower typed-empty = KNOWN_LIMITATION
M8/30 supplemental-only = KNOWN_LIMITATION
causal attribution = KNOWN_LIMITATION
performance threshold none = KNOWN_LIMITATION
windward/leeward joint population = NOT_APPLICABLE

不存在阻止 bounded N6 strategic exit 的 BLOCKED 项。
N6.4 status = COMPLETE
N6 strategic exit = SIGNED / COMPLETE
N6 final sign-off = ISSUED
formal bounded scope = ACCEPTED AS THE COMPLETED N6 EVIDENCE SCOPE
```

## 9. GATE C entry evidence index

本索引只定位材料，不作 GATE C 裁决。

| # | evidence item | canonical location / status |
|---:|---|---|
| 1 | final main identity | status=`to be authenticated by final Git closeout`；authority=closeout 后 local main、origin/main 与真实远端 `refs/heads/main` 指向包含本认证文档的同一提交；最终 SHA 不在本文自引用 |
| 2 | N6.1 approved matrix | `docs/current_model_decisions_zh.md` 第 33 节 |
| 3 | N6.2b package and manifests | `runs/n6_exact_custom_formal/20260724T111443Z_79ed536fc8c1_n6_exact_custom/` |
| 4 | N6.3 package and manifest | `runs/n6_3_layered_error_portrait/20260724T151247Z_e279af25b509_n6_3_layered_error_portrait/` |
| 5 | N6.4 formal coverage matrix | 本文第 4 节 |
| 6 | evidence-tier matrix | 本文第 4.1–4.3 节 |
| 7 | exclusion / non-admission register | 本文第 5 节 |
| 8 | engineering limitation register | 本文第 6 节 |
| 9 | third-party reproducibility matrix | 本文第 7 节 |
| 10 | N6 exit-condition matrix | 本文第 8 节 |
| 11 | current regression evidence | current-v5 manifests 与 `scripts/tools/current_baseline_regression_check.py`；independent QA PASS，final closeout rerun required |
| 12 | source identity | 本文第 3.2 节；current-v5 manifests |
| 13 | artifact identity | N6.2b package/evidence manifests 与 N6.3 analysis manifest |
| 14 | canonical docs | 本文及 `docs/README_INDEX.md`、`docs/faceted3d_file_index_zh.md`、三个 final canonical status 文件 |
| 15 | known limitations | 本文第 6 节 |
| 16 | prohibited interpretations | 本文第 2、4、6、7 节 |
| 17 | unresolved questions | 本文第 10 节；均为未来独立决策，不阻断 bounded exit |
| 18 | final N6 sign-off | `ISSUED`；N6 strategic exit=`SIGNED / COMPLETE` |

GATE C entry evidence index 的 18 类证据已完整。其含义仅为证据已准备完成，具备请求 GATE C review 的资格；不表示 GATE C 已开始或已通过，不表示 engineering freeze 已批准，也不表示 N7 可自动进入。GATE C 保持 `NOT DECIDED`，N7 保持 `NOT ENTERED`。

## 10. Unresolved questions

以下均为未来决策事项，不是本轮 docs-only implementation blocker：

1. 是否未来为 M8/30 建立独立 formal admission。
2. 是否未来认证 45 km exact-input provenance。
3. 是否未来建立 windward source-level formal contract。
4. 是否未来获得 lower formal observations。
5. 是否未来建立 validated-atmosphere case identity。
6. 是否由 GATE C 接受当前 bounded formal scope。

## 11. 最终认证边界

```text
N6.4 status = COMPLETE
N6 strategic exit = SIGNED / COMPLETE
N6 final sign-off = ISSUED
formal bounded scope = ACCEPTED AS THE COMPLETED N6 EVIDENCE SCOPE
GATE C entry evidence index = COMPLETE
eligibility = ELIGIBLE_TO_REQUEST_GATE_C_REVIEW
GATE C decision = NOT DECIDED
GATE C approval = NOT ISSUED
engineering freeze = NOT APPROVED
N7 = NOT ENTERED
release/tag = NOT CREATED
performance threshold = none
model performance assessment = not performed
provider systematic bias conclusion = not established
causal attribution = not supported
```

本文只认证冻结 bounded scope 内 N6.0–N6.4 的 observation identity、formal ingestion、exact-custom package、layered descriptive error portrait、coverage、exclusion、engineering limitations、third-party reproducibility 与 exit certification 已形成完整、tracked、经独立 QA 的证据链。它不认证模型性能达到阈值，不认证 provider 物理准确性，不建立 provider systematic bias，不消除既有工程局限，不扩充 formal surface/case，也不构成 GATE C、engineering freeze、N7、tag 或 release 决定。
