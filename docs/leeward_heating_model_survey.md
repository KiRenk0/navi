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

以下路线排序是 2026-06-28 调研结论，保留为历史候选空间，不是当前执行顺序。当前正式阶段不进入 residual learning，也不修改 legacy 背风模型；exact projection、projected semantics integration、Phase 5A Fluent clean、Phase 5B1 LF clean、Phase 5B2 mapping contract audit、Phase 5C pairing QA、Phase 5D wall-temperature ingestion QA 与 Phase 5E source-level comparison QA 均已完成。Phase 5E 只冻结 observation/prediction join、many-to-one 行保留、数组与误差公式合同，不输出第一轮正式性能误差结论。

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

## 6. 当前实现边界（2026-07-18 收口）

### 两条独立物理链

- Phase 5B1 implementation landing SHA=`3a7922518cb05533c779a11eb0eb3a4d3f653f32`；107 tests、87 subtests、58/58 source identities PASS；runtime `solver.last_fields` 为 74 项，正式 `fields.npz` 为 72 fields，schema=`current-tpg-baseline-regression/v5`，Groups 1–8 `max_abs_diff=0`，`CURRENT REGRESSION OVERALL: PASS`。
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
- clean-leeward temperature comparison 的 raw 几何前置层已完成：Fluent geometry input、显式 `+0.030 m` 坐标合同、canonical identity、exact STL projection、projected semantics integration 与全量 21,250 点 geometry-only QA 均已通过；6,341 个 STL triangles 的 5 mm gate 为 21,250/21,250 PASS。
- Fluent clean 已完成；它是 Fluent canonical points 上 raw projected semantics 的 geometry-only 派生 mapping subset，不回写 raw semantics。
- LF clean 已完成；它是 canonical LF 点上的 geometry/semantics-only 只读派生 subset：source 1/2 eligible，source 0/3 excluded，不进入 legacy fixed-wall chain，也不读取温度。
- LF clean 正式 `alpha=+5°` QA 为 upper/lower/any=`256/0/256`；非 baseline `alpha=-5°` lower-sheet integration shakeout 为 `1/1443/1444`，仅覆盖分支集成，不构成新的正式物理 validation case。
- Phase 5C Fluent clean → LF clean geometry pairing、Phase 5D wall-temperature ingestion 与 Phase 5E source-level comparison 均已完成并通过 formal QA。正式 comparison 以一个 Fluent clean-leeward source 为一行，upper 保留 `186` 行并直接索引 `80` 个 unique LF full-canonical targets；many-to-one 不去重、不聚合。Phase 5E 收口时点只证明合同与公式正确，尚未形成第一轮正式性能误差证据；该状态已由后续 Chapter 3.4/3.5 正式结果收口更新，但仍不能声明 leeward model validated。
- raw LF leeward mask 属于正式物理字段合同；LF clean 与 Fluent clean 属于后续 mapping 合同，三者不得与 raw counts 混写。
- Fluent clean 不读取温度；q-chain acceptance 不作为其 predicate，`normal_source` 1 与 2 均可进入。当前正式 Fluent clean upper/lower/any=`186/0/186`。

### 后续裁决

固定实现顺序 `Fluent clean → LF clean geometry pairing → mapping QA → wall-temperature ingestion → source-level comparison` 已执行完毕。Phase 5E prediction 唯一使用 Group 8 `Taw_tpg_leeward_<sheet>`；legacy `Tw_l=300 K` 仍是壁面边界条件，不是 adiabatic prediction。当前 freestream-recovery provider 仍是 diagnostic；Chapter 3.4/3.5 已形成描述性误差证据，但没有证明 provider 是否应升级。residual learning 不是当前阶段。

### Classification 相关性

normal-dot classification 审计中发现的鼻尖/圆弧前缘/near-tangent 上表面分类粗化问题属于未来 mapping/filtering contract 的裁决范围，不影响当前 windward baseline 主结果。

---

## 7. Chapter 3.1 Evidence 入口审计裁决（2026-07-20）

### 当前 comparison consumers

- 正式内存 API `src/ref_enthalpy_method/mapping/fluent_lf_taw_comparison.py` 提供 `FluentLfTawComparison` 与 `build_fluent_lf_taw_comparison`，负责构造保留 Fluent source-row identity 的正式 source-level comparison object；它不持久化 evidence，不生成 case-level summary 或 visualization。
- Phase 5E formal QA `scripts/tools/faceted3d_phase5e_fluent_lf_taw_comparison_qa.py` 验证 comparison 合同、source identity、many-to-one、typed-empty、误差公式与 metadata，并向 stdout 输出 PASS/FAIL；它不是正式 evidence exporter、case reporter、visualization pipeline 或模型性能判定入口。
- Unit test `tests/test_fluent_lf_taw_comparison.py` 验证 API 与 fail-closed 边界，不承担正式 evidence 输出。

正式裁决为结论 2：当前已有部分入口，但不完整，不能直接承担 Chapter 3 正式 evidence。已有正式 comparison API、unit tests、Phase 5E formal QA、内存 source identity 与基础 provenance metadata；仍缺正式 source-level raw evidence exporter、case-level descriptive summary、leeward spatial/statistical visualization、完整 evidence CLI/reporter、持久化 evidence manifest 与正式 evidence artifact-hash 登记。Phase 5E QA 不等价于正式 evidence pipeline。

### 正式 case 与 source-level 语义

当前仅 `ma6_a5_h30km` 与 `ma8_a5_h40km` 具备可信 Fluent wall-temperature CSV、正式 ingestion、Fluent→LF pairing、comparison、current baseline manifest、CSV SHA-256、provider/pairing metric 和 source/target identity provenance 的完整可构造链。两 case 均为 `alpha=+5°`，upper=`186` Fluent source rows、`80` unique LF targets，lower=typed-empty。

`186 → 80` 是这两个 case 的事实，不是未来 case 的永久计数合同。两者攻角相同，几何及 clean/pairing topology 相同，不能泛化到其他攻角、lower-sheet branch 或尚未进入 Phase 5C–5E 正式链的 Fluent cases。

source-level comparison 的冻结语义保持不变：一行对应一个 Fluent source row，全部 source rows 完整保留；多个 Fluent source rows 可以共享同一个 LF prediction，不按 unique LF target 去重。source-level statistics 按 Fluent source rows 计数，target multiplicity 只属于 diagnostic；不得引入 distance、mutual 或 multiplicity gate，不得引入 accepted mask、Hungarian/injective assignment，也不得以 target-level 去重结果冒充 source-level evidence。

### Windward 可比性、N3c 与性能判定

现有 windward diagnostic 与 leeward source-level comparison 在 row identity、mapping direction、统计母体、repeated-target weighting、relative-error representation 和 provenance 完整性方面不一致。因此，现有 windward summary 不能直接作为与 leeward source-level evidence 同口径的正式对照；这不等于宣布 windward evidence 无效。

当前已发现建议评估 N3c 的触发证据，但 Chapter 3.1 未进入 N3c，未建立 windward source-level comparison，未设计 windward 新合同，也未修改 leeward comparison 合同。

当前没有用户批准的统一性能阈值。缺少性能 PASS/FAIL 不是 evidence consumer 的实现缺口，不得新增 performance threshold、accepted 或 gate；任何 PASS 仅表示程序、合同、QA 或资产生成成功，不表示模型性能合格。

### 阶段边界

Chapter 3.1 已完成；该审计时点 3.2 Evidence 合同与资产边界、3.3 Source-level evidence 实现与验证尚未开始。该状态已由后续 Chapter 3.2/3.3 正式 evidence consumer 收口更新；Chapter 3 仍尚未完成，GATE A 仍尚未进入。

---

## 8. Chapter 3.2/3.3 正式 Evidence Consumer 状态（2026-07-20）

### Consumer 职责与冻结数据流

- 现有 `FluentLfTawComparison` 合同保持不变。Chapter 3.3 consumer 只负责 evidence materialization，不重新执行 ingestion、pairing、nearest 或 error calculation，也不改变 provider、comparison、pairing、ingestion 或 baseline。
- 正式 population 为等权 Fluent source rows；many-to-one source rows 全部保留且不按 LF target 去重，target multiplicity 只作 diagnostic。空间表达使用 comparison 提供的 authoritative projected coordinates。
- 显式 two-case registry 仅包含 `ma6_a5_h30km` 与 `ma8_a5_h40km`。两个 case 当前均为 upper=`186` source rows、`80` unique LF targets，lower=typed-empty；这些计数是当前 case 事实，不扩张为未来 case 的永久合同。

### Evidence 资产边界

- raw evidence 为 deterministic NPZ，case summary 为 JSON，visualization 为 PNG；provenance、source hashes 与 artifact hashes 由 independent manifest 登记。
- 资产采用原子发布与防覆盖约束。当前 evidence 证明链已具备正式生成能力，但本阶段没有把正式长期 evidence run 写入项目 `runs/`，Chapter 3.4 也尚未开展 case-level descriptive summary 与图表结果分析。
- formal QA 的 PASS 只证明程序、合同、资产生成与完整性成功，不进行模型性能数值 gate，也不把 fixed plotting range 解释为性能阈值。

### N3c 触发证据与阶段边界

现有 windward diagnostic 与 leeward source-level evidence 在 row identity、mapping direction、统计母体、repeated-target weighting、relative-error representation 和 provenance 完整性方面不可直接比较。这是建议评估 N3c 的触发证据，不是 windward evidence 无效或 provider 路线裁决。

该阶段没有建立 windward 新合同，没有正式启动 N3c，没有进行 GATE A provider 路线裁决，也没有模型性能数值 gate。Chapter 3.1、3.2 已完成，Chapter 3.3 技术实现与验证已完成；该时点 Chapter 3.4 尚未开始。该状态已由后续 Chapter 3.4/3.5 正式结果收口更新；strategy v1.0 保持冻结。

---

## 9. Chapter 3.4/3.5 背风 Evidence 解释（2026-07-20）

### 正式数据流与 case 内误差结构

正式 run=`20260720T055647Z_af1f1f5395a9`，对应 `main@af1f1f5395a992bf8b9f439cf824376c209ab19b`，manifest SHA-256=`4db8b71bf79602ffdae12a71a345c251711b0b791ae7405b97105cffef4f0b90`。registry 仅含 `ma6_a5_h30km` 与 `ma8_a5_h40km`；每个 case 的 upper 为 `186` 个等权 Fluent source rows、`80` 个 unique LF targets，lower 为 typed-empty。many-to-one source rows 不按 target 去重，也不使用 inverse-multiplicity weighting。

freestream-recovery provider 使每个 case 内 source-row prediction 为常数。对任一行：

`signed_error_i = constant_prediction - observation_i`

因此精确代数上：

`centered_signed_error = -centered_observation`

在两个 case 的严格 row alignment 下：

`Δsigned_error = Δprediction - Δobservation`

Case A 的 prediction=`1550.4342365955222 K`，位于 observation range 内，因此正式资产同时包含 `136` 个正误差行与 `50` 个负误差行；Case B 的 prediction=`2699.7814815610645 K`，高于全部 observation rows，因此 `186` 行 signed error 均为正。这些是 source-row population 的描述性事实，不是性能接受性结论。

### Cross-case 事实与有限排除

两个正式资产的 source canonical index、authoritative projected coordinates、target canonical index、pairing distance / dx / dspan 与 target multiplicity 逐元素相等。由此只能排除“这些 recorded structures 在 A、B 两资产之间发生变化”作为本次差异来源；不能据此证明 mapping、geometry 或 pairing 绝对正确，也不能排除共同 mapping/geometry bias。

B−A 的 mean signed error=`82.866029 K`、mean absolute error=`80.189112 K`、mean signed relative error=`2.770578 percentage points`、mean absolute relative error=`2.598714 percentage points`；positive rows 增加 `50` 行，即 `26.881720 percentage points`。这些 cross-case 变化由正式资产与独立重算支持，但 Case A 同时为 Mach 6 / 30 km，Case B 同时为 Mach 8 / 40 km，Mach 与高度混杂，不能把变化单独归因于任一因素。

### 仍未建立的物理结论

当前证据没有证明 provider 物理正确或应被修改，没有判定 Fluent observation 的质量或因果责任，没有证明 mapping/pairing 绝对正确，没有排除共同 mapping/geometry bias，也没有形成 windward/leeward 联合结论、模型性能接受性、物理因果或机制归因。未来若要区分 Mach、高度、provider 与 observation 影响，需要独立对照、新 case 或更严格的实验设计，而不是从当前两点混杂比较外推。

Chapter 3.4 与 Chapter 3.5 技术范围已完成。N3c 触发证据继续保留，但 N3c 未正式启动；GATE A 未进入；provider 未修改；display limits 不是 performance threshold，integrity PASS 也不是性能 PASS。

---

## 10. Chapter 3.6 GATE A 输入 Package 边界（2026-07-20）

### Package 状态与 evidence tier

Chapter 3.6A readiness audit 已完成，readiness=`READY_FOR_3_6B`；随后完成 Chapter 3.6B evidence package assembly 与 boundary QA，submission status=`PACKAGE_READY_FOR_GATE_A_REVIEW`。formal run、two-case source-row population、cross-case facts 与 limited attribution 已组装进 GATE A 输入 package；本节不重复 Chapter 3.4/3.5 已冻结数值。

formal leeward 属于正式 source-row evidence tier。windward 仅为 `DIAGNOSTIC CONTEXT ONLY`、`NOT FORMAL SOURCE-LEVEL EVIDENCE`，不构成与 formal leeward 同层级的 source-level evidence，也不能与 leeward 形成联合 population 或联合性能统计。两侧 signed relative error 的代数方向和 percent 单位可以对应，但 row identity、mapping direction、population、repeated-target weighting、provenance/integrity、registry/alignment 与 figure/display contract 不同；只能分层并列，不得直接数值排名或借助颜色、面积、fixed scale 作跨表面性能比较。

### 允许与禁止的归因

当前允许使用 formal asset facts、independent recomputation、exact algebraic implications、有限 exclusion statements，以及明确标记的 unresolved/confounded issues。当前证据禁止推出 Mach 或高度的独立因果、provider 责任、Fluent observation 责任、mapping/geometry/pairing 绝对正确、provider 必须升级或模型性能接受性。

`PACKAGE_READY_FOR_GATE_A_REVIEW` 仅表示 package 完整、可追溯且边界明确，不表示 GATE A 已开始或已作路线裁决。当前 package 路径不要求启动 N3c；N3c 未启动，也未被永久取消。若未来要求同 identity、同 population、同 weighting、同 provenance 的跨表面联合数值比较，必须重新裁决是否正式启动 N3c。

### 未决问题与后续证据分支

- 正式 leeward evidence 仅覆盖两个 case，Mach 与高度混杂；lower 仍为 typed-empty。
- windward 尚无同层级 formal source-level contract；共同 geometry/mapping bias 不能排除。
- 当前没有用户批准的性能 threshold，integrity PASS 不等于 performance PASS。
- 证据数量不足、case 覆盖不足、变量混杂、需要新增可信 case 或补充正式诊断时，可能进入 N3a；只有发现 identity、data、geometry、mapping 或 evidence-chain 的具体错误时，才可能进入 N3b。当前不决定进入 N3a 或 N3b，也不裁决 provider 路线。

---

## 11. Chapter 3.7A Provider 路线审查入口边界（2026-07-20）

Chapter 3.7A 只读审计已完成，N3 formal evidence package 的 technical exit conditions 已认证满足，entry eligibility=`READY_TO_REQUEST_GATE_A_ENTRY`。该状态足以请求用户批准进入 GATE A，但不是 GATE A 路线裁决；用户尚未批准，GATE A 尚未开始。

### 当前证据适用范围

- formal leeward 仍只覆盖 `ma6_a5_h30km` 与 `ma8_a5_h40km` 两个 source-level cases；两者 lower 均为 typed-empty，Mach 与高度混杂，共同 geometry/mapping bias 未被绝对排除。
- 上述事项已作为明确适用范围或非阻塞局限记录，足以支持 GATE A entry request，但不足以选择任何 provider 路线分支。
- windward 继续仅作为 `DIAGNOSTIC CONTEXT ONLY`，不得与 formal leeward 形成联合 population、联合统计或直接排名。

### GATE A 必须回答的问题

- 当前 evidence 数量是否足够，two-case 覆盖与变量混杂是否要求补充证据；
- 是否存在具体 identity、data、geometry 或 mapping 问题；
- 是否存在稳定、可解释且跨 case 的 provider 系统偏差；
- 用户认可的工程目标与模型性能口径是什么。

当前不得由误差大小直接推导 provider 足够、provider 失败、provider 必须升级，也不得推导 Fluent observation 或 provider 的因果责任。A0/A1/A2/A3 尚未选择，provider 未修改，模型性能没有 PASS/FAIL 结论。
