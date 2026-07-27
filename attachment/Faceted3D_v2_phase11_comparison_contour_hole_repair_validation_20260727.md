# Faceted3D v2 - Phase11 Comparison Contour Hole Repair Validation

> 日期：2026-07-27（Asia/Shanghai）  
> 产品：`runs/n8_taw_surface/*_phase11_comparison_contour_fixed_v3`  
> 状态：`PASS_12_OF_12`  
> 任务边界：修复 phase10 Fluent comparison 温差云图的大片空白并重跑 12 工况；不宣称 G3 geometry-domain closure 完成。

## 1. 问题与根因

phase10 的 `Taw_error_vs_fluent_upper/lower.png` 在 `x≈2.3-2.55 m` 附近出现从底边向上切入的大块空白。该区域不是物理域外，也不是接近零误差的白色色阶。

根因是绘图三角网格把两类不同语义混在了一起：

- 先把 comparison-unsupported 坐标放入 Delaunay 网格，再屏蔽所有接触 unsupported 顶点的三角形；
- 又把 source-to-target 的 local mapping support 半径误用成 source-to-source 的云图连边上限。

少量分散的 unsupported source rows 因此被放大成可见的大块缺口。

## 2. 修复

`_build_comparison_contour_mesh()` 现在：

- 仅使用 comparison-supported、数值有限且 support limit 有效的 Fluent 投影样本建网；
- 重合投影坐标仍只在绘图副本中聚合，NPZ source rows 不去重；
- 在 supported-sample convex hull 内使用 `tricontourf` 连续插值；
- unsupported rows 仍保留在 NPZ、failure reason 和统计合同中，不进入误差统计；
- 不再使用 mapping support 半径删除云图三角形边。

新增回归测试覆盖：中央整列样本 unsupported 时，三角网仍跨过该稀疏缺样带，不切出可见空洞。

## 3. 十二工况验收

```text
run directories = 12
validator PASS = 12/12
artifact inventory = exact 11 per run
projection cache hit = 12/12
NPZ arrays exact vs phase10 = 12/12
non-error PNG SHA-256 exact vs phase10 = 72/72
error PNG SHA-256 changed as expected = 24/24
no-bottom-notch checks = 24/24
full pytest = 502 passed, 137 subtests passed
```

无缺口检查直接识别坐标区背景色，并要求每个有云图的横向列覆盖到底边。它用旧 phase10 代表图作负对照：

```text
phase10 ma8_a10_h40km upper bottom-deficit columns = 105
phase11 24 error contours bottom-deficit columns = 0 each
```

同时对 24 张上/下表面温差云图总览进行了逐张肉眼检查，均无内部空白或从底边切入的缺口。

## 4. 边界

- phase9、phase10 均未覆盖、未删除；
- phase10 报告的像素验收未能识别大片缺口，已由本报告取代；
- 数值数组保持不变，本轮仅修复 comparison error PNG 的连续云图网格；
- 本轮不等同于 `phase10_geometry_domain_*`，G3 geometry-domain implementation 仍未完成；
- 未执行 Git stage/commit/push/merge/tag/release。
