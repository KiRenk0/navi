# 0920 全湍流绝热壁面温度（参考焓法低保真模型）

本项目用参考焓法计算 0920 外形的全湍流绝热壁温 Taw，作为多保真代理模型的低保真（LF）
数据，与 Fluent 绝热壁结果（HF）配对使用。

- 数学推导：[Reference_Enthalpy_Method_Technical_Doc.md](Reference_Enthalpy_Method_Technical_Doc.md)
- 计算链与代码对应：[docs/current_calculation_chain.md](docs/current_calculation_chain.md)
- 2026-11-18 核查与修复记录：[docs/calculation_audit_2026-11-18.md](docs/calculation_audit_2026-11-18.md)

```text
scripts/run_n8_taw_case.py  (单工况)      scripts/build_lf_hf_baseline.py  (批量 LF+HF)
  -> specs/cases/*.yaml 或 run sheet 中的来流 (H, M, alpha, T_inf, p_inf)
  -> 0920 STL / outline / 连续外法向，入射量 s = -u·n
  -> 修正牛顿压力 Cp = Cp,max(M, gamma)·max(s, 0)^2
  -> 条带前缘 TPG 正激波熵 + 等熵边缘状态
  -> Eckert 参考焓恢复 r = Pr(T*)^(1/3)
  -> Taw 场、PNG、JSON、NPZ
```

## 物理闭合

- **气体**：理想气体密度；NASA-9 两段 7 系数 Cp（200–1000 K、1000–6000 K，与 Fluent air
  一致）；三系数 Sutherland 黏度；kinetic-theory 导热率 `k=mu(Cp+1.25R)`。6000 K 以上
  Cp 取端点值并一致积分 h、s，逐点用 `property_in_fit_range` 标记。设计包络内只有
  M12、约 41–58 km 的鼻部会超过 6000 K，对 Taw 的影响不超过 0.03%。
- **压力**：修正牛顿；背风面与切向面 `Cp=0`。
- **边缘状态**：每个展向条带取前缘窗口（首个有效点后 0.05 x/c）内的最大入射作参考，
  以 `M_inf·s_ref` 求热完全气体正激波（质量、动量、总焓同时满足）得到参考熵；表面
  压力下沿该等熵线求 `T_e`，`V_e^2 = 2(h0 - h_e)`。`h_e > h0` 记为失败，不改写成驻点。
  结构点与插入点读同一条带参考并直接求解。
- **恢复**：`h* = h_e + 0.72(h_aw - h_e)`，`r = Pr(T*)^(1/3)`，与 `h_aw` 迭代求解；
  迎风面与背风自由来流恢复使用同一闭合。
- **调度**：`s<=0` 自由来流恢复；`0<s<0.05` 焓空间 C1 平滑混合；`s>=0.05` 迎风候选。

每点保存参考入射、`T*`、恢复因子、边缘 `T_e/p_e/V_e`、能量与熵回代残差和状态，
summary 记录最大残差与温区外点数。

## 运行单工况

case 文件是来流参数的唯一来源，Fluent 导出按原文件名直接读取，按内容 SHA-256 记录：

```powershell
python -m pip install -r .\requirements.txt
$env:PYTHONPATH = (Resolve-Path .\src)
python .\scripts\run_n8_taw_case.py `
  --case .\specs\cases\n8_taw_c01.yaml `
  --mach 10.983 --alpha_deg 6.06 --T_inf_K 216.65 --p_inf_Pa 5529.31 `
  --run_dir .\runs\n8_taw_surface\c01
```

## 批量生成 LF+HF 基线

新增工况只需在 run sheet 加一行并放好 Fluent 导出，不需要新建任何配置文件：

```powershell
python .\scripts\build_lf_hf_baseline.py --set train --workers 6   # fenqu1-25 -> C01-C25
python .\scripts\build_lf_hf_baseline.py --set dev --workers 6     # dv01-15  -> DV01-DV15
```

每个工况输出 LF 场、映射后的 Fluent 温度与 HF−LF 残差、`case.json`（来流、角色、输入
哈希、误差指标）和图件；数据集级输出 `case_manifest.csv`、`case_metrics.csv`、
`DATASET.json`（求解器源码哈希）。Fluent CSV 和映射算子不复制。脚本拒绝覆盖已有工况，
失败工况不留暂存。输出目录在本机，不进入版本控制。

## 回归基线

`baselines/0920_fully_turbulent_taw/` 冻结 C01（20 km、M10.983、6.06°）的完整 LF 产物，
manifest 锁定 case、STL、outline、sampling、projection cache 与全部产物的 SHA-256：

```powershell
python .\scripts\tools\0920_taw_baseline.py `
  --manifest .\baselines\0920_fully_turbulent_taw\manifest.json --replay
```

C01 相对 Fluent 的平均相对误差为上表面 3.48%、下表面 3.18%，LF 整体偏高。这是低保真
模型的系统偏差，由多保真模型修正；基线只用于回归，不代表全包络精度。

## 测试

```powershell
python -m pytest -q                 # 单元与契约测试
python -m pytest -q -m integration  # 实际运行 CLI 并逐字段 replay 基线
```

## 本机数据（不进入版本控制）

`fluent_export/`（Fluent 原始导出）、`runs/`（运行输出与 projection cache）和
`fenqu_zanshi/`（分区研究子工程及 40 工况基线）只保存在本机。
