#!/usr/bin/env python3
"""Generate the geometry-only local-incidence alpha coverage scan.

Runs the formal CLI independently (temp dir, auto-cleaned) for ma6_a5_h30km,
then performs a pure-geometry alpha sweep using the diagnostic normal fields.
No longer reads from the deprecated runs/local_incidence_qa_raw_facet/.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run_case_rem.py"
VEHICLE = ROOT / "specs" / "vehicles" / "htv2_faceted3d_0629.yaml"
CASE = ROOT / "specs" / "cases" / "doc_ma6_alpha5_h30km_faceted3d.yaml"
SAMPLING = ROOT / "specs" / "sampling" / "engineering_full_wing_surface_grid_81x41.yaml"
OUTPUT = ROOT / "runs" / "local_incidence_alpha_scan"
ALPHAS = (3.0, 5.0, 8.0, 10.0)
EPSILONS = (0.03, 0.05, 0.08)
NX, NY = 81, 41
SWEEP_DEG = 72.0


# ── formal CLI runner ──────────────────────────────────────────────

def _run_formal(out: Path) -> None:
    cmd = [
        sys.executable, str(RUNNER),
        "--vehicle", str(VEHICLE), "--case", str(CASE),
        "--sampling", str(SAMPLING), "--run_dir", str(out),
        "--mach", "6", "--alpha", "5", "--h_m", "30000",
        "--transition_weighting", "step", "--no_plots",
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    for name in ("fields.npz", "summary.json"):
        if not (out / name).is_file():
            raise RuntimeError(f"formal runner did not produce {out / name}")


# ── analysis helpers ───────────────────────────────────────────────

def classify(s: np.ndarray, epsilon: float) -> np.ndarray:
    valid = np.isfinite(s)
    return np.where(s > epsilon, 1, np.where(s < -epsilon, -1, np.where(valid, 0, -2))).astype(np.int8)


def incidence(normals: np.ndarray, alpha_deg: float) -> np.ndarray:
    alpha = math.radians(alpha_deg)
    u = np.array([math.cos(alpha), 0.0, math.sin(alpha)])
    valid = np.all(np.isfinite(normals), axis=1)
    return np.where(valid, -np.sum(normals * u, axis=1), np.nan)


def point_weights(x: np.ndarray, y: np.ndarray, normals: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, dict[str, float | int]]:
    """Distribute valid quad area to corners using the local facet metric."""
    xg, yg = x.reshape(NY, NX), y.reshape(NY, NX)
    ng = normals.reshape(NY, NX, 3)
    vg = valid.reshape(NY, NX)
    weights = np.zeros((NY, NX), dtype=float)
    cell_count = 0
    rejected_cells = 0
    for j in range(NY - 1):
        for i in range(NX - 1):
            corners = ((j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i))
            if not all(vg[a, b] for a, b in corners):
                rejected_cells += 1
                continue
            p = np.array([[xg[a, b], yg[a, b]] for a, b in corners])
            edge_a = p[1] - p[0]
            edge_b = p[2] - p[0]
            edge_c = p[3] - p[0]
            cross_ab = edge_a[0] * edge_b[1] - edge_a[1] * edge_b[0]
            cross_bc = edge_b[0] * edge_c[1] - edge_b[1] * edge_c[0]
            projected = 0.5 * abs(cross_ab) + 0.5 * abs(cross_bc)
            nz = np.array([abs(ng[a, b, 2]) for a, b in corners])
            if not np.all(np.isfinite(nz)) or np.any(nz <= 1e-12):
                rejected_cells += 1
                continue
            area = float(projected * np.mean(1.0 / nz))
            if not np.isfinite(area) or area <= 0.0:
                rejected_cells += 1
                continue
            for a, b in corners:
                weights[a, b] += area / 4.0
            cell_count += 1
    return weights.ravel(), {
        "valid_cells": cell_count,
        "rejected_or_cross_outline_cells": rejected_cells,
        "surface_area_m2": float(np.sum(weights)),
    }


def components(mask: np.ndarray, weights: np.ndarray) -> list[dict[str, object]]:
    grid = mask.reshape(NY, NX)
    wg = weights.reshape(NY, NX)
    seen = np.zeros_like(grid, dtype=bool)
    result: list[dict[str, object]] = []
    for j, i in zip(*np.where(grid)):
        if seen[j, i]:
            continue
        queue = deque([(int(j), int(i))])
        seen[j, i] = True
        indices: list[int] = []
        while queue:
            yy, xx = queue.popleft()
            indices.append(yy * NX + xx)
            for y2, x2 in ((yy - 1, xx), (yy + 1, xx), (yy, xx - 1), (yy, xx + 1)):
                if 0 <= y2 < NY and 0 <= x2 < NX and grid[y2, x2] and not seen[y2, x2]:
                    seen[y2, x2] = True
                    queue.append((y2, x2))
        result.append({"indices": indices, "points": len(indices), "area_m2": float(np.sum(wg.ravel()[indices]))})
    return sorted(result, key=lambda item: (float(item["area_m2"]), int(item["points"])), reverse=True)


def fractions(mask_by_name: dict[str, np.ndarray], weights: np.ndarray) -> dict[str, float]:
    total = float(np.sum(weights))
    return {name: float(np.sum(weights[mask]) / total) if total else 0.0 for name, mask in mask_by_name.items()}


def region_stats(selected: np.ndarray, weights: np.ndarray, xc: np.ndarray, yb: np.ndarray, source: np.ndarray) -> dict[str, object]:
    comps = components(selected, weights)
    largest = comps[0] if comps else {"indices": [], "points": 0, "area_m2": 0.0}
    idx = np.asarray(largest["indices"], dtype=int)
    total_area = float(np.sum(weights[selected]))
    def subset(mask: np.ndarray) -> dict[str, float | int]:
        chosen = selected & mask
        return {"points": int(np.count_nonzero(chosen)), "area_m2": float(np.sum(weights[chosen]))}
    return {
        "points": int(np.count_nonzero(selected)),
        "area_m2": total_area,
        "connected_components_4_neighbor": len(comps),
        "largest_component_points": int(largest["points"]),
        "largest_component_area_m2": float(largest["area_m2"]),
        "largest_component_fraction_of_leeward_area": float(largest["area_m2"] / total_area) if total_area else 0.0,
        "largest_component_xc_range": [float(np.min(xc[idx])), float(np.max(xc[idx]))] if idx.size else None,
        "largest_component_yb_range": [float(np.min(yb[idx])), float(np.max(yb[idx]))] if idx.size else None,
        "nose": subset(xc <= 0.05),
        "trailing_edge": subset(xc >= 0.95),
        "tip": subset(yb >= 0.95),
        "analytic_fallback": subset(source == 3),
        "stl_rejected_but_used": subset(source == 2),
    }


def sheet_counts(cls: np.ndarray, source: np.ndarray) -> dict[str, object]:
    valid = cls != -2
    n = int(np.count_nonzero(valid))
    def entry(mask: np.ndarray) -> dict[str, float | int]:
        count = int(np.count_nonzero(mask))
        return {"points": count, "percent_of_valid": 100.0 * count / n if n else 0.0}
    return {
        "valid": n,
        "stl_accepted": entry(source == 1),
        "stl_rejected_but_used": entry(source == 2),
        "analytic_fallback": entry(source == 3),
        "windward": entry(cls == 1),
        "near_tangent": entry(cls == 0),
        "leeward": entry(cls == -1),
    }


def plot_alpha(alpha: float, xc: np.ndarray, yb: np.ndarray, s: np.ndarray, cls: np.ndarray, clean: np.ndarray, out_dir: Path) -> list[str]:
    files: list[str] = []
    specifications = (
        (s, "incidence_s", f"Upper incidence s, geometric alpha={alpha:g} deg", "coolwarm", None),
        (cls, "surface_class", f"Upper surface class, alpha={alpha:g} deg, epsilon=0.05", ListedColormap(["#3569a8", "#d6d6d6", "#b9473f"]), BoundaryNorm([-1.5, -0.5, 0.5, 1.5], 3)),
        (clean.astype(int), "clean_leeward_candidate", f"Upper clean leeward candidate, alpha={alpha:g} deg, epsilon=0.05", ListedColormap(["#d6d6d6", "#3569a8"]), BoundaryNorm([-0.5, 0.5, 1.5], 2)),
    )
    for values, suffix, title, cmap, norm in specifications:
        fig, ax = plt.subplots(figsize=(10, 4.8), constrained_layout=True)
        kwargs = {"c": values, "s": 17, "cmap": cmap, "rasterized": True}
        if norm is not None:
            kwargs["norm"] = norm
        image = ax.scatter(xc, yb, **kwargs)
        ax.set(xlabel="x/c", ylabel="y/b", title=title, xlim=(0, 1), ylim=(0, 1))
        ax.grid(alpha=0.2)
        fig.colorbar(image, ax=ax, label=suffix)
        destination = out_dir / f"alpha_{alpha:g}_{suffix}.png"
        fig.savefig(destination, dpi=180)
        plt.close(fig)
        files.append(str(destination.resolve()))
    return files


# ── main ───────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detailed-plots", action="store_true",
                        help="optional: generate per-alpha diagnostic PNGs (12 files) in addition to the default summary")
    args = parser.parse_args()

    OUTPUT.mkdir(parents=True, exist_ok=True)

    # ── run formal CLI independently ──
    with tempfile.TemporaryDirectory(prefix="li_alpha_scan_") as temp:
        work = Path(temp)
        _run_formal(work)
        with np.load(work / "fields.npz", allow_pickle=False) as fields:
            data = {name: np.asarray(fields[name]) for name in fields.files}

    sheets: dict[str, dict[str, np.ndarray]] = {}
    for sheet, suffix in (("upper", "l"), ("lower", "w")):
        normals = np.column_stack([data[f"normal_x_{sheet}"], data[f"normal_y_{sheet}"], data[f"normal_z_{sheet}"]])
        valid = np.all(np.isfinite(normals), axis=1)
        weights, area_meta = point_weights(data[f"x_{suffix}_m"], data[f"span_{suffix}_m"], normals, valid)
        sheets[sheet] = {"normals": normals, "source": data[f"normal_source_{sheet}"], "xc": data[f"xc_{suffix}"], "yb": data[f"yb_{suffix}"], "weights": weights}
        sheets[sheet]["area_meta"] = area_meta  # type: ignore[assignment]

    report: dict[str, object] = {
        "metadata": {
            "diagnostic_only": True,
            "formal_solver_routing_unchanged": True,
            "source": "independent formal CLI run ma6_a5_h30km (temp dir, auto-cleaned)",
            "alphas_deg": ALPHAS,
            "epsilons": EPSILONS,
            "classification": "s=-dot((cos(alpha),0,sin(alpha)),n_out); W:s>eps, L:s<-eps, NT:otherwise",
            "area_weighting": "structured projected (x,span) quad area times mean(1/abs(n_z)), distributed equally to four corners; separate real STL/analytic normals for upper and lower",
            "clean_mask": "upper leeward AND raw STL source in {accepted,rejected-but-used} AND x/c>0.05 AND x/c<0.95 AND y/b<0.95 AND abs(n_z)>=0.8",
            "region_bounds": {"nose_xc_max": 0.05, "trailing_edge_xc_min": 0.95, "tip_yb_min": 0.95, "chine_side_abs_nz_min": 0.8},
            "connectivity": "4-neighbor on 41x81 structured point grid",
            "effective_alpha_formula": "atan(tan(alpha)/cos(72deg))",
        },
        "sheet_geometry": {sheet: value["area_meta"] for sheet, value in sheets.items()},
        "alphas": {},
        "figures": [],
    }
    figure_files: list[str] = []
    for alpha in ALPHAS:
        alpha_e = math.degrees(math.atan(math.tan(math.radians(alpha)) / math.cos(math.radians(SWEEP_DEG))))
        alpha_result: dict[str, object] = {"geometric_alpha_deg": alpha, "alpha_e_deg": alpha_e, "difference_deg": alpha_e - alpha, "epsilons": {}, "alpha_e_classification_counts": {}}
        s_by_sheet = {sheet: incidence(value["normals"], alpha) for sheet, value in sheets.items()}
        se_by_sheet = {sheet: incidence(value["normals"], alpha_e) for sheet, value in sheets.items()}
        for epsilon in EPSILONS:
            eps_result: dict[str, object] = {}
            for sheet, values in sheets.items():
                cls = classify(s_by_sheet[sheet], epsilon)
                masks = {"windward": cls == 1, "near_tangent": cls == 0, "leeward": cls == -1}
                eps_result[sheet] = {
                    "counts": sheet_counts(cls, values["source"]),
                    "area_m2": {name: float(np.sum(values["weights"][mask])) for name, mask in masks.items()},
                    "area_fraction": fractions(masks, values["weights"]),
                }
                alpha_result["alpha_e_classification_counts"].setdefault(str(epsilon), {})[sheet] = sheet_counts(classify(se_by_sheet[sheet], epsilon), values["source"])
            upper = sheets["upper"]
            upper_cls = classify(s_by_sheet["upper"], epsilon)
            leeward = upper_cls == -1
            raw = np.isin(upper["source"], (1, 2))
            clean = leeward & raw & (upper["xc"] > 0.05) & (upper["xc"] < 0.95) & (upper["yb"] < 0.95) & (np.abs(upper["normals"][:, 2]) >= 0.8)
            eps_result["upper_leeward_connectivity"] = region_stats(leeward, upper["weights"], upper["xc"], upper["yb"], upper["source"])
            eps_result["clean_upper_leeward"] = region_stats(clean, upper["weights"], upper["xc"], upper["yb"], upper["source"])
            alpha_result["epsilons"][str(epsilon)] = eps_result
        report["alphas"][str(int(alpha))] = alpha_result
        if args.detailed_plots:
            cls05 = classify(s_by_sheet["upper"], 0.05)
            upper = sheets["upper"]
            clean05 = (cls05 == -1) & np.isin(upper["source"], (1, 2)) & (upper["xc"] > 0.05) & (upper["xc"] < 0.95) & (upper["yb"] < 0.95) & (np.abs(upper["normals"][:, 2]) >= 0.8)
            figure_files.extend(plot_alpha(alpha, upper["xc"], upper["yb"], s_by_sheet["upper"], cls05, clean05, OUTPUT))

    # ── summary PNG (always generated) ──
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for ax, metric, ylabel in ((axes[0, 0], "points", "Upper class points"), (axes[0, 1], "area_fraction", "Upper area fraction"), (axes[1, 0], "clean_points", "Clean leeward points"), (axes[1, 1], "clean_area", "Clean leeward area (m\u00b2)")):
        for epsilon in EPSILONS:
            values = []
            for alpha in ALPHAS:
                item = report["alphas"][str(int(alpha))]["epsilons"][str(epsilon)]
                if metric == "points": values.append(item["upper"]["counts"]["leeward"]["points"])
                elif metric == "area_fraction": values.append(item["upper"]["area_fraction"]["leeward"])
                elif metric == "clean_points": values.append(item["clean_upper_leeward"]["points"])
                else: values.append(item["clean_upper_leeward"]["area_m2"])
            ax.plot(ALPHAS, values, marker="o", label=f"epsilon={epsilon:.2f}")
        ax.set(xlabel="Geometric alpha (deg)", ylabel=ylabel)
        ax.grid(alpha=0.25)
        ax.legend()
    summary = OUTPUT / "epsilon_comparison_summary.png"
    fig.savefig(summary, dpi=180)
    plt.close(fig)
    figure_files.append(str(summary.resolve()))
    report["figures"] = figure_files

    destination = OUTPUT / "local_incidence_alpha_scan.json"
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())