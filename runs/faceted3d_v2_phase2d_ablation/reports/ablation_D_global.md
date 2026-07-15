# Ablation Report: D_global

> Generated: 2026-06-30 00:56

## Description

x_phys-only: x_length_mode = global

## Overrides

```
{
  "faceted3d.x_length_mode": "global"
}
```

## Region Summary

| case | region | n_aligned | turb_fraction | q_ratio_mean | q_ratio_std | q_ratio_iqr | lam_q_ratio_mean | turb_q_ratio_mean | p_ratio_mean |
|---|---|---|---|---|---|---|---|---|---|
| N/A | N/A | N/A | 0.0000 | 7.9847 | 0.6211 | 0.6211 | 7.9847 | N/A | 0.9923 |
| N/A | N/A | N/A | 0.0000 | 1.7169 | 0.2690 | 0.2185 | 1.7169 | N/A | 1.3294 |
| N/A | N/A | N/A | 0.8428 | 1.3222 | 0.5227 | 0.5862 | 0.3766 | 1.5191 | 1.3889 |
| N/A | N/A | N/A | 0.2762 | 0.9652 | 0.8026 | 0.7149 | 0.6017 | 2.2916 | 1.4393 |
| N/A | N/A | N/A | 1.0000 | 1.9945 | 0.4516 | 0.1774 | N/A | 1.9945 | 1.4342 |
| N/A | N/A | N/A | 0.0000 | 8.4063 | 0.6121 | 0.6121 | 8.4063 | N/A | 0.9535 |
| N/A | N/A | N/A | 0.0000 | 2.1683 | 0.3011 | 0.2727 | 2.1683 | N/A | 1.4419 |
| N/A | N/A | N/A | 0.6204 | 1.4023 | 0.7665 | 1.5395 | 0.4242 | 1.8930 | 1.5752 |
| N/A | N/A | N/A | 0.0000 | 0.7655 | 0.3575 | 0.6235 | 0.7655 | N/A | 1.6820 |
| N/A | N/A | N/A | 0.8942 | 2.4478 | 0.7284 | 0.4669 | 0.5629 | 2.5727 | 1.6657 |

## Figures

- `D_global_ma6_a5_h30km_qratio_vs_x.png`
- `D_global_ma6_a5_h30km_qratio_vs_wtr.png`
- `D_global_ma6_a5_h30km_qratio_box.png`
- `D_global_ma8_a5_h30km_qratio_vs_x.png`
- `D_global_ma8_a5_h30km_qratio_vs_wtr.png`
- `D_global_ma8_a5_h30km_qratio_box.png`

## Observations (evidence only, no physical conclusions)

- ma6_a5_h30km / cap_mask: q_ratio_mean=7.9847 (overestimate), std=0.6211, n_aligned=2
- ma6_a5_h30km / true_nose_cap: q_ratio_mean=1.7169 (overestimate), std=0.2690, n_aligned=8
  - p_ratio_mean=1.3294 (deviation from 1.0 = +0.3294)
  - spearman_x_qratio=-0.9524 (strong x-trend in q_ratio)
- ma6_a5_h30km / leading_edge_near: q_ratio_mean=1.3222 (overestimate), std=0.5227, n_aligned=1700
  - p_ratio_mean=1.3889 (deviation from 1.0 = +0.3889)
- ma6_a5_h30km / windward_body: q_ratio_mean=0.9652 (neutral), std=0.8026, n_aligned=251
  - p_ratio_mean=1.4393 (deviation from 1.0 = +0.4393)
- ma6_a5_h30km / aft_body: q_ratio_mean=1.9945 (overestimate), std=0.4516, n_aligned=499
  - p_ratio_mean=1.4342 (deviation from 1.0 = +0.4342)
- ma8_a5_h30km / cap_mask: q_ratio_mean=8.4063 (overestimate), std=0.6121, n_aligned=2
  - p_ratio_mean=0.9535 (deviation from 1.0 = -0.0465)
- ma8_a5_h30km / true_nose_cap: q_ratio_mean=2.1683 (overestimate), std=0.3011, n_aligned=8
  - p_ratio_mean=1.4419 (deviation from 1.0 = +0.4419)
  - spearman_x_qratio=-0.8095 (strong x-trend in q_ratio)
- ma8_a5_h30km / leading_edge_near: q_ratio_mean=1.4023 (overestimate), std=0.7665, n_aligned=1700
  - p_ratio_mean=1.5752 (deviation from 1.0 = +0.5752)
  - spearman_x_qratio=0.6212 (strong x-trend in q_ratio)
- ma8_a5_h30km / windward_body: q_ratio_mean=0.7655 (underestimate), std=0.3575, n_aligned=251
  - p_ratio_mean=1.6820 (deviation from 1.0 = +0.6820)
  - spearman_x_qratio=-0.6765 (strong x-trend in q_ratio)
- ma8_a5_h30km / aft_body: q_ratio_mean=2.4478 (overestimate), std=0.7284, n_aligned=499
  - p_ratio_mean=1.6657 (deviation from 1.0 = +0.6657)

---
*Evidence-only report. No physical conclusions or route changes.*
