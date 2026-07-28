# N8 跨工况共同几何误差分区：方法框架

## 1. 文档目的

本文档定义 N8 飞行器表面跨工况共同几何误差分析与自动分区的第一版方法框架。本文档只冻结研究问题、数据合同、统计方法、分区方法、稳定性检验、权重语义、输出合同和后续工况接入规则，不记录尚未重新计算的数值结论。

后续实现应以本文档为设计依据，并满足以下原则：

- 所有数值均从正式 `runs/n8_taw_surface/*_phase13_geometry_domain_v4` 产物重新计算；
- 不从 PNG 或既有报告反推数值；
- upper 和 lower 分开建模；
- 工况是跨工况验证的基本单位；
- canonical node 是同一工况内部的空间离散位置，不是独立工况样本；
- 分区方法必须允许最终选择不额外分区，即 `K=1`；
- 分区必须连续、少量、可解释，并明确边界不确定性；
- 新增工况后必须能够确定性全量重算。

### 1.1 历史 12 工况的证据资格

现有 12 个 N8 工况全部保留，不删除、不重跑。它们使用各 run 中显式记录的自定义 `T_inf/p_inf`，显式温压对按合同优先于名义高度，因此没有调用本次修正后的 USSA1976。对这些工况应作如下限定：

- 每个工况内部的 prediction、Fluent observation、mapping 和 signed error 仍是同一精确输入下的有效比较；
- 固定几何、固定 canonical node 对应关系和跨工况重复空间结构仍可作为共同几何误差分区的初步证据；
- 它们不能验证标准大气实现，也不能支持高度、Mach、攻角或其他来流变量的物理因果结论；
- 旧来流参数可能改变误差幅值，甚至改变部分空间模式，因此当前分区只能称为初步工程分区；
- 后续修正 USSA 的新工况必须使用独立 provenance 标识，与这 12 个 `legacy_explicit_custom` 工况分层报告；
- 增加新工况后应使用全部合格工况全量重算共同模态、分区和 LOO 稳定性，不冻结旧边界。

未来运行必须冻结实际送入预测器和 Fluent 的同一组 `T_inf_K`、`p_inf_Pa` 和由约定状态方程得到的 `rho_inf_kg_m3`，并记录其来源、USSA 版本和输入几何高度。不得让两个求解端各自独立重算来流后再假定它们相同。
## 2. 研究问题

误差定义为：

```text
signed_error_K = Taw_prediction_K - wall_temperature_K
signed_relative_error_pct = 100 * signed_error_K / wall_temperature_K
```

本分析不尝试解释高度、Mach、攻角、来流温度或压力的因果作用，只回答以下问题：

1. 12 个工况的误差场是否共享主要空间形状？
2. 工况差异是否主要表现为整体偏移和共同形状的放大或缩小？
3. 去除共同形状后，是否仍存在跨工况重复出现、具有不同统计性质的连续几何区域？
4. 与不分区及仅区分 upper/lower 相比，自动区域是否提供稳定增量？
5. 区域和边界对删除单个工况、统计权重和网格离散方式是否稳定？
6. 当前证据是否足以支持残差学习原型，以及应使用什么目标域和权重？

## 3. 当前数据结构

### 3.1 固定 canonical mesh

当前 12 个工况共享同一 canonical mesh。正式分析脚本必须再次验证：

- `node_id` 完全一致；
- `geometric_sheet` 完全一致；
- 三维坐标完全一致；
- `x_over_c`、`y_over_b` 完全一致；
- `triangle_node_ids` 和 `triangle_geometric_sheet` 完全一致；
- topology schema 和 topology hash 一致。

若任一项不一致，脚本应停止并报告差异，不得按数组行号勉强拼接。

### 3.2 固定误差节点集合

当前数值检查表明：

```text
upper：12 个工况均为完全相同的 2120 个有效 unique target nodes
lower：12 个工况均为完全相同的 2232 个有效 unique target nodes
```

因此当前应直接构造：

```text
Y_upper.shape = (12, 2120)
Y_lower.shape = (12, 2232)
```

矩阵的每一行是一个工况，每一列是固定的同一个 `target_canonical_index`。列必须按 canonical node ID 升序排列，并保存 node ID 到矩阵列号的显式映射。

所谓“共同节点交集”在当前数据中只是一项输入检查，没有删除任何节点：每个工况的有效节点集合、它们的交集和并集完全相同。

### 3.3 全网格与误差支持域

完整 canonical mesh 的节点多于具有配对 Fluent observation 的 target nodes。prediction 可能存在于更大的网格范围，但只有同时具有以下条件的节点才能直接形成误差观测：

- mapping supported；
- `comparison_valid=true`；
- prediction 有限；
- Fluent observation 有限；
- error 和 relative error 有限。

最终输出必须区分：

- `geometry_node`：完整 canonical 几何节点；
- `error_supported_node`：具有有效配对误差的节点；
- `partition_inference_node`：实际参与分区估计的节点；
- `extrapolated_node`：若未来确有需要，由模型从支持域扩展标签的节点。

不得将外推节点与直接受数据支持的节点混为一谈。第一版主结论只针对固定的误差支持域。

## 4. 输入合同与独立复算

每个工况、每个 sheet 都应独立完成以下审计：

1. 从 prediction 和 observation 重新计算 signed error；
2. 重新计算 signed relative error；
3. 与 NPZ 序列化数组逐项比较；
4. 使用 `source_row_index` 回查原始 Fluent CSV observation；
5. 验证 mapping failure reason 和 comparison-valid mask；
6. 检查 target index 范围和 sheet 一致性；
7. 检查 many-to-one multiplicity；
8. 检查同一 target 的重复 source rows 是否具有相同 prediction；
9. 记录同一 target 内 Fluent observation 的离散程度；
10. 记录全部输入文件路径、大小和 SHA-256。

只要任一关键合同未闭合，该工况不得静默进入共同模式或分区计算。

## 5. source-row 到 target-node 的聚合

对一个工况和一个 sheet，令 source row `i` 映射到 canonical target node `n(i)`。在 target node 上构造：

```text
node_error(case, node) = 该 target 对应全部有效 source-row error 的平均值
node_observation(case, node) = 对应全部有效 source-row observation 的平均值
multiplicity(case, node) = 映射到该 target 的有效 source-row 数量
```

如果 source CSV 含有物理面积或可信度字段，应优先使用面积守恒或精度加权聚合；若没有，则简单平均是透明的默认值，并将 target 内 observation 方差作为聚合不确定性诊断。

必须保留 source-row 级数组，以便复现正式 source-row 统计；但共同几何模式和面向 target-node 的残差学习不应把重复 source rows 当成独立几何节点。

## 6. 权重体系

### 6.1 `area_target`：建议的主几何权重

从三角网格坐标计算每个 triangle 的物理面积，并将每个非退化三角形面积的三分之一分配给三个顶点，得到 barycentric lumped node area：

```text
a_node = sum(area_triangle / 3 for adjacent triangles)
```

在每个 sheet 和误差支持域内归一化：

```text
w_area(node) = a_node / sum(a_node)
```

它使离散损失近似曲面上的积分误差，避免高密度网格区域仅因节点多而获得更大权重。已知网格含极少数退化或近退化三角形；正式实现必须设置明确的面积容差、排除退化面积贡献并输出审计记录。

### 6.2 `unique_target`：节点等权敏感性

```text
w_unique(case, node) = 1
```

它回答“如果未来模型在每个 canonical target node 上等权训练，结论如何”。

### 6.3 `source_row`：正式采样分布敏感性

```text
w_source(case, node) = multiplicity(case, node)
```

该权重必须逐工况使用，不能先对 12 个工况取 multiplicity 中位数或平均值。它回答“如果目标是复现当前 Fluent source-row 分布，结果如何”。

### 6.4 `inverse_multiplicity`：压力测试

```text
w_inverse(case, node) = 1 / multiplicity(case, node)
```

这不是默认物理权重，而是刻意压低高复用 target 的敏感性诊断。报告不得把它描述为天然正确的无偏权重。

### 6.5 权重结论的解释

- 面向曲面整体误差积分：优先 `area_target`；
- 面向 canonical node 等权训练：使用 `unique_target`；
- 面向现有 Fluent source-row 分布：使用 `source_row`；
- 检查 many-to-one 是否支配结论：加入 `inverse_multiplicity`。

若不同权重得到不同共同模式或边界，必须报告这种差异，不能选择其中最符合预期的一种作为唯一结果。

## 7. 共同空间形状检验

upper 和 lower 完全分开进行以下计算。

### 7.1 原始量级模型

首先拟合：

```text
Y(case,node) ≈ offset(case) + scale(case) * pattern(node)
```

该分支保留真实 K 量级，回答共同模式能够解释多少原始误差变化。

在固定节点权重下，平方损失版本可转化为加权 rank-1 SVD。若使用逐工况不同的 `source_row` 权重，则不能用一个跨工况中位权重代替，应使用显式加权交替最小二乘或其他真正优化逐项加权损失的方法。

### 7.2 标准化形状模型

为避免高误差工况仅凭幅值控制共同形状，另建标准化分支：

```text
robust_offset(case) = 加权中位数或 Huber location
robust_scale(case) = 加权 MAD 或其他稳健尺度
Z(case,node) = (Y(case,node) - robust_offset(case)) / robust_scale(case)
```

随后拟合：

```text
Z(case,node) ≈ score(case) * standardized_pattern(node)
```

标准化分支回答“只比较空间形状时，各工况是否相似”。原始分支和标准化分支必须同时报告，不能用其中一个替代另一个。

### 7.3 模态符号约定

PCA/SVD 模态的正负号在数学上不唯一。为保证确定性复跑，应使用明确符号规则，例如：

1. 找到绝对值最大的 pattern coefficient；
2. 强制该 coefficient 为正；
3. LOO 模态与 full-fit 模态按加权相关系数对齐符号。

不得使用接近机器误差的均值相关性决定符号。

### 7.4 输出指标

每种 sheet 和权重至少输出：

- raw PC1 explained fraction；
- standardized PC1 explained fraction；
- PC2 的增量解释率；
- 工况两两加权相关系数；
- 每个工况的 offset、scale/score；
- 每个工况的 rank-1 R2 和 RMSE；
- 每个工况与共同模式的相关系数；
- LOO 模态与 full-fit 模态的加权 cosine similarity；
- 删除每个工况后 PC1 解释率变化；
- 偏离共同模式最明显的工况及其空间残差图。

相关系数在每个工况仅乘正尺度时不会变化，因此“中心化相关”和“标准化相关”若数学上相同，不应伪装成两个独立证据。

### 7.5 对共同形状假设的判断

不设置机械的统计显著性结论。采用多证据描述：

- PC1 是否占主导；
- 大多数工况的 rank-1 重构是否良好；
- 工况间相关是否普遍为正且较高；
- LOO common pattern 是否稳定；
- 是否存在少数明确偏离工况；
- area、unique 和 source-row 权重下结论是否一致。

12 个工况只支持初步定性判断，不支持把节点数当作重复数进行显著性推断。

## 8. 分区所用节点特征

分区应主要识别“共同误差统计结构”，而不是单个恶劣工况的绝对幅值。

### 8.1 主特征集

对每个 node 构造：

```text
F1 = standardized common pattern
F2 = 跨工况标准化误差中位数
F3 = 跨工况标准化误差 MAD
F4 = rank-1 residual RMS
F5 = 误差或残差符号一致率
```

所有特征使用稳健尺度标准化。若某一特征几乎为常数，应自动剔除并记录。

### 8.2 直接 residual-profile 敏感性

另做一个低优先级对照：

```text
F_direct(node) = [common_pattern(node), residual(case_1,node), ..., residual(case_C,node)]
```

它能保留摘要统计可能丢失的工况特异结构，但特征维度会随工况数变化，因此只作为敏感性分析，不作为第一版唯一方法。

### 8.3 坐标的作用

`x_over_c`、`y_over_b` 和三维坐标用于：

- 构造和验证网格拓扑；
- 计算面积和几何边权；
- 绘图；
- 描述区域几何范围；
- 计算边界距离。

坐标不应直接作为普通聚类特征，否则算法可能仅因距离产生人为几何切片。

## 9. 连续图分区

### 9.1 邻接图

对 upper/lower 分别从 `triangle_node_ids` 构造无向邻接图。正式实现必须检查：

- 自环；
- 重复边；
- 退化 triangle；
- 孤立节点；
- 图连通分量数量；
- 每条边的三维长度；
- 每个节点的面积权重。

### 9.2 主方法：多特征 graph TV / group fused lasso

令 `F_node` 为节点特征，`M_node` 为图上去噪后的区域参数，求解类似：

```text
min_M
    0.5 * sum_node w_node * ||F_node - M_node||^2
    + lambda * sum_edge edge_weight * ||M_i - M_j||_2
```

第一项保持区域参数接近观测特征，第二项促使相邻节点融合。`lambda` 较大时所有节点可融合成一个区域，因此该方法天然允许 `K=1`。

第一版不得把“普通 primal edge length 权重”直接解释为严格连续曲面边界长度。应比较：

- topology-only graph fusion；
- 经过节点面积或局部尺度归一化的 graph fusion；
- 有文献和离散推导支持的 geometry-aware surface TV。

主结论只有在合理离散方式下保持一致时才可靠。

### 9.3 区域提取

对完整 `lambda` 路径求解。相邻节点的 `M` 在求解器数值容差内相同时视为融合，融合边构成的连通分量即为区域。

数值融合容差必须与以下量关联：

- 特征标准化尺度；
- ADMM 或优化器 primal/dual residual；
- 求解器停止容差。

不能随意写死一个与数据尺度无关的阈值。

### 9.4 连续性和碎片控制

每个区域必须在当前 sheet 图上连通。另设以下工程约束：

- 最小节点数；
- 最小曲面面积比例；
- 小区域是否在不同 LOO 中复现；
- 是否仅位于退化网格或低支持位置；
- 是否能带来跨工况稳定收益。

最小面积阈值应做敏感性比较，例如 2%、5% 和 10%，不能仅凭一个阈值决定结论。

## 10. 为什么当前不使用 PointNet 或图神经网络

### 10.1 图正则化不是图神经网络

本项目会使用 canonical mesh 的邻接图，但用途是定义透明的 graph TV / fused-lasso 正则项。该方法没有需要从大量样本训练的网络参数，每一项损失和每条边界都可以审计。

图神经网络则需要从多个训练样本中学习消息传递权重。当前只有 12 个工况，虽然每个工况有数千节点，但这些节点不是数千个独立几何样本；它们属于同一张固定网格上的一个相关空间场。把节点当成网络训练样本会严重夸大有效样本量。

### 10.2 PointNet 当前没有解决额外问题

PointNet/PointNet++ 的主要价值包括：

- 处理无固定对应关系的点云；
- 对点顺序保持不变性；
- 从大量不同形状或不同采样点云中学习几何表示。

本项目的几何固定、canonical node ID 固定、三角邻接已知，且工况间节点一一对应。PointNet 为“不知道点如何对应”而设计的主要能力在这里没有用途，反而会丢掉已经明确拥有的网格拓扑信息。

### 10.3 GNN 当前的风险

在 12 个工况下训练 GNN，主要风险是：

- 参数量相对工况数过大；
- 很容易记住当前 12 个误差场；
- 不能可靠区分共同几何结构与工况特异噪声；
- LOO 只有 11 个训练工况，超参数选择非常不稳定；
- 区域边界难以解释为明确的统计目标；
- 权重、many-to-one 和曲面积分语义更难审计；
- 不能自然回答 `K=1` 是否优于多区域；
- 网络性能提升未必意味着区域是真实稳定结构。

因此当前采用 PCA/稳健低秩分解加 graph TV，不是因为不用图，而是因为固定图上的统计优化已经直接解决了问题，且更适合小样本。

### 10.4 何时重新考虑 GNN

只有出现以下一种或多种条件时，才重新评估 GNN：

- 已有数百到数千个相互独立的工况；
- 几何形状会变化，canonical node correspondence 不再固定；
- 需要把一个几何上的知识迁移到另一种几何；
- 需要从局部流场、法向、曲率和邻域变量联合预测完整残差场；
- 有独立测试几何或独立工况族可验证泛化；
- 简单低秩加图方法留下稳定、非线性且可重复的残差结构；
- 能明确说明 GNN 相比固定图统计方法多解决了哪个可验证问题。

即使未来使用 GNN，本框架的 area-weighted baseline、LOO/组级验证、权重敏感性和边界稳定性仍应保留，作为神经网络必须超过的基线。

## 11. 基线和模型比较

至少比较以下表示：

```text
M0：全表面不分区，仅每工况一个整体 offset
M1：仅 upper/lower，每工况每个 sheet 一个 offset
M2：每个 sheet 的 offset + scale * common_pattern
M3：M2 + 自动区域 residual intercept
```

M3 的区域来自训练工况，不得使用留出工况重新定义边界。

对留出工况，如果使用它自身的数据估计 offset、scale 和区域 residual intercept，则衡量的是：

```text
给定已学区域后，该区域表示对新工况误差场的压缩或表示能力
```

这不是对未知工况误差的真正预测。只有未来使用工况输入或其他可用特征预测这些参数时，才能报告 predictive performance。

比较指标至少包括：

- equal-case weighted SSE；
- weighted RMSE；
- weighted MAE；
- 相对 M2 的误差下降；
- 改善工况数量；
- 最差工况改善或退化；
- 区域参数数量；
- 区域面积和连续性。

## 12. 区域数与正则化参数选择

不直接搜索并强制 `K=2,3,4`。主搜索变量是 graph-TV 的 `lambda`，区域数由融合路径自然产生。

选择规则：

1. 搜索路径必须包含全部融合的 `K=1`；
2. 每个候选在 LOO 中从头重拟合；
3. 只有相对 M2 在多数留出工况中产生非微小改善的候选才保留；
4. 改善不能由一个极端工况单独驱动；
5. 区域面积必须满足最低要求；
6. 区域内部和边界必须具有足够稳定性；
7. 在性能统计不易区分时选择更大的 `lambda` 和更少的区域；
8. 若没有候选可靠超过 `K=1`，最终结论必须是不建议额外分区。

“多数工况”和“非微小改善”的具体阈值必须在运行前写入配置并做敏感性报告，不能看完结果后调整。

## 13. Leave-one-case-out 稳定性

对每个 sheet、每个主要权重口径执行 12 次 LOO。第 `c` 次删除整个工况 `c`，使用剩余 11 个工况重新完成：

1. target 聚合；
2. offset/scale；
3. common pattern；
4. 节点特征；
5. graph-TV 路径；
6. lambda/区域数选择；
7. 区域标签；
8. 边界集合。

不得只在 full-fit 分区固定后重新计算区域统计。

### 13.1 区域级指标

- adjusted Rand index；
- variation of information；
- 最优标签匹配后的节点一致率；
- 每个区域的 Jaccard；
- 每个区域的面积变化；
- 区域连通性变化。

### 13.2 边界级指标

- exact cut-edge Jaccard；
- 允许一层或两层网格邻域偏移的 boundary precision/recall/F1；
- boundary geodesic distance；
- 每条 edge 的 LOO cut frequency；
- 每个 node 成为边界邻接节点的频率。

ARI 很高而 exact boundary Jaccard 较低，通常表示大区域内部稳定但边界在一个窄带内移动。报告应将其解释为 provisional boundary band，而不是精确边界。

### 13.3 稳定性分类

建议输出以下标签，但阈值必须在配置中明确：

- `stable_interior`：在绝大多数 LOO 中保持同一区域内部；
- `stable_boundary`：cut edge 在绝大多数 LOO 中复现；
- `provisional_boundary`：边界在连续窄带内移动；
- `case_driven_anomaly`：主要由一个或少数工况决定；
- `low_support`：数据或网格证据不足。

## 14. 权重和采样机制敏感性

对主分区至少执行以下比较：

- `area_target` vs `unique_target`；
- `area_target` vs `source_row`；
- `area_target` vs `inverse_multiplicity`；
- 区域标签 ARI；
- 区域面积变化；
- exact 和 tolerance-aware boundary similarity；
- common-pattern correlation；
- PC1 解释率变化。

另做伪边界诊断，将以下非误差特征与主边界比较：

- multiplicity；
- 节点面积；
- 局部网格密度；
- pairing distance；
- mapping support radius 或距离；
- target 内 source-row observation dispersion。

若自动边界与采样密度或 pairing distance 边界高度重合，应优先解释为采样或映射机制敏感性，而不是共同物理误差区域。

## 15. 区域统计

最终每个 `case × sheet × region × weighting` 至少输出：

- source-row N；
- unique-target N；
- 权重和；
- 几何面积；
- mean error；
- variance；
- standard deviation；
- MAE；
- RMSE；
- skewness；
- p05、p25、p50、p75、p95；
- positive、negative、zero fraction；
- mean signed relative error；
- mean absolute relative error；
- rank-1 residual 的相同统计。

跨工况汇总必须先在每个工况内计算，再对 12 个工况等权汇总。不得把所有节点和工况摊平后用空间点数量制造虚假精度。

## 16. 图像输出

至少生成：

1. upper/lower observation-support map；
2. raw common spatial pattern；
3. standardized common spatial pattern；
4. 每工况 offset 和 scale；
5. 每工况 rank-1 R2 和 RMSE；
6. 偏离共同模式工况的 residual map；
7. lambda 路径上的区域数、LOO 收益和稳定性；
8. 最终 upper/lower 区域图；
9. stable/provisional boundary map；
10. LOO cut-edge frequency map；
11. 权重敏感性分区对比；
12. multiplicity、面积和 pairing-distance 伪边界诊断图；
13. 不分区、sheet-only、common-mode 和自动区域模型对比图。

图中必须区分直接受误差数据支持的节点与任何外推节点。

## 17. 新增工况自动接入

新增 `*_phase13_geometry_domain_v4` run 后：

1. 扫描全部正式 run；
2. 按 case ID 确定性排序；
3. 验证 topology；
4. 验证 upper/lower target node 集合；
5. 若集合与当前固定集合一致，误差矩阵增加一行；
6. 若集合不一致，停止并生成 node-set difference 报告；
7. 从全部工况重新计算共同模式；
8. 重新计算 graph-TV 路径和区域选择；
9. 重新执行 LOO；
10. 比较本次与上次数据版本的模式和边界；
11. 写入新的输入哈希和输出哈希。

不采用增量拼接旧 PCA 或冻结旧分区，因为新工况可能推翻当前共同模式。旧结果应保留为独立的数据版本，以便审计分区如何随工况增加而变化。

当工况数明显增加后，可在 LOO 之外加入 case-level bootstrap 或 repeated grouped cross-validation，但仍不得对节点做普通独立 bootstrap。

## 18. 决策门槛

分析按以下顺序做决定：

### Gate A：输入是否可比

只有 topology、node mapping、误差公式和 mask 合同全部闭合，才进入共同模式分析。

### Gate B：共同形状是否存在

综合 PC1、case-level rank-1 fit、pairwise correlation 和 LOO mode stability 判断。若共同模式不稳定，则停止自动共同分区，转而报告工况特异误差场。

### Gate C：共同模式后是否仍值得分区

只有 graph-TV 区域相对 common-mode baseline 在多数工况中提供稳定增量，才接受 `K>1`。

### Gate D：边界是否可定位

若区域存在但 exact boundary 不稳定，则输出稳定区域和 provisional boundary band，不输出一条被描述为精确物理边界的曲线。

### Gate E：是否可启动残差学习

若共同模式、区域统计和权重敏感性均可接受，可启动 target-node residual-learning 原型。原型主损失使用 area 或明确的 target-node 权重，并并行报告 unique-target 与 source-row 指标。

## 19. 输出文件合同

后续实现至少生成：

```text
analyze_common_geometry_partition.py
report.md
analysis_config.json
input_contract_audit.csv
input_asset_manifest.csv
common_shape_case_metrics.csv
case_pairwise_spatial_correlations.csv
common_pattern_nodes.csv
common_pattern_fields.npz
partition_path_metrics.csv
canonical_node_partition.csv
canonical_node_partition.npz
region_case_statistics.csv
region_summary.csv
leave_one_case_out_metrics.csv
boundary_stability.csv
weighting_sensitivity.csv
sampling_mechanism_diagnostics.csv
model_comparison.csv
reproducibility.json
artifact_manifest.json
figures/*.png
```

所有 CSV 行序、JSON key、NPZ member 顺序和图像生成参数应确定。审计文件不写运行时钟、临时目录或其他每次变化的非确定字段。

## 20. 最终报告必须直接回答

1. 当前工况是否显示共同几何误差分布？
2. offset + scale × common pattern 成立到什么程度？
3. 哪些工况偏离共同模式？
4. upper/lower 是否必须分别建模？
5. 数据是否支持 `K>1`？若支持，建议每个 sheet 几个区域？
6. 每个区域的几何范围、面积和误差特征是什么？
7. 哪些区域内部稳定？
8. 哪些边界稳定，哪些只是 provisional band？
9. 哪些局部结构由个别工况驱动？
10. source-row、unique-target、area 和 inverse-multiplicity 是否改变结论？
11. 采样密度或 mapping 是否可能制造边界？
12. 当前工况数是否足以支持初步定性分区？
13. 新增什么类型的工况最可能检验或推翻当前分区？
14. 是否足以启动残差学习原型？
15. 为什么当前没有使用 PointNet 或 GNN，以及将来何时重新评估？

## 21. 第一版实施顺序

建议按以下顺序实现，避免一次写成不可审计的大脚本：

1. 输入、公式、mask、node-set 和 topology 审计；
2. source-row 到 target-node 聚合及四种权重；
3. triangle/node area 和图拓扑审计；
4. raw 与 standardized common-shape 分析；
5. LOO common-pattern 稳定性；
6. 分区特征生成；
7. graph-TV 求解与完整 lambda 路径；
8. `K=1` 在内的模型比较；
9. LOO 全流程重拟合；
10. 边界带、权重和采样机制敏感性；
11. 区域统计和图像；
12. 独立数值复核、确定性复跑和哈希清单；
13. 最终报告。

本框架的核心逻辑是：

```text
先验证误差数据可以逐节点跨工况比较
-> 再检验共同空间形状
-> 再检验共同模式后的残差是否值得分区
-> 分区方法允许返回 K=1
-> 再验证区域和边界对完整工况扰动是否稳定
-> 最后才判断是否进入残差学习
```
