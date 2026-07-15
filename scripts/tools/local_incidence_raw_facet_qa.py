#!/usr/bin/env python3
"""Generate raw-facet local-incidence QA statistics and review figures.

Runs the formal CLI independently (temp dir, auto-cleaned) to produce the
12 local-incidence diagnostic fields, then validates and reports.
No longer reads from the deprecated runs/local_incidence_qa_raw_facet/.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run_case_rem.py"
VEHICLE = ROOT / "specs" / "vehicles" / "htv2_faceted3d_0629.yaml"
CASE = ROOT / "specs" / "cases" / "doc_ma6_alpha5_h30km_faceted3d.yaml"
SAMPLING = ROOT / "specs" / "sampling" / "engineering_full_wing_surface_grid_81x41.yaml"
NX, NY = 81, 41
EPSILONS = (0.03, 0.05, 0.08)

# ── formal CLI runner ──────────────────────────────────────────────

CASES = {
    "ma6_a5_h30km": (6.0, 5.0, 30000.0),
    "ma8_a5_h40km": (8.0, 5.0, 40000.0),
}


def _run_formal(case_id: str, out: Path) -> None:
    mach, alpha, altitude = CASES[case_id]
    cmd = [
        sys.executable, str(RUNNER),
        "--vehicle", str(VEHICLE), "--case", str(CASE),
        "--sampling", str(SAMPLING), "--run_dir", str(out),
        "--mach", str(mach), "--alpha", str(alpha), "--h_m", str(altitude),
        "--transition_weighting", "step", "--no_plots",
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    for name in ("fields.npz", "summary.json"):
        if not (out / name).is_file():
            raise RuntimeError(f"formal runner did not produce {out / name}")


# ── analysis helpers ───────────────────────────────────────────────

def _counts(values: np.ndarray) -> dict[str, int]:
    return {
        "windward": int(np.count_nonzero(values == 1)),
        "near_tangent": int(np.count_nonzero(values == 0)),
        "leeward": int(np.count_nonzero(values == -1)),
        "invalid": int(np.count_nonzero(values == -2)),
    }


def _source_counts(source: np.ndarray) -> dict[str, int]:
    return {
        "stl_accepted": int(np.count_nonzero(source == 1)),
        "stl_rejected_but_used": int(np.count_nonzero(source == 2)),
        "analytic_fallback_no_stl": int(np.count_nonzero(source == 3)),
        "invalid": int(np.count_nonzero(source == 0)),
    }


def _components(mask: np.ndarray) -> list[int]:
    grid = np.asarray(mask, dtype=bool).reshape(NY, NX)
    seen = np.zeros_like(grid)
    sizes: list[int] = []
    for j, i in zip(*np.where(grid)):
        if seen[j, i]:
            continue
        queue = deque([(int(j), int(i))])
        seen[j, i] = True
        size = 0
        while queue:
            y, x = queue.popleft()
            size += 1
            for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= yy < NY and 0 <= xx < NX and grid[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True
                    queue.append((yy, xx))
        sizes.append(size)
    return sorted(sizes, reverse=True)


def _spatial(fields: np.lib.npyio.NpzFile, sheet: str, class_value: int) -> dict[str, object]:
    cls = np.asarray(fields[f"surface_class_{sheet}"], dtype=np.int8)
    source = np.asarray(fields[f"normal_source_{sheet}"], dtype=np.int8)
    xc = np.asarray(fields[f"xc_{'w' if sheet == 'lower' else 'l'}"], dtype=float)
    yb = np.asarray(fields[f"yb_{'w' if sheet == 'lower' else 'l'}"], dtype=float)
    selected = cls == class_value
    components = _components(selected)
    count = int(np.count_nonzero(selected))
    return {
        "count": count,
        "xc_range": [float(np.nanmin(xc[selected])), float(np.nanmax(xc[selected]))] if count else None,
        "yb_range": [float(np.nanmin(yb[selected])), float(np.nanmax(yb[selected]))] if count else None,
        "nose_xc_le_0p05": int(np.count_nonzero(selected & (xc <= 0.05))),
        "trailing_edge_xc_ge_0p95": int(np.count_nonzero(selected & (xc >= 0.95))),
        "tip_yb_ge_0p95": int(np.count_nonzero(selected & (yb >= 0.95))),
        "source_stl_accepted": int(np.count_nonzero(selected & (source == 1))),
        "source_stl_rejected_but_used": int(np.count_nonzero(selected & (source == 2))),
        "source_analytic_fallback_no_stl": int(np.count_nonzero(selected & (source == 3))),
        "connected_components_4_neighbor": len(components),
        "largest_component_points": components[0] if components else 0,
        "largest_component_fraction": float(components[0] / count) if components and count else 0.0,
        "top_component_sizes": components[:10],
    }


def _case_stats(path: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    with np.load(path, allow_pickle=False) as fields:
        for sheet in ("upper", "lower"):
            s = np.asarray(fields[f"incidence_s_{sheet}"], dtype=float)
            cls = np.asarray(fields[f"surface_class_{sheet}"], dtype=np.int8)
            source = np.asarray(fields[f"normal_source_{sheet}"], dtype=np.int8)
            valid = np.isfinite(s)
            sf = s[valid]
            nx = np.asarray(fields[f"normal_x_{sheet}"], dtype=float)
            ny = np.asarray(fields[f"normal_y_{sheet}"], dtype=float)
            nz = np.asarray(fields[f"normal_z_{sheet}"], dtype=float)
            normal_valid = np.isfinite(nx) & np.isfinite(ny) & np.isfinite(nz)
            norms = np.sqrt(nx[normal_valid] ** 2 + ny[normal_valid] ** 2 + nz[normal_valid] ** 2)
            result[sheet] = {
                "total_valid": int(np.count_nonzero(valid)),
                "source": _source_counts(source),
                "classification_epsilon_0p05": _counts(cls),
                "incidence_s": {
                    "min": float(np.min(sf)), "mean": float(np.mean(sf)), "median": float(np.median(sf)),
                    "p5": float(np.percentile(sf, 5)), "p95": float(np.percentile(sf, 95)), "max": float(np.max(sf)),
                },
                "epsilon_sensitivity": {
                    str(epsilon): _counts(np.where(s > epsilon, 1, np.where(s < -epsilon, -1, np.where(valid, 0, -2))))
                    for epsilon in EPSILONS
                },
                "normal_qa": {
                    "valid": int(np.count_nonzero(normal_valid)),
                    "max_abs_norm_error": float(np.max(np.abs(norms - 1.0))),
                    "orientation_ok": bool(np.all(nz[normal_valid] > 0.0) if sheet == "upper" else np.all(nz[normal_valid] < 0.0)),
                },
            }
        result["upper_leeward_spatial"] = _spatial(fields, "upper", -1)
        result["upper_near_tangent_spatial"] = _spatial(fields, "upper", 0)
    return result


def _transition_matrix(path_a: Path, path_b: Path) -> dict[str, int]:
    with np.load(path_a, allow_pickle=False) as new:
        rejected_with_facet = np.asarray(new["normal_source_upper"]) == 2
        after = np.asarray(new["surface_class_upper"])
        return {
            "before_fallback_w_total": int(np.count_nonzero(rejected_with_facet)),
            "after_windward": int(np.count_nonzero(rejected_with_facet & (after == 1))),
            "after_near_tangent": int(np.count_nonzero(rejected_with_facet & (after == 0))),
            "after_leeward": int(np.count_nonzero(rejected_with_facet & (after == -1))),
            "after_invalid": int(np.count_nonzero(rejected_with_facet & (after == -2))),
        }


def _plot(fields_path: Path, plots_dir: Path) -> list[str]:
    output_files: list[str] = []
    with np.load(fields_path, allow_pickle=False) as fields:
        xc = np.asarray(fields["xc_w"], dtype=float)
        yb = np.asarray(fields["yb_w"], dtype=float)
        for sheet in ("upper", "lower"):
            for field, title, cmap, limits in (
                (f"incidence_s_{sheet}", f"{sheet.title()} incidence s (raw-facet classification)", "coolwarm", None),
                (f"surface_class_{sheet}", f"{sheet.title()} local-incidence classification", "coolwarm", (-1.5, 1.5)),
                (f"normal_source_{sheet}", f"{sheet.title()} diagnostic normal source", "viridis", (-0.5, 3.5)),
            ):
                values = np.asarray(fields[field], dtype=float)
                valid = np.isfinite(values)
                fig, ax = plt.subplots(figsize=(10, 4.8), constrained_layout=True)
                kwargs = {"s": 16, "cmap": cmap, "rasterized": True}
                if limits is not None:
                    kwargs.update(vmin=limits[0], vmax=limits[1])
                plot = ax.scatter(xc[valid], yb[valid], c=values[valid], **kwargs)
                ax.set_xlabel("x/c")
                ax.set_ylabel("y/b")
                ax.set_title(title)
                ax.set_xlim(0.0, 1.0)
                ax.set_ylim(0.0, 1.0)
                ax.grid(alpha=0.2)
                colorbar = fig.colorbar(plot, ax=ax)
                colorbar.set_label(field)
                filename = plots_dir / f"raw_facet_{field}.png"
                fig.savefig(filename, dpi=180)
                plt.close(fig)
                output_files.append(str(filename.resolve()))
    return output_files


def _generate_output_json(report: dict[str, object], path: Path | None) -> None:
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if path is not None:
        path.write_text(text, encoding="utf-8")
    else:
        print(text)


# ── main ───────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plots", type=str, default=None, metavar="DIR",
                        help="optional: write 6 diagnostic PNGs to this directory (default: no plots)")
    parser.add_argument("--output-json", type=str, default=None, metavar="PATH",
                        help="optional: write report JSON to this path (default: stdout only)")
    args = parser.parse_args()

    plots_dir = Path(args.plots) if args.plots else None
    if plots_dir is not None:
        plots_dir.mkdir(parents=True, exist_ok=True)

    # ── run formal CLI independently for each case ──
    case_dirs: dict[str, Path] = {}
    with tempfile.TemporaryDirectory(prefix="li_raw_facet_qa_") as temp:
        for case_id in CASES:
            work = Path(temp) / case_id
            work.mkdir()
            _run_formal(case_id, work)
            case_dirs[case_id] = work

        # ── analyse ──
        report: dict[str, object] = {}
        for case_id in CASES:
            report[case_id] = _case_stats(case_dirs[case_id] / "fields.npz")

        report["classification_identical_between_cases"] = all(
            np.array_equal(
                np.load(case_dirs[CASES_LIST[0]] / "fields.npz", allow_pickle=False)[field],
                np.load(case_dirs[CASES_LIST[1]] / "fields.npz", allow_pickle=False)[field],
            )
            for field in ("incidence_s_upper", "incidence_s_lower", "surface_class_upper", "surface_class_lower", "normal_source_upper", "normal_source_lower")
        )
        report["original_fallback_w_transition"] = _transition_matrix(
            case_dirs[CASES_LIST[0]] / "fields.npz",
            case_dirs[CASES_LIST[1]] / "fields.npz",
        )
        if plots_dir is not None:
            report["figures"] = _plot(case_dirs[CASES_LIST[0]] / "fields.npz", plots_dir)
        else:
            report["figures"] = []

        _generate_output_json(report, Path(args.output_json) if args.output_json else None)

    return 0


CASES_LIST = list(CASES.keys())


if __name__ == "__main__":
    raise SystemExit(main())