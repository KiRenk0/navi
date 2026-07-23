# Faceted3D v2 — 文档索引

> 更新：2026-07-23
> 用途：新接手 DS/GPT 快速定位

## 当前主线一句话

Route A-TPG（thermally-perfect-gas）是**唯一正式且唯一可运行**的 thermodynamic baseline；CLI 不提供 thermodynamics 选择。正式高度参数域、Taw、provider、comparison、pairing、ingestion、Groups 1–8 与 72-field contract 均保持冻结。GATE A 已完成，final branch=`A0`；主线仍为 N3a，但 N3b source-identity 技术链已完成：current-v5 pipeline 已改为以 committed Git HEAD tree 中 production path 对应的 Git blob bytes 为 canonical source identity，并完成 61→65 source-only migration、dirty-tree adversarial QA、full pytest 与 official current regression。当前正式 source inventory=`65`，schema=`git-head-tree-source-identity/v1`；authoritative full pytest=`419 passed, 125 subtests passed, 0 failed`，`CURRENT REGRESSION OVERALL: PASS`。N3b Git closeout 尚未完成；独立 fast-forward merge closeout 后返回 N3a.8，不自动进入 GATE A、provider 修改或 formal evidence。正式 registry 仍仅含 TPG 的 `ma6_a5_h30km` 与 `ma8_a5_h40km`，provider 与 comparison 数值/合同未改变，也没有用户批准的统一性能 threshold。历史 Fluent 对比工况中的 30、35、40、45 km 仅是 nominal / historical labels，对应历史自定义来流，不属于任何已验证大气模型；它们只能用于相同精确来流输入下的代码—Fluent 误差对比，本 N3b 未处理 case 扩展或大气模型归属。

---

## Canonical Docs（必读）

| 文档 | 说明 |
|------|------|
| `faceted3d_current_status_zh.md` | 当前工程状态 |
| `current_model_decisions_zh.md` | 冻结模型决策 |
| `faceted3d_file_index_zh.md` | 文件索引（代码/配置/Fluent CSV） |
| `htv2_faceted3d_update_log.md` | 主线历史 |
| `faceted3d_official_cli_run_guide_zh.md` | Official CLI 跑法 |
| `audits/faceted3d_phase5b2_mapping_contract_audit_20260718.md` | Phase 5B2 mapping contract audit 的关键结论与主要定量证据；原画布未保存的完整原始统计已明确标注 |

## 技术参考

| 文档 | 说明 |
|------|------|
| `airfoils.md` | 翼型参考 |
| `functional_baseline_contract.md` | 基线合约定义 |
| `leeward_heating_model_survey.md` | 背风面模型调研 |

## Official CLI

```
scripts/run_case_rem.py
```

## 当前禁止事项

- 不修改迎风面参考焓公式 / Busemann / Kemp-Riddell / transition / chord_min_m
- cp_model = newtonian_like, A=0.38, n=1.15 已冻结
- q_scale / multiplier 禁止
- `ma8_a10_h50km` 为 formal 20–40 km 域外 reserved legacy stress/reference case；不参与训练或模型选择
- 不进入 residual learning / GPR / MoE
- Taw fixed fully turbulent `Pr^(1/3)`，与 q-chain transition 解耦
- validation complete 未声明

## 下一步

- 正式 CLI 默认大气参数域：20–40 km（几何高度输入，内部位势换算）；这只描述无 explicit override 的 CLI 运行配置，不把历史 30/35/40/45 km 自定义来流对比工况升级为已验证大气模型
- 当前 diagnostic comparison：`runs/fluent_freestream_v2/comparison_table.json`（9 工况 30–40 km）
- local-incidence classification 与 sheet-specific leeward freestream-recovery TPG Taw diagnostic 已正式收口；alpha-sign routing 不变
- current baseline schema v5，Groups 1–8，official CLI `fields.npz` 共 72 字段
- Phase 5A Fluent clean、Phase 5B1 LF clean、Phase 5B2 mapping contract audit、Phase 5C pairing、Phase 5D wall-temperature ingestion 与 Phase 5E source-level comparison：完成
- comparison 口径：direction=`Fluent→LF`，metric=`projected physical`，many-to-one allowed，no gate / no edge buffer
- Chapter 3.1–3.7A：已完成；Package 0–12=`13/13 PASS`；N3 technical exit=`CERTIFIED SATISFIED`
- GATE A：已完成，final branch=`A0`；主线仍为 `N3a`
- N3b source-identity 技术工作：完成；Git closeout 尚未完成
- current-v5 source identity：committed Git HEAD tree / Git blob bytes，schema=`git-head-tree-source-identity/v1`，inventory=`65`
- N3b QA：full pytest=`419 passed, 125 subtests passed, 0 failed`；official current regression=`PASS`
- N3b source-only migration 未改变 provider、comparison、Groups 1–8、72-field arrays 或数值资产
- 下一步：独立 Git fast-forward merge closeout；完成后返回 N3a.8，不自动进入 GATE A、provider 修改或 formal evidence
- 历史 30/35/40/45 km Fluent 对比工况均为自定义精确来流下的代码—Fluent 对比；高度仅为 nominal / historical label，不代表已验证大气模型
- N3c 尚未正式启动；N4、N6 尚未进入；residual learning 尚未启动
- 不做调参，不进 residual learning；除单独明确授权的审计证据外，不新增 closeout / manifest / audit / handoff md
