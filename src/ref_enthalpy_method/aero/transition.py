"""Boundary-layer transition criterion.

Implements eq. (2.46):
    (Re_tri)_e = 10^(5.37 + 0.2326 Ma_e - 0.004015 Ma_e^2)
"""

from __future__ import annotations

import math


def transition_reynolds(*, ma_e: float) -> float:
    mae = float(ma_e)
    expo = 5.37 + 0.2326 * mae - 0.004015 * (mae**2)
    return 10.0**expo


def _smoothstep(t: float) -> float:
    """Hermite smoothstep: 3t^2 - 2t^3, clamped to [0,1]."""
    t = max(0.0, min(t, 1.0))
    return float(t * t * (3.0 - 2.0 * t))


def transition_weight(
    *,
    enable: bool = True,
    re_measure: float,
    re_tri: float,
    weighting: str = "logistic",
    width_decades: float = 0.25,
    delta_decades: float = 0.5,
    x_over_c: float | None = None,
    transition_x_over_c: float | None = None,
    x_phys: float | None = None,
    x_tr_phys: float | None = None,
    lambda_m: float | None = None,
) -> float:
    """Return w in [0,1] (0=laminar, 1=turbulent).

    This is an engineering helper (baseline-compatible), not from the doc directly.
    - weighting="step": hard switch at Re >= Re_tri
    - weighting="logistic": smooth blend in log10(Re/Re_tri) over `width_decades`
    - weighting="smoothstep": onset-based Hermite over [Re_tri, Re_tri*10^delta_decades]
    - weighting="dhawan_narasimha": streamwise intermittency
        xi = (x_phys - x_tr_phys) / lambda_m
        gamma = 1 - exp(-0.412 * xi^2)       for x >= x_tr
        gamma = 0                              for x < x_tr
        Requires x_phys, x_tr_phys, lambda_m. Falls back to 0 if any missing/invalid.
    - if transition_x_over_c is provided, forbid transition before that x/c.
    """

    if not bool(enable):
        return 0.0

    re_tri = float(re_tri)
    if not math.isfinite(re_tri) or re_tri <= 0:
        return 0.0

    re_measure = float(re_measure)
    if not math.isfinite(re_measure) or re_measure <= 0:
        return 0.0

    if transition_x_over_c is not None and x_over_c is not None:
        try:
            if float(x_over_c) < float(transition_x_over_c):
                return 0.0
        except Exception:
            pass

    mode = str(weighting).strip().lower()
    if mode in {"step", "hard"}:
        return 1.0 if re_measure >= re_tri else 0.0

    if mode == "smoothstep":
        Re_start = re_tri
        Re_end = re_tri * (10.0 ** max(float(delta_decades), 1e-6))
        if re_measure <= Re_start:
            return 0.0
        if re_measure >= Re_end:
            return 1.0
        t = math.log10(re_measure / Re_start) / math.log10(Re_end / Re_start)
        return _smoothstep(t)

    # IMPORTANT: For doc reproduction we treat the criterion as a threshold:
    # if the measured Reynolds number does not reach Re_tri, keep fully-laminar.
    # The logistic blend is only used after crossing the threshold, to avoid
    # introducing a "pre-transition" turbulent contribution that can lift the
    # aft-chord temperatures even when Re < Re_tri everywhere.
    if re_measure < re_tri:
        return 0.0

    if mode == "dhawan_narasimha":
        if x_phys is None or x_tr_phys is None or lambda_m is None:
            return 0.0
        try:
            xp = float(x_phys)
            xtr = float(x_tr_phys)
            lm = float(lambda_m)
        except Exception:
            return 0.0
        if not (math.isfinite(xp) and math.isfinite(xtr) and math.isfinite(lm)):
            return 0.0
        if xtr <= 0.0 or lm <= 0.0:
            return 0.0
        if xp < xtr:
            return 0.0
        dx = xp - xtr
        xi = dx / lm
        exponent = -0.412 * (xi * xi)
        exponent = max(exponent, -60.0)
        return float(1.0 - math.exp(exponent))

    width = max(float(width_decades), 1e-6)
    z = math.log10(re_measure / re_tri) / width
    z = max(min(z, 60.0), -60.0)
    return float(1.0 / (1.0 + math.exp(-z)))

