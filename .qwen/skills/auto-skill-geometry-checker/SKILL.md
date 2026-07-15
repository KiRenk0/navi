---
name: geometry-checker
description: Procedure for creating and running the Faceted3D geometry input checker (prepare_geometry.py) MVP, plus running the full solver pipeline for a new STL model
source: auto-skill
extracted_at: '2026-06-28T01:30:00.000Z'
---

## Context

This project uses a Faceted3D solver that consumes ASCII STL surface meshes and optional outline CSV polylines. A `prepare_geometry.py` script was created as a read-only geometry checker to validate these inputs before running simulations.

## Key project paths (ASCII-only)

- Project root: `D:\ref\reference-enthalpy_03_12_26-main`
- **Never** use Chinese path `d:\参考焓\...` — it is unreachable on this machine.
- STL: `new_spec/prt0001_ascii.stl`
- Outline: `new_spec/outline_xz_right.csv`
- Vehicle spec: `specs/vehicles/htv2_faceted3d_creo_outline.yaml`
- Checker script: `scripts/geometry/prepare_geometry.py`

## Coordinate mapping (Creo -> solver)

| CAD axis | Solver axis | Notes |
|----------|-------------|-------|
| x_cad (nose→tail) | x | direct |
| y_cad (up) | z_up | direct |
| z_cad (centerline→LEFT wing) | span | `span = span_sign * z_cad`, span_sign = -1 |

STL is exported for the full model; solver uses right-half only (span >= 0).

## prepare_geometry.py design constraints

1. **No modification** of any existing source files or geometry inputs.
2. **Single new file**: `scripts/geometry/prepare_geometry.py`
3. **No** `--write-newspec`, no auto-YAML editing, no streamline tracing, no Zoby, no heat flux formula changes.
4. All outputs go to `--out-dir` (default: `prepare_geometry_out/`).

## Implementation notes

### JSON serialization
numpy types (`np.bool_`, `np.int64`, `np.float64`, `np.ndarray`) are **not** JSON serializable by default. Use a custom `json.JSONEncoder`:

```python
class _NpEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.floating): return float(o)
        if isinstance(o, np.bool_): return bool(o)
        if isinstance(o, np.ndarray): return o.tolist()
        return super().default(o)
```

### STL span overlap check
STL may contain both left and right halves (span_min < 0, span_max > 0), while outline CSV is right-half only (span >= 0). When computing overlap:

- Compare STL's **right-half max span** (`max(span_max, 0)`) against outline's span range.
- Do NOT compare full STL span range against right-half-only outline — this gives false low overlap.

### Command

```powershell
python scripts/geometry/prepare_geometry.py `
  --stl new_spec/prt0001_ascii.stl `
  --outline new_spec/outline_xz_right.csv `
  --unit mm `
  --span-sign -1 `
  --expected-length-m 3.6 `
  --out-dir prepare_geometry_out
```

### Output files

1. `geometry_check.json` — full check report
2. `geometry_preview.png` — 4-subplot figure (planform, side view, |nz_hat| histogram, area histogram)
3. `prepare_geometry.log` — timestamped log

## Known geometry stats (HTV2)

- STL triangles: 650 (2 degenerate, 648 valid)
- Lx = 3.6 m (matches expected)
- b_half from outline ≈ 1.106 m
- Skin ratio (|nz_hat| >= 0.45): 72%
- STL is ASCII, ~164 KB

## `--strict` / `--no-strict` parameter

**Do NOT use** `action="store_true"` with `default=True` — this makes `--no-strict` unable to override the default.

**Correct approach**: use `argparse.BooleanOptionalAction`:

```python
parser.add_argument(
    "--strict", "--no-strict",
    action=argparse.BooleanOptionalAction,
    default=True, dest="strict",
    help="Exit non-zero on ERROR (default: --strict)"
)
```

This gives:
- Default: `strict=True` (exit non-zero on errors)
- `--no-strict`: `strict=False` (exit 0 even with errors)
- `--strict`: explicit `strict=True`

## Full vs right-half bbox/triangle output

The JSON report already contains both `bbox_m_full` and `bbox_m_right_half`. The terminal summary should explicitly label:

- `full span range` — the full STL span extent (may include both left and right halves)
- `right-half span range` — only span >= 0 portion (what the solver actually uses)
- `right-half triangles` — triangle count in the right-half region

The right-half is defined by: `span_solver = span_sign * z_cad * scale`, with `span >= 0`.

## Running the full solver pipeline for a new STL

When the user provides a new STL model and wants heat flux / temperature results (not just geometry check):

1. **Create a new vehicle YAML** (do NOT modify existing ones):
   - Copy the existing faceted3d vehicle YAML (e.g. `specs/vehicles/htv2_faceted3d_creo_outline.yaml`)
   - Change only the `faceted3d.surface.stl` path to point to the new STL
   - Update `vehicle_id` to reflect the new model
   - Save as `specs/vehicles/htv2_faceted3d_<tag>.yaml`

2. **Run the geometry checker first** (optional but recommended):
   ```powershell
   python scripts/geometry/prepare_geometry.py `
     --stl new_spec/<new_stl>.stl `
     --outline new_spec/outline_xz_right.csv `
     --unit mm --span-sign -1 --expected-length-m 3.6 `
     --out-dir <out_dir>
   ```

3. **Run the solver**:
   ```powershell
   python scripts/run_case_rem.py `
     --vehicle specs/vehicles/htv2_faceted3d_<tag>.yaml `
     --case specs/cases/htv2_ma8p3_alpha2p2_h56p7km_isothermal300.yaml `
     --sampling specs/sampling/engineering_full_wing_surface_grid_81x41.yaml `
     --run_dir runs/<out_dir> `
     --mach 8.3 --alpha 2.2
   ```

4. **Output files** in `runs/<out_dir>/`:
   - `summary.json` — full result data
   - `fields.npz` — field arrays
   - `Tw_surface_windward.png` — windward temperature
   - `Tw_surface_leeward.png` — leeward temperature
   - `q_surface_windward.png` — windward heat flux
   - `q_surface_leeward.png` — leeward heat flux
   - `lf_warnings.log` — warning log

## ⚠️ YAML path resolution: relative paths are relative to the YAML file's directory

**Critical gotcha**: When a vehicle YAML contains relative paths (e.g., `outline_csv: "../../new_spec/outline_xz_right.csv"`), the solver resolves them **relative to the YAML file's directory**, NOT relative to the project root or the working directory.

For example, if the YAML is at `prepare_geometry_out_htv2_0629_check/htv2_faceted3d_0629_test.yaml`, then `../../new_spec/outline_xz_right_0629.csv` resolves to `D:\ref\new_spec\...` (two levels up from the YAML's directory), which may not exist.

**Fix**: Use **absolute paths** in the YAML when the YAML is in a non-standard location (not `specs/vehicles/`):

```yaml
planform:
  outline_csv: "D:/ref/reference-enthalpy_03_12_26-main/new_spec/outline_xz_right_0629.csv"
surface:
  stl: "D:/ref/reference-enthalpy_03_12_26-main/new_spec/htv2_0628.stl"
```

Use forward slashes (`/`) even on Windows — the solver handles them correctly.

**Safe alternative**: Place new vehicle YAMLs in `specs/vehicles/` so that relative paths like `../../new_spec/...` resolve correctly from that directory.

## `--no_plots` flag

The `run_case_rem.py` script accepts a `--no_plots` flag. When provided:
- The solver still runs and writes `summary.json` and `fields.npz`
- But **no PNG figures** are generated (no `q_surface_windward.png`, etc.)
- If the user wants to see heat flux plots, omit `--no_plots` (or re-run without it — the solver will overwrite the existing run directory)

## Outline vs spec b_half mismatch

The solver compares the outline's span extent against `planform.b_half_m` in the YAML. If they disagree by >5%, a warning is logged and the solver uses the outline's value for sampling. This is expected when the outline is the authoritative geometry source.
