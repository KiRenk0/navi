"""Source-level Fluent observation to LF leeward TPG prediction comparison."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields as dataclass_fields
from typing import Literal

import numpy as np

from ref_enthalpy_method.mapping.fluent_lf_pairing import FluentLfCleanPairing
from ref_enthalpy_method.mapping.fluent_wall_temperature import (
    FluentWallTemperatureObservations,
)
from ref_enthalpy_method.mapping.lf_clean import LfCleanLeewardMasks

_OBSERVATION_FIELD_NAME = "wall-temperature"
_UNIT = "K"
_PREDICTION_PROVIDER = (
    "ref_enthalpy_method.aero.leeward_recovery."
    "build_leeward_freestream_recovery"
)
_SHEETS = ("upper", "lower")


def _readonly_copy(value: np.ndarray, *, dtype: np.dtype | type) -> np.ndarray:
    result = np.array(value, dtype=dtype, copy=True, order="C")
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class FluentLfTawComparison:
    sheet: Literal["upper", "lower"]
    source_csv_sha256: str
    observation_field_name: str
    prediction_field_name: str
    unit: str
    prediction_provider: str
    pairing_metric: str
    source_canonical_index: np.ndarray
    source_row_index: np.ndarray
    target_canonical_index: np.ndarray
    wall_temperature_K: np.ndarray
    Taw_tpg_leeward_K: np.ndarray
    signed_error_K: np.ndarray
    signed_relative_error_pct: np.ndarray
    absolute_error_K: np.ndarray
    absolute_relative_error_pct: np.ndarray

    def __post_init__(self) -> None:
        if self.sheet not in _SHEETS:
            raise ValueError("sheet must be exactly 'upper' or 'lower'")
        if (
            len(self.source_csv_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.source_csv_sha256
            )
        ):
            raise ValueError(
                "source_csv_sha256 must be a lowercase hexadecimal SHA-256"
            )
        if self.observation_field_name != _OBSERVATION_FIELD_NAME:
            raise ValueError(
                f"observation_field_name must be exactly {_OBSERVATION_FIELD_NAME!r}"
            )
        expected_prediction_field = f"Taw_tpg_leeward_{self.sheet}"
        if self.prediction_field_name != expected_prediction_field:
            raise ValueError(
                f"prediction_field_name must be exactly {expected_prediction_field!r}"
            )
        if self.unit != _UNIT:
            raise ValueError(f"unit must be exactly {_UNIT!r}")
        if self.prediction_provider != _PREDICTION_PROVIDER:
            raise ValueError(
                f"prediction_provider must be exactly {_PREDICTION_PROVIDER!r}"
            )
        if not isinstance(self.pairing_metric, str) or not self.pairing_metric:
            raise ValueError("pairing_metric must be a nonempty string")

        index_names = (
            "source_canonical_index",
            "source_row_index",
            "target_canonical_index",
        )
        float_names = (
            "wall_temperature_K",
            "Taw_tpg_leeward_K",
            "signed_error_K",
            "signed_relative_error_pct",
            "absolute_error_K",
            "absolute_relative_error_pct",
        )
        expected_dtypes = {
            **{name: np.dtype(np.int64) for name in index_names},
            **{name: np.dtype(np.float64) for name in float_names},
        }
        count: int | None = None
        for item in dataclass_fields(self):
            if item.name not in expected_dtypes:
                continue
            value = getattr(self, item.name)
            if (
                not isinstance(value, np.ndarray)
                or value.dtype != expected_dtypes[item.name]
                or value.ndim != 1
                or not value.flags.owndata
                or not value.flags.c_contiguous
                or value.flags.writeable
            ):
                raise ValueError(
                    f"{item.name} violates the immutable owned array contract"
                )
            if count is None:
                count = value.size
            elif value.shape != (count,):
                raise ValueError(
                    "all per-source comparison arrays must have identical shapes"
                )


def _require_array(
    value: np.ndarray,
    *,
    name: str,
    dtype: np.dtype | type,
    shape: tuple[int, ...] | None = None,
) -> np.ndarray:
    array = np.asarray(value)
    expected_dtype = np.dtype(dtype)
    if array.dtype != expected_dtype or array.ndim != 1:
        raise ValueError(f"{name} must have shape (N,) and dtype {expected_dtype}")
    if shape is not None and array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    return array


def build_fluent_lf_taw_comparison(
    *,
    observation: FluentWallTemperatureObservations,
    pairing: FluentLfCleanPairing,
    lf_fields: Mapping[str, np.ndarray],
    lf_masks: LfCleanLeewardMasks,
    sheet: Literal["upper", "lower"],
) -> FluentLfTawComparison:
    """Join each Fluent source directly to its paired full-canonical LF Taw value."""
    if sheet not in _SHEETS:
        raise ValueError("sheet must be exactly 'upper' or 'lower'")
    if not isinstance(observation, FluentWallTemperatureObservations):
        raise TypeError("observation must be FluentWallTemperatureObservations")
    if not isinstance(pairing, FluentLfCleanPairing):
        raise TypeError("pairing must be FluentLfCleanPairing")
    if not isinstance(lf_fields, Mapping):
        raise TypeError("lf_fields must be a mapping")
    if not isinstance(lf_masks, LfCleanLeewardMasks):
        raise TypeError("lf_masks must be LfCleanLeewardMasks")
    if observation.sheet != sheet:
        raise ValueError("observation sheet does not match requested sheet")
    if pairing.sheet != sheet:
        raise ValueError("pairing sheet does not match requested sheet")
    if observation.column_name != _OBSERVATION_FIELD_NAME:
        raise ValueError(
            f"observation column_name must be exactly {_OBSERVATION_FIELD_NAME!r}"
        )
    if observation.unit != _UNIT:
        raise ValueError(f"observation unit must be exactly {_UNIT!r}")

    observation_source = _require_array(
        observation.source_canonical_index,
        name="observation source_canonical_index",
        dtype=np.int64,
    )
    pairing_source = _require_array(
        pairing.source_canonical_index,
        name="pairing source_canonical_index",
        dtype=np.int64,
    )
    if observation_source.shape != pairing_source.shape:
        raise ValueError(
            "observation and pairing source_canonical_index shapes differ"
        )
    if not np.array_equal(observation_source, pairing_source):
        raise ValueError(
            "observation and pairing source_canonical_index identities differ"
        )
    count = observation_source.size

    source_row = _require_array(
        observation.source_row_index,
        name="observation source_row_index",
        dtype=np.int64,
        shape=(count,),
    )
    target = _require_array(
        pairing.target_canonical_index,
        name="pairing target_canonical_index",
        dtype=np.int64,
        shape=(count,),
    )
    wall_temperature = _require_array(
        observation.wall_temperature_K,
        name="observation wall_temperature_K",
        dtype=np.float64,
        shape=(count,),
    )
    if not np.all(np.isfinite(wall_temperature)):
        raise ValueError("observation wall_temperature_K must contain only finite values")
    if np.any(wall_temperature <= 0.0):
        raise ValueError("observation wall_temperature_K must be greater than zero K")

    clean_target_mask = np.asarray(getattr(lf_masks, f"clean_leeward_{sheet}"))
    if clean_target_mask.dtype != np.dtype(np.bool_) or clean_target_mask.ndim != 1:
        raise ValueError(
            f"LF clean_leeward_{sheet} must be a full-domain one-dimensional bool mask"
        )
    full_domain_size = clean_target_mask.size
    if pairing.target_pool_size != int(np.count_nonzero(clean_target_mask)):
        raise ValueError("pairing target_pool_size does not match the LF clean target pool")
    if target.size and (
        np.any(target < 0)
        or np.any(target >= full_domain_size)
        or not np.all(clean_target_mask[target])
    ):
        raise ValueError(
            "pairing target_canonical_index contains an index outside the LF clean target pool"
        )

    prediction_field_name = f"Taw_tpg_leeward_{sheet}"
    if prediction_field_name not in lf_fields:
        raise ValueError(
            f"missing required LF prediction field: {prediction_field_name}"
        )
    prediction_field = _require_array(
        lf_fields[prediction_field_name],
        name=prediction_field_name,
        dtype=np.float64,
        shape=(full_domain_size,),
    )
    selected_prediction = prediction_field[target]
    if not np.all(np.isfinite(selected_prediction)):
        raise ValueError("selected LF prediction must contain only finite values")
    if np.any(selected_prediction <= 0.0):
        raise ValueError("selected LF prediction must be greater than zero K")

    signed_error = selected_prediction - wall_temperature
    signed_relative_error = 100.0 * signed_error / wall_temperature
    absolute_error = np.abs(signed_error)
    absolute_relative_error = np.abs(signed_relative_error)

    return FluentLfTawComparison(
        sheet=sheet,
        source_csv_sha256=observation.source_csv_sha256,
        observation_field_name=_OBSERVATION_FIELD_NAME,
        prediction_field_name=prediction_field_name,
        unit=_UNIT,
        prediction_provider=_PREDICTION_PROVIDER,
        pairing_metric=pairing.metric,
        source_canonical_index=_readonly_copy(observation_source, dtype=np.int64),
        source_row_index=_readonly_copy(source_row, dtype=np.int64),
        target_canonical_index=_readonly_copy(target, dtype=np.int64),
        wall_temperature_K=_readonly_copy(wall_temperature, dtype=np.float64),
        Taw_tpg_leeward_K=_readonly_copy(selected_prediction, dtype=np.float64),
        signed_error_K=_readonly_copy(signed_error, dtype=np.float64),
        signed_relative_error_pct=_readonly_copy(
            signed_relative_error, dtype=np.float64
        ),
        absolute_error_K=_readonly_copy(absolute_error, dtype=np.float64),
        absolute_relative_error_pct=_readonly_copy(
            absolute_relative_error, dtype=np.float64
        ),
    )
