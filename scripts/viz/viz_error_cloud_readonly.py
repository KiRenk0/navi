"""Phase 2E-P5R — 3D Taw Error Cloud Visualization Prototype (READ-ONLY, CORRECTED).

Tier A: diagnostic 3D scatter of signed relative error (LF Taw vs Fluent Tw).

Taw field rules (P5R correction):
- TPG default: MUST use Taw_tpg_w from fields.npz.
  If Taw_tpg_w is missing or all-NaN, script FAILS immediately.
  T_r_lam_w / T_r_turb_w / w_tr are printed as diagnostic info only,
  NEVER used as TPG Taw substitute.

P5 original invalid results disclaimer:
  The P5 (~2026-07-09 first run) scatter and stats used a manually blended
  LF_Taw = w_tr * T_r_turb_w + (1-w_tr) * T_r_lam_w from the OLD fields.npz
  that lacked Taw_tpg_w. That result (+9.6% mean overprediction, 1717K LF Taw)
  is INVALID and does NOT represent the P4+ TPG default baseline.

Hard constraints:
- Does NOT modify src, specs, YAML, docs, model, formulas, Cp(T), pressure baseline.
- Does NOT enable DN, does NOT tune parameters.
- Does NOT touch holdout (ma8_a10_h50km).
- Does NOT declare validation complete.
- Uses KD-tree nearest-neighbor mapping for VIZ ONLY.
  Does NOT replace P2R2 canon; does NOT update P2R2 table.

Usage:
  python scripts/viz_error_cloud_readonly.py
  python scripts/viz_error_cloud_readonly.py --fluent_csv <path> --lf_npz <path> --out_dir <dir>
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import KDTree
from matplotlib.colors import TwoSlopeNorm, Normalize
from matplotlib import cm

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT = _THIS_DIR.parents[1]


def _default_fluent_csv() -> Path:
    return _PROJECT / "fluent_export/adiabatic_wall_csv/1197pa_226.509k_30km_5alpha_6ma.csv"


def _default_lf_npz() -> Path:
    return _PROJECT / "runs/htv2_p5_corrected_tpg/fields.npz"


def _default_out_dir() -> Path:
    return _PROJECT / "runs/htv2_p5_corrected_tpg/viz"


def _infer_case_id(lf_npz_path: Path) -> str:
    for i, part in enumerate(lf_npz_path.parts):
        if part == "runs" and i + 1 < len(lf_npz_path.parts):
            return lf_npz_path.parts[i + 1]
    return "unknown_case"


def _parse_fluent_csv(csv_path: Path) -> dict:
    """Read Fluent wall CSV, return structured data and column map."""
    with open(csv_path, "r", newline="") as fh:
        reader = csv.reader(fh)
        raw_header = next(reader)
        rows = list(reader)

    header = [h.strip() for h in raw_header]
    n_cols = len(header)
    n_rows = len(rows)

    col_map = {h: i for i, h in enumerate(header)}

    x_col = None
    y_col = None
    z_col = None
    tw_col = None
    for h in header:
        hl = h.lower().replace(" ", "").replace("_", "-").replace("\t", "")
        if "x-coordinate" in hl or hl == "x-coordinate":
            x_col = h
        elif "y-coordinate" in hl or hl == "y-coordinate":
            y_col = h
        elif "z-coordinate" in hl or hl == "z-coordinate":
            z_col = h
        elif "wall-temperature" in hl or hl == "wall-temperature":
            tw_col = h
        elif "temperature" in hl and tw_col is None:
            tw_col = h

    if x_col is None or y_col is None or z_col is None:
        raise RuntimeError(
            f"Cannot identify coordinate columns in {csv_path}. Header: {header}"
        )
    if tw_col is None:
        raise RuntimeError(
            f"Cannot identify wall-temperature column in {csv_path}. Header: {header}"
        )

    data = np.array([[float(v) for v in row] for row in rows], dtype=np.float64)
    assert data.shape[1] == n_cols
    assert data.shape[0] == n_rows

    return {
        "x": data[:, col_map[x_col]],
        "y": data[:, col_map[y_col]],
        "z": data[:, col_map[z_col]],
        "Tw": data[:, col_map[tw_col]],
        "header": header,
        "n_points": n_rows,
        "fluent_path": str(csv_path),
        "x_col": x_col,
        "y_col": y_col,
        "z_col": z_col,
        "tw_col": tw_col,
    }


def _inspect_lf_fields(npz_path: Path) -> dict:
    """Load fields.npz and require the official TPG Taw field."""
    data = np.load(npz_path)
    all_keys = list(data.keys())

    taw_like_keys = [k for k in all_keys if any(
        tag in k.lower() for tag in ["taw", "tw", "t_w", "t_aw"]
    )]

    taw_stats = {}
    for k in taw_like_keys:
        v = np.asarray(data[k], dtype=float)
        finite = np.isfinite(v)
        taw_stats[k] = {
            "shape": v.shape,
            "finite_count": int(np.sum(finite)),
            "total_count": int(v.size),
            "mean": float(np.mean(v[finite])) if np.any(finite) else None,
            "min": float(np.min(v[finite])) if np.any(finite) else None,
            "max": float(np.max(v[finite])) if np.any(finite) else None,
        }

    x_w_m = np.asarray(data["x_w_m"], dtype=float)
    span_w_m = np.asarray(data["span_w_m"], dtype=float)
    mask_w = np.asarray(data["mask_w"], dtype=float)

    if "Taw_tpg_w" not in all_keys:
        raise RuntimeError(
            f"TPG visualization requires 'Taw_tpg_w' in fields.npz, but it is missing. "
            f"Available keys: {all_keys}. Cannot proceed."
        )
    lf_taw_raw = np.asarray(data["Taw_tpg_w"], dtype=float)
    if not np.any(np.isfinite(lf_taw_raw)):
        raise RuntimeError(
            "TPG visualization requires 'Taw_tpg_w' to have finite values, "
            "but it is all-NaN. Cannot proceed."
        )
    taw_field_name = "Taw_tpg_w"
    taw_source = "Taw_tpg_w (Route A-TPG default, enthalpy-based Taw)"

    lf_valid = (
        np.isfinite(x_w_m)
        & np.isfinite(span_w_m)
        & np.isfinite(lf_taw_raw)
        & (mask_w > 0.5)
    )

    # Read recovery temps as diagnostic-only (never used as Taw)
    T_r_lam_w = None
    T_r_turb_w = None
    w_tr = None
    recovery_blend_warn = ""
    if "T_r_lam_w" in all_keys and "T_r_turb_w" in all_keys and "w_tr" in all_keys:
        T_r_lam_w = np.asarray(data["T_r_lam_w"], dtype=float)
        T_r_turb_w = np.asarray(data["T_r_turb_w"], dtype=float)
        w_tr = np.asarray(data["w_tr"], dtype=float)
        blend = w_tr * T_r_turb_w + (1.0 - w_tr) * T_r_lam_w
        blend_finite = lf_valid & np.isfinite(blend)
        blend_mean = float(np.mean(blend[blend_finite])) if np.any(blend_finite) else None
        recovery_blend_warn = (
            f"NOTE: T_r_lam/T_r_turb/w_tr recovery blend mean={blend_mean:.2f} K. "
            f"This is diagnostic-only; Taw field used is {taw_field_name}."
        )

    return {
        "all_keys": all_keys,
        "taw_like_keys": taw_like_keys,
        "taw_stats": taw_stats,
        "taw_field_name": taw_field_name,
        "taw_source": taw_source,
        "x_w_m": x_w_m,
        "span_w_m": span_w_m,
        "mask_w": mask_w,
        "LF_Taw": lf_taw_raw,
        "lf_valid": lf_valid,
        "n_total": int(x_w_m.size),
        "n_finite": int(np.sum(lf_valid)),
        "T_r_lam_w": T_r_lam_w,
        "T_r_turb_w": T_r_turb_w,
        "w_tr": w_tr,
        "recovery_blend_warn": recovery_blend_warn,
    }


def _nn_map(lf_x: np.ndarray, lf_span: np.ndarray, lf_valid: np.ndarray,
            fluent_x: np.ndarray, fluent_y: np.ndarray, kdtree_k: int = 1) -> dict:
    """Nearest-neighbor mapping from LF (x, span) to Fluent (x-coordinate, y-coordinate)."""
    vx = lf_x[lf_valid]
    vspan = lf_span[lf_valid]
    lf_coords = np.column_stack([vx, vspan])

    fluent_coords = np.column_stack([fluent_x, fluent_y])

    kd = KDTree(lf_coords)
    distances, indices = kd.query(fluent_coords, k=kdtree_k)

    return {
        "lf_indices": indices,
        "distances": distances,
        "n_mapped": int(len(fluent_x)),
        "median_distance": float(np.median(distances)),
        "p95_distance": float(np.percentile(distances, 95)),
    }


def _compute_errors(lf_taw: np.ndarray, lf_valid: np.ndarray,
                    lf_indices: np.ndarray, fluent_tw: np.ndarray) -> dict:
    """Compute signed and absolute relative errors."""
    v_lf_taw = lf_taw[lf_valid]
    mapped_lf_taw = v_lf_taw[lf_indices]

    signed_error = mapped_lf_taw - fluent_tw
    signed_rel_error = np.where(
        np.abs(fluent_tw) > 1e-9,
        signed_error / fluent_tw,
        0.0,
    )
    abs_rel_error = np.abs(signed_rel_error)

    finite_mask = np.isfinite(signed_rel_error)
    valid_count = int(np.sum(finite_mask))

    over_fraction = float(np.mean(signed_rel_error[finite_mask] > 0)) if valid_count > 0 else 0.0
    under_fraction = float(np.mean(signed_rel_error[finite_mask] < 0)) if valid_count > 0 else 0.0

    return {
        "signed_error": signed_error,
        "signed_rel_error": signed_rel_error,
        "abs_rel_error": abs_rel_error,
        "valid_mapped_count": valid_count,
        "mean_signed_rel_error": float(np.mean(signed_rel_error[finite_mask])) if valid_count > 0 else None,
        "p95_abs_rel_error": float(np.percentile(abs_rel_error[finite_mask], 95)) if valid_count > 0 else None,
        "over_fraction": over_fraction,
        "under_fraction": under_fraction,
        "finite_mask": finite_mask,
    }


def _plot_scatter(fluent: dict, lf_info: dict, errors: dict,
                  case_id: str, out_dir: Path,
                  color_limit: Optional[float] = None) -> Path:
    """Generate 3D scatter PNG."""
    fin = errors["finite_mask"]
    fx = fluent["x"][fin]
    fy = fluent["y"][fin]
    fz = fluent["z"][fin]
    c = errors["signed_rel_error"][fin]

    if color_limit is None:
        color_limit = max(float(np.percentile(np.abs(c), 98)) * 1.2, 0.02)

    fig = plt.figure(figsize=(14, 10))
    ax = fig.add_subplot(111, projection="3d")

    norm = TwoSlopeNorm(vmin=-color_limit, vcenter=0.0, vmax=color_limit)
    sc = ax.scatter(fx, fy, fz, c=c, cmap="RdBu_r", norm=norm, s=4, alpha=0.7,
                    edgecolors="none", rasterized=True)

    cbar = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.10)
    cbar.set_label("Signed Relative Error (LF_Taw - Fluent_Tw)/Fluent_Tw", fontsize=10)

    ax.set_xlabel("x-coordinate (streamwise) [m]", fontsize=10)
    ax.set_ylabel("y-coordinate (spanwise) [m]", fontsize=10)
    ax.set_zlabel("z-coordinate (vertical) [m]", fontsize=10)

    taw_fn = lf_info.get("taw_field_name", "?")
    title_lines = [
        f"Taw Error Diagnostic Scatter  (P5R corrected)",
        f"case_id={case_id} | thermo_model=TPG | Taw field={taw_fn}",
        f"diagnostic scatter | NOT validation complete",
        f"color = signed_rel_error, clim=[{-color_limit:.4f}, {color_limit:.4f}]",
    ]
    ax.set_title("\n".join(title_lines), fontsize=11, fontfamily="monospace")

    ax.view_init(elev=25, azim=-60)
    ax.set_box_aspect([1.0, 0.5, 0.3])

    out_dir.mkdir(parents=True, exist_ok=True)
    safe_case = case_id.replace("/", "_").replace("\\", "_")
    out_path = out_dir / f"diag_scatter_{safe_case}_tpg_signed_rel_error.png"
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    return out_path


def _write_stats_json(errors: dict, mapping: dict, fluent: dict, lf_info: dict,
                      case_id: str, out_dir: Path,
                      color_limit: float, scatter_path: Path) -> Path:
    """Write error stats JSON."""
    suffix = "tpg"
    taw_fn = lf_info.get("taw_field_name", "?")
    taw_src = lf_info.get("taw_source", "?")

    stats = {
        "case_id": case_id,
        "thermo_model": "TPG",
        "taw_field_used": taw_fn,
        "taw_source": taw_src,
        "p5r_note": (
            "P5R CORRECTED RESULT. The original P5 run (2026-07-09) used a manually "
            "blended LF_Taw = w_tr * T_r_turb_w + (1-w_tr) * T_r_lam_w from a "
            "fields.npz that lacked Taw_tpg_w. That result (mean +9.6%, LF_Taw ~1717K) "
            "is INVALID and does NOT represent the P4+ TPG default baseline. "
            f"This corrected result uses the proper {taw_fn} field."
        ),
        "status": "diagnostic visualization only — NOT validation complete",
        "mapping_note": "KD-tree nearest-neighbor in (x,span) space — visualization only, not P2R2 canon",
        "error_stats": {
            "mean_signed_rel_error": errors["mean_signed_rel_error"],
            "p95_abs_rel_error": errors["p95_abs_rel_error"],
            "over_fraction": errors["over_fraction"],
            "under_fraction": errors["under_fraction"],
            "valid_mapped_count": errors["valid_mapped_count"],
            "color_limit": color_limit,
        },
        "mapping_stats": {
            "lf_n_finite": lf_info["n_finite"],
            "fluent_n_points": fluent["n_points"],
            "n_mapped": mapping["n_mapped"],
            "median_distance_m": mapping["median_distance"],
            "p95_distance_m": mapping["p95_distance"],
        },
        "input_paths": {
            "fluent_csv": fluent["fluent_path"],
            "lf_npz": str(lf_info.get("npz_path", "")),
        },
        "outputs": {
            "scatter_png": str(scatter_path),
        },
        "coordinate_mapping": {
            "fluent_x_col": fluent["x_col"],
            "fluent_y_col": fluent["y_col"],
            "fluent_z_col": fluent["z_col"],
            "fluent_tw_col": fluent["tw_col"],
            "lf_x_field": "x_w_m",
            "lf_span_field": "span_w_m",
            "note": "LF x_w_m -> Fluent x-coordinate, LF span_w_m -> Fluent y-coordinate. Fluent z-coordinate is vertical/thickness, NOT spanwise.",
        },
        "taw_field_check": lf_info.get("taw_stats", {}),
    }

    safe_case = case_id.replace("/", "_").replace("\\", "_")
    out_path = out_dir / f"error_stats_{safe_case}_{suffix}.json"
    with open(out_path, "w") as fh:
        json.dump(stats, fh, indent=2, ensure_ascii=False)

    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 2E-P5: 3D Taw Error Cloud Visualization Prototype (read-only)"
    )
    parser.add_argument(
        "--fluent_csv",
        type=Path,
        default=None,
        help="Path to Fluent wall CSV (default: adiabatic_wall_csv/1197pa_226.509k_30km_5alpha_6ma.csv)",
    )
    parser.add_argument(
        "--lf_npz",
        type=Path,
        default=None,
        help="Path to LF fields.npz (default: runs/htv2_0629_ma6_a5_h30km/fields.npz)",
    )
    parser.add_argument(
        "--out_dir",
        type=Path,
        default=None,
        help="Output directory for viz artifacts (default: runs/<case>/viz)",
    )
    parser.add_argument(
        "--color_limit",
        type=float,
        default=0.10,
        help="Symmetric color limit for signed_rel_error (default: 0.10)",
    )
    args = parser.parse_args()

    fluent_csv = args.fluent_csv or _default_fluent_csv()
    lf_npz = args.lf_npz or _default_lf_npz()
    case_id = _infer_case_id(lf_npz)
    out_dir = args.out_dir or (_PROJECT / "runs" / case_id / "viz")

    if not fluent_csv.exists():
        print(f"ERROR: Fluent CSV not found: {fluent_csv}", file=sys.stderr)
        return 1
    if not lf_npz.exists():
        print(f"ERROR: LF fields.npz not found: {lf_npz}", file=sys.stderr)
        return 1

    print("=" * 70)
    print("Phase 2E-P5 — 3D Taw Error Cloud Visualization Prototype")
    print("=" * 70)
    print()

    # ---- step 1: load fluent ----
    print("[1/6] Loading Fluent wall CSV ...")
    fluent = _parse_fluent_csv(fluent_csv)
    print(f"  File: {fluent['fluent_path']}")
    print(f"  Points: {fluent['n_points']}")
    print(f"  x-col: '{fluent['x_col']}'  range [{np.min(fluent['x']):.4f}, {np.max(fluent['x']):.4f}]")
    print(f"  y-col: '{fluent['y_col']}'  range [{np.min(fluent['y']):.4f}, {np.max(fluent['y']):.4f}]")
    print(f"  z-col: '{fluent['z_col']}'  range [{np.min(fluent['z']):.4f}, {np.max(fluent['z']):.4f}]")
    print(f"  Tw-col: '{fluent['tw_col']}'  range [{np.min(fluent['Tw']):.2f}, {np.max(fluent['Tw']):.2f}] K")
    print()

    # ---- step 2: load and inspect LF fields ----
    print("[2/6] Loading LF fields.npz and inspecting Taw-like fields ...")
    lf_info = _inspect_lf_fields(lf_npz)
    lf_info["npz_path"] = str(lf_npz)
    print(f"  File: {lf_npz}")
    print(f"  All keys ({len(lf_info['all_keys'])}): {', '.join(lf_info['all_keys'][:20])}...")
    print()
    print(f"  Taw-like keys ({len(lf_info['taw_like_keys'])}):")
    for k in lf_info["taw_like_keys"]:
        s = lf_info["taw_stats"][k]
        if s['mean'] is not None:
            print(f"    {k}: shape={s['shape']}, finite={s['finite_count']}/{s['total_count']}, "
                  f"mean={s['mean']:.4f}, min={s['min']:.4f}, max={s['max']:.4f}")
        else:
            print(f"    {k}: shape={s['shape']}, finite={s['finite_count']}/{s['total_count']}, ALL NaN")
    print()
    print(f"  RESOLVED Taw field: {lf_info['taw_field_name']}")
    print(f"  Taw source: {lf_info['taw_source']}")
    print(f"  LF_Taw mean: {np.mean(lf_info['LF_Taw'][lf_info['lf_valid']]):.2f} K")
    print(f"  LF valid points (mask_w + finite): {lf_info['n_finite']}")
    print()

    # Print recovery temperatures as diagnostic-only
    if lf_info.get("T_r_lam_w") is not None:
        print(f"  [Diagnostic-only] T_r_lam_w: mean={np.mean(lf_info['T_r_lam_w'][lf_info['lf_valid']]):.2f} K")
    if lf_info.get("T_r_turb_w") is not None:
        print(f"  [Diagnostic-only] T_r_turb_w: mean={np.mean(lf_info['T_r_turb_w'][lf_info['lf_valid']]):.2f} K")
    if lf_info.get("w_tr") is not None:
        print(f"  [Diagnostic-only] w_tr: mean={np.mean(lf_info['w_tr'][lf_info['lf_valid']]):.4f}")
    if lf_info.get("recovery_blend_warn"):
        print(f"  {lf_info['recovery_blend_warn']}")
    print()

    if lf_info["n_finite"] == 0:
        print("ERROR: No valid LF points after mask_w + finite check.", file=sys.stderr)
        return 1

    # ---- step 3: coordinate convention ----
    print("[3/6] Coordinate convention confirmation ...")
    print(f"  Fluent x = '{fluent['x_col']}'  (streamwise / chordwise)")
    print(f"  Fluent span = '{fluent['y_col']}'  (spanwise)")
    print(f"  Fluent vert = '{fluent['z_col']}'  (vertical / thickness)")
    print(f"  LF x = 'x_w_m'  (streamwise / chordwise)")
    print(f"  LF span = 'span_w_m'  (spanwise)")
    print(f"  Mapping: LF (x_w_m, span_w_m) -> Fluent ('{fluent['x_col']}', '{fluent['y_col']}')")
    print(f"  Fluent z-coordinate used ONLY for 3D scatter z-axis (display), NOT for mapping.")
    print()

    # ---- step 4: nearest-neighbor mapping ----
    print("[4/6] KD-tree nearest-neighbor mapping ...")
    mapping = _nn_map(
        lf_x=lf_info["x_w_m"],
        lf_span=lf_info["span_w_m"],
        lf_valid=lf_info["lf_valid"],
        fluent_x=fluent["x"],
        fluent_y=fluent["y"],
    )
    print(f"  Mapped points: {mapping['n_mapped']}")
    print(f"  Median distance: {mapping['median_distance']:.6f} m")
    print(f"  P95 distance: {mapping['p95_distance']:.6f} m")
    print()

    # ---- step 5: compute errors ----
    print("[5/6] Computing error fields ...")
    errors = _compute_errors(
        lf_taw=lf_info["LF_Taw"],
        lf_valid=lf_info["lf_valid"],
        lf_indices=mapping["lf_indices"],
        fluent_tw=fluent["Tw"],
    )
    print(f"  Valid mapped count: {errors['valid_mapped_count']}")
    print(f"  Mean signed_rel_error: {errors['mean_signed_rel_error']:.6f}")
    print(f"  P95 abs_rel_error: {errors['p95_abs_rel_error']:.6f}")
    print(f"  Over fraction (LF > Fluent): {errors['over_fraction']:.4f}")
    print(f"  Under fraction (LF < Fluent): {errors['under_fraction']:.4f}")
    print()

    # ---- step 6: generate scatter ----
    print("[6/6] Generating 3D diagnostic scatter ...")
    scatter_path = _plot_scatter(
        fluent=fluent,
        lf_info=lf_info,
        errors=errors,
        case_id=case_id,
        out_dir=out_dir,
        color_limit=args.color_limit,
    )
    print(f"  Scatter PNG: {scatter_path}")

    # ---- stats JSON ----
    stats_path = _write_stats_json(
        errors=errors,
        mapping=mapping,
        fluent=fluent,
        lf_info=lf_info,
        case_id=case_id,
        out_dir=out_dir,
        color_limit=args.color_limit,
        scatter_path=scatter_path,
    )
    print(f"  Stats JSON: {stats_path}")

    print()
    print("=" * 70)
    print("DONE. P5R corrected Tier A diagnostic scatter complete.")
    print("Taw field used:", lf_info["taw_field_name"])
    print("NOTE: This is VIZ-ONLY mapping (KD-tree NN). Does NOT update P2R2 canon.")
    print("      Does NOT declare validation complete.")
    print("NOTE: P5 original result (blended T_r_lam/T_r_turb, ~1717K LF_Taw, +9.6%)")
    print("      is INVALID and does NOT represent P4+ TPG default baseline.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
