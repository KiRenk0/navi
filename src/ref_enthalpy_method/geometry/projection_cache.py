"""Geometry-identity projection cache with fail-closed loading.

The cache binds a full projection result to a complete geometry identity
so that the same projection can be reused across different temperature cases
that share identical geometry.

Cache identity includes:
- schema version
- algorithm semantic version
- Fluent source geometry SHA-256
- Fluent canonical geometry SHA-256
- canonical point count
- x_offset_m
- STL raw SHA-256
- triangle canonical identity/hash
- vehicle spec raw SHA-256
- sampling spec raw SHA-256
- outline/source geometry hash
- projection_gate_m
- coordinate convention
- exact tie-break identity
- dtype/shape contract

Loading fails closed on any mismatch.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_SCHEMA_VERSION = "exact-projection-cache/v1"
ALGORITHM_VERSION = "n3a.5b-exact-bvh/v1"
COORDINATE_CONVENTION = "solver-(x,span,up)-metres"
TIE_BREAK_IDENTITY = (
    "smallest-triangle-index-among-equivalent-distances;"
    "tie_abs_tol=1e-12;tie_rel_tol=1e-12"
)
DTYPE_CONTRACT = {
    "projected_xyz": "float64",
    "triangle_id": "int64",
    "raw_normal": "float64",
    "projection_distance_m": "float64",
    "projection_gate_pass": "bool",
}
SHAPE_TEMPLATES = {
    "projected_xyz": (None, 3),
    "triangle_id": (None,),
    "raw_normal": (None, 3),
    "projection_distance_m": (None,),
    "projection_gate_pass": (None,),
}


# ---------------------------------------------------------------------------
# Helper: deterministic SHA-256 from bytes or file
# ---------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: str | Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _sha256_geometry_csv(path: str | Path) -> str:
    """Hash only the required Fluent geometry fields in source-row order."""
    source_bytes = Path(path).read_bytes()
    try:
        source_text = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Fluent geometry CSV must be UTF-8 text: {path}") from exc

    reader = csv.reader(io.StringIO(source_text, newline=""))
    try:
        raw_header = next(reader)
    except StopIteration as exc:
        raise ValueError("Fluent geometry CSV is empty") from exc
    header = [field.strip().lower() for field in raw_header]
    required = ("cellnumber", "x-coordinate", "y-coordinate", "z-coordinate")
    if not all(name in header for name in required):
        return _sha256_file(path)
    columns = [header.index(name) for name in required]

    digest = hashlib.sha256()
    row_count = 0
    for line_number, row in enumerate(reader, start=2):
        if len(row) <= max(columns):
            raise ValueError(f"incomplete data row at CSV line {line_number}")
        values = [row[index].strip() for index in columns]
        if not values[0]:
            raise ValueError(f"empty cellnumber at CSV line {line_number}")
        try:
            coordinates = np.asarray(values[1:], dtype=np.float64)
        except ValueError as exc:
            raise ValueError(
                f"non-numeric geometry coordinate at CSV line {line_number}"
            ) from exc
        if not np.all(np.isfinite(coordinates)):
            raise ValueError(f"non-finite geometry coordinate at CSV line {line_number}")
        digest.update(values[0].encode("utf-8"))
        digest.update(b"\0")
        digest.update(np.ascontiguousarray(coordinates).tobytes(order="C"))
        row_count += 1
    if row_count == 0:
        raise ValueError("Fluent geometry CSV contains no data rows")
    return digest.hexdigest()


def _sha256_ndarray(arr: np.ndarray) -> str:
    """Deterministic SHA-256 of array content (C-order bytes)."""
    return _sha256_bytes(np.ascontiguousarray(arr).tobytes(order="C"))


def _sha256_triangles(triangles: np.ndarray) -> str:
    """Deterministic SHA-256 of triangle mesh (C-order, float64)."""
    tris = np.asarray(triangles, dtype=np.float64)
    return _sha256_bytes(np.ascontiguousarray(tris).tobytes(order="C"))


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

_REQUIRED_MANIFEST_KEYS = frozenset(
    {
        "cache_schema_version",
        "algorithm_version",
        "fluent_source_geometry_sha256",
        "fluent_canonical_geometry_sha256",
        "canonical_point_count",
        "x_offset_m",
        "stl_raw_sha256",
        "triangle_canonical_sha256",
        "vehicle_spec_raw_sha256",
        "sampling_spec_raw_sha256",
        "outline_geometry_sha256",
        "projection_gate_m",
        "coordinate_convention",
        "tie_break_identity",
        "projected_xyz_sha256",
        "triangle_id_sha256",
        "raw_normal_sha256",
        "projection_distance_m_sha256",
        "projection_gate_pass_sha256",
        "projected_xyz_shape",
        "triangle_id_shape",
        "raw_normal_shape",
        "projection_distance_m_shape",
        "projection_gate_pass_shape",
    }
)


def build_cache_manifest(
    *,
    fluent_source_geometry_sha256: str,
    fluent_canonical_geometry_sha256: str,
    canonical_point_count: int,
    x_offset_m: float,
    stl_raw_sha256: str,
    triangle_canonical_sha256: str,
    vehicle_spec_raw_sha256: str,
    sampling_spec_raw_sha256: str,
    outline_geometry_sha256: str,
    projection_gate_m: float,
    projected_xyz: np.ndarray,
    triangle_id: np.ndarray,
    raw_normal: np.ndarray,
    projection_distance_m: np.ndarray,
    projection_gate_pass: np.ndarray,
) -> dict[str, Any]:
    """Build a complete cache manifest dict."""
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "fluent_source_geometry_sha256": str(fluent_source_geometry_sha256),
        "fluent_canonical_geometry_sha256": str(fluent_canonical_geometry_sha256),
        "canonical_point_count": int(canonical_point_count),
        "x_offset_m": float(x_offset_m),
        "stl_raw_sha256": str(stl_raw_sha256),
        "triangle_canonical_sha256": str(triangle_canonical_sha256),
        "vehicle_spec_raw_sha256": str(vehicle_spec_raw_sha256),
        "sampling_spec_raw_sha256": str(sampling_spec_raw_sha256),
        "outline_geometry_sha256": str(outline_geometry_sha256),
        "projection_gate_m": float(projection_gate_m),
        "coordinate_convention": COORDINATE_CONVENTION,
        "tie_break_identity": TIE_BREAK_IDENTITY,
        "projected_xyz_sha256": _sha256_ndarray(projected_xyz),
        "triangle_id_sha256": _sha256_ndarray(triangle_id),
        "raw_normal_sha256": _sha256_ndarray(raw_normal),
        "projection_distance_m_sha256": _sha256_ndarray(projection_distance_m),
        "projection_gate_pass_sha256": _sha256_ndarray(projection_gate_pass),
        "projected_xyz_shape": list(projected_xyz.shape),
        "triangle_id_shape": list(triangle_id.shape),
        "raw_normal_shape": list(raw_normal.shape),
        "projection_distance_m_shape": list(projection_distance_m.shape),
        "projection_gate_pass_shape": list(projection_gate_pass.shape),
    }


# ---------------------------------------------------------------------------
# Cache data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CachedProjection:
    """Immutable projection result loaded from a validated cache."""

    projected_xyz: np.ndarray           # (N, 3) float64
    triangle_id: np.ndarray             # (N,) int64
    raw_normal: np.ndarray              # (N, 3) float64
    projection_distance_m: np.ndarray   # (N,) float64
    projection_gate_pass: np.ndarray    # (N,) bool
    manifest: dict[str, Any]


# ---------------------------------------------------------------------------
# Cache writer
# ---------------------------------------------------------------------------


def write_projection_cache(
    *,
    target_path: str | Path,
    projected_xyz: np.ndarray,
    triangle_id: np.ndarray,
    raw_normal: np.ndarray,
    projection_distance_m: np.ndarray,
    projection_gate_pass: np.ndarray,
    manifest: dict[str, Any],
) -> None:
    """Write a projection cache NPZ file atomically.

    Parameters
    ----------
    target_path : Path
        Destination file path. Written atomically via a temporary sibling.
    """
    path = Path(target_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True)

    # Validate shapes against manifest before writing
    _validate_cache_arrays(
        projected_xyz=projected_xyz,
        triangle_id=triangle_id,
        raw_normal=raw_normal,
        projection_distance_m=projection_distance_m,
        projection_gate_pass=projection_gate_pass,
        manifest=manifest,
    )

    # Write atomically to a temp file, then rename
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=".npz", prefix=".proj_cache_", dir=path.parent
    )
    # Close the fd immediately on Windows to avoid file locking
    os.close(tmp_fd)
    try:
        np.savez_compressed(
            tmp_path,
            projected_xyz=np.ascontiguousarray(projected_xyz, dtype=np.float64),
            triangle_id=np.ascontiguousarray(triangle_id, dtype=np.int64),
            raw_normal=np.ascontiguousarray(raw_normal, dtype=np.float64),
            projection_distance_m=np.ascontiguousarray(
                projection_distance_m, dtype=np.float64
            ),
            projection_gate_pass=np.ascontiguousarray(
                projection_gate_pass, dtype=np.bool_
            ),
            manifest_json=manifest_json.encode("utf-8"),
        )
        Path(tmp_path).replace(path)
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Cache loader (fail-closed)
# ---------------------------------------------------------------------------


class CacheIdentityMismatchError(ValueError):
    """Raised when cache identity does not match the requested geometry."""


class CacheIntegrityError(ValueError):
    """Raised when cache content is corrupted or fails validation."""


def _validate_cache_arrays(
    *,
    projected_xyz: np.ndarray,
    triangle_id: np.ndarray,
    raw_normal: np.ndarray,
    projection_distance_m: np.ndarray,
    projection_gate_pass: np.ndarray,
    manifest: dict[str, Any],
) -> None:
    """Validate array shape, dtype, content, and manifest shape metadata."""
    try:
        count = int(manifest["canonical_point_count"])
        projection_gate_m = float(manifest["projection_gate_m"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CacheIntegrityError(
            "cache manifest has invalid point-count or projection-gate metadata"
        ) from exc
    if count < 0 or not np.isfinite(projection_gate_m) or projection_gate_m <= 0.0:
        raise CacheIntegrityError(
            "cache manifest point count or projection gate is outside its contract"
        )

    arrays = {
        "projected_xyz": np.asarray(projected_xyz),
        "triangle_id": np.asarray(triangle_id),
        "raw_normal": np.asarray(raw_normal),
        "projection_distance_m": np.asarray(projection_distance_m),
        "projection_gate_pass": np.asarray(projection_gate_pass),
    }
    expected_shapes = {
        "projected_xyz": (count, 3),
        "triangle_id": (count,),
        "raw_normal": (count, 3),
        "projection_distance_m": (count,),
        "projection_gate_pass": (count,),
    }

    for name, arr in arrays.items():
        expected_shape = expected_shapes[name]
        if arr.shape != expected_shape:
            raise CacheIntegrityError(
                f"{name} shape mismatch: expected {expected_shape}, got {arr.shape}"
            )
        if str(arr.dtype) != DTYPE_CONTRACT[name]:
            raise CacheIntegrityError(
                f"{name} dtype mismatch: expected {DTYPE_CONTRACT[name]}, got {arr.dtype}"
            )
        manifest_shape = manifest.get(f"{name}_shape")
        if manifest_shape != list(expected_shape):
            raise CacheIntegrityError(
                f"{name} manifest shape mismatch: expected {list(expected_shape)}, "
                f"got {manifest_shape!r}"
            )

    for name in ("projected_xyz", "raw_normal", "projection_distance_m"):
        if not np.all(np.isfinite(arrays[name])):
            raise CacheIntegrityError(f"{name} contains non-finite values")

    if np.any(arrays["projection_distance_m"] < 0.0):
        raise CacheIntegrityError("projection_distance_m contains negative values")
    if np.any(arrays["triangle_id"] < 0):
        raise CacheIntegrityError("triangle_id contains negative indices")

    expected_gate = arrays["projection_distance_m"] <= projection_gate_m
    if not np.array_equal(arrays["projection_gate_pass"], expected_gate):
        raise CacheIntegrityError(
            "projection_gate_pass is inconsistent with projection_distance_m "
            "and projection_gate_m"
        )


def _validate_manifest_identity(
    manifest: dict[str, Any],
    *,
    fluent_source_geometry_sha256: str,
    fluent_canonical_geometry_sha256: str,
    canonical_point_count: int,
    x_offset_m: float,
    stl_raw_sha256: str,
    triangle_canonical_sha256: str,
    vehicle_spec_raw_sha256: str,
    sampling_spec_raw_sha256: str,
    outline_geometry_sha256: str,
    projection_gate_m: float,
) -> None:
    """Fail-closed identity check: every field must match exactly."""

    if not isinstance(manifest, dict):
        raise CacheIntegrityError("cache manifest must be a JSON object")

    missing = _REQUIRED_MANIFEST_KEYS - set(manifest)
    if missing:
        raise CacheIdentityMismatchError(
            f"Cache manifest is missing required keys: {sorted(missing)}"
        )

    checks = (
        ("cache_schema_version", CACHE_SCHEMA_VERSION),
        ("algorithm_version", ALGORITHM_VERSION),
        ("coordinate_convention", COORDINATE_CONVENTION),
        ("tie_break_identity", TIE_BREAK_IDENTITY),
    )
    for key, expected in checks:
        actual = manifest.get(key)
        if actual != expected:
            raise CacheIdentityMismatchError(
                f"Cache {key} mismatch: expected {expected!r}, got {actual!r}"
            )

    # String-compare identity fields
    identity_checks = (
        ("fluent_source_geometry_sha256", fluent_source_geometry_sha256),
        ("fluent_canonical_geometry_sha256", fluent_canonical_geometry_sha256),
        ("stl_raw_sha256", stl_raw_sha256),
        ("triangle_canonical_sha256", triangle_canonical_sha256),
        ("vehicle_spec_raw_sha256", vehicle_spec_raw_sha256),
        ("sampling_spec_raw_sha256", sampling_spec_raw_sha256),
        ("outline_geometry_sha256", outline_geometry_sha256),
    )
    for key, expected in identity_checks:
        actual = manifest.get(key)
        expected = str(expected)
        actual = str(actual) if actual is not None else ""
        if actual != expected:
            raise CacheIdentityMismatchError(
                f"Cache {key} mismatch:\n"
                f"  expected: {expected}\n"
                f"  got:      {actual}"
            )

    # Numeric identity checks
    numeric_checks = (
        ("canonical_point_count", canonical_point_count),
        ("x_offset_m", x_offset_m),
        ("projection_gate_m", projection_gate_m),
    )
    for key, expected in numeric_checks:
        actual = manifest.get(key)
        expected_float = float(expected)
        try:
            actual_float = float(actual)
        except (TypeError, ValueError):
            raise CacheIdentityMismatchError(
                f"Cache {key} is not numeric: {actual!r}"
            )
        if actual_float != expected_float:
            raise CacheIdentityMismatchError(
                f"Cache {key} mismatch: expected {expected_float}, "
                f"got {actual_float}"
            )


def load_projection_cache(
    cache_path: str | Path,
    *,
    fluent_source_geometry_sha256: str,
    fluent_canonical_geometry_sha256: str,
    canonical_point_count: int,
    x_offset_m: float,
    stl_raw_sha256: str,
    triangle_canonical_sha256: str,
    vehicle_spec_raw_sha256: str,
    sampling_spec_raw_sha256: str,
    outline_geometry_sha256: str,
    projection_gate_m: float,
    triangle_count: int | None = None,
) -> CachedProjection:
    """Load a projection cache with strict fail-closed identity validation.

    Parameters
    ----------
    cache_path : Path
        Path to the .npz cache file.
    (all other parameters) : identity fields that must match the cache exactly.

    Returns
    -------
    CachedProjection

    Raises
    ------
    CacheIdentityMismatchError
        Any identity field mismatch.
    CacheIntegrityError
        Corrupted or invalid cache content.
    """
    path = Path(cache_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Cache file does not exist: {path}")

    try:
        with path.open("rb") as cache_file:
            with np.load(cache_file, allow_pickle=False) as data:
                try:
                    manifest_json = bytes(data["manifest_json"]).decode("utf-8")
                    manifest = json.loads(manifest_json)
                except KeyError as exc:
                    raise CacheIntegrityError(
                        f"Cache file {path} is missing manifest_json"
                    ) from exc
                except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise CacheIntegrityError(
                        f"Cache file {path} has corrupted manifest: {exc}"
                    ) from exc

                _validate_manifest_identity(
                    manifest,
                    fluent_source_geometry_sha256=fluent_source_geometry_sha256,
                    fluent_canonical_geometry_sha256=fluent_canonical_geometry_sha256,
                    canonical_point_count=canonical_point_count,
                    x_offset_m=x_offset_m,
                    stl_raw_sha256=stl_raw_sha256,
                    triangle_canonical_sha256=triangle_canonical_sha256,
                    vehicle_spec_raw_sha256=vehicle_spec_raw_sha256,
                    sampling_spec_raw_sha256=sampling_spec_raw_sha256,
                    outline_geometry_sha256=outline_geometry_sha256,
                    projection_gate_m=projection_gate_m,
                )

                try:
                    projected_xyz = np.array(data["projected_xyz"], copy=True)
                    triangle_id = np.array(data["triangle_id"], copy=True)
                    raw_normal = np.array(data["raw_normal"], copy=True)
                    projection_distance_m = np.array(
                        data["projection_distance_m"], copy=True
                    )
                    projection_gate_pass = np.array(
                        data["projection_gate_pass"], copy=True
                    )
                except KeyError as exc:
                    raise CacheIntegrityError(
                        f"Cache file {path} is missing array: {exc}"
                    ) from exc
    except (CacheIdentityMismatchError, CacheIntegrityError):
        raise
    except (ValueError, OSError, IOError, EOFError, zipfile.BadZipFile) as exc:
        raise CacheIntegrityError(
            f"Failed to load cache file: {path}: {exc}"
        ) from exc

    _validate_cache_arrays(
        projected_xyz=projected_xyz,
        triangle_id=triangle_id,
        raw_normal=raw_normal,
        projection_distance_m=projection_distance_m,
        projection_gate_pass=projection_gate_pass,
        manifest=manifest,
    )

    content_checks = (
        ("projected_xyz_sha256", projected_xyz),
        ("triangle_id_sha256", triangle_id),
        ("raw_normal_sha256", raw_normal),
        ("projection_distance_m_sha256", projection_distance_m),
        ("projection_gate_pass_sha256", projection_gate_pass),
    )
    for key, arr in content_checks:
        expected_hash = manifest.get(key)
        actual_hash = _sha256_ndarray(arr)
        if expected_hash != actual_hash:
            raise CacheIntegrityError(
                f"Cache {key} content hash mismatch:\n"
                f"  expected: {expected_hash}\n"
                f"  actual:   {actual_hash}"
            )

    if triangle_count is not None:
        try:
            validated_triangle_count = int(triangle_count)
        except (TypeError, ValueError) as exc:
            raise CacheIntegrityError("triangle_count must be a positive integer") from exc
        if validated_triangle_count <= 0:
            raise CacheIntegrityError("triangle_count must be a positive integer")
        if np.any(triangle_id >= validated_triangle_count):
            raise CacheIntegrityError(
                "triangle_id contains index outside triangle mesh bounds"
            )

    return CachedProjection(
        projected_xyz=projected_xyz,
        triangle_id=triangle_id,
        raw_normal=raw_normal,
        projection_distance_m=projection_distance_m,
        projection_gate_pass=projection_gate_pass,
        manifest=manifest,
    )


# ---------------------------------------------------------------------------
# Convenience: build identity hashes from source files
# ---------------------------------------------------------------------------


def build_geometry_identity(
    *,
    fluent_geometry_source_path: str | Path,
    fluent_canonical_geometry_sha256: str,
    canonical_point_count: int,
    x_offset_m: float,
    stl_path: str | Path,
    triangles: np.ndarray,
    vehicle_spec_path: str | Path,
    sampling_spec_path: str | Path,
    outline_path: str | Path | None = None,
    projection_gate_m: float = 0.005,
) -> dict[str, Any]:
    """Build a complete geometry identity dict from source files.

    This is a convenience wrapper that hashes all source files and constructs
    the full identity dictionary needed by ``load_projection_cache`` and
    ``build_cache_manifest``.
    """
    return {
        "fluent_source_geometry_sha256": _sha256_geometry_csv(
            fluent_geometry_source_path
        ),
        "fluent_canonical_geometry_sha256": str(fluent_canonical_geometry_sha256),
        "canonical_point_count": int(canonical_point_count),
        "x_offset_m": float(x_offset_m),
        "stl_raw_sha256": _sha256_file(stl_path),
        "triangle_canonical_sha256": _sha256_triangles(triangles),
        "vehicle_spec_raw_sha256": _sha256_file(vehicle_spec_path),
        "sampling_spec_raw_sha256": _sha256_file(sampling_spec_path),
        "outline_geometry_sha256": (
            _sha256_file(outline_path) if outline_path is not None
            else _sha256_text("no-outline")
        ),
        "projection_gate_m": float(projection_gate_m),
    }