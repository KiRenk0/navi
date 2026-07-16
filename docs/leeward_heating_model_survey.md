# Leeward / 3D Hypersonic Engineering Heat Flux Model Survey

> 调研日期: 2026-06-28
> 目标: 评估当前 Faceted3D 背风面常值模型是否有更合理的工程替代路线

---

## 1. 当前代码背风面模型概述

当前背风面模型在 `src/ref_enthalpy_method/heatflux/leeward.py` 中实现，核心公式：

**Re_ns** (Eq. 2.45): 正激波后参考 Reynolds 数（每 strip 一个标量值）
```
Re_ns = ρ_inf · V_inf · R_ref / mu_ns
```
其中 `R_ref` 是该 strip 的有效弦长（`chord_eff`，受 `chord_min_m=0.02` 钳制），`mu_ns` 由正激波后温度 `T_ns` 通过 Sutherland 公式计算。

**St** (Eq. 2.44): Stanton 数（每 strip 的 x/c 函数）
```
St(x) = 0.00282 · (0.7905 + 1.067 · h_wwd(x) / h_s) · Re_ns^(-0.37)
```

**q_l** (Eq. 2.43): 背风面热流
```
q_l(x) = ρ_inf · V_inf · St(x) · (h_s - h_w)
```

**当前运行结果 (`runs/0629_fields_phase4`)**:

| 变量 | 值 | 空间变化? |
|------|----|-----------|
| q_l | 1,076.87 W/m² | **常数** |
| St_l | 2.68e-4 | **常数** |
| Re_ns_l | 405.73 | **常数** |

---

## 2. 当前模型为什么是常值

三条独立原因叠加导致全表面常值：

### 2a. Re_ns 恒值 — 弦长钳位效应

`Re_ns` 公式中唯一随 strip 变化的参数是 `R_ref`，它来自 `chord_eff`。对于所有 strip，`chord_eff = max(chord, chord_min_m) = max(chord, 0.02)`。实际弦长从根部 3.6m 减小到翼尖 ~0.006mm，但翼尖被 `chord_min_m=0.02` 钳住，所有 strip 的有效弦长都 ≥0.02。对于 isothermal300 工况，`Re_ns` 变成全表面常数。

### 2b. St 恒值 — h_wwd 不变

`St(x)` 公式中唯一 x/c 依赖项是 `h_wwd(x)`（背风面壁焓）。对于 isothermal 壁温 (Tw=300K)，`h_wwd(x) = h_w = constant`。因此 St 不再随 x/c 变化。

### 2c. q_l 恒值 — 所有输入不变

`q_l = ρ_inf · V_inf · St · (h_s - h_w)` 中所有项在 strip 内均为常数 → q_l 恒值。不同 strip 间因 Re_ns 相同 → q_l 全表面恒值。

### 2d. 模型结构局限

背风面模型使用**正激波后状态**作为参考，而非局部外缘状态。这意味着：
- 没有局部外缘 T_e、p_e、ma_e、rho_e、v_e
- 没有 x/c 相关的流线发展长度
- 没有展向流或三维效应
- 没有膨胀波或横流修正

这些都不是"bug"——这是当前工程模型的**设计选择**，其原始用途是为二维/2.5D 片条理论提供一个可接受的背风面热流量级。

---

## 3. 可选升级路线

### 路线 A: 保持当前模型，将背风面误差交给残差学习

**思路**: 当前模型给出正确量级（1,077 W/m²），空间均匀。后续多保真代理模型可以用 Fluent 高保真数据训练残差修正。

**需要新增的输入**: 无

**是否需要 Fluent 外缘场**: 否（但需要 Fluent 背风面热流作为修正目标）

**是否需要表面流线**: 否

**实现难度**: 无（维持现状）

**收益**: 零开发成本；背风面加热量级正确（占迎风面 max 的 0.28%，对总热载荷贡献极小）；残差代理模型可以吸收系统偏差

**风险**: 如果 Fluent 显示背风面有强烈空间变化（如膨胀区热流升高、再压缩区热点），单一修正因子不够

**推荐指数**: ⭐⭐⭐⭐⭐（当前阶段首选）

### 路线 B: 给背风面引入 x/c 相关的经验 Stanton 分布

**思路**: 不改变 Re_ns 结构，但将 Stanton 公式从常数 h_wwd 改为一个经验的 x/c 分布：
```
St(x) = St_base · f(x/c)
```
其中 `f(x/c)` 来自文献经验分布（如层流 Blasius 或湍流 1/7 次方律的形状函数）。

**需要新增的输入**: 无（完全自包含）

**是否需要 Fluent 外缘场**: 否

**是否需要表面流线**: 否

**实现难度**: 低（修改 leeward.py 中的 stanton_number 或 leeward_stanton_distribution）

**收益**: 引入合理的 x/c 衰减趋势；背风面前缘热流略高、后缘略低，更符合物理

**风险**: 
- 经验形状函数可能需要根据具体工况调整系数
- 当前是 isothermal 壁温；如果改为辐射平衡，形状函数可能需要重新标定

**推荐指数**: ⭐⭐⭐（中等优先，可作为 Fluent 对比后的改进项）

### 路线 C: 基于局部外缘状态的参考焓背风面模型

**思路**: 将背风面从"正激波后平均状态"改为"局部外缘状态 + 参考焓法"。这本质上是将迎风面的 `windward_ref_enthalpy_branches()` 重用于背风面，但使用不同的外缘条件。

外缘条件可以从以下来源获取：
- 从 outline 几何估计局部膨胀角 → Prandtl-Meyer 膨胀波关系 → 局部 p_e、T_e、ma_e
- 或从 windward 侧 cache 的外缘状态插值

**需要新增的输入**: 局部外缘状态 T_e、p_e、Ma_e（需要新增一个"背风面外缘预估器"）

**是否需要 Fluent 外缘场**: 否（可以用膨胀波关系自估计），但 Fluent 数据可以用于验证

**是否需要表面流线**: 否（但流线长度有助于 x 方向发展）

**实现难度**: 中-高（需要实现 Prandtl-Meyer 膨胀波计算 + 背风面外缘预估）

**收益**: 
- 背风面热流获得 x/c 方向的空间变化
- 背风面前缘热流自然升高（因外缘速度更高、密度更低）
- 物理基础更扎实

**风险**: 
- 膨胀波关系对三维前缘/翼尖区域可能不适用
- 背风面分离区（如果有）无法用无粘膨胀波描述
- 需要大量验证

**推荐指数**: ⭐⭐⭐（中长期升级路线，需要 Fluent 数据验证后实施）

### 路线 D: 三维表面流线 + 参考焓法

**思路**: 实现表面流线追踪（Hamilton/Dec 方法），沿流线使用轴身类比（axisymmetric analog）将三维边界层映射到等效轴对称体，再用参考焓法沿流线求解。

**需要新增的输入**: 
- 表面网格（已有 STL）
- 无粘外缘速度场（从 Euler 或 Newtonian 近似）
- 流线追踪算法

**是否需要 Fluent 外缘场**: 是（需要 Euler 或 panel 法外缘解）

**是否需要表面流线**: 是（核心）

**实现难度**: 高（需要流线积分 + 轴身类比 + 参考焓 BL 求解器）

**收益**: 
- 全表面（迎风+背风）统一处理
- 物理一致性最高
- 可以捕捉翼尖/前缘的三维加热效应

**风险**: 
- 背风面分离区流线不可靠
- 开发周期长（数周至数月）
- 可能超出当前项目的工程范围

**推荐指数**: ⭐⭐（长期愿景，不适合当前阶段）

### 路线 E: Euler/无粘外缘场 + 边界层/参考焓法

**思路**: 使用外部 CFD（Euler 或 NS）提供外缘状态，用参考焓法沿表面网格点计算背风面热流。这是路线 D 的简化版——不追踪流线，只在每个网格点使用局部外缘状态。

**需要新增的输入**: 
- Fluent/Euler 导出的表面 p_e、T_e、Ma_e、rho_e、v_e
- 或一个快速 panel 法求解器

**是否需要 Fluent 外缘场**: 是

**是否需要表面流线**: 否（但需要 x 方向发展长度，可从 outline 或 STL 几何获得）

**实现难度**: 中（需要外部 CFD + 数据接口）

**收益**: 
- 背风面热流获得全表面空间变化
- 外缘状态由 CFD 提供，物理准确性高
- 与当前参考焓法无缝衔接

**风险**: 
- 依赖外部 CFD 输出，降低自包含性
- Fluent 背风面本身就有热流结果——再用参考焓法算一遍的边际收益有限

**推荐指数**: ⭐⭐（与直接使用 Fluent 背风面热流有重叠）

---

## 4. 路线对比总结

| 路线 | 空间变化 | 开发成本 | 需外部 CFD? | 保真度提升 | 风险 | 推荐 |
|------|---------|---------|------------|-----------|------|------|
| **A. 残差学习** | 无（保持常值） | 零 | 否（仅需 Fluent 热流作为修正目标） | 中（通过 ML） | 低 | **⭐⭐⭐⭐⭐** |
| B. 经验 St 分布 | x/c 方向 | 低 | 否 | 低-中 | 低-中 | ⭐⭐⭐ |
| C. 外缘状态+参考焓 | 全表面 | 中-高 | 否（自估计） | 中-高 | 中-高 | ⭐⭐⭐ |
| D. 表面流线+轴身类比 | 全表面 3D | 高 | 是 | 高 | 高 | ⭐⭐ |
| E. Euler 外缘+参考焓 | 全表面 | 中 | 是 | 高 | 中 | ⭐⭐ |

---

## 5. 历史建议与当前裁决

以下路线排序是 2026-06-28 调研结论，保留为历史候选空间，不是当前执行顺序。当前正式阶段不进入 residual learning，也不修改 legacy 背风模型；先完成已裁决的 Fluent clean-leeward filtering / exact geometry mapping integration，并在 integration 完成前不计算温度误差。

### 历史路线 A

当时建议保持 legacy 背风模型不变，并把残差学习视为远期候选。该建议没有进入当前主线；是否需要任何 provider 或 residual 升级，必须由 clean-leeward mapping 后的误差证据裁决。

### 映射证据形成后

如果正式映射显示背风区域存在稳定、可重复的空间结构，可再评估经验 Stanton 分布或 local-expansion provider。不得在 mapping integration 前拟合修正函数。

### 中长期候选

如项目确需更高保真度，可重新评估基于局部外缘状态的参考焓模型；表面流线/轴身类比和外部 Euler 外缘方案仍属于高成本候选，不是当前阶段入口。

### 绝对不做的事项（无论哪个路线）

- 不要修改迎风面参考焓公式
- 不要修改当前冻结的 `newtonian_like` pressure closure（`A=0.38`, `n=1.15`）
- 不要修改 Kemp-Riddell 驻点公式
- 不要删除或重写现有的 leeward.py（它提供了一个可接受的下界/均值）
- 不要将背风面升级与迎风面升级耦合（两者应可独立验证）

---

*报告编制: 2026-06-28*
*基于: AIAA-2006-3390 (Dec & Braun), NASA TP-2914 (Tauber), NASA TM-89156 (Delarnette et al.)*

---

## 6. 当前实现边界（2026-07-15 收口）

### 两条独立物理链

- legacy `Tw_l` / `q_l` / `St_l` / `Re_ns_l` 仍是 fixed-wall chain；`Tw_l` 是壁面边界条件，其他字段是 legacy mean-heating chain，不是绝热温度预测。
- 新增并冻结 sheet-specific freestream-recovery TPG Taw diagnostic。upper/lower 分别输出 mask、`T_e/p_e/rho_e/V_e/Ma_e/h_e/mu_e` 与 `Taw_tpg`，不存在 generic `Taw_tpg_l` 字段。
- 两条链物理定义、字段和数据流完全分离；新 diagnostic 不接管 legacy q-chain、pressure、windward edge-state 或 windward Taw。

### 新 diagnostic 合同

- raw mask 唯一定义：`mask_leeward_<sheet> = (surface_class_<sheet> == -1)`。
- 首轮 provider=freestream：`T_e/p_e/rho_e/V_e/Ma_e = T_inf/p_inf/rho_inf/V_inf/Ma_inf`，`h_e=h(T_inf)`，`mu_e=mu(T_inf)`。
- TPG recovery：`h_aw = h_e + Pr^(1/3)·V_e²/2`，`Taw = T_from_h(h_aw)`，`Pr=0.72`。
- mask 外所有连续字段为 NaN。由于 provider 是 freestream，mask 内 edge-state 与 Taw 空间常数是结构预期，不是异常，也不构成最终模型声明。
- 正式 alpha-sign routing 尚未切换；upper/lower geometric sheet 与 windward/near-tangent/leeward aerodynamic class 必须保持区分。

### 可比性与当前限制

- 新 `Taw_tpg_leeward_upper/lower` 在绝热恢复温度定义层面可以与 Fluent adiabatic Tw 对应。
- Fluent clean-leeward filtering / exact geometry mapping 合同已经裁决，但尚未完成 integration，也未进行 temperature-error calculation，因此仍不能报告 leeward error 或声明 leeward model validated。
- raw leeward mask 属于正式物理字段合同；clean leeward subset 只属于后续 mapping/filtering 合同，不得与 raw counts 混写。

### 后续裁决

下一阶段只集成已裁决的 Fluent clean-leeward filtering / exact geometry mapping 合同：Fluent face center 以 exact point-to-triangle 投影到当前 STL，projection distance hard gate 为 `0.005 m`；Fluent clean 独立构造；LF clean 到 clean Fluent 在 `(x, span)` 做最近邻并要求 `d_xy<=0.04 m`；duplicates 允许且记录，mutual NN 仅作 flag。integration 完成前不计算温度误差，也不升级 provider；后续是否采用 local-expansion provider，必须由映射后的误差分布裁决。

### Classification 相关性

normal-dot classification 审计中发现的鼻尖/圆弧前缘/near-tangent 上表面分类粗化问题属于未来 mapping/filtering contract 的裁决范围，不影响当前 windward baseline 主结果。
