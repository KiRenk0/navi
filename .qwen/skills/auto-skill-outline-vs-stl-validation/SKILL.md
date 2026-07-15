---
name: outline-vs-stl-validation
description: Procedure to validate a CATIA-exported outline CSV against an ASCII STL, including geometry checker run, per-station error analysis, regional breakdowns, and defect diagnosis
source: auto-skill
extracted_at: '2026-06-28T04:10:00.000Z'
---

## Context

When a new outline CSV is provided (e.g., from CATIA projection), it must be validated against the corresponding STL before being used in the solver pipeline. The outline may have defects: sparse TE points, missing mid-span LE points, incorrect z_m sign, or incomplete closure.

## Step 1: Run the geometry checker

```powershell
python scripts/geometry/prepare_geometry.py `
  --stl new_spec/<stl_file>.stl `
  --outline new_spec/<outline_file>.csv `
  --unit mm `
  --span-sign -1 `
  --expected-length-m 3.6 `
  --out-dir <output_dir>
```

Check the output:
- `overall` in `geometry_check.json` (PASS/FAIL)
- `b_half` vs STL right-half `span_max` — should match within ~5 mm
- z_m sign: solver uses `span = -z_m`, so right-half outline should have `z_m <= 0`
- Number of outline points — very few points (< 50) is a red flag

## Step 2: Analyze outline structure

Print all points to understand the outline's topology:

```python
import numpy as np
d = np.genfromtxt('<outline.csv>', delimiter=',', names=True, dtype=float, encoding='utf-8')
ox, oz = d['x_m'], d['z_m']
ospan = -oz
tip_idx = int(np.argmax(ospan))
print(f"Total points: {len(ox)}")
print(f"Tip index: {tip_idx}, span={ospan[tip_idx]:.6f}, x={ox[tip_idx]:.6f}")
for i in range(len(ox)):
    print(f"  [{i:3d}] x={ox[i]:.6f}  z={oz[i]:.6f}  span={ospan[i]:.6f}")
```

Expected structure for a valid outline:
- **LE side**: indices 0..tip_idx, span increasing from 0 to b_half, x increasing from nose to tip
- **TE side**: indices tip_idx..-1, span decreasing from b_half to 0, x near max chord
- **Closing point**: last point = first point (x, z match)

Common defects:
| Defect | Symptom |
|--------|---------|
| **Sparse TE** | TE side has only 2–3 points (tip, root, close) — TE is a straight line, not the actual wing TE |
| **Missing mid-span LE** | LE side has dense nose points (span<0.05) then jumps directly to tip — no points in span 0.05–0.9 |
| **Only nose region** | All points concentrated at span<0.05 — CATIA only exported the nose detail |
| **z_m sign reversed** | Most z_m > 0 — solver expects z_m <= 0 for right half |
| **Not closed** | First and last points don't match |

## Step 3: Per-station error analysis

Create a temporary analysis script in the output directory (NOT in `scripts/`):

### 3a. Parse STL and bin by span

```python
def parse_stl_vertices(path):
    vertices = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("vertex"): continue
            parts = line.split()
            if len(parts) < 4: continue
            try: vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except: pass
    return np.array(vertices, dtype=float).reshape(-1, 3)

arr = parse_stl_vertices(stl_path)
x_sol = arr[:, 0] * scale          # CAD mm -> m
span_sol = span_sign * arr[:, 2] * scale  # span_sign = -1

right = span_sol >= -1e-9
x_r = x_sol[right]
span_r = span_sol[right]

n_bins = 300
span_bins = np.linspace(0, span_max_stl, n_bins + 1)
bin_centers = (span_bins[:-1] + span_bins[1:]) / 2

stl_x_min = np.full(n_bins, np.nan)
stl_x_max = np.full(n_bins, np.nan)
for i in range(n_bins):
    lo, hi = span_bins[i], span_bins[i+1]
    in_bin = (span_r >= lo) & (span_r < hi)
    if in_bin.sum() < 5: continue
    stl_x_min[i] = float(x_r[in_bin].min())
    stl_x_max[i] = float(x_r[in_bin].max())
```

### 3b. Interpolate outline LE/TE to same stations

```python
from scipy.interpolate import interp1d

# LE: span increasing
f_le = interp1d(le_span, le_x, kind="linear", bounds_error=False, fill_value=np.nan)
outline_le_x = f_le(bin_centers)

# TE: span decreasing (tip->root), sort by span first
te_sort = np.argsort(te_span)
f_te = interp1d(te_span[te_sort], te_x[te_sort], kind="linear", bounds_error=False, fill_value=np.nan)
outline_te_x = f_te(bin_centers)
```

### 3c. Compute errors

```python
valid = np.isfinite(stl_x_min) & np.isfinite(stl_x_max) & np.isfinite(outline_le_x) & np.isfinite(outline_te_x)
le_err = outline_le_x[valid] - stl_x_min[valid]
te_err = outline_te_x[valid] - stl_x_max[valid]
chord_err = (outline_te_x[valid] - outline_le_x[valid]) - (stl_x_max[valid] - stl_x_min[valid])

def stats(err):
    return {
        "mean_mm": float(np.mean(err) * 1000),
        "mae_mm": float(np.mean(np.abs(err)) * 1000),
        "rmse_mm": float(np.sqrt(np.mean(err**2)) * 1000),
        "max_abs_mm": float(np.max(np.abs(err)) * 1000),
    }
```

## Step 4: Regional breakdown

Split errors into three span regions:

| Region | Span range | Purpose |
|--------|-----------|---------|
| Nose | span < 0.05 m | Nose radius / leading edge detail |
| Inner | 0.05 ≤ span < 0.5 × b_half | Mid-wing |
| Outer | span ≥ 0.5 × b_half | Tip region |

Compute LE RMSE, TE RMSE, chord RMSE per region.

## Step 5: Pass/fail criteria

| Criterion | Threshold | Action |
|-----------|-----------|--------|
| `overall` from geometry_check | PASS | Continue; FAIL → stop |
| b_half error | < 5 mm | Span match OK |
| LE RMSE (overall) | < 10 mm | Outline LE matches STL |
| TE RMSE (overall) | < 10 mm | Outline TE matches STL |
| Nose LE RMSE | < 20 mm | Nose radius preserved |
| Outer TE RMSE | < 20 mm | Tip TE captured correctly |
| z_m sign | > 90% negative | Right-half convention OK |
| chord ≤ 0 at any station | 0 occurrences | Fatal — outline unusable |

If any criterion fails significantly (e.g., TE RMSE > 100 mm), the outline has a structural defect and needs to be re-exported from CAD.

## Step 6: Output files

Write to the output directory:
1. `outline_vs_stl_error.csv` — per-station errors (span, STL LE, outline LE, LE error, STL TE, outline TE, TE error, chords)
2. `outline_vs_stl_error_summary.json` — all error statistics + regional breakdowns
3. `outline_vs_stl_preview.png` — 6-panel figure (planform, nose zoom, LE comparison, TE comparison, LE error vs span, TE error vs span)

## Step 7: Diagnosis guide

Given the error patterns, diagnose the root cause:

| Error pattern | Likely cause | Fix |
|---------------|-------------|-----|
| TE RMSE ~1800 mm, TE has 2–3 points | CATIA exported only TE root + tip | Re-export with TE sampling along span |
| LE RMSE ~200 mm, LE has dense nose + 1 mid point | CATIA exported only nose detail + tip | Re-export with uniform LE sampling |
| LE RMSE ~10 mm, TE RMSE ~10 mm, b_half matches | Outline is valid | Ready for solver |
| z_m mostly positive | Sign convention reversed | Multiply z_m by -1 in CSV |
| Not closed | Missing closing point | Add duplicate of first point at end |
| Nose LE RMSE > 50 mm | Nose geometry differs between STL and CATIA projection | Check CAD model version |
