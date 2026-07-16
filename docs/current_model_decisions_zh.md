# 当前 Faceted3D 冻结模型决策

> 更新：2026-07-17（Git/source identity 与 mapping 入口收口）

---

## 0. 仓库、字节身份与 artifact 语义（冻结）

- `https://github.com/KiRenk0/navi.git` 的 GitHub `main` 是 source of truth；正式本地活动工作区为 `E:\navi_clean`。恢复证据目录和历史目录不是活动开发入口。
- Git 当前 LF 字节身份是活动 Python、Markdown、YAML 等文本的正式源码合同；manifest source hash 绑定 Git 当前字节身份。
- `runs/**`、`fluent_export/**`、CSV、STL、NPZ 与其他 binary artifact 保持原始字节；不得无授权执行全仓库 renormalize。
- raw artifact hash、parsed semantic contract、数值与字段合同、provenance path 必须分别表述，不能相互替代。
- baseline `summary.json` 当前只作为 legacy provenance；其 raw SHA-256 不进入 current regression overall gate。未来 summary v5 promotion 应冻结 parsed semantic contract，而不是跨环境 candidate raw hash。
- 三项 source identity promotion 仅收口 CRLF/LF：STL parsed geometry、CSV parsed numeric arrays、`local_incidence.py` AST/executable semantics 均保持一致；没有物理模型或数值 baseline 漂移，manifest 仍为 49 项 source hash。

## 1. 压力 baseline（冻结）

- cp_model = `newtonian_like`
- cp_newtonian_A = 0.38
- cp_newtonian_n = 1.15
- 已在 `specs/vehicles/htv2_faceted3d_0629.yaml` 显式写入

## 2. Transition（冻结）

- 默认 weighting = `step`
- logistic / smoothstep 为 opt-in
- Dhawan-Narasimha 为 experimental opt-in，默认不启用，未写入正式 case YAML

## 3. 热流计算链（冻结）

- reference enthalpy core 冻结
- Kemp-Riddell 驻点热流冻结
- chord_min_m = 0.02 冻结
- windward / leeward / leading_edge 热流公式冻结

## 4. 禁止事项

- q_scale / multiplier 禁止
- `ma8_a10_h50km` 为 formal 域外 reserved legacy stress/reference case
- 不进入 residual learning / GPR / MoE
## 5. Taw Recovery Factor（冻结）

- Route A-TPG Taw 固定使用 fully turbulent recovery：`r_aw = Pr^(1/3)`，`Pr = 0.72`
- Taw 与 q-chain transition weighting 彻底解耦；Taw 不使用 `w_tr`
- q-chain 仍保留自己的 transition 逻辑（`w_tr`），不受 Taw 影响
- 不再使用层流/湍流混合恢复因子 `(1-w_tr)·sqrt(Pr) + w_tr·Pr^(1/3)`（历史实现，已被覆盖）
- Taw 为 adiabatic wall / recovery temperature candidate，不是 TPS material temperature
- Taw 是 prototype comparison，不是 validated temperature model
- validation complete 未声明
- Fluent heat-flux 在 adiabatic wall 中只作为 zero-heat-flux sanity，不是主误差量

## 6. 背风面

- legacy `Tw_l` / `q_l` / `St_l` / `Re_ns_l` 保持 fixed-wall chain；其常值结构是工程模型限制，不是 bug
- sheet-specific leeward freestream-recovery TPG Taw diagnostic 为独立链，不修改或接管 legacy fixed-wall q-chain
- 首轮唯一 edge-state provider 为 freestream；这是零阶 diagnostic baseline，不是最终背风模型
- recovery 与 windward Taw 使用同一 TPG enthalpy form：`h_aw = h_e + Pr^(1/3)·V_e²/2`，`Taw = T_from_h(h_aw)`，`Pr=0.72`
- 新 diagnostic 不接管 pressure、windward edge-state、windward Taw 或 q-chain
- 后续是否升级 local-expansion provider，只能由完成正式 mapping 后的误差证据裁决

## 7. Fluent 对比

- Corrected mapping: LF `(x_w_m, span_w_m)` → Fluent `(x-coordinate, y-coordinate)`
- Fluent y 是 spanwise 轴（范围 [0, 1.030] = b_half），z 是厚度方向
- Fluent adiabatic wall CSV：用户确认为 **density=ideal gas, Cp(T)=piecewise-polynomial, k(T)=piecewise-polynomial, μ=Sutherland, species/chemistry/dissociation=off, energy=on**
- heat-flux 仅用于 adiabatic sanity check
- 当前 comparison 基准为 corrected Fluent CSV
- pressure/Cp audit 与 recovery/thermo audit 分支处理，不混调

## 8. 默认 thermodynamic model: Route A-TPG（Phase 2E-P4 生效）

Route A-TPG 是唯一正式且唯一可运行的 thermodynamic baseline；CLI 无 thermodynamics 选择。历史 CPG→TPG 对比仅保留为 thermodynamic-architecture 改善证据。

- TPG 是唯一正式且唯一可运行模型；CLI 无 thermo 选择
- 历史 CPG→TPG 改善证据表明切换改变 Taw 与 enthalpy-based q-chain fields；这是物理一致性改变，不是 empirical tuning
- Reference-enthalpy core formulas（Eckert, Kemp-Riddell, r_eff, Pr, pressure closure, transition）全部冻结，未因切换而修改
- 不是 validation complete

## 9. Windward / Leeward Classification（2026-07-15 更新）

- 默认 `alpha-sign + upper/lower` classification 暂不修改，仍是正式 solver routing
- local-incidence normal-dot classification 已冻结为 additive diagnostic（`s = -dot(u_hat, n_out)`，geometric alpha，epsilon=0.05）
- upper/lower 是 geometric sheet identity；windward/leeward/near-tangent 是逐点 aerodynamic class；upper 不等于 leeward，lower 不等于 windward
- near-tangent（|s| <= 0.05）是模型有效性缓冲区；raw STL outward normal 优先，analytic fallback 仅无 STL 覆盖时使用
- `mask_leeward_<sheet>` 唯一由 raw `surface_class_<sheet> == -1` 产生；clean filtering 不进入物理字段合同
- 正式 alpha-sign routing 尚未切换；新 diagnostic 不改变正式 pressure、edge-state、windward Taw 或 q-chain routing

## 10. Leeward Temperature Error（2026-07-17）

- sheet-specific `Taw_tpg_leeward_upper/lower` 已存在，在物理定义层面可与 Fluent adiabatic wall temperature 对应；不存在 generic `Taw_tpg_l` 字段
- Fluent clean-leeward filtering / exact geometry mapping 合同已裁决，但尚未集成，尚未计算 temperature error
- 正式映射以 Fluent face center 到当前 STL 的 exact point-to-triangle 投影为真值；禁止固定有限 `k` centroid candidates 作为正式真值；projection distance hard gate=`0.005 m`
- LF clean 六条件冻结为：upper leeward、raw STL source 属于 accepted/rejected-but-used、`x/c>0.05`、`x/c<0.95`、`y/b<0.95`、`abs(n_z)>=0.8`；Fluent clean 独立构造
- 主映射冻结为 LF clean → nearest clean Fluent in `(x, span)`，`d_xy<=0.04 m`；duplicates allowed and recorded；mutual NN 只作 flag，不作为 gate
- mapping integration 完成前暂不计算温度误差；当前禁止报告 leeward temperature error，不能声明 leeward model validated
- freestream provider 是零阶 diagnostic baseline，不是最终背风模型

## 11. Windward Error Cloud Visualization（2026-07-10）

- `scripts/viz/plot_windward_error_vs_fluent.py` 为只读 diagnostic visualization 工具
- 不替代 P2R2 corrected comparison canon
- 不代表 validation complete
- 不涉及 leeward temperature error

## 12. 45 km（已退出 active 参数域）

- 45 km 使用的 241.65 K / 131 Pa 不是标准 ISA/USSA 1976 大气，而是 prescribed/off-standard freestream（+1 K/km simplified model）
- 原始 Fluent CSV、LF runs、PNG、JSON 等已从项目中彻底删除
- 45 km 不参与 residual learning、模型选择、标准高度趋势、holdout 或泛化评价
- 不再称为 `FREESTREAM QA FAIL`

## 13. 正式高度参数域（2026-07-12）

- 正式高度参数域：20–40 km
- 30、35、40 km 属于正式标准大气工况
- 45 km、50 km 不属于 active formal domain

## 14. 正式默认大气（2026-07-12）

- CLI 输入 `h_m` 为几何高度
- 内部换算为位势高度，按 1976 标准大气分层计算
- `isa1976.py` 是唯一正式计算实现
- `ussa1976.py` 仅为薄兼容 alias，不再维护独立简化公式
- explicit `T_inf / p_inf` override 保留（必须成对提供），可用于复现 Fluent 实际输入

## 15. 50 km（2026-07-12）

- `ma8_a10_h50km` 为 formal 20–40 km 域外的 reserved legacy stress/reference case
- 本轮未运行，不参与当前训练或模型选择，也不作为完全盲的端到端外推证据
- 不删除其文件，不运行，不重新分析

## 16. Endpoint 与 regression governance（2026-07-13）

- 81×41 sampling 维度冻结；row 40 动态移动到最外侧 `chord>=chord_min_m` 的有效站位
- 当前 `n_valid=3321`；`chord_min_m=0.02 m` 不变；约 3.50 mm 合法退化尖端 sliver 保持空白
- 唯一 current regression 命令：`python scripts/tools/current_baseline_regression_check.py`
- baseline 仅含 TPG 两 case：`ma6_a5_h30km`、`ma8_a5_h40km`
- CPG runtime、current compatibility baseline 与 phase4a0 replay 已删除；历史 CPG→TPG 改善仅作历史证据
- `src_snapshots` 已移出主工程；`ds_plan` 已删除

## 17. 当前状态（2026-07-17）

- residual learning 尚未启动，也不是当前下一阶段
- 当前下一阶段唯一入口是 Fluent clean-leeward exact geometry mapping integration；integration 完成前不计算温度误差
- 只有未来另行重启 residual learning 时，才需要单独冻结 residual-label mapping、dataset schema 和 case-level validation protocol
- windward TPG 基线、大气、pressure 和 edge-state 已冻结
- local-incidence classification 与 sheet-specific leeward freestream-recovery TPG Taw diagnostic 均已正式收口；baseline schema v5 / Groups 1–8

## 18. Local-Incidence Classification（2026-07-14 冻结）

- **分类公式：** `s = -dot(u_hat, n_out)`，`u_hat = (cos(alpha), 0, sin(alpha))`
- **alpha basis：** geometric alpha（不使用 `alpha_e`）
- **epsilon：** 0.05（0.03/0.08 仅 sensitivity）
- **法线优先级：** raw STL facet → analytic fallback；upper `n_z>0`，lower `n_z<0`
- **normal source 编码：** 0=INVALID, 1=STL_ACCEPTED, 2=STL_REJECTED_BUT_USED, 3=ANALYTIC_FALLBACK
- **不继承 q-chain 20° reference-cone rejection**
- **正式 routing：** 当前仍为 alpha-sign；local-incidence 与 sheet-specific leeward recovery 是 additive diagnostic，不切换正式 pressure/edge-state/windward Taw/q-chain 路由
- **Leeward recovery mask：** `mask_leeward_<sheet> = (surface_class_<sheet> == -1)`；clean filtering 不进入字段合同
- **Leeward recovery fields：** upper/lower 分开的 freestream edge-state 与 `Taw_tpg_leeward_upper/lower` 已冻结；不存在 generic `Taw_tpg_l` 字段
