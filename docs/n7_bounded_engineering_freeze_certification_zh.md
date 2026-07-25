# N7 Bounded Engineering-Freeze Certification Candidate

> 状态日期：2026-07-25
>
> 文档类型：tracked certification / change-gate authority
>
> 当前阶段：candidate implementation；不是 final engineering-freeze certification

---

## 1. 文档职责与权威边界

本文是 Faceted3D v2 N7 bounded engineering-freeze 的 tracked certification/change-gate authority。它只固定已获批准的 OPTION 3 bounded/degraded freeze 范围、候选实施状态、复现与完整性边界、known limitations、prohibited claims、后续验证门禁及回退路径。

本文不替代：

- `docs/current_model_decisions_zh.md` 第 33 节的 detailed evidence-tier authority；
- current-v5 baseline/manifests、N6.2b package/evidence manifests 或 N6.3 analysis manifest；
- formal registry、approved bindings、solver/API/comparison contracts；
- 独立 QA、用户 final freeze decision、main closeout、annotated tag 或 GitHub release。

## 2. 起始技术基线与 candidate commit 身份

- technical base：`e3ad9d51482c5ddfb085c9c06cd3345f54a964ed`；
- starting branch：`main`；
- candidate branch：`docs/n7-bounded-engineering-freeze-candidate`；
- candidate commit identity：该分支上首个完整包含本 certification 与其余六份 N7 current-authority 更新的 Git commit；其精确 SHA 由提交后的 Git ref、真实远端 ref 与任务交付报告认证，本文不进行不可实现的 commit 自引用；
- candidate commit 的 parent 必须是上述 technical base；
- 本轮版本身份只由 Git commit、technical base SHA 与本文共同表达，不新增软件版本入口或 package metadata。

## 3. GATE C OPTION 3 用户批准事实

以下治理事实已经批准并冻结，不在 N7 重审：

- `GATE C = COMPLETE`；
- selected branch：`OPTION 3 bounded/degraded freeze`；
- bounded engineering-freeze scope：`APPROVED`；
- N7 entry：`AUTHORIZED`；
- provider：`unchanged`；
- performance threshold：`none`；
- repairable technical gap identified at GATE C：`none`；
- GATE C approval 不等于 final freeze completion、main closeout、tag 或 release 授权。

## 4. Approved bounded engineering-freeze scope

本 candidate 只冻结以下有界范围：

- formal cases：`ma6_a5_h30km`、`ma8_a5_h40km`；
- alpha：`+5°`；surface / region：`upper / leeward`；
- 每 case：`186` 个等权 Fluent source rows → `80` 个 unique LF primary targets；
- formal statistical population：`186 source rows`；`80 unique targets` 只表示 mapping topology，不是等权 formal population；
- many-to-one 完整保留，不去重、不压缩、不聚合、不改为 injective assignment；
- freestream：historical exact-custom comparison inputs；
- `atmosphere_model = none / unverified`；
- provider unchanged；performance threshold none；不存在 physical-accuracy gate。

本范围不授权修改 provider、threshold、evidence tier、formal registry、population、baseline、manifest、source/artifact hash、Groups 1–8、72-field contract、solver/API/comparison identity 或任何数值资产。

## 5. Evidence-tier matrix 的权威引用

`docs/current_model_decisions_zh.md` 第 33 节继续作为 detailed scope/tier 的唯一 tracked canonical authority；本文引用并冻结该 authority，不建立第二套详细数字矩阵。

必要边界摘要如下：

- `formal_core`：M6/30、M8/40 upper/leeward；
- `supplemental_diagnostic`：M8/30 upper/leeward；
- `independent_diagnostic_context`：windward；
- `tracked_candidate`：three 45 km cases；
- `typed_empty_known_limitation`：formal lower sheets；
- `excluded / not_applicable distribution/replay boundary`：external projection cache。

上述 tier 不得自动提升、降级、合并或重新命名。若本文摘要与第 33 节产生歧义，以第 33 节详细 authority 为准，并触发本文的变更门禁。

## 6. Reproducibility 与 integrity 承诺边界

- 复现承诺限于已冻结的 committed source、tracked contracts、formal manifests、approved bindings 与现有 canonical assets；
- current baseline regression、N6.3 `--validate-existing`、existing pytest、raw manifest SHA-256 和 Git identity 是 program/contract/asset/integrity 证据，不是模型性能或 physical accuracy 证据；
- 数值与字段合同、parsed semantic contract、raw artifact hash 与 provenance path 必须分别认证，不得相互替代；
- external projection cache 不属于 formal distribution/replay commitment；其缺失不得被改写为 formal evidence-chain defect；
- geometry/mapping traceability 只证明可追溯与合同一致，不证明绝对正确；
- 本 candidate 不执行 solver、formal generation、new analysis、baseline promotion、manifest migration、summary-hash repair 或 evidence/candidate generation。

## 7. Known limitations

1. Condition 3 在当前 approved bounded scope 内不可达。
2. Windward 是 non-formal independent diagnostic context。
3. Windward 不存在 leeward 等级的 formal source-level contract/package。
4. Lower 是 typed-empty known limitation，不是 numerical coverage。
5. Windward/leeward 的 population、mapping、weighting、provenance 不可直接比较。
6. 禁止建立 windward/leeward joint population。
7. 禁止建立 windward/leeward joint statistics。
8. 禁止 direct ranking 或 unified performance conclusion。
9. Formal core 仅为 M6/30、M8/40 upper/leeward。
10. M8/30 仅为 supplemental diagnostic。
11. 三个 45 km cases 仅为 tracked candidate。
12. Historical exact-custom freestream 只支持 specified-input comparison。
13. `atmosphere_model = none / unverified`。
14. Nominal altitude 不是 validated atmosphere 或真实高度性能证据。
15. 不存在 performance threshold。
16. 不存在 physical-accuracy gate。
17. Attribution 只支持 descriptive/exclusionary boundary。
18. 不支持 quantitative causal attribution。
19. 不支持 Mach、高度、压力或温度的单变量因果归因。
20. 不支持 provider systematic-bias claim，包括声称其存在或不存在。
21. Geometry/mapping 可追溯不等于绝对正确。
22. `186 source rows` 是 formal statistical population。
23. `80 targets` 仅为 mapping topology，不是等权 formal population。
24. Many-to-one 不得去重、压缩、聚合或改为 injective assignment。
25. External projection cache 不属于 formal distribution/replay commitment。
26. 证据不得外推至其他 case、surface、freestream、真实高度或未 admission tier。
27. Provider unchanged。

## 8. Prohibited claims

不得声称：

1. full-scope GATE C 的全部成功条件已满足；
2. OPTION 1 成立；
3. integrity/regression/QA/replay PASS 等于模型性能 PASS；
4. 模型达到任何数值性能阈值；
5. Faceted3D v2 已通过 physical-accuracy validation；
6. windward 已具有 formal evidence；
7. lower 已具有 numerical coverage；
8. full-surface performance evidence 已成立；
9. windward/leeward 可联合统计或排名；
10. atmosphere 已验证；
11. nominal altitude 是真实高度性能证据；
12. M8/30 已进入 formal core；
13. 45 km candidate 已 admission；
14. quantitative causal attribution 已完成；
15. provider systematic bias 存在或不存在；
16. `80 targets` 是正式等权统计母体；
17. external projection cache 是正式 replay/distribution asset；
18. bounded freeze 授权修改 provider、threshold 或 tier；
19. N7 entry authorized 等于 N7 complete；
20. GATE C approval 等于 tag/release authorization；
21. candidate implementation 等于 final engineering freeze completion。

## 9. Final validation matrix

| Gate | Candidate requirement | 当前状态 |
|---|---|---|
| Git / changed-path identity | technical base、parent、branch、exact 7-path allowlist、tracked clean | 起始门禁与 pre-commit 7-path allowlist PASS；commit/push identity 待交付阶段认证 |
| Current-authority consistency | 陈旧 current state 已 supersede；历史状态保持历史标注 | PASS；陈旧字面仅保留在显式历史段 |
| Artifact-integrity contract | focused artifact hash integrity pytest | PASS：`5 passed` |
| Registry/binding contract | focused observation binding pytest | PASS：`37 passed` |
| Existing canonical analysis | N6.3 `--validate-existing`，禁止 `--execute` | PASS：8 artifacts；manifest SHA-256 exact match |
| Manifest raw hashes | N6.2b package/evidence 与 N6.3 analysis 三份 SHA-256 | PASS：三份均 exact match |
| Temporary/cache hygiene | 不产生 `.pytest_cache`、`__pycache__`、新 run/manifest/binary | post-focused scan PASS；提交与推送后仍须复核 |
| Independent QA | 后续独立只读 QA | `NOT YET COMPLETED` |
| User final freeze decision | 独立用户决策 | `NOT YET GRANTED` |
| Main closeout | 独立 main closeout | `NOT YET COMPLETED` |

focused implementation validation 只支撑本 candidate 的 docs/governance 与冻结资产完整性，不得替代 independent QA 或 final engineering-freeze certification。

## 10. 维护规则

- detailed evidence matrix 只在 `docs/current_model_decisions_zh.md` 第 33 节维护；本文只保留引用、必要摘要和 certification 状态机；
- 历史 N6/GATE C 前状态必须保留为历史事实，不得静默改写为当时已完成 N7；
- current status、文档索引、CLI guide、文件索引与 update log 必须与本文 candidate 状态一致；
- provider、threshold、tier、population、formal case 或资产 identity 的任何变化均超出本 candidate。

## 11. 变更门禁

任何下列变化都必须停止本 bounded candidate，并获得独立授权：

- 修改 approved bounded scope、provider、performance threshold、physical-accuracy gate 或 evidence tier；
- 修改 source/tests/scripts/specs/runs/fluent_export、baseline、manifest、formal registry/bindings、source/artifact hash 或 binary asset；
- 将 independent QA、user final approval、main closeout、tag 或 release 写成已完成；
- 发现新的唯一可复现 repairable technical gap 或 tracked authority contradiction。

## 12. 回退路径

本 candidate 是单一 task commit、exact 7-path docs/governance-only 变更。若 focused gate、后续 independent QA 或用户决策不接受：

1. 不合并 task branch；或
2. 对已共享 candidate commit 创建显式 revert commit；
3. technical base、provider、baseline、manifest、formal assets 与 contracts 无需迁移或重建。

不得通过 force、reset、历史改写、baseline promotion 或 manifest/hash 更新掩盖回退。

## 13. Tag/release 独立授权门

- GATE C approval 与 N7 entry authorization 不构成 tag/release authorization；
- annotated tag 只能在 final freeze decision、independent QA 与 main closeout 均完成后由用户单独授权；
- GitHub release 同样需要单独授权；
- 当前 `annotated tag = NOT CREATED`，`GitHub release = NOT CREATED`。

## 14. 当前 candidate 状态

- `N7 candidate implementation = COMPLETE`；
- `independent QA = NOT YET COMPLETED`；
- `engineering freeze completion = NOT YET CERTIFIED`；
- `user final freeze approval = NOT YET GRANTED`；
- `main closeout = NOT YET COMPLETED`；
- `annotated tag = NOT CREATED`；
- `GitHub release = NOT CREATED`。

## 15. Final user decision

Final user decision 尚未取得。本 candidate 只提供后续 independent QA 与用户决策所需的 tracked governance authority，不请求、不代替也不解释 final freeze approval。

## 16. Independent QA

Independent QA 尚未完成，结果栏待后续独立任务填写。本轮 focused validation 不是 independent QA；本轮结束后不得自行进入 independent QA、main closeout、final freeze approval、tag 或 release。
