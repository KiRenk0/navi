# Ablation Report: G_qscale09_11

> Generated: 2026-06-30 00:57

## Description

Negative-control: q_scale_lam=0.9, q_scale_turb=1.1

## Overrides

```
{
  "q_scale_lam": 0.9,
  "q_scale_turb": 1.1
}
```

## Region Summary

| case | region | n_aligned | turb_fraction | q_ratio_mean | q_ratio_std | q_ratio_iqr | lam_q_ratio_mean | turb_q_ratio_mean | p_ratio_mean |
|---|---|---|---|---|---|---|---|---|---|
| N/A | N/A | N/A | 0.0000 | 2.9534 | 0.2418 | 0.2418 | 2.9534 | N/A | 0.9923 |
| N/A | N/A | N/A | 0.0000 | 1.8974 | 0.3879 | 0.3360 | 1.8974 | N/A | 1.3294 |
| N/A | N/A | N/A | 0.0000 | 0.6386 | 0.3716 | 0.2250 | 0.6386 | N/A | 1.3889 |
| N/A | N/A | N/A | 0.0110 | 0.5726 | 0.2139 | 0.3524 | 0.5726 | N/A | 1.4393 |
| N/A | N/A | N/A | 0.6101 | 1.3952 | 1.1222 | 1.8079 | 0.3653 | 2.4458 | 1.4342 |
| N/A | N/A | N/A | 0.0000 | 3.4694 | 0.2668 | 0.2668 | 3.4694 | N/A | 0.9535 |
| N/A | N/A | N/A | 0.0000 | 2.4353 | 0.4979 | 0.4426 | 2.4353 | N/A | 1.4419 |
| N/A | N/A | N/A | 0.0000 | 0.8272 | 0.4595 | 0.2701 | 0.8272 | N/A | 1.5752 |
| N/A | N/A | N/A | 0.0000 | 0.7882 | 0.3009 | 0.4910 | 0.7882 | N/A | 1.6820 |
| N/A | N/A | N/A | 0.2792 | 0.8432 | 0.9985 | 0.1575 | 0.4763 | 3.3827 | 1.6657 |

## Figures

- `G_qscale09_11_ma6_a5_h30km_qratio_vs_x.png`
- `G_qscale09_11_ma6_a5_h30km_qratio_vs_wtr.png`
- `G_qscale09_11_ma6_a5_h30km_qratio_box.png`
- `G_qscale09_11_ma8_a5_h30km_qratio_vs_x.png`
- `G_qscale09_11_ma8_a5_h30km_qratio_vs_wtr.png`
- `G_qscale09_11_ma8_a5_h30km_qratio_box.png`

## Observations (evidence only, no physical conclusions)

- ma6_a5_h30km / cap_mask: q_ratio_mean=2.9534 (overestimate), std=0.2418, n_aligned=2
- ma6_a5_h30km / true_nose_cap: q_ratio_mean=1.8974 (overestimate), std=0.3879, n_aligned=8
  - p_ratio_mean=1.3294 (deviation from 1.0 = +0.3294)
  - spearman_x_qratio=-0.5714 (strong x-trend in q_ratio)
- ma6_a5_h30km / leading_edge_near: q_ratio_mean=0.6386 (underestimate), std=0.3716, n_aligned=1700
  - p_ratio_mean=1.3889 (deviation from 1.0 = +0.3889)
- ma6_a5_h30km / windward_body: q_ratio_mean=0.5726 (underestimate), std=0.2139, n_aligned=251
  - p_ratio_mean=1.4393 (deviation from 1.0 = +0.4393)
  - spearman_x_qratio=-0.6544 (strong x-trend in q_ratio)
- ma6_a5_h30km / aft_body: q_ratio_mean=1.3952 (overestimate), std=1.1222, n_aligned=499
  - p_ratio_mean=1.4342 (deviation from 1.0 = +0.4342)
- ma8_a5_h30km / cap_mask: q_ratio_mean=3.4694 (overestimate), std=0.2668, n_aligned=2
  - p_ratio_mean=0.9535 (deviation from 1.0 = -0.0465)
- ma8_a5_h30km / true_nose_cap: q_ratio_mean=2.4353 (overestimate), std=0.4979, n_aligned=8
  - p_ratio_mean=1.4419 (deviation from 1.0 = +0.4419)
- ma8_a5_h30km / leading_edge_near: q_ratio_mean=0.8272 (underestimate), std=0.4595, n_aligned=1700
  - p_ratio_mean=1.5752 (deviation from 1.0 = +0.5752)
- ma8_a5_h30km / windward_body: q_ratio_mean=0.7882 (underestimate), std=0.3009, n_aligned=251
  - p_ratio_mean=1.6820 (deviation from 1.0 = +0.6820)
  - spearman_x_qratio=-0.5977 (strong x-trend in q_ratio)
- ma8_a5_h30km / aft_body: q_ratio_mean=0.8432 (underestimate), std=0.9985, n_aligned=499
  - p_ratio_mean=1.6657 (deviation from 1.0 = +0.6657)

---
*Evidence-only report. No physical conclusions or route changes.*
