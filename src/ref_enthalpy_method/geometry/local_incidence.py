"""Pure local-incidence diagnostics for faceted upper/lower surface sheets."""

from __future__ import annotations

import numpy as np

INCIDENCE_EPSILON = 0.05

SURFACE_CLASS_LEEWARD = -1
SURFACE_CLASS_NEAR_TANGENT = 0
SURFACE_CLASS_WINDWARD = 1
SURFACE_CLASS_INVALID = -2

NORMAL_SOURCE_INVALID = 0
NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER = 1
NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION = 2
NORMAL_SOURCE_ANALYTIC_FALLBACK_NO_STL_COVERAGE = 3


def orient_outward_normal(*, normal: np.ndarray, sheet: str) -> np.ndarray:
    """Normalize and orient a raw normal using upper/lower sheet identity."""

    raw = np.asarray(normal, dtype=float)
    if raw.shape[-1:] != (3,):
        raise ValueError("normal must have a trailing dimension of length 3")
    target_sign = 1.0 if str(sheet).strip().lower() == "upper" else -1.0
    if str(sheet).strip().lower() not in {"upper", "lower"}:
        raise ValueError("sheet must be 'upper' or 'lower'")

    norm = np.linalg.norm(raw, axis=-1, keepdims=True)
    valid = np.all(np.isfinite(raw), axis=-1, keepdims=True) & np.isfinite(norm) & (norm > 1e-12)
    unit = np.divide(raw, norm, out=np.full_like(raw, np.nan), where=valid)
    flip = np.isfinite(unit[..., 2]) & (unit[..., 2] * target_sign < 0.0)
    unit = np.where(flip[..., None], -unit, unit)
    oriented = valid[..., 0] & np.isfinite(unit[..., 2]) & (unit[..., 2] * target_sign > 1e-12)
    return np.where(oriented[..., None], unit, np.nan)


def outward_normal_from_slopes(*, sx: np.ndarray, sy: np.ndarray, sheet: str) -> np.ndarray:
    """Build the sheet-oriented normal from the solver's sampled z(x,y) slopes."""

    sx_arr, sy_arr = np.broadcast_arrays(np.asarray(sx, dtype=float), np.asarray(sy, dtype=float))
    graph_normal = np.stack([-sx_arr, -sy_arr, np.ones_like(sx_arr)], axis=-1)
    return orient_outward_normal(normal=graph_normal, sheet=sheet)


def freestream_velocity_direction(*, alpha_deg: float) -> np.ndarray:
    """Return actual gas velocity direction in body axes: x nose-to-tail, y span, z up."""

    alpha = float(np.deg2rad(float(alpha_deg)))
    return np.array([np.cos(alpha), 0.0, np.sin(alpha)], dtype=float)


def classify_incidence(*, normal_out: np.ndarray, alpha_deg: float, epsilon: float = INCIDENCE_EPSILON) -> tuple[np.ndarray, np.ndarray]:
    """Compute s=-dot(u_hat,n_out) and encode windward/near-tangent/leeward."""

    if not (float(epsilon) >= 0.0):
        raise ValueError("epsilon must be non-negative")
    normals = np.asarray(normal_out, dtype=float)
    if normals.shape[-1:] != (3,):
        raise ValueError("normal_out must have a trailing dimension of length 3")

    valid = np.all(np.isfinite(normals), axis=-1)
    s = -np.sum(normals * freestream_velocity_direction(alpha_deg=float(alpha_deg)), axis=-1)
    s = np.where(valid, s, np.nan)
    classes = np.full(s.shape, SURFACE_CLASS_INVALID, dtype=np.int8)
    classes[valid & (s > float(epsilon))] = SURFACE_CLASS_WINDWARD
    classes[valid & (s < -float(epsilon))] = SURFACE_CLASS_LEEWARD
    classes[valid & (np.abs(s) <= float(epsilon))] = SURFACE_CLASS_NEAR_TANGENT
    return s, classes


def diagnose_sheet_from_geometry(
    *,
    raw_facet_normal: np.ndarray,
    qchain_stl_accepted: np.ndarray,
    analytic_sx: np.ndarray,
    analytic_sy: np.ndarray,
    sheet: str,
    alpha_deg: float,
    epsilon: float = INCIDENCE_EPSILON,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Diagnose from raw STL geometry, using analytic slopes only where STL has no coverage."""

    raw = np.asarray(raw_facet_normal, dtype=float)
    accepted = np.asarray(qchain_stl_accepted, dtype=bool)
    analytic_normal = outward_normal_from_slopes(sx=analytic_sx, sy=analytic_sy, sheet=sheet)
    if raw.shape != analytic_normal.shape or accepted.shape != analytic_normal.shape[:-1]:
        raise ValueError("raw_facet_normal, qchain_stl_accepted, and analytic slopes must have matching shapes")

    facet_normal = orient_outward_normal(normal=raw, sheet=sheet)
    has_facet = np.all(np.isfinite(facet_normal), axis=-1)
    has_analytic = np.all(np.isfinite(analytic_normal), axis=-1)
    normal = np.where(has_facet[..., None], facet_normal, analytic_normal)

    source = np.full(has_facet.shape, NORMAL_SOURCE_INVALID, dtype=np.int8)
    source[has_facet & accepted] = NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER
    source[has_facet & ~accepted] = NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION
    source[~has_facet & has_analytic] = NORMAL_SOURCE_ANALYTIC_FALLBACK_NO_STL_COVERAGE

    incidence_s, surface_class = classify_incidence(normal_out=normal, alpha_deg=alpha_deg, epsilon=epsilon)
    return normal, incidence_s, surface_class, source


def diagnose_sheet(*, sx: np.ndarray, sy: np.ndarray, sheet: str, alpha_deg: float, epsilon: float = INCIDENCE_EPSILON) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return outward normals, incidence scalar, and classification for one sheet."""

    normal = outward_normal_from_slopes(sx=sx, sy=sy, sheet=sheet)
    incidence_s, surface_class = classify_incidence(normal_out=normal, alpha_deg=alpha_deg, epsilon=epsilon)
    return normal, incidence_s, surface_class