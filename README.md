# 0920 全湍流绝热壁面温度

本项目的唯一正式计算目标是：

- 几何 authority：`0920`
- 流态：`fully turbulent`
- 温度目标：`adiabatic wall temperature (Taw)`

活动生产链只有一条：

```text
scripts/run_n8_taw_case.py
  -> 0920 vehicle/STL/outline
  -> USSA1976 或成对的 T_inf_K/p_inf_Pa
  -> Faceted3D 连续法向与几何域
  -> fully turbulent TPG Taw provider
  -> upper/lower surface field、PNG、JSON、NPZ
```

## 运行

在仓库根目录执行：

```powershell
python -m pip install -r .\requirements.txt
$env:PYTHONPATH = (Resolve-Path .\src)
python .\scripts\run_n8_taw_case.py `
  --case .\specs\cases\n8_taw_ma5_a10_h60km.yaml `
  --mach 5 `
  --alpha_deg 10 `
  --h_m 60000 `
  --run_dir .\runs\n8_taw_surface\official_0920_taw
```

运行结果必须包含 `summary.json`、`Taw_surface_fields.npz`、误差统计和上下表面图，并遵循当前 88-field Taw schema。

## Baseline

`baselines/0920_fully_turbulent_taw/manifest.json` 是当前正式 baseline。它锁定 0920 case/spec、STL、outline、sampling、projection cache 以及 run artifacts 的 SHA-256。重新校验：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
python .\scripts\tools\0920_taw_baseline.py `
  --manifest .\baselines\0920_fully_turbulent_taw\manifest.json `
  --replay
```

## 新网格比较

新的 Fluent 网格比较使用
`specs/cases/n8_taw_ma5_a10_h60km.yaml`，对应
`fluent_export/adiabatic_wall_csv/21.96pa_247.02k_60km_10alpha_5ma.csv`。
该导出的原始列顺序为 `x, up, span`，case 会使用对应的 projection cache。运行后生成
`Taw_error_vs_fluent_upper.png` 和
`Taw_error_vs_fluent_lower.png`：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
python .\scripts\run_n8_taw_case.py `
  --case .\specs\cases\n8_taw_ma5_a10_h60km.yaml `
  --mach 5 `
  --alpha_deg 10 `
  --h_m 60000 `
  --run_dir .\runs\n8_taw_surface\newgrid_ma5_a10_h60km
```

## 测试

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
python -m pytest -q
```

默认测试覆盖当前 case authority、source identity、baseline manifest 和
88-field artifact contract。正式集成验证会实际运行 CLI 并逐字段 replay NPZ：

```powershell
python -m pytest -q -m integration
```

pytest 只扫描 `tests/active/`；runtime `runs/` 不属于软件合同。
