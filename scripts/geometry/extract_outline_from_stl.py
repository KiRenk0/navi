#!/usr/bin/env python
"""
Extract right-half outline from STL x-span projection with nose refinement.

Strategy:
  1. Project all right-half STL vertices to (x, span) plane.
  2. Bin by span with nose-refined spacing.
  3. For each bin, take x_min as leading edge (absolute minimum x).
  4. Smooth the leading edge curve with a gentle moving average.
  5. Trailing edge uses x_max (absolute maximum x).
  6. Assemble closed polyline: LE root→tip, TE tip→root, close.

Output: new_spec/outline_xz_right_0628.csv (x_m, z_m columns, meters)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


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


def _parse_ascii_stl_vertices(path: Path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            v = _parse_vertex_line(line)
            if v is not None:
                yield v


def _smooth(x: np.ndarray, window: int = 5) -> np.ndarray:
    """Gentle moving average, preserving endpoints."""
    if len(x) < window + 2:
        return x.copy()
    kernel = np.ones(window) / window
    pad = window // 2
    # Reflect-pad to avoid edge effects
    padded = np.concatenate([x[:pad][::-1], x, x[-pad:][::-1]])
    smoothed = np.convolve(padded, kernel, mode="valid")
    # Trim back to original length
    extra = len(smoothed) - len(x)
    if extra > 0:
        smoothed = smoothed[extra // 2 : extra // 2 + len(x)]
    return smoothed


def extract_outline(
    stl_path: Path,
    span_sign: float = -1.0,
    scale: float = 1e-3,
    n_span_bins: int = 300,
    nose_span_limit: float = 0.05,
    nose_extra_bins: int = 100,
    le_percentile: float = 0.0,  # 0.0 = use absolute x_min (true LE)
    smooth_window: int = 7,
    min_points_per_bin: int = 5,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Extract right-half outline from STL x-span projection.

    Uses x_min for leading edge (absolute minimum x per span bin) and
    x_max for trailing edge.  When le_percentile > 0, uses that percentile
    instead of absolute min (useful for STLs with noisy leading-edge facets).

    Returns (x_m, z_m) for a closed outline polyline, and a metadata dict.
    z_m = -span_m (compatible with outline_xz_right.csv convention).
    """
    vertices = list(_parse_ascii_stl_vertices(stl_path))
    arr = np.array(vertices, dtype=float).reshape(-1, 3)
    n_tri = len(vertices) // 3
    if n_tri == 0:
        raise ValueError("No triangles parsed")

    # CAD coords -> solver coords
    x_sol = arr[:, 0] * scale
    span_sol = float(span_sign) * arr[:, 2] * scale

    # Right half only
    right = span_sol >= -1e-9
    x_r = x_sol[right]
    span_r = span_sol[right]

    if x_r.size == 0:
        raise ValueError("No right-half points found")

    span_max = float(np.max(span_r))

    # ---- Build span bins with nose refinement ----
    uniform_bins = np.linspace(0, span_max, n_span_bins + 1)

    nose_max = min(float(nose_span_limit), span_max * 0.15)
    if nose_max > 0:
        nose_bins = np.linspace(0, nose_max, nose_extra_bins + 1)
        # Only keep nose bins that are finer than the uniform spacing
        nose_bins = nose_bins[nose_bins < uniform_bins[1]]
        span_bins = np.unique(np.concatenate([nose_bins, uniform_bins]))
    else:
        span_bins = uniform_bins

    n_bins = len(span_bins) - 1

    # ---- Extract leading edge and trailing edge per bin ----
    le_span = []
    le_x = []
    te_span = []
    te_x = []
    n_skipped_bins = 0

    for i in range(n_bins):
        lo = span_bins[i]
        hi = span_bins[i + 1]
        in_bin = (span_r >= lo) & (span_r < hi)
        n_in = int(in_bin.sum())
        if n_in < min_points_per_bin:
            n_skipped_bins += 1
            continue
        x_in = x_r[in_bin]
        span_center = (lo + hi) / 2.0

        # Leading edge: use x_min (absolute minimum) when le_percentile==0,
        # otherwise use the specified percentile to reject side-face protrusions.
        if le_percentile <= 0.0:
            x_le = float(x_in.min())
        else:
            x_le = float(np.percentile(x_in, le_percentile))
        # Trailing edge: use x_max (absolute maximum) — the true TE is a
        # straight line at x≈3.6, and smoothing will reject outlier facets.
        x_te = float(x_in.max())

        le_span.append(span_center)
        le_x.append(x_le)
        te_span.append(span_center)
        te_x.append(x_te)

    le_span = np.array(le_span)
    le_x = np.array(le_x)
    te_span = np.array(te_span)
    te_x = np.array(te_x)

    # ---- Smooth leading edge ----
    le_x_smooth = _smooth(le_x, window=smooth_window)

    # ---- Enforce monotonicity on leading edge ----
    # x should increase (or stay same) as span increases
    for i in range(1, len(le_x_smooth)):
        if le_x_smooth[i] < le_x_smooth[i - 1]:
            le_x_smooth[i] = le_x_smooth[i - 1]

    # ---- Smooth trailing edge ----
    # For a straight wing, TE should be a straight line.  Use iterative
    # linear fitting (reject outliers beyond threshold) to get a robust
    # TE line.  The root rib (span≈0) has vertices covering the full chord
    # [0, 3.6] but NO wing TE vertices, so x_max in span<0.01 bins is
    # polluted by rib-face points (x≈0.003-0.35).  Internal structure
    # facets also pollute x_max at various span positions.
    te_span_arr = np.array(te_span)
    te_x_arr = np.array(te_x)

    def _iterative_te_fit(span, x, n_iter=20, threshold=0.3):
        """Iteratively fit TE line, rejecting outliers beyond threshold."""
        mask = np.ones(len(span), dtype=bool)
        for _ in range(n_iter):
            A = np.column_stack([span[mask], np.ones_like(span[mask])])
            coeffs, *_ = np.linalg.lstsq(A, x[mask], rcond=None)
            x_fit = np.column_stack([span, np.ones_like(span)]) @ coeffs
            residuals = np.abs(x - x_fit)
            new_mask = residuals <= threshold
            if new_mask.sum() == mask.sum():
                break
            mask = new_mask
            if mask.sum() < 10:
                break
        return coeffs, mask, x_fit

    coeffs_te, te_inlier_mask, te_x_fit = _iterative_te_fit(te_span_arr, te_x_arr)
    # Use fit where raw is an outlier, raw elsewhere
    te_x_clean = np.where(te_inlier_mask, te_x_arr, te_x_fit)
    te_x_smooth = _smooth(te_x_clean, window=smooth_window)

    # ---- Build closed outline polyline ----
    le_fwd_span = le_span.copy()
    le_fwd_x = le_x_smooth.copy()

    te_rev_span = te_span[::-1]
    te_rev_x = te_x_smooth[::-1]

    x_out = np.concatenate([le_fwd_x, te_rev_x, le_fwd_x[:1]])
    span_out = np.concatenate([le_fwd_span, te_rev_span, le_fwd_span[:1]])

    # Convert to outline CSV convention: z_m = -span_m
    z_out = -span_out

    meta = {
        "n_triangles": n_tri,
        "span_max_m": float(span_max),
        "n_span_bins": n_span_bins,
        "nose_extra_bins": nose_extra_bins,
        "nose_span_limit_m": float(nose_max),
        "n_outline_points": int(x_out.size),
        "le_points": int(le_span.size),
        "te_points": int(te_span.size),
        "n_skipped_bins": n_skipped_bins,
        "le_percentile": le_percentile,
        "smooth_window": smooth_window,
    }

    return x_out, z_out, meta, (le_span, le_x, le_x_smooth, te_span, te_x, te_x_smooth)


def _generate_preview(
    stl_path: Path,
    x_new: np.ndarray,
    z_new: np.ndarray,
    old_path: Path,
    le_span_raw: np.ndarray,
    le_x_raw: np.ndarray,
    le_x_smooth: np.ndarray,
    out_dir: Path,
):
    """Generate comparison preview with nose zoom."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available; skipping preview")
        return

    # Parse STL for scatter
    vertices = list(_parse_ascii_stl_vertices(stl_path))
    arr = np.array(vertices, dtype=float).reshape(-1, 3)
    scale = 1e-3
    x_sol = arr[:, 0] * scale
    span_sol = -1.0 * arr[:, 2] * scale
    right = span_sol >= -1e-9
    x_r = x_sol[right]
    span_r = span_sol[right]

    # Old outline
    old_data = np.genfromtxt(old_path, delimiter=",", names=True, dtype=float, encoding="utf-8")
    ox_old = old_data["x_m"]
    oz_old = old_data["z_m"]
    ospan_old = -oz_old

    # New outline span
    span_new = -z_new

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # ---- 1. Full planform ----
    ax1 = axes[0, 0]
    ax1.scatter(x_r[::3], span_r[::3], s=0.5, c="blue", alpha=0.3, label="STL points (1/3)")
    ax1.plot(ox_old, ospan_old, "r-", linewidth=1.5, label="old outline", alpha=0.8)
    ax1.plot(x_new, span_new, "g-", linewidth=1.5, label="new outline", alpha=0.8)
    ax1.set_xlabel("x (m)")
    ax1.set_ylabel("span (m)")
    ax1.set_title("Planform: STL + old outline + new outline")
    ax1.set_aspect("equal", adjustable="box")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)

    # ---- 2. Nose zoom ----
    ax2 = axes[0, 1]
    nose_mask = span_r < 0.10
    ax2.scatter(x_r[nose_mask], span_r[nose_mask], s=1.0, c="blue", alpha=0.4, label="STL points")
    # Old outline nose
    old_nose = ospan_old < 0.10
    ax2.plot(ox_old[old_nose], ospan_old[old_nose], "r-o", markersize=2, linewidth=1.5, label="old outline", alpha=0.8)
    # New outline nose
    new_nose = span_new < 0.10
    ax2.plot(x_new[new_nose], span_new[new_nose], "g-o", markersize=2, linewidth=1.5, label="new outline", alpha=0.8)
    ax2.set_xlabel("x (m)")
    ax2.set_ylabel("span (m)")
    ax2.set_title("Nose zoom (span<0.10 m)")
    ax2.set_aspect("equal", adjustable="box")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)

    # ---- 3. Leading edge comparison ----
    ax3 = axes[1, 0]
    ax3.plot(le_span_raw, le_x_raw, "b.", markersize=2, alpha=0.5, label="LE raw (percentile)")
    ax3.plot(le_span_raw, le_x_smooth, "g-", linewidth=1.5, label="LE smoothed")
    # Old outline LE (first half)
    mid = len(ox_old) // 2
    ax3.plot(ospan_old[:mid], ox_old[:mid], "r-", linewidth=1.5, label="old outline LE", alpha=0.8)
    ax3.set_xlabel("span (m)")
    ax3.set_ylabel("x (m)")
    ax3.set_title("Leading edge: raw vs smoothed vs old")
    ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.3)

    # ---- 4. Nose LE zoom ----
    ax4 = axes[1, 1]
    nose_le = le_span_raw < 0.05
    ax4.plot(le_span_raw[nose_le], le_x_raw[nose_le], "b.", markersize=4, alpha=0.6, label="LE raw")
    ax4.plot(le_span_raw[nose_le], le_x_smooth[nose_le], "g-o", markersize=3, linewidth=1.5, label="LE smoothed")
    old_nose_le = ospan_old[:mid] < 0.05
    ax4.plot(ospan_old[:mid][old_nose_le], ox_old[:mid][old_nose_le], "r-o", markersize=3, linewidth=1.5, label="old outline LE", alpha=0.8)
    ax4.set_xlabel("span (m)")
    ax4.set_ylabel("x (m)")
    ax4.set_title("Nose LE zoom (span<0.05 m)")
    ax4.legend(fontsize=8)
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    png_path = out_dir / "outline_comparison.png"
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    print(f"Preview saved: {png_path}")


def main():
    stl_path = Path("new_spec/htv2_0628.stl")
    old_outline_path = Path("new_spec/outline_xz_right.csv")
    out_dir = Path("prepare_geometry_out_htv2_0628")
    out_dir.mkdir(parents=True, exist_ok=True)

    if not stl_path.exists():
        print(f"STL not found: {stl_path}")
        sys.exit(1)

    print("=" * 60)
    print("  OUTLINE EXTRACTION FROM STL")
    print("=" * 60)
    print(f"  STL: {stl_path}")
    print()

    x_m, z_m, meta, (le_s, le_x, le_xs, te_s, te_x, te_xs) = extract_outline(
        stl_path,
        span_sign=-1.0,
        scale=1e-3,
        n_span_bins=300,
        nose_span_limit=0.05,
        nose_extra_bins=100,
        le_percentile=0.0,  # use absolute x_min for true LE
        smooth_window=5,    # smaller window to preserve nose shape
        min_points_per_bin=10,  # require more points per bin to reject sparse bins
    )

    print(f"  Triangles in STL:       {meta['n_triangles']}")
    print(f"  Span max:               {meta['span_max_m']:.6f} m")
    print(f"  Span bins (uniform):    {meta['n_span_bins']}")
    print(f"  Nose extra bins:        {meta['nose_extra_bins']}")
    print(f"  Nose span limit:        {meta['nose_span_limit_m']:.6f} m")
    print(f"  LE percentile:          {meta['le_percentile']}")
    print(f"  Smooth window:          {meta['smooth_window']}")
    print(f"  Skipped bins (low pts): {meta['n_skipped_bins']}")
    print(f"  Outline points:         {meta['n_outline_points']}")
    print(f"  LE points:              {meta['le_points']}")
    print(f"  TE points:              {meta['te_points']}")

    # Write CSV
    out_csv = Path("new_spec/outline_xz_right_0628.csv")
    header = "x_m,z_m"
    np.savetxt(
        out_csv,
        np.column_stack([x_m, z_m]),
        delimiter=",",
        header=header,
        comments="",
        fmt="%.10f",
    )
    print(f"\n  Written: {out_csv.resolve()}")

    # Validation
    span_check = -z_m
    print(f"\n--- Validation ---")
    print(f"  x range:     [{x_m.min():.10f}, {x_m.max():.6f}]")
    print(f"  span range:  [{span_check.min():.6f}, {span_check.max():.6f}]")
    print(f"  Closed:      first=({x_m[0]:.8f}, {z_m[0]:.8f}) last=({x_m[-1]:.8f}, {z_m[-1]:.8f})")

    # Nose region detail
    le_end = meta["le_points"]
    nose_le = span_check[:le_end] < 0.05
    if nose_le.sum() > 0:
        print(f"\n--- Nose region LE (span<0.05 m, {nose_le.sum()} points) ---")
        for i in np.where(nose_le)[0]:
            print(f"    span={span_check[i]:.10f}  x={x_m[i]:.10f}")

    # Compare with old outline
    if old_outline_path.exists():
        old = np.genfromtxt(old_outline_path, delimiter=",", names=True, dtype=float, encoding="utf-8")
        ox, oz = old["x_m"], old["z_m"]
        ospan = -oz
        print(f"\n--- Comparison with old outline ---")
        print(f"  Old outline points:     {len(ox)}")
        print(f"  Old span range:         [{ospan.min():.6f}, {ospan.max():.6f}]")
        print(f"  New span range:         [{span_check.min():.6f}, {span_check.max():.6f}]")
        print(f"  Span diff (old - new):  {ospan.max() - span_check.max():.6f} m")

        # Old outline point order (from debug):
        #   indices 0..tip_idx: root (span=0, x=0) -> tip (max span, x≈3.59)
        #     BUT first ~20 points are at span=0 with x increasing 0→0.32 (nose vertical line)
        #     then span starts increasing — this is the TRAILING EDGE side!
        #   indices tip_idx+1..end: tip -> root  [leading edge side]
        # So old outline goes: root→TE→tip→LE→root
        tip_idx = int(np.argmax(ospan))

        # Old outline LE: from tip back to root (indices tip_idx..end)
        old_le_span = ospan[tip_idx:]
        old_le_x = ox[tip_idx:]

        # New outline LE
        new_le_span = span_check[:le_end]
        new_le_x = x_m[:le_end]

        # Compare LE in overlapping span region
        from scipy.interpolate import interp1d
        f_old_le = interp1d(old_le_span, old_le_x, kind="linear", bounds_error=False, fill_value="extrapolate")
        old_le_at_new = f_old_le(new_le_span)
        valid = np.isfinite(old_le_at_new)
        if valid.sum() > 0:
            diff = new_le_x[valid] - old_le_at_new[valid]
            print(f"  LE comparison ({valid.sum()} points):")
            print(f"    mean diff (new - old): {np.mean(diff):.8f} m")
            print(f"    max |diff|:            {np.max(np.abs(diff)):.8f} m")
            print(f"    RMSE:                  {np.sqrt(np.mean(diff**2)):.8f} m")

            # Nose-specific (span<0.05)
            nose_valid = valid & (new_le_span < 0.05)
            if nose_valid.sum() > 0:
                diff_nose = new_le_x[nose_valid] - old_le_at_new[nose_valid]
                print(f"  Nose LE diff (span<0.05, {nose_valid.sum()} points):")
                print(f"    mean diff: {np.mean(diff_nose):.8f} m")
                print(f"    max |diff|: {np.max(np.abs(diff_nose)):.8f} m")

        # Print detailed comparison for first 10 points
        print(f"\n  Detailed LE comparison (first 15 points):")
        print(f"    {'span':>12s}  {'new_x':>12s}  {'old_x':>12s}  {'diff':>12s}")
        count = 0
        for i in range(len(new_le_span)):
            if count >= 15:
                break
            s = new_le_span[i]
            xn = new_le_x[i]
            xo = float(f_old_le(s)) if np.isfinite(f_old_le(s)) else float("nan")
            d = xn - xo if np.isfinite(xo) else float("nan")
            print(f"    {s:12.8f}  {xn:12.8f}  {xo:12.8f}  {d:12.8f}")
            count += 1

    # Generate preview
    print(f"\n--- Generating preview ---")
    _generate_preview(
        stl_path, x_m, z_m, old_outline_path,
        le_s, le_x, le_xs, out_dir,
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
