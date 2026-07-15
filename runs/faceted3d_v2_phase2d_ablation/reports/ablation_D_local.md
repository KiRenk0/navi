# Ablation Report: D_local

> Generated: 2026-06-30 00:56

## Description

x_phys-only: x_length_mode = local

## Overrides

```
{
  "faceted3d.x_length_mode": "local"
}
```

## Region Summary

| case | region | n_aligned | turb_fraction | q_ratio_mean | q_ratio_std | q_ratio_iqr | lam_q_ratio_mean | turb_q_ratio_mean | p_ratio_mean |
|---|---|---|---|---|---|---|---|---|---|
| N/A | N/A | N/A | 0.0000 | 7.9847 | 0.6211 | 0.6211 | 7.9847 | N/A | 0.9923 |
| N/A | N/A | N/A | 0.0000 | 1.8820 | 0.2039 | 0.3863 | 1.8820 | N/A | 1.3294 |
| N/A | N/A | N/A | 0.0005 | 0.6542 | 0.3353 | 0.2298 | 0.6534 | 2.0775 | 1.3889 |
| N/A | N/A | N/A | 0.0276 | 0.6421 | 0.3216 | 0.3945 | 0.6287 | 3.9962 | 1.4393 |
| N/A | N/A | N/A | 0.8069 | 1.7325 | 0.8633 | 0.3842 | 0.3902 | 2.1482 | 1.4342 |
| N/A | N/A | N/A | 0.0000 | 8.4063 | 0.6121 | 0.6121 | 8.4063 | N/A | 0.9535 |
| N/A | N/A | N/A | 0.0000 | 2.3844 | 0.2601 | 0.4373 | 2.3844 | N/A | 1.4419 |
| N/A | N/A | N/A | 0.0000 | 0.8462 | 0.4149 | 0.2686 | 0.8462 | N/A | 1.5752 |
| N/A | N/A | N/A | 0.0000 | 0.8656 | 0.3389 | 0.5599 | 0.8656 | N/A | 1.6820 |
| N/A | N/A | N/A | 0.4096 | 1.1817 | 1.0966 | 1.6640 | 0.5094 | 2.7458 | 1.6657 |

## Figures

- `D_local_ma6_a5_h30km_qratio_vs_x.png`
- `D_local_ma6_a5_h30km_qratio_vs_wtr.png`
- `D_local_ma6_a5_h30km_qratio_box.png`
- `D_local_ma8_a5_h30km_qratio_vs_x.png`
- `D_local_ma8_a5_h30km_qratio_vs_wtr.png`
- `D_local_ma8_a5_h30km_qratio_box.png`

## Observations (evidence only, no physical conclusions)

- ma6_a5_h30km / cap_mask: q_ratio_mean=7.9847 (overestimate), std=0.6211, n_aligned=2
- ma6_a5_h30km / true_nose_cap: q_ratio_mean=1.8820 (overestimate), std=0.2039, n_aligned=8
  - p_ratio_mean=1.3294 (deviation from 1.0 = +0.3294)
  - spearman_x_qratio=-0.6190 (strong x-trend in q_ratio)
- ma6_a5_h30km / leading_edge_near: q_ratio_mean=0.6542 (underestimate), std=0.3353, n_aligned=1700
  - p_ratio_mean=1.3889 (deviation from 1.0 = +0.3889)
- ma6_a5_h30km / windward_body: q_ratio_mean=0.6421 (underestimate), std=0.3216, n_aligned=251
  - p_ratio_mean=1.4393 (deviation from 1.0 = +0.4393)
  - spearman_x_qratio=-0.6936 (strong x-trend in q_ratio)
- ma6_a5_h30km / aft_body: q_ratio_mean=1.7325 (overestimate), std=0.8633, n_aligned=499
  - p_ratio_mean=1.4342 (deviation from 1.0 = +0.4342)
- ma8_a5_h30km / cap_mask: q_ratio_mean=8.4063 (overestimate), std=0.6121, n_aligned=2
  - p_ratio_mean=0.9535 (deviation from 1.0 = -0.0465)
- ma8_a5_h30km / true_nose_cap: q_ratio_mean=2.3844 (overestimate), std=0.2601, n_aligned=8
  - p_ratio_mean=1.4419 (deviation from 1.0 = +0.4419)
- ma8_a5_h30km / leading_edge_near: q_ratio_mean=0.8462 (underestimate), std=0.4149, n_aligned=1700
  - p_ratio_mean=1.5752 (deviation from 1.0 = +0.5752)
- ma8_a5_h30km / windward_body: q_ratio_mean=0.8656 (underestimate), std=0.3389, n_aligned=251
  - p_ratio_mean=1.6820 (deviation from 1.0 = +0.6820)
  - spearman_x_qratio=-0.6472 (strong x-trend in q_ratio)
- ma8_a5_h30km / aft_body: q_ratio_mean=1.1817 (overestimate), std=1.0966, n_aligned=499
  - p_ratio_mean=1.6657 (deviation from 1.0 = +0.6657)

---
*Evidence-only report. No physical conclusions or route changes.*
