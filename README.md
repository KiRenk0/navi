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
  -> Faceted3D 连续外法向与 s=-u·n 入射量
  -> 修正牛顿压力系数 Cp=Cp,max(M,gamma)·max(s,0)^2
  -> fully turbulent TPG Taw provider
  -> upper/lower surface field、PNG、JSON、NPZ
```

## 当前物理闭合

- 坐标约定为机体系 `x` 向后、`y` 为展向、`z` 向上；无侧滑来流方向为
  `u=(cos(alpha), 0, sin(alpha))`。上下表面都先构造真实外法向，再统一计算
  `s=-u·n_out`，不再使用上下表面共用的斜率符号近似。
- 压力闭合只有一套修正牛顿模型。`Cp,max` 由当前 Mach 数和 `gamma` 的法向激波后
  总压确定；背风面和切向面使用 `Cp=0`。车辆 YAML 中没有旧固定系数、模型选择器、
  effective-alpha/Mach 开关或 `phi` 正值钳制。
- 密度采用 ideal gas，`Cp/h/s` 采用与 Fluent air 对齐的 NASA-9 分段多项式，粘度采用
  `C1=1.716e-5`、`Tref=273.11 K`、`S=110.56 K` 的 Sutherland 公式，导热率采用
  Fluent kinetic-theory 对应的 modified Eucken 关系
  `k=mu·(Cp+1.25R)`。
- 恢复因子中的局部 Prandtl 数直接由 `Pr(T)=mu(T)Cp(T)/k(T)` 得到；case 文件不提供
  一个不会参与计算的常数 Prandtl 数。
- 鼻尖允许物理合理的亚声速或驻点边缘状态，不再为了强制 `Ma_e>=1` 降低 `Cp0`。
  如果压力/熵闭合给出 `h_e>h0`，代码会把边缘状态一致地限制到驻点焓，并同步更新
  `T_e`、`rho_e` 和 `V_e`。
- `s<=0` 使用自由来流恢复温度；`0<s<0.05` 在焓空间进行 C1 平滑混合；
  `s>=0.05` 使用全湍流迎风候选值。

设计参数范围为高度 20--60 km、Mach 5--12、攻角 -10--10 deg。压力闭合会随
Mach 数自动变化，但当前正式 Fluent 数值验证只有 `Ma=5, alpha=10 deg, h=60 km`
这一组，不应把单工况误差直接外推为全包线精度。

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

当前 baseline 中，Ma=5 时 `Cp,max=1.80877`；此前锁定的鼻尖对照位置上，代码
Taw 约为上表面 `1353.66 K`、下表面 `1377.46 K`。鼻尖 `x<0.1 m` 区域相对
Fluent 的误差范围为上表面约 `-2.72%` 到 `+3.47%`、下表面约 `-2.47%` 到
`+2.08%`。

## 新网格比较

新的 Fluent 网格比较使用
`specs/cases/n8_taw_ma5_a10_h60km.yaml`，对应
`fluent_export/adiabatic_wall_csv/21.96pa_247.02k_60km_10alpha_5ma.csv`。
该导出的原始列顺序为 `x, up, span`，case 会使用对应的 projection cache。运行后生成
`Taw_error_vs_fluent_upper_auto_range.png` 和
`Taw_error_vs_fluent_lower_auto_range.png`。同时生成按鼻尖区域有效误差独立调整色标的
`Taw_error_vs_fluent_upper_nose_x_lt_0p1m_auto_range.png` 和
`Taw_error_vs_fluent_lower_nose_x_lt_0p1m_auto_range.png`。两图使用同一插值网格和同一份
0920 权威轮廓。Fluent 锐缘节点会归入侧面而不是上下表面，因此绘图会把上下表面
误差场以最近值延拓过半个边界网格；仅当缺口不超过局部 Fluent 三角网格 P95 边长的
3 倍时允许延拓，超过该范围会直接报错：

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
