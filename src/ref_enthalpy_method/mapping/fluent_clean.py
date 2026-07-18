"""Geometry-only Fluent clean leeward mask contract."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

import numpy as np

from ref_enthalpy_method.geometry.local_incidence import (
    NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER,
    NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION,
    SURFACE_CLASS_LEEWARD,
)
from ref_enthalpy_method.geometry.projected_semantics import (
    GEOMETRIC_SHEET_LOWER,
    GEOMETRIC_SHEET_UPPER,
)
from ref_enthalpy_method.mapping.fluent_semantics import (
    FluentProjectedSemanticsIntegration,
    semantic_valid_mask,
)


@dataclass(frozen=True)
class FluentCleanLeewardMasks:
    projection_gate_valid: np.ndarray
    semantic_valid: np.ndarray
    planform_domain_valid: np.ndarray
    clean_eligible: np.ndarray
    clean_leeward_upper: np.ndarray
    clean_leeward_lower: np.ndarray
    clean_leeward_any: np.ndarray

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if (
                value.dtype != np.dtype(np.bool_)
                or value.ndim != 1
                or not value.flags.owndata
                or not value.flags.c_contiguous
                or value.flags.writeable
            ):
                raise ValueError(f"{item.name} violates the immutable owned boolean mask contract")


def _require_array(
    value: np.ndarray,
    *,
    name: str,
    dtype: np.dtype | type,
    shape: tuple[int, ...],
) -> np.ndarray:
    array = np.asarray(value)
    expected_dtype = np.dtype(dtype)
    if array.dtype != expected_dtype:
        raise ValueError(f"{name} must have dtype {expected_dtype}, got {array.dtype}")
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    if not array.flags.c_contiguous:
        raise ValueError(f"{name} must be C-contiguous")
    if array.flags.writeable:
        raise ValueError(f"{name} must be read-only")
    if not array.flags.owndata:
        raise ValueError(f"{name} must own its data")
    return array


def _readonly_mask(value: np.ndarray) -> np.ndarray:
    result = np.array(value, dtype=np.bool_, copy=True, order="C")
    result.setflags(write=False)
    return result


def build_fluent_clean_leeward_masks(
    integration: FluentProjectedSemanticsIntegration,
) -> FluentCleanLeewardMasks:
    """Derive clean masks without q-chain acceptance, edge, or physical-result filters."""

    semantics = integration.semantics
    gate_raw = np.asarray(integration.projection.projection_gate_pass)
    if gate_raw.ndim != 1:
        raise ValueError(f"projection_gate_pass must have shape (N,), got {gate_raw.shape}")
    count = gate_raw.shape[0]
    gate = _require_array(
        gate_raw,
        name="projection_gate_pass",
        dtype=np.bool_,
        shape=(count,),
    )
    x_over_c = _require_array(
        semantics.x_over_c, name="x_over_c", dtype=np.float64, shape=(count,)
    )
    y_over_b = _require_array(
        semantics.y_over_b, name="y_over_b", dtype=np.float64, shape=(count,)
    )
    planform_valid = _require_array(
        semantics.planform_parameterization_valid,
        name="planform_parameterization_valid",
        dtype=np.bool_,
        shape=(count,),
    )
    sheet = _require_array(
        semantics.geometric_sheet, name="geometric_sheet", dtype=np.int8, shape=(count,)
    )
    surface_class = _require_array(
        semantics.surface_class, name="surface_class", dtype=np.int8, shape=(count,)
    )
    _require_array(
        semantics.normal_source, name="normal_source", dtype=np.int8, shape=(count,)
    )
    _require_array(
        semantics.outward_normal,
        name="outward_normal",
        dtype=np.float64,
        shape=(count, 3),
    )
    _require_array(
        semantics.incidence_s, name="incidence_s", dtype=np.float64, shape=(count,)
    )

    semantic = np.asarray(semantic_valid_mask(semantics))
    if semantic.dtype != np.dtype(np.bool_) or semantic.shape != (count,):
        raise ValueError("semantic_valid_mask must return bool with shape (N,)")

    planform_domain = (
        planform_valid
        & np.isfinite(x_over_c)
        & np.isfinite(y_over_b)
        & (x_over_c >= 0.0)
        & (x_over_c <= 1.0)
        & (y_over_b >= 0.0)
        & (y_over_b <= 1.0)
    )
    eligible = gate & semantic & planform_domain
    upper = (
        eligible
        & (sheet == GEOMETRIC_SHEET_UPPER)
        & (surface_class == SURFACE_CLASS_LEEWARD)
    )
    lower = (
        eligible
        & (sheet == GEOMETRIC_SHEET_LOWER)
        & (surface_class == SURFACE_CLASS_LEEWARD)
    )
    any_sheet = upper | lower
    if np.any(upper & lower) or not np.array_equal(any_sheet, upper | lower):
        raise ValueError("clean sheet masks violate disjoint-union invariants")

    return FluentCleanLeewardMasks(
        projection_gate_valid=_readonly_mask(gate),
        semantic_valid=_readonly_mask(semantic),
        planform_domain_valid=_readonly_mask(planform_domain),
        clean_eligible=_readonly_mask(eligible),
        clean_leeward_upper=_readonly_mask(upper),
        clean_leeward_lower=_readonly_mask(lower),
        clean_leeward_any=_readonly_mask(any_sheet),
    )


def fluent_clean_qa(
    integration: FluentProjectedSemanticsIntegration,
    masks: FluentCleanLeewardMasks,
) -> dict[str, Any]:
    """Summarize only geometry and semantic clean-mask fields."""

    source = integration.semantics.normal_source
    upper = masks.clean_leeward_upper
    lower = masks.clean_leeward_lower
    return {
        "point_count": int(upper.size),
        "projection_gate_valid_count": int(np.count_nonzero(masks.projection_gate_valid)),
        "semantic_valid_count": int(np.count_nonzero(masks.semantic_valid)),
        "planform_domain_valid_count": int(np.count_nonzero(masks.planform_domain_valid)),
        "clean_eligible_count": int(np.count_nonzero(masks.clean_eligible)),
        "clean_upper_count": int(np.count_nonzero(upper)),
        "clean_lower_count": int(np.count_nonzero(lower)),
        "clean_any_count": int(np.count_nonzero(masks.clean_leeward_any)),
        "clean_upper_source_1_count": int(np.count_nonzero(upper & (source == NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER))),
        "clean_upper_source_2_count": int(np.count_nonzero(upper & (source == NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION))),
        "clean_lower_source_1_count": int(np.count_nonzero(lower & (source == NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER))),
        "clean_lower_source_2_count": int(np.count_nonzero(lower & (source == NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION))),
        "upper_lower_overlap_count": int(np.count_nonzero(upper & lower)),
    }
