# Faceted3D v2 - G1/G2 Geometry Domain Closure

> 日期：2026-07-27（Asia/Shanghai）  
> 基准：`runs/n8_taw_surface/*_phase9_continuous_normal_cached_v3`  
> 代表工况：`ma8_a10_h40km`  
> 状态：`G1=PASS`，`G2=PASS`，`UNKNOWN=0`  
> 边界：未修改源码、测试或 phase9 产物；未重跑工况；未执行 Git 动作。

## 1. G1 结论

### 1.1 十二工况几何身份

12 个 phase9 NPZ 的 333 个 geometry-invalid 点在以下字段上 byte-exact：

```text
canonical_index, geometric_sheet, x_over_c, y_over_b,
x_m, span_m, z_m, sx, sy, triangle_id,
geometry_valid, geometry_failure_reason, normal_out,
stl_face_normal_out, normal_smoothing_angle_deg
```

所选字段/invalid slice 的统一 SHA-256 为：

```text
8cd4750a3dfd42f8b3f0b4db2928f8322940740a0387a6a987c1f08bc2b23acb
```

因此昂贵几何审计只执行一次，其余 11 工况只做身份验证。完整 333 行代表几何审计见：

```text
attachment/n8_taw_geometry_invalid_g1_audit_20260727.csv
rows = 333
sha256 = 1bca5d933ebf892877260239b9836328ddbae80366f50e713c49c0c5d8a65a32
```

### 1.2 精确 index 集

每个 sheet 的 `outside_stl_support` 使用相同 grid 集：

```text
j=0..30: i=0
j=31:    i=0..1
j=32:    i=0..1
j=33:    i=0..2
j=34:    i=0..2
j=35:    i=0..3
j=36:    i=0..4
j=37:    i=0..5
j=38:    i=0..9
j=39:    i=0..18
```

共 85 点/sheet；upper canonical index 为 `j*81+i`，lower 为 `3321+j*81+i`。

退化 tip 行为：

```text
upper canonical = 3240..3320
lower canonical = 6561..6641
grid = j=40, i=0..80
y/b = 1
span = 1.031027 m
x = 3.5989941527510467..3.599 m
physical chord represented by 81 nodes = 5.8472489533e-6 m
```

唯一 mismatch：

```text
sheet/canonical/grid = upper / 2188 / (j=27, i=1)
x/c, y/b = 0.0125, 0.675
x, span = 2.092875772868064 m, 0.695943225 m
```

### 1.3 85 个 outside-support 点

按最近权威 outline 分段，每个 sheet 的分区为：

```text
nose=2, LE=83, TE=0, root=0, tip=0, other=0
```

其中：

- 40 点是各 `j=0..39` 的 `i=0` outline 边界点，没有命中任何 STL 投影三角形；
- 45 点命中两个圆钝前缘/侧盖投影三角形，但这些候选的最大 `|n_z|` 仅为 `0.08595301284438553..0.4479698426015874`，均低于 graph-skin 阈值 `0.45`；
- 没有一个点命中当前 eligible skin。

每个 sheet 的距离范围：

| 距离对象 | min (m) | max (m) | mean (m) |
|---|---:|---:|---:|
| 任意 STL projected support | 0 | 0.000800880577322733 | 0.000143003141076800 |
| 任意 eligible skin support | 0.000003865793612096 | 0.005945811206493847 | 0.002773732714920452 |
| 同 sheet graph-skin support | 0.000003865793612096 | 0.006392413959846023 | 0.003055378386736239 |
| outline boundary | 0 | 0.005711419156158161 | 0.001655360302767272 |

结论：`outside_stl_support` 混合了两种精确情况：outline/STL 投影边界最多约 `0.801 mm` 的不一致，以及位于 STL 投影内但不属于 upper/lower graph-skin 的圆钝 cap 区。它不是 tolerance 缺陷，不能靠放宽 `1e-12` 修复。

### 1.4 upper mismatch 路径

该点命中两个投影候选：

| triangle | z (m) | `|n_z|` | classifier |
|---:|---:|---:|---|
| 2184 | 0.01956713069035 | 0.4242414211375845 | other/cap |
| 4633 | -0.01811083021289 | 0.5534742755728491 | lower |

当前 sampler 先按 `|n_z|>=0.45` 排除 triangle 2184，再把唯一剩余的 lower triangle 4633 同时作为 upper 和 lower 返回；调用方随后才发现 upper sheet mismatch。triangle 2184 的 edge neighbors 2185、2187 已分类 upper，triangle 4633 的 edge neighbors 4566、4645 已分类 lower，4632 则仍为 invalid。

这证明：

1. 该 upper 点位于 cap/upper-skin 边界外，是可解释的 graph-skin domain exclusion；
2. `geometric_sheet_mismatch` 这个运行时路径本身是 sampler 缺少 requested-sheet prefilter 的缺陷；
3. 当前 triangle classifier 还有 76 个 `|n_z|>=0.45` 三角形被标为 invalid，不能直接充当完整产品域 authority。

### 1.5 tip authority

outline tip 为 `(x,span)=(3.599,1.031027) m`，最近 STL tip vertex 为 `(3.6,1.031027,~0) m`，相差 `1 mm`。STL tip 只命中 triangle 1964/5740；二者均为 cap/other，`|n_z|` 分别为 `0.08595301284438553` 和 `0.08588171037693319`，正式 sampler 对 outline tip 和 STL tip 都返回 `(None,None)`。

所以精确物理 tip 不属于当前 upper/lower graph-skin Taw 域。81 点 tip 行既不是 81 个物理点，也不能折叠后伪造一个 graph-skin Taw 顶点。

### 1.6 分类闭包

- 点的物理身份：cap、outline/STL 边界外和精确 tip 均是有依据的 graph-skin domain exclusion；
- 产品表达缺陷：矩形 81x41 域把 exclusion 留作内部 invalid/mask，制造假孔洞；
- sampler 缺陷：upper/lower 选择前没有按 sheet 过滤，形成唯一 mismatch；
- tip 拓扑缺陷：每 sheet 用 81 个节点表达一个退化/域外端部；
- `UNKNOWN=0`。v3 合同已经指定 STL face 持有 position、support、triangle identity 和 sheet audit authority；outline 只能作为采样种子和诊断参考。

## 2. G2 产品域方案

### 2.1 域 authority

新产品域定义为：

```text
authoritative geometry = STL
product domain = sheet-specific graph-skin triangle support
excluded domain = nose/LE cap, side/cap faces, exact physical tip outside graph-skin
outline role = row/parameter seed and audit reference only
```

不扩大 tolerance，不把 cap 值借给 upper/lower，不跨 sheet 借值，不做 nearest fill 或无依据外推。

### 2.2 sheet classifier 与 sampler

1. 先在 eligible skin 三角形上建立 edge adjacency；
2. 用能明确同时看到 upper/lower 的内部 sampler 结果作为 seed；
3. 在同一 eligible connected component 内传播 sheet identity；
4. 冲突、未覆盖 component 或跨 cap 传播一律 fail closed；
5. sampler 必须先按 requested sheet 过滤候选，再做 z 排序；一个 triangle 不得同时满足 upper/lower；
6. G3 必须证明当前 76 个 eligible/unclassified triangle 全部被唯一分类或有精确 exclusion。

### 2.3 tip 与边界拓扑裁决

两种原始候选都被 G1 证据否决：

- 直接删除 `y/b=1` 行会把产品截断在 `y/b=0.975`，损失 `25.775675 mm` 半展长；
- 折叠到 outline/STL exact tip 会跨入 cap 域，而 exact tip 没有 graph-skin normal/Taw。

采用第三种、域一致的方案：

```text
clip the structured sampling mesh to each sheet's authoritative graph-skin support;
insert exact skin-boundary intersection nodes;
terminate topology on the skin/cap boundary;
do not create a Taw node at the physical cap tip.
```

这等价于删除退化矩形行并重建端部 connectivity，但终止位置由 sheet graph-skin 边界决定，而不是武断停在 `y/b=0.975` 或折叠到域外 tip。边界 triangle 必须引用权威 STL triangle/edge identity。

### 2.4 canonical identity 与 NPZ v4

固定 `sheet_offset+j*81+i` 只保留为 phase9 legacy provenance，不再充当新拓扑 identity。新 schema 使用显式 node/triangle 表：

```text
node_id
geometric_sheet
x_m, span_m, z_m
parameter_row, parameter_column
legacy_phase9_canonical_index  # 无直接祖先时为 -1
domain_role                    # interior | skin_boundary
source_stl_triangle_id / source_stl_edge_id
provider/normal/Taw fields

triangle_id
triangle_node_ids[M,3]
triangle_geometric_sheet
source_stl_triangle_id
```

另序列化 exclusion audit 表，保留 phase9 的 333 点身份、原因、距离和 G1 分类。summary/dispatch/normal v3 数值合同保持，产品 summary/NPZ topology schema 升级为新版本；phase9 不覆盖。

### 2.5 plotting 与 mapping

- plotting 只消费显式 `triangle_node_ids`，继续使用 flat triangle color；不再 `reshape(41,81)`，也不靠 invalid vertex mask 形成边界；
- mapping target pool 只包含新域节点，并只沿同 sheet 显式 triangles 计算 local support；
- 落在 cap/产品域外的 Fluent source row 使用新的 typed reason，例如 `MAPPING_OUTSIDE_PRODUCT_DOMAIN`，不得混入一般数值失败；
- projection cache 的 Fluent-to-STL canonical geometry 身份不变；LF target topology hash 必须新增并进入 validator/summary。

### 2.6 G3/G4 验收门

G3 必须先在 `ma8_a10_h40km` 建立新目录并覆盖：

```text
sheet classifier complete and conflict-free
requested-sheet sampler isolation
tip/cap boundary topology
no unexplained included node
no interior hole
triangle/plot/mapping consistency
phase9 v3 provider/continuous-normal/cache regression
```

随后 G4 才能新建 12 个 `*_phase10_geometry_domain_*` 产品目录。成功条件是显式域边界和完整拓扑，不是把 NaN 改成常数，也不是强求历史 invalid 数量为零。

## 3. 下一入口

```text
G1 = PASS
G2 = PASS
UNKNOWN = 0
next = G3 implementation and focused validation
authorization still absent = Git stage/commit/push/merge/tag/release
```
---

## 4. 2026-07-28 最终闭包回传（supersede 第 3 节）

本节覆盖第 3 节的旧入口和旧授权状态。G1/G2 方案已经完成实现并通过十二工况验收：

```text
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
inventory = exact 13/run
projection cache = 12/12 hit
nodes/triangles = 9663/18110 per run
provider-valid = 9663/9663 per run
legacy exclusion audit = 333/run
full tests = 508 passed, 137 subtests passed
Git closeout authorization = granted by user on 2026-07-28
```

每个产品目录的四张误差图包括原有 upper/lower 固定 `±10%` 图，以及 upper/lower 按该表面实际最小值、最大值自动定界的误差图。固定范围图便于跨工况比较，自动范围图用于显示完整极值；二者并存，不互相替代。

代表工况 `ma8_a10_h40km` 在 projection cache hit 条件下，包含 Python 启动、完整计算、13 个 PNG/NPZ/JSON 产物写出及 validator 的端到端墙钟时间为 `18.702 s`。该数值不是 projection cache miss 的冷启动基准。

本次源码净增一项正式 production source；Git 收口必须在实现提交后执行 current-v5 的 source-only identity migration，并再次通过 official current regression。该迁移只允许更新两个 manifest 的 `source_identity` 与 `source_hashes_sha256`，不得 freeze 或改写数值基线。
