# Ablation Report: C_logistic

> Generated: 2026-06-30 00:56

## Description

Intermittency-only: transition.weighting = logistic

## Overrides

```
{
  "transition.weighting": "logistic"
}
```

## Region Summary

| case | region | n_aligned | turb_fraction | q_ratio_mean | q_ratio_std | q_ratio_iqr | lam_q_ratio_mean | turb_q_ratio_mean | p_ratio_mean |
|---|---|---|---|---|---|---|---|---|---|
| N/A | N/A | N/A | 0.0000 | 7.9847 | 0.6211 | 0.6211 | 7.9847 | N/A | 0.9923 |
| N/A | N/A | N/A | 0.0000 | 1.9287 | 0.2228 | 0.4162 | 1.9287 | N/A | 1.3294 |
| N/A | N/A | N/A | 0.0000 | 0.6854 | 0.3502 | 0.2378 | 0.6854 | N/A | 1.3889 |
| N/A | N/A | N/A | 0.0110 | 0.6362 | 0.2377 | 0.3915 | 0.6362 | N/A | 1.4393 |
| N/A | N/A | N/A | 0.6101 | 0.9225 | 0.5875 | 0.8529 | 0.4059 | 1.4495 | 1.4342 |
| N/A | N/A | N/A | 0.0000 | 8.4063 | 0.6121 | 0.6121 | 8.4063 | N/A | 0.9535 |
| N/A | N/A | N/A | 0.0000 | 2.4449 | 0.2946 | 0.3964 | 2.4449 | N/A | 1.4419 |
| N/A | N/A | N/A | 0.0000 | 0.8882 | 0.4367 | 0.2843 | 0.8882 | N/A | 1.5752 |
| N/A | N/A | N/A | 0.0000 | 0.8757 | 0.3343 | 0.5456 | 0.8757 | N/A | 1.6820 |
| N/A | N/A | N/A | 0.2792 | 0.7005 | 0.4837 | 0.1750 | 0.5292 | 1.8858 | 1.6657 |

## Figures

- `C_logistic_ma6_a5_h30km_qratio_vs_x.png`
- `C_logistic_ma6_a5_h30km_qratio_vs_wtr.png`
- `C_logistic_ma6_a5_h30km_qratio_box.png`
- `C_logistic_ma8_a5_h30km_qratio_vs_x.png`
- `C_logistic_ma8_a5_h30km_qratio_vs_wtr.png`
- `C_logistic_ma8_a5_h30km_qratio_box.png`

## Observations (evidence only, no physical conclusions)

- ma6_a5_h30km / cap_mask: q_ratio_mean=7.9847 (overestimate), std=0.6211, n_aligned=2
- ma6_a5_h30km / true_nose_cap: q_ratio_mean=1.9287 (overestimate), std=0.2228, n_aligned=8
  - p_ratio_mean=1.3294 (deviation from 1.0 = +0.3294)
  - spearman_x_qratio=-0.5238 (strong x-trend in q_ratio)
- ma6_a5_h30km / leading_edge_near: q_ratio_mean=0.6854 (underestimate), std=0.3502, n_aligned=1700
  - p_ratio_mean=1.3889 (deviation from 1.0 = +0.3889)
- ma6_a5_h30km / windward_body: q_ratio_mean=0.6362 (underestimate), std=0.2377, n_aligned=251
  - p_ratio_mean=1.4393 (deviation from 1.0 = +0.4393)
  - spearman_x_qratio=-0.6544 (strong x-trend in q_ratio)
- ma6_a5_h30km / aft_body: q_ratio_mean=0.9225 (underestimate), std=0.5875, n_aligned=499
  - p_ratio_mean=1.4342 (deviation from 1.0 = +0.4342)
- ma8_a5_h30km / cap_mask: q_ratio_mean=8.4063 (overestimate), std=0.6121, n_aligned=2
  - p_ratio_mean=0.9535 (deviation from 1.0 = -0.0465)
- ma8_a5_h30km / true_nose_cap: q_ratio_mean=2.4449 (overestimate), std=0.2946, n_aligned=8
  - p_ratio_mean=1.4419 (deviation from 1.0 = +0.4419)
- ma8_a5_h30km / leading_edge_near: q_ratio_mean=0.8882 (underestimate), std=0.4367, n_aligned=1700
  - p_ratio_mean=1.5752 (deviation from 1.0 = +0.5752)
- ma8_a5_h30km / windward_body: q_ratio_mean=0.8757 (underestimate), std=0.3343, n_aligned=251
  - p_ratio_mean=1.6820 (deviation from 1.0 = +0.6820)
  - spearman_x_qratio=-0.5977 (strong x-trend in q_ratio)
- ma8_a5_h30km / aft_body: q_ratio_mean=0.7005 (underestimate), std=0.4837, n_aligned=499
  - p_ratio_mean=1.6657 (deviation from 1.0 = +0.6657)

---
*Evidence-only report. No physical conclusions or route changes.*
