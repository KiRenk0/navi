# Phase 2D 标准诊断主目录

本目录是 Phase 2D 当前活跃的诊断证据中心，**不是历史废弃目录**。

## 内容清单

| 任务 | 文件 | 说明 |
|------|------|------|
| T1 | `phase2d_region_master_table.csv` | 两工况全区域标准口径误差总表 |
| T2 | `windward_q_chain_audit.csv` | 迎风面 q 量级链逐点审计 |
| T3 | `capmask_metric_recheck.csv` | cap_mask 指标冲突复核 |
| T4 | `aft_body_outlier_transition_audit.csv` | aft_body 离群/transition 审计 |
| T5 | `alignment_sanity_by_region.csv` | 各区域对齐映射质量 |
| — | `capmask_nose_audit.csv` | 历史鼻锥审计（已被 T3 supersede） |
| — | `le_pressure_diagnostic_corrected.csv` | LE 压力诊断（修正版） |
| — | `le_pressure_diagnostic.csv` | LE 压力诊断（v1 错误版，保留参考） |
| — | `le_consistency_audit.csv` | LE 一致性审计 |
| 图件 | `figures/` | T1–T4 所有诊断图 |

## 标准口径

solver 全链 newtonian（cp_model=newtonian_like, A=0.38, n=1.15），transition.weighting=step。仅 ma6_a5_h30km 和 ma8_a5_h30km 两工况。ma8_a10_h50km 保持 holdout 冻结。

## 关联文档

- `docs/faceted3d_v2_phase2d_region_master_table_zh.md`
- `docs/faceted3d_v2_phase2d_windward_q_chain_audit_zh.md`
- `docs/faceted3d_v2_phase2d_capmask_metric_recheck_zh.md`
- `docs/faceted3d_v2_phase2d_aft_body_outlier_transition_audit_zh.md`
- `docs/faceted3d_v2_phase2d_alignment_sanity_by_region_zh.md`

## 旧版本弃用说明

在此之前由 `capmask_nose_audit.py` 生成的 `capmask_nose_audit.csv` 使用同一标准口径，但其 `q_ratio=7.98/8.41`（cap_mask）已被 T3 直接 Fluent 统计判定为指标/映射伪信号。应以 `capmask_metric_recheck.csv` 为准。
