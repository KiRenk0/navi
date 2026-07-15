# Ablation Report: G_qscale08_12

> Generated: 2026-06-30 00:57

## Description

Negative-control: q_scale_lam=0.8, q_scale_turb=1.2

## Overrides

```
{
  "q_scale_lam": 0.8,
  "q_scale_turb": 1.2
}
```

## Region Summary

| case | region | n_aligned | turb_fraction | q_ratio_mean | q_ratio_std | q_ratio_iqr | lam_q_ratio_mean | turb_q_ratio_mean | p_ratio_mean |
|---|---|---|---|---|---|---|---|---|---|
| N/A | N/A | N/A | 0.0000 | 2.6253 | 0.2149 | 0.2149 | 2.6253 | N/A | 0.9923 |
| N/A | N/A | N/A | 0.0000 | 1.6866 | 0.3448 | 0.2987 | 1.6866 | N/A | 1.3294 |
| N/A | N/A | N/A | 0.0000 | 0.5676 | 0.3303 | 0.2000 | 0.5676 | N/A | 1.3889 |
| N/A | N/A | N/A | 0.0110 | 0.5090 | 0.1902 | 0.3132 | 0.5090 | N/A | 1.4393 |
| N/A | N/A | N/A | 0.6101 | 1.4847 | 1.2582 | 2.0447 | 0.3247 | 2.6682 | 1.4342 |
| N/A | N/A | N/A | 0.0000 | 3.0839 | 0.2372 | 0.2372 | 3.0839 | N/A | 0.9535 |
| N/A | N/A | N/A | 0.0000 | 2.1647 | 0.4425 | 0.3934 | 2.1647 | N/A | 1.4419 |
| N/A | N/A | N/A | 0.0000 | 0.7353 | 0.4085 | 0.2401 | 0.7353 | N/A | 1.5752 |
| N/A | N/A | N/A | 0.0000 | 0.7006 | 0.2674 | 0.4365 | 0.7006 | N/A | 1.6820 |
| N/A | N/A | N/A | 0.2792 | 0.8358 | 1.1182 | 0.1400 | 0.4234 | 3.6902 | 1.6657 |

## Figures

- `G_qscale08_12_ma6_a5_h30km_qratio_vs_x.png`
- `G_qscale08_12_ma6_a5_h30km_qratio_vs_wtr.png`
- `G_qscale08_12_ma6_a5_h30km_qratio_box.png`
- `G_qscale08_12_ma8_a5_h30km_qratio_vs_x.png`
- `G_qscale08_12_ma8_a5_h30km_qratio_vs_wtr.png`
- `G_qscale08_12_ma8_a5_h30km_qratio_box.png`

## Observations (evidence only, no physical conclusions)

- ma6_a5_h30km / cap_mask: q_ratio_mean=2.6253 (overestimate), std=0.2149, n_aligned=2
- ma6_a5_h30km / true_nose_cap: q_ratio_mean=1.6866 (overestimate), std=0.3448, n_aligned=8
  - p_ratio_mean=1.3294 (deviation from 1.0 = +0.3294)
  - spearman_x_qratio=-0.5714 (strong x-trend in q_ratio)
- ma6_a5_h30km / leading_edge_near: q_ratio_mean=0.5676 (underestimate), std=0.3303, n_aligned=1700
  - p_ratio_mean=1.3889 (deviation from 1.0 = +0.3889)
- ma6_a5_h30km / windward_body: q_ratio_mean=0.5090 (underestimate), std=0.1902, n_aligned=251
  - p_ratio_mean=1.4393 (deviation from 1.0 = +0.4393)
  - spearman_x_qratio=-0.6544 (strong x-trend in q_ratio)
- ma6_a5_h30km / aft_body: q_ratio_mean=1.4847 (overestimate), std=1.2582, n_aligned=499
  - p_ratio_mean=1.4342 (deviation from 1.0 = +0.4342)
- ma8_a5_h30km / cap_mask: q_ratio_mean=3.0839 (overestimate), std=0.2372, n_aligned=2
  - p_ratio_mean=0.9535 (deviation from 1.0 = -0.0465)
- ma8_a5_h30km / true_nose_cap: q_ratio_mean=2.1647 (overestimate), std=0.4425, n_aligned=8
  - p_ratio_mean=1.4419 (deviation from 1.0 = +0.4419)
- ma8_a5_h30km / leading_edge_near: q_ratio_mean=0.7353 (underestimate), std=0.4085, n_aligned=1700
  - p_ratio_mean=1.5752 (deviation from 1.0 = +0.5752)
- ma8_a5_h30km / windward_body: q_ratio_mean=0.7006 (underestimate), std=0.2674, n_aligned=251
  - p_ratio_mean=1.6820 (deviation from 1.0 = +0.6820)
  - spearman_x_qratio=-0.5977 (strong x-trend in q_ratio)
- ma8_a5_h30km / aft_body: q_ratio_mean=0.8358 (underestimate), std=1.1182, n_aligned=499
  - p_ratio_mean=1.6657 (deviation from 1.0 = +0.6657)

---
*Evidence-only report. No physical conclusions or route changes.*
