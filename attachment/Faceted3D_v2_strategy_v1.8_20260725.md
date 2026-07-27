# Faceted3D v2 - 项目战略总纲

> 版本：v1.8-current  
> 日期：2026-07-27（Asia/Shanghai）  
> 当前阶段：N8 Taw 连续法向与 canonical projection cache 已验证；geometry-invalid 产品域待闭包  
> 当前任务：`N8_TAW_GEOMETRY_DOMAIN_CLOSURE`  
> 当前状态：原计划任务 3～6 已完成；phase9 通过 12/12 工况，但每工况仍有 333 个 geometry-invalid 点  
> 当前分类：`N8_TAW_SURFACE_V3_PROVIDER_AND_NORMAL_CHAIN_VALIDATED__GEOMETRY_DOMAIN_OPEN`  
> 当前入口：第 12 节；第 11 节及以前的“下一步”只作历史记录

---

## 0. 文件职责

本战略总纲只负责：

- 当前项目意图；
- 必须保持的技术合同；
- 原子任务顺序和阶段门；
- 哪些动作已授权、哪些动作仍被阻止；
- 当前阶段何时算完成。

具体代码函数、数组布局、逐案例统计和下一任操作入口见：

```text
attachment/Faceted3D_v2_GPT_handoff_current_20260726_n7_n6_3_reference_validator_repair_entry.md
```

实时技术事实以当前源码和 `runs/n8_taw_surface/*phase5_repair` 产物为准。旧聊天、旧 handoff 和已被当前状态取代的阶段结论不构成当前执行指令。

---

## 1. 当前项目意图

现有 N8 链路已经能够生成：

- geometric upper/lower Taw 主字段；
- provider 和 validity 字段；
- Fluent source-row comparison；
- NPZ、JSON 和上下表面 PNG；
- 12 个单工况 `phase5_repair` 产品目录。

当前不再以“跑通整个项目”或“补齐全部数学链条”为目标。

当前唯一战略目标是：

```text
解释并解决用户在背风区域看到的 Taw 温度花纹和温度 NaN/空洞，
同时保持现有健康链路和已验证数据身份不被破坏。
```

当前阶段的成功不是“文件能够生成”，而是：

1. 花纹最早出现的数据层被证明；
2. 所有相关 NaN、空洞和 mask 均有明确身份；
3. 根因绑定到精确数据流和代码条件；
4. 最小修复范围经用户批准；
5. 修复后的 raw field、NPZ、mask、plot input 和 PNG 同时通过验证；
6. 不引入与目标缺陷无关的项目扩张。

---

## 2. 当前问题边界

### 2.1 分析对象

只使用：

```text
E:/navi_clean/runs/n8_taw_surface/*phase5_repair
```

共 12 个 run_dir，每个目录 11 个产物：

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

旧 run 不作为当前产品证据，也不需要重新评价。

### 2.2 当前必须回答的问题

```text
A. 温度花纹最早存在于 raw/in-memory field、NPZ、sheet extraction、
   reshape、vertex/cell mask、plot input 还是 PNG？

B. 用户看到的 NaN/空洞属于主 Taw 数据 NaN、预期 geometry-invalid mask、
   comparison MAPPING_UNSUPPORTED，还是可视化层缺陷？

C. 异常是否固定在相同 topology/grid index，还是随工况变化？
```

### 2.3 当前不做的事情

- 不重新设计完整物理模型；
- 不重新评价已经健康的项目链路；
- 不重开旧阶段资格和历史案例讨论；
- 不通过平滑、插值、补值或调色隐藏现象；
- 不在根因闭包前删除旧代码、重跑 12 工况或实施修复。

若原子任务 3、4 的直接证据证明需要扩大范围，必须先向用户说明原因和精确影响面。

---

## 3. 必须保持的技术合同

### 3.1 表面与流态是正交维度

```text
geometric_sheet = upper | lower
surface_class = windward | leeward | near_tangent
provider = windward_turbulent | leeward_recovery | zero_incidence_recovery
```

必须保持：

- upper/lower 决定最终几何表面归属；
- surface_class 是局部流态诊断；
- provider 是 Taw 数值提供者；
- 不得用 upper、lower 或 z 坐标代替背风点定义；
- `surface_class=leeward` 和 `provider=leeward_recovery` 必须分别统计。

当前 12 个正攻角工况的实际背风点都位于 geometric upper。这只是当前数据结果，不是 upper 与背风面的通用等价关系。

### 3.2 主 Taw 与 comparison 必须分开

主 Taw 字段：

```text
canonical_index
geometric_sheet
geometry_valid
surface_class
incidence_s
provider
valid
failure_reason
Taw_prediction_K
```

comparison 字段：

```text
source_row_index
target_canonical_index
comparison_valid
comparison_failure_reason
wall_temperature_K
Taw_prediction_K
signed/absolute error
```

`MAPPING_UNSUPPORTED` 只解释 comparison prediction/error NaN，不解释主 Taw 图。不得混计两类 NaN。

### 3.3 数据身份与顺序必须保留

- 12 个 source CSV 的字节身份必须保持；
- Fluent source rows 不去重；
- many-to-one target pairing 保持；
- canonical index 不重新排序；
- upper/lower 固定 sheet 布局保持；
- 现有 `phase5_repair` 目录不覆盖、不改写。

### 3.4 可视化必须接受数据层验证

PNG 可读、非空或色彩正常不能代替数据验证。

必须同时验证：

```text
raw or earliest available Taw
NPZ Taw
sheet slice
reshape result
vertex finite mask
cell triangle mask
plot input
PNG-visible region
```

---

## 4. 原子任务计划与状态

### 1. 输入、产物、schema 和实际背风点集认证 - 已完成

完成结论：

```text
run_dir = 12 of 12 authenticated
inventory = exact 11 per run / 132 total files
artifact size/SHA-256 = 120 of 120 verified
source CSV byte hash = 12 of 12 verified / 12 distinct
JSON schemas = valid
NPZ = 56 fields
NPZ key/shape/dtype signature = identical across 12 runs
case/freestream/CSV/NPZ identity findings = 0

surface_class=leeward = 4699 points
provider=leeward_recovery = 10882 points
```

两套背风点集数量不同是当前字段合同的正常结果，不是缺陷。

状态：

```text
ATOMIC TASK 1 = COMPLETE
NEXT GPT MUST NOT REPEAT WITHOUT CONTRADICTORY EVIDENCE
```

### 2. 逐案例、逐 geometric sheet 的 NaN 分类 - 已完成

完成结论：

```text
canonical rows = 79704
geometry-valid / valid = 75708

main Taw NaN = 3996
geometry-invalid main NaN = 3996
geometry-valid provider/nonfinite defect = 0
main UNKNOWN = 0
leeward main Taw NaN = 0

comparison rows = 178092
comparison supported = 173508
comparison NaN rows = 4584
MAPPING_UNSUPPORTED = 4584
supported-row NaN defect = 0
comparison UNKNOWN = 0
wall_temperature_K NaN = 0
```

现有 NPZ 中没有 geometry-valid 背风主 Taw NaN。这个结论排除了一个来源，但没有否定用户在 PNG 中看到的花纹或空洞。

状态：

```text
ATOMIC TASK 2 = COMPLETE
NEXT GPT MUST USE THIS RESULT AS TASK 3 INPUT
```

逐案例表和代码级数组布局见 current handoff。

### 3. 定位温度花纹首次出现层 - 已完成

必须完成：

1. 将 PNG 异常区域绑定到 case、sheet、grid index 和 canonical index；
2. 比较两套实际背风点集；
3. 重建 fixed sheet slice 和 `reshape(41, 81)`；
4. 比较 Taw finite mask、geometry/validity mask 和 cell triangle mask；
5. 对照最终 PNG 可见区域；
6. 跨 12 工况比较相同网格位置；
7. 给出首个出现异常的数据层和精确 UNKNOWN。

原子任务 3 执行时授权（历史记录，后续已扩大）：

```text
READ-ONLY
NO SOURCE EDIT
NO RUN RERUN
NO ARTIFACT OVERWRITE
```

若只读证据不足以比较 raw/in-memory field，先提出最小插桩或单工况重跑需求，由用户决定。

### 4. 用精确代码和数据流证据闭合根因 - 已完成

必须给出：

- first divergence；
- 受影响 case/sheet/index；
- 直接代码路径和触发条件；
- 花纹空间结构形成原因；
- expected-by-contract、defect、UNKNOWN 分类；
- 最小影响范围。

完成门：

```text
ROOT CAUSE PROVEN
or
EXACT UNKNOWN SET REPORTED
```

原子任务 4 在只读阶段完成；用户随后明确授权全链路整改。

### 5. 全链路修复设计 - 已完成

原子任务 4 完成后已执行。

修复设计已覆盖：

- 修改哪些文件；
- 为什么这些文件足够；
- 新增或修改哪些测试；
- 选择哪个受影响工况做 red/green；
- 是否需要重跑其他工况；
- 明确不修改的范围。

用户已明确取消“最小范围”约束并批准全链路整改。

### 6. 实施并验证用户批准的修复 - 已完成

用户已批准，实施和 12 工况验证均已完成。

验证必须覆盖：

```text
raw field
NPZ
mask/reason
structured plot input
PNG
focused regression
affected product validation
```

不得用 PNG 观感单独判定修复成功。

### 7. 删除审计、适用回归、code audit 与 Git 收口 - 未授权

只有原子任务 6 通过后才重新确定范围。

该阶段至少需要：

- 引用和运行可达性审计；
- 适用专项测试；
- 适用全量回归；
- defect-first code audit；
- 精确暂存边界；
- 普通提交和任务分支推送。

合并 main、tag、Release 仍需用户单独授权。

---

## 5. 阶段门

### GATE 1 - NaN 身份门

要求：

- 输入和产物身份精确；
- 主 Taw 与 comparison NaN 完全分开；
- defect 和 UNKNOWN 有明确数量。

状态：

```text
PASS
由原子任务 1、2 完成
```

### GATE 2 - 花纹根因门

要求：

- 花纹首次出现层精确；
- index 和 mask 传播精确；
- 代码触发条件精确；
- 受影响范围精确。

状态：

```text
OPEN
由原子任务 3、4 关闭
```

GATE 2 未关闭前，原子任务 5～7 不得开始。

### GATE 3 - 最小修复批准门

要求：

- 根因已证明；
- 修复范围与根因一一对应；
- red/green 工况和测试明确；
- 用户明确批准。

状态：

```text
BLOCKED BY GATE 2
```

### GATE 4 - 产品与工程收口门

要求：

- 修复后数据层和 PNG 同时通过；
- 受影响范围产品重新验收；
- 删除审计、回归和 code audit 完成；
- Git 边界清楚。

状态：
```text
BLOCKED
```

---

## 6. 不可破坏的边界

- 已发布 main、tag、Release 和历史产物不改写。
- 当前工作区已有 N8 source/spec/test 修改不回退。
- 12 个 `phase5_repair` 目录保持只读诊断输入。
- `attachment/` 保持未跟踪治理目录，不暂存、不提交。
- 不伪造旧 hash、manifest 或 provenance。
- 不通过降低产品范围来宣称问题消失。
- 不把文件生成成功等同于温度产品正确。
- 不把聚合统计 PASS 等同于花纹根因闭包。

---

## 7. 当前历史压缩记录

只保留与当前入口有关的历史事实：

1. 已发布基线保持冻结，不因当前缺陷诊断改写。
2. N8 Taw-only 双 geometric-sheet 链已建立。
3. 12 个单工况 `phase5_repair` 目录已形成并通过身份、字段和聚合产物认证。
4. 用户随后指出背风区域 Taw 温度花纹和 NaN/空洞，因此聚合 PASS 不再被视为当前问题闭包。
5. 当前只完成了产物认证和 NaN 分类，花纹首次出现层与根因仍待证明。

旧阶段的详细命令、测试数量、案例资格、证据层级、提交过程和发布过程不再放入当前战略总纲。

---

## 8. 历史执行指令（已完成）

以下指令已经完成，不应重复执行：

```text
原子任务 3：
定位温度花纹首次出现于哪一层。

原子任务 4：
用精确代码路径和数据流证据闭合根因。

后续扩大：
用户已明确授权全链路整改，最终状态见第 10 节。
```

禁止重复原子任务 1、2，除非发现实际输入身份变化或现有结论自相矛盾。

代码函数、数组布局、逐案例表和固定回传格式以 current handoff 为准。

---

## 9. 战略总纲更新触发条件

只在以下情况更新：

- 原子任务 3 或 4 完成；
- 出现精确 UNKNOWN 或诊断阻塞；
- 用户批准最小修复包；
- 修复验证改变当前产品状态；
- 用户改变当前目标或授权边界；
- 进入删除、Git closeout、merge 或 release 决策。

普通代码阅读、重复统计和无状态变化的检查不需要改写战略总纲。

---

## 10. 2026-07-27 原子任务 3/4 与全链路修复闭包

### 10.1 原子任务 3：首次异常层

状态：PASS。

- 12 个工况的花纹最早已存在于 raw/in-memory Taw_prediction_K，不是 NPZ 序列化、sheet slice、reshape(41, 81) 或 canonical index 错误。
- surface_class=leeward 的主 Taw 在 12 个工况中全部有限；comparison 的 MAPPING_UNSUPPORTED 与主 Taw NaN 无数据依赖。
- 每个工况主 Taw NaN 固定为 upper 167、lower 166，且全部为 geometry_valid=false；没有 geometry-valid 主 Taw NaN，也没有内部封闭孔洞。
- 每工况 geometry-invalid 精确分类：
  - upper：81 degenerate_planform_chord、85 outside_stl_support、1 geometric_sheet_mismatch；
  - lower：81 degenerate_planform_chord、85 outside_stl_support。
- 原四顶点 cell 遮罩会因一个无效顶点同时删除同一 quad 的两个三角形，扩大 PNG 可见空洞。

### 10.2 原子任务 4：根因

状态：PASS，UNKNOWN=0。

first divergence：

1. 诊断分类使用 INCIDENCE_EPSILON=0.05，但旧 provider 用约 1e-12 的 signed-incidence 正负号硬切；
2. 同一个 surface_class=near_tangent 区域因此被交替送入 freestream recovery 与 windward turbulent 两套 Taw 候选；
3. tricontourf 又跨 provider/分面三角形连续插值，形成数据层已有、绘图层加重的条带；
4. geometry-invalid 是翼尖退化弦长、formal outline 超出 STL 投影支持和 1 个 upper sheet mismatch，不是 provider nonfinite。

### 10.3 已实施的 v2 合同

- Group 8 冻结诊断数值和正式 solver 路径不变；整改限定在 N8 联合 Taw 产品链。
- s <= 0 使用 leeward_recovery；0 < s < 0.05 使用 C1 smoothstep 焓混合；s >= 0.05 使用 windward_turbulent。
- NPZ 新增 Taw_windward_candidate_K、Taw_recovery_candidate_K、windward_blend_weight、geometry_failure_reason 和 taw_dispatch_schema=n8-taw-dispatch/v2。
- 几何外部支持不虚构补值；所有无效点保留可追踪平面坐标和精确原因。
- 绘图连通与 pairing support 统一为逐原始三角形判断；主 Taw PNG 使用 flat triangle color，不跨分面虚构连续等值带。
- summary schema 为 n8-taw-run-summary/v2。

### 10.4 验证

- 专项测试：32 passed，12 subtests passed。
- 全量测试：493 passed，137 subtests passed。
- 12/12 新 *_phase6_leeward_chain_v2 目录 PASS；每目录 11 个产物。
- 跨 12 工况：75,708 个 geometry-valid 点全部 provider-valid；10,459 个 near-tangent blend 点；3,996 个 geometry-invalid 点全部有精确原因。
- 代表工况 ma8_a10_h40km：全场相邻 Taw 跳变 P95 从 14.58 K 降到 1.68 K；旧 provider 边界跳变 P95 为 17.79 K。
- 旧 phase4、phase5_repair 和 repair_candidate 结果内容未覆盖；已发现的受保护结果目录均恢复为父目录继承 ACL。

当前产品状态：N8_TAW_LEEWARD_CHAIN_V2_REPAIR_VALIDATED_12_CASES

---

## 11. 2026-07-27 v3 连续法向与缓存闭包（supersedes 第 10 节产品入口）

当前产品状态：

`N8_TAW_SURFACE_CONTINUOUS_NORMAL_CACHED_V3_VALIDATED_12_CASES`

### 法向适用性

- N8 联合 Taw surface 必须使用连续法向，因为其局部 incidence、迎背风分类和 windward candidate 坡度都依赖设计表面方向连续性。
- 冻结 Group 8、current-v5、N6/N7 历史产品不需要连续法向回算，也禁止借本轮改写。
- STL face normal 继续负责 position、geometric sheet、triangle identity、support、crease detection 与审计。
- 当前 spec 没有完整解析曲面方程；正式实现是 20° crease-preserving angle-weighted continuous STL normal，不宣称 exact CAD analytic normal。

### 任务 5/6 最终解释

- 原子任务 5 已完成：全链修复设计已扩展为 provider/plot/mask 整改、连续法向责任边界、v3 schema/validator 和 canonical projection reuse。
- 原子任务 6 已完成：源码实现、formal STL 专项、cache 专项、N8 专项、全量回归和 12 工况 v3 产品验证均已执行。
- 下一任不得按旧计划重做任务 5/6，也不得把 phase6 v2 当作当前最终入口。
- 任务 7 的 Git 暂存、提交、推送、合并、tag、release 未授权；技术验证完成不自动扩大 Git 权限。

### v3 验证事实

- summary/dispatch/normal schema：`n8-taw-run-summary/v3`、`n8-taw-dispatch/v3`、`stl-angle-weighted-continuous-normal/v1`。
- 12/12 `*_phase9_continuous_normal_cached_v3` PASS；每工况 11 件套；本轮 12/12 cache hit。
- 最终全量回归=`499 passed, 137 subtests passed`；缓存/连续法向/N8 组合专项=`54 passed, 14 subtests passed`。
- geometry-valid/invalid=`75,708/3,996`；near-tangent blend=`10,684`；所有 geometry-valid 点 provider-valid。
- formal STL upper shared-edge continuous-normal error `<1e-12`；lower >20° crease 保留；最大平滑角 `8.0004408333°`。
- canonical coordinate identity 跨 12 CSV exact equal；projection unique key=1，miss/hit=1/11；source row/cellnumber 差异不触发重复投影。

阶段门更新：GATE 2=PASS；扩大授权后的 GATE 3=PASS；GATE 4 的数据/PNG/专项/全量/12 工况技术部分=PASS，Git closeout 仍为未授权。

---

## 12. 当前战略入口：Geometry Domain Closure（supersedes 第 11 节“下一步”）

当前精确状态：

`N8_TAW_SURFACE_V3_PROVIDER_AND_NORMAL_CHAIN_VALIDATED__GEOMETRY_DOMAIN_OPEN`

phase9 已证明 provider dispatch、连续法向、缓存、序列化和绘图链通过，但不能把 `3,996` 个 geometry-invalid 仅因“原因已分类”就视为最终工程闭包。它们不是 provider nonfinite，也不是内部随机孔洞；剩余问题是产品采样域、outline 与 STL 支撑域、sheet identity 是否工程一致。

### 12.1 当前已知事实

每工况固定 `333` 个 geometry-invalid：

- upper：`81 degenerate_planform_chord` + `85 outside_stl_support` + `1 geometric_sheet_mismatch` = `167`；
- lower：`81 degenerate_planform_chord` + `85 outside_stl_support` = `166`；
- 12 工况总计 `3,996`，几何身份跨工况相同。

其余 `75,708` 个 geometry-valid 点全部 provider-valid。该事实只证明 provider coverage，没有证明 rectangular 81×41 产品拓扑对翼尖和边界是正确表达。

### 12.2 下一批原子任务

#### G1. Geometry-invalid source audit

1. 从 phase9 NPZ 导出全部 invalid canonical/grid index、`x/c`、`y/b`、`x/span/z`、sheet、triangle candidate 和 failure reason。
2. 证明 12 工况几何 invalid identity 是否 byte-exact；若相同，只分析一套几何并在其余 11 套做 identity validation，不重复计算。
3. 给 85 个 `outside_stl_support` 点按 nose/LE/TE/root/tip/other 分区，计算到 STL projected support 和 outline 边界的精确距离。
4. 定位 upper 唯一 `geometric_sheet_mismatch` 的 triangle ID、相邻三角形、sheet classifier 输入和选择路径。

#### G2. Geometry product-domain design

1. `y/b=1` 处弦长退化时，81 个 x 采样点在物理上塌缩为翼尖拓扑，不能继续被当作 81 个独立表面点。必须在“移除退化行”与“折叠为单一 tip vertex 并重建三角连接”之间作工程设计。
2. 对 `outside_stl_support`，先裁决是 outline/STL/坐标合同缺陷、边界包含语义缺陷，还是确实位于权威 STL 域外；不得先扩大 tolerance。
3. 对真实域外点，应修改产品域/拓扑并在边界显式终止，而不是保留矩形网格后显示成孔洞。
4. 对可证明属于表面的点，应修复 authoritative geometry/sampling/triangle selection；禁止 nearest fill、无依据外推、跨 sheet 借值或伪造 Taw。
5. G2 必须同时定义 plotting triangles、mapping support、canonical identity 与 NPZ schema 如何表示新拓扑，不能只修 PNG。

#### G3. Implementation and focused validation

- 增加 tip topology、outline/STL boundary、sheet mismatch、no-unexplained-invalid、no-interior-hole、mapping-support consistency 测试。
- 保持 N8 v3 continuous-normal/provider 合同，除非 G1 证明它与几何域修复有直接冲突。
- 冻结 Group 8、current-v5、N6/N7 和 phase9；所有新产品使用新 phase/schema 或明确兼容版本，禁止覆盖旧目录。

#### G4. Twelve-case product validation

- 先用 `ma8_a10_h40km` 做 red/green，再新建 `*_phase10_geometry_domain_*` 跑 12 工况。
- 验收 raw field、NPZ、failure/domain representation、triangle topology、mapping support、PNG 和 validator。
- 成功条件不是强求 geometry-invalid count=0，而是：无未解释 invalid、无矩形拓扑制造的假孔洞、无跨域补值、所有保留表面点都有物理和几何依据。

### 12.3 边界与顺序

- 不重做原子任务 3–6；phase9 是本批工作的只读输入与回归基准。
- 原任务 7 的 Git closeout 延后到 G1–G4 完成之后；当前仍不授权 stage/commit/push/merge/tag/release。
- 不修改历史认证文档，不把 geometry-domain 修复升级为 provider CFD validation。
- 若 G1 发现 authoritative outline 与 STL 本身互相矛盾且无法由现有仓库裁决，必须报告精确 UNKNOWN 和所需几何 authority，不得自行猜测。

---

## 13. 2026-07-27 G1/G2 完成（supersedes 第 12.2 节任务入口）

### 13.1 G1 状态

`G1 Geometry-invalid source audit = PASS`，`UNKNOWN=0`。

- 12 工况 invalid geometry identity byte-exact，只审计一套几何；
- 85 outside 点/sheet=`nose 2 + LE 83`；40 点为 outline/STL projected boundary 差异，45 点只属于 `|n_z|<0.45` cap；
- 唯一 upper mismatch 是 sampler 未先按 requested sheet 过滤造成的 lower triangle 复用；
- exact tip 属于 cap/other，不属于当前 upper/lower graph-skin；
- 矩形域和退化 tip 行是产品拓扑缺陷，不是 provider nonfinite。

### 13.2 G2 状态

`G2 Geometry product-domain design = PASS`。

方案冻结为：

```text
STL authority
-> topology-based complete sheet classification
-> requested-sheet candidate filtering
-> graph-skin domain clipping
-> explicit boundary nodes and triangles
-> explicit canonical node/triangle identity
-> shared plotting/mapping connectivity
-> typed domain exclusion audit
```

不采用截断到 `y/b=0.975` 的简单删行，也不把域外 exact tip 伪造成 graph-skin Taw vertex。新拓扑在权威 skin/cap boundary 终止；phase9 保持只读，新产品进入新 schema/phase。

完整证据和 333 行审计：

```text
attachment/Faceted3D_v2_G1_G2_geometry_domain_closure_20260727.md
attachment/n8_taw_geometry_invalid_g1_audit_20260727.csv
```

### 13.3 当前下一入口

```text
NEXT = G3 implementation and focused validation
red/green case = ma8_a10_h40km
G4/12-case rerun = not started
Git closeout = not authorized
```

---

## 14. 2026-07-27 Comparison Contour 产品批次

用户在 G1/G2 后追加授权：误差图改用云图，并利用 projection cache 重跑 12 工况。

状态：

```text
product = *_phase10_comparison_contour_v3
12/12 validator PASS
12/12 projection cache hit
24/24 error PNG filled-contour pixel checks PASS
502 passed, 137 subtests passed
```

该批次只改变 comparison visualization：supported projected source coordinates 使用受 local mapping-support 约束的 filled triangular contour，unsupported/跨空隙 triangle mask，不再使用点状图。12/12 NPZ 与 phase9 逐字段一致，72/72 非误差 PNG 哈希一致。

此批次不关闭 geometry domain：

```text
G1 = PASS
G2 = PASS
G3 = NOT STARTED
phase10_comparison_contour_v3 != phase10_geometry_domain
NEXT = G3 implementation and focused validation
Git closeout = not authorized
```

