# Faceted3D v2 - 当前 GPT 交接：N8 Taw geometry-invalid 产品域闭包

> 日期：2026-07-27（Asia/Shanghai）  
> 当前任务：`N8_TAW_GEOMETRY_DOMAIN_CLOSURE`  
> 当前状态：原计划任务 3～6 已完成；phase9 通过 12/12 工况，但每工况仍有 333 个 geometry-invalid 点  
> 当前分类：`N8_TAW_SURFACE_V3_PROVIDER_AND_NORMAL_CHAIN_VALIDATED__GEOMETRY_DOMAIN_OPEN`  
> 当前入口：第 9 节；第 1～8 节保留为历史证据，不得据其旧“下一步”重开已完成任务  
> 工作区：`E:/navi_clean`  
> 分支：`feat/n8-taw-surface-pipeline`  
> HEAD：`b8f9878e2ec3dc617a88f27d34d23a8507147d6a`

---

## 1. 当前意图

当前项目链路已经具备可用的 Taw 双几何表面生成、序列化、比较和绘图能力。现在不再以“跑通整个项目、补齐全部数学链条”为目标。

当前唯一目标是：

```text
解释并解决用户在背风区域看到的 Taw 温度花纹和温度 NaN/空洞。
```

本轮已完成根因诊断和用户授权的 N8 全链路整改；未重开早期项目资格问题。

必须回答两个问题：

1. 用户看到的温度花纹最早出现在哪一层；
2. 用户看到的 NaN/空洞是主 Taw 数据 NaN、预期几何遮罩、comparison unsupported，还是绘图层引入。

原子任务 3、4 的只读阶段未修改源码；用户随后授权修复和 12 工况验证，仍未授权提交或推送。

战略总纲规定当前目标、技术合同、阶段门和授权边界；本 handoff 提供代码地图、已完成结论和下一任操作入口。当前执行同时以两份文件、当前源码和实际 `phase5_repair` 产物为准，不重新展开已删除的旧战略节点。

---

## 2. 当前可用入口

### 2.1 诊断产物

权威诊断目录：

```text
E:/navi_clean/runs/n8_taw_surface/*phase5_repair
```

已认证恰好 12 个目录，每个目录恰好包含：

```text
summary.json
Taw_error_stats.json
Taw_surface_fields.npz
Taw_surface_upper.png
Taw_surface_lower.png
Taw_provider_upper.png
Taw_provider_lower.png
Taw_validity_upper.png
Taw_validity_lower.png
Taw_error_vs_fluent_upper.png
Taw_error_vs_fluent_lower.png
```

当前诊断只消费这 12 个 `phase5_repair` 目录。旧 `phase2`、`phase4` 和其他候选 run 不作为当前产品输入。

### 2.2 当前缺陷所需代码地图

只保留下列与背风 Taw 花纹/NaN 直接相关的入口。

#### 单工况入口

`scripts/run_n8_taw_case.py`

- `main()` 解析一个 case、一个 run_dir、Ma、alpha 和来流参数；
- 将参数交给 `run_n8_taw_case()`；
- 当前没有 batch/sweep 逻辑；
- 原子任务 3 以读取现有产物为主，不应先调用该脚本重跑。

#### Taw 主链

`src/ref_enthalpy_method/n8_taw_surface.py`

| 函数 | 当前位置 | 当前职责 |
|---|---:|---|
| `load_n8_taw_case_spec()` | 291 | 读取单工况 schema |
| `load_n8_sampling_spec()` | 349 | 读取结构化采样网格 |
| `_load_geometry_inputs()` | 384 | 建立几何、mesh 和上下表面输入 |
| `dispatch_taw_predictions()` | 461 | 按 signed incidence 选择 Taw provider，并输出 prediction/provider/valid/reason |
| `_build_lf_surface_fields()` | 534 | 在 upper/lower 两个结构化网格上建立几何、分类、provider 和 Taw 主字段 |
| `_structured_cell_triangles()` | 957 | 只为四顶点全部有效的原始网格 cell 建立两个三角形 |
| `_plot_structured_surface()` | 978 | 将二维 Taw 网格绘制成 `Taw_surface_*.png` |
| `validate_n8_run_artifacts()` | 1153 | 验证产物字段和聚合合同，不负责判断可见花纹 |
| `run_n8_taw_case()` | 1237 | 串联输入认证、主字段、comparison、NPZ、JSON 和八张 PNG |

#### 主字段的精确数组布局

`_build_lf_surface_fields()` 使用：

```text
sampling.nx = 81
sampling.ny = 41
shape = (41, 81)
count_per_sheet = 3321
combined canonical rows = 6642
```

每个 sheet 先独立生成二维数组，然后按以下顺序以 C-order flatten：

```text
canonical 0..3320 = upper.reshape(-1)
canonical 3321..6641 = lower.reshape(-1)
```

以下主字段使用同一拼接顺序：

```text
x_m
span_m
z_m
incidence_s
geometry_valid
mapping_support_radius_m
Taw_prediction_K
valid
provider
failure_reason
surface_class_code / surface_class
normal_out
```

因此原子任务 3 必须验证异常 canonical index 与 `sheet_offset + j*81 + i` 一致，不能自行排序或按坐标重新配对。

#### Provider 与主 Taw NaN 的生成位置

`dispatch_taw_predictions()` 的实际行为：

```text
geometry-invalid:
  prediction = NaN
  provider = typed_invalid
  valid = false
  reason = invalid_geometry

geometry-valid + positive signed incidence:
  provider = windward_turbulent

geometry-valid + negative signed incidence:
  provider = leeward_recovery

geometry-valid + numerical zero incidence:
  provider = zero_incidence_recovery

dispatched prediction 非有限或 <= 0:
  valid = false
  reason = provider_nonfinite
```

原子任务 2 已证明现有 12 组 NPZ 中 `provider_nonfinite=0`；因此原子任务 3 不应从修改 provider 公式开始。

#### NPZ 到 Taw PNG 的实际路径

`run_n8_taw_case()` 先将 combined fields 和 upper/lower comparison arrays 写入：

```text
np.savez_compressed(.../Taw_surface_fields.npz)
```

随后对每个 sheet 使用固定 slice：

```text
upper slice = 0:3321
lower slice = 3321:6642
shape = (41, 81)

x_grid = x_m[sheet_slice].reshape(shape)
span_grid = span_m[sheet_slice].reshape(shape)
taw_grid = Taw_prediction_K[sheet_slice].reshape(shape)
geometry_grid = geometry_valid[sheet_slice].reshape(shape)
valid_grid = valid[sheet_slice].reshape(shape)
provider_grid = provider[sheet_slice].reshape(shape)
```

`Taw_surface_{sheet}.png` 只向 `_plot_structured_surface()` 传入 `x_grid`、`span_grid` 和 `taw_grid`。该函数内部定义：

```text
finite = isfinite(x_grid) & isfinite(span_grid) & isfinite(taw_grid)
```

`_structured_cell_triangles(finite)` 只保留四个顶点全部有限的原始 quadrilateral cell，并将每个保留 cell 拆成两个三角形，再交给 `tricontourf`。一个顶点无效会使所有触及该顶点的 cell 不进入 Taw 图。

`geometry_grid` 和 `valid_grid` 会用于 provider/validity 图，但不会作为独立参数传给 Taw 绘图函数；Taw 图通过 `taw_grid` 的有限性间接获得遮罩。这是原子任务 3 必须核对的实现事实，不等于根因已经成立。

#### Comparison 链

`src/ref_enthalpy_method/mapping/fluent_wall_temperature.py`

- 读取 Fluent wall-temperature observation；
- 保留 source-row identity；
- 构建 geometric-sheet observation；
- 不生成主 Taw 网格或 Taw surface PNG。

`n8_taw_surface.py` 中：

- `pair_projected_physical_points()` 建立 source-row 到 LF target 的 many-to-one pairing；
- `_build_comparison()` 生成 supported/`MAPPING_UNSUPPORTED` 和误差数组；
- `_plot_comparison_surface()` 只生成 `Taw_error_vs_fluent_*.png`。

因此 comparison NaN 不应被拿来解释主 `Taw_surface_*.png` 的花纹，除非原子任务 3 找到新的直接数据依赖。

#### 当前相关测试

`tests/test_n8_taw_surface.py`

| 测试类 | 当前覆盖 |
|---|---|
| `N8TawDispatchTest` | signed-incidence provider、invalid geometry 和 nonfinite reason |
| `N8StructuredConnectivityTest` | 原始网格 cell 连通与无效顶点遮罩 |
| `N8SourceRowPairingTest` | many-to-one pairing 和 local support |
| `N8WallTemperaturePublicReaderTest` | Fluent wall-temperature observation 读取 |

现有测试证明合同分支能够运行，但不证明用户所见花纹已被解释。原子任务 3、4 应先形成可复现证据，再决定需要补哪一条最小回归测试。

当前应追踪的唯一主链：

```text
_build_lf_surface_fields()
-> combined upper/lower flattened fields
-> Taw_surface_fields.npz
-> fixed sheet slice
-> reshape(41, 81)
-> finite vertex mask
-> original-cell triangle mask
-> tricontourf plot input
-> Taw_surface_upper/lower.png
```

### 2.3 必须保持的字段语义

```text
geometric_sheet = upper | lower
surface_class = windward | leeward | near_tangent
provider = windward_turbulent | leeward_recovery | zero_incidence_recovery
```

这些字段不是同一件事：

- `geometric_sheet` 决定 upper/lower 图归属；
- `surface_class` 是局部流态诊断分类；
- `provider` 是 Taw 计算提供者；
- 背风点不能用 upper、lower 或 z 坐标替代；
- `surface_class=leeward` 与 `provider=leeward_recovery` 必须分别统计。

当前 12 个正攻角工况中，实际背风点恰好都落在 geometric upper；这是这组数据的结果，不是 upper 与背风面的通用等价关系。

---

## 3. 原子任务计划

### 1. 认证 12 组输入、产物和实际背风点集 - 已完成

结论：

```text
run_dir = 12 of 12 authenticated
per-run inventory = exact 11 files
all-run inventory = 132 files
summary-declared artifact size/SHA-256 = 120 of 120 verified
source CSV byte hash = 12 of 12 verified
distinct source CSV SHA-256 = 12
summary schema = n8-taw-run-summary/v1
stats schema = n8-taw-error-stats/v1
NPZ schema = 56 fields
NPZ key/shape/dtype signature = identical across all 12 runs
directory/case/freestream/CSV/NPZ identity findings = 0
```

实际背风点集结论：

```text
surface_class=leeward = 4699 points
provider=leeward_recovery = 10882 points
both sets' geometric lower count = 0 in these 12 cases
```

两套点集数量不同是合同预期：`near_tangent` 是诊断标签，但 provider 仍按 signed incidence 选择。这个差值不是缺陷。

本任务不需要下一任重复；只有发现文件身份变化或现有数字自相矛盾时才重新认证。

### 2. 逐案例、逐几何面分类 Taw/comparison NaN - 已完成

聚合结论：

```text
canonical rows = 79704
geometry-valid / valid rows = 75708

main Taw NaN = 3996
  geometry-invalid NaN = 3996
  geometry-valid provider/nonfinite defect = 0
  main UNKNOWN = 0

surface_class=leeward main Taw NaN = 0
provider=leeward_recovery main Taw NaN = 0

comparison rows = 178092
comparison supported rows = 173508
comparison NaN rows = 4584
  exact MAPPING_UNSUPPORTED = 4584
  supported-row NaN defect = 0
  comparison UNKNOWN = 0
  wall_temperature_K NaN = 0

surface_class=leeward comparison target rows = 3620
  supported and finite = 3608
  MAPPING_UNSUPPORTED = 12
```

逐案例、逐 geometric sheet 结果：

| case_id | leeward class U/L | leeward provider U/L | 主 Taw NaN U/L | comparison NaN U/L | leeward mapping-unsupported U/L |
|---|---:|---:|---:|---:|---:|
| `ma6_a5_h30km` | 255/0 | 638/0 | 167/166 | 190/192 | 0/0 |
| `ma6p5_a3_h30km` | 0/0 | 382/0 | 167/166 | 190/192 | 0/0 |
| `ma6p5_a5_h40km` | 255/0 | 638/0 | 167/166 | 190/192 | 0/0 |
| `ma6p5_a8_h35km` | 610/0 | 1098/0 | 167/166 | 190/192 | 3/0 |
| `ma8_a10_h40km` | 847/0 | 1919/0 | 167/166 | 190/192 | 3/0 |
| `ma8_a10_h45km` | 847/0 | 1919/0 | 167/166 | 190/192 | 3/0 |
| `ma8_a5_h30km` | 255/0 | 638/0 | 167/166 | 190/192 | 0/0 |
| `ma8_a5_h40km` | 255/0 | 638/0 | 167/166 | 190/192 | 0/0 |
| `ma8_a5_h45km` | 255/0 | 638/0 | 167/166 | 190/192 | 0/0 |
| `ma9_a5_h40km` | 255/0 | 638/0 | 167/166 | 190/192 | 0/0 |
| `ma9_a5_h45km` | 255/0 | 638/0 | 167/166 | 190/192 | 0/0 |
| `ma9_a8_h35km` | 610/0 | 1098/0 | 167/166 | 190/192 | 3/0 |

每个工况的主 Taw NaN 都固定为 upper 167、lower 166，且全部位于 `geometry_valid=false`。现有 NPZ 中没有 geometry-valid 背风主 Taw NaN。

这不否定用户看到的温度 NaN/空洞。它只证明问题不能直接归为 NPZ 主 Taw provider nonfinite；下一步必须检查结构化 mask、reshape 和最终 PNG。

本任务不需要下一任重复；原子任务 3 应直接使用这些结论缩小搜索范围。

### 3. 定位温度花纹首次出现层 - 已完成

目标：

```text
确定花纹或可见空洞最早存在于：
raw/in-memory Taw field
| NPZ
| geometric-sheet extraction
| 81x41 reshape
| vertex/cell mask
| plot input
| final PNG
```

执行要求：

1. 从 12 张 `Taw_surface_upper.png` 入手，因为当前实际背风点位于 upper；lower 仍作为对照，不把 upper 当成背风定义。
2. 将 PNG 中的异常区域绑定到 canonical index、网格位置和坐标。
3. 同时检查 `surface_class` 与 `provider` 两套背风点集。
4. 对照 `geometry_valid`、`valid`、`failure_reason`、`Taw_prediction_K`。
5. 重建实际传给绘图函数的二维 Taw 和 cell mask。
6. 区分“数据值为 NaN”和“相邻 cell 因无效顶点被遮罩”。
7. 跨 12 工况比较相同 canonical/grid index，判断图案固定于拓扑还是随工况变化。
8. 不通过平滑、插值、补值或调色消除现象。
9. 本任务保持只读；若必须重跑或插桩，先向用户说明必要性和精确范围。

交付：

```text
受影响 run/sheet/PNG
异常区域和 canonical/grid index
每层输入的有限性与 mask 状态
首个出现异常的层
仍为 UNKNOWN 的点
```

### 4. 用代码和数据流证据闭合根因 - 已完成

目标：

- 将原子任务 3 找到的首个异常层绑定到具体代码路径和条件；
- 说明花纹为什么呈现当前空间结构；
- 证明它是预期几何遮罩、索引/reshape 错误、mask 扩散、绘图问题或其他明确原因；
- 将所有受影响点归为 expected-by-contract、defect 或 UNKNOWN；
- 给出精确影响范围；后续实施由用户扩大授权触发。

完成标准：

```text
first divergence is exact
affected cases and indices are exact
code path is exact
all observed NaN/holes are classified
root cause is reproducible from existing evidence
UNKNOWN = 0, or exact UNKNOWN set is reported
```

### 5. 全链路修复设计 - 已完成

原子任务 4 根因闭包后已完成，且用户明确取消最小范围约束：

- 必须修改的最小文件；
- 必须新增或调整的最小测试；
- 一个受影响工况的 red/green；
- 是否需要重跑其他工况的证据。

用户已批准全背风 Taw 链路整改。

### 6. 实施并验证批准后的修复 - 已完成

已经完成实施、专项测试、全量测试和 12 工况产品验证。

### 7. 删除审计、回归、code audit 与 Git 收口 - 未授权

当前不得开始。只有缺陷修复完成并通过受影响产品验证后，才重新确定该阶段范围。

---

## 4. 历史入口（已完成）

下一任无需重做原子任务 1～6。

以下历史指令已经完成：

```text
先完成原子任务 3：定位温度花纹首次出现层。
随后完成原子任务 4：用代码和数据流证据闭合根因。
后续由用户扩大授权完成全链路整改，最终状态见第 7 节。
```

主 Taw 有效背风点没有 NaN；用户所见花纹和空洞现已分别由 provider 阈值分裂、绘图插值和 geometry-invalid 遮罩精确解释。

---

## 5. 当前保护边界

- 不修改已发布 main、tag、Release 或历史产物。
- 不覆盖、删除或重写 12 个 `phase5_repair` 目录。
- 不把 upper/lower 与 windward/leeward 混为一谈。
- 不把 `MAPPING_UNSUPPORTED` comparison NaN 混入主 Taw NaN。
- 不把 near-tangent label 与 provider 选择混为一谈。
- 不处理与当前背风温度花纹/NaN 没有直接因果关系的项目历史。
- 工作区已有的 source/spec/test 修改属于当前 N8 现场，不得回退。
- `attachment/` 是未跟踪治理目录，不暂存、不提交。

---

## 6. 原子任务 3/4 回传格式

```text
status = PASS | FAIL | BLOCKED
task = 3 | 4
affected runs/sheets/images =
affected canonical/grid indices =
surface_class/provider selection =
raw or earliest available Taw state =
NPZ state =
reshape/mask state =
plot-input state =
PNG-visible state =
first divergence =
root cause =
expected-by-contract =
defect =
UNKNOWN =
files modified = none
runs rerun = none
next action =
```

---

## 7. 2026-07-27 闭包回传

原子任务 3：

- status = PASS
- affected runs/sheets/images = 12/12 phase5_repair；upper 为实际背风主区域，lower 为对照
- affected canonical/grid indices = 所有异常均保持 sheet_offset + j*81 + i；未发现重排或 reshape 错位
- surface_class/provider selection = near_tangent 诊断域被旧 signed-incidence 硬切为两种 provider
- raw or earliest available Taw state = 花纹首次存在于 raw/in-memory Taw_prediction_K
- NPZ state = 与 raw 一致；surface_class=leeward Taw 全部有限
- reshape/mask state = reshape 正确；四顶点 cell mask 过度删除有效 sibling triangle
- plot-input state = 主 Taw NaN 仅位于 geometry-invalid；comparison unsupported 不进入主 Taw 图
- PNG-visible state = 原始数据条带经跨 provider/分面 contour 插值加重
- first divergence = provider threshold 约 1e-12 与诊断 epsilon 0.05 不一致
- UNKNOWN = 0

原子任务 4：

- status = PASS
- root cause = threshold 语义分裂 + provider 硬切 + contour 插值 + quad 级过度遮罩
- expected-by-contract = 333 geometry-invalid/case 保持 NaN；不做外部支持虚构补值
- defect = near-tangent provider 分派、候选不可追踪、geometry 原因不精确、三角形/绘图过度处理
- UNKNOWN = 0

精确 geometry-invalid 分类（每工况）：

- upper：81 degenerate_planform_chord、85 outside_stl_support、1 geometric_sheet_mismatch；
- lower：81 degenerate_planform_chord、85 outside_stl_support；
- 12 工况总计 3,996 点；无内部封闭孔洞。

已实施：

- N8 dispatch schema：n8-taw-dispatch/v2；summary schema：n8-taw-run-summary/v2；
- s <= 0 recovery，0 < s < 0.05 C1 smoothstep 焓混合，s >= 0.05 windward；
- 序列化两套候选、blend weight、geometry failure reason；
- 逐原始三角形连通和 pairing support；
- 主 Taw 图使用 flat triangle color，取消跨分面等值插值；
- Group 8 冻结数值与正式 solver 不变。

验证：

- 32 个专项测试和 12 个 subtests 通过；
- 493 个全量测试和 137 个 subtests 通过；
- 12/12 *_phase6_leeward_chain_v2 运行 PASS，每工况 11 个产物；
- 跨 12 工况 75,708 个 geometry-valid 点全部有有效 provider；
- 10,459 个 near-tangent blend 点，3,996 个 geometry-invalid 点全部有精确原因；
- 结果目录保护已解除，旧结果内容未覆盖。

下一入口：本 Taw 花纹/NaN 缺陷已闭包；不重做原子任务 1～6；Git 和 release 动作仍需独立授权。

---

## 8. 2026-07-27 Current Handoff：连续法向 v3 已完成

本节 supersede 第 7 节的 v2 产品入口，但保留其原子任务 3/4 根因事实。

### 当前唯一产品入口

- `runs/n8_taw_surface/*_phase9_continuous_normal_cached_v3`
- `summary.schema=n8-taw-run-summary/v3`
- `taw_dispatch_schema=n8-taw-dispatch/v3`
- `normal_model_schema=stl-angle-weighted-continuous-normal/v1`
- `normal_crease_angle_deg=20.0`

12/12 工况由当前 validator PASS，每工况严格 11 件套。总计 geometry-valid/invalid=`75,708/3,996`，near-tangent blend=`10,684`，所有 geometry-valid 点 provider-valid。

最终 full pytest=`499 passed, 137 subtests passed`；缓存/连续法向/N8 组合专项=`54 passed, 14 subtests passed`；静态检查与 `git diff --check` PASS。

### 不得误解的法向责任

- 需要连续法向：N8 incidence、surface class、near-tangent dispatch、windward candidate `sx/sy` 和联合 Taw surface。
- 不需要/不得回算：Group 8、current-v5、N6/N7 frozen evidence/certification、旧 phase 产物。
- STL face normal 不删除：继续持有 position/sheet/triangle/support/crease/audit。
- 无完整解析曲面方程，故当前是连续且锐边保持的工程重建；不得写成已恢复 exact CAD analytic normal。

### Projection cache

- 12 CSV 的 canonical solver coordinates SHA-256 均为 `f8e831b08dd86283bb69dc2f5be5fdb636e160a801ce97ec4d9382098b611c23`。
- exact projection 只执行 1 次；缓存 unique key=1，首例 miss，其余 11 例 hit。
- source row、cellnumber 和 wall-temperature 逐工况处理，不进入 projection payload。
- 默认 cache scope 仍为 `source_geometry`；只有 N8 显式选择 `canonical_geometry`。scope 写入 manifest 并 fail closed。

### 下一任 GPT

1. 不重做原子任务 3/4。
2. 不继续旧任务 5/6；两项已在扩大授权下完成。
3. 以 phase9 v3 而不是 phase6 v2/phase7/phase8 中间目录作为当前结果。
4. 不修改 `docs/n6_4_exit_certification_zh.md`、`docs/n7_bounded_engineering_freeze_certification_zh.md` 或历史 mapping audit。
5. 未经新授权，不执行 Git stage/commit/push/merge/tag/release。
6. 如果进入新物理任务，先区分 N8 surface product 与 frozen Group 8/solver routing；v3 PASS 不等于 provider CFD validated。

当前剩余不是任务 5/6，而是用户明确指定的新任务或单独授权的 Git closeout。

---

## 9. Current Repair Entry：Geometry-invalid 产品域闭包

本节 supersede 第 8 节“当前剩余”句子。下一任 GPT 不做 Git closeout，也不重做 3–6；先完成 geometry domain closure。

### 9.1 基准与问题

只读基准：

- `runs/n8_taw_surface/*_phase9_continuous_normal_cached_v3`
- 12/12 validator PASS，每工况 11 件套；
- full pytest=`499 passed, 137 subtests passed`；
- continuous normal/provider/cache 合同保持当前 v3。

当前未闭包问题：

| reason | upper/case | lower/case | 12-case total | 当前解释 |
|---|---:|---:|---:|---|
| `degenerate_planform_chord` | 81 | 81 | 1,944 | `y/b=1` tip row 弦长退化，矩形网格把塌缩拓扑表达成 81 点 |
| `outside_stl_support` | 85 | 85 | 2,040 | outline 采样位置不在 STL projected support；边界分区和距离尚未完成 |
| `geometric_sheet_mismatch` | 1 | 0 | 12 | upper 单点命中三角形的 sheet identity 不一致，精确路径尚待审计 |
| total | 167 | 166 | 3,996 | provider 链没有失败，但产品几何域仍需工程闭包 |

### 9.2 必须按顺序执行

#### Step G1：只读几何证据

- 导出并冻结全部 invalid 点的 canonical/grid identity、坐标、reason、triangle candidate。
- 验证 12 工况几何 identity；相同则只运行一次昂贵几何分析，其余只验 identity。
- 将 85 点分为 nose/LE/TE/root/tip/other，记录到 outline 与 STL support 的精确距离。
- 对 upper mismatch 输出选中 triangle、相邻 triangle、raw/continuous normal、sheet classifier 和 sampler decision。

G1 回传至少包含：

`case/sheet/index =`  
`physical coordinate =`  
`reason =`  
`nearest support/triangle =`  
`distance =`  
`expected domain =`  
`defect | valid exclusion | UNKNOWN =`

#### Step G2：产品域方案

- tip row：比较“删除退化行”和“折叠为单 tip vertex + 重建 connectivity”，选择能同时满足物理拓扑、canonical identity、plot 和 mapping support 的方案。
- outside support：先判定 authority/transform/boundary semantics，再决定修 geometry/sampling 或显式缩小产品域；禁止先放宽 tolerance。
- mismatch：若是 classifier/sampler defect 则修复；若权威几何无法裁决则保留 typed invalid 并报告 exact UNKNOWN。
- 不接受 nearest-neighbor 补洞、跨 sheet 借值、无依据外推、仅在 PNG 隐藏点或把 NaN 改成常数。

#### Step G3：实现与测试

- 测试必须覆盖 tip topology、boundary support、sheet mismatch、no unexplained invalid、no interior hole、triangle/mapping consistency。
- 不覆盖 phase9；先建立代表工况新目录。
- N8 v3 法向/dispatch/cache 是回归基准，不得无因改回 STL face-normal routing。

#### Step G4：12 工况 phase10

- red/green：`ma8_a10_h40km`。
- 全量目录：新建 `*_phase10_geometry_domain_*`。
- 逐目录运行当前或升级后的 validator；核对 raw/NPZ/domain/topology/mapping/PNG。
- 最终允许保留有物理依据的边界 exclusion，但不得保留未解释 invalid 或由错误矩形拓扑制造的假孔洞。

### 9.3 禁止范围

- 不修改 `docs/n6_4_exit_certification_zh.md`、`docs/n7_bounded_engineering_freeze_certification_zh.md`、历史 mapping audit、Group 8 或 current-v5。
- 不覆盖/删除 phase6–phase9 正式或诊断结果。
- 不执行 Git stage/commit/push/merge/tag/release。
- 不把 geometry-domain closure 写成 provider CFD validation 或 performance PASS。

### 9.4 下一任启动口令

`读取 strategy 第 12 节和 handoff 第 9 节；从 G1 geometry-invalid source audit 开始。先只读，不改源码，不重跑 12 工况。G1 证据闭合后再进入 G2。`

---

## 10. 2026-07-27 G1/G2 Geometry Domain Closure 回传

本节 supersede 第 9.4 节启动口令。完整证据与方案见：

```text
attachment/Faceted3D_v2_G1_G2_geometry_domain_closure_20260727.md
attachment/n8_taw_geometry_invalid_g1_audit_20260727.csv
```

### G1 - PASS

- 12 个 phase9 的 333 个 invalid 几何字段 byte-exact；统一 invalid-geometry digest=`8cd4750a3dfd42f8b3f0b4db2928f8322940740a0387a6a987c1f08bc2b23acb`。
- 每 sheet 的 85 个 outside 点精确分区为 nose=2、LE=83；40 点在 outline/STL projected boundary 外，45 点只命中 `|n_z|<0.45` cap triangle。
- upper mismatch=`canonical 2188 / grid(27,1)`；cap triangle 2184 被阈值排除后，sampler 把 lower triangle 4633 同时返回给 upper/lower，证明 requested-sheet prefilter 缺失。
- tip 行每 sheet 81 点只覆盖 `5.8472489533e-6 m` 退化弦；outline tip 与 STL tip 相差 1 mm，exact STL tip 只属于 cap/other，不存在 graph-skin Taw sample。
- 当前 classifier 另有 76 个 eligible triangle 未分类；G3 必须用 adjacency/seed propagation 闭合。
- physical exclusion 有依据；矩形域、tip duplication 和 mismatch 路径为 defect；UNKNOWN=0。

### G2 - PASS

- STL 持有 position/support/topology authority；outline 降为 sampling seed/audit reference。
- 产品域明确为 sheet-specific graph-skin；nose/LE cap、side/cap 和 exact physical tip 不进入 upper/lower Taw 域。
- “删 tip 行”会截短 25.775675 mm；“折叠到 exact tip”会跨入 cap 域，二者均不采用。
- 采用 domain-conforming clipped topology：按 sheet graph-skin 裁剪结构采样网格，插入精确 boundary intersection nodes，在 skin/cap boundary 显式终止。
- 新 NPZ 使用显式 node/triangle connectivity、domain role、STL source identity、legacy phase9 provenance 和 exclusion audit；plot/mapping 只消费同一套显式 triangles。
- sampler 在 z 排序前按 requested sheet 过滤；classifier 用 eligible triangle adjacency 和无歧义内部 seed 传播，冲突/未覆盖 fail closed。

### 当前入口

```text
G1 = PASS
G2 = PASS
next = G3 implementation and focused validation
phase9 = frozen read-only regression baseline
source/test changes in this G1/G2 turn = none
runs rerun = none
Git authorization = none
```

---

## 11. 2026-07-27 Comparison Error 云图与 12 工况重跑

用户明确授权把误差图从点状图改成云图并重跑 12 工况。完成结果：

```text
product = runs/n8_taw_surface/*_phase10_comparison_contour_v3
validator = 12/12 PASS
inventory = 11 artifacts/run
projection cache = 12/12 hit
focused tests = 22 passed, 12 subtests passed
full tests = 502 passed, 137 subtests passed
```

渲染合同：Delaunay + `tricontourf`；三角形只保留三个 supported 顶点且每条边的 local mapping-support 半径相交者。unsupported 和跨空隙区域 mask，不再使用 scatter marker。原 source rows 和 NPZ 不去重。

对照 phase9：12/12 NPZ 数组逐字段一致；72/72 非误差 PNG 哈希一致；24/24 误差 PNG 按预期变化并通过连续填色像素检查。stats 仅新增本轮命令传入的 `altitude_input_m` provenance，freestream 仍为 explicit custom，数值未变。

完整记录：

```text
attachment/Faceted3D_v2_phase10_comparison_contour_validation_20260727.md
```

本轮不是 G3 geometry-domain implementation。第 10 节 G1/G2 结论和下一入口保持：`NEXT=G3`。Git 动作仍未授权。


---

## 12. 2026-07-27 G3 Geometry Domain Implementation

本节 supersede 第 10/11 节的 G3 下一入口。完整记录：

~~~text
attachment/Faceted3D_v2_G3_geometry_domain_implementation_validation_20260727.md
~~~

状态：

~~~text
G1 = PASS
G2 = PASS
G3 = PASS
UNKNOWN = 0
representative = ma8_a10_h40km_phase13_geometry_domain_v4_redgreen
summary = n8-taw-run-summary/v4
topology = n8-taw-domain-topology/v1
nodes/triangles = 9663/18110
provider-valid = 9663/9663
legacy exclusions = 333 in separate typed audit table
focused = 30 passed, 12 subtests passed
full = 505 passed, 137 subtests passed
NEXT = G4 twelve-case geometry-domain validation
Git authorization = none
~~~

实现已经完成 requested-sheet prefilter、eligible component sheet propagation、显式 graph-skin 裁剪节点/三角表、STL source triangle/edge identity、统一 plotting/mapping connectivity、topology hash 和 v4 validator。6309 个 phase9 直接祖先节点的 v3 normal/provider/Taw 字段 byte-exact；新增边界节点才使用完整分类法向。

phase12_geometry_domain_v4_redgreen 是隔离 v3 normal responsibility 前的诊断目录，不作为最终代表产品。phase13 是当前 G3 red/green authority。G4 尚未运行，不得把单工况 G3 PASS 写成 12 工况产品闭包。
---

## 13. 2026-07-27 G4 Twelve-case Geometry Domain Validation

本节 supersede 第 12 节的 G4 下一入口。

~~~text
G1 = PASS
G2 = PASS
G3 = PASS
G4 = PASS
UNKNOWN = 0
current product = runs/n8_taw_surface/*_phase13_geometry_domain_v4
summary = n8-taw-run-summary/v4
topology = n8-taw-domain-topology/v1
topology sha256 = 1490f733d15e373ba017d503025b6bb0f4e558378e94e719e3f3a7b0c2b7acae
runner/validator = 12/12 PASS
inventory = exact 11/run
projection cache = 12/12 hit
nodes/triangles = 9663/18110 per run
provider-valid = 9663/9663 per run
legacy exclusion audit = 333/run
phase9 direct-ancestor byte-exact = 12/12
focused = 30 passed, 12 subtests passed
full = 505 passed, 137 subtests passed
Git authorization = none
~~~

完整记录：

~~~text
attachment/Faceted3D_v2_G3_geometry_domain_implementation_validation_20260727.md
~~~

geometry-domain closure 已完成。phase9-phase11 未覆盖；phase12 red/green 仅为中间诊断，不是当前产品。下一入口不再是 G1-G4，而是用户明确指定的新任务或单独授权的 Git closeout。
---

## 14. 2026-07-28 N8 最终闭包、清理与下一轮审计入口（supersede 旧口径）

本节覆盖前文的产物数量、测试数量、Git 授权和下一入口。

```text
G1/G2/G3/G4 = PASS
UNKNOWN = 0
current product = runs/n8_taw_surface/*_phase13_geometry_domain_v4
runner/validator = 12/12 PASS
inventory = exact 13 artifacts/run
projection cache = 12/12 hit
nodes/triangles = 9663/18110 per run
provider-valid = 9663/9663 per run
legacy exclusion audit = 333/run
full tests = 508 passed, 137 subtests passed
N8/projection focused = 63 passed, 14 subtests passed
N8-targeted Ruff = PASS
full-repository Ruff = 416 historical warnings, intentionally not autofixed
Git stage/commit/push authorization = granted by user on 2026-07-28
```

每工况现有四张误差图：upper/lower 固定 `±10%` 两张，以及 upper/lower 按实际最小值和最大值自动定界两张。固定图保留跨工况可比性，自动范围图完整呈现超出或小于 `±10%` 的实际误差；因此产物清单由 11 项增至 13 项。

代表工况 `ma8_a10_h40km` 的 cache-hit 端到端实测为 `18.702 s`，范围包括 Python 启动、计算、13 个产物写出和 validator。未测当前 v4 的 projection cache miss 冷启动，不得把历史版本的 miss 时间冒充当前精确性能。

仓库清理已经完成以下已确认安全的部分：

- 卸载了指向 `D:\ref\reference-enthalpy_03_12_26-main` 的旧 editable 安装，避免 Python 在仓库外误导入旧包；
- 删除 `scripts/_archive/` 中 29 个 tracked 过期文件（本地合计 54 项缓存/文件，约 1.29 MB）；
- 未新增 `pytest.ini`，也未新增代码导览声明；现有文档直接按当前有效代码更新；
- `src/ref_enthalpy_method/aero/adiabatic_wall_temp.py` 当前运行时零引用，但仍被 current-v5 source identity 冻结，本轮不绕过受控 migration 删除。

### 下一任 GPT 的唯一清理入口

全仓 `ruff check src tests scripts` 仍报告 `416` 个历史 style/static warning，主要集中在诊断脚本和旧测试。这 416 项只是“疑似旧文件/代码”的候选集，不等于 416 个都可以删除。下一任必须逐项完成 incoming reference、正式 CLI、spec、test、baseline/source identity 和文档引用审计后，再分批删除或修正；禁止直接 `ruff --fix` 或按目录整批删除。

### Git 与 current-v5 收口要求

本轮 production source inventory 净增 1 项。实现提交形成 clean committed HEAD 后，必须使用现有 `--migrate-source-identity` 流程，对两个 current-v5 manifest 做 source-only migration，再运行 official current regression。只允许改变 `source_identity` 和 `source_hashes_sha256`；`fields.npz`、`summary.json`、artifact hashes、Groups 1-8 和数值 baseline 必须 zero drift。用户已授权跟踪并更新本交接附件及 G1/G2 附件。
