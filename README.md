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
  --case .\specs\cases\n8_taw_ma8_a5_h40km.yaml `
  --mach 8 `
  --alpha_deg 5 `
  --h_m 40000 `
  --run_dir .\runs\n8_taw_surface\official_0920_taw_smoke
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

## 测试

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
python -m pytest -q
```

默认测试覆盖全部 13 个 case authority、source identity、baseline manifest 和
88-field artifact contract。正式集成验证会实际运行 CLI 并逐字段 replay NPZ：

```powershell
python -m pytest -q -m integration
```

pytest 只扫描 `tests/active/`；runtime `runs/` 不属于软件合同。
