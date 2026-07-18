"""Geometry and semantics-only LF clean leeward mask contract."""

from __future__ import annotations

from dataclasses import dataclass, fields as dataclass_fields
from typing import Any, Mapping

import numpy as np

from ref_enthalpy_method.geometry.local_incidence import (
    NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER,
    NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION,
    SURFACE_CLASS_INVALID,
    SURFACE_CLASS_LEEWARD,
)

_FLOAT_FIELDS = (
    "x_w_m",
    "span_w_m",
    "x_l_m",
    "span_l_m",
    "xc_w",
    "yb_w",
    "xc_l",
    "yb_l",
    "normal_x_upper",
    "normal_y_upper",
    "normal_z_upper",
    "incidence_s_upper",
    "normal_x_lower",
    "normal_y_lower",
    "normal_z_lower",
    "incidence_s_lower",
)
_INT_FIELDS = (
    "surface_class_upper",
    "normal_source_upper",
    "surface_class_lower",
    "normal_source_lower",
)
_REQUIRED_FIELDS = _FLOAT_FIELDS + _INT_FIELDS


@dataclass(frozen=True)
class LfCleanLeewardMasks:
    planform_domain_valid: np.ndarray
    semantic_valid_upper: np.ndarray
    semantic_valid_lower: np.ndarray
    clean_eligible_upper: np.ndarray
    clean_eligible_lower: np.ndarray
    clean_leeward_upper: np.ndarray
    clean_leeward_lower: np.ndarray
    clean_leeward_any: np.ndarray

    def __post_init__(self) -> None:
        expected_shape: tuple[int, ...] | None = None
        for item in dataclass_fields(self):
            value = getattr(self, item.name)
            if not isinstance(value, np.ndarray):
                raise ValueError(f"{item.name} must be a numpy array")
            if (
                value.dtype != np.dtype(np.bool_)
                or value.ndim != 1
                or not value.flags.owndata
                or not value.flags.c_contiguous
                or value.flags.writeable
            ):
                raise ValueError(
                    f"{item.name} violates the immutable owned boolean mask contract"
                )
            if expected_shape is None:
                expected_shape = value.shape
            elif value.shape != expected_shape:
                raise ValueError("all LF clean masks must have identical shapes")
        if expected_shape is None or expected_shape[0] <= 0:
            raise ValueError("LF clean masks must contain at least one point")
        if np.any(self.clean_leeward_upper & self.clean_leeward_lower):
            raise ValueError("LF clean upper and lower masks must be disjoint")
        if not np.array_equal(
            self.clean_leeward_any,
            self.clean_leeward_upper | self.clean_leeward_lower,
        ):
            raise ValueError("LF clean any mask must be the exact upper/lower union")


def _require_fields(fields: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    missing = [name for name in _REQUIRED_FIELDS if name not in fields]
    if missing:
        raise ValueError(f"missing required LF clean fields: {missing}")

    arrays = {name: np.asarray(fields[name]) for name in _REQUIRED_FIELDS}
    first = arrays[_REQUIRED_FIELDS[0]]
    if first.ndim != 1 or first.size <= 0:
        raise ValueError("LF clean fields must be non-empty one-dimensional arrays")
    shape = first.shape

    for name in _FLOAT_FIELDS:
        value = arrays[name]
        if value.dtype != np.dtype(np.float64):
            raise ValueError(f"{name} must have dtype float64, got {value.dtype}")
        if value.ndim != 1 or value.shape != shape:
            raise ValueError(f"{name} must have shape {shape}, got {value.shape}")
    for name in _INT_FIELDS:
        value = arrays[name]
        if value.dtype != np.dtype(np.int8):
            raise ValueError(f"{name} must have dtype int8, got {value.dtype}")
        if value.ndim != 1 or value.shape != shape:
            raise ValueError(f"{name} must have shape {shape}, got {value.shape}")
    return arrays


def _require_canonical_identity(arrays: Mapping[str, np.ndarray]) -> None:
    pairs = (
        ("x_w_m", "x_l_m"),
        ("span_w_m", "span_l_m"),
        ("xc_w", "xc_l"),
        ("yb_w", "yb_l"),
    )
    for left, right in pairs:
        if not np.array_equal(arrays[left], arrays[right], equal_nan=True):
            raise ValueError(f"canonical coordinate identity failed: {left} != {right}")


def _readonly_mask(value: np.ndarray) -> np.ndarray:
    result = np.array(value, dtype=np.bool_, copy=True, order="C")
    result.setflags(write=False)
    return result


def _semantic_valid(
    arrays: Mapping[str, np.ndarray],
    *,
    sheet: str,
) -> np.ndarray:
    source = arrays[f"normal_source_{sheet}"]
    surface_class = arrays[f"surface_class_{sheet}"]
    return (
        (
            (source == NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER)
            | (
                source
                == NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION
            )
        )
        & np.isfinite(arrays[f"normal_x_{sheet}"])
        & np.isfinite(arrays[f"normal_y_{sheet}"])
        & np.isfinite(arrays[f"normal_z_{sheet}"])
        & np.isfinite(arrays[f"incidence_s_{sheet}"])
        & (surface_class != SURFACE_CLASS_INVALID)
    )


def build_lf_clean_leeward_masks(
    fields: Mapping[str, np.ndarray],
) -> LfCleanLeewardMasks:
    """Derive sheet-specific LF clean masks in canonical input order."""

    arrays = _require_fields(fields)
    _require_canonical_identity(arrays)

    planform = (
        np.isfinite(arrays["x_w_m"])
        & np.isfinite(arrays["span_w_m"])
        & np.isfinite(arrays["xc_w"])
        & np.isfinite(arrays["yb_w"])
        & (arrays["xc_w"] >= 0.0)
        & (arrays["xc_w"] <= 1.0)
        & (arrays["yb_w"] >= 0.0)
        & (arrays["yb_w"] <= 1.0)
    )
    semantic_upper = _semantic_valid(arrays, sheet="upper")
    semantic_lower = _semantic_valid(arrays, sheet="lower")
    eligible_upper = planform & semantic_upper
    eligible_lower = planform & semantic_lower
    clean_upper = eligible_upper & (
        arrays["surface_class_upper"] == SURFACE_CLASS_LEEWARD
    )
    clean_lower = eligible_lower & (
        arrays["surface_class_lower"] == SURFACE_CLASS_LEEWARD
    )
    clean_any = clean_upper | clean_lower

    if np.any(clean_upper & clean_lower):
        raise ValueError("LF clean upper and lower masks overlap")
    if not np.array_equal(clean_any, clean_upper | clean_lower):
        raise ValueError("LF clean any mask is not the exact upper/lower union")

    return LfCleanLeewardMasks(
        planform_domain_valid=_readonly_mask(planform),
        semantic_valid_upper=_readonly_mask(semantic_upper),
        semantic_valid_lower=_readonly_mask(semantic_lower),
        clean_eligible_upper=_readonly_mask(eligible_upper),
        clean_eligible_lower=_readonly_mask(eligible_lower),
        clean_leeward_upper=_readonly_mask(clean_upper),
        clean_leeward_lower=_readonly_mask(clean_lower),
        clean_leeward_any=_readonly_mask(clean_any),
    )


def lf_clean_qa(
    fields: Mapping[str, np.ndarray],
    masks: LfCleanLeewardMasks,
) -> dict[str, Any]:
    """Return deterministic geometry/semantics-only LF clean counts."""

    arrays = _require_fields(fields)
    _require_canonical_identity(arrays)
    point_count = arrays["x_w_m"].size
    if masks.planform_domain_valid.shape != (point_count,):
        raise ValueError("LF clean masks do not match input point count")

    upper_source = arrays["normal_source_upper"]
    lower_source = arrays["normal_source_lower"]
    raw_upper = arrays["surface_class_upper"] == SURFACE_CLASS_LEEWARD
    raw_lower = arrays["surface_class_lower"] == SURFACE_CLASS_LEEWARD
    clean_upper = masks.clean_leeward_upper
    clean_lower = masks.clean_leeward_lower
    overlap = clean_upper & clean_lower
    if np.any(overlap) or not np.array_equal(
        masks.clean_leeward_any, clean_upper | clean_lower
    ):
        raise ValueError("LF clean masks violate disjoint-union invariants")

    result: dict[str, Any] = {
        "point_count": int(point_count),
        "planform_domain_valid_count": int(
            np.count_nonzero(masks.planform_domain_valid)
        ),
        "semantic_valid_upper_count": int(
            np.count_nonzero(masks.semantic_valid_upper)
        ),
        "semantic_valid_lower_count": int(
            np.count_nonzero(masks.semantic_valid_lower)
        ),
        "clean_eligible_upper_count": int(
            np.count_nonzero(masks.clean_eligible_upper)
        ),
        "clean_eligible_lower_count": int(
            np.count_nonzero(masks.clean_eligible_lower)
        ),
        "raw_upper_leeward_count": int(np.count_nonzero(raw_upper)),
        "raw_lower_leeward_count": int(np.count_nonzero(raw_lower)),
        "clean_upper_count": int(np.count_nonzero(clean_upper)),
        "clean_lower_count": int(np.count_nonzero(clean_lower)),
        "clean_any_count": int(np.count_nonzero(masks.clean_leeward_any)),
        "upper_lower_overlap_count": int(np.count_nonzero(overlap)),
    }
    for sheet, source, raw, clean in (
        ("upper", upper_source, raw_upper, clean_upper),
        ("lower", lower_source, raw_lower, clean_lower),
    ):
        for source_id in (1, 2, 3):
            result[f"clean_{sheet}_source_{source_id}_count"] = int(
                np.count_nonzero(clean & (source == source_id))
            )
        for source_id in (0, 1, 2, 3):
            result[f"global_{sheet}_source_{source_id}_count"] = int(
                np.count_nonzero(source == source_id)
            )
        for source_id in (1, 2, 3):
            result[f"raw_{sheet}_source_{source_id}_count"] = int(
                np.count_nonzero(raw & (source == source_id))
            )
    if (
        result["clean_upper_source_3_count"] != 0
        or result["clean_lower_source_3_count"] != 0
    ):
        raise ValueError("normal source 3 must be excluded from LF clean masks")
    return result
