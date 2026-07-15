---
name: stl-outline-te-cleaning
description: Iterative linear fitting to clean trailing edge outline from STL when internal structure (ribs, spars) and root rib faces pollute per-bin x_max values
source: auto-skill
extracted_at: '2026-06-28T01:30:00.000Z'
---

## Problem

When extracting a 2D outline from an ASCII STL via x-span projection (binning by span, taking x_min for LE and x_max for TE), the TE can be severely corrupted by:

1. **Root rib face vertices** — span≈0 bins contain rib face vertices covering the full chord [0, Lx], not wing TE vertices. x_max in these bins is ~0.003–0.35 instead of the true TE (~3.5).
2. **Internal structure facets** — ribs and spars inside the STL have vertices at various span positions with x values far from the true TE, causing x_max to fluctuate wildly (e.g., 2.4–3.6 for a wing with true TE at ~3.5–3.6).

A simple linear fit on all TE points is biased by these outliers and produces incorrect TE values, especially near the root.

## Solution: Iterative Linear Fitting

Replace a single `np.polyfit(span, x, 1)` with an iterative fit that rejects outliers beyond a threshold:

```python
def _iterative_te_fit(span, x, n_iter=20, threshold=0.3):
    """Iteratively fit TE line, rejecting outliers beyond threshold (meters)."""
    mask = np.ones(len(span), dtype=bool)
    for _ in range(n_iter):
        A = np.column_stack([span[mask], np.ones_like(span[mask])])
        coeffs, *_ = np.linalg.lstsq(A, x[mask], rcond=None)
        x_fit = np.column_stack([span, np.ones_like(span)]) @ coeffs
        residuals = np.abs(x - x_fit)
        new_mask = residuals <= threshold
        if new_mask.sum() == mask.sum():
            break  # converged
        mask = new_mask
        if mask.sum() < 10:
            break  # too few points — abort
    return coeffs, mask, x_fit
```

Then apply:

```python
coeffs_te, te_inlier_mask, te_x_fit = _iterative_te_fit(te_span_arr, te_x_arr)
# Use fit where raw is an outlier, raw elsewhere
te_x_clean = np.where(te_inlier_mask, te_x_arr, te_x_fit)
# Optional: smooth the cleaned TE
te_x_smooth = _smooth(te_x_clean, window=5)
```

## Parameters (tuned for HTV2 wing, 3.6m chord)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `threshold` | 0.3 m | ~8% of chord — allows for slight TE curvature while rejecting internal structure outliers |
| `n_iter` | 20 | Generous; typically converges in 3–5 iterations |
| `min_points_per_bin` | 10 | Rejects sparse bins (root rib region) that have no wing TE vertices |
| `smooth_window` | 5 | Gentle smoothing to remove residual noise without distorting shape |

## Expected outcome

- ~70% of bins become inliers (true TE vertices)
- ~30% are outliers (root rib, internal structure) replaced by fit values
- TE line converges to the true wing trailing edge (e.g., `x = 0.05*span + 3.46` for a near-straight TE)
- Root TE value is correctly extrapolated (~3.52 for a 3.6m chord wing)
- The fit line represents the straight-line approximation of the wing TE connecting root TE to tip TE

## Integration into outline extraction pipeline

The full pipeline is:

1. Parse ASCII STL vertices
2. Transform coordinates (CAD → solver: scale, span_sign)
3. Filter right-half (span >= 0)
4. Bin by span with nose refinement (finer bins near nose)
5. Per bin: LE = x_min (or percentile), TE = x_max
6. **Apply iterative TE fit** (this skill)
7. Smooth LE + enforce monotonicity
8. Assemble closed outline: LE(root→tip) + TE(tip→root) + close

## Validation

After cleaning, verify:
- TE x values at root and tip are physically plausible (e.g., ~3.5 for a 3.6m chord wing)
- TE is monotonic or near-linear (slight sweep is OK)
- The closed outline's first and last points match (closing point = LE root)
- Plot raw TE vs cleaned TE vs fit line to visually confirm outlier rejection
