"""Strict canonical ingestion of Fluent wall-temperature observations."""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Literal

import numpy as np

from ref_enthalpy_method.mapping.fluent_clean import FluentCleanLeewardMasks
from ref_enthalpy_method.mapping.fluent_lf_pairing import FluentLfCleanPairing
from ref_enthalpy_method.mapping.fluent_semantics import FluentProjectedSemanticsIntegration
from ref_enthalpy_method.mapping.fluent_surface import (
    compare_canonical_geometry,
    read_fluent_surface_geometry_csv,
)

_COLUMN_NAME = "wall-temperature"
_UNIT = "K"
_METRIC = "projected_physical_x_span_euclidean_m"
_SHEETS = ("upper", "lower")


def _readonly_copy(value: np.ndarray, *, dtype: np.dtype | type) -> np.ndarray:
    result = np.array(value, dtype=dtype, copy=True, order="C")
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class FluentWallTemperatureObservations:
    sheet: Literal["upper", "lower"]
    column_name: str
    unit: str
    source_csv_sha256: str
    source_canonical_index: np.ndarray
    source_row_index: np.ndarray
    wall_temperature_K: np.ndarray

    def __post_init__(self) -> None:
        if self.sheet not in _SHEETS:
            raise ValueError("sheet must be exactly 'upper' or 'lower'")
        if self.column_name != _COLUMN_NAME:
            raise ValueError(f"column_name must be exactly {_COLUMN_NAME!r}")
        if self.unit != _UNIT:
            raise ValueError(f"unit must be exactly {_UNIT!r}")
        if (
            len(self.source_csv_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.source_csv_sha256)
        ):
            raise ValueError("source_csv_sha256 must be a lowercase hexadecimal SHA-256")

        expected_dtypes = {
            "source_canonical_index": np.dtype(np.int64),
            "source_row_index": np.dtype(np.int64),
            "wall_temperature_K": np.dtype(np.float64),
        }
        count: int | None = None
        for item in fields(self):
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
                raise ValueError(f"{item.name} violates the immutable owned array contract")
            if count is None:
                count = value.size
            elif value.shape != (count,):
                raise ValueError("all per-source observation arrays must have identical shapes")


def _read_wall_temperature_column(
    csv_path: str | Path,
) -> tuple[np.ndarray, str]:
    """Read one strict source-order wall-temperature column and raw-byte hash."""
    path = Path(csv_path)
    source_bytes = path.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Fluent wall-temperature CSV must be UTF-8 text") from error

    rows = csv.reader(io.StringIO(source_text, newline=""))
    try:
        header = next(rows)
    except StopIteration as error:
        raise ValueError("Fluent wall-temperature CSV is empty") from error
    normalized_header = [field.strip() for field in header]
    matches = [index for index, name in enumerate(normalized_header) if name == _COLUMN_NAME]
    if len(matches) != 1:
        raise ValueError("wall-temperature column must exist exactly once")
    column_index = matches[0]

    temperatures: list[np.float64] = []
    for csv_line_number, row in enumerate(rows, start=2):
        if column_index >= len(row):
            raise ValueError(f"missing wall-temperature value at CSV line {csv_line_number}")
        raw_value = row[column_index].strip()
        if not raw_value:
            raise ValueError(f"blank wall-temperature value at CSV line {csv_line_number}")
        try:
            value = np.float64(raw_value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"non-numeric wall-temperature value at CSV line {csv_line_number}"
            ) from error
        if not np.isfinite(value):
            raise ValueError(
                f"non-finite wall-temperature value at CSV line {csv_line_number}"
            )
        if value <= 0.0:
            raise ValueError(
                f"wall-temperature must be greater than zero K at CSV line {csv_line_number}"
            )
        temperatures.append(value)

    return np.array(temperatures, dtype=np.float64, copy=True, order="C"), source_sha256


def _validate_geometry_identity(
    csv_path: str | Path,
    integration: FluentProjectedSemanticsIntegration,
):
    projection = integration.projection
    canonical_solver_xyz = np.asarray(projection.solver_xyz)
    if canonical_solver_xyz.dtype != np.dtype(np.float64) or canonical_solver_xyz.ndim != 2 or canonical_solver_xyz.shape[1:] != (3,):
        raise ValueError("integration canonical solver geometry contract is invalid")
    count = canonical_solver_xyz.shape[0]
    if not np.array_equal(projection.canonical_index, np.arange(count, dtype=np.int64)):
        raise ValueError("integration canonical index must be exactly 0..N-1")
    expected_canonical_hash = hashlib.sha256(
        canonical_solver_xyz.tobytes(order="C")
    ).hexdigest()
    if projection.canonical_geometry_sha256 != expected_canonical_hash:
        raise ValueError("integration canonical geometry SHA-256 is invalid")

    provenance_path = Path(projection.geometry_source_path)
    provenance_bytes = provenance_path.read_bytes()
    if hashlib.sha256(provenance_bytes).hexdigest() != projection.geometry_source_sha256:
        raise ValueError("integration geometry source provenance SHA-256 is invalid")

    provenance_unshifted = read_fluent_surface_geometry_csv(
        provenance_path, x_offset_m=0.0
    )
    if provenance_unshifted.canonical_solver_xyz.shape != canonical_solver_xyz.shape:
        raise ValueError("integration geometry provenance domain does not match projection")
    x_offset_m = float(
        canonical_solver_xyz[0, 0]
        - provenance_unshifted.canonical_solver_xyz[0, 0]
    )
    provenance_surface = read_fluent_surface_geometry_csv(
        provenance_path, x_offset_m=x_offset_m
    )
    if not (
        provenance_surface.canonical_solver_xyz.dtype == canonical_solver_xyz.dtype
        and np.array_equal(
            provenance_surface.canonical_solver_xyz, canonical_solver_xyz
        )
        and provenance_surface.canonical_solver_xyz.tobytes(order="C")
        == canonical_solver_xyz.tobytes(order="C")
    ):
        raise ValueError(
            "integration canonical solver geometry does not exactly match its provenance"
        )

    current_surface = read_fluent_surface_geometry_csv(
        csv_path, x_offset_m=x_offset_m
    )
    if current_surface.canonical_solver_xyz.shape != canonical_solver_xyz.shape:
        raise ValueError("CSV row count does not match full Fluent canonical domain")
    if not compare_canonical_geometry(provenance_surface, current_surface).equal:
        raise ValueError("CSV geometry does not exactly match integration geometry")
    return current_surface


def _validate_mask(mask: np.ndarray, *, name: str, count: int) -> np.ndarray:
    value = np.asarray(mask)
    if value.dtype != np.dtype(np.bool_) or value.shape != (count,):
        raise ValueError(f"{name} must be a full-domain boolean mask with shape ({count},)")
    return value


def build_fluent_wall_temperature_observations(
    *,
    csv_path: str | Path,
    integration: FluentProjectedSemanticsIntegration,
    fluent_masks: FluentCleanLeewardMasks,
    pairing: FluentLfCleanPairing,
    sheet: Literal["upper", "lower"],
) -> FluentWallTemperatureObservations:
    """Attach source-order Fluent temperatures to validated paired source identities."""
    if sheet not in _SHEETS:
        raise ValueError("sheet must be exactly 'upper' or 'lower'")
    if pairing.sheet != sheet:
        raise ValueError("pairing sheet does not match requested sheet")
    if pairing.metric != _METRIC:
        raise ValueError(f"pairing metric must be exactly {_METRIC!r}")

    source_temperature_K, source_csv_sha256 = _read_wall_temperature_column(csv_path)
    surface = _validate_geometry_identity(csv_path, integration)
    count = surface.canonical_index.size
    if source_temperature_K.dtype != np.dtype(np.float64) or source_temperature_K.ndim != 1:
        raise ValueError("source-order wall-temperature must be one-dimensional float64")
    if source_temperature_K.shape != (count,):
        raise ValueError("CSV row count does not match full Fluent canonical domain")

    mask_names = (
        "projection_gate_valid",
        "semantic_valid",
        "planform_domain_valid",
        "clean_eligible",
        "clean_leeward_upper",
        "clean_leeward_lower",
        "clean_leeward_any",
    )
    validated_masks = {
        name: _validate_mask(getattr(fluent_masks, name), name=name, count=count)
        for name in mask_names
    }
    selected_mask = validated_masks[
        "clean_leeward_upper" if sheet == "upper" else "clean_leeward_lower"
    ]
    expected_source_index = np.flatnonzero(selected_mask).astype(np.int64, copy=False)

    source_index_raw = np.asarray(pairing.source_canonical_index)
    if source_index_raw.dtype != np.dtype(np.int64) or source_index_raw.ndim != 1:
        raise ValueError("pairing source_canonical_index must have shape (N,) and dtype int64")
    if source_index_raw.size and (
        np.any(source_index_raw < 0)
        or np.any(source_index_raw >= count)
        or np.any(source_index_raw[1:] <= source_index_raw[:-1])
    ):
        raise ValueError(
            "pairing source_canonical_index must be unique, strictly increasing, and in-domain"
        )
    if not np.array_equal(source_index_raw, expected_source_index):
        raise ValueError("pairing source_canonical_index does not match the sheet clean mask")

    canonical_temperature_K = source_temperature_K[surface.canonical_to_source_row]
    if not np.array_equal(
        canonical_temperature_K[surface.source_to_canonical_row],
        source_temperature_K,
    ):
        raise ValueError("wall-temperature canonical/source round-trip failed")

    source_canonical_index = _readonly_copy(source_index_raw, dtype=np.int64)
    source_row_index = _readonly_copy(
        surface.canonical_to_source_row[source_canonical_index], dtype=np.int64
    )
    wall_temperature_K = _readonly_copy(
        canonical_temperature_K[source_canonical_index], dtype=np.float64
    )
    if not np.array_equal(
        wall_temperature_K,
        source_temperature_K[source_row_index],
    ):
        raise ValueError("wall-temperature source provenance identity failed")

    return FluentWallTemperatureObservations(
        sheet=sheet,
        column_name=_COLUMN_NAME,
        unit=_UNIT,
        source_csv_sha256=source_csv_sha256,
        source_canonical_index=source_canonical_index,
        source_row_index=source_row_index,
        wall_temperature_K=wall_temperature_K,
    )