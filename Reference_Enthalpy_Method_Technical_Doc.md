# 全湍流绝热壁面温度的焓法推导与当前实现

更新日期：2026-11-18。本文以当前 Fluent 的绝热壁边界条件和本项目现行代码为准，求解目标为绝热壁面温度 $T_{aw}$。历史同名文档来自 Git 提交 `06a97c47a71e01403bb11cf5c2e51a5d58a22a89`，其中包含辐射平衡及壁体热响应；本版已按当前任务改写，不再作为原论文第 2.3 节的逐字整理。

本文区分数学定义与当前工程近似，公式记录代码实际执行的模型。2026-11-18 核查发现的三个实现问题（物性越界、前缘参考、边缘闭合）已修复，过程与验收结果见 [计算核查报告](docs/calculation_audit_2026-11-18.md)。

## 1. 目标、符号与边界条件

当前工况是固定壁面、无滑移、无渗透的全湍流绝热壁。令 $q_w$ 表示气体向壁面的法向热流密度，绝热边界为

$$
q_w=0.
\tag{1}
$$

壁面温度是满足该边界的求解结果，不需要预先给定。绝热不表示边界层内部没有黏性耗散，也不表示壁温等于自由来流温度。当前低阶模型用恢复焓近似这项耗散对壁面温度的影响。

| 符号 | 含义 | 单位 |
|---|---|---|
| $T_\infty,p_\infty,M_\infty,V_\infty$ | 自由来流温度、压力、马赫数和速度 | K、Pa、1、m/s |
| $T_e,p_e,\rho_e,V_e$ | 边界层外缘状态 | K、Pa、kg/m³、m/s |
| $h(T),s^0(T)$ | 固定组分热完全气体的比焓、温度部分的比熵 | J/kg、J/(kg·K) |
| $h_0$ | 自由来流总焓 | J/kg |
| $h_{aw},T_{aw}$ | 恢复焓及其对应的绝热壁温 | J/kg、K |
| $c_p,C_p$ | 定压比热、压力系数，二者不得混用 | J/(kg·K)、1 |
| $r,Pr$ | 恢复因子、Prandtl 数 | 1 |
| $\alpha_h$ | 以焓差定义的传热系数 | kg/(m²·s) |

本问题不需要通过 $q_a=\varepsilon\sigma T_w^4$ 求温度，也不引入壁体厚度、材料热容或蓄热时间积分。将这些量加入会改变当前 Fluent 对照问题的热边界条件。

## 2. 由绝热条件得到恢复温度

在恢复焓传热近似中，向壁面的对流热流写成

$$
q_w=\alpha_h(h_{aw}-h_w),\qquad h_w=h(T_w).
\tag{2}
$$

在有效的局部换热模型中 $\alpha_h>0$，式 (1) 与式 (2) 给出

$$
h(T_{aw})=h_{aw},\qquad T_{aw}=h^{-1}(h_{aw}).
\tag{3}
$$

这解释了为什么当前求 $T_{aw}$ 不必显式计算雷诺数对应的传热系数：在该近似下，它不决定零热流条件的焓值。全湍流假设仍通过恢复因子参与计算，不能据此把层流与湍流视为相同。精确驻点应按相容边缘状态的极限处理，不能通过任意修改压力或温度制造 $V_e=0$。

恢复焓模型为

$$
h_{aw}=h_e+r\frac{V_e^2}{2},\qquad h_e=h(T_e).
\tag{4}
$$

恢复因子按 Eckert 参考焓状态取物性（全湍流）：

$$
r=[Pr(T^*)]^{1/3},\qquad T^*=h^{-1}(h^*),\qquad h^*=h_e+0.72(h_{aw}-h_e).
\tag{5}
$$

$h^*$ 由式 (23)–(24) 在绝热条件 $h_w=h_{aw}$ 下得到。$h_{aw}$ 与 $T^*$ 互相依赖，代码用不动点迭代求解式 (25)，一般 6 次收敛到 $10^{-6}\,\mathrm{J/kg}$（`aero/recovery.py`）。迎风面和背风自由来流恢复使用同一闭合。

如果 $c_p$ 为常数，将式 (4) 展开可得到熟悉的检验式

$$
T_{aw}=T_e+\frac{rV_e^2}{2c_p}
=T_e\left[1+r\frac{\gamma-1}{2}M_e^2\right].
\tag{6}
$$

当前 $c_p$ 随温度变化，应使用式 (3) 的焓反演，不能直接把常比热式 (6) 当作生产公式。

## 3. 当前气体物性

当前使用固定组分的热完全理想气体：

$$
\rho=\frac{p}{RT},\qquad
c_p(T)=\frac{a_1}{T^2}+\frac{a_2}{T}+a_3+a_4T+a_5T^2+a_6T^3+a_7T^4.
\tag{7}
$$

系数分段与 `gas/thermo.py` 一致，温区为 200–1000 K 和 1000–6000 K。代码中的系数直接给出 SI 比热；不要再额外乘 $R$。以 $T_{ref}=200\,\mathrm K$ 为一致参考，

$$
h(T)=\int_{T_{ref}}^T c_p(\theta)\,d\theta,\qquad
s^0(T)=\int_{T_{ref}}^T\frac{c_p(\theta)}{\theta}\,d\theta.
\tag{8}
$$

每个分段先积分，再累加跨段积分，因此焓、熵参考连续。任意共同焓零点不改变式 (4) 的温度结果。对固定 $R$，

$$
\gamma(T)=\frac{c_p(T)}{c_p(T)-R},\qquad
a(T)=\sqrt{\gamma(T)RT},\qquad
V_\infty=M_\infty a(T_\infty),\qquad
h_0=h(T_\infty)+\frac{V_\infty^2}{2}.
\tag{9}
$$

黏度使用当前 Sutherland 参数：

$$
\mu(T)=\mu_{ref}\left(\frac{T}{T_{ref,\mu}}\right)^{3/2}
\frac{T_{ref,\mu}+S}{T+S},\quad
\mu_{ref}=1.716\times10^{-5},\ T_{ref,\mu}=273.11\,\mathrm K,\ S=110.56\,\mathrm K.
\tag{10}
$$

导热率与 Prandtl 数为

$$
k(T)=\mu(T)[c_p(T)+1.25R],\qquad
Pr(T)=\frac{\mu(T)c_p(T)}{k(T)}=\frac{c_p(T)}{c_p(T)+1.25R}.
\tag{11}
$$

式 (11) 是当前 Fluent kinetic-theory 对应关系的化简，黏度在 Pr 中抵消是该物性模型的结果。

**温区约束与外延：** 在 Fluent 拟合温区 200–6000 K 内有 $dh/dT=c_p>0$、$ds^0/dT=c_p/T>0$，式 (3) 的反演唯一。温区之外，代码把 $c_p$ 固定为端点值并继续积分：

$$
h(T)=h(T_b)+c_p(T_b)(T-T_b),\qquad s^0(T)=s^0(T_b)+c_p(T_b)\ln(T/T_b),\qquad T_b\in\{200,6000\}\,\mathrm K,
\tag{11a}
$$

所以 $dh/dT=c_p$ 及正反函数一致性在外延区同样成立，反演不再饱和于 6000 K。外延只是数学延续，不是高温空气模型；每个迎风点的边缘温度和 $T_{aw}$ 是否落在拟合温区记录在 `property_in_fit_range`，summary 中给出温区外点数。20–50000 K 之外直接报错。

## 4. 几何与压力闭合

机体系为 $x$ 向后、$y$ 为展向、$z$ 向上。无侧滑来流方向与有符号入射量为

$$
\hat{\boldsymbol u}=(\cos\alpha,0,\sin\alpha),\qquad
s=-\hat{\boldsymbol u}\cdot\boldsymbol n_{out}.
\tag{12}
$$

外法向由 0920 STL 及上下表面方向确定；轮廓定义前缘、弦长和计算域。$s>0$ 为迎风，$s\le0$ 使用当前背风/切向恢复模型。

迎风压力采用修正牛顿近似：

$$
C_p=C_{p,max}\,[\max(s,0)]^2,\qquad
C_{p,max}=\frac{2}{\gamma_fM_\infty^2}
\left(\frac{p_{02}}{p_\infty}-1\right).
\tag{13}
$$

这里 $\gamma_f$ 是 case 中的固定压力模型参数，当前为 1.4；它与式 (9) 的变比热 $\gamma(T)$ 要区分。$p_{02}$ 是法向激波后再等熵减速至驻点的总压。可用固定比热比法向激波公式计算：

$$
\frac{p_2}{p_\infty}=\frac{2\gamma_fM_\infty^2-(\gamma_f-1)}{\gamma_f+1},\qquad
M_2^2=\frac{1+(\gamma_f-1)M_\infty^2/2}{\gamma_fM_\infty^2-(\gamma_f-1)/2},
\tag{14}
$$

$$
\frac{p_{02}}{p_\infty}=\frac{p_2}{p_\infty}
\left[1+\frac{\gamma_f-1}{2}M_2^2\right]^{\gamma_f/(\gamma_f-1)}.
\tag{15}
$$

局部压力按当前代码取

$$
p_e=p_\infty\left(1+\frac{\gamma_f}{2}M_\infty^2C_p\right).
\tag{16}
$$

这套固定 $\gamma_f$ 压力近似与变比热速度定义组合使用，并非完整热完全气体激波解。三维法向已经包含几何后掠，当前实现没有再使用历史 Busemann 和条带有效攻角/马赫数的另一套压力公式。

## 5. 边缘状态：条带前缘参考激波与等熵膨胀

整条计算链只用一套热力学模型：式 (7)–(8) 的 $h(T)$、$s^0(T)$ 加 $p=\rho RT$。

**条带参考入射。** 每个展向条带（结构参数网格的一行 $y/b$）取前缘窗口 $x/c\le x/c_{first}+0.05$ 内有效几何点的最大正入射 $s_{le}$，其中 $x/c_{first}$ 是该行第一个有效几何点。窗口内取最大值，而不读首个样本，因此首点位置或首点无效不改变定义。任一点（结构点、插入点或单独求解点）都在自身 $y/b$ 处读取该条带参考（相邻行线性插值，两端外保持端值），实际使用 $s_{ref}=\max(s_{le},s)$，使一点的参考激波不弱于它自身的法向激波极限。若某一面没有任何条带具有正前缘入射，程序直接报错。实现见 `aero/strip_reference.py`。

**参考激波。** 以法向马赫数 $M_n=M_\infty s_{ref}$ 求热完全气体正激波：

$$
\rho_1u_1=\rho_2u_2,\qquad p_1+\rho_1u_1^2=p_2+\rho_2u_2^2,\qquad h(T_1)+\tfrac12u_1^2=h(T_2)+\tfrac12u_2^2,\qquad p_2=\rho_2RT_2.
\tag{17}
$$

记 $\varepsilon=\rho_1/\rho_2$，质量与动量给出 $p_2(\varepsilon)$、$T_2(\varepsilon)$，能量方程在 $T_2=T_1$ 的下界与理想气体密度比之间二分求根。参考熵 $s_{ref}=s^0(T_2)-R\ln p_2$。$M_n\le1$ 时没有激波，取来流熵。这里的 $p_2$ 是激波后静压，不是驻点总压。

**局部边缘状态。** 表面静压 $p_e$ 来自修正牛顿式 (16)。边缘状态在参考等熵线上：

$$
s^0(T_e)-R\ln p_e=s_{ref},\qquad
V_e=\sqrt{2[h_0-h(T_e)]},\qquad
\rho_e=\frac{p_e}{RT_e},\qquad M_e=\frac{V_e}{a(T_e)}.
\tag{18}
$$

若 $h(T_e)>h_0$，说明该压力与参考组合在此模型中无可容许解：点被标为 `edge_static_enthalpy_exceeds_total` 并判为无效，不再改写成驻点。修正牛顿驻点压力 $C_{p,max}$ 用理想气体激波关系求得，它比热完全气体参考激波对应的总压低约 1–2%（M5–12），所以在设计包络内 $h_e<h_0$ 始终成立，鼻部趋于 $V_e\to0^+$、$T_{aw}\to T_0^-$。

每点保存 `reference_incidence_s`、`edge_T_e_K`、`edge_p_e_Pa`、`edge_V_e_m_s`、`edge_status`、`edge_energy_residual_J_kg`（$h_e+V_e^2/2-h_0$）和 `edge_entropy_residual_J_kgK`（式 (18) 回代）。插入节点用同一条带参考直接求解（`windward_solve_method=inserted_direct`），不再从父点插值温度。

## 6. 背风面与近切向过渡

当前背风/切向候选使用自由来流恢复焓：

$$
h_{aw,rec}=h(T_\infty)+[Pr(T_\infty)]^{1/3}\frac{V_\infty^2}{2},\qquad
T_{aw,rec}=h^{-1}(h_{aw,rec}).
\tag{20}
$$

它没有另解背风面膨胀、分离及局部外缘流动，是当前明确采用的低阶近似。迎风候选由式 (3)–(5) 给出。令 $\epsilon=0.05$，当 $0<s<\epsilon$ 时定义

$$
t=s/\epsilon,\qquad w=3t^2-2t^3,
\qquad h_{aw}=(1-w)h(T_{aw,rec})+wh(T_{aw,wind}).
\tag{21}
$$

最终分派为

$$
T_{aw}=\begin{cases}
T_{aw,rec},&s\le0,\\
h^{-1}[(1-w)h(T_{aw,rec})+wh(T_{aw,wind})],&0<s<\epsilon,\\
T_{aw,wind},&s\ge\epsilon.
\end{cases}
\tag{22}
$$

$w(0)=0,w(1)=1,w'(0)=w'(1)=0$，在候选值规则且连续的前提下可平滑衔接。阈值是工程设置，不是由绝热条件推导出的普适物理常数。混合在焓空间，不能误写成直接线性混合温度。

## 7. 与历史参考焓表达式的关系

历史表达式为

$$
h^*=h_e+0.5(h_w-h_e)+0.22(h_{aw}-h_e).
\tag{23}
$$

在绝热条件 $h_w=h_{aw}$ 下，它化为

$$
h^*=h_e+0.72(h_{aw}-h_e).
\tag{24}
$$

若进一步选择 $r=[Pr(T^*)]^{1/3}$，则应迭代求解

$$
F(h_{aw})=h_{aw}-h_e-
\left[Pr\left(h^{-1}\{h_e+0.72(h_{aw}-h_e)\}\right)\right]^{1/3}
\frac{V_e^2}{2}=0.
\tag{25}
$$

当前代码执行式 (25)。与旧近似 $r=[Pr(T_e)]^{1/3}$ 相比，来流恢复温度升高约 0.7%（M5）到 2.0%（M12, 50 km）；这是两种恢复模型之间的差，不是对 CFD 的误差。

## 8. 计算流程、必要自检及验证边界

当前流程是：工况与物性 → STL/轮廓/计算域 → 外法向与入射量 → 修正牛顿压力 → 参考与局部边缘状态 → 全湍流恢复焓 → 背风候选和焓混合 → 焓反演得到 $T_{aw}$ → 独立读取 Fluent 温度作比较。映射权重或 CFD 温度不能参与反推修改低阶预测。

每个有效点至少应满足：物性温区有效、$p_e>0$、$\rho_e>0$，焓/熵正反函数一致，$h_e+V_e^2/2=h_0$；若采用式 (18)，还应检查它的熵残差。对于 $0\le r\le1$ 的相容状态，有

$$
h_e\le h_{aw}\le h_0.
\tag{26}
$$

式 (26) 只是必要范围约束，不能替代原方程的回代残差。超过物性范围时不能将 6000 K 当作成功反演；边缘闭合失效时不能仅凭 $V_e=0$ 将其认作物理驻点。这三项已在 2026-11-18 修复，见第 3、5 节。

代码参数化范围为高度 20–60 km、Mach 5–12、攻角 -10–10°。40 个 Fluent 工况（训练 25、开发验证 15）上，逐工况 LF 平均绝对相对误差为 3.3–5.4%，LF 一致偏高；冻结回归点为 C01（20 km、M10.983、6.06°）。这是低保真模型的系统偏差，不是精度验收结论。

## 9. 公式与代码对应

| 内容 | 代码 |
|---|---|
| $c_p,h,s^0$、焓/熵反演 | `src/ref_enthalpy_method/gas/thermo.py` |
| $\rho,\mu,k,Pr$ | `gas/transport.py`、`types.py` |
| 外法向与 $s$ | `geometry/local_incidence.py` 及 STL 几何链 |
| $C_{p,max},C_p$ | `aero/pressure_coefficient.py` |
| 参考状态及局部边缘状态 | `aero/edge_conditions.py` |
| 条带前缘参考入射 | `aero/strip_reference.py` |
| 参考焓恢复，式 (5)、(25) | `aero/recovery.py` |
| 迎风恢复焓 | `aero/windward_cache_faceted3d.py` |
| 自由来流恢复候选 | `aero/leeward_recovery.py` |
| 网格、插入点与式 (22) 分派 | `n8_taw_surface.py` |

恢复焓、恢复因子与参考状态取物性的理论交叉依据：NASA NTRS 20210015675 的式 (10)–(12)。导热率依据 Fluent 用户手册 kinetic-theory 公式。引用只支持对应关系，不表示这些资料验证了本机体和当前边缘状态近似。

```text
https://ntrs.nasa.gov/api/citations/20210015675/downloads/Numerical_Correlation.JMCooper.AIAA.2022.pdf?attachment=true
https://wwwafs.frascati.enea.it/project/neptunius/docs/fluent/html/ug/node301.htm
```
