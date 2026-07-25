# Faceted3D Official CLI 与 N6/N7 canonical 验证运行指南

---

## 入口

```
scripts/run_case_rem.py
```

## 标准命令模板

```
python scripts/run_case_rem.py \
  --vehicle specs/vehicles/htv2_faceted3d_0629.yaml \
  --case specs/cases/doc_ma6_alpha5_h30km_faceted3d.yaml \
  --sampling specs/sampling/engineering_full_wing_surface_grid_81x41.yaml \
  --mach <MACH> \
  --alpha <ALPHA_DEG> \
  --h_m <ALTITUDE_M> \
  --run_dir <RUN_DIR> \
  --no_plots \
  --save_npz \
  --transition_weighting step
```

TPG 是唯一正式且唯一可运行的 thermodynamic model；CLI 无 thermodynamics 选择参数。

`--h_m` 为**几何高度**（m），内部自动换算为位势高度后按 1976 标准大气分层计算。

### 显式自由流覆盖（optional）

```
--T_inf_K <T_inf> --p_inf_Pa <p_inf>
```

- 两者必须**成对提供**，禁止只覆盖一个
- 显式提供后跳过大气模型，直接使用指定 T/p
- `altitude` 仍保留为工况标签及几何/文档信息
- 输出 `summary.json` 的 `freestream_source` 为 `explicit_override`
- 不提供时使用默认标准大气

## 关键规则

1. 工况参数**必须**通过 `--mach / --alpha / --h_m` 显式输入。不要靠文件夹名、旧 archive、旧 YAML metadata 推断
2. Route A-TPG 是唯一正式且唯一可运行的 thermodynamic model；CLI 无 thermo 选择
3. 默认 geometry 来自 root `new_spec/`（STL + outline），已在 vehicle YAML 中配置
3. HTV2 cp_model 已在 `specs/vehicles/htv2_faceted3d_0629.yaml` 显式冻结为 `newtonian_like`, A=0.38, n=1.15
4. 输出 `summary.json` 必须检查：
   - `actual_mach` / `actual_alpha` / `actual_h_m` 与 CLI 一致
   - `actual_cp_model` = `newtonian_like`
   - `actual_cp_newtonian_A` = 0.38, `actual_cp_newtonian_n` = 1.15
   - `actual_stl_path` / `actual_outline_path` 指向 `new_spec/`
5. `--transition_weighting step` 控制的是 **q-chain** 的层流/湍流分支混合权重。Taw 固定使用 fully turbulent `Pr^(1/3)` recovery，不通过 `--transition_weighting` 控制。

## Sampling

`specs/sampling/engineering_full_wing_surface_grid_81x41.yaml` 保持 81×41 维度。翼尖 row 40 动态移动到最外侧 `chord>=chord_min_m` 的有效站位；当前 windward 有效点为 3321。`chord_min_m=0.02 m` 未修改，最外侧约 3.50 mm 合法零弦长尖端 sliver 保持空白。

## Current regression

- 唯一命令：`python scripts/tools/current_baseline_regression_check.py`
- baseline 仅含 TPG 两工况：`ma6_a5_h30km`、`ma8_a5_h40km`
- snapshot 位于 `runs/current_baseline_snapshot/tpg/`，严格比较 shape、dtype、NaN mask、mandatory fields、row 40 与 endpoint metadata；当前浮点合同要求 byte-exact 且 `max_abs_diff=0`
- Groups 1–8 全部纳入合同；Group 8 为 18 个 sheet-specific leeward freestream-recovery 字段；`fields.npz` 共 72 字段，baseline schema `current-tpg-baseline-regression/v5`

## `fields.npz` leeward recovery 字段

official CLI 自动序列化 18 个 Group 8 字段：

- bool masks：`mask_leeward_upper`、`mask_leeward_lower`
- float64 edge-state：`T_e_leeward_upper`、`T_e_leeward_lower`、`p_e_leeward_upper`、`p_e_leeward_lower`、`rho_e_leeward_upper`、`rho_e_leeward_lower`、`V_e_leeward_upper`、`V_e_leeward_lower`、`Ma_e_leeward_upper`、`Ma_e_leeward_lower`、`h_e_leeward_upper`、`h_e_leeward_lower`、`mu_e_leeward_upper`、`mu_e_leeward_lower`
- float64 recovery temperature：`Taw_tpg_leeward_upper`、`Taw_tpg_leeward_lower`

每个 sheet 的 mask 唯一定义为 `surface_class_<sheet> == -1`；所有连续字段在 mask 外为 NaN。upper/lower 是 geometric sheet，leeward 是 aerodynamic class；不存在 generic `Taw_tpg_l` 字段。

## Local-Incidence QA 工具

```text
python scripts/tools/local_incidence_raw_facet_qa.py
python scripts/tools/local_incidence_alpha_scan.py
```

- 仅为 geometry/classification QA；不切换正式 solver routing；sheet-specific leeward recovery 由 official run 自动序列化，不由这些 QA 工具生成
- `local_incidence_raw_facet_qa.py` 默认 stdout 输出，`--plots DIR` 可选生成诊断图
- `local_incidence_alpha_scan.py` 默认生成 JSON + summary PNG，`--detailed-plots` 可选逐攻角图

## N6.3 canonical validation

正式入口：`scripts/tools/n6_3_layered_error_portrait.py`；模式为 `--execute` 与 `--validate-existing`。现有 canonical run 只允许验证，不得重复执行覆盖；任何新执行必须生成新 run ID，且不得 overwrite 已存在目录。

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
$env:PYTHONDONTWRITEBYTECODE = "1"

python -B scripts/tools/n6_3_layered_error_portrait.py `
  --validate-existing `
  --analysis-root runs/n6_3_layered_error_portrait/20260724T151247Z_e279af25b509_n6_3_layered_error_portrait
```

N6.2b canonical package available：`runs/n6_exact_custom_formal/20260724T111443Z_79ed536fc8c1_n6_exact_custom`。N6.3 canonical package available：`runs/n6_3_layered_error_portrait/20260724T151247Z_e279af25b509_n6_3_layered_error_portrait`。N6.3 `--validate-existing` 是 official 只读验证入口；`current_baseline_regression_check.py` 是 official current regression 入口；`docs/n6_4_exit_certification_zh.md` 是 official N6.4 certification document。

该 validation PASS 证明 program、contract、asset 与 regression integrity，不表示 model performance PASS。N6.4 certification document 已正式签发。N6 closeout 时点的 GATE C/N7 文本属于历史状态；current governance 已由后续 GATE C OPTION 3 approval 与 N7 candidate authority supersede。

## N6.4 canonical certification

正式文档：`docs/n6_4_exit_certification_zh.md`。其状态为 `N6.4 COMPLETE`、`N6 strategic exit SIGNED / COMPLETE`、`N6 final sign-off ISSUED`；其中 GATE C/N7 表述只记录 N6 closeout 当时状态，不再作为 current action。该文档不是 solver、analysis 或 release 命令入口。

## N7 bounded engineering-freeze candidate 与后续独立 QA 入口

治理 authority：`docs/n7_bounded_engineering_freeze_certification_zh.md`。当前状态为 GATE C complete、OPTION 3 bounded/degraded freeze approved、N7 entry authorized、candidate implementation complete；independent QA、user final approval 与 main closeout pending，tag/release not created。

后续独立 QA 只允许复用现有只读验证入口：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
$env:PYTHONDONTWRITEBYTECODE = "1"

python -B scripts/tools/current_baseline_regression_check.py
python -B scripts/tools/n6_3_layered_error_portrait.py `
  --validate-existing `
  --analysis-root runs/n6_3_layered_error_portrait/20260724T151247Z_e279af25b509_n6_3_layered_error_portrait
python -B -m pytest -p no:cacheprovider <existing-test-selection>
```

这些入口只允许在后续独立 QA 的明确范围内运行；不得发明新 CLI/API。明确禁止 `n6_3_layered_error_portrait.py --execute`、solver、formal generation、new analysis、`current_baseline_regression_check.py --freeze`、baseline promotion、manifest migration、summary-hash repair、evidence generation 或 candidate generation。

## Fluent 对比

正确 mapping: LF `(x_w_m, span_w_m)` → Fluent `(x-coordinate, y-coordinate)`

**Fluent CSV 的 `y-coordinate` 是 spanwise 轴，`z-coordinate` 是厚度方向。** 不要用 `(x,z)` 匹配 span。

Fluent 四工况 CSV 位于 `fluent_export/adiabatic_wall_csv/`。

## 禁止

- 不修改 src / specs / YAML / Fluent CSV
- `ma8_a10_h50km` 为 formal 域外 reserved legacy stress/reference case，不参与当前训练或模型选择
- 不进入 residual learning / GPR / MoE
- 不使用 q_scale / multiplier
- 不声明 validation complete
