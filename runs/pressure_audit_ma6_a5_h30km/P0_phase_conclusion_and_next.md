# P0 阶段总结：Faceted3D 误差溯源与阶段性判断

> 编制日期: 2026-06-29
> 分析工况: Ma=6, α=5°, h=30km, Tw=300K (isothermal)
> 对照基准: Fluent wall static pressure + total surface heat flux (单一工况)

---

## 一、P0.1 核心发现

### 误差链量化

| 环节 | 数值 | 与 Fluent 偏差 |
|------|------|---------------|
| phi (STL 法向入流角) | 均值 18.8°, 范围 14.6°–22.2° | — |
| Busemann Cp | 均值 0.448, 范围 [0.28, 0.62] | **Fluent Cp 均值 0.133 → 4.88× 高估** |
| p_e (外缘压力) | 均值 14,403 Pa | **Fluent 均值 5,097 Pa → 2.83× 高估** |
| q (参考焓热流) | 均值 312,429 W/m² | **Fluent 均值 138,823 W/m² → 2.25× 高估** |

### 关键判据

- **corr(p_ratio, q_ratio) = 0.088** → 压力误差不能单独解释热流误差
- **p_res 与 q_res 同号率 69.6%** → 压力是主要贡献者之一，但不是唯一
- **下游 p_ratio 从 3.5 升至 4.7** → 缺压力松弛，且随 x 恶化

---

## 二、P0.2 核心发现

### 区域化 Cp 误差（细化区域 V2）

| 区域 | 定义规则 | Count | Cp_fluent | Cp_f3 | Cp_ratio | p_ratio | phi_deg |
|------|---------|-------|-----------|-------|----------|---------|---------|
| true_nose_cap | x<0.15m, span<0.10m | 3,530 | **0.2045** | 0.4442 | **2.97×** | 2.46 | 18.7° |
| leading_edge_near | span > x/6 | 5,264 | 0.1082 | 0.4572 | **5.38×** | 3.79 | 19.0° |
| windward_body | 其他主体内点 | 969 | 0.0583 | 0.4350 | **7.46×** | 4.84 | 18.5° |
| aft_body | x>2.4m | 653 | 0.0566 | 0.4168 | **7.37×** | 4.74 | 18.1° |

**重要修正**：之前"nose 4.0x"主要来自旧区域定义 x<0.6m + span<0.15m（包含大量 leading_edge 点）。
真实 nose_cap 的 Cp 比率是 **2.97×**（仍偏高但明显改善）而不是 4.0×。

### 候选模型对比

| 模型 | Cp RMSE | Cp MAE | p_ratio | 说明 |
|------|---------|--------|---------|------|
| baseline_Busemann | 0.3381 | 0.3250 | 3.50 | 原始 |
| A_global_scale | 0.1090 | 0.0716 | 1.24 | 破坏 nose |
| **B_x_relaxation** | **0.0918** | **0.0608** | **1.21** | **Cp RMSE 最优** |
| C_region_relax | 0.1007 | 0.0550 | 0.96 | p_ratio 最优 |
| D_newtonian_fit | 0.1105 | 0.0682 | 1.06 | A=0.375, n=1.099 |
| E_linear_reg | 0.0923 | 0.0533 | 1.13 | — |

**结论**：
- **B_x_relaxation**（Cp RMSE 最优）和 **C_region_relax**（p_ratio 最优）均明显优于 baseline
- **全局缩放不可行**——Cp 区域跨度 3.0×–7.5×
- Model C 的 p_ratio=0.963 最接近 1:1，但 Cp RMSE 略高于 Model B

---

## 三、P0.3 核心发现

### Re_x / transition

| 指标 | 结果 |
|------|------|
| w_tr 分布 | 75.8% 层流 (w_tr=0), 24.2% 湍流 (w_tr=1), **0% 过渡区** |
| 前段 w_tr | 0.00–0.05 (几乎全层流) |
| 后段 w_tr | 0.58–0.66 (偏湍流) |
| corr(p_ratio, q_ratio) | **0.088** — 压力解释了极少的 q 方差 |
| q_lam vs q_turb vs Fluent | Fluent 低于 q_turb 但高于 q_lam — 介于之间 |
| 前段 Fluent q | ≈ 161,205 W/m² → q_lam=285,115 (过高) / q_turb=656,375 (过高) |
| **关键判断** | **Fluent 在这个工况下既不是层流也不是湍流，而是过渡态** |

### 跨工况验证

- **仅 1 个 Fluent 工况可用**（Ma=6, α=5°, h=30km），不足以做跨工况 Cp 模型标定
- Faceted3D 的 Busemann Cp 跨工况变化来源于 phi 分布的变化（大攻角→phi 增大→Cp 自然增大）
- Cp 修正系数是否有跨工况稳定性 → **需要至少 2–3 个额外 Fluent 工况验证**
- Cp_f3 在 Ma=8, α=20°, h=70km 时均值达 4.09，远超超声速有效范围

---

## 四、阶段性判断

### A. Faceted3D v2 第一优先级是 Cp / pressure relaxation？

**是**。但理由需要修正：
- Busemann Cp 高估是**全局系统性**的（各区域 3–7.5×），不是局部问题
- 真正的 Cp 模型问题，不是一个小修小补能解决的
- **B_x_relaxation**（x 依赖松弛）是 Cp RMSE 最优解，且不依赖 Fluent 先验

### B. 第二优先级是 Re_x / transition？

**否，但需要并行确认**。
- corr(p_ratio, q_ratio) = 0.088 表明热流误差主要不由压力控制
- 但这是因为 Cp 高估 → p_e 高估 → p_e → rho_e/T_e/v_e → q 的链条在 Faceted3D 的内部逻辑中是自洽的
- 压力的改变会通过 edge_conditions 链同时改变 rho_e、T_e、v_e、mu_e，从而影响 Re_x 和 h_star
- **在完成压力修正沙盒的完整 q 重算之前，不能断言 Re_x 是第二主因**
- w_tr 的二元分布（0 或 1，没有过渡区）是 transition 模型的结构性问题——step weighting 导致

### C. 是否需要完整三维表面流线追踪？

**不需要**。压力误差来自 Busemann Cp 模型本身不适用于大后掠钝头体 + 缺少几何膨胀效应。
这两个问题不是流线追踪能解决的。

### D. 是否暂缓 Fluent 残差学习？

**是，暂缓**。理由更新：
1. 当前只验证了 1 个 Fluent 工况
2. Cp 修正模型未跨工况验证
3. 压力修正后的完整 q 沙盒因 NaN 未能验证 q 改善
4. w_tr 的 step weighting 使 transition 无光滑过渡，可能引入非物理热流跳变
5. 残差学习的目标是 learnable residual，但当前残差中仍有系统性区域结构

### E. 什么时候可以进入真正的残差代理模型？

**至少满足以下条件之一**：

**条件 A（保守路线）**：
1. 至少完成 3 个不同 Ma/α/h 的 Fluent 工况对齐
2. Cp 修正模型在 3 个工况间一致
3. 压力修正后 q 砂盒验证通过

**条件 B（激进路线，当前建议）**：
1. 直接进入 Faceted3D v2 的 **Phase 1 物理升级**：替换 Busemann Cp 为 Newtonian-like Cp + x-dependent relaxation
2. 升级后的 Faceted3D v2 在 1 个工况上验证与 Fluent 对齐
3. 然后以此为基础开始残差代理模型设计

---

## 五、下一步建议

### 立即做（无风险）

1. **导出 2–3 个额外 Fluent 工况**：至少一个高马赫（Ma=8~12）+ 一个高攻角（α=10~20°）
2. **修复热流沙盒 NaN 问题**：`compute_edge_conditions` + `windward_ref_enthalpy_branches` 调用链的 NaN 排查

### 短中期（Faceted3D v2 物理升级）

3. **替换 Busemann Cp**（只替换 `busemann_cp` 函数中的公式，不修改 solver 架构）：
   - 实施 `Cp = A * sin(phi)^n`，A=0.375, n=1.099（从 Fluent 数据拟合）
   - 或用 `Cp = R(x) * Busemann(phi)`，R(x) 从 x 分段统计得到
4. **保留当前 solver 不动**，将 Cp 修正作为 edge_conditions 计算链的前处理层

### 长期（残差学习）

5. Phase 1 升级验证通过后，再启动 Fluent 残差学习

---

## 六、输出文件索引

| 阶段 | 输出目录 | 关键文件 |
|------|---------|---------|
| P0.1 (压力诊断) | `runs/pressure_audit_ma6_a5_h30km/` | `pressure_audit_diagnostics.md`, `aligned_pressure_points.csv` |
| P0.2 (Cp 修正沙盒) | `runs/pressure_audit_ma6_a5_h30km/cp_pressure_correction_sandbox/` | `cp_pressure_correction_sandbox.md`, `recommendation_for_faceted3d_v2.md` |
| P0.2 V2 (细化区域) | `runs/pressure_audit_ma6_a5_h30km/cp_pressure_correction_sandbox_v2_regions/` | `refined_region_cp_pressure_summary.md`, `refined_region_masks.png` |
| P0.3 (跨工况+Re_x) | `runs/cp_correction_cross_case_validation/` | `cross_case_validation_report.md` |
| P0.3 (Re_x/transition) | `runs/pressure_audit_ma6_a5_h30km/rex_transition_audit/` | `rex_transition_audit.md` |
| **本文档** | `runs/pressure_audit_ma6_a5_h30km/` | **`P0_phase_conclusion_and_next.md`** |

---

*本阶段结论基于单一 Fluent 工况 (Ma=6, α=5°, h=30km, Tw=300K)。跨工况推广需额外 Fluent 数据验证。*
