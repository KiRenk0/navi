# Ablation Report: G_qscale10_10

> Generated: 2026-06-30 00:57

## Description

Negative-control: q_scale_lam=1.0, q_scale_turb=1.0 (should match baseline)

## Overrides

```
{
  "q_scale_lam": 1.0,
  "q_scale_turb": 1.0
}
```

## Region Summary

| case | region | n_aligned | turb_fraction | q_ratio_mean | q_ratio_std | q_ratio_iqr | lam_q_ratio_mean | turb_q_ratio_mean | p_ratio_mean |
|---|---|---|---|---|---|---|---|---|---|
| N/A | N/A | N/A | 0.0000 | 3.2816 | 0.2687 | 0.2687 | 3.2816 | N/A | 0.9923 |
| N/A | N/A | N/A | 0.0000 | 2.1082 | 0.4310 | 0.3733 | 2.1082 | N/A | 1.3294 |
| N/A | N/A | N/A | 0.0000 | 0.7095 | 0.4129 | 0.2500 | 0.7095 | N/A | 1.3889 |
| N/A | N/A | N/A | 0.0110 | 0.6362 | 0.2377 | 0.3915 | 0.6362 | N/A | 1.4393 |
| N/A | N/A | N/A | 0.6101 | 1.3056 | 0.9864 | 1.5712 | 0.4059 | 2.2235 | 1.4342 |
| N/A | N/A | N/A | 0.0000 | 3.8549 | 0.2965 | 0.2965 | 3.8549 | N/A | 0.9535 |
| N/A | N/A | N/A | 0.0000 | 2.7058 | 0.5532 | 0.4918 | 2.7058 | N/A | 1.4419 |
| N/A | N/A | N/A | 0.0000 | 0.9191 | 0.5106 | 0.3002 | 0.9191 | N/A | 1.5752 |
| N/A | N/A | N/A | 0.0000 | 0.8757 | 0.3343 | 0.5456 | 0.8757 | N/A | 1.6820 |
| N/A | N/A | N/A | 0.2792 | 0.8506 | 0.8795 | 0.1750 | 0.5292 | 3.0752 | 1.6657 |

## Figures

- `G_qscale10_10_ma6_a5_h30km_qratio_vs_x.png`
- `G_qscale10_10_ma6_a5_h30km_qratio_vs_wtr.png`
- `G_qscale10_10_ma6_a5_h30km_qratio_box.png`
- `G_qscale10_10_ma8_a5_h30km_qratio_vs_x.png`
- `G_qscale10_10_ma8_a5_h30km_qratio_vs_wtr.png`
- `G_qscale10_10_ma8_a5_h30km_qratio_box.png`

## Observations (evidence only, no physical conclusions)

- ma6_a5_h30km / cap_mask: q_ratio_mean=3.2816 (overestimate), std=0.2687, n_aligned=2
- ma6_a5_h30km / true_nose_cap: q_ratio_mean=2.1082 (overestimate), std=0.4310, n_aligned=8
  - p_ratio_mean=1.3294 (deviation from 1.0 = +0.3294)
  - spearman_x_qratio=-0.5714 (strong x-trend in q_ratio)
- ma6_a5_h30km / leading_edge_near: q_ratio_mean=0.7095 (underestimate), std=0.4129, n_aligned=1700
  - p_ratio_mean=1.3889 (deviation from 1.0 = +0.3889)
- ma6_a5_h30km / windward_body: q_ratio_mean=0.6362 (underestimate), std=0.2377, n_aligned=251
  - p_ratio_mean=1.4393 (deviation from 1.0 = +0.4393)
  - spearman_x_qratio=-0.6544 (strong x-trend in q_ratio)
- ma6_a5_h30km / aft_body: q_ratio_mean=1.3056 (overestimate), std=0.9864, n_aligned=499
  - p_ratio_mean=1.4342 (deviation from 1.0 = +0.4342)
- ma8_a5_h30km / cap_mask: q_ratio_mean=3.8549 (overestimate), std=0.2965, n_aligned=2
  - p_ratio_mean=0.9535 (deviation from 1.0 = -0.0465)
- ma8_a5_h30km / true_nose_cap: q_ratio_mean=2.7058 (overestimate), std=0.5532, n_aligned=8
  - p_ratio_mean=1.4419 (deviation from 1.0 = +0.4419)
- ma8_a5_h30km / leading_edge_near: q_ratio_mean=0.9191 (underestimate), std=0.5106, n_aligned=1700
  - p_ratio_mean=1.5752 (deviation from 1.0 = +0.5752)
- ma8_a5_h30km / windward_body: q_ratio_mean=0.8757 (underestimate), std=0.3343, n_aligned=251
  - p_ratio_mean=1.6820 (deviation from 1.0 = +0.6820)
  - spearman_x_qratio=-0.5977 (strong x-trend in q_ratio)
- ma8_a5_h30km / aft_body: q_ratio_mean=0.8506 (underestimate), std=0.8795, n_aligned=499
  - p_ratio_mean=1.6657 (deviation from 1.0 = +0.6657)

---
*Evidence-only report. No physical conclusions or route changes.*
