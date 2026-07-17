"""Strict geometry-only input contract for Fluent surface CSV exports."""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_REQUIRED_COLUMNS = (
    "cellnumber",
    "x-coordinate",
    "y-coordinate",
    "z-coordinate",
)


def _readonly_copy(value: np.ndarray, *, dtype: np.dtype | type) -> np.ndarray:
    result = np.array(value, dtype=dtype, copy=True, order="C")
    result.setflags(write=False)
    return result


def _normalize_header(value: str) -> str:
    return value.strip().lower()


def transform_fluent_xyz_to_solver(
    raw_xyz: np.ndarray,
    *,
    x_offset_m: float,
) -> np.ndarray:
    """Convert Fluent ``(x, y, z)`` metres to solver ``(x, span, up)`` metres.

    The caller must supply the finite x offset explicitly. No axis exchange,
    sign change, scaling, unit inference, absolute value, fitting, or automatic
    translation is performed.
    """
    source = np.asarray(raw_xyz, dtype=np.float64)
    if source.ndim != 2 or source.shape[1] != 3:
        raise ValueError(f"raw_xyz must have shape (N, 3), got {source.shape}")
    if not np.all(np.isfinite(source)):
        raise ValueError("raw_xyz must contain only finite coordinates")
    try:
        offset = float(x_offset_m)
    except (TypeError, ValueError) as error:
        raise ValueError("x_offset_m must be a finite scalar") from error
    if not np.isfinite(offset):
        raise ValueError("x_offset_m must be a finite scalar")

    solver_xyz = np.array(source, dtype=np.float64, copy=True, order="C")
    solver_xyz[:, 0] += offset
    return solver_xyz


@dataclass(frozen=True)
class CanonicalGeometryComparison:
    shape_equal: bool
    dtype_equal: bool
    numerical_exact_equal: bool
    c_order_bytes_equal: bool
    maximum_absolute_coordinate_difference: float

    @property
    def equal(self) -> bool:
        return (
            self.shape_equal
            and self.dtype_equal
            and self.numerical_exact_equal
            and self.c_order_bytes_equal
        )


@dataclass(frozen=True)
class FluentSurfaceGeometry:
    """Immutable Fluent geometry rows and their deterministic canonical identity.

    ``canonical_index`` is stable only for the same explicit coordinate
    transform and the same unique solver-coordinate set, ordered exactly by
    ``solver_x``, ``solver_span``, then ``solver_up``. It is not an identity
    across different meshes, geometry versions, or floating-point rewrites.
    All arrays are owned, C-contiguous, and read-only.
    """

    source_path: Path
    source_sha256: str
    source_row_index: np.ndarray
    cellnumber: np.ndarray
    raw_xyz: np.ndarray
    solver_xyz: np.ndarray
    canonical_index: np.ndarray
    canonical_to_source_row: np.ndarray
    source_to_canonical_row: np.ndarray

    @property
    def canonical_solver_xyz(self) -> np.ndarray:
        result = np.ascontiguousarray(self.solver_xyz[self.canonical_to_source_row])
        result.setflags(write=False)
        return result


def _canonical_mappings(solver_xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    count = solver_xyz.shape[0]
    canonical_to_source = np.lexsort(
        (solver_xyz[:, 2], solver_xyz[:, 1], solver_xyz[:, 0])
    ).astype(np.int64, copy=False)
    canonical_xyz = solver_xyz[canonical_to_source]
    if count > 1:
        duplicate_pairs = np.all(canonical_xyz[1:] == canonical_xyz[:-1], axis=1)
        duplicate_count = int(np.count_nonzero(duplicate_pairs))
        if duplicate_count:
            raise ValueError(
                "duplicate geometry coordinates are not supported: "
                f"found {duplicate_count} duplicate coordinate pair(s)"
            )

    source_to_canonical = np.empty(count, dtype=np.int64)
    source_to_canonical[canonical_to_source] = np.arange(count, dtype=np.int64)
    expected = np.arange(count, dtype=np.int64)
    if not (
        np.array_equal(canonical_to_source[source_to_canonical], expected)
        and np.array_equal(source_to_canonical[canonical_to_source], expected)
    ):
        raise RuntimeError("canonical/source geometry mappings failed round-trip validation")
    return canonical_to_source, source_to_canonical


def read_fluent_surface_geometry_csv(
    source_path: str | Path,
    *,
    x_offset_m: float,
) -> FluentSurfaceGeometry:
    """Read only Fluent geometry fields and establish canonical row identity."""
    path = Path(source_path).resolve()
    source_bytes = path.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    try:
        source_text = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"Fluent geometry CSV must be UTF-8 text: {path}") from error

    rows = csv.reader(io.StringIO(source_text, newline=""))
    try:
        raw_header = next(rows)
    except StopIteration as error:
        raise ValueError("Fluent geometry CSV is empty") from error
    if not raw_header or all(not field.strip() for field in raw_header):
        raise ValueError("Fluent geometry CSV has no header")

    normalized_header = [_normalize_header(field) for field in raw_header]
    duplicates = sorted(
        {name for name in normalized_header if normalized_header.count(name) > 1}
    )
    if duplicates:
        raise ValueError(
            "duplicate CSV header(s) after normalization: " + ", ".join(duplicates)
        )
    missing = [name for name in _REQUIRED_COLUMNS if name not in normalized_header]
    if missing:
        raise ValueError("missing required Fluent geometry column(s): " + ", ".join(missing))
    columns = {name: normalized_header.index(name) for name in _REQUIRED_COLUMNS}

    cellnumbers: list[str] = []
    coordinates: list[tuple[float, float, float]] = []
    for csv_line_number, row in enumerate(rows, start=2):
        if not row or all(not field.strip() for field in row):
            raise ValueError(f"empty data row at CSV line {csv_line_number}")
        required_max_index = max(columns.values())
        if len(row) <= required_max_index:
            raise ValueError(f"incomplete data row at CSV line {csv_line_number}")
        cellnumber = row[columns["cellnumber"]].strip()
        if not cellnumber:
            raise ValueError(f"empty cellnumber at CSV line {csv_line_number}")
        try:
            xyz = tuple(
                np.float64(row[columns[name]].strip())
                for name in _REQUIRED_COLUMNS[1:]
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"non-numeric geometry coordinate at CSV line {csv_line_number}"
            ) from error
        if not np.all(np.isfinite(xyz)):
            raise ValueError(f"non-finite geometry coordinate at CSV line {csv_line_number}")
        cellnumbers.append(cellnumber)
        coordinates.append(xyz)

    if not coordinates:
        raise ValueError("Fluent geometry CSV contains no data rows")

    raw_xyz = np.asarray(coordinates, dtype=np.float64)
    solver_xyz = transform_fluent_xyz_to_solver(raw_xyz, x_offset_m=x_offset_m)
    canonical_to_source, source_to_canonical = _canonical_mappings(solver_xyz)
    count = raw_xyz.shape[0]

    return FluentSurfaceGeometry(
        source_path=path,
        source_sha256=source_sha256,
        source_row_index=_readonly_copy(np.arange(count), dtype=np.int64),
        cellnumber=_readonly_copy(np.asarray(cellnumbers), dtype=np.str_),
        raw_xyz=_readonly_copy(raw_xyz, dtype=np.float64),
        solver_xyz=_readonly_copy(solver_xyz, dtype=np.float64),
        canonical_index=_readonly_copy(np.arange(count), dtype=np.int64),
        canonical_to_source_row=_readonly_copy(canonical_to_source, dtype=np.int64),
        source_to_canonical_row=_readonly_copy(source_to_canonical, dtype=np.int64),
    )


def compare_canonical_geometry(
    left: FluentSurfaceGeometry,
    right: FluentSurfaceGeometry,
) -> CanonicalGeometryComparison:
    """Compare canonical coordinates exactly, without tolerance-based equivalence."""
    left_xyz = left.canonical_solver_xyz
    right_xyz = right.canonical_solver_xyz
    shape_equal = left_xyz.shape == right_xyz.shape
    dtype_equal = left_xyz.dtype == right_xyz.dtype
    numerical_exact_equal = shape_equal and bool(np.array_equal(left_xyz, right_xyz))
    c_order_bytes_equal = (
        shape_equal
        and dtype_equal
        and left_xyz.tobytes(order="C") == right_xyz.tobytes(order="C")
    )
    if shape_equal:
        maximum_difference = float(np.max(np.abs(left_xyz - right_xyz), initial=0.0))
    else:
        maximum_difference = float("inf")
    return CanonicalGeometryComparison(
        shape_equal=shape_equal,
        dtype_equal=dtype_equal,
        numerical_exact_equal=numerical_exact_equal,
        c_order_bytes_equal=c_order_bytes_equal,
        maximum_absolute_coordinate_difference=maximum_difference,
    )
