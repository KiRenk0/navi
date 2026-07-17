"""Shared pure geometry predicate for q-chain STL skin acceptance."""

from __future__ import annotations

import numpy as np

from .local_incidence import outward_normal_from_slopes

QCHAIN_MAX_NORMAL_ANGLE_DEG = 20.0
QCHAIN_MIN_ABS_NZ = 0.45


def qchain_stl_acceptance(
    *,
    candidate_normal_out: np.ndarray,
    reference_normal_out: np.ndarray,
    max_normal_angle_deg: float = QCHAIN_MAX_NORMAL_ANGLE_DEG,
    min_abs_nz: float = QCHAIN_MIN_ABS_NZ,
) -> np.ndarray:
    """Return the formal closed-boundary STL skin acceptance mask."""

    candidate = np.asarray(candidate_normal_out, dtype=float)
    reference = np.asarray(reference_normal_out, dtype=float)
    if candidate.shape[-1:] != (3,) or reference.shape[-1:] != (3,):
        raise ValueError("candidate and reference normals must end with dimension 3")
    try:
        candidate, reference = np.broadcast_arrays(candidate, reference)
    except ValueError as error:
        raise ValueError("candidate and reference normals must be broadcast-compatible") from error
    if not np.isfinite(float(max_normal_angle_deg)) or not 0.0 <= float(max_normal_angle_deg) <= 180.0:
        raise ValueError("max_normal_angle_deg must be finite and within [0, 180]")
    if not np.isfinite(float(min_abs_nz)) or not 0.0 <= float(min_abs_nz) <= 1.0:
        raise ValueError("min_abs_nz must be finite and within [0, 1]")

    candidate_norm = np.linalg.norm(candidate, axis=-1)
    reference_norm = np.linalg.norm(reference, axis=-1)
    valid = (
        np.all(np.isfinite(candidate), axis=-1)
        & np.all(np.isfinite(reference), axis=-1)
        & (candidate_norm > 1e-12)
        & (reference_norm > 1e-12)
    )
    dot = np.divide(
        np.sum(candidate * reference, axis=-1),
        candidate_norm * reference_norm,
        out=np.full(candidate_norm.shape, np.nan),
        where=valid,
    )
    threshold = np.cos(np.deg2rad(float(max_normal_angle_deg)))
    return valid & (np.clip(dot, -1.0, 1.0) >= threshold) & (np.abs(candidate[..., 2] / candidate_norm) >= float(min_abs_nz))


def qchain_stl_acceptance_from_slopes(
    *,
    sx: np.ndarray,
    sy: np.ndarray,
    ref_sx: float,
    ref_sy: float,
    max_normal_angle_deg: float = QCHAIN_MAX_NORMAL_ANGLE_DEG,
    min_abs_nz: float = QCHAIN_MIN_ABS_NZ,
) -> np.ndarray:
    """Preserve the solver's graph-normal slope acceptance semantics."""

    sx_arr = np.asarray(sx, dtype=float)
    sy_arr = np.asarray(sy, dtype=float)
    if sx_arr.shape != sy_arr.shape:
        raise ValueError("sx and sy must have the same shape")
    candidate = outward_normal_from_slopes(sx=sx_arr, sy=sy_arr, sheet="upper")
    reference = outward_normal_from_slopes(
        sx=np.asarray(float(ref_sx)), sy=np.asarray(float(ref_sy)), sheet="upper"
    )
    return qchain_stl_acceptance(
        candidate_normal_out=candidate,
        reference_normal_out=reference,
        max_normal_angle_deg=max_normal_angle_deg,
        min_abs_nz=min_abs_nz,
    )