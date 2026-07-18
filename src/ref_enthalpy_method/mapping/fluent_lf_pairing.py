"""Deterministic geometry-only Fluent-clean to LF-clean pairing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields as dataclass_fields
from typing import Literal

import numpy as np

from ref_enthalpy_method.mapping.fluent_clean import FluentCleanLeewardMasks
from ref_enthalpy_method.mapping.fluent_semantics import (
    FluentProjectedSemanticsIntegration,
)
from ref_enthalpy_method.mapping.lf_clean import LfCleanLeewardMasks

_METRIC = "projected_physical_x_span_euclidean_m"
_SHEETS = ("upper", "lower")


@dataclass(frozen=True)
class FluentLfCleanPairing:
    sheet: Literal["upper", "lower"]
    metric: str
    target_pool_size: int
    source_canonical_index: np.ndarray
    target_canonical_index: np.ndarray
    distance_m: np.ndarray
    dx_m: np.ndarray
    dspan_m: np.ndarray
    second_target_canonical_index: np.ndarray
    second_distance_m: np.ndarray
    ambiguity_margin_m: np.ndarray
    mutual_nearest: np.ndarray
    target_multiplicity: np.ndarray

    def __post_init__(self) -> None:
        if self.sheet not in _SHEETS:
            raise ValueError("sheet must be exactly 'upper' or 'lower'")
        if self.metric != _METRIC:
            raise ValueError(f"metric must be exactly {_METRIC!r}")
        if (
            isinstance(self.target_pool_size, (bool, np.bool_))
            or not isinstance(self.target_pool_size, (int, np.integer))
            or int(self.target_pool_size) < 0
        ):
            raise ValueError("target_pool_size must be a nonnegative integer")

        expected_dtype = {
            "source_canonical_index": np.dtype(np.int64),
            "target_canonical_index": np.dtype(np.int64),
            "distance_m": np.dtype(np.float64),
            "dx_m": np.dtype(np.float64),
            "dspan_m": np.dtype(np.float64),
            "second_target_canonical_index": np.dtype(np.int64),
            "second_distance_m": np.dtype(np.float64),
            "ambiguity_margin_m": np.dtype(np.float64),
            "mutual_nearest": np.dtype(np.bool_),
            "target_multiplicity": np.dtype(np.int64),
        }
        source_count: int | None = None
        for item in dataclass_fields(self):
            if item.name not in expected_dtype:
                continue
            value = getattr(self, item.name)
            if not isinstance(value, np.ndarray):
                raise ValueError(f"{item.name} must be a numpy array")
            if (
                value.dtype != expected_dtype[item.name]
                or value.ndim != 1
                or not value.flags.owndata
                or not value.flags.c_contiguous
                or value.flags.writeable
            ):
                raise ValueError(
                    f"{item.name} violates the immutable owned array contract"
                )
            if source_count is None:
                source_count = value.size
            elif value.shape != (source_count,):
                raise ValueError("all per-source pairing arrays must have identical shapes")

        assert source_count is not None
        if source_count > 1 and np.any(
            self.source_canonical_index[1:] <= self.source_canonical_index[:-1]
        ):
            raise ValueError("source_canonical_index must be strictly increasing")
        if np.any(self.source_canonical_index < 0):
            raise ValueError("source_canonical_index must be nonnegative")
        if np.any(self.target_canonical_index < 0):
            raise ValueError("target_canonical_index must be nonnegative")
        if not (
            np.all(np.isfinite(self.distance_m))
            and np.all(np.isfinite(self.dx_m))
            and np.all(np.isfinite(self.dspan_m))
        ):
            raise ValueError("primary pairing geometry must be finite")
        if np.any(self.distance_m < 0.0):
            raise ValueError("distance_m must be nonnegative")
        if source_count and np.any(self.target_multiplicity < 1):
            raise ValueError("target_multiplicity must be positive for every source")

        if self.target_pool_size == 1:
            if not (
                np.all(self.second_target_canonical_index == -1)
                and np.all(np.isposinf(self.second_distance_m))
                and np.all(np.isposinf(self.ambiguity_margin_m))
            ):
                raise ValueError("single-target second-nearest sentinels are invalid")
        elif self.target_pool_size >= 2:
            if (
                np.any(self.second_target_canonical_index < 0)
                or not np.all(np.isfinite(self.second_distance_m))
                or not np.all(np.isfinite(self.ambiguity_margin_m))
                or np.any(self.ambiguity_margin_m < 0.0)
            ):
                raise ValueError("second-nearest outputs are invalid")


def _readonly_copy(value: np.ndarray, *, dtype: np.dtype | type) -> np.ndarray:
    result = np.array(value, dtype=dtype, copy=True, order="C")
    result.setflags(write=False)
    return result


def _domain_size(value: int, *, name: str) -> int:
    if (
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (int, np.integer))
        or int(value) < 0
    ):
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(value)


def _canonical_index(
    value: np.ndarray,
    *,
    name: str,
    full_domain_size: int,
) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != 1:
        raise ValueError(f"{name} must have shape (N,), got {array.shape}")
    if np.issubdtype(array.dtype, np.bool_) or not np.issubdtype(
        array.dtype, np.integer
    ):
        raise ValueError(f"{name} must have an integer dtype")
    if array.size and (
        np.any(array < 0)
        or any(int(item) >= full_domain_size for item in array.flat)
    ):
        raise ValueError(f"{name} contains an index outside its full canonical domain")
    converted = np.array(array, dtype=np.int64, copy=True, order="C")
    if np.unique(converted).size != converted.size:
        raise ValueError(f"{name} must contain unique canonical identities")
    return converted


def _coordinates(
    value: np.ndarray,
    *,
    name: str,
    count: int,
) -> np.ndarray:
    array = np.asarray(value)
    if array.dtype != np.dtype(np.float64):
        raise ValueError(f"{name} must have dtype float64, got {array.dtype}")
    if array.shape != (count, 2):
        raise ValueError(f"{name} must have shape ({count}, 2), got {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite coordinates")
    return np.array(array, dtype=np.float64, copy=True, order="C")


def _empty_pairing(
    *,
    sheet: Literal["upper", "lower"],
    target_pool_size: int,
) -> FluentLfCleanPairing:
    empty_int = lambda: _readonly_copy(np.empty(0), dtype=np.int64)
    empty_float = lambda: _readonly_copy(np.empty(0), dtype=np.float64)
    return FluentLfCleanPairing(
        sheet=sheet,
        metric=_METRIC,
        target_pool_size=target_pool_size,
        source_canonical_index=empty_int(),
        target_canonical_index=empty_int(),
        distance_m=empty_float(),
        dx_m=empty_float(),
        dspan_m=empty_float(),
        second_target_canonical_index=empty_int(),
        second_distance_m=empty_float(),
        ambiguity_margin_m=empty_float(),
        mutual_nearest=_readonly_copy(np.empty(0), dtype=np.bool_),
        target_multiplicity=empty_int(),
    )


def _pair_projected_physical_points(
    *,
    sheet: Literal["upper", "lower"],
    source_canonical_index: np.ndarray,
    source_x_span_m: np.ndarray,
    source_full_domain_size: int,
    target_canonical_index: np.ndarray,
    target_x_span_m: np.ndarray,
    target_full_domain_size: int,
) -> FluentLfCleanPairing:
    """Pair validated canonical identities using exact float64 2-D geometry."""

    if sheet not in _SHEETS:
        raise ValueError("sheet must be exactly 'upper' or 'lower'")
    source_domain = _domain_size(
        source_full_domain_size, name="source_full_domain_size"
    )
    target_domain = _domain_size(
        target_full_domain_size, name="target_full_domain_size"
    )
    source_index = _canonical_index(
        source_canonical_index,
        name="source_canonical_index",
        full_domain_size=source_domain,
    )
    target_index = _canonical_index(
        target_canonical_index,
        name="target_canonical_index",
        full_domain_size=target_domain,
    )
    source_coordinates = _coordinates(
        source_x_span_m,
        name="source_x_span_m",
        count=source_index.size,
    )
    target_coordinates = _coordinates(
        target_x_span_m,
        name="target_x_span_m",
        count=target_index.size,
    )

    source_order = np.argsort(source_index, kind="stable")
    target_order = np.argsort(target_index, kind="stable")
    source_index = source_index[source_order]
    source_coordinates = source_coordinates[source_order]
    target_index = target_index[target_order]
    target_coordinates = target_coordinates[target_order]

    source_count = source_index.size
    target_count = target_index.size
    if source_count == 0:
        return _empty_pairing(sheet=sheet, target_pool_size=int(target_count))
    if target_count == 0:
        raise ValueError("pairing is undefined for a nonempty source and empty target")

    with np.errstate(over="ignore", invalid="ignore"):
        delta = target_coordinates[None, :, :] - source_coordinates[:, None, :]
        distance_squared = np.sum(delta * delta, axis=2, dtype=np.float64)
    if not np.all(np.isfinite(distance_squared)):
        raise ValueError("pairwise squared distance must be finite")

    source_rows = np.arange(source_count, dtype=np.int64)
    nearest_row = np.argmin(distance_squared, axis=1)
    nearest_d2 = distance_squared[source_rows, nearest_row]
    nearest_delta = delta[source_rows, nearest_row]
    distance = np.sqrt(nearest_d2)

    if target_count == 1:
        second_target = np.full(source_count, -1, dtype=np.int64)
        second_distance = np.full(source_count, np.inf, dtype=np.float64)
        ambiguity_margin = np.full(source_count, np.inf, dtype=np.float64)
    else:
        second_search = np.array(distance_squared, copy=True, order="C")
        second_search[source_rows, nearest_row] = np.inf
        second_row = np.argmin(second_search, axis=1)
        second_target = target_index[second_row]
        second_distance = np.sqrt(distance_squared[source_rows, second_row])
        ambiguity_margin = second_distance - distance

    reverse_source_row = np.argmin(distance_squared, axis=0)
    mutual = reverse_source_row[nearest_row] == source_rows
    target_hits = np.bincount(nearest_row, minlength=target_count).astype(
        np.int64, copy=False
    )
    multiplicity = target_hits[nearest_row]

    return FluentLfCleanPairing(
        sheet=sheet,
        metric=_METRIC,
        target_pool_size=int(target_count),
        source_canonical_index=_readonly_copy(source_index, dtype=np.int64),
        target_canonical_index=_readonly_copy(
            target_index[nearest_row], dtype=np.int64
        ),
        distance_m=_readonly_copy(distance, dtype=np.float64),
        dx_m=_readonly_copy(nearest_delta[:, 0], dtype=np.float64),
        dspan_m=_readonly_copy(nearest_delta[:, 1], dtype=np.float64),
        second_target_canonical_index=_readonly_copy(
            second_target, dtype=np.int64
        ),
        second_distance_m=_readonly_copy(second_distance, dtype=np.float64),
        ambiguity_margin_m=_readonly_copy(ambiguity_margin, dtype=np.float64),
        mutual_nearest=_readonly_copy(mutual, dtype=np.bool_),
        target_multiplicity=_readonly_copy(multiplicity, dtype=np.int64),
    )


def _require_mask(
    value: np.ndarray,
    *,
    name: str,
    count: int,
) -> np.ndarray:
    array = np.asarray(value)
    if array.dtype != np.dtype(np.bool_) or array.shape != (count,):
        raise ValueError(f"{name} must have dtype bool and shape ({count},)")
    return array


def build_fluent_lf_clean_pairing(
    *,
    integration: FluentProjectedSemanticsIntegration,
    fluent_masks: FluentCleanLeewardMasks,
    lf_fields: Mapping[str, np.ndarray],
    lf_masks: LfCleanLeewardMasks,
    sheet: Literal["upper", "lower"],
) -> FluentLfCleanPairing:
    """Build one explicit-sheet Fluent-clean to LF-clean geometry pairing."""

    if sheet not in _SHEETS:
        raise ValueError("sheet must be exactly 'upper' or 'lower'")
    if not isinstance(integration, FluentProjectedSemanticsIntegration):
        raise TypeError("integration must be FluentProjectedSemanticsIntegration")
    if not isinstance(fluent_masks, FluentCleanLeewardMasks):
        raise TypeError("fluent_masks must be FluentCleanLeewardMasks")
    if not isinstance(lf_fields, Mapping):
        raise TypeError("lf_fields must be a mapping")
    if not isinstance(lf_masks, LfCleanLeewardMasks):
        raise TypeError("lf_masks must be LfCleanLeewardMasks")

    projected_xyz = np.asarray(integration.projection.projected_xyz)
    if projected_xyz.dtype != np.dtype(np.float64):
        raise ValueError("integration projected_xyz must have dtype float64")
    if projected_xyz.ndim != 2 or projected_xyz.shape[1] != 3:
        raise ValueError("integration projected_xyz must have shape (N, 3)")
    source_domain_size = projected_xyz.shape[0]
    projection_index = np.asarray(integration.projection.canonical_index)
    if (
        projection_index.dtype != np.dtype(np.int64)
        or projection_index.shape != (source_domain_size,)
        or not np.array_equal(
            projection_index, np.arange(source_domain_size, dtype=np.int64)
        )
    ):
        raise ValueError("integration projection canonical identity must be 0..N-1")
    source_mask = _require_mask(
        getattr(fluent_masks, f"clean_leeward_{sheet}"),
        name=f"fluent clean_leeward_{sheet}",
        count=source_domain_size,
    )

    required_lf_fields = ("x_l_m", "span_l_m")
    missing = [name for name in required_lf_fields if name not in lf_fields]
    if missing:
        raise ValueError(f"missing required LF pairing fields: {missing}")
    target_x = np.asarray(lf_fields["x_l_m"])
    target_span = np.asarray(lf_fields["span_l_m"])
    if target_x.dtype != np.dtype(np.float64) or target_span.dtype != np.dtype(
        np.float64
    ):
        raise ValueError("LF leeward pairing coordinates must have dtype float64")
    if target_x.ndim != 1 or target_span.shape != target_x.shape:
        raise ValueError("LF leeward pairing coordinates must be equal-length 1-D arrays")
    target_domain_size = target_x.size
    target_mask = _require_mask(
        getattr(lf_masks, f"clean_leeward_{sheet}"),
        name=f"LF clean_leeward_{sheet}",
        count=target_domain_size,
    )

    source_index = np.flatnonzero(source_mask).astype(np.int64, copy=False)
    target_index = np.flatnonzero(target_mask).astype(np.int64, copy=False)
    source_coordinates = projected_xyz[source_mask][:, (0, 1)]
    target_coordinates = np.column_stack(
        (target_x[target_mask], target_span[target_mask])
    )

    return _pair_projected_physical_points(
        sheet=sheet,
        source_canonical_index=source_index,
        source_x_span_m=source_coordinates,
        source_full_domain_size=source_domain_size,
        target_canonical_index=target_index,
        target_x_span_m=target_coordinates,
        target_full_domain_size=target_domain_size,
    )