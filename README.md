# 参考焓法气动热工程实现

本仓库包含两条受测试保护的计算产品线：

1. `scripts/run_case_rem.py`：正式低保真参考焓法求解器，支持二维翼型与 Faceted3D，输出热流、恢复温度、壁温及审计字段。
2. `scripts/run_n8_taw_case.py`：N8 联合 upper/lower Taw surface 产品，使用连续 STL 法向、几何域拓扑和 Fluent 壁温对比。

当前热力学正式路线只有 TPG。`src/ref_enthalpy_method/atmosphere/ussa1976.py` 是唯一活动标准大气实现；显式 `T_inf_K/p_inf_Pa` 必须成对提供并优先于高度推导。

## 快速入口

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

正式 Faceted3D 工况：

```powershell
python scripts/run_case_rem.py ^
  --vehicle specs/vehicles/htv2_faceted3d_0629.yaml ^
  --case specs/cases/doc_ma6_alpha5_h30km_faceted3d.yaml ^
  --sampling specs/sampling/engineering_full_wing_surface_grid_81x41.yaml ^
  --mach 6 --alpha 5 --h_m 30000 ^
  --run_dir runs/example_faceted3d ^
  --save_npz --no_plots
```

N8 Taw surface 工况：

```powershell
python scripts/run_n8_taw_case.py ^
  --case specs/cases/n8_taw_ma8_a10_h40km.yaml ^
  --mach 8 --alpha_deg 10 --h_m 40000 ^
  --run_dir runs/n8_taw_surface/example_n8
```

测试：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
python -m pytest -q
```


## 当前闭合状态

- current-v5 正式基线：Groups 1-8，72-field solver serialization；正式 registry 仍为 `ma6_a5_h30km`、`ma8_a5_h40km`。
- N6.0-N6.4：完成并签署；N7 bounded engineering-freeze candidate 的治理状态见专门认证文档。
- N8 Taw surface：G1-G4 全部 PASS，12/12 工况通过；当前产品目录为 `runs/n8_taw_surface/*_phase13_geometry_domain_v4`，每工况 13 件产物。
- 最近全量回归：`508 passed, 137 subtests passed`。

PASS 表示程序、合同、资产和回归完整性通过，不自动等于 provider 物理精度或统一性能门限通过。

## 代码结构

```text
src/ref_enthalpy_method/
  aero/          压力、外缘状态、恢复温度、迎/背风气动热候选
  atmosphere/    USSA1976 标准大气
  config/        低保真热流配置
  gas/           TPG 热力学与输运
  geometry/      翼型、Faceted3D、精确投影、连续法向、N8 域拓扑
  heatflux/      前缘、迎风、背风热流
  mapping/       Fluent 清洗、投影、配对、壁温摄取和误差对比
  sampling/      采样网格
  specs/         YAML 加载与数据模型
  thermal/       定常/瞬态壁温
  analysis/      已认证分析的可复用实现
  solver.py
  solver_faceted3d.py
  n8_taw_surface.py
scripts/
  run_case_rem.py
  run_case_sweep.py
  run_n8_taw_case.py
  geometry/ pressure/ tools/ viz/
specs/
tests/
docs/
```

当前状态、代码索引、输入输出和维护边界统一从 docs/README_INDEX.md 进入。
