# Faceted3D v2 — 文档索引

> 更新：2026-07-20
> 用途：新接手 DS/GPT 快速定位

## 当前主线一句话

Route A-TPG（thermally-perfect-gas）是**唯一正式且唯一可运行**的 thermodynamic baseline；CLI 不提供 thermodynamics 选择。正式高度参数域 **20–40 km**。Taw 固定使用 fully turbulent `Pr^(1/3)` recovery。Fluent clean、LF clean、Phase 5C pairing、Phase 5D ingestion、Phase 5E source-level comparison、Chapter 3.1 正式 evidence 入口审计、Chapter 3.2 Evidence 合同与资产边界，以及 Chapter 3.3 技术实现与验证均已完成；Chapter 3 整体尚未完成，下一小节为 3.4 Case-level descriptive summary 与图表。N3 尚未完成，N3c 尚未正式启动，GATE A 尚未进入，strategy v1.0 保持冻结。冻结 comparison 口径为 direction=`Fluent→LF`、metric=`projected physical`、many-to-one allowed、no gate / no edge buffer；provider、comparison、pairing、ingestion 与 baseline 均未因 Chapter 3.2/3.3 改变。current regression 为 162 tests、117 subtests、schema v5、72 fields、Groups 1–8 zero drift；唯一命令是 `python scripts/tools/current_baseline_regression_check.py`，baseline 仅含 TPG 的 `ma6_a5_h30km` 与 `ma8_a5_h40km`。CPG runtime、current compatibility baseline 与 phase4a0 replay 均已删除；历史 CPG→TPG 改善只作为历史证据。

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

- 正式参数域：20–40 km，30/35/40 km 标准大气（几何高度输入，内部位势换算）
- 当前 diagnostic comparison：`runs/fluent_freestream_v2/comparison_table.json`（9 工况 30–40 km）
- local-incidence classification 与 sheet-specific leeward freestream-recovery TPG Taw diagnostic 已正式收口；alpha-sign routing 不变
- current baseline schema v5，Groups 1–8，official CLI `fields.npz` 共 72 字段
- Phase 5A Fluent clean、Phase 5B1 LF clean、Phase 5B2 mapping contract audit、Phase 5C pairing、Phase 5D wall-temperature ingestion 与 Phase 5E source-level comparison：完成
- comparison 口径：direction=`Fluent→LF`，metric=`projected physical`，many-to-one allowed，no gate / no edge buffer
- Chapter 3.1 正式 evidence 入口审计：已完成；裁决为已有部分入口但不完整，不能直接承担 Chapter 3 正式 evidence
- Chapter 3.2 Evidence 合同与资产边界：已完成
- Chapter 3.3 Source-level evidence 技术实现与验证：已完成
- 当前唯一下一小节：3.4 Case-level descriptive summary 与图表；尚未开始
- Chapter 3 整体与 N3 尚未完成；N3c 尚未正式启动；GATE A 尚未进入；strategy v1.0 保持冻结
- residual learning 尚未启动
- 不做调参，不进 residual learning；除单独明确授权的审计证据外，不新增 closeout / manifest / audit / handoff md
