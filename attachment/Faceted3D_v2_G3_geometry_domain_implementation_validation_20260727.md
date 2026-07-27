# Faceted3D v2 - G3/G4 Geometry Domain Validation

> 日期：2026-07-27（Asia/Shanghai）  
> 代表工况：ma8_a10_h40km  
> 最终产品：runs/n8_taw_surface/*_phase13_geometry_domain_v4  
> 状态：G1=PASS，G2=PASS，G3=PASS，G4=PASS，UNKNOWN=0  
> 边界：未覆盖 phase9-phase11；未执行 Git stage/commit/push/merge/tag/release。

## 1. 实现闭包

### 1.1 Sheet classifier 与 sampler

- eligible STL triangle 先由无歧义质心 sampler 产生 seed，再按完整共享边 connected component 传播；
- 正式 STL 分类 other/upper/lower=513/3150/2678，unresolved=0；
- 75 个旧 unclassified eligible triangle 获得唯一 sheet；
- triangle 2169 是无 seed 的孤立 nose component，明确归为 other/cap exclusion；
- sampler 在 z 排序前按 triangle_sheet 过滤 requested sheet；
- G1 mismatch 点的 unfiltered upper/lower 均返回 lower triangle 4633；filtered upper=None、lower=4633。

### 1.2 Domain-conforming topology

- 原结构三角形与 requested-sheet graph-skin STL support 做二维裁剪；
- mixed boundary cell 插入精确 skin-boundary intersection node；
- exact physical cap tip 不生成 Taw node；
- 产品 node table 持有参数行列、legacy phase9 identity、domain role、source STL triangle/edge；
- triangle table 持有 triangle_node_ids、geometric sheet 与 source STL triangle；
- plotting 和 mapping support 使用同一 triangle_node_ids；
- topology schema=n8-taw-domain-topology/v1；
- summary schema=n8-taw-run-summary/v4；
- Taw dispatch 保持 n8-taw-dispatch/v3；
- continuous normal 保持 stl-angle-weighted-continuous-normal/v1。

### 1.3 v3 数值保护

完整 classifier 只负责产品域、requested-sheet 选择和新增边界节点；phase9 直接祖先节点继续使用 seed-only v3 normal adjacency。每工况 6309 个直接祖先节点在以下字段与 phase9 byte-exact：

~~~text
x_m, span_m, z_m, sx, sy,
incidence_s, stl_face_incidence_s,
normal_smoothing_angle_deg,
normal_out, stl_face_normal_out,
surface_class_code, surface_class,
Taw_windward_candidate_K,
Taw_recovery_candidate_K,
windward_blend_weight,
Taw_prediction_K, provider, valid
~~~

## 2. 产品域结果

每工况：

~~~text
nodes = 9663
  upper = 4675
  lower = 4988
triangles = 18110
skin-boundary nodes = 870
provider-valid nodes = 9663/9663
upper max y/b = 0.9939747629018159
lower max y/b = 0.993981562127428
topology sha256 = 1490f733d15e373ba017d503025b6bb0f4e558378e94e719e3f3a7b0c2b7acae
~~~

独立 legacy exclusion audit：

~~~text
degenerate_planform_chord = 162
outside_stl_support = 170
geometric_sheet_mismatch = 1
total = 333
~~~

333 个 phase9 点不再作为产品 node table 内部 invalid/mask；它们保留原 canonical identity、坐标、reason 和 typed domain classification。产品边界由显式 triangles 终止，不由 NaN mask 形成。

## 3. G3 代表工况验证

~~~text
product = ma8_a10_h40km_phase13_geometry_domain_v4_redgreen
runner = PASS
artifact validator = PASS
artifact inventory = exact 11
focused = 30 passed, 12 subtests passed
full pytest = 505 passed, 137 subtests passed
ruff = PASS
py_compile = PASS
git diff --check = PASS
upper/lower Taw PNG visual inspection = no interior hole or rectangular tip mask
~~~

phase12_geometry_domain_v4_redgreen 是隔离 v3 normal responsibility 前的诊断目录，不是当前产品。

## 4. G4 十二工况验证

~~~text
product = runs/n8_taw_surface/*_phase13_geometry_domain_v4
runs = 12
runner PASS = 12/12
validator PASS = 12/12
inventory = exact 11 artifacts/run
projection cache hit = 12/12
nodes/triangles = 9663/18110 per run
provider-valid = 9663/9663 per run
comparison supported upper/lower = 7276/8068 per run
topology unique hash = 1
phase9 direct-ancestor 18-field byte-exact = 12/12
legacy exclusions = 333/run
UNKNOWN = 0
~~~

## 5. 最终入口

~~~text
G1 = PASS
G2 = PASS
G3 = PASS
G4 = PASS
UNKNOWN = 0
current product = *_phase13_geometry_domain_v4
Git authorization = none
~~~