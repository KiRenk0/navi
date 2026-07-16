# Faceted3D 当前工程状态

> 更新：2026-07-17（canonical documentation closeout）

---

## 1. 正式工作区与源码身份

- 正式远端：`https://github.com/KiRenk0/navi.git`。
- 当前正式本地活动工作区：`E:\navi_clean`。
- GitHub `main` 是当前 source of truth；开发、验证和正式产物必须从该仓库身份出发。
- `E:\Faceted3D_recovery_hold_20260715`、`E:\Faceted3D_recovery_work_20260715` 仅为只读恢复证据，`D:\ref\reference-enthalpy_03_12_26-main` 仅为历史资料；三者都不是活动工作区或正式来源。

活动 Python、Markdown、YAML 等文本按 `.gitattributes` 使用 LF。`runs/**`、`fluent_export/**`、CSV、STL、NPZ 与其他 binary artifact 保持原始字节，不执行无差别 normalization；未经单独授权不得执行全仓库 renormalize。

## 2. 当前正式模型

- 正式高度参数域：20–40 km；30、35、40 km 使用 1976 标准大气口径，CLI 输入几何高度并在内部换算位势高度。
- Route A-TPG 是唯一正式且唯一可运行的 thermodynamic baseline；CLI 不提供 thermodynamics 选择。
- TPG Taw 固定使用 fully turbulent `Pr^(1/3)` recovery，与 q-chain transition weighting 解耦。
- pressure closure 冻结为 `newtonian_like`，`A=0.38`、`n=1.15`；transition 默认 `step`；`chord_min_m=0.02 m`。
- 正式 alpha-sign windward/leeward routing 未改变；local-incidence 是 frozen additive diagnostic，不接管正式 routing。

## 3. Current baseline 与 regression

正式 baseline 位于 `runs/current_baseline_snapshot/tpg/`：

- schema：`current-tpg-baseline-regression/v5`；
- cases：`ma6_a5_h30km`、`ma8_a5_h40km`；
- `fields.npz`：72 fields；
- Groups 1–8：全部 PASS，全部 `max_abs_diff=0`；
- Group 8 semantic QA：PASS；
- endpoint/metadata：PASS；
- source hashes：49/49 PASS；
- tests：30/30 PASS；
- overall：`CURRENT REGRESSION OVERALL: PASS`。

唯一 current regression 命令为 `python scripts/tools/current_baseline_regression_check.py`。该 PASS 只证明 harness 实际执行的数值、字段、semantic QA、endpoint/metadata 与 49 项 source hash gate，不得扩大解释为未执行的 validation 或 artifact gate。

### 3.1 Source identity promotion

两个 baseline manifest 中以下三项 source hash 已绑定 Git 仓库当前 LF 字节身份：

- `new_spec/htv2_0628.stl`；
- `new_spec/outline_xz_right_0629.csv`；
- `src/ref_enthalpy_method/geometry/local_incidence.py`。

该变化仅收口 CRLF/LF source identity：STL parsed geometry 完全一致，CSV parsed numeric arrays 完全一致，`local_incidence.py` AST/executable semantics 完全一致。没有物理模型或数值 baseline 漂移，manifest 仍为 49 项 source hash。

## 4. Group 8 能力与边界

Group 8 冻结了 18 个 sheet-specific leeward freestream-recovery 字段，upper/lower 分开输出 mask、freestream edge-state 与 TPG recovery temperature。provider 使用 freestream edge-state + TPG recovery；这是 zero-order diagnostic，而不是最终背风温度模型。

- raw mask 唯一定义为 `surface_class_<sheet> == -1`；local-incidence diagnostic 与正式 alpha-sign routing 相互独立。
- 当前正攻角 baseline/shakeout cases 的 formal lower mask 为 0；这是这些工况的分类结果，不表示 lower sheet 永远没有 leeward 区域。
- legacy `Tw_l`、`q_l`、`St_l`、`Re_ns_l` 仍是 fixed-wall legacy chain，与 Group 8 完全解耦。
- legacy `Tw_l` 不能用于对比 Fluent adiabatic `Tw`；不存在通用 `Taw_tpg_l`，只有 `Taw_tpg_leeward_upper/lower`。
- 尚未完成与 Fluent clean-leeward 的正式映射和误差验证；不得声称背风温度模型已经 CFD validated，不得报告 leeward temperature error。

## 5. `summary.json` 当前限制

当前 baseline `summary.json` 仍是 legacy provenance artifact：

- baseline summary 的 `outputs_available` 为 56 项；
- 当前 official CLI candidate summary 的 `outputs_available` 为 74 项；
- `fields.npz` 正式 schema 为 72 项；
- summary 仍可能保存旧绝对路径与旧 `run_dir` provenance；
- summary raw SHA-256 不进入当前 regression overall gate；
- endpoint/metadata PASS 不表示 baseline summary 与当前 candidate summary 在 raw 或 parsed 层面完全一致。

因此当前 summary 只用于 legacy provenance。summary v5 parsed-semantic promotion 尚未执行；后续应冻结 parsed semantic contract，而不是跨环境 candidate raw hash。本轮未修改 summary、manifest 或 regression harness。

## 6. 下一正式入口：Fluent clean-leeward mapping integration

下一阶段是 **Fluent clean-leeward filtering / exact geometry mapping contract integration**。已裁决合同如下：

1. Fluent face center 精确投影到当前 STL，以 exact point-to-triangle 为真值；禁止固定有限 `k` centroid candidates 作为正式真值。
2. projection distance hard gate 为 `0.005 m`。
3. LF clean 使用六条件：upper leeward、raw STL source 属于 accepted/rejected-but-used、`x/c>0.05`、`x/c<0.95`、`y/b<0.95`、`abs(n_z)>=0.8`。
4. Fluent clean 独立构造，不从 LF clean 反推。
5. 主映射为 LF clean → nearest clean Fluent in `(x, span)`，`d_xy <= 0.04 m`。
6. duplicates allowed and recorded；mutual NN 只作 flag，不作为 gate。
7. mapping integration 完成前暂不计算温度误差。

该 mapping 合同已裁决但尚未集成；不得写成 mapping 或 CFD validation 已完成。

## 7. 当前禁止项

- 不进入 residual learning、GPR 或 MoE。
- 不扩展 45 km/50 km active domain；`ma8_a10_h50km` 仅为域外 reserved legacy stress/reference case。
- 不做大规模 pruning，不重构 Group 6，不修改 pressure、TPG 或正式 windward routing。
- 不调整冻结物理合同，不用 manifest 更新掩盖源码或数值漂移。
- 在 mapping integration 完成前不计算或发布背风温度误差。
