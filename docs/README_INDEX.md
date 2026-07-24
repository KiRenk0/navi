# Faceted3D v2 — 文档索引

> 更新：2026-07-25
> 用途：新接手 DS/GPT 快速定位

## 当前主线一句话

Route A-TPG（thermally-perfect-gas）是**唯一正式且唯一可运行**的 thermodynamic baseline；CLI 不提供 thermodynamics 选择。N6.0、N6.1、N6.2a、N6.2b 与 N6.3 已完成；N6.4 docs-only certification candidate 已实施并 pending independent QA，整个 N6 不得表述为完成；GATE C 未裁决，N7 未进入。N6.3 canonical analysis package 为 `runs/n6_3_layered_error_portrait/20260724T151247Z_e279af25b509_n6_3_layered_error_portrait`，正式入口为 `scripts/tools/n6_3_layered_error_portrait.py`。current-v5 source identity 使用 committed Git HEAD tree / Git blob bytes，schema=`git-head-tree-source-identity/v1`，inventory=`68`。正式 registry 仍仅含 `ma6_a5_h30km` 与 `ma8_a5_h40km`；provider 未修改、无统一 performance threshold、无 model performance PASS/FAIL。历史 30、35、40、45 km 仅为 nominal / historical labels，对应 historical custom freestream，不属于已验证大气模型。

---

## Canonical Docs（必读）

| 文档 | 说明 |
|------|------|
| `faceted3d_current_status_zh.md` | 当前工程状态 |
| `current_model_decisions_zh.md` | 冻结模型决策 |
| `faceted3d_file_index_zh.md` | 文件索引（代码/配置/Fluent CSV） |
| `htv2_faceted3d_update_log.md` | 主线历史 |
| `faceted3d_official_cli_run_guide_zh.md` | Official CLI 跑法 |
| `n6_4_exit_certification_zh.md` | N6.4 coverage / exclusion / engineering limitations / third-party reproducibility / N6 exit-condition 的 tracked canonical certification candidate；当前状态为 `pending independent QA`，不表示 N6 已正式完成 |
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

## 当前 N6 状态

- N6.0、N6.1、N6.2a、N6.2b、N6.3：completed
- N6.4 docs-only certification candidate：implemented，pending independent QA；N6 final sign-off 未签发
- GATE C：not decided；N7：not entered
- canonical analysis：`runs/n6_3_layered_error_portrait/20260724T151247Z_e279af25b509_n6_3_layered_error_portrait`
- current-v5 source identity：68 sources；Groups 1–8、72 fields、numerical assets、artifact hashes zero drift
- QA/regression PASS 不是 model performance PASS；provider unchanged，无 performance threshold 与 causal attribution

## 下一步

- 正式 CLI 默认大气参数域：20–40 km（几何高度输入，内部位势换算）；这只描述无 explicit override 的 CLI 运行配置，不把历史 30/35/40/45 km 自定义来流对比工况升级为已验证大气模型
- 当前 diagnostic comparison：`runs/fluent_freestream_v2/comparison_table.json`（9 工况 30–40 km）
- local-incidence classification 与 sheet-specific leeward freestream-recovery TPG Taw diagnostic 已正式收口；alpha-sign routing 不变
- current baseline schema v5，Groups 1–8，official CLI `fields.npz` 共 72 字段
- Phase 5A Fluent clean、Phase 5B1 LF clean、Phase 5B2 mapping contract audit、Phase 5C pairing、Phase 5D wall-temperature ingestion 与 Phase 5E source-level comparison：完成
- comparison 口径：direction=`Fluent→LF`，metric=`projected physical`，many-to-one allowed，no gate / no edge buffer
- Chapter 3.1–3.7A：已完成；Package 0–12=`13/13 PASS`；N3 technical exit=`CERTIFIED SATISFIED`
- GATE A：已完成，final branch=`A0`；主线仍为 `N3a`
- N3b source-identity 修复与 Git closeout：已完成
- current-v5 source identity：committed Git HEAD tree / Git blob bytes，schema=`git-head-tree-source-identity/v1`，inventory=`68`
- N6.0、N6.1、N6.2a、N6.2b、N6.3 已完成；N6.4 docs-only certification candidate 已实施并 pending independent QA；GATE C 未裁决，N7 未进入
- N6.3 independent QA 与 full regression 已通过；provider、formal registry、performance threshold 均未改变
- 不做调参，不进 residual learning；除单独明确授权的审计证据外，不新增 closeout / manifest / audit / handoff md
