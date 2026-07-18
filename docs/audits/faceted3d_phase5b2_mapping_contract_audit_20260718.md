# Faceted3D v2 — Phase 5B2 Mapping Contract Audit

> 审计日期：2026-07-18  
> 审计基点：`main@60e3473cc48d366671921ca246aaccf60f5a1fd1`  
> 作用域：只读 geometry/mapping contract audit  
> 正式工况：`ma6_a5_h30km`、`ma8_a5_h40km`；两工况几何 mapping 结果 byte-exact

本审计不包含正式 pairing implementation、mapping QA implementation、wall-temperature ingestion、temperature comparison、leeward temperature error 或 model validation。审计过程未向 Git 仓库写入运行产物。

## 1. 合同裁决

- 推荐方向：Fluent clean → LF clean。
- 推荐口径：P，即 exact-projected physical `(x, span)` metres 上的二维欧氏距离。
- error domain：186 个 Fluent canonical source 点。
- duplicate policy：many-to-one allowed；LF target multiplicity 保留为 diagnostic。
- mutual nearest：diagnostic only，不是 acceptance condition。
- injective/Hungarian assignment：不用于正式 pairing。
- hard mapping-distance gate：未冻结；20 mm、30 mm 只作为观察统计。
- edge buffer：未冻结。
- `accepted` / acceptance mask：未定义。

## 2. 输入结构与 projection

| 点集 | 数量 | x 或 x/c 范围 | span 或 y/b 范围 | 重复 | 最小非零间距 |
|---|---:|---:|---:|---:|---:|
| LF physical | 256 | 2.092876–3.599000 m | 0.695943–0.979476 m | 0 | 3.655 mm |
| LF normalized | 256 | 0.0125–1.0000 | 0.6750–0.9500 | 0 | 0.0125 |
| Fluent raw | 186 | 2.396308–3.595320 m | 0.753017–0.992090 m | 0 | 2.284 mm |
| Fluent projected | 186 | 2.396313–3.595327 m | 0.753000–0.992089 m | 0 | 2.285 mm |
| Fluent normalized | 186 | 0.09674–0.99307 | 0.73034–0.96223 | 0 | 0.00483 |

Raw Fluent centroid → exact projection 的 3D displacement：min/median/p95/p99/max=`0.0030/0.0724/0.2038/0.2321/0.2788 mm`。

- `|dx|` median/p95/max=`0.0013/0.0061/0.0077 mm`。
- `|dspan|` median/p95/max=`0.0060/0.0311/0.0358 mm`。
- 该 displacement 只描述 Fluent 投影，不是 LF↔Fluent mapping distance。

## 3. P / R / U 双向最近邻

P=exact-projected physical；R=raw Fluent centroid physical；U=projected normalized `(x/c, y/b)`。

| 候选与方向 | median | p95 | max | unique target / coverage | collision excess | max multiplicity | ratio≤1.01/1.05/1.10/1.25 |
|---|---:|---:|---:|---:|---:|---:|---:|
| P · LF→Fluent | 7.984 mm | 26.737 mm | 308.755 mm* | 85 / 186 (45.7%) | 171 | 5 | 8 / 34 / 58 / 102 |
| P · Fluent→LF | 7.349 mm | 17.752 mm | 21.042 mm | 80 / 256 (31.3%) | 106 | 4 | 7 / 28 / 47 / 86 |
| R · LF→Fluent | 7.999 mm | 26.735 mm | 308.753 mm* | 86 / 186 (46.2%) | 170 | 5 | 9 / 34 / 60 / 102 |
| R · Fluent→LF | 7.361 mm | 17.745 mm | 21.043 mm | 80 / 256 (31.3%) | 106 | 4 | 7 / 28 / 47 / 86 |
| U · LF→Fluent | 0.00890 | 0.01766 | 0.11111* | 143 / 186 (76.9%) | 113 | 4 | 3 / 15 / 29 / 69 |
| U · Fluent→LF | 0.00713 | 0.01459 | 0.02064 | 143 / 256 (55.9%) | 43 | 3 | 3 / 11 / 22 / 56 |

`*` LF→Fluent maximum 由唯一 domain-mismatch 点 canonical 2188（`x/c=0.0125, y/b=0.675`）主导；除该点外 Candidate P 全部 ≤40 mm。

### 3.1 Candidate P Fluent→LF 核心 fingerprint

- source Fluent count=`186`；target LF pool count=`256`。
- unique LF targets=`80`；target coverage=`31.25%`。
- collision excess=`106`；duplicate LF targets=`60`；maximum multiplicity=`4`。
- mutual nearest pairs=`80`；nearest exact ties=`0`。
- distance min/mean/median/p95/max=`0.323/8.180/7.349/17.752/21.042 mm`。
- within 20 mm=`183/186`；within 30 mm=`186/186`。

这些数值是 geometry audit fingerprint，不是 acceptance gate。31.25% target coverage 不是失败；LF 是更密的预测网格，正式目标不是覆盖全部 LF 点。

## 4. Mutual nearest 与 rectangular injective 诊断

### 4.1 Mutual nearest

| 候选 | pairs | LF 占比 | Fluent 占比 | median | p95 | max |
|---|---:|---:|---:|---:|---:|---:|
| P | 80 | 31.25% | 43.01% | 4.359 mm | 9.821 mm | 20.146 mm |
| R | 80 | 31.25% | 43.01% | 4.351 mm | 9.840 mm | 20.145 mm |
| U | 137 | 53.52% | 73.66% | 0.00605 | 0.01189 | 0.01578 |

### 4.2 Rectangular injective 诊断

| 候选 | pairs | 同普通 NN | 改派 | median | p95 | max | 增量 median/p95/max |
|---|---:|---:|---:|---:|---:|---:|---:|
| P | 186 | 76 | 110 | 9.504 mm | 22.948 mm | 33.454 mm | 1.005 / 9.641 / 16.197 mm |
| R | 186 | 76 | 110 | 9.511 mm | 22.950 mm | 33.454 mm | 1.006 / 9.647 / 16.194 mm |
| U | 186 | 118 | 68 | 0.00966 | 0.02196 | 0.03849 | 0 / 0.01115 / 0.02746 |

## 5. Assignment 稳定性

| 方向 | 比较 | 相同 | 比例 | 改变 | 改变区域 |
|---|---|---:|---:|---:|---|
| LF→Fluent | P vs R | 255 / 256 | 99.61% | 1 | `x/c=0.5, y/b=0.85` |
| LF→Fluent | P vs U | 134 / 256 | 52.34% | 122 | `x/c 0.10–0.9375; y/b 0.75–0.95` |
| Fluent→LF | P vs R | 186 / 186 | 100% | 0 | — |
| Fluent→LF | P vs U | 47 / 186 | 25.27% | 139 | `x/c 0.0967–0.9899; y/b 0.7342–0.9606` |

P 与 R 几乎完全一致，说明 raw centroid → exact projection 不会实质改变当前 assignment。P 与 U 在两个方向分别改变 47.7% 和 74.7%，normalized metric 会实质重写邻接拓扑，不能作为 P 的无害替代；U collision 较低不等于更正确。

## 6. Candidate P 4×4 空间 bins

bin `x0..x3` / `y0..y3` 的边界为 `[0, .25, .5, .75, 1]`；距离单位为 mm。下表完整保留画布中的全部非空 bins；画布未为其余空单元提供统计，本文件不补写不存在的分位数。

| 方向 | bin | count | median | p95 | max | duplicate-target | mutual |
|---|---|---:|---:|---:|---:|---:|---:|
| LF→Fluent | x0·y2 | 3 | 27.742 | 280.654 | 308.755 | 100% | 33.3% |
| LF→Fluent | x0·y3 | 38 | 16.820 | 33.004 | 38.013 | 92.1% | 26.3% |
| LF→Fluent | x1·y3 | 89 | 10.789 | 21.975 | 27.259 | 98.9% | 27.0% |
| LF→Fluent | x2·y3 | 69 | 7.324 | 14.982 | 16.638 | 95.7% | 31.9% |
| LF→Fluent | x3·y3 | 57 | 4.409 | 8.814 | 9.588 | 98.2% | 40.4% |
| Fluent→LF | x0·y2 | 2 | 14.349 | 16.903 | 17.187 | 50.0% | 50.0% |
| Fluent→LF | x0·y3 | 31 | 8.652 | 19.818 | 20.146 | 90.3% | 32.3% |
| Fluent→LF | x1·y3 | 56 | 7.371 | 16.399 | 18.350 | 91.1% | 46.4% |
| Fluent→LF | x2·y3 | 47 | 7.678 | 16.376 | 21.042 | 87.2% | 44.7% |
| Fluent→LF | x3·y3 | 50 | 6.230 | 14.736 | 20.215 | 90.0% | 44.0% |

## 7. Candidate P gate curves

阈值仅用于观察覆盖率；不构成 hard gate。

| 观察阈值 (mm) | LF→Fluent count | LF→Fluent coverage | Fluent→LF count | Fluent→LF coverage |
|---:|---:|---:|---:|---:|
| 1 | 5 | 1.95% | 5 | 2.69% |
| 2 | 13 | 5.08% | 13 | 6.99% |
| 5 | 66 | 25.78% | 56 | 30.11% |
| 10 | 161 | 62.89% | 125 | 67.20% |
| 15 | 199 | 77.73% | 167 | 89.78% |
| 20 | 232 | 90.63% | 183 | 98.39% |
| 30 | 249 | 97.27% | 186 | 100% |
| 40 | 255 | 99.61% | 186 | 100% |
| 50 | 255 | 99.61% | 186 | 100% |
| 75 | 255 | 99.61% | 186 | 100% |
| 100 | 255 | 99.61% | 186 | 100% |

LF→Fluent 在 40–100 mm 均停在 255，剩余单点距离为 308.755 mm。

## 8. Candidate P worst 20 — LF→Fluent

| source | target | source x/c · y/b | dx · dspan (mm) | d1 (mm) | d2/d1 | multiplicity | mutual |
|---:|---:|---|---|---:|---:|---:|---|
| 2188 | 17624 | 0.0125 / 0.6750 | 303.44 / 57.06 | 308.755 | 1.264 | 3 | 否 |
| 2438 | 17724 | 0.1000 / 0.7500 | 37.77 / 4.26 | 38.013 | 1.070 | 5 | 否 |
| 2519 | 17733 | 0.1000 / 0.7750 | -33.61 / -10.67 | 35.268 | 1.132 | 1 | 否 |
| 2443 | 17783 | 0.1625 / 0.7500 | 32.55 / 1.95 | 32.604 | 1.215 | 5 | 否 |
| 2524 | 17881 | 0.1625 / 0.7750 | 31.42 / 8.34 | 32.507 | 1.034 | 5 | 否 |
| 2447 | 17783 | 0.2125 / 0.7500 | -31.81 / 1.95 | 31.874 | 1.139 | 5 | 否 |
| 2528 | 17881 | 0.2125 / 0.7750 | -28.97 / 8.34 | 30.148 | 1.037 | 5 | 否 |
| 2609 | 17980 | 0.2125 / 0.8000 | -29.40 / 4.12 | 29.686 | 1.005 | 5 | 否 |
| 2357 | 17624 | 0.1000 / 0.7250 | 27.19 / 5.51 | 27.742 | 3.949 | 3 | 否 |
| 2605 | 17980 | 0.1625 / 0.8000 | 27.03 / 4.12 | 27.340 | 1.018 | 5 | 否 |
| 2532 | 17983 | 0.2625 / 0.7750 | -27.26 / -0.42 | 27.259 | 1.224 | 4 | 否 |
| 2613 | 18081 | 0.2625 / 0.8000 | -26.85 / 3.85 | 27.123 | 1.093 | 4 | 否 |
| 2442 | 17724 | 0.1500 / 0.7500 | -26.59 / 4.26 | 26.925 | 1.135 | 5 | 否 |
| 2520 | 17781 | 0.1125 / 0.7750 | 26.49 / -3.15 | 26.674 | 1.035 | 4 | 否 |
| 2617 | 18283 | 0.3125 / 0.8000 | 25.92 / 4.66 | 26.340 | 1.052 | 4 | 否 |
| 2621 | 18383 | 0.3625 / 0.8000 | 19.94 / 13.93 | 24.323 | 1.269 | 3 | 否 |
| 2692 | 18179 | 0.2375 / 0.8250 | -22.95 / 1.10 | 22.981 | 1.002 | 4 | 否 |
| 2700 | 18381 | 0.3375 / 0.8250 | -21.66 / 6.14 | 22.514 | 1.094 | 4 | 否 |
| 2448 | 17883 | 0.2250 / 0.7500 | 17.44 / 13.96 | 22.335 | 1.715 | 1 | 否 |
| 2439 | 17724 | 0.1125 / 0.7500 | 21.68 / 4.26 | 22.097 | 1.196 | 5 | 否 |

## 9. Candidate P worst 20 — Fluent→LF

| source | target | source x/c · y/b | dx · dspan (mm) | d1 (mm) | d2/d1 | multiplicity | mutual |
|---:|---:|---|---|---:|---:|---:|---|
| 20379 | 3058 | 0.6784 / 0.9454 | -1.40 / -20.99 | 21.042 | 1.016 | 4 | 否 |
| 20988 | 3073 | 0.9570 / 0.9055 | 1.83 / 20.13 | 20.215 | 1.012 | 3 | 否 |
| 18378 | 2772 | 0.2189 / 0.8468 | 19.88 / 3.28 | 20.146 | 1.133 | 1 | 是 |
| 18078 | 2611 | 0.1868 / 0.8193 | -1.33 / -19.92 | 19.960 | 1.185 | 4 | 否 |
| 18379 | 2698 | 0.2345 / 0.8437 | -3.88 / -19.29 | 19.676 | 1.062 | 4 | 否 |
| 19579 | 2960 | 0.4487 / 0.9177 | 2.31 / -18.20 | 18.350 | 1.029 | 4 | 否 |
| 21088 | 3075 | 0.9753 / 0.9075 | 2.41 / 18.05 | 18.206 | 1.006 | 3 | 否 |
| 19079 | 2870 | 0.3430 / 0.8926 | 1.47 / -18.14 | 18.196 | 1.082 | 4 | 否 |
| 20279 | 3055 | 0.6453 / 0.9426 | -1.52 / -18.13 | 18.191 | 1.020 | 4 | 否 |
| 18679 | 2783 | 0.2761 / 0.8669 | 4.19 / -17.44 | 17.940 | 1.043 | 3 | 否 |
| 17701 | 2440 | 0.1619 / 0.7342 | -5.57 / 16.26 | 17.187 | 1.127 | 3 | 否 |
| 18079 | 2611 | 0.1991 / 0.8165 | -1.34 / -17.04 | 17.096 | 1.246 | 4 | 否 |
| 18380 | 2698 | 0.2487 / 0.8407 | -3.89 / -16.23 | 16.685 | 1.109 | 4 | 否 |
| 20381 | 3058 | 0.7017 / 0.9411 | -1.41 / -16.59 | 16.648 | 1.026 | 4 | 否 |
| 21188 | 3076 | 0.9931 / 0.9094 | -1.81 / 16.10 | 16.200 | 1.019 | 2 | 否 |
| 17733 | 2440 | 0.0967 / 0.7646 | -5.60 / -15.10 | 16.107 | 1.141 | 3 | 否 |
| 18885 | 2790 | 0.4998 / 0.8346 | 1.28 / 15.83 | 15.885 | 1.168 | 2 | 否 |
| 19285 | 2877 | 0.5748 / 0.8598 | 1.39 / 15.68 | 15.742 | 1.057 | 2 | 否 |
| 20179 | 3052 | 0.6135 / 0.9396 | -0.60 / -15.08 | 15.091 | 1.050 | 4 | 否 |
| 18680 | 2783 | 0.2934 / 0.8637 | 4.18 / -14.08 | 14.685 | 1.064 | 3 | 否 |

## 10. 正式实现边界

下一阶段 geometry pairing 可承载 source/target canonical indices、sheet identity、distance、`dx/dspan`、mutual flag、LF target multiplicity、稳定 canonical-index tie-break 和显式 metric=P。

本审计不冻结 `accepted` mask、hard distance gate、nose/LE/TE/root/outer-span buffer、Hungarian assignment、mutual-only subset、temperature ingestion 或 error calculation。推荐分层保持：geometry pairing → mapping diagnostics → future acceptance policy → physical comparison。