# 功能基准线（Functional Baseline Contract）

本文件定义 `src/ref_enthalpy_method/` 的 **功能基准线**：与旧实现 `ref_enthalpy/` **行为等价**的输入/输出契约。

目标：后续重写（更清晰的模块化 + 更强的可测试性）时，**不丢功能、不改用户工作流**。

## 0. 正式参数域与默认口径（2026-07-12 冻结）

- **正式高度参数域：20–40 km。** 30/35/40 km 采用标准 USSA 1976 大气口径。
- **大气模型：** CLI 输入 `h_m` 为几何高度，内部自动换算为位势高度后按 1976 标准大气分层计算。`isa1976.py` 是唯一正式实现，`ussa1976.py` 为薄兼容 alias。
- **explicit override：** 支持 `--T_inf_K` / `--p_inf_Pa` 成对显式覆盖（必须同时提供），覆盖后跳过大气模型。
- **thermodynamics：** Route A-TPG 是唯一正式且唯一可运行模型；CLI 不提供 thermodynamics 选择。
- **Taw recovery：** Route A-TPG Taw 固定使用 fully turbulent `r_aw = Pr^(1/3)`（`Pr=0.72`），与 q-chain transition weighting 解耦。
- **pressure closure：** `newtonian_like`，`A=0.38`，`n=1.15`（已冻结）。
- **edge-state：** 工程降阶链冻结，不升级。
- **residual learning：** 尚未启动。45 km 不参与训练。

## 1. 输入契约：三类 spec 文件 + 翼型 .dat

我们沿用旧实现的组织方式与 schema（保持兼容），但现在以本项目根目录的 `specs/` 作为默认位置：

### 1.1 `specs/vehicles/*.yaml`（几何）

顶层键：`vehicle_spec`

关键字段（最小集）：

- `vehicle_spec.vehicle_id`: string
- `vehicle_spec.planform.b_half_m`: 半展长
- `vehicle_spec.planform.c_root_m`: 根弦
- `vehicle_spec.planform.c_tip_m`: 梢弦
- `vehicle_spec.planform.sweep_le_deg`: 前缘后掠角（deg）
- `vehicle_spec.leading_edge.rn_m`: 前缘钝头半径（m）
- `vehicle_spec.airfoil.type`: 目前支持 `dat_file`
- `vehicle_spec.airfoil.path`: 指向翼型 `.dat` 文件的相对路径（相对 vehicle spec 文件）
- `vehicle_spec.surface.emissivity`: 表面辐射率（用于壁温辐射平衡）

### 1.2 `specs/cases/*.yaml`（工况/物性/模型开关）

顶层键：`case_spec`

关键字段（最小集）：

- `case_spec.fixed.h_m`: 高度（m）
- `case_spec.gas.gamma`, `case_spec.gas.R_J_per_kgK`
- `case_spec.viscosity.*`: Sutherland 参数（mu_ref, T_ref, S）
- `case_spec.lf_qw_model.pr`
- `case_spec.wall.temperature_K`: 若 wall model 为固定壁温（仅算热流时可用）
- `case_spec.tw_model.type`:
  - `radiative_equilibrium`：稳态辐射平衡（Doc Eq 2.58）
  - `transient_balance`：瞬态显式推进（Doc Eq 2.57）
- `case_spec.tw_model.sigma`: \(\\sigma\\)（文档取值 5.76e-8）
- `case_spec.tw_model.transient.*`: 瞬态材料参数与时间步
- `case_spec.transition_x_over_c`: 可选，禁止该位置之前发生转捩（工程约束）

### 1.3 `specs/sampling/*.yaml`（采样网格）

顶层键：`canonical_sampling_spec`

支持两种模式：

- `mode: root_windward_chord_line`：1D 沿根弦线
  - `x_over_c.{start,end,n}`
  - `y_over_b`: 单一值（通常 0）
  - `output_fields/concat_order`: 常见为 `[q_w]` 或扩展加入 `Tw_w` 等
- `mode: full_wing_surface_grid`：2D 半翼面
  - `x_over_c.{start,end,n}`
  - `y_over_b.{start,end,n}`
  - `output_fields/concat_order`: 常见为 `[q_w, q_l]`，也可扩展

### 1.4 翼型 `.dat` 格式（你后续加翼型就按这个）

示例：`ref_enthalpy/specs/airfoils/doubleconvex_t0p03.dat`

- **第 1 行**：翼型名字/注释（任意字符串，读取时会跳过）
- **后续每行**：两个浮点数 `x y`
- 推荐约定（与当前实现兼容）：
  - `x` 为弦向坐标，归一化到 \([0,1]\)
  - 数据顺序通常为：**上表面**从 `x=1 → 0`，然后**下表面**从 `x=0 → 1`
  - 上下表面通过 `y>=0` 与 `y<0` 分开（对称翼型也 OK）

几何处理（基准行为）：

- 优先使用 `scipy.interpolate.CubicSpline` 拟合上下表面
- 若无 SciPy，则降级为线性插值
- 在采样 `x_over_c` 网格上计算 `dy/dx`，并对坡度做截断（防止前缘数值奇异）

## 2. 输出契约：字段命名与落盘格式

### 2.1 核心字段（与 ref_enthalpy 对齐）

常见输出数组（1D 时长度 `nx`；2D 时长度 `nx*ny` 扁平化）：

- `q_w`：迎风面热流密度（W/m^2）
- `q_l`：背风面热流密度（W/m^2）
- `Tw_w`：迎风面壁温（K）
- `Tw_l`：背风面壁温（K）

瞬态输出（当 `tw_model.type=transient_balance`）：

- `t_s`：时间序列（s）
- `Tw_w_time`：壁温时间历程
- `q_w_time`：热流时间历程

#### 2.1.1 瞬态在 2D 网格（ny>1）时的策略（为避免爆内存）

默认行为（推荐）：

- **ny==1**：
  - 若 `tw_model.transient.save_time_history=true`：保存 `t_s/Tw_w_time/q_w_time`
  - 否则只保存最终态 `Tw_w/q_w`
- **ny>1**：
  - 默认 **只保存最终态** `Tw_w/q_w`（每条 strip 都会给最终态）
  - 若用户强制开启 `save_time_history`，实现会记录 warning，并仍只对根部 strip 保存时序（其余 strip 只保最终态）

### 2.2 Run artifacts（runs 目录）

跑单工况会输出到：`runs/<run_dir>/`

- `summary.json`：人读的参数与统计摘要
- `fields.npz`：机读数组（供画图/二次处理）
- current regression snapshot：`runs/current_baseline_snapshot/tpg/<case_id>/`，每个 case 保存正式三件套引用副本、`fields.npz`、`summary.json` 与机器可读 `manifest.json`
- `lf_warnings.log`：运行过程的数值/物理异常提示（NaN/Inf、phi clamp、过大热流等）

### 2.3 Current regression contract（2026-07-18）

- 唯一 current regression 命令：`python scripts/tools/current_baseline_regression_check.py`
- baseline 仅含 TPG official cases：`ma6_a5_h30km`、`ma8_a5_h40km`；三工况 shakeout 不属于 current baseline case
- baseline schema：`current-tpg-baseline-regression/v5`
- `fields.npz` 共 72 个字段：Groups 1–8 的 71 个合同字段，加既有 additional field `Tw_w`
- Groups 1–8：Geometry/sampling、Pressure/incidence、Edge-state/transport、TPG/Taw、q-chain、Leeward legacy fields、Local-incidence diagnostic、**Sheet-specific leeward freestream-recovery TPG Taw diagnostic**
- **Group 8（18 字段）：**
  - masks：`mask_leeward_upper`、`mask_leeward_lower`
  - edge temperature：`T_e_leeward_upper`、`T_e_leeward_lower`
  - edge pressure：`p_e_leeward_upper`、`p_e_leeward_lower`
  - edge density：`rho_e_leeward_upper`、`rho_e_leeward_lower`
  - edge velocity：`V_e_leeward_upper`、`V_e_leeward_lower`
  - edge Mach：`Ma_e_leeward_upper`、`Ma_e_leeward_lower`
  - edge enthalpy：`h_e_leeward_upper`、`h_e_leeward_lower`
  - edge viscosity：`mu_e_leeward_upper`、`mu_e_leeward_lower`
  - TPG recovery temperature：`Taw_tpg_leeward_upper`、`Taw_tpg_leeward_lower`
- Group 8 mask 字段为 bool；其余 16 个连续字段为 float64。mask 唯一定义为 `surface_class_<sheet> == -1`，mask 外连续字段必须为 NaN
- 两个 current baseline 均为 raw upper leeward count=256、raw lower leeward count=0；这是逐 sheet aerodynamic classification 结果，不表示 upper 等同 leeward，也不表示 lower 永远没有 leeward
- Groups 1–7 所有既有字段 exact unchanged，`max_abs_diff=0`
- shape 必须一致；bool/int exact；NaN mask exact；浮点字段 byte-exact 且 `max_abs_diff=0`；row 40 不得跳过；mandatory field 任一侧缺失即 group FAIL
- endpoint metadata 必须确认 81×41、`n_valid=3321`、row 40 全 81 点有效，并与 snapshot 精确一致
- **Local-incidence group（12 字段）：** `normal_x/y/z_upper/lower`、`incidence_s_upper/lower`、`surface_class_upper/lower`（int8, -2/-1/0/1）、`normal_source_upper/lower`（int8, 0/1/2/3）
- **Semantic QA：** normal unit length <= 1e-12 error、upper `n_z>0` / lower `n_z<0`、surface class 与 `s/epsilon` 一致、source 编码合法；Group 8 验证 mask/class exact equal、dtype/shape、NaN domain、freestream state、TPG recovery 与 sheet isolation
- source inventory 共 57 项并全部 PASS；source hash promotion 只管理源码身份，不等于数值 baseline freeze
- tests：97/97 PASS（另有 77 subtests PASS）；current regression overall：PASS
- Phase 5A Fluent clean 属于 additive geometry/mapping infrastructure，不进入现有 `fields.npz`、72-field schema 或 Groups 1–8；新增 `fluent_clean.py` 与公开 `semantic_valid_mask()` 不改变现有数值组
- `semantic_valid_mask()` 是 semantic-valid 公共单源：`normal_source in {1,2}`、geometric sheet 为 UPPER/LOWER、outward normal 与 incidence finite、surface class 非 INVALID；projection gate 与 planform validity 不属于 semantic-valid
- Fluent clean eligibility 允许 `normal_source` 1 与 2，0 与 3 由 semantic-valid 排除；`qchain_stl_accepted` 不属于 Fluent clean predicate
- Phase 5A formal QA 是独立 geometry-only gate；正式 Fluent clean upper/lower/any=`186/0/186`。它与 Group 8 的 LF solver raw upper/lower mask count=`256/0` 分属不同点集、不同 ordering 与不同阶段，不得互换
- 两份 manifest 在上一代码阶段仅新增 `fluent_clean.py` source hash、更新 `fluent_semantics.py` source hash；本阶段不修改 manifest。schema 仍为 v5，fields 仍为 72，Groups 1–8 数值仍全部 `max_abs_diff=0`
- `fields.npz`、summary、schema、artifact hashes 与 Groups 1–8 数值均未改变
- **正式 routing：** alpha-sign 未切换；local-incidence 与 sheet-specific leeward recovery 均为 additive diagnostic；不存在 generic `Taw_tpg_l` 字段

### 2.4 未注册 TPG candidate manifest 合同（2026-07-21）

`current-tpg-baseline-regression/v5` 与 `tpg-candidate-manifest/v1` 是严格隔离的两类身份：

- `current-tpg-baseline-regression/v5` 只用于正式 current TPG baseline regression，保持冻结，正式 case 仍仅为 `ma6_a5_h30km` 与 `ma8_a5_h40km`；不得用于未注册 candidate。
- `tpg-candidate-manifest/v1` 只为未注册 TPG candidate run 记录 source/artifact identity；它不是 baseline，不是 formal evidence，不构成 registry admission 或 promotion。

candidate manifest 顶层字段按顺序固定为：

- `manifest_schema`
- `provenance`
- `suite_type`
- `admission_status`
- `case_id`
- `case`
- `freestream`
- `atmosphere`
- `thermo`
- `pressure`
- `grid`
- `endpoint_metadata`
- `local_incidence`
- `fields_schema`
- `source_hashes_sha256`
- `artifact_hashes_sha256`
- `manifest_generator`
- `generator_cli_template`

固定身份为 `manifest_schema=tpg-candidate-manifest/v1`、`suite_type=TPG candidate`、`admission_status=unregistered_candidate`。该 schema 不含 `baseline_date`、`baseline_generator`、Git SHA、branch、commit SHA、performance PASS/FAIL 或 formal evidence admission。

- candidate builder 不依赖 `CASES`，并复用既有 `source_files()` / `sha256()`；不得建立平行 hash 链。
- candidate manifest 不能通过编辑、重命名或改字段成为 v5 baseline manifest。未来若 candidate 获准进入正式 baseline，必须先有独立 admission 决策，再由既有正式 freeze 机制重新生成真正的 v5 manifest。
- candidate CLI 只读取既有 `fields.npz` 与 `summary.json`，不运行 solver；`run_dir` 必须位于 `ROOT/runs`，且目录名必须包含 `candidate`。
- candidate CLI 拒绝 `current_baseline_snapshot` 与 `leeward_source_evidence`，拒绝覆盖既有 `manifest.json`，不提供 `--overwrite`，并以原子方式发布新 manifest。
- candidate-only 显式 freestream provenance 通过成对可选参数 `--t-inf-k` / `--p-inf-pa` 提供；两项必须同时提供或同时省略，非有限、零值或负值一律拒绝。它们只补充 candidate manifest provenance，不是 solver 新能力。
- 显式路径生成的 runner 复现命令使用正式 runner 参数名 `--T_inf_K` / `--p_inf_Pa`，并必须完整记录真实显式温压参数和值。
- 显式路径交叉校验 `inputs.T_inf_K_override`、`inputs.p_inf_Pa_override`、`freestream.freestream_source`、`freestream.T_inf_K` 与 `freestream.p_inf_Pa`；source 必须为 `explicit_override`，校验通过后记录 `atmosphere.explicit_freestream_override=true`。显式 summary 未同时提供对应 provenance pair 时拒绝生成 manifest。
- 非显式 candidate 路径保持向后兼容并记录 `atmosphere.explicit_freestream_override=false`。本修复未改变 candidate manifest 顶层字段集合，也未改变正式 v5 baseline、`CASES`、registry、freeze/check、source inventory、Groups 1–8 或 72-field serialization contract。


当你确认 `specs/` 内容齐全后（本项目默认即为 `specs/`）：

- 新项目运行不再依赖 `ref_enthalpy/`
- 你可以安全删除 `ref_enthalpy/`（如需保留历史文档/截图，可自行备份）

## 3. 文档来源

- `ref_enthalpy/具体方法/Reference_Enthalpy_Method_Technical_Doc.md`
- `ref_enthalpy/使用教程.md`

