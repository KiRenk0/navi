> **已取代（2026-07-27）**：本报告的像素验收漏检了温差云图中的大片空白，phase10 产品不再视为最终合格结果。修复与重新验收见 `Faceted3D_v2_phase11_comparison_contour_hole_repair_validation_20260727.md`。

# Faceted3D v2 - Phase10 Comparison Contour Validation

> 日期：2026-07-27（Asia/Shanghai）  
> 产品：`runs/n8_taw_surface/*_phase10_comparison_contour_v3`  
> 状态：`PASS_12_OF_12`  
> 任务边界：只改变 Fluent comparison error PNG 的渲染方式并重跑 12 工况；不宣称 G3 geometry-domain closure 完成。

## 1. 实现

`Taw_error_vs_fluent_upper/lower.png` 从 source-row scatter 改为 filled triangular contour：

- 在绘图副本中按 projected `(x,span)` 合并完全重合的坐标，原 NPZ source rows 不去重；
- 使用 Delaunay triangles 和 `tricontourf`；
- 三角形必须三个顶点均 comparison-supported；
- 每条边必须满足两端 local mapping-support 半径相交；
- unsupported 或跨空隙 triangle 被 mask，图中不再绘制点状 marker；
- 色标仍为 case spec 的 signed relative error limit，方向仍为 `prediction-observation`。

summary 新增 `contracts.comparison_rendering`，现有 summary/dispatch/normal schema 不变。

## 2. 测试

```text
N8 focused = 22 passed, 12 subtests passed
full pytest = 502 passed, 137 subtests passed
```

新增测试覆盖：

- 重合 projected coordinate 的仅绘图聚合；
- local support 不相交时不跨空隙连三角形；
- unsupported vertex 不进入可见 triangle；
- filled-contour PNG smoke test。

## 3. 十二工况产品验收

```text
run directories = 12
validator PASS = 12/12
artifact inventory = exact 11 per run
projection cache hit = 12/12
comparison contour PNG pixel checks = 24/24
```

与 phase9 对照：

```text
NPZ arrays exact by key/value = 12/12
non-error PNG SHA-256 exact = 72/72
error PNG SHA-256 changed as expected = 24/24
```

24 张误差图均通过连续填色检查：彩色区域占比大于 10%，连续色带和覆盖行数均远高于点状图阈值。

本轮批量命令显式传入了 case label altitude，同时仍由显式 `T_inf_K/p_inf_Pa` 提供 freestream。因此 `Taw_error_stats.json` 相比 phase9 只有 `altitude_input_m: null -> case altitude` 的 provenance 差异；`altitude_used_for_freestream=false`，NPZ 数值逐字段不变。

## 4. 边界与下一入口

- phase9 未覆盖、未删除；
- `phase10_comparison_contour_v3` 不是 `phase10_geometry_domain_*`；
- G1/G2 结论不变，G3 geometry-domain implementation 仍未开始；
- 未执行 Git stage/commit/push/merge/tag/release。
