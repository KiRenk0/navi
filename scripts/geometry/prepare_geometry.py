#!/usr/bin/env python
"""Faceted3D geometry input checker — MVP v1.

Reads an STL (and optional outline CSV), runs a battery of structural and
geometric sanity checks, writes:
  - geometry_check.json
  - geometry_preview.png
  - prepare_geometry.log

Does NOT modify any existing source files or geometry inputs.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


class _NpEncoder(json.JSONEncoder):
    """Handle numpy scalars/arrays in json.dump."""
    def default(self, o):
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)


# ---------------------------------------------------------------------------
# Minimal ASCII STL parser (mirrors stl_surface.py logic but self-contained)
# ---------------------------------------------------------------------------


def _parse_vertex_line(line: str):
    line = line.strip()
    if not line.startswith("vertex"):
        return None
    parts = line.split()
    if len(parts) < 4:
        return None
    try:
        return float(parts[1]), float(parts[2]), float(parts[3])
    except Exception:
        return None


def _detect_ascii_stl(path: Path, sample_bytes: int = 8192) -> bool:
    """Heuristic: if the first sample_bytes contain 'solid' or 'vertex' as text, it's ASCII."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(sample_bytes)
        return "vertex" in head or "solid" in head
    except Exception:
        return False


def _parse_ascii_stl_vertices(path: Path):
    """Yield (x, y, z) for every vertex line in an ASCII STL."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            v = _parse_vertex_line(line)
            if v is not None:
                yield v


# ---------------------------------------------------------------------------
# Outline CSV loader
# ---------------------------------------------------------------------------


def _load_outline_csv(path: Path, span_col: str, span_sign: float):
    """Return (x_m, span_m, raw_dict, errors)."""
    errors: list[str] = []
    data = np.genfromtxt(path, delimiter=",", names=True, dtype=float, encoding="utf-8")
    if data is None or getattr(data, "dtype", None) is None or data.dtype.names is None:
        errors.append("CSV has no parseable header or is empty")
        return np.array([]), np.array([]), {}, errors

    names = [str(n) for n in data.dtype.names]
    if "x_m" not in names:
        errors.append(f"Missing required column 'x_m'; found: {sorted(names)}")
    if span_col not in names:
        errors.append(f"Missing span column '{span_col}'; found: {sorted(names)}")

    if errors:
        return np.array([]), np.array([]), {"columns": names}, errors

    x = np.asarray(data["x_m"], dtype=float).reshape(-1)
    s_raw = np.asarray(data[span_col], dtype=float).reshape(-1)
    span = s_raw * float(span_sign)

    ok = np.isfinite(x) & np.isfinite(span)
    x = x[ok]
    span = span[ok]

    return x, span, {"columns": names}, errors


# ---------------------------------------------------------------------------
# Geometry checks
# ---------------------------------------------------------------------------


@dataclass
class CheckReport:
    input: dict = field(default_factory=dict)
    stl_format: dict = field(default_factory=dict)
    unit: dict = field(default_factory=dict)
    bbox_m_full: dict = field(default_factory=dict)
    bbox_m_right_half: dict = field(default_factory=dict)
    triangles: dict = field(default_factory=dict)
    normals: dict = field(default_factory=dict)
    outline: dict = field(default_factory=dict)
    status: dict = field(default_factory=lambda: {"errors": [], "warnings": [], "overall": "PASS"})

    def add_error(self, msg: str):
        self.status["errors"].append(msg)
        self.status["overall"] = "FAIL"

    def add_warning(self, msg: str):
        self.status["warnings"].append(msg)
        if self.status["overall"] == "PASS":
            self.status["overall"] = "WARN"


def _run_checks(args: argparse.Namespace, log: logging.Logger) -> CheckReport:
    rpt = CheckReport()
    rpt.input = {
        "stl_path": str(args.stl),
        "outline_path": str(args.outline) if args.outline else None,
        "unit": args.unit,
        "span_sign": args.span_sign,
        "outline_span_col": args.outline_span_col,
        "expected_length_m": args.expected_length_m,
    }

    stl_path = Path(args.stl)
    if not stl_path.exists():
        rpt.add_error(f"STL file not found: {stl_path}")
        return rpt

    # --- STL format check ---
    is_ascii = _detect_ascii_stl(stl_path)
    file_size = stl_path.stat().st_size

    vertices_cad = list(_parse_ascii_stl_vertices(stl_path))
    n_tri_total = len(vertices_cad) // 3
    leftover = len(vertices_cad) % 3

    rpt.stl_format = {
        "is_ascii": is_ascii,
        "file_size_bytes": file_size,
        "has_vertex_token": len(vertices_cad) > 0,
        "total_vertices_parsed": len(vertices_cad),
        "leftover_vertices": leftover,
        "triangles_total": n_tri_total,
    }

    if not is_ascii:
        rpt.add_error("STL is NOT ASCII format — parser requires ASCII STL")
    if n_tri_total == 0:
        rpt.add_error("STL parsed 0 triangles")

    # --- Unit handling ---
    unit_str = str(args.unit).strip().lower()
    v_abs_max = 0.0
    for vx, vy, vz in vertices_cad:
        v_abs_max = max(v_abs_max, abs(vx), abs(vy), abs(vz))

    if unit_str == "m":
        scale = 1.0
        auto_detected = False
    elif unit_str == "mm":
        scale = 1e-3
        auto_detected = False
    else:  # auto
        auto_detected = True
        scale = 1e-3 if v_abs_max > 50.0 else 1.0

    rpt.unit = {
        "user_specified": args.unit,
        "effective_unit": "mm" if scale == 1e-3 else "m",
        "scale_factor": scale,
        "auto_detected": auto_detected,
        "v_abs_max_cad": v_abs_max,
    }

    # --- Convert to solver coords and build arrays ---
    n_tri = min(n_tri_total, len(vertices_cad) // 3)
    if n_tri == 0:
        rpt.bbox_m_full = {}
        rpt.bbox_m_right_half = {}
        rpt.triangles = {}
        rpt.normals = {}
        return rpt

    arr = np.array(vertices_cad[: n_tri * 3], dtype=float).reshape(-1, 3)  # (nt*3, 3)
    x_cad = arr[:, 0]
    y_cad = arr[:, 1]
    z_cad = arr[:, 2]

    x_sol = x_cad * scale
    span_sol = float(args.span_sign) * z_cad * scale
    up_sol = y_cad * scale

    # --- Full STL bbox (all triangles) ---
    x_min_f, x_max_f = float(np.min(x_sol)), float(np.max(x_sol))
    span_min_f, span_max_f = float(np.min(span_sol)), float(np.max(span_sol))
    up_min_f, up_max_f = float(np.min(up_sol)), float(np.max(up_sol))

    rpt.bbox_m_full = {
        "note": "Full STL bounding box in solver coordinates",
        "x_min": round(x_min_f, 6),
        "x_max": round(x_max_f, 6),
        "Lx": round(x_max_f - x_min_f, 6),
        "span_min": round(span_min_f, 6),
        "span_max": round(span_max_f, 6),
        "L_span": round(span_max_f - span_min_f, 6),
        "up_min": round(up_min_f, 6),
        "up_max": round(up_max_f, 6),
        "L_up": round(up_max_f - up_min_f, 6),
    }

    # Triangle-level data
    v0 = arr[0::3]
    v1 = arr[1::3]
    v2 = arr[2::3]

    # Solver-coord triangles
    v0_sol = np.stack([v0[:, 0] * scale, float(args.span_sign) * v0[:, 2] * scale, v0[:, 1] * scale], axis=1)
    v1_sol = np.stack([v1[:, 0] * scale, float(args.span_sign) * v1[:, 2] * scale, v1[:, 1] * scale], axis=1)
    v2_sol = np.stack([v2[:, 0] * scale, float(args.span_sign) * v2[:, 2] * scale, v2[:, 1] * scale], axis=1)

    # Degenerate triangles (near-zero area)
    e1 = v1_sol - v0_sol
    e2 = v2_sol - v0_sol
    cross = np.cross(e1, e2)
    areas = 0.5 * np.linalg.norm(cross, axis=1)

    n_degenerate = int(np.sum(areas < 1e-12))
    n_valid = n_tri - n_degenerate

    # Right-half mask: all 3 vertices have span >= -eps
    right_mask = (span_sol.reshape(-1, 3) >= -1e-9).all(axis=1)
    n_right = int(np.sum(right_mask))

    # Right-half bbox
    if n_right > 0:
        x_r = x_sol.reshape(-1, 3)[right_mask]
        span_r = span_sol.reshape(-1, 3)[right_mask]
        up_r = up_sol.reshape(-1, 3)[right_mask]
        # Flatten back to per-vertex then per-triangle stats
        x_r_flat = x_r.flatten()
        span_r_flat = span_r.flatten()
        up_r_flat = up_r.flatten()
        rpt.bbox_m_right_half = {
            "note": "Right-half bbox (solver uses span_solver = span_sign * z_cad * scale; right-half = span>=0)",
            "n_triangles": n_right,
            "x_min": round(float(np.min(x_r_flat)), 6),
            "x_max": round(float(np.max(x_r_flat)), 6),
            "Lx": round(float(np.max(x_r_flat) - np.min(x_r_flat)), 6),
            "span_min": round(float(np.min(span_r_flat)), 6),
            "span_max": round(float(np.max(span_r_flat)), 6),
            "L_span": round(float(np.max(span_r_flat) - np.min(span_r_flat)), 6),
            "up_min": round(float(np.min(up_r_flat)), 6),
            "up_max": round(float(np.max(up_r_flat)), 6),
            "L_up": round(float(np.max(up_r_flat) - np.min(up_r_flat)), 6),
        }
    else:
        rpt.bbox_m_right_half = {"note": "No right-half triangles found", "n_triangles": 0}

    # Normal computation (full STL)
    norms = np.linalg.norm(cross, axis=1, keepdims=True)
    norms_safe = np.where(norms < 1e-18, 1.0, norms)
    n_hat = cross / norms_safe  # (nt, 3)
    nz_hat = np.abs(n_hat[:, 2])

    n_skin = int(np.sum(nz_hat >= 0.45))
    skin_ratio = n_skin / n_tri if n_tri > 0 else 0.0

    # Right-half normals
    if n_right > 0:
        nz_hat_r = nz_hat[right_mask]
        n_skin_r = int(np.sum(nz_hat_r >= 0.45))
        skin_ratio_r = n_skin_r / n_right
    else:
        nz_hat_r = np.array([])
        n_skin_r = 0
        skin_ratio_r = 0.0

    # Triangle area stats (full)
    areas_sorted = np.sort(areas)
    area_median = float(np.median(areas)) if n_tri > 0 else 0.0
    area_mean = float(np.mean(areas)) if n_tri > 0 else 0.0
    area_p5 = float(areas_sorted[int(0.05 * n_tri)]) if n_tri > 0 else 0.0
    area_p95 = float(areas_sorted[min(int(0.95 * n_tri), n_tri - 1)]) if n_tri > 0 else 0.0

    rpt.triangles = {
        "full_total": n_tri,
        "full_degenerate_lt_1e12": n_degenerate,
        "full_valid": n_valid,
        "right_half_triangles": n_right,
        "right_half_valid": n_right - int(np.sum(areas[right_mask] < 1e-12)) if n_right > 0 else 0,
        "area_stats": {
            "median": area_median,
            "mean": area_mean,
            "p5": area_p5,
            "p95": area_p95,
            "min": float(areas_sorted[0]) if n_tri > 0 else 0.0,
            "max": float(areas_sorted[-1]) if n_tri > 0 else 0.0,
        },
    }

    rpt.normals = {
        "full": {
            "nz_hat_mean": round(float(np.mean(nz_hat)), 4),
            "nz_hat_median": round(float(np.median(nz_hat)), 4),
            "nz_hat_min": round(float(np.min(nz_hat)), 4),
            "nz_hat_max": round(float(np.max(nz_hat)), 4),
            "skin_ratio_nz_hat_gte_0.45": round(skin_ratio, 4),
            "skin_count": n_skin,
        },
        "right_half": {
            "nz_hat_mean": round(float(np.mean(nz_hat_r)), 4) if n_right > 0 else None,
            "nz_hat_median": round(float(np.median(nz_hat_r)), 4) if n_right > 0 else None,
            "skin_ratio_nz_hat_gte_0.45": round(skin_ratio_r, 4),
            "skin_count": n_skin_r,
        },
    }

    # --- Bbox checks (use full Lx) ---
    Lx = x_max_f - x_min_f
    expected = float(args.expected_length_m)
    if expected > 0 and n_tri > 0:
        deviation = abs(Lx - expected) / expected
        if deviation > 0.10:
            rpt.add_warning(
                f"Lx={Lx:.4f} m deviates {deviation*100:.1f}% from expected {expected} m"
            )
        if deviation > 0.50:
            rpt.add_error(
                f"Lx={Lx:.4f} m deviates {deviation*100:.1f}% from expected {expected} m (>50%)"
            )

    if span_max_f <= 0:
        rpt.add_error(f"span_max={span_max_f:.6f} <= 0; right-half geometry not found")

    if n_tri > 0 and n_right < 3:
        rpt.add_warning(f"Only {n_right} triangles in right half; very sparse")

    if skin_ratio < 0.10 and n_tri > 0:
        rpt.add_warning(
            f"Skin ratio nz_hat>=0.45 is only {skin_ratio:.2%}; may not have enough upper/lower surface"
        )

    # --- Outline CSV check ---
    outline_data: dict[str, Any] = {"provided": bool(args.outline), "auto_outline_not_implemented_in_mvp": True}
    if args.outline:
        ol_path = Path(args.outline)
        if not ol_path.exists():
            rpt.add_error(f"Outline CSV not found: {ol_path}")
        else:
            ox, os_, ol_meta, ol_errs = _load_outline_csv(ol_path, args.outline_span_col, args.span_sign)
            n_ol = int(ox.size)

            outline_data["file"] = str(ol_path)
            outline_data["columns"] = ol_meta.get("columns", [])
            outline_data["n_points"] = n_ol
            outline_data["parse_errors"] = ol_errs

            if ol_errs:
                for e in ol_errs:
                    rpt.add_error(f"Outline CSV: {e}")
            elif n_ol < 3:
                rpt.add_error(f"Outline CSV has only {n_ol} finite points (need >= 3)")
            else:
                ox_min, ox_max = float(np.min(ox)), float(np.max(ox))
                os_min, os_max = float(np.min(os_)), float(np.max(os_))
                b_half_ol = os_max

                # Check closure
                closed = (
                    abs(ox[0] - ox[-1]) < 0.01 * max(ox_max - ox_min, 1e-6)
                    and abs(os_[0] - os_[-1]) < 0.01 * max(os_max - os_min, 1e-6)
                )

                outline_data["x_range"] = [round(ox_min, 6), round(ox_max, 6)]
                outline_data["span_range"] = [round(os_min, 6), round(os_max, 6)]
                outline_data["b_half_from_outline"] = round(b_half_ol, 6)
                outline_data["appears_closed"] = closed

                # Consistency with STL: compare right-half span ranges.
                # STL may contain both halves (span_min<0, span_max>0);
                # outline is typically right-half only (span>=0).
                if n_tri > 0:
                    stl_right_max = max(span_max_f, 0.0) if span_max_f > 0 else 0.0
                    overlap = min(stl_right_max, os_max) - max(0.0, os_min)
                    denom = max(stl_right_max, os_max, 1e-6)
                    span_overlap_ratio = max(0.0, overlap) / denom
                    outline_data["stl_outline_span_overlap_ratio"] = round(span_overlap_ratio, 4)
                    if span_overlap_ratio < 0.5:
                        rpt.add_warning(
                            f"Outline span range and STL right-half span range overlap ratio is only {span_overlap_ratio:.2%}"
                        )

                if not closed:
                    rpt.add_warning("Outline polyline does not appear to be closed")

    rpt.outline = outline_data

    return rpt


# ---------------------------------------------------------------------------
# Preview figure
# ---------------------------------------------------------------------------


def _generate_preview(rpt: CheckReport, args: argparse.Namespace, log: logging.Logger):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        log.warning("matplotlib not available; skipping preview figure")
        return

    stl_path = Path(args.stl)
    if not stl_path.exists():
        return

    unit_str = str(args.unit).strip().lower()
    v_abs_max = rpt.unit.get("v_abs_max_cad", 0.0)
    scale = rpt.unit.get("scale_factor", 1.0)

    # Re-parse for plotting (lightweight)
    vertices_cad = list(_parse_ascii_stl_vertices(stl_path))
    n_tri = len(vertices_cad) // 3
    if n_tri == 0:
        return

    arr = np.array(vertices_cad[: n_tri * 3], dtype=float).reshape(-1, 3)
    v0 = arr[0::3]
    v1 = arr[1::3]
    v2 = arr[2::3]

    x_sol = arr[:, 0] * scale
    span_sol = float(args.span_sign) * arr[:, 2] * scale
    up_sol = arr[:, 1] * scale

    v0_sol = np.stack([v0[:, 0] * scale, float(args.span_sign) * v0[:, 2] * scale, v0[:, 1] * scale], axis=1)
    v1_sol = np.stack([v1[:, 0] * scale, float(args.span_sign) * v1[:, 2] * scale, v1[:, 1] * scale], axis=1)
    v2_sol = np.stack([v2[:, 0] * scale, float(args.span_sign) * v2[:, 2] * scale, v2[:, 1] * scale], axis=1)

    e1 = v1_sol - v0_sol
    e2 = v2_sol - v0_sol
    cross = np.cross(e1, e2)
    norms = np.linalg.norm(cross, axis=1, keepdims=True)
    norms_safe = np.where(norms < 1e-18, 1.0, norms)
    n_hat = cross / norms_safe
    nz_hat = np.abs(n_hat[:, 2])
    areas = 0.5 * np.linalg.norm(cross, axis=1)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # --- 1. Planform projection ---
    ax1 = axes[0, 0]
    # Scatter triangle centroids for density
    cx = (v0_sol[:, 0] + v1_sol[:, 0] + v2_sol[:, 0]) / 3.0
    cspan = (v0_sol[:, 1] + v1_sol[:, 1] + v2_sol[:, 1]) / 3.0
    sc = ax1.scatter(cx, cspan, c=nz_hat, s=4, cmap="viridis", alpha=0.6, edgecolors="none")
    plt.colorbar(sc, ax=ax1, label="|nz_hat|")

    # Overlay outline
    if args.outline and Path(args.outline).exists():
        ox, os_, _, ol_errs = _load_outline_csv(Path(args.outline), args.outline_span_col, args.span_sign)
        if not ol_errs and ox.size >= 3:
            ax1.plot(ox, os_, "r-o", markersize=2, linewidth=1.5, label="outline", alpha=0.8)
            ax1.legend()

    ax1.set_xlabel("x (m)")
    ax1.set_ylabel("span (m)")
    ax1.set_title("Planform (x vs span)")
    ax1.set_aspect("equal", adjustable="box")
    ax1.grid(True, alpha=0.3)

    # --- 2. Side view ---
    ax2 = axes[0, 1]
    cup = (v0_sol[:, 2] + v1_sol[:, 2] + v2_sol[:, 2]) / 3.0
    ax2.scatter(cx, cup, c=nz_hat, s=4, cmap="viridis", alpha=0.6, edgecolors="none")
    ax2.set_xlabel("x (m)")
    ax2.set_ylabel("up (m)")
    ax2.set_title("Side view (x vs up)")
    ax2.set_aspect("equal", adjustable="box")
    ax2.grid(True, alpha=0.3)

    # --- 3. nz_hat histogram ---
    ax3 = axes[1, 0]
    ax3.hist(nz_hat, bins=60, edgecolor="black", alpha=0.85)
    ax3.axvline(0.45, color="red", linestyle="--", linewidth=2, label="threshold 0.45")
    ax3.set_xlabel("|nz_hat|")
    ax3.set_ylabel("Count")
    ax3.set_title("Normal |nz_hat| distribution")
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # --- 4. Area distribution ---
    ax4 = axes[1, 1]
    # Use log scale for areas
    valid_areas = areas[areas > 0]
    if valid_areas.size > 0:
        log_areas = np.log10(valid_areas)
        ax4.hist(log_areas, bins=60, edgecolor="black", alpha=0.85)
        ax4.set_xlabel("log10(triangle area / m^2)")
    else:
        ax4.text(0.5, 0.5, "no valid areas", ha="center", va="center", transform=ax4.transAxes)
    ax4.set_ylabel("Count")
    ax4.set_title("Triangle area distribution (log10)")
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / "geometry_preview.png"
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    log.info("Preview saved: %s", png_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Faceted3D geometry input checker (MVP)")
    parser.add_argument("--stl", required=True, help="Path to ASCII STL file")
    parser.add_argument("--outline", default=None, help="Path to outline CSV (optional)")
    parser.add_argument("--unit", default="mm", choices=["auto", "mm", "m"], help="STL unit (default: mm)")
    parser.add_argument("--span-sign", type=float, default=-1.0, help="Span sign (default: -1.0)")
    parser.add_argument("--outline-span-col", default="z_m", help="Outline span column name (default: z_m)")
    parser.add_argument("--expected-length-m", type=float, default=3.6, help="Expected length in meters (default: 3.6)")
    parser.add_argument("--out-dir", default="prepare_geometry_out", help="Output directory (default: prepare_geometry_out)")
    parser.add_argument("--strict", "--no-strict", action=argparse.BooleanOptionalAction, default=True, dest="strict", help="Exit non-zero on ERROR (default: --strict)")

    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Logging setup
    log_path = out_dir / "prepare_geometry.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    log = logging.getLogger("prepare_geometry")

    log.info("Starting geometry check — STL=%s", args.stl)

    rpt = _run_checks(args, log)

    # Write JSON report
    json_path = out_dir / "geometry_check.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rpt.__dict__, f, indent=2, ensure_ascii=False, cls=_NpEncoder)
    log.info("JSON report saved: %s", json_path)

    # Generate preview
    _generate_preview(rpt, args, log)

    # Terminal summary
    print("\n" + "=" * 60)
    print("  GEOMETRY CHECK SUMMARY")
    print("=" * 60)
    print(f"  STL is ASCII:          {rpt.stl_format.get('is_ascii', 'N/A')}")
    tri = rpt.triangles
    print(f"  Triangles (full STL):  {tri.get('full_total', 0)}")
    print(f"  Degenerate (full):     {tri.get('full_degenerate_lt_1e12', 0)}")
    print(f"  Valid (full):          {tri.get('full_valid', 0)}")
    print(f"  Triangles (right-half):{tri.get('right_half_triangles', 0)}")
    print(f"  Valid (right-half):    {tri.get('right_half_valid', 0)}")

    bf = rpt.bbox_m_full
    print(f"\n  Full STL bbox (all triangles):")
    print(f"    x:     [{bf.get('x_min', 'N/A')}, {bf.get('x_max', 'N/A')}]  Lx={bf.get('Lx', 'N/A')} m")
    print(f"    span:  [{bf.get('span_min', 'N/A')}, {bf.get('span_max', 'N/A')}]  L_span={bf.get('L_span', 'N/A')} m  (full span range)")
    print(f"    up:    [{bf.get('up_min', 'N/A')}, {bf.get('up_max', 'N/A')}]  L_up={bf.get('L_up', 'N/A')} m")

    br = rpt.bbox_m_right_half
    if br.get("n_triangles", 0) > 0:
        print(f"\n  Right-half bbox (solver uses span_solver = span_sign * z_cad * scale; right-half = span>=0):")
        print(f"    x:     [{br.get('x_min', 'N/A')}, {br.get('x_max', 'N/A')}]  Lx={br.get('Lx', 'N/A')} m")
        print(f"    span:  [{br.get('span_min', 'N/A')}, {br.get('span_max', 'N/A')}]  L_span={br.get('L_span', 'N/A')} m  (right-half span range)")
        print(f"    up:    [{br.get('up_min', 'N/A')}, {br.get('up_max', 'N/A')}]  L_up={br.get('L_up', 'N/A')} m")
        print(f"    right-half triangles: {br.get('n_triangles', 0)}")
    else:
        print(f"\n  Right-half bbox:       {br.get('note', 'no right-half triangles')}")

    if args.outline:
        ol = rpt.outline
        print(f"\n  Outline provided:      Yes")
        print(f"  Outline points:        {ol.get('n_points', 0)}")
        print(f"  b_half from outline:   {ol.get('b_half_from_outline', 'N/A')} m")
        ol_errs = ol.get('parse_errors', [])
        print(f"  Outline parse errors:  {len(ol_errs)}")
    else:
        print(f"\n  Outline provided:      No")

    nf = rpt.normals.get("full", {})
    nr = rpt.normals.get("right_half", {})
    print(f"\n  Skin ratio full (|nz|>=0.45):   {nf.get('skin_ratio_nz_hat_gte_0.45', 'N/A')}")
    print(f"  Skin ratio right-half (|nz|>=0.45): {nr.get('skin_ratio_nz_hat_gte_0.45', 'N/A')}")

    print(f"\n  Warnings:              {len(rpt.status['warnings'])}")
    print(f"  Errors:                {len(rpt.status['errors'])}")
    print(f"  Overall:               {rpt.status['overall']}")
    print(f"\n  Output files:")
    print(f"    {json_path}")
    print(f"    {out_dir / 'geometry_preview.png'}")
    print(f"    {log_path}")
    print("=" * 60 + "\n")

    if rpt.status["errors"]:
        for e in rpt.status["errors"]:
            log.error("ERROR: %s", e)
    if rpt.status["warnings"]:
        for w in rpt.status["warnings"]:
            log.warning("WARNING: %s", w)

    if args.strict and rpt.status["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
