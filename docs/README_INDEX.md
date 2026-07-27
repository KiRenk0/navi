# Faceted3D v2 - 文档索引

> 更新：2026-07-27
> 用途：从当前代码状态进入；历史认证和审计按原日期保留

## 当前主线

- Route A-TPG 是正式低保真求解器唯一可运行的 thermodynamic baseline；`scripts/run_case_rem.py` 是正式主入口。
- current-v5 保持 Groups 1-8、72-field serialization 和两个正式 registry case，不因 N8 回算。
- N6.0-N6.4 已完成并签署；N7 bounded engineering-freeze candidate 的 independent QA、final approval 与 main closeout 状态以 N7 认证文档为准。
- N8 Taw surface 的 G1-G4 已闭合，12/12 `*_phase13_geometry_domain_v4` 工况 PASS，每工况 13 件产物。
- 最近全量回归：`508 passed, 137 subtests passed`。

PASS 表示程序、合同、资产与回归完整性通过，不自动表示 provider 物理精度或统一 performance threshold 通过。

## 当前说明

| 文档 | 当前职责 |
|------|----------|
| `faceted3d_current_status_zh.md` | 当前工程与闭合状态 |
| `current_model_decisions_zh.md` | 现行模型、几何、provider 和合同决策 |
| `faceted3d_file_index_zh.md` | 当前源码、脚本、spec、结果和证据索引 |
| `functional_baseline_contract.md` | 正式 solver 与 N8 的输入输出合同 |
| `faceted3d_official_cli_run_guide_zh.md` | 正式 solver、N8 和只读验证命令 |
| `airfoils.md` | 翼型格式与参考 |
| `leeward_heating_model_survey.md` | 背风模型调研及当前 N8 边界 |

## 历史与治理文档

| 文档 | 性质 |
|------|------|
| `htv2_faceted3d_update_log.md` | 只追加的主线历史；旧 v2/v3/phase 记录不是当前入口 |
| `n6_4_exit_certification_zh.md` | 已签署 N6 历史认证 |
| `n7_bounded_engineering_freeze_certification_zh.md` | N7 candidate/change-gate authority |
| `audits/faceted3d_phase5b2_mapping_contract_audit_20260718.md` | 历史 mapping 审计证据 |

签署认证、历史 audit 和旧日志条目不因代码清理改写。

## 正式入口

- 主求解器：`scripts/run_case_rem.py`
- N8 Taw surface：`scripts/run_n8_taw_case.py`
- current-v5 只读回归：`scripts/tools/current_baseline_regression_check.py`
- N6.3 canonical 只读验证：`scripts/tools/n6_3_layered_error_portrait.py --validate-existing`

仓库使用 `src/` 布局。运行测试时显式设置当前仓库源码：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
python -m pytest -q
```

## N8 Taw Surface v4

当前正式产品目录：

```text
runs/n8_taw_surface/*_phase13_geometry_domain_v4
```

当前合同：

- summary：`n8-taw-run-summary/v4`
- dispatch：`n8-taw-dispatch/v3`
- normal：`stl-angle-weighted-continuous-normal/v1`
- topology：`n8-taw-domain-topology/v1`
- 每工况 9,663 nodes、18,110 triangles、333 typed legacy exclusions
- provider-valid=geometry-valid=9,663/9,663
- 12/12 runner PASS，12/12 validator PASS
- 每工况 13 件产物

误差图同时保留：

- `Taw_error_vs_fluent_upper/lower.png`：固定 `-10%..+10%`
- `Taw_error_vs_fluent_upper/lower_auto_range.png`：各 sheet 有效有限误差的实际 min..max

G1-G4 证据：

- `attachment/Faceted3D_v2_G1_G2_geometry_domain_closure_20260727.md`
- `attachment/Faceted3D_v2_G3_geometry_domain_implementation_validation_20260727.md`

N8 v4 是工程闭合的 Taw surface product contract，不是 provider CFD validation、baseline promotion 或统一性能 PASS。

## 清理边界

已删除可再生缓存和明确标为 superseded/temp/closeout 的 `scripts/_archive/`。`src/`、`tests/`、`specs/`、current-v5/N6/N7 validator 与 N8 生产链不得仅凭文件名或浅层“无直接引用”删除；必须证明无入口、无公开 API、无动态/相对导入、无测试、无资产复现依赖且已有替代者。