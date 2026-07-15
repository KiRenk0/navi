# **工程操作手册：AI 辅助二维至三维气动热仿真代码升级指南**

在现代航空航天工程中，高超声速飞行器的气动热预测是热防护系统设计的核心。从传统的二维片条理论（Strip Theory）转向三维无粘表面流线法（3D Streamline Method）与轴对称类比（Axisymmetric Analogue），不仅是几何维度的增加，更是底层偏微分方程和物理模型的全面重构 1。本操作手册专为具备一定流体力学背景但缺乏软件工程经验的研究人员设计，旨在利用当前前沿的人工智能代理（如配置了 Opus 4.8 与 GPT-5.5 的 Windsurf / Devin，以及 DeepSeek V4 API），构建一个成本可控、质量可验证的多模型协同工作流，确保科学计算代码在重构过程中避免数值发散与物理逻辑崩溃 1。

## **一页总流程图文字版**

以下文本流程图展示了从二维参考焓法向三维飞行器表面气动加热预测版本升级的宏观执行路径。该路径严格遵循“宽而浅”的任务拆解原则，避免代理因一次性处理过多上下文而导致项目崩盘 1。

# **\========================================================================================== 阶段一：知识植入与架构脚手架搭建 (高频调用，利用低成本大窗口模型) \-\> 读取数十篇参考焓法、Zoby 公式文献及 2D 旧代码，提取纯粹的数学公式与变量字典。 \[Opus 4.8\] \-\> 审阅提取出的物理逻辑，规划 3D Python 软件的模块化目录结构与函数接口声明。**

# **|| /**

# **阶段二：三维几何与无粘流场预处理 (数据密集型，利用低成本推理模型) \-\> 编写网格读取、法向量计算、基于 CFD 速度矢量的表面投影函数。 \-\> 读取 Fluent 导出的海量 CSV 数据，进行单位清洗与坐标对齐。 \-\> 抽查网格拓扑奇异点（如驻点位置极值）的处理逻辑是否符合物理直觉。**

# **|| /**

# **阶段三：流线追踪与度量系数推导 (数学密集型，双轨制模型校验) \-\> 实现四阶龙格-库塔 (RK4) 沿流线反向积分算法，追踪跨面元流线。 \-\> 推导并审查度量系数 (Metric Coefficient, h) 的跨流线偏导数几何计算法则。 \[Opus 4.8\] \-\> 将高风险数学模块整合入主分支，确保 NumPy 数组广播形状 (Shape) 绝对对齐。**

# **|| /**

# **阶段四：Zoby 热流计算与奇异点处理 (物理边界极值测试) \-\> 编写边界层动量厚度积分与 Eckert 参考焓热流计算代码。 \-\> 设计并注入针对驻点速度趋零 (u\_e \-\> 0\) 或度量系数趋零 (h \-\> 0\) 的洛必达极限处理。 \[Human Operator\] \-\> 在本地运行标准的 40 度球锥解析几何算例，对比风洞实验热流分布曲线。**

# **|| /**

# **阶段五：验证体系与防崩溃迭代 (自动化回归测试) \-\> 为每个独立数学函数编写 PyTest 单元测试，检查单位量纲。 \[Opus 4.8\] \-\> 处理所有联调报错 (Traceback)，仅执行局部内联修复 (Inline Edit)，拒绝全项目重构。 \[Human Operator\] \-\> 将 3D Python 代码输出热流结果与 Fluent 完整 N-S 方程计算结果进行误差带核验。**

## **一、模型分工与成本路由**

针对广义上的科学计算工程，大型语言模型的能力谱系已高度分化。传统的代码生成工具依赖开源后端的模式识别，而气动热偏微分方程求解需要极其严苛的物理边界约束与多步数学推理 1。在拥有 Opus 4.8、GPT-5.5 以及 DeepSeek V4 API 的情况下，建立基于比较优势的成本路由（Cost Routing）策略至关重要。

### **DeepSeek V4 API 的适用边界**

DeepSeek V4 提供了 Flash 和 Pro 两个层级，其核心优势在于支持 1M Token 的超长上下文窗口，且调用成本极低（Flash 输入成本低至 $0.14/1M Tokens，Pro 为 $0.435/1M Tokens） 3。在针对编程和数学的评测中，DeepSeek V4 Pro 展现出极其强大的独立算法实现能力 3。  
在气动热重构任务中，DeepSeek V4 极度适合承担数据繁杂、逻辑机械或需要大量试错的低风险任务。这些任务包括解析庞大的 Fluent 表面网格导出文件、进行数据清洗与单位转换、根据文献长文提取 Eckert 参考焓公式与变量名、为单一数学函数（如四阶龙格-库塔步长计算）编写 Python 逻辑、生成 matplotlib 画图脚本，以及在控制台报错时进行长篇报错日志的初步原因分析。让低成本模型处理这些任务，可以避免将高昂的 Opus/GPT 上下文窗口浪费在语法纠错上。  
然而，DeepSeek V4 在复杂工程的全局架构稳定性（SWE-Bench 表现略弱于 Opus）以及对刚性物理方程（Stiff Systems）的全局数值稳定性设计上存在潜在风险 1。因此，DeepSeek V4 不适合单独负责跨模块的依赖重构、三维轴对称类比理论中度量系数偏导数矩阵的最终数学确认、驻点数学奇点（Singularity）的物理极限策略选择，以及在未受限制的情况下对整个项目目录进行全量重构。

### **高价值模型：Opus 4.8 与 GPT-5.5 的职责划分**

处于能力前沿的专有模型必须被部署在需要深厚数理洞察与架构防御的节点上。  
Claude Opus 4.8 在代码工程测试中具有压倒性优势（高达 88.6%），以其极其严谨的指令遵循能力和极少篡改无关代码的特性闻名 1。在本项目中，Opus 4.8 应当担任系统架构师与版本控制管理员的角色。其专属任务包括：定义 3D 流线法的顶层模块化架构、审查 DeepSeek 生成模块的接口匹配度、进行代码审查（Code Review）以排查变量生命周期与内存泄漏风险，以及在收到具体报错时执行最小范围的内联修复（Inline Edit） 1。  
GPT-5.5 则在复杂的数理推导基准测试中占据统治地位，具备极强的几何流形转张量运算能力 1。GPT-5.5 应当被用作物理验证官与首席科学家。其高价值任务包括：审查三维流线间距变化转化为度量系数 ![][image1] 的微分方程推导是否符合 DeJarnette 或 Hamilton 的原始论文定义 7；核查驻点处动量厚度雷诺数积分的数值稳定性；确认代码中 Zoby 热流公式各项物理量数量级是否合理；以及最终科学结果与 Fluent 对比时的误差合理性判断。

### **DeepSeek V4 省钱用法表**

通过精确的工作流切片，将“便宜模型先干，贵模型把关”的策略工程化，可以最大限度地降低 API 消耗。

| 任务切片 | DeepSeek V4 承担的低成本工作 | 节省的费用/资源去向 |
| :---- | :---- | :---- |
| **文献与公式消化** | 将十余篇关于轴对称类比和 Zoby 理论的 PDF 喂给 DeepSeek Flash，命令其提取公式、约束与单位表，输出为 Markdown。 | 避免将百万 Token 的原始 PDF 塞入 GPT-5.5，Opus 只需阅读生成的精简 Markdown 即可进行架构设计。 |
| **CFD 数据预处理** | 编写脚本读取数十万行的 Fluent CSV 网格节点，完成表头重命名、缺失值清洗与英制到国际单位的转换。 | 避免高价值代理在枯燥的 Pandas 语法调试和数据格式化上浪费推理算力。 |
| **单一函数初稿编写** | DeepSeek Pro 根据已确定的公式，编写孤立的向后积分流线追踪算法，并附带详细注释。 | 充当高级打字员，包揽 80% 的基础 NumPy 数组初始化与循环逻辑编写工作。 |
| **测试用例生成** | DeepSeek Flash 为写好的几何度量函数生成 20 个极端的 NumPy 输入输出断言测试（PyTest）。 | 消除人工编写重复测试的冗长工时，确保物理审计前代码语法无误。 |
| **报错堆栈分析** | 将控制台的 IndexError 或 ValueError: shapes not aligned 长篇报错直接发给 DeepSeek 解释原因。 | 快速定位 NumPy 数组维度问题，明确修改意见后再交给 Opus 实施精确修复。 |

### **多模型任务分工表**

科学计算项目必须依据风险等级与计算复杂度进行任务分发，下表规定了针对气动加热代码的强制性分工路线。

| 任务 | 推荐模型 | DeepSeek V4 可用性 | Opus/GPT 终审要求 | 输入文件 | 输出结果 | 验收标准 | 风险等级 |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| **项目目录设计** | Opus 4.8 | 不推荐 | 必须 (Opus) | 二维旧代码、提取的 3D 公式 Markdown | 空的模块化目录与占位符 Python 文件 | 高内聚低耦合，数据读取与物理计算严格分离。 | 高 |
| **网格几何预处理** | DeepSeek Pro | 完全胜任 | 否 | Fluent 表面网格节点 CSV | geometry.py | 法向量符合右手法则，面元面积总和等于真实表面积。 | 中 |
| **表面无粘流线追踪** | DeepSeek Pro | 完全胜任 | 必须 (GPT) | 速度矢量数据、几何文件 | streamline.py | 采用 RK4 向后积分，流线在面元边界平滑过渡不断裂 2。 | 高 |
| **度量系数 (h) 计算** | GPT-5.5 | 仅限代码编写 | 必须 (GPT) | 追踪好的流线坐标 | metric.py | 从几何坐标偏导数计算的 h 能准确反映流线发散，数量级合理 8。 | 极高 |
| **参考焓边界层积分** | DeepSeek Pro | 完全胜任 | 必须 (GPT) | 边缘流场数据、流线与 h 数组 | enthalpy.py | 动量厚度雷诺数积分无异常放大，参考态物理参数正确查找。 | 高 |
| **驻点奇点处理** | GPT-5.5 | 严禁单独负责 | 必须 (GPT) | 包含 h-\>0 或 u\_e-\>0 的数组位置 | singularity.py | 驻点处使用极限或 L'Hôpital 法则，不产生 NaN 或 Inf 1。 | 极高 |
| **热流结果输出与绘图** | DeepSeek Flash | 完全胜任 | 否 | 计算得到的壁面热流数组 ![][image2] | plot\_results.py | 等值线云图色标正确，文件输出格式符合 Tecplot 或 Paraview 标准。 | 低 |

## **二、面向代码小白的 Agent 使用流程**

在工程软件重构中，最致命的错误是采用“又高又深（Tall & Deep）”的指令模式，即将所有文件丢进智能代理并下达“将二维升级为三维”的模糊命令 1。这会诱发代理的幻觉并产生无法追踪的数值崩塌。必须采用结构化、宽而浅（Wide & Shallow）的防御性代理工程策略 1。

### **推荐的项目文件夹组织结构**

不要让代理扫描混乱的桌面文件夹。构建严格的上下文边界是控制代理注意力的基础：  
/aerothermal\_3d\_solver ├── /docs │ ├── 01\_2D\_to\_3D\_theory\_survey.md \# 调研报告（关于轴对称类比与流线法） │ ├── 02\_zoby\_eckert\_equations.md \# 由DeepSeek提取的关键公式与单位规范 │ └── 03\_mesh\_data\_dictionary.md \# 记录Fluent导出数据的表头和物理意义 ├── /legacy\_2d \# 存放旧版二维代码（设为只读，供物理变量参考） ├── /src │ ├── **init**.py │ ├── config.py \# 全局物理常数（如R, 普朗特数, 经验系数） │ ├── input\_reader.py \# 读取并清洗三维表面数据 │ ├── geometry\_topology.py \# 表面点排序、法向量与曲率计算 │ ├── streamline\_tracker.py \# 反向积分流线追踪模块 │ ├── metric\_calculator.py \# 轴对称类比度量系数推导模块 │ ├── aerothermal\_solver.py \# Eckert 参考焓与 Zoby 表面热流计算 │ └── singularity\_handler.py \# 驻点异常处理逻辑 ├── /tests \# 每个模块的单独测试代码 ├── /data │ ├── /raw \# 原始全尺寸Fluent数据（严禁让agent直接读取） │ ├── /processed\_sample \# 截取机头附近的500个面元的样本数据（供代理测试） │ └── /validation \# 用于回归对比的风洞实验或CFD热流结果 └── /agent\_prompts \# 保存标准的提示词模板

### **必须提前准备的关键文件清单**

在允许代理编写任何代码之前，研究人员必须亲手或利用 DeepSeek 准备好以下“铁律”文件，用以约束 Opus 和 GPT 的发散思维：

1. **关键公式 Markdown (02\_zoby\_eckert\_equations.md)**：清晰写出边界层积分公式、Zoby 近似对流加热方程、以及动量厚度的计算法则 1。必须注明经验系数（如 0.22, 0.664）的来源 1。  
2. **变量单位表**：强制声明代码内部矩阵全盘采用国际单位制（SI），明确规定压力是 ![][image3]（而不是 ![][image4] 或 ![][image5]），热流是 ![][image6] 1。  
3. **一个极小测试案例**：抽取一个标准球头前缘极小区域的数据（如 100 个节点），包括 ![][image7], 压力, 温度, 速度矢量，供代理在编写函数后快速完成 print 验证。

文件对代理的开放策略是：**文档目录全局开放，数据文件只开放极小测试样例，二维代码仅限查询时特定引入。** 绝对不能将包含百万网格的完整 Fluent 导出文件放进工作区，否则代理的上下文处理成本会激增且大概率超时。

### **防止项目崩盘的“从 0 到 1”执行流程**

每一次开启 Windsurf/Devin 进行代码修改，必须遵循一套硬性操作规范。在下达修改指令前，必须强制代理进行“假设验证（Explain Assumptions）” 1。具体的提问范式如下：  
每次让 Agent 编写/修改代码前，要求其输出一份《数学与工程设计书》，需涵盖：

1. **物理模型理解**：它将使用哪组微分方程来近似当前的物理过程。  
2. **拟修改范围**：明确列出将改动哪几个 .py 文件。  
3. **函数签名**：列出即将编写的函数的输入参数和返回值。  
4. **张量形状 (Shape)**：明确声明 NumPy 数组维度，例如速度矢量是 (N, 3\) 还是独立的三个 (N,) 数组。  
5. **物理量纲**：输入输出的具体单位。  
6. **验收标准**：证明这段代码写对的客观依据。

在审查该设计书并确认无误后，才允许其真正开始写代码。为了防范小白操作导致代码被覆写，流程中需加入备份机制：每次只改一个模块；改完后立即在本地运行极小测试样例；通过后使用 git commit 或复制文件保留备份；如果报错，将报错信息交给另一个代理审查差分（Diff），使用内联编辑（Inline Edit）指令进行微调，严禁代理“为了修复一个小 Bug 而重新实现整个架构” 1。

## **三、从二维片条理论代码升级到三维流线法的技术路线拆解**

传统的二维片条理论忽略了高超声速飞行器展向流动的边界层三维效应，导致热流预测存在严重偏差 1。将其升级为依赖 Cooke 等人提出的三维轴对称类比（Axisymmetric Analogue）与流线追踪法，需要对物理和数学底层进行外科手术式的解耦 1。整个重构工程应拆分为以下严格分离的模块：

### **1\. 输入数据与单位对齐模块**

* **目标**：从三维非结构网格数据源安全载入边界层边缘参数。  
* **输入**：Fluent 导出的 CSV 文件（坐标、![][image8]）。  
* **输出**：形状严谨的 NumPy 字典对象，全量转换为国际单位制。  
* **关键公式**：![][image9]  
* **推荐由哪个模型实现**：DeepSeek V4 Pro  
* **需要哪个模型审查**：无（基础任务）  
* **最小测试方法**：打印前 5 行变量，人工比对数量级（如密度是否为普通空气数量级，速度是否匹配马赫数）。

### **2\. 几何预处理与拓扑构建模块**

* **目标**：获取网格的表面法向量，并寻找整个流场的驻点（Stagnation Point）。  
* **输入**：三维节点坐标系。  
* **输出**：单元面元法向量矩阵、包含驻点坐标的极值标量。  
* **关键逻辑**：驻点定义为边界层边缘速度 ![][image10] 的全局极小值点或表面压力 ![][image11] 的全局最大值点 12。  
* **推荐由哪个模型实现**：DeepSeek V4 Pro  
* **需要哪个模型审查**：Opus 4.8（检查向量外积计算的广播逻辑）  
* **最小测试方法**：选取一个标准的解析球体，验证算法找到的驻点是否确实位于迎风面最前端。

### **3\. 表面无粘流线追踪模块 (核心算法)**

* **目标**：基于给定的表面速度矢量，生成离散的三维表面流线路径。  
* **输入**：法向量矩阵、三维速度场、作为种子的尾缘面元索引。  
* **输出**：多条流线的坐标轨迹数组列表。  
* **关键数学方法**：由于高超声速流线在驻点附近剧烈发散，若从驻点向下游追踪会产生极大的网格跨越误差。因此，必须采用向后积分（Backward Integration）策略，从飞行器下游节点逆着流速反向追踪至驻点附近 1。  
* **关键公式**：![][image12] （负号代表逆向追踪）。采用四阶龙格-库塔（RK4）方法求解该常微分方程 2。  
* **可能的函数名**：trace\_streamline\_backward\_rk4()  
* **推荐由哪个模型实现**：DeepSeek V4 Pro  
* **需要哪个模型审查**：GPT-5.5  
* **最小测试方法**：追踪一条流线，判断其轨迹是否贴合机体表面（与法向量点乘必须处处为 0），且最终收敛于驻点所在的局部面元内 2。

### **4\. 三维轴对称类比 / 度量系数模块 (核心物理)**

* **目标**：计算度量系数 ![][image1]，该系数用于表征相邻流线之间的聚拢（Convergence）或发散（Divergence）程度，在数学上等效于二维轴对称体方程中的“体半径” 1。  
* **输入**：已追踪完成的流线坐标数组、表面网格拓扑。  
* **输出**：沿每条流线的 ![][image13] 一维数组。  
* **关键公式**：度量系数 ![][image1] 可通过跨流线方向的偏导数求解。一种常用的解析近似是计算表面坐标偏导数，例如使用笛卡尔坐标系的两个独立变量进行积分推导：![][image14] 或者利用相邻流线的几何垂距直接近似 7。  
* **可能的函数名**：calculate\_metric\_coefficient\_h()  
* **推荐由哪个模型实现**：GPT-5.5（涉及复杂的张量偏导数与散度运算）  
* **需要哪个模型审查**：GPT-5.5 深度交叉检查  
* **最小测试方法**：输入一个理想圆锥的流场，检查算出的度量系数 ![][image1] 是否随着距圆锥顶点的距离 ![][image15] 呈绝对的线性增长关系。

### **5\. Eckert 参考焓 / Zoby 气动加热公式模块**

* **目标**：结合流线几何与流场参数，积分求解边界层动量厚度，进而求得表面对流热流分布。  
* **输入**：边界层边缘状态 (![][image16])，壁面温度 ![][image17]，度量系数 ![][image1]。  
* **输出**：沿流线分布的热流标量数组 ![][image18]。  
* **关键公式**：  
  1. **参考焓（Eckert）**：使用经典的经验法则在可压缩边界层内寻找参考态。对于层流与湍流，参考焓 ![][image19] 的常见逼近值为 ![][image20]（绝热壁焓 ![][image21]，其中恢复系数指数 ![][image22] 对于层流，![][image23] 对于湍流） 9。在参考焓下计算参考密度 ![][image24] 和参考黏度 ![][image25]。  
  2. **动量厚度积分**（层流）： ![][image26] 1  
  3. **Zoby 修正雷诺类比热流方程**（层流）： ![][image27] 1  
* **可能的函数名**：integrate\_momentum\_thickness(), compute\_zoby\_heat\_flux()  
* **推荐由哪个模型实现**：DeepSeek V4 Pro  
* **需要哪个模型审查**：Opus 4.8（核对单位与经验常数）  
* **最小测试方法**：固定一组空气动力学参数，手算一个点的热流值，检查 Python 代码输出的标量是否与手算完全一致（规避括号优先级错误）。

### **6\. 驻点奇异点处理与数值稳定性模块 (防御性工程)**

* **目标**：防止微分方程在几何顶点处产生数值爆炸。  
* **输入**：驻点极近区域（![][image28]\-curve）内的热力学与动力学变量 1。  
* **输出**：被安全修正的驻点热流与初始动量厚度。  
* **关键数学机理**：在驻点处，度量系数 ![][image29] 且边缘速度 ![][image30]。直接调用上述动量厚度积分方程将触发“除以零”错误（Division by Zero） 1。必须对极点使用洛必达法则（L'Hôpital's rule）求极限，或直接调用 Fay-Riddell 等驻点专用工程公式，在驻点附近的极小环量面（![][image28]\-curve）上提供流线追踪的积分初值 1。  
* **推荐由哪个模型实现**：GPT-5.5  
* **需要哪个模型审查**：GPT-5.5  
* **最小测试方法**：人为构造 ![][image31] 极小的数组序列输入，检查程序是否报 NaN，确保在接近奇点时算法能平滑切换到极限计算函数。

### **7\. 输出与验证对比模块**

* **目标**：将流线上计算得到的热流投影回三维网格，并与高保真 CFD 结果形成对比闭环。  
* **输入**：![][image2] 流线数组、Fluent 热流参考场。  
* **输出**：误差统计报告。  
* **推荐由哪个模型实现**：DeepSeek V4 Flash

## **四、验证体系的设计与小白执行流程**

对于初学者的工程算法开发，“代码能跑通不报错”是最危险的假象。一套鲁棒的验证体系必须从简到繁、层层推进。

### **第一步：基础算例的回归测试**

不要直接计算高超声速飞行器全机。

1. **旧二维代码回归**：先给 3D 代码输入一个展向完全均匀的无限大翼型数据，计算出的中心截面热流必须与原有的二维片条理论代码结果一致，误差应在 1% 以内。  
2. **轴对称体（钝锥/球头）**：输入一个攻角为零的 40 度球锥模型。驻点热流必须达到全局峰值，下游壁面热流必须沿着母线逐渐平滑下降 17。这是检验度量系数 ![][image1] 提取是否正确的试金石。

### **第二步：物理合理性断言检查**

在每个简单算例的测试脚本中，必须强制检查：

* **单位准确度**：确保最终热流 ![][image2] 没有因为混用英制（如 ![][image32] 或 ![][image33]）而缩放异常。如果结果在 ![][image34] 以上或 ![][image35] 以下，必定是单位错位或密度 ![][image36] 查表失败 1。  
* **驻点峰值**：代码必须能识别在主流附着点（驻点/驻点线）热流绝对最大。  
* **物理趋势**：随马赫数 ![][image37] 增加，热流应增加；随高度增加（空气变稀薄），对流热流应减小。

### **第三步：与 Fluent 全 N-S 求解器结果的容差比对**

当简单几何验证通过后，方可比对 Fluent 导出的真实三维飞行器气动热数据。

* **对比指标**：提取飞行器迎风面中心对称面（Windward Symmetry Plane）的流线热流分布曲线，将 Zoby 公式预测值与 Fluent 数据画在同一张图上对比。  
* **误差定义**：使用相对误差 ![][image38]。  
* **可接受的物理误差范围**：工程近似法（Zoby/参考焓法）的核心在于速度快。在迎风面附着流区域（Attached Flow），其预测结果比高保真 Navier-Stokes 解偏高或偏低 **10% 到 20%** 都是学术界公认的合理误差范围 18。  
* **判断算法正确与否的标准**：  
  * **正常误差大**：在背风面分离区（Separated Flow）、激波-激波干扰区或尾流区，误差超过 50% 甚至完全失效是正常的。因为轴对称类比的前提是“忽略横向边界层卷起”，该前提在分离流中不成立 11。  
  * **算法写错的标志**：如果迎风面大面积区域趋势相反（如 CFD 曲线下降，Python 曲线突增），或者热流数值出现明显的锯齿形震荡，说明流线追踪的网格跨越插值逻辑崩溃，或度量系数 ![][image1] 的微分计算存在未平滑的数值噪声 11。

### **小白可执行的排错优先流程**

1. 跑出结果后，**先看云图**：热点是否全在迎风面和驻点？如果背风面比迎风面热，大概率法向量计算反了或者速度积分反了。  
2. **看最大值**：找到驻点处热流数值。打印代码中该点的流场密度 ![][image39] 和黏度 ![][image40] 查表结果。如果该处热流为 0 或 NaN，优先检查奇点处理模块。  
3. **看曲线平滑度**：提取一条流线画出 ![][image18]。如果有严重毛刺，立刻要求 Opus 代理检查 Numpy 的偏导数插值代码是否加入了平滑滤波。

## **五、我本人到底需要学懂什么（最低限度学习清单）**

将脏活累活交给 AI 不代表人类可以放弃物理学。您不需要成为全栈工程师，但必须守住核心领域的评判底线。

### **A. 必须亲自搞懂的物理护城河（如果代理写错，你必须能一眼看穿）：**

* **参考焓法核心公式与物理意义**：必须深刻理解 ![][image20] 每一项在物理上代表边界层的哪一层能量。必须背诵普朗特数指数（层流 ![][image41]，湍流 ![][image42]） 1。代理极容易张冠李戴。  
* **度量系数 ![][image1] 的物理直觉**：不需要会解复杂的空间几何偏导方程，但必须知道：如果流线互相靠拢，![][image1] 变小；如果流线互相发散，流管变宽，![][image1] 增大。通过可视化云图，你能判断 ![][image1] 的变化趋势是否正确 1。  
* **边界层边缘状态概念**：代码读取 Fluent 数据时，如果代理不小心抓取了“壁面温度 ![][image17]”当做“边界层边缘温度 ![][image43]”来计算动力黏度，结果会错出天际。必须知道使用无粘流体力学计算出的外部流场才是边缘状态 1。  
* **数量级直觉**：对特定攻角和马赫数下，热流是百 ![][image44] 还是几十 ![][image45] 必须有概念。

### **B. 让 DeepSeek 反复教你的工具技能（遇到不懂直接问）：**

* **NumPy 数组广播与花式索引**：当看到 np.einsum 或形如 array\[:, np.newaxis\] 的操作时，不用死记硬背。直接复制整段代码发给 DeepSeek 要求：“用大白话解释这三行数组形状是怎么变换的”。  
* **Pandas 读表与清洗**：让 DeepSeek 生成脚本以应对 Fluent 千奇百怪的导出列名。  
* **Python 的面向对象（Class封装）**：了解如何把一大堆孤立的函数重构为一个 StreamlineTracker 类，便于保存进度。  
* **读懂 Python Traceback 报错**：将底部的 Error 类型与引发错误的文件行定位交给模型分析。

### **C. 暂时不需要深入掌握的高级技术（现阶段知道会带来复杂性即可，规避使用）：**

* **高级并行优化技术（如 MPI、CUDA 编程）**：只要计算一万条以内流线，使用 Python 自带的多进程 multiprocessing 加 NumPy 足够快了。  
* **隐式/高阶 TVD 差分格式开发**：工程热流计算多是单向常微分方程积分，不需要卷入计算流体力学底层的双曲型方程复杂求解器阵地。  
* **CI/CD 与后端打包工程**：无需搭建 Docker 或 GitHub Actions 自动化流水线。本地 Conda 虚拟环境加 git 备份即可。

## **六、可复制的 Agent 提示词模板**

请在 Windsurf、Devin 或独立 API 界面中严格按阶段复制使用以下提示词模板。请将括号 \[ \] 中的内容替换为实际需求。

### **1\. 项目初始化提示词（目标代理：Claude Opus 4.8）**

“我正在将一个二维的高超声速气动加热 Python 代码升级为三维基于流线法与轴对称类比的工程计算软件。现在，请你扮演一位拥有二十年经验的航空计算科学首席架构师。  
约束条件 1：在当前对话中，绝对不允许你生成任何可执行的 Python 逻辑代码。  
约束条件 2：请仔细阅读 /docs 下关于 Zoby 方程和度量系数的数学说明文档。  
任务：请输出一份详细的模块化架构设计书。请规划出推荐的目录树结构；针对核心的文件（如流线追踪、几何预处理、热流计算），请以接口声明（Interface）的形式列出所有必须的函数签名、输入参数（明确指出 NumPy 数组应该是一维还是二维）、返回参数以及物理单位规范（必须基于国际单位制 SI）。如果理解，请输出架构文档。”

### **2\. 公式梳理提示词（目标代理：DeepSeek V4 Flash）**

“请阅读附件中的三维气动加热理论文献与旧二维报告。我需要你将里面散落的所有关于 Eckert 参考焓法和 Zoby 工程热流公式的数学方程全部提取出来。  
提取要求：

1. 用纯 Markdown 和 LaTeX 数学公式表示。  
2. 为每一个数学符号列出一个详尽的 Markdown 表格，指出其物理含义、推荐的代码变量名、以及 SI 单位（如密度 ![][image46], 动力黏度 ![][image47] 等）。  
3. 必须明确提取出层流和湍流情况下的所有经验常数（如 0.28, 0.5, 0.22, 0.664 等），以及普朗特数的修正指数。  
   此文档将作为后续编码的最高指导法则，务必做到准确无误。”

### **3\. DeepSeek 低成本预处理与脚手架提示词（目标代理：DeepSeek V4 Pro）**

“请根据已经确定的公式文档与接口规范，实现一个名为 \[ geometry\_topology.py \] 的独立模块。  
任务目标：\[ 从散乱的三维面元数据中计算表面单位法向量，并找到压力全局最大值作为驻点 \]。  
约束条件：

1. 大量使用 NumPy 矢量化运算，禁止使用效率低下的双重 for 循环遍历数十万个网格节点。  
2. 在每个函数上方，必须提供极其详细的 Google-style Docstring，说明输入张量的 Shape 要求（如 (N, 3)）。  
3. 对除以零的潜在风险做防御性判断。  
   仅输出该模块的 Python 代码。”

### **4\. 贵模型物理与逻辑审查提示词（目标代理：GPT-5.5 / Opus 4.8）**

“以下是低成本模型生成的 \[ metric\_calculator.py \] 模块，它负责从三维流线计算度量系数 ![][image1]。  
请你作为首席物理审计员对其进行深度 Review。审查重点：

1. 物理准确性：跨越流线的偏导数推导是否符合 DeJarnette 或 Hamilton 的原始算法逻辑？  
2. 数组维度对齐：检查 NumPy 函数操作中，是否存在潜在的广播（Broadcasting）错误。  
3. 边界条件防御：在流线发散或过度收敛的地方，是否有溢出保护。  
   若发现逻辑或物理错误，请清晰说明错误机理，并提供只针对该函数的修正代码。”

### **5\. 局部报错修复提示词（目标代理：Opus 4.8 / GPT-5.5）**

“我在运行 \[ streamline\_tracker.py \] 时遇到了如下 Python Traceback 报错：  
\`\`  
约束条件：请精确诊断是哪一行引发的错误（疑似是数组形状不匹配或变量类型错误）。请只告诉我发生错误的原因，并使用 **内联编辑（Inline Edit）** 的模式，仅给出修复那几行代码的具体修改方案。绝对禁止对当前文件进行大段重构，更不允许修改物理方程公式。”

### **6\. 代码解释提示词（目标代理：DeepSeek V4 Flash）**

“我对这段 NumPy 操作代码不是很理解：  
\[ 粘贴你看不懂的代码块，例如 np.einsum 或者 np.cross \]  
我是一个 Python 初学者，但我有流体力学背景。请你逐行向我解释：

1. 这段代码里的数组操作对应着现实中流体或几何的哪个物理变化步骤？  
2. 它在对内存里的多维数组做什么变换？请用具体数字（比如 500 行 3 列的数组）举例说明。”

### **7\. 结果异常诊断提示词（目标代理：GPT-5.5）**

“代码已经跑通并且输出了热流云图。但是物理结果非常奇怪：\`\`。  
请作为气动专家帮我按优先级排查问题。请具体列出：

1. 是否是在奇异点（![][image31] 极小值处）缺少了极限或洛必达法则修正？  
2. 是否是参考焓或参考温度算出了负值，导致算黏度时出现了复数或 NaN？  
3. 给定常规高超飞行条件，流场中哪个变量输入错了单位会导致热流放大一百万倍？请提供 3 个可以在代码中 print() 出来检查的断点排查建议。”

### **8\. 模块实现提示词（目标代理：DeepSeek V4 Pro）**

“请按照阶段任务，实现 \[ aerothermal\_solver.py \] 模块中的 \[ compute\_momentum\_thickness \] 函数。  
数学要求：运用基于流线步长 ![][image48] 的梯形数值积分，计算动量厚度 ![][image49]。必须引入度量系数 ![][image1] 的平方项 ![][image50]。  
物理要求：气动黏度请根据萨瑟兰定律（Sutherland's law）内部调用辅助函数求解。  
请先用注释列出该数学公式的求解假设，然后提供向量化的 Python 运算代码。”

## **七、实施计划与高风险任务清单**

### **第一周实施日程表（小白安全指南）**

为了防止陷入“改代码-报错-再改代码-彻底崩溃”的死循环，请严格执行这 7 天计划。

* **Day 1 (文档与基建)**：不动任何代理软件。手动在本地构建好 Section II 中的文件夹结构。将 2D 旧代码移入 legacy\_2d。收集好 Fluent 数据，建立测试样例文件夹。  
* **Day 2 (公式固化)**：使用提取公式的提示词，让 DeepSeek 从文献中生成包含 Eckert 公式、常数、单位规范的 Markdown。**你必须亲自花半天时间将这些公式与论文反复校对**。  
* **Day 3 (系统架构与数据读取)**：启动 Opus 4.8 使用“初始化提示词”规划接口结构。再启动 DeepSeek V4 生成读取 Fluent 数据的 Pandas 脚本。打印出速度和温度数组，检查形状。  
* **Day 4 (拓扑与几何运算)**：使用 DeepSeek V4 编写法向量计算、面元面积求解和驻点搜索逻辑。本地运行一个单纯的“找顶点”测试。  
* **Day 5 (流线追踪攻坚)**：这是最难的一步。用 DeepSeek V4 Pro 起草逆向 RK4 积分代码。写完后务必交给 GPT-5.5 使用“贵模型审查提示词”进行数学审计。测试单条流线是否平滑收敛。  
* **Day 6 (度量系数与驻点防御)**：处理度量系数 ![][image1] 偏导数。强制 GPT-5.5 在代码最前端写明：如果 ![][image51] 或 ![][image52] 时，热流采取极限替代算法，规避奇点除零。  
* **Day 7 (热流映射与闭环)**：实现最终的 Zoby 热流公式。跑通 40 度球锥验证算例，将中心线热流分布通过 Matplotlib 画出来，对比理论规律。

### **下一步应优先准备的文件**

1. **极简的测试网格文件 (sphere\_cone\_test\_100\_cells.csv)**：从你的全尺寸 3D 飞行器中裁切出一个标准的钝头球锥前缘数据。它必须包含网格拓扑、节点坐标和无粘流体解。这是你的试验台。  
2. **物理与经验常数清单 (constants\_dict.py)**：把 ![][image53]（普朗特数）、特定的热容比 ![][image54] 等事先手写在 Python 文件里。别让 AI 每次都在算流场时凭空猜测这些常数。  
3. **解析验证标准（Benchmark Truth）**：找出一篇基于同样 40 度球锥的文献或你预先跑好的 Fluent 数据点。整理出一份表格，标明：当 ![][image55] 时，![][image2] 理应大约等于 ![][image56]。没有“标答”，代理生成的程序好坏便无从谈起。

### **高风险任务避坑清单**

* **Risk 1：驻点奇异性崩溃**（极高风险）。驻点处主流速度降为零，直接沿用常规公式会导致动量厚度积分出现分母为零。未作奇异点处理的代码运行 1 秒钟就会报出漫天飞舞的 NaN 和 Inf 1。  
* **Risk 2：顺流向（正向）积分发散**。在高超声速驻点附近，流线呈现指数级发散，如果按常规逻辑从驻点顺着流场网格往前积分插值，误差会迅速放大。必须采用向后积分（Backward Integration）的反直觉流线追踪法 2。  
* **Risk 3：经验公式里的隐蔽单位制灾难**。早期 NASA 报告常常使用英制单位（BTU, slug, foot） 1。语言模型在拼接不同文献时容易错乱单位。务必全局锁定采用国际单位制，特别是黏度（![][image47] 或 ![][image57]）。  
* **Risk 4：修改爆炸（Agent Hallucination Cascade）**。为了修一个标量运算的 TypeError，代理自作主张把整个网格拓扑数据结构改成了字典树，导致全盘皆崩。在 Windsurf 中，只要是 Bug 修复，严格限制代理使用局部替换的 Inline Edit。

#### **引用的著作**

1. AI辅助工程代码优化.pdf  
2. Approximate Method for Computing Convective Heating on Hypersonic Vehicles Using Unstructured Grids | Journal of Spacecraft and Rockets \- Aerospace Research Central, 檢索日期：6月 23, 2026， [https://arc.aiaa.org/doi/10.2514/1.A32518](https://arc.aiaa.org/doi/10.2514/1.A32518)  
3. DeepSeek V4 Pro \- API, Specs, Playground & Pricing \- Puter Developer, 檢索日期：6月 23, 2026， [https://developer.puter.com/ai/deepseek/deepseek-v4-pro/](https://developer.puter.com/ai/deepseek/deepseek-v4-pro/)  
4. DeepSeek API: Models, Pricing, and How to Call It (2026) \- Morph, 檢索日期：6月 23, 2026， [https://www.morphllm.com/deepseek-api](https://www.morphllm.com/deepseek-api)  
5. DeepSeek V4 Preview Release, 檢索日期：6月 23, 2026， [https://api-docs.deepseek.com/news/news260424](https://api-docs.deepseek.com/news/news260424)  
6. deepseek-ai/DeepSeek-V4-Pro \- Hugging Face, 檢索日期：6月 23, 2026， [https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro)  
7. Approximate Method for Computing Convective Heating on Hypersonic Vehicles Using Unstructured Grids \- Aerospace Research Central, 檢索日期：6月 23, 2026， [https://arc.aiaa.org/doi/pdfplus/10.2514/1.A32518](https://arc.aiaa.org/doi/pdfplus/10.2514/1.A32518)  
8. Efficient Method for Heat Flux Calculations within Multidisciplinary Analyses of Hypersonic Vehicles \- MDPI, 檢索日期：6月 23, 2026， [https://www.mdpi.com/2226-4310/10/10/846](https://www.mdpi.com/2226-4310/10/10/846)  
9. Application of axisymmetric analog to unstructured grid for aeroheating prediction of hypersonic vehicles | International Journal of Numerical Methods for Heat & Fluid Flow \- Emerald Insight, 檢索日期：6月 23, 2026， [https://www.emerald.com/hff/article/19/3-4/501/74190/Application-of-axisymmetric-analog-to-unstructured](https://www.emerald.com/hff/article/19/3-4/501/74190/Application-of-axisymmetric-analog-to-unstructured)  
10. Validation and Application of the Axisymmetric Analogue Technique on Rapid Hypersonic Shape Optimisation \- TU Delft Research Portal, 檢索日期：6月 23, 2026， [https://research.tudelft.nl/files/104466186/6.2022\_0146\_1.pdf](https://research.tudelft.nl/files/104466186/6.2022_0146_1.pdf)  
11. Validation of Computational Fluid Dynamics Volume 2 \- Poster Papers \- DTIC, 檢索日期：6月 23, 2026， [https://apps.dtic.mil/sti/tr/pdf/ADA211894.pdf](https://apps.dtic.mil/sti/tr/pdf/ADA211894.pdf)  
12. one-dimensional heat equation: Topics by Science.gov, 檢索日期：6月 23, 2026， [https://www.science.gov/topicpages/o/one-dimensional+heat+equation](https://www.science.gov/topicpages/o/one-dimensional+heat+equation)  
13. Calculation of laminar heating rates on three-dimensional configurations using the axisymmetric analogue \- NASA Technical Reports Server (NTRS), 檢索日期：6月 23, 2026， [https://ntrs.nasa.gov/citations/19800025211](https://ntrs.nasa.gov/citations/19800025211)  
14. (PDF) Efficient Method for Heat Flux Calculations within Multidisciplinary Analyses of Hypersonic Vehicles \- ResearchGate, 檢索日期：6月 23, 2026， [https://www.researchgate.net/publication/374309187\_Efficient\_Method\_for\_Heat\_Flux\_Calculations\_within\_Multidisciplinary\_Analyses\_of\_Hypersonic\_Vehicles](https://www.researchgate.net/publication/374309187_Efficient_Method_for_Heat_Flux_Calculations_within_Multidisciplinary_Analyses_of_Hypersonic_Vehicles)  
15. Dataset of the experimentally measured heat transfer in the throat region of liquid rocket engine thrust chambers \- PMC, 檢索日期：6月 23, 2026， [https://pmc.ncbi.nlm.nih.gov/articles/PMC8187832/](https://pmc.ncbi.nlm.nih.gov/articles/PMC8187832/)  
16. /I/93/ 4q, 檢索日期：6月 23, 2026， [https://ntrs.nasa.gov/api/citations/19900008232/downloads/19900008232.pdf?attachment=true](https://ntrs.nasa.gov/api/citations/19900008232/downloads/19900008232.pdf?attachment=true)  
17. Centerline Heating Methodology for use in Preliminary Design Studies, 檢索日期：6月 23, 2026， [https://repository.gatech.edu/bitstreams/f8269a93-de90-4281-b9d3-c7ac85640cd4/download](https://repository.gatech.edu/bitstreams/f8269a93-de90-4281-b9d3-c7ac85640cd4/download)  
18. Hypersonic Impact Method for Aerodynamics and Convective Heating (HI-Mach) with Sensitivities \- MDPI, 檢索日期：6月 23, 2026， [https://www.mdpi.com/2226-4310/13/4/373](https://www.mdpi.com/2226-4310/13/4/373)  
19. Evaluation of engineering heat transfer prediction methods in high enthalpy flow conditions \- Aerospace Research Central, 檢索日期：6月 23, 2026， [https://arc.aiaa.org/doi/pdfplus/10.2514/6.1996-1860](https://arc.aiaa.org/doi/pdfplus/10.2514/6.1996-1860)  
20. Viscous and Interacting Flow Field Effects. \- DTIC, 檢索日期：6月 23, 2026， [https://apps.dtic.mil/sti/tr/pdf/ADA089239.pdf](https://apps.dtic.mil/sti/tr/pdf/ADA089239.pdf)  
21. Application of axisymmetric analogue for calculating heating in three-dimensional flows \- NASA Technical Reports Server (NTRS), 檢索日期：6月 23, 2026， [https://ntrs.nasa.gov/citations/19850037460](https://ntrs.nasa.gov/citations/19850037460)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAZCAYAAAAFbs/PAAAAyklEQVR4XmNgGF5gNxA/AuJXQPwAVQo3KAfi/1CaIGAB4jVA/BuIbdDksAJpBohT7gKxOKoUduACxP8YILaAbANp4kBRgQa2MkDcD/K0O1SsFSoWAVOEDJ4D8U8gtkUSwxsIIIn5QMwI5YNoEB8k7glThAxAEulIfBEgvgrET4BYEUkcDJSA+DQQCyKJTWFAdb8mkhyDHxDPQRZggJh8nQESWiCMYgsoNKKRBYDgKxAvBWJmIC5jQPgNDHiQOVAAUiAMxSiKR8HAAwBOoyQQQpcK6wAAAABJRU5ErkJggg==>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABUAAAAaCAYAAABYQRdDAAABKUlEQVR4Xu2UPUsDQRCGXwvFoCBiCAlapLAR0lnYpBGEkJSSLj/A3kawlXRWqfML7FIIFnbaCbFKIwgJpLO2CkTfl9n1ls0HObvAPfDA3dyyOzM3d0BGxnqySfPueoNuBc9SU6QP9Iv2aYM+0+twUVo+aZfm3P2UTmj1b0VKbmgnin3TR7odxVdC/RvQiyj+AzvsX5zCsjqK4io/Pmhl/Ka7QWyfDulhEEuFXswTbCNxTD+QlL5H72kJySSogpF7pgmZ26YT+kJ79JW+Iym9TM9hFUnRhr1E0aKX7nqGAj1wvmG2x8pGVWkatOGtiyt7JbUU3+NwlPxGQm0Y0jqs/Dsks72QK9g4hezAeicqdAz7KGq06RfN4wy2wKtM4gzUIv0bRDgtGevIL/CWKuSl64DJAAAAAElFTkSuQmCC>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABsAAAAaCAYAAABGiCfwAAABeklEQVR4Xu2UvytGYRTHj1CUQiSFgc1kkI3NQGLwY5DFZjTJX+AfkMmPZDCxGJgMbykDi4VFyiAGE8VAfny/zn3eznvuey9eUup+6lP3nvO853nu85znFcn47wzCZbgGTyL5zBidhQ350T+kE47DTfgGp6P34BN8gEPR+F9hUXQyzwB8heewzeVKogPewHufAKOii3iGvS5XEiOiBY99AiyJ5o6k+NlVwjIfTGNBtOCqT4Br0XMbdvFmuA5vRZtqUrSx2AOJ1MCc6GRTJl4O++CdaMdaWPBCdHHVcAy+yBe2OmzhKWx0uSQ4ng0V6BI9711YZeIxwhZuwwqXKwYXxO7sNzHuCGvMm1gMu4UzhalEuuEVbDUxfqVfQIzQ8o+wx+WS4GQ50YUG2MWXsEX0PCdMLs+K6FftSeGP02BDsHh99M7irLEBa+EWbI9yH4QD5SDrvh2Uwhk8gDui94//odyhQzgn37x3n8Fr0RTJZxbnha+zgzIyMv6GdxkdT1B/N5oRAAAAAElFTkSuQmCC>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACQAAAAaCAYAAADfcP5FAAAB/klEQVR4Xu2UP0gdQRCHJ6igKPgvKGIgGGwE0UIwKJYJaGGKNBKEtCaVoJB0ooWgrY2lWAgm2kmsLCKCCIpJQBHEgIoYUmgRoo2Y+Pvd3PDm7buHlWhxH3y8e7O3d7OzsyeSkpIS8Qg2hsH7pAN+ggXhwH1QCBfhi3DgruB2VIVBRz08hLVBvBhWi843KmCNZFeS14zdSimcgL/hV/gejsK3oi/5Af8n2CvKFvwJd+BT+A2ewHN4CUvgB3gKj+E6fBLNzMMm/C6Zm/ZFXzgjmhBXVQcn4zivWaUiWA6bRZPjGJOzKrNq26LbPCiZav2DU/F1Du/gF9GyGyvwAra52DP4C+66GOkRTXpO9EXdbszmhFvMxMeDWARXtwEHgjgfwqpVuhhfbFULeSya6KFonxmvROf43uLBYOKJB6MV/ol/PX67DK6I8X4XM7rgleRW2uZ4GuCe5FYtglvCreEKPfZiruYNLBNtdttGJvpatIHJkOicj/F/4ud4+FzrnxbY6cai7l+STJnZjAvwSLRx2V8jsAmewXnRxuQ97fEcwhPGLfMLY8JM0jevbS1/n4s+h4lnwZPF4zoLD2CfaPlX4ZpoFXiapuFf+Fm0nzysQrjFY/AavnQxjg/DZdHq5T36PJ52jAmz9v8NfuyS9p4rDu9N+lga4QczJSUl5UFwA/R0YxC/xb/CAAAAAElFTkSuQmCC>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABsAAAAaCAYAAABGiCfwAAABsElEQVR4Xu2UPShGURjH/0IR8hkJC0lKUkqRTBSDxUcpBpvNSJkUBqtYZLFQKIuvQVIWZRMZUCxkkIjBgv/zPue65577Mrmm+69f7/t83HOfe57nHCBWLF8ZJM91RqFyckEeSI0T+3M1k3eyT3Kd2P+rkKRYdrZju0onJa4T2it3rYBayR3ZJRVkiZyRS9Jg5YkyySx5IXtkB/5WyQtuyStZgxYckCRukWHySZ5IP/TBTehLi02u+KbIESkwvmsyYv53QNebgPZMeheQJHRBm/lIaq3YMrSAcWM3kjfyDF2wCv6WyZiPkjpowRskTR8L6x5acY7lE1te1m1sqfrY+DzcbZ40/gHHH9AHmXN88qXu1xaRaXIFXXQbOhSeTsgNKbN8IcmDPUl8q/C3Q4qp98OoJufQAjxJ0fPQrW0jLVYsoUrowkPGlsQx0vudoVu4Yn49SbzJsrOg01hKOskCkvStHTr20o91aK+kYldy/RyQReh2nQbDCcnwyHE4hF5bIc2QQfgH9adDmQo9BlL5T5es+CVHckOST5ext4cgMkm/ZOzz3UAU6rP4dVxjxYpUXzL7TxJcptcqAAAAAElFTkSuQmCC>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADsAAAAaCAYAAAAJ1SQgAAADAUlEQVR4Xu2XTahNURTHl1BEPl/kK5FIFIUBoTegGJBQhJnCwMiAvIFeycRAPkqSFEJCMhBFeUwwkoGMlCeliBmFxPq19nb3W++c++6599TzOL/6d89Ze9+799p7rbX3FakYUGxTnVUdVc1xbf3KUNVob2yBVarV4Znffarq+tPaz6xXHffGFmhX7UzeL6i6k/deDFEdEguFKL4EC50dHVaNCu0nXNvkYM+D32U3ymRQ+Bwptqvsbi50Xqb6ovolNqHNoW16eH4c2naFvnGALarnqp+qU2JhWo/bqrHeWBKEMz5s8g1ZvBRzaJ1vUA6ItY1wdpzGyR3OnkenN5QEm/JCbPHjRtTlgZhDOJYyT/UxtPldOa9a4Wx5LBILtbI5oloannGUNOsTwheHTiY2wvKi6kxom5S0wWmxnG+ETm8IjHHvEzJsvGMf7OzMD2dJNdShutKjRw7R2VicgDzA2Q2hLXV2vGpW8l4PIuKeNyobVZ9Ud1XjVHtVb1Xfg43jhJrwTvVZLMJS1orNK9W5Hj1yYFXofFksHAi5a2JhTAiS/HxG9iTPfbFGddXZcOSG1OoBNYNTAVgEbJdUU4NtiuqNlJQKu8UG6BL7wZuqaaGNAVldjg0W4pg0XpSY5CPVDGdnV1aKjfdeNTNp2yc2F3Y6MlcsCoYltqahCjPAa7FwTXeO9+7Qh929Lo2v8FaxQpZXJXGA4hgrPTWAHf+qWhI7KdvF5lcK0VmcIldTZyaKLQJnWJEKzMSpAYRxHoxJkYnEsQjrtmDjd0iDb7FTq8S8RE9cW7ydvJJiFZjQeyi1SWeBs4R0ZLnqh9RqB5ACpBG3I1Iq6y5QCHKG3PGFKMIOHZT8cMyCcIxnYBaMmYYw8B0/B4oYC8BC3JJa0WqamJccylkO4SxnXRHuSP3cbpfel5hnYjuY/jtaoPqguq9anNibZrjYecp5lwV/CoqSVtMsuCT4iwIXiKwFogr7S81fAxeJ+d74r8KZ3GghG9BwfJCv/wWzVfu9saKioqIIvwEvfpHZ/munXgAAAABJRU5ErkJggg==>

[image7]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEUAAAAaCAYAAADhVZELAAACsklEQVR4Xu2XTahNURTH/0IRERl45SNlQD5LqWemKB+JUJSJUlJkoBC9AQNTSoqEGBkwMBFhhIFSylSZSAxFUZSP9Wudfe+5+953zzn37FdXnV/9u9299lnnnLXWXnsfqaGhoWHiWGC6Zboe6VBmP2m6mRu/Y9qd2Yq4pm6/xztmSGtMDzIb4prVHTPKs1/uA38fxtG01uw+zDXtNB02/TX9lAdiVWbfYHqS2S6YdpnmZbYidpiOmD7Jrz+ott8Avs6a/pi+mrabZnTMKMds0yvTD3lgCdDeTCSV+/9uza5ACMpoboybPTWdz41V5bLc9/LYYEwynTI9kydoUNaZvpumR+Mk9Ys8IPsiWymuyB/+o2mJ2iU9NT9pAEIWH6v7od+aFkdjVWFJ3DNtjMZJAu9D0An+QFAhVAqOTihNQAKn5Zkko4H1meqy0HRDHvwAgX5nuqqa70AWySZBYY3nb1KXlXK/57L/a01vWta0sHm8lt+vVkACNKgQlJRQ4vjlYQkIy2ZPx4w0kEj6E/diSdWGRvTCdFvulL6Sks9yv2OmyZEtBVQF/p+b5ufGWUq9mnwpQtOj1OnYxzrNtaGnxH0lFQSEHkgfyTduGiznMFZAZTiQBWdTTHflO0bKvhKWz5zYUBOq7ozc/9LIRrW/zH4rsUndTW+LvK/wmwIyxkNzZklJOOfgm+qOIVj35YkuhHLjQPZLXl5xlw6NkS2awPTqAWyDzEH9ypNrt5m+qdrS4RMA3/0qlkMZyTtqGsmJZ36k9pmrkK1qv0zQwwI7itksP5rzUJxDYlgmYWuMxT2KmCn3/V7+ojGL1O03Fm2gVJWk5oB6ByUFBJby7xWUoYU1fUnelyYCdkK+zEt93Q4LK+Sf6uOt+bpcVP9+NXTwib9MNT62SjArHmhoaGho+A/5B27Pn7W6IsD7AAAAAElFTkSuQmCC>

[image8]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAI8AAAAaCAYAAACOyA9jAAAFAElEQVR4Xu2aW8htUxTH/0KR+yUSOegIIUWEvBDiwaVDKI8eTkkKIRRfJOFBSZLUcUmIB5LbIb6QRJFyKaU+cnmSiHLJZfzOWOPsuea39lp77bPW7pzMX/07355z77HGmmvMMcec60iFQqFQKBQK/z+OMj1oetj0TaXnq8/oftPZph3jB3Oyq+k2Tex26Tz/WWFrZl/ThaYbTf+YbjVdXOkK01umf00fxg/m5DTTX6ZnNAmQp+W2XzBdLr/ep1UbQVvYRjjXtGI6MGvfzvSA/IHukPX1gWB4M2sjoH4znZC07WP6yLQ+aStsxexiekOefXIImOfkwbN/1jcrZ5oeUz34djK9pNUZZi/Ty/LltLANcJjpB3kmyCETrciDhyw0D/eaLsvaDjJ9a1qXtR8gDyqW03nBTzIYddYQEOh7Zm3UgHur/5jkdpqYx24OE32o+2/lfDVnFm7ghqrvy6xvSyEbUWMNnWEYeDIXk+FP1R8Cg0nNRTDMyvbyOux70yumPeR2Npr+Np01+Wor+PWU6TvTdar7hf0rq7+xzXhfMunuxe7ybL5s+lVeV+LzaNyp5prmJvkAvSfPFEMS1xx6djxkusi0m+kd1ScEmZUlOL/PNi6VZ5mb5f5SGzIWX1Sfm5b6HH6f+vWV6n5hJ2o8MuasdnPWyAPxyerzWnnQP7L5GwPDzP9RngUWRVyTQRoaHi4sqW4/arempXkah5iuMp1i+sP0qmnnqo8geE2z2cOn8IugwGZAyfCZ6ss0WY3M3Afscr9peYBNbLMpGQW2yFx0JWsfk1gmWVrGgDT9vumnpC1qt3xpnoUlub/pQ8cem4x8d9pG+HVM0kZQbVB9GXtR/exGkDCeBGNwnOkXjRg8pDQGhlm5KFiTuSaF8RjEmVJqP2qsPktWwBkXmTKtz86Rn1X1KWwjg0X2ApZvJnDK4+rnZ3q/aT0XiYHAGhy2xQxMuuaOTXpN6ogxuFar64ZI6zzsC+S7ullh9lI/sVQBD5ajBwKoD+FXEEckJyZtkO9Mu4h7S+8XHynQ8/bBuF5unB3AEVlfDsXemurvg013JX0xCMwqZlcbcU1S7LFZH5DaX5fv8njQ16h+iBiZEk0bZNpj0LDBckPhH0cD91Xt0GUL+B0BT+DDs6aTJt2bSP2aBsFG9otrM6b4dXr1OQrrnC4fV+T9d2hi+2158RzPjH8/kV8T7lG/CbSZWAvDqRDtTRwqH0AudqrpCa3eopK5GJimd1JpgZyLdJsWnUvywDpefsMMZroj47o/y681bUYRzBtMv8sf+t3yFM5ndo4xoNBlC6hL+B4Pg4xzRr17E6lf0yA4bpFnMV7JvGs6Wf477H4snzQ5XT7SR5FNpsE2xxGUBmzbA/o+MB1eiddQfZbGuWHwyCq872LGTTsnYf1uCp4+kMGYNVwLW9NqCoJh2mAGHMilgYffTb7PYosHT7HdVXDn9UsTTML95GdIgJ+0tR1btPnIJGRJZKzY6jf5yPEAW3jGlRfdC4OHSObpgoyUFpXzsKzuWohBYunpu51tYgxbQ9PmI5Mhz95NfK3Vp/kLgZrj8+TzWtPtyefgUW15KmS5IYMFV8uXypSj5f9tZIiT0zFsDU2bj03nRE0sq54Vl+TPcWGQDknfTXQ534dIv03vgahnjtT05awvQ9ka2q+UNru8xpi1VGCZZLlsWx4LhUKhUCgUCoXCvPwHcLMWDQHjzvAAAAAASUVORK5CYII=>

[image9]: <data:image/png;base64,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>

[image10]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABQAAAAZCAYAAAAxFw7TAAABOElEQVR4Xu2UvUpDQRCFR9QioIUIhoCF2IqVWIjYJRAISW9nIwqChaKSB8gjpBEtrEIgbaoUCUmlVj6AhZWlENBSPYfZm9yd/JgVC4t88BW7Zxl2785ekSl/xQW8Nq54K0Qq8NZlNOfHg5TgF3yESyYjC7AJD+CMHw3nSLTgC0yZjBzDKpy3wSjyogXf4ZbJyBPcsJPjYBEW+4Rpk3FX52buR5LwWXSXV7H5NXgfG08MP3pLtOCNm+POeKNFNw7mTrRgzY0LsA2XeysCiVqnA1fhA9zzVgQS3XRXtB9tcwezDT9Ei2ZMFjEL90VfTR3u+rHPOnwVLThnMsIXcgkbbrwDT/rxICyShZs2cJzBN3go2uQTv5pRsD95YYs2+C1sI9589PPgkYNfUBwesSza+PQUJrwVU/4f30mqM+OLT7P9AAAAAElFTkSuQmCC>

[image11]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABUAAAAaCAYAAABYQRdDAAABH0lEQVR4Xu2SvUsDQRBHByQimCbYqqDYWKUIWoiWgiKm0PwBdilTpg8EsRUrPyqxs7a2ttJCm1SKaK2goIL61rkLexM5cntYCHnwYG9/s8vu3ogM+GtWcR+P8A4vo7GbczZwrFvdJ7NYwxO8xa3oO/YdX3Atqs/ELh7aSVjBT+zghMlSmcZHLNsANvALP3DRZKlURReWbAB7otmFZHzbtujC33gQfdd1G6RRxHPp3XQIl/BJtEMyEV/92gZ5iK9+aoNQ/KvXk1E4cSu94pzJgjkQPeWZ6KnT2MSraDyJ2172g2vyZ9ENfUf9Io8pvMcdXMBjXE5UBOBa6g2bOI8jyTgM1/jupOM2yEMFb0R/rGMGWzjcrciBu3bBTg74R3wD5x827PdCsCEAAAAASUVORK5CYII=>

[image12]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAIoAAAAaCAYAAABo4cQnAAAFCUlEQVR4Xu2Za6ilUxjH/0JhlGuMKENKE2LClNuHaSgSSkThmxqEZkYRilMok5TckpR8kGshybUcQxhKlFuGOjSRKSmhkMvz87xPe+211/vuffaZ2Zcz76/+zey11nn3u9Z6bmttqWWcnGx63LRX3tHSkvKTabNpo2lp1tfSol1NNySfdzJdlHzeodmtUktLI/eZLs4bW6afy0zfVfoz6xuGt0yH5Y0Zr8u/b6s8dy8WiKR3mR7OtCQdZDyX9KFHursnk2NMl5q+NP2V9Q0DEYVc3MTZpg2mf03PZn3TDDXJatO38rl9ZrpEvetxuel7uWPeK1+PqeB00z9a+KYdbdonbyyA570kN8xTs77FAJuPocya9uzu+p97TLep14AmHipzJrY+75gnM3lDDQeb5kzfmA7s7loUxHoSWQ7K+uBD0wF546Sys/xlS95N3/7yUFr6XIJI8kremIF37afuCLZL1wiHMbwb3zuNnCM3FO5Plmd9zO3crG0iobC60/SjPDRSTFFUkk8xBm4PXzBtMv0qP/fPyY1gi+o50/Ri3lhxivx5n5s+Nj0tX8g16SB5KL5SPhbxjmd1jZgOcDgc73fTiUk787tRZeeYKDCCP0ynJW0PqHvTXjMdbjrW9ItpmdwLPqnGleCU8071b87fcsNIo9HP6hhmQEQiJD9Zfcbw+D5OCHVg9BSCF8xDXKdvb0g3UdBGOmftX9boLtwiY5RqpL5cIU8z6YXYG+q2/Kvl/VTrqWEcofrCEyO7X73FGS9KiiHVpPBcfvtIx8fiYlgr5UYQqXHaYHNm5fO8o2q7zvSUmtP3tgTnfNT0lcoOXAsW/b56w/0P6vVuiMq9H7vLU05uDMDFW+nZpbTDAkZKQhwdr1Kv8Y0CNhrDHVT5O5JaqL/CIVbIIzLONireNd1u+lTzLJwjlfBvCpPB8tLJRhrAiPpxkvwCrfTLKBdJ+WUSm/Cb6fisHYgi18qjCu9FmuT5o+YadS4hB1EpvDNv5jBrelUezUdJHrEHhuqbKjydFLVHbBp1CfUJRNqJsNnERvn9SQmiEieAFC73wjB5PpGF9Mf3pUZ1k8qnhmnhfHWi41FZX8pxckd73nRC1Xae6SN15k5EIB0D60mtc7PpGflNOBErWGt6T27APDctpgciUgR3GLCv/IuoCwifWPwtVR8bVqotSjyh+ir+DHV+PcUwOBZSyNLG5KmXyJ8YCqeqQ6qxhOgvTNdrSK+YAOLk05S+icJEGzbzTXnhy3rMyO+Y4sTHs3BkxmMgZAXWhkKefcpPhjh+KWIPDBtBznrM9LW8AmcyWOXbpkPVKcTm1DGqOjCQph8A2WSiQlg+eZvoQ0rD6inwGIMnYbCkO47r/A19oyr8tgeR6iNKl8BB5+TOdqTcmYkwCEOJ9cexSMvLTKvkhkEfbVw95OtENFvwRSbphofEwzGM9DPsXbX3Ayvv90KcWlgQnhkQTdLPgMHwboyd1ou2FDb9QjU7G2u+QR51iKpR5+GAcYqMwjiFlN10GiRtN/WPHI7SLcNBNFgndzYcg5oi0gXOR1QADI3oQjqmXODvMKo6SoY1VjiNUGO0DAdlADfgnPIQ6SZgs6knbzU9JD9acxID6kbuRuqgAN6cN46TGbURZaFEus3TMKTpnxQVRT3RZ4/q/yWoXz7IG8cF+Y88GKeUlvFzt/yq4kEN/it+yw4IJyeuGLiPaR24paVlAvgPzh8C6ivUadQAAAAASUVORK5CYII=>

[image13]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACYAAAAaCAYAAADbhS54AAACWElEQVR4Xu2WP2hUQRDGPzGCYkCDEg1RPMUiQbtoIaQKWliooJVgK6aw0sLGIk2KdKIWEgJiIaikCSEgQfBI5Z9CBMVKUBsLUYloIQH1+5zbvL25fffeJZdU94OPhJm5t7O7M/Me0GH92UZt8sYcFKf4NecydQvlE1NSM9RZ72jGc+oT9ZN66Hx5vKR6vbGAfdRr6px35HEGtpu/1BXnS3GQOuGNJblAvYMlWcgG6j61RA07n0exN6gt3lESXekz2DMKGaJ+UdNUl/N5VFufvbFFDlPfvTHFJdRfo2pnY+ZeZjM1Rz3xjgR9sPgUPbAaLToE3IVd40VqgfpGLVIn4yDYYh+pKWePqcCe8Rh2Kldh1x8TSmenszfwFnZiuvsKsh1J+j8QrvxaZIvZQb2grsMWH4V1+2AcVGMcaXsdSipe7ACsjqpUd2Q/BYvV3xR6hvyvYEluR/3vYxR73BtjtDPfjadhC2hXMUWJHaN+w2KkB8if9kos7zn/0VW9p3ZFttvUHzTuqCgxcQSWUEhOjZVCiR31xhjVjR8TH5DVlwo+vEZ0qjrd1BBW44whO6HzsM3dDAEOJaa1c1GH+aEaTkXTeZbaW7Ori9Qo6ijPV1ixhw6chI2V1FWGsbPVOwIqzCqsUGO+UE9h79CRyK5FNVqUnGcC9ju9a+9Rj6jddREZ/bBbaYo6x6Md5Q1INYYKPEX4ndQM1e4Pb1wteiu88cYW0KmruTSA246+EPZ7Y0kOwYbuSr9OCplHC99VNRSvok81RNtQYd+h9nhHDgOwT501TapDhzL8AzGAanuRpG9BAAAAAElFTkSuQmCC>

[image14]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAIsAAAAfCAYAAADX7j6qAAAE1UlEQVR4Xu2aXagVVRTHl5TRJxFGFhhoiNFDvUQ9RIJgn0hBFpgmEfVQ9BZSUQ8hmKAQRB/0RRElFYFUEErUg9cStHqNgiCwkIKCoCihInX9XLM7e9aZPXdm7j3n3H2aH/yZc/aes+fMnv/svdaeEcmDK1VrfOE884Av6MmTYJYzVB+pjs+i91Wn80PlBtVB1WHVftVMsf1WygbpzTIl3FIIzha74F/9VztghepVMVPFXKf625XBVcWWNp+MK3ryJTYLrFf9G30PPKS6yRcq21VHis8XqVYXny8rtr1ZpghvlnNVh1RLojJgVOHCxzAd7Sm0SPWglNuC3ixThDcL3FkohhHHc4nqJ7Fp6GfVLzIYUQKzmeUs1WJfOEfOUZ3iyjgGI9/S4vOo4BiIm40baKqoMksYXdgCHRw+x4R4he0y1S4ZHn1mM8sbMnz8ucDxPhAL3GP4/rrqGdXyctW88opYEvCxDPdFIz5R/SB29x0uV02cKrPAF2KGuVSskz3xFBSyoyramuVh1WtinR70guqCaB/u2neievZfV9TVmaXTxesAx+I/dDoeJ7JTLPWkcxcSKbNsFgt096nucnUQpiAC3DramIVh+xqxKfBL1Y9iafdaKU8dTF23i/Xnm6o7VOcXddmbBR4VOzm2C4mUWbiTSaEZYXywy/dfxc7nD6kfLduYJQYTYpjzfEUB7d4jw3FB9mY5VbVb9Y/qWlc3aVJmAe5oNBe6muV+1fdiwWIVjDhVgWr2ZiEAPCZmGIxDwFg3z4+TOrPMB13NQofTZ/RdDAZ5V7XFlQeyN8vjYkM225fFFrHIIli7YP6dJDfLIDgcBZzfVl8YkTILMRF95lP2DWJxX+pCZG8WTo4TJxu6sShjTqbMr2d4CNwI4Nro8pO/zIOUWRh9fYy3XPW56uqozJO9Wcga/pLBUjg0DXhHZZavJyRPyix0NP3D6BsgTX5MhoPamOzNwkmzVhFOki3fKWcamAT3TUielFmA/glxHnwqw5mZJ2uz8IM/pfznQ8DLwlLoiIXAJklnH21p2s5sZiEjulj1otSPKIGszUKg5tcLnpdyvOKfp8RgLPZto+dO/rI93iyc7Eti0wfrLTOF+PyZlFdVPfNllt/Fph76sAltzLJPLHasSsGB93VYxb5X0kZ9QqydK6Kyzma5VcrzLpANfSMWxKEV5eqJcbdUX2Q6FNPH1GUkUNVOFXVmOSpmGDLH611dijZmoW1Wqde48sCM2D7fiV2nKjAz+3Aegc5moaP9cjnT0ltiT0YfkbRrx802Gb7I4RmQXxfaIfX/27eTos4sJAZcCKagptN1G7P8pjog6f+6RSxcYCZIHX+vmJnjFL+zWap+QCcvKVTX4eOmyixMg3QGXCj2UK/qnDy+nRR1ZuFlqyaZXUwbs4yKzmbJiSqzhPUgnppjmmfL1Ul8OynqzNKF3ixjwpslfg0BCDSJwZrQm2V8x5sI3iz+NQSyglWD6loWollWynjelGOV/kP5n5kFk2AWnwkB8QTPfXiod5sML5Y1NUtPpsRmIb0nrSRe4SWkM8NOEbxK+Z5Uv3PSm2XK8SNLHRvFRpenxDK608rVjdvpyZQ2Znlb9bTYgqNfR4Km7fRkShuzMC2xqEjG5BfsoGk7PT09PT0j4QTGmzzMF/lq9AAAAABJRU5ErkJggg==>

[image15]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAAaCAYAAACO5M0mAAAAm0lEQVR4XmNgGAW0AsxALAbEwkDMiCYHBzlA/BaIDwHxFSC+gCqNALeBWBXKlgHiI0hycCAJxL+AeBIQawMxNxCLoKiAAhYg/o+EPwKxJ4oKJFAIxJeA+C8DRPFVVGkGBjUGiJUwIATEhxkgHoMDkJXLGVAdbgbEz4E4GEkMDAyA+AYQzwLifUD8CIjDGXCEI0gQ5HO8AT0KKAMA0PYZLAbjc+QAAAAASUVORK5CYII=>

[image16]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAE8AAAAaCAYAAAD2dwHCAAADOklEQVR4Xu2YS8hNURiGX7lESCJyLWJggCKUTInEAGXA4I8BRYT6xUB/JBmRJLkmGYiZMCCJohigXAZSSIwMKAq5vG/fXuess6yz/3PW3sfEfuqts9e39rp/37f2ASoqKir+X5ZQJ6jT1FvqcfZbZdJWakStdjozqGOot5unRdk7KfRB4/ilXQ01gHXUhczmlMQ0ahWssTdUV/YsHaG+U1+opVn9FDSho9Rv1Ad7ErZZT6n11BpYf4+o/fZaEuqrCzYX9XePmu5XyJ7PwOzqT/0XQgM/FRaSxdQv6iU1IbC1yjjqBbXaKxtOPYQtmo/Kw7J20QLqMGhxzgU2x1rqCjUkNLTLZOoDNTM0kBWwQfygFgS2VtBEDsE2wUcLpHa1WD5DYd5QlO2w9u+GBnIY5soaW2GWIz4R390eIC326R2dglFemdo9C2s3ZDQ1MixMYBmsfblvyC2kzSWKYkxsIlOo97C4p8GUhXPZWJ9lMYf6Sn0OyodRC4OyZOTzt/H3RPrC4tQnWEYuk9mwJPQxNJSIQpAWTuHGZwfVLyhLxrnss9DQIXyXVZLqFIqdinfuUPSnLlIbazVKwLns5dDQIRTPtFHqs2hWzWMgdRX1xVPi03Ph7OrwXXZDo6lj+C5bRlbNQ9cUzW08dZ+a12guhruiKLAqwP4LtEmakBJGmN3LZiesL12I96Gkq4lDt3w1fg29H+eV1JPs90TqgGdzp0lt5Q1QSegVrN5mWByKoX7Un9A7Yzybxqn3X8Mu33ko0amu4noMZd4bVHf2vA02l1xcJlLDvgb7lTwmUe+og9R86jwa070GcZ36ifgmuAtrTGG4UCbUnXJqpp6szKHNUT9y+94m6ja12Sb1wDxvFrWJOo74+AuhHfwGc4O5sGAcQ2Gg2Qa0ii7JulTr21p/EMQus1pMeU3si8hnECxRxNA4b1J3YH2NRb7XJKMLsk6eAm8e4SdYCnLRZhN2aIEvodiXiEuWu4Py0tHxfw47WUJfHnupAbUa5hoKzEXRpPwrjE6P+vPRR/2eoKxd3H3T/YOj2LoFFpY6gty1WfxQfCrqsg5NRN/CzeJPbx7QDlrEWGioqKioqKhI5w9dG6fhq/9zyAAAAABJRU5ErkJggg==>

[image17]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAZCAYAAAArK+5dAAABLElEQVR4Xu2UsStFURzHf0IRstgMShZlsxrNNpMyWEworyjTW0w2WUhhMlAGKRPKaGZTb/MXGCz4fP3OzX2/1Hu6Z1Depz51+p577+/0O+dcsw5/hR48+IVL/lr7LONEyF7wA+dKWS9e4G4pa0mf+UsRfVxFxkN+Yr6gtpnEyxiaF7gyX0CBWnmKs6WsJepnPWRD5gW2Qj6IZ+aLqsQCNnA05FnowiM8N29JdkbwEdfjRC6m8RVn4kQO1BK1RhusVmVHm9owL/ATw7iPN+YLkDu4Yn6XZPlYN6GJeXzHN+xunv6iZt7CTRyw7/3SqdvAW/OjXAkVeE5j3eh783ujPVssHqpC8VGh38ZhGq/hVBpXQsf3DvvxGrdTXrdM92YMH3APj/EJV1Pe4T/yCc0RNNl5d3C1AAAAAElFTkSuQmCC>

[image18]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAC8AAAAaCAYAAAAnkAWyAAACmUlEQVR4Xu2XTahNURTHl3xElEQ+okgMRBkIExNRPoYoCmOKCQNKZjIzkIxkYqSkJClFUgxEIRGRekSSDCgG5OP/s85+d7/l7nPPGbjE+9Uv197n7LP23mvtc57ZMP8uo+XE2FgD13LPX8EluSw21rBRnrN2E/4tEMDO2NiDEXKfvGx/cAIEcUiOix0NmCxvmk+CcfrOQvkqNrZgi3xjPk5fmSYfycOxowWs+HH5MHbUQaVPqX4zwJisrymr5Ve5LnYERpqnSCk1tsovsbEb0+UZ+VbekevlFbk3v6gh++UHuTh2VBD0bvlOPpD35OwhVzhL5afY2I1n8qR1Cuyb+axXDF7RnFPyuZwROyq2yadyvpwlb8hjQ65w5srXsTHCSsWbP8qLcmxo78UEea2S3xEmxMQ+mz9zvHmashuRdG0xBm6kKMjTnO/mk2pLr+BHydPm4+N7K9dGCr7bOD9ZYr7KbF8OaRMn1IRewQOrvUfeN58Ai5cOiZwUfKmgB4PPHzRJDsiZWVtTWNmz5jXEkRkhVVZl/79uXrgLsrZECr4IBcr3BwHDPPnEOinDK/qI+UDp5GFHGJQ+TqSYXjvMTwlOixwmRnHmu0xB8j3TjXTk1sKsWYHz5oPftU7KzJErzXcIgZcPxQycxRuq34m0m0wi8ljelifkVbnZymnBovQ8bWCq+QsDGTzWAAOxS1Q+gR+o2tmNuOUp70mfCIHyDHaSf0uk51DcjUmrlh9PaSDgoQPmJwRpU/r44mvyRWxswSLzb5u1saMOtpoTIIfTgdwGBn1p/vJaIzeliwKs6q3Y2BB256i8YN0X5heWmweSZGXjjaRW+iundAzmEAQ71ua7nGu5p1TEfWW73BUbazho5ZfWMMP81/wAwgNxpQiEkq8AAAAASUVORK5CYII=>

[image19]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA8AAAAbCAYAAACjkdXHAAAA90lEQVR4Xu2SsWoCQRCGJyQBQwIS09rYCykEBQmplJDaR7C18zls7C1sEkSwFhQkTUjIa9iLdUjM97MnuHtmvVr84Ct25vZ2ZnbNjpYLrOFVmAg5wwJe7sRucYLFndheurjBXrK+xzoOsYozfE5yKV7xB1vJWpXMcYmf2MTzJJdC5eaD2HbzGz6a+2EKBXNh0DL0rMQC1/gU5FSN+t47bQXH5vpUeSOL9BXSMDdN3ecv9v10HI1+O4hvfPDT2Sjhh6WnfRD1PcUy3mAbr70vImjTytxVqeyBuRlkQn3rWerUF6z46Th3+I5f2LF/XlEMPQadfOKExx+/NB+U4EhuTQAAAABJRU5ErkJggg==>

[image20]: <data:image/png;base64,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>

[image21]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAJYAAAAfCAYAAAAFvjTyAAAFAklEQVR4Xu2aW8ilUxjH/zLKaRynQUODnMkUg4hQiEQylJrJBcKFzDSmGSn6bjRSzsdw4ZBcIC5QpHwODTUX00wZUpMZOSShxAVyeH6ed7XXXrO/vd/T/vben/Wrf33vWu/e37ve/aznedazlpTJdLOL6TrTaaabTId2d2cy9Vho+tx0iWl3uXFlMq2yzLRb2pjJxOxpes70lWmL6Z6ifZFpk+kn0xdFGyw1rY+uM5m+/G26IGkjn3rAtEdxfZjpWrm3OjfclMn0A8O6LLrGmB4yHV5c7216x/RPIYwukxnIb6Z10fXVpuuj60ymFp+aXpSXFdAZ3d2ZTD2mCxHyzpEb16ywn7x+MRdgLOPE8abHTU+Z3pWv0F4vrtHDpotUbYm/r/w7N5vuNL1metA0L74pgpXhNtOx8s/NCpeb/pI/5KRDxZixnJe0j5IFpivkOc6fprtMV0V6T54wb1T5ijffx8oNo6RcgMGiveKbIu42fWd6RN1J/FDZ1bS/ZtE9DpkqM78M/BDM+Kbw42JAvSIDRkffjrSjD0fK70/LCL1gDN+ajko7MqOjDcPCk+BRMJ4Uwtcr8j7CVVnYfuF+ip2DOMB0XNpYcJbpftMpaUcTDpQndHMBxsF42qYNw8K7EIoIhSkYxna5YT1atBE9GEvwbuk14AHfTNqqcqHpeblxXZr01QYrZrB/mG7T5IZCQvlK0zemX+WJbZu0YVjksTN5pLXyPnKlxfJQ/oTpY3n96Xx5ueBteeIPGBNGFdem6vCM6WXTqfL32BgeHktllk/LB3xQfMOQICQwM+LkdZCYTf2MfoXpSfmYeNGEiDZpw7BCfkXIi2ESsNjYoE7ifo08yd5H/tuEvivlTiAk6OwDNjUGPCRVdt5dK6tpXj6akg/4lq7eyYJnZwafafpdnb2vOvByD0nE/hmzOm1HHDcZBOWGH9V7v64XeDCe42x56Ayhjv+H96rC1hL6rEdbrFoT9RP5oBn8pDOl3slxWUii75OHm1icAMBTpO3o/f8+2Z/l8ufarnKJdoAzUU3GM1KYRS9p5sLapEAYZ+Z9nXa0QNNQSB4TwmDZ9xxWir2S/bGHh8ewLpbnMBzwGjYnmn5QZxe9jN6Q5xP9IC/hXnKGk+WV7LZoalgUPnm2Kqcyw0oRTRysBJhNGNXtppuL9sXyKjyGdpLpZ3niCHyGBDlUeVmt4Or5jrUaTekiXYC8oE6exVjChCHRvbf4uwpNDIv8CKNixcp2SllWq7oxVoF8ja0gtpRYUbcKP8iX8jzhMfnKAANhz2m66CeB3CHPwXhJC4q+sMwNfUCtpt/qbZiski/N35IbE+CRCfNHF5qSb6dUpY5hLTH9op29L21l4P8xHibyMHhafrDvGNMHKr+VVJqF6l5mBhd8R3HNjPnQNL+4ZqB4BjwZxH0Y4ShhHIwngPfiWSlZEBrrFk/rGFZTmNStLP9n4CO51wJW003rYQPBcJhVYYlJAslGJ57qCO1saITSQOsutSG8ODxqUzhmUsfTjTPfqxOaeU9DnziEMupCr5rWyA+HPStfhpO3EGZIRtfLE2XqHLfKC3ohBI0TS003ynNICsIndHf/7wmpz6z9dsEV8485+RBXeGkjrHAPeRnerGkFeJgQHkexqJgEWNjMheNSmTHidPkBwYPTjkymLoQ+UhkOIsBUpyuTqQ91yBvkK2aKy5O8V5zJZDI1+Bf0zQDWz37EPgAAAABJRU5ErkJggg==>

[image22]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEQAAAAaCAYAAAAOl/o1AAAB+0lEQVR4Xu2XzStEURjGX6EoUShEiZQUJUopZWPBgiQLewsbW2znb2BjNwvFRllQvjY+ltbYUKyUQhQb+Xge59zmzpn7ce5mxnB+9VvcczI5z7zvee+IOBz/jQqtA5TAFThjbvwVeMB2WGluhNAMj2Gbsc6K6YN1oj6zKOmAafgM+429MFgZrBDv0OVwAT7AR/gFr+Cw3i8KeuAFfBF1gFexC4RVsAVH9TNDWYRrsBqWwln4oS06muCt2AeS0nqMiQqULvnWp/TakG8tELO/zOd8kzSQPdjte+6Cd6KqYcK3Pi4qEAYWygC8hmewEy7DU3giKphCkDSQbcm9fNlGVcbanKhAGFggNXBHMsmxd+fhrn6OSpL9Pp3ASVj/85fxJAmElWwzahnOkahzlWVvZeCB6Sb8hCN6nT3Gm75QJAmE33pce7MLnuA+rDX2AjmHN6Jm+W/ANhC2Cdsljku4KrltFcq7qCoJLaU8YxvIIDw0Fw1aRY1gjl6P2C/eHE828CXIG202+lsyDttAUhL9fzfCA8luKd4lUZ8pDaJaxvbCywe98B6+SXiIfAnbkOCq5rDwBkOQ5vTJgmmlJf5iygdeZZgHMCuFIaxL+HTxpmaYkbC3+N5fTPBHH+8OVrdD1LsSXyAdGk5EThiHhhXi0PA3Sou56HA4HIXmG7alepH4xjgvAAAAAElFTkSuQmCC>

[image23]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEQAAAAaCAYAAAAOl/o1AAACK0lEQVR4Xu2Xv0scQRTHn6hoiGihJIixUIQQoiCECELARkQhgoiFYGlhCtsgBIT7DwTzB0iapAlYKBhIikQb0VYlIMLZCNopaKH44/v1zegy7u3ONnc5Mx/4gPtm7s59997bOZFA4H+j1hgAFfAzHHcXHgu8wXb4xF0oQAv8A9uceDVsho2i71mWdMAFeAzfOGuFYGWwQuxNV8JpeAi/iL7XEXxv1suCLrgDT+A1PBW/hHBuLMLBSOwD3Iat5ppJPoCXdzvKCJb4vvgnJGe02AQxqesmVgd/m1jq4HX7y70uNlkT8gN2OrGnsA/Wm2vOmLxoQhLpgXtwE76E83ANroomphRkTciSpA9fthCT8ctdiNIAl+Gw6Gb2LgfRirkeut/6APb7WAZHYNPtK9PJkhBWctKj9pVo+5yLftm2YmLhDdPv8Ar2m/g70SFUKrIkZEr82pvVviE6VFP3cxrnRfvsX8A3IWwTtosvn0Qr/7W74HIhWiVV7kKJ8E1IL/zpBkXPIKxyyr8tdjSwqhLhphk3mAIPQXydr9GWTMM3ITmJ/785U+znTkbioyaWmJDnoi3jO/CKQbfoqfJMCieRh7BvEl/V9hA2B2tM7BncEk1I4gzhN7AgKZuKhK0Mt7rcSmESvkry0+Ut3IV/4azo+/JJ8zG6KQ72GH8AlRP80cfZwepOgvfGRE7AAdHD2qOEZyWeKQIGPhH5hAkYWCEBA3+pvnCDgUAgUGpuAAazeY3D211PAAAAAElFTkSuQmCC>

[image24]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABMAAAAaCAYAAABVX2cEAAAA8UlEQVR4Xu2Srw9BURTHjxnJJNPZMKqkm0ZQFEUSRcU0BdE/oNh0UXiN5C8QzIwkChLfs/tsx5kf795m89k+5XvfPTvvnEv05w0FmNChK1NY1aEtGbiBQ1iBfTiHUfmRDTm4g1vYg/GnUwt0ZyOy6CwGwzoky5ll4Qru4Rk2YEicB95mGZ5gh0xXXXiFJflRECbwAosiq8MbmV+z4gA9MrN6MCDHYnyJL0uWft5W+Vf4Uk1lvADuOKXyj6TJFGuKjJcxhhGRBYI7msE1XPge6fU7+wrPigvy5aSvUyHengfzKneC58UPVT4JZ1pkiv35de5W2io60mSQOQAAAABJRU5ErkJggg==>

[image25]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABUAAAAZCAYAAADe1WXtAAAA+ElEQVR4Xu2TrQoCQRSFr0FQMPgHYhJ8BfENLAoafAKxCAarT2CyGOwGMfgOhsVqttsEu0b1HGaE68LKrGNzP/hY5gx75+5cViThS2rh4BdMw4EPVbiEJ/vk2psSXIgpOrdrL4pwD4dwDCd2zTySHMyEwwic7rQF73CmsjI8wgMsqNwZFnvAnsoa8ApXMKVyZ3bwDOsqG4k5iM+vYMFAzL0SdraBN9i0WWzYUV+tWYgFWZgHdNSeE+yORbsq43Rfn56Fa7XnBO+RBQYqu9iMB3FgW7XnBCfPqbNj/nZ5m6dhxeax4AuBvE/dGxbj5GN384m2mLtL+Deehswm9jHBTx0AAAAASUVORK5CYII=>

[image26]: <data:image/png;base64,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>

[image27]: <data:image/png;base64,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>

[image28]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAbCAYAAABBTc6+AAAAg0lEQVR4XmNgGAUkA0YgNgfiFUD8DIhfA7E2soJVQPwDiBuBWBWIhRkgmsCAH4j/AnEwTAAdlAPxeiBmRZcAAR4gPgDE/9EwyBowkATih0CsBBNAB5xAvAOITdElkIErEM9iQHUDyMso4DoQ3wHiuUB8GoitUaUhfgb5HeQmATS5EQ8ACy4TcCzBFrcAAAAASUVORK5CYII=>

[image29]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADYAAAAaCAYAAAD8K6+QAAABz0lEQVR4Xu2WPyhFURzHf0Ipyr8ik5dBBpvBYpLFgFWZ/ZkMFtkUVgtRUjIYxECyKS8WMisDJSWDKMVC/ny/nfty3s/98959l546n/r07jvnvNc5537P714Rh8PxV5zCG/gMN1VfMVEB2z2rVJ8vA3AXfsIJ1VcslMIHuAXXvevyrBE+lMAN+Aa7VF+xMAa7re9tcErM3APpgC9wG5apviThf8/CVt0RQb+YNGnYNqobbdhpx7BBzK3/DaYlYjI+zEnwwhjLQNbExHAYHsFH+AR77UEJwXTs6MYIOPmghaUlpJCcixl0AlOwFp558jpJeCbmvc9cYCXcl5gL44BJ63sLvJOIH3mwMjXCpjzlpi1712FUwgOJsTDunK6GmcPKbEfRCS/EPAfz8RW+wyUJmJhFrCgyaldidj3DIvyAPVZbknAzj8XEPhfCigcfU76x5mHWZf5avs8Xo5J0hWQiqnVjCEMSvDD7CGWxKj8fyvxBH2yGe6qvUAbhgm6MgHdkRkzsM6TEVHPftw9mMw3rVfs9PBTzDmk/7QuFE1yReBFnEbmF43AEXsK6rBGKGt0gpsQygvxMEi6Mk/Hd5RzgGwvvOKOZ79uLw+FwOBz/gi9qCGJtfWvtFAAAAABJRU5ErkJggg==>

[image30]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAD4AAAAaCAYAAADv/O9kAAACAElEQVR4Xu2XPyhFURzHf0IRJQwig0nEhFISi4GBQQZlMaGUMqBMrzBYDBSSksEgBoskBjHaZaAkMRkUFvnz/XbO4b7z3Pfn9jy8zqc+de/vnnvfPff8fr97n4jD4XD8L2q1+faBdCUTjsAtuA7v4WzYiDRlCD579qvgLczwxP4sWXAaVtoHYtAF3+G8FZ+Ag1YsgmKYYwd/gZDEcbMWM6Imzol66RSV9r6UwztRqcLBhgZ4Dls9sZ+mHu5IYs2Jk/Ob+JH4XCtXVEPg5G/gpqhGQZg6L7BZ76cC1uQcHLcP+MAs3ZUAE++ALXANvsE2Ha8W1Rm3RdVeULJhCSxN0Bq4pLejkQcPJcDEDVfwFBbq/T75/mKJ0iiqXK4D+AoXJcaNS8BUN/BENgkD09ybAamE6d4PK8LDvvg1t264ITFeaTyRaW84EVXzrH2aSvh6Yt3Gi8nOVSvOB2E/jAi4uu16m3XDCzGF2Pz41EgBPJCvxjMqqgsnk164IDFWyYJjp+CTJ1YBL0X1mKjswQdRXf0MLsNHUXU/pseERL326uCwHhO1fhKEE1iRYOXFxWKD5mfrALyA+2EjfOCP8iOGXZSvCLNPuW265zHsgWU6nkx4vSKJY5V84PnMGKY+v/6Scn9c2SM4acXTHj49ppLp/ObfUNPniDTHlIDD4XA4/hofQe1l1K+qIaUAAAAASUVORK5CYII=>

[image31]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABQAAAAZCAYAAAAxFw7TAAAA/ElEQVR4Xu2TPQ/BUBSGjyCR+EwM4iPxB2wmYrAaLOJniAQJiclitlrEaLGaGBoWf0JisPsBIrwn51RLDFWJGPokT9pze2/ue3pbIg+P/yIJI6+DbgjCKYzCHTzAlD6rwAtcau2IEsmCAjxDg6ykA3iDXa0dUVNHJItbOh4g2YgTctKP2ZMk5KRMFh7p+RV8BKfjFk3s7fpg2vbMEby4bqtXZLXLCTkxE4MTOIMLkq/jLfaEnOgKTzAHGzoWh2vY13kdWNT7tyRIWjNPOaQ1X8NwA7ewCTMkm7iGNzHg8GXcNZxmDsda+2Eblh8zXJAn+Zt6JAdSpS/b9vgBd6UAJ3ixn0mBAAAAAElFTkSuQmCC>

[image32]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAC8AAAAaCAYAAAAnkAWyAAACLElEQVR4Xu2WP2gVQRDGv6ABRYkE7dKpIGphZRFQKwUttBBBQfsUWmlnEbRIFVCwUPAPkoCNWCiilchTS1sFwS6NoEhQsFCJ+n2ZG9+8yd7lJI2Q+8GPx+3M3u7tzu07oKNjdXOAPqRzQV3frLxMt//NBjbRSyG+nOcWewEn6L1C/EgV308f1MRq2Qm78RX6jp6prt0v9De9QIfoYfqLfqQzsEF6Vc43Ogl74Ed0gb6G4ePoAebp2ep6rIrr9zR9DruXYluq2LJM0Wu5Ef3Jfqfj9C69TdeHHPXVgFq5taldbRGNkfMi52FjtGYr/QBbncxBDE7+KmwHHO/7k+4L7eIinQjXnpvzHK30K7onB5rwCW7MAfIYtqoqj2F6aDCMY7D4Wyzd5huwezuem/McPdQLOpoDTfi2Z0Zg7dMYLJNIXcmU8Ny4cxHtkkqyNevoE/RX19UL94Pu6KcW6cH6xvIooV3tobxIQg+uBdBL2xovmV5qF1ohDXYfVjIl6komE8urxIpKpnTSCMU+o/wyi38tmXz6OCsqmeMp5jRNXqXQpmQ20GewXB2FGT24dvdUDjThR1fd5FQqGlAnTumFVZ/SEZmJkz+aYkL/rvpz2pwDTdyC3fB6aFtDt8GOOcX2hlhEA83Sp2hXp7vpJ/oyte+iJ1F/Ai1BfwJfYZOr8w363yWRpn4qQZViHVoIfTvps+IO7HPk/UDGf45KUceh6ltlp53u6Ojo6OhY5A8cCZk8r5Z9hwAAAABJRU5ErkJggg==>

[image33]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACcAAAAaCAYAAAA0R0VGAAACPklEQVR4Xu2VTUhVURSFV1hk9KtJEQVBYBAGBoJINKomIjSoQYENmggNnEhIEBiCiDQVgxAhGkQ4iqAmDfKSo2gSEQQ1KSmFRCRQsCJrrfY5se95enHke4O74OPds/c99/zsnweUKlW72kpmyDfyhRzNu6urLeQm+UUysivnrQFdIH/IaOqoBWVkgZxI7JumOnKA7E8d1ByZJrsTu0K8L7FtRJqzoXnaVC/sZl6Sd6hM+jSk28gI+Up+kDHn20ueuHGUcvcSeU/ekA+wXL4NK7o1dZV8JM1hfASVuaXNKe+irpN7ZDt5SGad7zxZdeOoQbJEusJYB9R3n5H6YKvQZ/ITtqEWshN2m1HHUFmlPbDTpoWiRbSY0sDrIFkkJxO75nYmtpwewV6KfM+7/20gvUlJYboPazFngk0H0cayMI66Emz+gHrWu5qzrnRTfeQt+Q3bYJPzDyMf0qjD5BN5TRqCLYY0PYzG+o6XKj9DQd88Ts65cSOsKmPL0MQsjJWLZ4Nd0m3p1iac7RbscBdhtxUXfhBsXhqnG/4v5YxCqkWj2pHPF21KVbyDTJI259PzMqxSFeJrsJtXDh+CdYAo5fIQ7L09sM3qEIUhPQULyzh5AfsPvez8OoAWnyL9sI9H6fkGbENPyR3STVbIK1hL8VILUdvR7yCsQJRShVLT1Un16xePkm09n6TQab4fqzqLFKu86tLtdCQ2FchavXBTpb73GPlbaiXz5LmzVU0K+QDsL+suOY18ky9VqlSR/gJoWmwmPUwvHwAAAABJRU5ErkJggg==>

[image34]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFgAAAAZCAYAAAC1ken9AAADvElEQVR4Xu2YWahOURTHl1DmeQxdlCTkwRSJFEUyhLrKi6J4IA8elMKVlEgJpSRFSYkoY/FwDeVBkQfd8kSJkJTiRYb1s8/q7Lu+802+4ys5v/p3v7P2GfZZew37XJGCf46uqmWqQ6qJbuxfZqRqt+qUarsbaxrDVedV/ZPjRarT6XBT6a7q7Y0N8FCCk2GOamc01jSYwAvVxuR4vepIOtxUtqravLEB3kmakbzn2WisbsZ4g2OAaoKEKInppjqp+qlaqbqsGh2Nz5UQ4aSZ6Zxqqmqds6P9qn6/rxQ56MZWJfZy3JAQaXnRK/o9XepcvGGq76qvyV8c5CHt76oeq4YmtjWqb6odyTEOP6zao+qQcB8iuEsybpBeryRNuRgiI+v5sEGCc/3CZkEE/w1452feWA0aE1HZR9Uu2S9IhGEn7Y0eEiLldXK8WHVV1TPRPtUb1fhk3Fgu2Q7GcVckPMfXT7Lqpmqss2dBL/DPzINZEuY3wg/USiUH40iidZ6zH5P0fCJzbzQ2RPVANS2yAQ7+qJrk7CskzSDmEsNibXG2chAMlKs8aVGdUA1KjtvSodqp5GAi7ouE+hODU+38JRLKiO0iqNOsuB0bM6X0XoNV11QXJNxvYDQGZIZ3ehY4lnt4uJYsNShbPBPFJYwsIgM8vNcm1VoJC/hHJaiSg3GIdwqYg+OXZ4IzpHytJH25hkg2cC4vi42xuDm2Su0RyXzanG2chDnZXB9JKGFAELxX3ZaQQeZsztuc/M6NvBxcDWpv7GAWgpcDc7A9hwZ8K/ldDTLljpTuHsxRVs5olAZzITtpXjGcl/tet1kOJpriF6A5WrRzf3sO0VRP7eXDhkyw6DTYl/eV0A8+qaZEY/QUeou/hvnFDT0XmuVgzjUHW+01zMFLVZOTMc6pBotBEyqX1jRUGmu7dJ5r3EMMMiGrCTdMJQdT5H9IiJIYPoWzzq8G1zyRkP6UAcNSFnute16g8ZyR0j23YfO0UgSjVC8TxRyQdKEWSI6OruRguqZPG9sHk3b1wr1YsNXOztbuueqDhAiuFSKdXUw5+EB6K533xwQLc7gU2ez5NEYi+bp0LikN0aJ6KuHlfeTQ1TtU9yXdds2WkM5H7aQ64BkXpfQ5tsj1Nhh2AX5rF/NZQjAQFMYuCfOIy4qVEs5rldAYa93B5AIOmS9hP1jtfxaVWCjl05n71wOOrRZlRCZfrDEsZrw3NmyPXG5+/x2UhjgyC3KEKDvujQX5QTO6540F+bFNSv+ZVFBQUFBQIL8A/7PF9i9Z2UwAAAAASUVORK5CYII=>

[image35]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAE8AAAAaCAYAAAD2dwHCAAAD8klEQVR4Xu2Ya6hOWRjHH7mHcY1k5NBISJRbNL64Rc1IU2pcikh88Mkll098kPBFMk3JbRKSe+P2YdIpJUVJkSJ1Ri6lfCCUZlye33n2cp53nX32u9/3HKec9q/+nXevtd991vqv53nW2q9IQUELMUK1S7VI1TXqa3P0jBuqpIvqb9UJVXfV76pPqnn+prYEkzwVN1YJ5p1T3VX1VY1XvVNt9DfloZ3qp7jRQX9/1RRV+6hvrOqYar/TEbH7GaBvR7Pqv2WscO0HVYtdXxr8/5NxYzPoqOqUfCbiiDwiMBeYMkp1QVVX2vWVGtUN1T2xST5SjXP9/VTzxZ7xWbVaNUNsYIiV/C/pO5TcH5is+ij2bIwc4vrS2C7lDa4WUvgfyVkWxogN/L3YxP4t7a6H6GFip6WhmO5QPRYz1bNK7Dmklmeg2LPpmxv1wWWxtCnHANVV1dC4owUgiDCuT9xRjpDraebVql6pRrq2YMZ9KY0ijMEg+j17knYUR800segsB5Mjar9FMZ8gFhAwUbXS9ZUly7wXYu3eECKrVuw7fDcQnuONhiuq22Lm+WLMc8676yyINqKO6IvpFV2zGHH0E9mIRfBMUl1TLRRbWMaTlh1NkmVeaE8zDzN+de3hOd5QUp3BkBKxeUtU29x1Fkxsn5ROns/rVA9Vf6p+UO1UPVP9n7R1Vv2ieqJ6q3qgGs6XlW7SMK6gN2IbYG6yzGP3yWvej6qnYqEf+E1skn+J3c9foJaeUQ1OrstxVvVz1EY0UouJqLDpLBP7f1vExs4OTrpDmOfh5LpFyDIvbCR5zKP+UQdDG7vuhuQzk+H+S6rRYjtbnk0isDVuUJaKlYhBqluq3q7vgJh5c1zbzKRtr2trNlnmVZK2oX2t2JmRWkeEAenK/fT/IZUVfo4OvhTEYApmeTCTLCAbAhxzGEPuc1wessxL2zB6qK6LHXF8igbzNql2i6VsAEODeaRRnh02wME4652ThYl3cWoXUc4hHViAm2KGku4tRpZ5rGBcRMNRpU4sZTzUtDuqo1I6YSIU8+INJQ9ZaYY5mBQXef4XpSLAAnwQe4/toJrq+qqG4kpd4A3gZXLtIf2eixXZEC2bxUzg7SCG1CCFGKAnLBCH60pgbGGTSYNNhLF7qH11UrqwPIMsGiZ2PImPMhVDBIUt2qtWSh8+XcxYVo16QboukMZGAymU9o6MeUQwm0heWIDjkl0fl4uN2VMjDREWIPJfqy6Kza9V4Uw0W2yH43NT8MqXBinMBLK+G0NtaupgHCAb4lcqFjXUOg8BwbMqqbffLWkH44IcEDn8bhcfjAtysEaq+FGywFgvjX9gKCgoKChoZb4AGFXddcWO/TcAAAAASUVORK5CYII=>

[image36]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAsAAAAaCAYAAABhJqYYAAAAuUlEQVR4XmNgGAUDCRiBWBiIBdAlkAFIkRMQ3wDiK0D8FIglUFQggRwgfg7EVlA+yPTlQMwCVwEFnEB8FYhFkMQ4gPgrEBsjiYEBSGA+A8QpMCDOgENxOhBHo4nZMGDaBjZtKRDrIwsyQPzQgCYGtgZknS2Uz8oAUfQOpgAZgKz/D8SXgHglEF8E4uNArIasCAbmAPE3BojvJRnwRIYgEJ9mgHiEINAE4rdAvAZdAhtIZoBEK0jTyAYAm8obSufDeVYAAAAASUVORK5CYII=>

[image37]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACEAAAAaCAYAAAA5WTUBAAAB10lEQVR4Xu2VPyiGURTGj1AKIUpCn2wy2vybDAyUf6UsTDaDkkKyWA0yWWSQgdWC8pUyGygl9bGY2Ezy53k67+He9/tc5ftM3qd+g3uOe88957nvJ5IoUVi9YAdcgwsw7Ic9lYI1cB/B/BY34bdKgTGwDt5FC/pO4+BJNO8cTIgWVjDxhs/gBJTHYqZtcCpaxGQslreaQBpcgQfQ6kVVPREv4AxU+uH81Qf2RAthNzq8qEgV2AILol3Y8MM5VQ3K4oshLYoeQD/wkEE/LLOifjgQjY/4YU+j4BZcgozo3vOgxMnJEqvdB92ivuAhc068HWyKGjADHkGbE3fFHBq3M/qbHeR+LD5YhI2CSewA/2kXFInenl0whUbRDG4ku8A30TOCslFQ9AI9kQYVoj7gbSh2LDSKGdG464Ma0e41OmtZckdB8VXwddyJ3oyvwcSNQqMwP7li7qH8YFB7mlZpnegz5WH0BUdiYktDTzNXEfyWsMsc9TRo8MNqIn71jkC9s87NXsGQs1YLjsEUKHbWXfWLzp/i3qui+3DE/LKuRLFPsU28LSs3zHCsnF7gRgOxHMN9PSbmL4uams9zCXSJfmF52dRX6t+LLaepTexyQX9fEiVK9D/0Aa6OY2eANb7WAAAAAElFTkSuQmCC>

[image38]: <data:image/png;base64,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>

[image39]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAAbCAYAAABxwd+fAAABI0lEQVR4Xu2TsStHURTHj/yUQUayEMlkU4pRDAaGX8rAYrMZ7fJLyiRllJTJovwBNlb/gsQkk8HE5/vOe3Xeza/3KKb3qU+9d+6599177nlmDQ1/ywD2psGfMIV3+IivuI49pYwaLOIL7pjvZhc/cC4mVTGJz3iKrTy2gp94XCTV4QTfcSbE2uYLnYdYJU94a17kgo79YiFNWE1iKrY+MJ7Eu6JdvOF0Etfi2+F9wXzXZ3iFG2EsY8J80maI6QaPsC/EHnAsfx7FgzCWoSNd4j3e5OoGY0PqeIc4gvN4gUthPENF1WKaOJSbdvWyeV+t4Sz2l4f9WGrCeFvfobZQboH6bi+8Z19SfarQb3JtXmA16D4OxoQt8x3VQccZtvIFNPw3X+N0LQps9f3AAAAAAElFTkSuQmCC>

[image40]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABQAAAAaCAYAAAC3g3x9AAABHUlEQVR4Xu2SsUoDQRCGR0xQUVSIKEFBEC2sLOzEUnwACxsfwEcQUohNGmt7KxH72IkellpZpLQQBHtRm6DxG3dWJ8cR7qwU7oMPbv69m2FvV6Sk5O9RxYl0+Fu00TXe44zLly0rzAo+4wWOunwPu67OzTF+4IbL5vARb12WmzY+4YLLtLkO0WGF6eA5DrusKWG7Oy7LjX7YcPUYJviKqxKaDrn1vsxKaHiEA5ZdWZbgOG5ZPo939jyIh1i3+hv9V+9mC89wTcKAF7yUcEcreIo3uIQHuG95D3o1diX8P5027dYmXa33U+/kCW5iLb7k0SZ6GOvphQx02IP8bD+TeNem0gsZxIOKpz4iYduLVn+xjW8+yIEehjYv+Q98AijLLaNiv5BKAAAAAElFTkSuQmCC>

[image41]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADkAAAAZCAYAAACLtIazAAACDUlEQVR4Xu2WvUtcQRRHr/iBovEDCxGtbELQLgZRrIWQTlJEbAX7gIpiyvRiRCHYWIQUsbBRECxShBCwyn+wSMRKO23EJL+TeaPj7Lr7ViQ+5R047JudmZ2ZN3furFnOf6dbvpMf5URUF9Nkrt28bI7qMs0nWZM898rhoM5TJ9fkiuyUP+X6tRYZ5olcCMod8m1Q9jyTx3I8rkgLP7BqLgwOEreSMi7LMVnvO9whhOpcUG6RG0HZw+JO5ZTclYt2y/m8lAXZE31PKBEmf8yFTRroMyJf3+CorLX0i6QN4zNHYPcLVjzXiryX27IxrrCrQZhUGtIussuKF0nkxEya28nnSZk+YTkVZKo9uz6gh93bNLdIJnWX8ELDBMJLnA7KHpIRZ5KXA8zzSPZdtkgBjenkfySEkCiYW6TPgnyS5TxxuRp2zF0NMCD7k+ch+St5bpM/zO0oY5GRP1v64/MPQrXUmeM+upDfzaV3eCM/yFb5O6gjORAN1d5fhC3Jj+TGYsrBzg/aLZIO5+CruUX67Ion8pt8ZW4iwCBfzO04ocu54I03mMvIS3a125nC30HsSiXa5WzyyULDRMV58mGXOYhzdrEQfV8JEkSpRJU5+Iexb26RpbLaTfhkVPU9dR9wz3CuzuSLqK4chOq5FSeqTDJjbhcP5dOorhz8v6Tfo4aMTPLJycnJycnJeYD8BRBuWZFOi6jLAAAAAElFTkSuQmCC>

[image42]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADwAAAAZCAYAAABtnU33AAACBklEQVR4Xu2Wz0sVURiGX1FDSbQw0KhNbkRoZxGG6zCkTQQJtYkWLYNAxUDc1C4iUgxctmlRCzftWoRIm1b+B5cgwiB3BSFW79s34xwOc+6duc6Fe/E88DAz58y5c77z4zsX6Ewu+gWdTBe95hd63HPuz9Jlep8OOuVtTy89QSfpT6/OZQpZwDfoX/rAude1o2gU8AqyJT1KH9PzsKB/wwakMBN0nW7QL4mbybN8CVtumo1WUS/gEfqc9vkVZIu+QpN9u05r9JxXrv21Bls6PV5dCLW5Sm8FnKbdh2+HA9b3ntELfkXCXfqdXvIrivCUvkf+SC7CAlayKEJVASvQJ7DfyyNt9wbFJ+M/J+kHWGA++qF3sIC1vFpBKODbdMZ5Vl9e0106jqyd+q4YCjNGv8FG3kdLvAYLOB1pXYfTF3KeyxIK+AU94zxr9WkV7sCSlvq7j/yJqouWc94eXaIH9BPsA2KOrsLOvz9O3U00MdINCGVfJSnt26ZW3AD9CAs4zdJyj27TWWT7TSP8Fjay+phm5QrsLFVm14yE9ltZhmB9qxwdSz9gs9WIU3QhuSpoN8kpofUn91UQmt0jcwc2uzWvvBE69EvvnRI89Auq4DT9jOyvWlHSROaf2W1Pmh1/0cteXT3S7OgnubZnHja7X2HnWlEewdodG5Q9lbgikUgkEolE6vIPtyFbeY3VXn0AAAAASUVORK5CYII=>

[image43]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABQAAAAZCAYAAAAxFw7TAAABCElEQVR4Xu2UsQsBcRTHn1AUg7LZZJHRJEazzSCbkkEZKMrkb1AWkUwGyiCT0Wa324wmgwXf1zvdebrh7gwGn/oM9313z+/d7+eI/nyLABw7sCaP2dOAKZWd4QOWLFkQruHQkn0QIrlJw824aVLlc5IF2JKGGx2SNNyS/OALfjULWLRkH/D7GKgsStKwr/IIXJIswhFVeIIJlbvCB2dwRTKiZ+LwCNu64JYsvMKCLriBR+RReUN4dM/wJpxIGtrhhxU4JTlW+feyCZ+3MrzDG8mDGl51F+6M6xxsmmXn8EZdYB1mSP6KnujBPcnB/wr8oTjAmHHNI3fMsnN4xBGcGLZg+O2OP7/HE2j3LCA4TmVDAAAAAElFTkSuQmCC>

[image44]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEYAAAAaCAYAAAAKYioIAAADsUlEQVR4Xu2XS6iNURTHlzwiyvsVukhJSPKKkIRIKBPPmcRABiRldBV5TYSB5BGSlKI8Q1yPlIwUMVGXGEgmQuS5ftbe3X3W/b5zz3XO5DrnV//uOWvv+31rr732WvuI1Kh6Rqr2qlaqurixNkM7VU9v/Ec6qy6pzqq6qZarfqkWp5PaCoPEFlMJCMwF1RNVb9UE1WfV1nRSMe6qXqs+qc65MZivOqM6kuiAqquqh2q3Gzts//bXsS2J/ZhqdhjLg13d741l0FHVKXwmU8gY3lESS8QW/lu1yY1BndjDHovNWaWaJpb2BGdhsP9U7QrfoYNqluq46rbYM/qEsSyYf0o13Q9UCDLxlqq7H8iDBRKY71LcKbKEAGRBin5UjfMDYhnHzrXEGNVlaYXjrYA1EpRefqAYk1RfVOfFdi0PsonAUMhSqPTYswK7WrXd2bLgmRfF6kClmSiWycBa1yZjRVkntrC0KOGoD8AisXn+OLD4N2GMOZEhqivhb0tMFdsY307bS/P34ZfPwP7B7pksdoxXiJUAgr+gYEYRcIiiNCd8P6p6oXqpmhsnSVNgBia2fqprYnPTwJC6ZApBK4Wdqg3OxpHiaD1VLVUNVd0R24SvwUYg9wTbD7F6FoNL/eP44FdU3nHP5JmqUaxVDlBNUW2W5lkUj9zgxEbXWa9qkML5o8U6XNYuZnFTNdzZKNYEF78+qB6qRoWx+2KbwaauCTbejQ8Vu6fwMHaC3akLthFi551UjuAUDmInI/aJ7RrErkaBBrqLT/c8eJZvoVwDNooFloWSUSkE5bnYEYrw7jTzywKnYpq9Ve0oHC6AI/RK7IzOELtRxrQ9KfYM/rKY8cFeCsPEsiIPFuzrAoWezcB/4LbMdYIjxfPKhsLWKFYgaavvpSlrPDEwy1SnpbCDUJdiYKgr0eFSIFvy5hPkBml+zHgXTSNC8f4mtlnFOmvJUDfSNr1NmgootYaLXCQ6+UDsGKWLief7XRgvlXhtzyMeXwppBF+pdfgeqRd7fwwyl9ayYKfTuwdnmUzIKp44RBCzfmvEjnVPWndBoxPVe2MC/vDcFPw9IYUbQybjG3WNhpB1gy+ZmAG03MhYsUL8SOxi5OGo8IPMQ2D4SZC295YggNcl/1LHbxzuHY3OTlb4Yn1IrEZeDZ9LLfy5UP09VHpSPIuZ3hDoq5onrXMo71KXwub5ls870m4JZA8bhvLqVZsh61JX9dANb0jzblP1HJQK3lD/J+qlsOjXqFGjRlXwBzebtdPaKlVMAAAAAElFTkSuQmCC>

[image45]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFEAAAAaCAYAAADPELCZAAAEIklEQVR4Xu2XW6hOaRjHHzmfj5mEMSQSiYTU5BBTMyaTHEpxR3HhUHK6UduF3DiUhiRsh5gMRRmncrFFEooL02hKbRK54I5CDs/Ps56+d73Wsr+99t6lbf3q397f+6zDe/g/z/sukZKSFmCAarNqv6pHFGu1tFd1jRsLslt1XWwi4Y1qYyXcelmpqokbC7JD9Vw1Mvn9SHWkEq6OUaq9qpuqx6qDql6pK9L0FHsJ195T/an6STVCLB1CzbBbZGpGbFcS66RaH8VWJ7EsuqnOq6bEgYK0VXUJfr+SAgvUTzVXtUb1UfVCbGKzaKNap3ordu0C1e9iqcVz9iTt71XbkjYYklxL7KlqhWpmEmunmq46pLqrWir57wcm77SqcxxoBhjf/2L9LcQsMWe9U/0cxZxJYi68r/oQxWCO2ESxmhOiGBCrE3NTDK7F5Q1BDSOdW4L5quFxY7WQUufEOshAsworq7RQtVzsGlIqholjAplgFiVkvNh91Bwv4s4S1c6oLY8TYu5tTnAeZamPapAUSGfgRmriWrGBHkiHP4MLO6pqJX+iec4TsTiudNhNjybtz1TDgthgsQXhb0Mweb/GjWIm6Cu20A51vX/wG6h/cb1nAq+olomVHMpKIafjmjNSSUcGRccc0u+wWI37V/JTHofhNJ4xL2jnfzYvHBqmOoPGgTixGsaofojaWNw7qodiZWaaWG1lMV+K1Xvq5waxekw9vyG24IBh6G+o35JYo9gq5ixPx9uq3kEchy4WmzgmkA7HgwHu4d7Qqbjholit4dmvVROT2GTVKcmukVlkuf8fscl1A5DupCXgTvrKRsTGiRNxMotJ6Wo2SK1rqoFScZq7hRVkpUYn19IZOkpdzIJdmtTgGjYg7qPWMhhwl3qq48IwBb8G2cKzYnANzzguX252jO0/SS84ZqAPGKfZ+EP1t1i9CSeBgTJZ4YTVS9pJWTB5PonUwV+CmE8izsah1e6ETBKFP2/xfPHro3bGVivphfpLsje+JoGtGZTjk0DbMUmnGi+ns37+y8LvZzH2iW0qjqf6JtWWoL0hhop9mvE3Cy8z8YkBt+G8EGpl7M4m0V11WdKbBHWHgW4XO5aE0B6vbIzf/0AqZcCpE4tdlezUzGOR2K6Z914/VYQ1k8Wvky/Pq1zn9XBsGCgCRfakWOGlMHsHsTmOw0kOsXFiH+fE8wYDXnNuxQGpuJQ6W+1Zj75dkvRGF4KjGEOcIZwIeFeIpz1/fVMrDJ9VfN7xEhfp4jHsztGhg+psdJ0r7xhALeWzj3oUgwM4ZlRbC6EmUR5+oogzhHJBP0KIc+0FMZf6Meeb40fVbEnXQgc3o8aAC3FjHmQUzorf5wfwGD+Ec993Ax8B4cG/pJGQfmwqJU2ACfzaJlZSBavihpKSkpKSb49P3FrruKsrTssAAAAASUVORK5CYII=>

[image46]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADoAAAAaCAYAAADmF08eAAADKklEQVR4Xu2Y2ctOURTGH6GIzKGQIZFkKGS8pFwY/gCKotyIQilFMly6kVIyRMmYUsid4QYpV6aUvGQorghl9jzW2d/ZZ337fIP31Nf79f7qqXPWPmefvfZae+39vkCThmEndYRaRw1wbV3GQKq3N9bBcmpDdP0nautSLlBTvLEORlKjs2s5/C1qK+UW9Yr6TJ1zbVWhfvt4YwUMoW5Th31DipXUaVj4t7i2qljlDRVwiHpJXaYGu7YkPWCO/qAWubYqGEGN98YKWU2998YUc6iv1EWql2urF03icW+sE43xFDU5u59FfaH6tTxRghaz0nZ7ZOufqQy1DYU50haK5HVvJINQ7F8VWZGPbepb3/Df0Vq/irwYKQuVje2iSP6mFmf3R6mn1HNqSXgoYiH1mHpIXaPWo3xStDa1lmI06Gew4qcioj3wDfWa+pnZllEvkBfJJ//ezJlJbYL1/4A6UWxO84iqUaNgZXsutRWto6wBroWlia6lvbDnhuWPtdCXuoTW615RVpROUr9gExYitgM26Ur3cAgIqemzZzZsD1UmdAgN9AZ1hRqb2SbCPtAzu9eglYIaxNLMJkLap9Ak7fZGsgY2qTXqPooVU9mkb8Qo07yt02iWNFBJ6bOv2NzCfNimXIMNUuhdpUxqfegkpInRZKUIg5djATksx5XCMftRPpkdRilXo8bAIvUBeVRjQuTiyqx3Q9p7NDF6VpmQQtFWf/H+OoP6BCs0AU3YXbR2vtNoa4kHrzWivBdaqwuy6zAwtQfibclzEPlZNIWckVNyLiCn/TdCJp2hpiMfT6dR6sTFQmmidJsKO7aFajocVjTOw7aCXbBBlR0yVGja2pP1Xipta8iXhlA/76gJ1FmUV/c20Us3YU4EpsEK0z1YVYuZRN2hvlN7YNuP5KueHFzhbB5NUvzMOOotLHLxBCm7PqJYKP8LbdweDby9A3go+anTlLYP77xHh/F4u9C1tpzUdxWQ9vqrBKXqPBR/3IbilFqHWmt+z2sIDsCciteUqq1OK+EYFlBE9NuzIVEkN8OKkxw8hvJ/CzaieJrqtmxDtf8kNGnSpJvzF2g/mvgiHToNAAAAAElFTkSuQmCC>

[image47]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADMAAAAaCAYAAAAaAmTUAAACBklEQVR4Xu2WP0hWURjGHwlBMEhNIqFQ3JoczEGwrSERQyLBRXDRHIQih5YGFwcdo6k/iIig4NwU8eHoYDq41KIOOoiKgoIF5vPw3qP3O97bd+N+wxecH/z4vnvOy73nz3vee4FAIJCHbvqBfqbbdC36rzb5kt6+jK5wHtDndJ5u0aHo2vmLntCeKP6/4B395DeSJ/Sc/qT3vb6KpJXu0ja/gzyjf+hv2uX1VSRPYQOu9zvIe1jfCpLPTgOt9hvLzE1a4zemMQkbcBI7sHPT67VrAmN0FVY4XtHpooj8tNBl2P0P6Titigf4aNYFXJ/MDfqIHsEqXpxaOkd/RNfN0X//HnlQFigb3sLGMgqblApWKi7FNvyOFNph1U3xjVGbJveV7rugFO7RddgzS/EGNq7vtJ/WwRb+r7gUW/I7UlDVU7x+Ha6AFGJtSajAHNPXfkcCnfQM9iy5QG8VRXjEU+xFcVcqBVi8qpzjMax8xyeYhPK9D1Y0svAQNokDZBijW9FT2uH1pVGApZnSzeF2V+kzggzpUIJhOoGrndAilFysj7BBfEH2AaiCxd85s7AH6euhiQ5E7XnQ2dOBd5VLlVNnMjHNXO66fHTqIJdCMTN0E/YJNAg7oNqtb0h54D8yRffoImyxNundeEC5UXXRTji0s3di13nRS1L3l5lfmIFAIBAIlJMLUi5o7Efn8eYAAAAASUVORK5CYII=>

[image48]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABQAAAAaCAYAAAC3g3x9AAABV0lEQVR4Xu2TvytGYRTHv0IRUoj8KJtNBkz4A/wFEjZitsgioz/AZJEJsUkZDK8UymIgBgqLUJSiMPA599zbve9F8kaW91Ofbvc557k95zznSnn+kiG8DH1JxXKiFQfxBF9TsZxpxPPQX2EC33A8HfgJhViLJbguL7c7K8OxeD2WpwMRZTiD15jBObzBI6yJ0wKa8Ao3wudSdtjZxwN5snEmL3cVi6Ik+ekP5ZUYvXgXh50xeXlWRsQmPmFnYs2I+moT0IAVWJ1MqMQ9HE0uykv5rNwefJZ/1NxRXFVAGz6EzySWPI8FqXWjQ97r6KOLyWA7PurjSSxxQN6/fizGEZyWV2V0yfdmwveAUlyTD7FRhSt4IR8L6++UvPn3OCw/tV3KJB5jc7AzgfXAbm4BT7FPPn9buC3fYCecxVtclv/ju9iiL7CbqpNvNGxgk+8R3w50njz/zTtMsEL9+LH5rwAAAABJRU5ErkJggg==>

[image49]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABQAAAAaCAYAAAC3g3x9AAABUUlEQVR4Xu2UPUsDQRCGR4igEBHiN7EwFoIiiFgJlilMkzpl/kE6BXt7wc7GUlBbQbARLLSwVGsVwUJMQLD0430zu8ncyskeluaBh+zObTYzs3sR6eHogyPu888swCt4A4/gcPJxNsrwGdZhCT7BTbsgC8uwBfdhP8zDcyfHmfmCBzDn5qPwFr7BJb8oFvaJG1ZNbB6+ipY9beJRrMF7WDSxiuiPMEtmm4lt+CLavz3nteiGx9JtQxRT8EH0hC0s9x2uuHkBnohm/Ajv5Od32rDhbHzYJ2Z3CgeDOKvh1UqFGTCTIRPjJp9w3cTIgGiWNBV/mrZPq/BQ9D5aWAVPnVmmwvd1B0648QZsJlZ02RItdzZ8EDIGL+GF6Hs8l3zcxpbLsYdXatLMO4zL7/8waeU24GIQi4JX5EP0wntm4K4kM47GXxffP2Z8BmudFT3+Cd9TxTslmzqLlAAAAABJRU5ErkJggg==>

[image50]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGQAAAAaCAYAAABByvnlAAAE7ElEQVR4Xu2YXagVVRTHV5T0YV9WZJFQ9qFEVFKiJAo+CNWDIlYUFD0JikaRUoEoXB96EJJQDCnsw4eIPh6SLAVDL9VDJEQPBaJIJqaUWCAVZpStH2sWs2afmblzjkeu5zI/+HPvnj1nz95rr73WmhFpaTmPuVG1RvWG6sqkb9S5QPWM6oRqpeqA6t7CHWOLjaqvxDYF/la9lHePPver/hTbFDgjNumxynrVL6qpWfsn1da8e/TZJHY67szabMjqvHuguFZ1WPWr6pDkpyByoeqy0MYZh0K7iimqb1W/qT5XjS92948fVAdVE7P2BLEwNohgpHViTvWp6pJidwesc7/q5rSjhOtUC8XGfjnp6yt4yLDq8uT6oEI+wGhN8sIjqtvTizWwgYy9IO3oJzzgvIqhZ8khKZ74MjgRhOprVJOkWcgC8u05DVdwtkmcOF0VGsalFyrgdBL/+xEq/1N9pLpI7Pnp3NgMjLpY9ajqLckLmjKuzgRLpDpc8aw6J2gEk256vFPwrA9UX6hOi8XuuAFXZX3pJPHeF0Ob/0nCf6h2hOvwrFgy7QbWs0r1uupnsbltkdyr+Z97oh7O+iI4ByHtO9U+1S7VHtW8eJPYOt9V/a7aKVZSY5ueuEJsQux8N0wXM+LarD1HOut53mVOSufx5nlPhvZrYhuJEelzKC72qm4N10aC08AYzO1BMaPi0Vx7Itw3EsznFdWp0H5bbJx0Pp+InchLszYOtyLv7g5K3X9Us9OOGvAwjP9AuMY4lM7U9IAhWADhI4LnYGSMDbeIGZGxGBMPc9i0uEFNwNN5bgx9bsiyU1DGXarjUnwVAIxcNh+uHVMtU92mul6stO4Jfynkb1OYaDQqsFgm5htCiUg5zUQjHPfUYDAk9nuP5b6hZQaog9OQnnbmcUQ1OblexZDYc2PZTGjnFKQOBkclD31oWrG7O+aLGbHsBaoKHpoWAR4WWARw4jh53na4L4Yr8NAUPbJqQ+ugMBiWTufCiO+JGbUJJHzWEsPOTWLVG0rhVGwQ6+N3X4vllZ5YJJ3eXkdZHc7DmQQLZzzw401ecKLB+J+NuVjyXEOfvwv5ycU496hmZdfrILazgXEtPl/PH4+FviqGxdYSk7c7GKeEucwUG5sXxZjA75DuHbwABtuaXqwBQ7HAp8I1khjVkXuFexP3UevDDWIVCtf4uvqq5JtHKCGkDIttCEeezx/cyz0fi1VqGICKzJ9D3lme/Q9+SiPMlwqImM5v1xa7S1kqtiHudM+JJXfGJqIwH+aAI/FNzCtL5ve4akbW7gk2I3rxSBCf+Q3G3a7apnpB8goD8CwW9G+m98W+AeFZbNBu1WYpLuRpsUV/KTb2XNX3YuUmpSd44sf7HlJ9qLo766OS4zRhoAgbzKn5TIqlbx3MixKeEMpaCc/3qX4Um487EvN+XmyD3sz6CLM9w4B4TxrTq/D7SeB4HNUESvFPF2weSTGtOtK2w70Ym+eAP8MhDFLr8zJHJeQb6mB8f4GL8MLZy0sn48XQw/PSdyrgGveVPbsrPKY3LXk90aZ1eAqJvNtSuglsNCdozNLUwI4ntvRTRAr5gHEZv58Q078JbULYytAeSIiJnsSJ9cT4pqwWewMeib/Ekt+5oirkDSRUECRCkvA7YomwZRQhMfFZgOTIh0HK0ZaWlpaWljr+B7T0Cs0an1d/AAAAAElFTkSuQmCC>

[image51]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGYAAAAaCAYAAABFPynYAAACx0lEQVR4Xu2YXahNQRiGX6HIb4j8RVIKIS6UXCokN7hQcqNcEaEoSufGhZQLpdyJciFSilxQ/gpFKTdKKeQnJKVI5Od9+2bstUdnrVl7r3PW3rt56umcmTVnn++sb+abmQMkEolEIpHIYyYdG3Z2KIvoITo6fNBLTKHH6A+6PnjWqdyhL+nU8EEvMJneo9/oL/oH3ZGYIbBYuyoxE+lrepgOD571h8rBLXRHYmbQu/QrSiZGL6aOujePnqVv6ajgWRFlE6OVNjTsHAQ00U7RfSiZmAn0HaxW64e15IT+8Mv0vGtXiV7QffqIrnPtssQkRoeCo/QjrL6/p2ubRgw8G+kVWLzRifHZHANbas9hm6pYSX/Si65dBfp9m+kzuhyNSdAKRYlZQl/BEqJSItbQx3SSHzTAzKK36QLXjk6MZo/sg/2BO13/MFhClBglqB0UxHHYzFXJrIq8xCh+9R9xba3I7bB9bLUfFKBJovgUb6xFnEPznhmdGM8D+pkudO3p9AWaV1CrHIQFVPVdIy8xc1z/B9iqkbuRPzH0eRfQGB9jHnPp7KCvdGK0Mq7SEa69iv6GrRrNvnZRUj7RkygRVAF5iVkGWx2+hNXBAfyfSMUqddh50hjaPxqsD/Loe/XthS3xKl7mSLoNFtQltLe/iKLEaM/U3lkXii8sfYr1DV2MyEqUTYxemC5ufsZtcH3j6HW6343bA3sBraJ/T1yjT2EHgrJoY9VGrti3Bs8Ur8qGDhie+bCTYPbkOZhon/OJ0TUhitP0O6zGPqRbXPsm7JYt+mDH6qV0B+w0p1nRLvpfl0qcEh6zD2VXSmh25ZygX2DH/TOw05GSUwf6/WGsmjhRjIctN/+ytd+ora+6/N2AHT030WmoftYpMdrndK+qimw56Un8LNUJK9FBaHWo3GXvBbvoin8jErXiL2GJRCKRSCQSiar4C/p8pV0wrkOyAAAAAElFTkSuQmCC>

[image52]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAF8AAAAaCAYAAADR2YAqAAAC5klEQVR4Xu2YTYiNURjHH6HIdyZMKR8pUUrZKErJgqbxkY2IBclSKclCSVnIbiIl02ShfEWarCxcw8Jkp0SihkQoImzk4//vuW/3vM+997znzL1z743zq1/dOc877z3v857znHOuSCKRSCT+R4bha/gNXjGxdjMOLrGNHQj7OacsPwezBd6Cf+AhE2sXfIDlov0ayYc6jnXwRdnn8BycmLvCAx/0EvwJ15pYO1gBf8EfogPiVT7cUWyH3+E+OB6egr/hJvciH6tEb3AdTjCxZsBOPYZX4TwT85H1q1OTz1wx0Ructq3wOJzhtHk5IPmSw7rFhDXKZLgXvoWLTCyEmORz9s60jWPMYvgGzreBGAZES85+OAQ/wS8SMXVqcBC+h2dht4mFEpJ8Png//AqfwQfltlbA/DyCq+Fd0bwdFh10wTwRHfkP4UI4S/SmlJ9jmC1a9yg/N0JR8ntE41yvposucjeldZuGI/AlvCOVHdlneF4iFlwmnjfK4HR6B0twqtNeD5YUlhaWmKi3XoAv+fwe9pslk/Bh+dBMRL16y9LEAcGZGGLRlpE5s2WHbezXbTjJaa8Jv8DucjaL3uCk01YPrg0n4G6JeNuB+JK/TLSPfOk8o3AE9oq/D0w8Xw6vD7Fo4HGGsWp0OW3sQ7ZDKyy3LCvs+Fyn7YxUr+JFsLazxrPWTzGx0eJLPvs2mrLYTFjz78NpTltU8vmAdos5IpUH4w1Cdz4cWadFXwJrcKMUJd/2u9WwPNskZzvHoIFxQaoPVvxnvsEFcNDEQsm2mZy+nBWxsBxuFC2JH8p/uzDpLDnuTw87Rc8TK522sYaHwaNS6d+Q6CmXufPCmlaS6l3JR9Gt0zBcb2KxsAbvgDfgUhOrB0cSB4C1JPk6fFl0ll0U/U2qT5oz42LYI3oSvwaPwaei61EQtQ4mXKWZgMLVOgK+xHtwjQ00CPvPvvJg2C44eLfBXeJf8BOJRCKRSCQSicQ/zF/Cip2t3sSzJQAAAABJRU5ErkJggg==>

[image53]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAC4AAAAaCAYAAADIUm6MAAACJ0lEQVR4Xu2WO0gcURSGjxjBJ1EUQrCJgkJAsLBRsUyRGBIs7GIhiFhpI8Y6BCGFlSCCikuQgI8UaUJSBLJgaZEqaGOhCBYiQiCV+Pj/nJnZ2ZNZmLmzFuJ88MHuPXfO3r3nzJ0Ryci4X7yAH+E+PIJf4LLnO9gJK4LZyWgUzcOczE393HQB9gezE/IUDsNP8BCOet/pT3gNt+FDb34SauA4PBfNsyiF3GPwlzfukjuA/37VjFXBnGjyJfigOBwLbswZ/AO7TYx/7DucNeOxaYcn8n9itggrwYXvwqbicCzmRK+3m0Ia4A78LG6bIq9Fk9uFtcFjLzZtYnHJi17/xoyTLtE2GrGBuPi7YuEN5LcJ28YFVjKqTVjN96L5600sFrwoL5rgMeyAQ3AK7sGX4n6qkKg2a4Yf4BXcCI0nwm8TJg/D8m2J+04TbgpzT9hAOSh18/SIHo+sgiu86S/ggA2kJdwm9uZ5JukXzmr+hi02kBb/GIy6eViJA/jIjCeBOXicprlHIlkR3W0+GatD4/z8VbQarAofFJui7UP/il6X8+ZbuNBe0aNu0PteCj41uWmn8K3oYcDXkEg4kbvMHw8bfgiwL7nASdH+nxFdAH/oG7yEP4LZBTjX5qWlFvNENMbqtsI6SXcg/OOV6HsFd7nSxNhm62bMFbYUKxyu+q3xHM7bQUdYOef3lSSwlGuwzwYc4enFU+zW4dOVvVguau1ARkbGHeIGAe1xwc7R1tQAAAAASUVORK5CYII=>

[image54]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAZCAYAAAAFbs/PAAAAnElEQVR4XmNgGAWDEQgAsTAQM6JLoINgIP4PxM+A+BeUDdIIAiDNfVA2GGgD8SMg5obymYE4EIgjoHwVIN4OZYNBAxBXIgtAwSogZgHiOiDOQJbgB2JWZAEoOATElkC8A4jF0eSwgvlA/BqIddAlcIGFQLycAeIsogDIBpjHiQKXGIh0OwxsBWIOdEFcAKSwHF0QH5ABYht0wRELALaGEnjDW95QAAAAAElFTkSuQmCC>

[image55]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFEAAAAaCAYAAADPELCZAAAClElEQVR4Xu2XS6hNURjH/0J5v/PIQKRboiiPIqWEkphQSDEwUDKXO5WizAyUR4Zud2RAUQa3DCgDE2QijzyKpBTlceP/71urs87aZ++1T+xz01m/+rU731779a1vPQ6QyWQymf+BRXQjnU/HRefqoGsmx8F+Ygt9RC+54xO6vq1FOUrecnqNro3O9Q0b6Gc63v2eCEumYime0t/0izv2ZRJX0E/0YRSfB6vGZVG8DE0FrzDGSZwFq4BesxtWQSNRfJqL7YziZaSSqPvpGz2aAua6Y8gCWNuu0Eu+o49hFXEcxRs3yUlUJ/FYFC+jKol7YfPsezqb7qcv6Gv6lq6jM+gF+ob+okN0pi5OsR0272x1v8/SZ7De6ISSu4nu68JddKouLiGVRJ2vQ1kSl9LbsG/Sve7T82it4h/oA9dmj4udgL1TrQ4cgTW+TrfByrvrUv5Lmk7iUbqGTqf36Kr20/gJS2C4NToDe6dDQayU07DG3nPo/bzYdBI9fgGLi0TPDp+hIazKVFtdk0QJO0jv0h+wGx5oa9E8qYVF5+uQSqKqSs8JmQCrxM1BTJv97yhWZ0cWwm7sFxHt0eJeiZlCb6K9elN+pCt1cQmrYXs8bWdCNIc9R81qQDqJV1BM4mL60h09fij7+bDy+bqpPsAzB7bB7fVwFprQR9HqUB1PuZhHi5NGjDplIIgLtde8p0VCc7vftHt8R92K4oMoLh4axmo3CbaKq1pLWQJbia/SG7CHVK2iTaIkaGt1Gbai6/iNHg4bwT5Yi2A4r6n64uqXX9GqSj9lhKNMyRlGcZRchHXGHdg2J4k2nxoGGjpjUYEx+tgjdAf+bYfq2/QPKK7QeJER6lDtUjptxDOZTCaTyWQymUr+ANqGl6u5TU7XAAAAAElFTkSuQmCC>

[image56]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGQAAAAaCAYAAABByvnlAAAFNElEQVR4Xu2YeehtUxTHv0KReXiGUJ5ZnsxEhmfMEMkTCvmThD8oIuX5wx/SkyQy9ZKQTAkR0iXJ8IcUkaEeGZIQRTwZ1sfa63fX3fecO7nlyfnUt3vP3mfYew17r3Okjo7/CaeYbjfdajqk6uuYgI1Ma9eNM7Kn6cLyfx3TQ6bt+t0dk/CcaXHdOCO7m1ak46tMB6TjidnQtKRoFJuadjWtW3cktjUdatrKtFbVB+ebPitaXfXBeqabTHcl3Wu6rvQz4dyHji99UPdtkfqaeFAezfMiso25r9QMzmbyX5ruMz0sT7PNB86QtjE9bvra9KTpW9MlGk71o0xvyw3B73uD3X9DWp9n+sD0R9UHOPtY06Wmn0zPmM4x7V36WaNvNP0pv/5005alD66QX/eD6VqNNjZ9J9aNc2Ivub2agrIVBnSPaf3U9pLpeXnWwCamF01vmRaVtmWm3+STDw42fa++kzAsjtlv4Yw+rKuritog0z6Vp30NywBGRzVkBONnPOMgOLauG+cANnvBdHXdMY5TTUdXbUz2R9NJ5ZgIxfiHL5zhUEUQpcDEyBqcliFyvzLtVLVfI7+2ydgBAdGTP6dux+BcH8/PPCtfLscRRps3rBxnqp8Z+6S+sWDkb+RrcNyA5eRD0w7lmCglEuvNCWOGQXAs/3sLvQ7Goz2cC+wRTU5mf4qsBMbzgHwpzTC+R02fa9ghZPwZVVsbPJtluIYgynsk4yVb+c0w3trxjPluuUPQxZoyA8NgiMHhBCaaJxVLQ5tDGGj87+UT1L9/lIJAtpA1n8gHu73pEdM78o0+gzNwSl6Hceb+8v2pdgiBNargCLjfbfJozpA1b5h+kduAvfML+R77u/yaY+TPxk7faTDYyIawZ2iD1D8RLDP5BrXhxzkEo49zSF6aTittRDkR/ZhpN/lkawPfIL9nZA6GJENiOcvnY8ymiG+CPexlDVdAy9XfuwiO10o7z6WQoIigKouih4DCObmo+EcQTR/L9wAilQkxSTbn2Izn7ZCefGKs9XeWNiZMdNXPuFxuHIxE4UEFGJA94ZBdNPneQUY/oeHqakd5xpAZ3JcAicwkcAiguiok2wnozar2mblIg6/3VEiUiwyIyTOQeTuEzZ82xGQ2Tn017E3hEDLj5tQXDuEZtNM/CUvk2dEW1VGskMlBW1VIOV4XHTNDir+u4Tp9D/maGamIQUY5BMZt6vQHHK8sfZeZXlX7yxvXUfHx+5Q8igOWM+51sjx4cuk+iuVFbRAkBA2rRkABQBFClgTYjefWmTYzsVY2QfSFQ3gHIVWPGzjD31/CISw3GI5rMqyx9eS45tzyn0mxWS4txzlbgSD4Wf5uRDZnIiBY5+vrRsGnkjq4Msyjp8GKL56VMz2KE2xEcJ+l4eCemmXyl5f8xn22/EHxYsXe8r7pFfmDAQOQNbeUYyDFMW6su/xy7/xZA8fkNZcKJJYk7nl/aQ+Y9K+mI6p2iKyM8nwSGFMEQxt18DF/Kqp682ap4twoJppegKeGAa42vWu6vugj00H5JGNf+eb/pnyjZdNn2cklHfei7o46nF+iOxwElIgr0jFQYvKCRqTznAyOukPNkYfRCIBpWFzUBlmxSoNfaA+TBwXBl+dyoPwdjnKdzzlzg6pjqTxy2KTa6njaj5Qbe1RUErkXmE7QcA1OJtbfv9pevIB9oW3zXSR/xjQwx2zUJvJSBYyXMTTZhTE3jbtjAnAuhUHHGgLl7tN1Y8e/AxsvzsApHWsAO5uuVHNx0NHR0dHR8Z/mLy00LOKqz70GAAAAAElFTkSuQmCC>

[image57]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEsAAAAaCAYAAAD/nKG4AAADXElEQVR4Xu2YS8hNURTH/0KIvPMIeYSSvPJ+zFAMMDAwoBiQiVIoZSB5DE2kTDwykGdGyMi7kInklZJLHgNJhPL2/1tnf2ff/e1z7/ncOzmf86t/nbv2OWfvvfbaa697gJKS9kAvqnNoLIlzmhoXGovIVeoF9Yk6GbQ1C723a2gsIsuoY9RvalPQ1ixWhoai0gHmrO/UvKCtGQykRobGojKd+kKdoToFbY2ihTgcGovMetgW3OrZeiTKQm39YM6ohSLqYmgkvVH9fp2UikDfpnerjzz9/CsdqQFoQx+KqF/UguT3Qeox9ZRa6G7ymEs9pO5TF6i1yHasctX+wKZBPYEdKAeontQr6iX1I7F1oZ4hPXge/X2yuchR76hrsLncrW6O84CqUEOoQdRMajNaR5smuYb6nFxLu2D39U9va6EbdRat86CiTSt5lPoJG6hb1W2whTsEc6KYirTPZrKKGpNcD6VueG2ZaLKXqXPU8MQ2GjZIeV9o4tpOmsiixCbcFo4hR+8IjWQ1bGEq1B2qj9emqA77UMTLVo+31HtqStgQYTD1nNpHjae6I77gVWi1NFlJW2F3dXMLs6mvSCNQ6NkjsFM0RBW7nCuHx3AOkHMccpqcp+2olXbsQfaC+Lh5LA4bIuggO470mQ/I8Zy8WaGGwVZTq+Oiy8dFkH9i6lm3hUPkXN2riIyhqNP7/PprEvWROo+0gJXTb8EcWI91sDoxq88QRdM9WCrQWDSXmqhs8B2gnLEkuVbumpNcu8mp3eGXHCEKbzk4CzlEjpGDHHJc2IeLaEXBRKTjaYSxsPHNT373pa7Dkn1NtA38BKyQ19bRPtZfFHfK6XhVIj4FO+a3wyaWVcgqedeq2fRcbAtWkG5zofe8oUZRJ5B96ubFbT8lc7fVZ8D6WO5uiqGOr8Ac4ZgAS/a3qWmeXWhFblLfqJ2w0kJSfeSjAS0NbCFytH/PCOo1bCK+kxXlyif+4dMok2GlkRbnEqw8WYEcp62KwxBNvt6fXnecx6p+lQahA0MU+v7gdK1yItavFrXe+9qK6y93MZoXbbtZSOse4RJ+LC8p9zR1AEViL8wxfo7RyaGq2j/ihSJD367+WxRRG2EJX05SdZ311XMDqqv+khpsQTv5IlpSUlJSVP4AOgynNEl5uJ4AAAAASUVORK5CYII=>