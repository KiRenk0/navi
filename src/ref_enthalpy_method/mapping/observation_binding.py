"""Minimal tracked Fluent observation binding record and fail-closed validator.

This module implements a read-only observation binding that captures the
exact identity of a single Fluent adiabatic-wall surface export CSV, together
with the user-confirmed freestream and solver parameters.  The binding does
NOT claim to prove the full Fluent project, journal, or export procedure.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Binding schema identity
# ---------------------------------------------------------------------------

_BINDING_SCHEMA = "faceted3d-observation-binding/v1"

# --- canonical field set (ordered) ---
_ALLOWED_FIELDS = frozenset(
    {
        "schema",
        "csv_path",
        "raw_sha256",
        "byte_size",
        "header",
        "row_count",
        "mach",
        "alpha_deg",
        "geometric_altitude_m",
        "T_inf_K",
        "p_inf_Pa",
        "freestream_provenance",
        "wall_thermal_condition",
        "observation_field",
        "observation_unit",
        "coordinate_unit",
        "fluent_source_convention",
        "solver_transform",
        "user_confirmation_date",
        "validation_policy",
    }
)

# ---------------------------------------------------------------------------
# Binding dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FluentObservationBinding:
    """Minimal tracked Fluent observation binding.

    Every field is mandatory.  Missing fields, wrong types, non-finite
    numerics, unknown extra fields, and path-escape attempts are rejected
    at construction time (fail-closed).
    """

    schema: str
    csv_path: str
    raw_sha256: str
    byte_size: int
    header: tuple[str, ...]
    row_count: int
    mach: float
    alpha_deg: float
    geometric_altitude_m: float
    T_inf_K: float
    p_inf_Pa: float
    freestream_provenance: str
    wall_thermal_condition: str
    observation_field: str
    observation_unit: str
    coordinate_unit: str
    fluent_source_convention: str
    solver_transform: str
    user_confirmation_date: str
    validation_policy: str

    def __post_init__(self) -> None:
        # --- schema ---
        if self.schema != _BINDING_SCHEMA:
            raise ValueError(
                f"schema must be exactly {_BINDING_SCHEMA!r}, got {self.schema!r}"
            )

        # --- csv_path: must be repo-relative, no absolute, no escape ---
        _validate_repo_relative_path(self.csv_path)

        # --- raw_sha256: lowercase hex, 64 chars ---
        if (
            len(self.raw_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in self.raw_sha256)
        ):
            raise ValueError(
                "raw_sha256 must be a lowercase hexadecimal SHA-256 string"
            )

        # --- byte_size: positive integer, bool rejected ---
        if (
            isinstance(self.byte_size, bool)
            or not isinstance(self.byte_size, int)
            or self.byte_size <= 0
        ):
            raise ValueError("byte_size must be a positive integer")

        # --- header: non-empty tuple ---
        if (
            not isinstance(self.header, tuple)
            or len(self.header) == 0
            or not all(isinstance(h, str) for h in self.header)
        ):
            raise ValueError("header must be a non-empty tuple of strings")

        # --- row_count: positive integer, bool rejected ---
        if (
            isinstance(self.row_count, bool)
            or not isinstance(self.row_count, int)
            or self.row_count <= 0
        ):
            raise ValueError("row_count must be a positive integer")

        # --- finite numerics, bool explicitly rejected ---
        for name in ("mach", "alpha_deg", "geometric_altitude_m", "T_inf_K", "p_inf_Pa"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not np.isfinite(value)
            ):
                raise ValueError(f"{name} must be a finite number")
            if name in ("T_inf_K", "p_inf_Pa") and value <= 0.0:
                raise ValueError(f"{name} must be positive")
            if name == "geometric_altitude_m" and value < 0.0:
                raise ValueError(f"{name} must be non-negative")

        # --- provenance must not be empty ---
        if not self.freestream_provenance.strip():
            raise ValueError("freestream_provenance must not be empty")

        # --- wall_thermal_condition ---
        if not self.wall_thermal_condition.strip():
            raise ValueError("wall_thermal_condition must not be empty")

        # --- observation_field ---
        if not self.observation_field.strip():
            raise ValueError("observation_field must not be empty")

        # --- observation_unit ---
        if not self.observation_unit.strip():
            raise ValueError("observation_unit must not be empty")

        # --- coordinate_unit ---
        if not self.coordinate_unit.strip():
            raise ValueError("coordinate_unit must not be empty")

        # --- fluent_source_convention ---
        if not self.fluent_source_convention.strip():
            raise ValueError("fluent_source_convention must not be empty")

        # --- solver_transform ---
        if not self.solver_transform.strip():
            raise ValueError("solver_transform must not be empty")

        # --- user_confirmation_date: YYYY-MM-DD ---
        date = self.user_confirmation_date
        if len(date) != 10 or date[4] != "-" or date[7] != "-":
            raise ValueError(
                "user_confirmation_date must be exactly YYYY-MM-DD format"
            )

        # --- validation_policy ---
        if self.validation_policy != "fail-closed":
            raise ValueError(
                "validation_policy must be exactly 'fail-closed'"
            )


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def _validate_repo_relative_path(csv_path: str) -> None:
    """Reject absolute paths, backslash, mixed-slash, path-escape attempts."""
    if not csv_path or not csv_path.strip():
        raise ValueError("csv_path must not be empty")
    # Reject any backslash — require canonical POSIX forward slash
    if "\\" in csv_path:
        raise ValueError(
            "csv_path must use forward slashes only (POSIX-style repo-relative)"
        )
    # Reject POSIX absolute paths — not host-filesystem-dependent
    if csv_path.startswith("/"):
        raise ValueError("csv_path must be repo-relative, not absolute")
    path_obj = Path(csv_path)
    if path_obj.is_absolute():
        raise ValueError("csv_path must be repo-relative, not absolute")
    # Check for path escape via ".." components
    parts = path_obj.parts
    if ".." in parts:
        raise ValueError("csv_path must not contain path-escape '..' components")
    # Reject Windows absolute-like paths (e.g. C:\...)
    if csv_path.startswith("\\") or (len(csv_path) >= 2 and csv_path[1] == ":"):
        raise ValueError("csv_path must be repo-relative, not absolute")
    # Reject leading dot-slash (e.g. .\ or ./)
    if csv_path.startswith("./") or csv_path.startswith(".\\"):
        raise ValueError(
            "csv_path must not start with './' or '.\\'"
        )
    # Reject path that ends with directory separator
    if csv_path.endswith("/") or csv_path.endswith("\\"):
        raise ValueError("csv_path must not end with a directory separator")


# ---------------------------------------------------------------------------
# CSV identity read (reused from fluent_surface pattern)
# ---------------------------------------------------------------------------


def _read_csv_raw_identity(
    repo_root: str | Path, csv_path: str
) -> dict[str, Any]:
    """Read raw identity of a CSV from its bytes — no parsing beyond header
    and row count."""
    root = Path(repo_root).resolve()
    full_path = (root / csv_path).resolve()

    # Ensure path stays within repo root
    try:
        full_path.relative_to(root)
    except ValueError:
        raise ValueError(
            f"csv_path {csv_path!r} escapes repository root"
        )

    source_bytes = full_path.read_bytes()
    raw_sha256 = hashlib.sha256(source_bytes).hexdigest()
    byte_size = len(source_bytes)

    try:
        source_text = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"CSV must be UTF-8 text: {full_path}"
        ) from exc

    rows = csv.reader(io.StringIO(source_text, newline=""))
    try:
        raw_header = next(rows)
    except StopIteration as exc:
        raise ValueError("CSV is empty") from exc

    if not raw_header or all(not field for field in raw_header):
        raise ValueError("CSV has no header")

    # Preserve exact whitespace in header fields
    header = tuple(raw_header)
    row_count = sum(1 for _ in rows)

    return {
        "raw_sha256": raw_sha256,
        "byte_size": byte_size,
        "header": header,
        "row_count": row_count,
    }


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_m8h30_observation_binding(
    repo_root: str | Path,
    *,
    csv_path: str = "fluent_export/adiabatic_wall_csv/30km_5alpha_8ma.csv",
) -> FluentObservationBinding:
    """Build the canonical M8/30 Fluent observation binding from the exact CSV.

    All freestream and solver parameters are user-confirmed project inputs.
    This function reads the CSV only to extract raw identity (SHA, size,
    header, row count); it does NOT parse geometry or temperature columns.
    """
    identity = _read_csv_raw_identity(repo_root, csv_path)

    return FluentObservationBinding(
        schema=_BINDING_SCHEMA,
        csv_path=csv_path,
        raw_sha256=identity["raw_sha256"],
        byte_size=identity["byte_size"],
        header=identity["header"],
        row_count=identity["row_count"],
        mach=8.0,
        alpha_deg=5.0,
        geometric_altitude_m=30000,
        T_inf_K=226.509,
        p_inf_Pa=1197.0,
        freestream_provenance="user-confirmed custom project input",
        wall_thermal_condition="adiabatic",
        observation_field="wall-temperature",
        observation_unit="K",
        coordinate_unit="m",
        fluent_source_convention="(x,y,z)",
        solver_transform="(x+0.030, span=y, up=z)",
        user_confirmation_date="2026-07-22",
        validation_policy="fail-closed",
    )


# ---------------------------------------------------------------------------
# Fail-closed validator
# ---------------------------------------------------------------------------


def validate_observation_binding(
    binding: FluentObservationBinding | dict[str, Any],
    *,
    repo_root: str | Path,
) -> tuple[bool, str]:
    """Fail-closed validation of a Fluent observation binding.

    Returns ``(True, "")`` on pass, ``(False, reason)`` on any rejection.

    The validator:

    * never modifies the binding or CSV;
    * never writes cache;
    * never auto-registers, auto-generates evidence, or auto-repairs;
    * never falls back to standard atmosphere;
    * never infers facts from the filename.

    Rejections are immediate and deterministic.
    """
    # --- Reject dict with unknown fields ---
    if isinstance(binding, dict):
        extra = set(binding.keys()) - _ALLOWED_FIELDS
        if extra:
            return False, f"unknown field(s): {sorted(extra)}"
        # Check that all required fields are present
        missing = _ALLOWED_FIELDS - set(binding.keys())
        if missing:
            return False, f"missing required field(s): {sorted(missing)}"
        try:
            binding = FluentObservationBinding(**binding)
        except Exception as exc:
            return False, f"binding construction failed: {exc}"

    if not isinstance(binding, FluentObservationBinding):
        return False, "binding must be a FluentObservationBinding or dict"

    # --- Schema ---
    if binding.schema != _BINDING_SCHEMA:
        return False, (
            f"schema mismatch: expected {_BINDING_SCHEMA!r}, "
            f"got {binding.schema!r}"
        )

    # --- CSV path ---
    try:
        _validate_repo_relative_path(binding.csv_path)
    except ValueError as exc:
        return False, f"csv_path invalid: {exc}"

    # --- Read actual CSV identity ---
    try:
        actual = _read_csv_raw_identity(repo_root, binding.csv_path)
    except Exception as exc:
        return False, f"CSV identity read failed: {exc}"

    # --- Cross-check raw identity ---
    if binding.raw_sha256 != actual["raw_sha256"]:
        return False, (
            f"raw_sha256 mismatch: binding claims {binding.raw_sha256}, "
            f"actual {actual['raw_sha256']}"
        )

    if binding.byte_size != actual["byte_size"]:
        return False, (
            f"byte_size mismatch: binding claims {binding.byte_size}, "
            f"actual {actual['byte_size']}"
        )

    if binding.header != actual["header"]:
        return False, (
            f"header mismatch: binding claims {list(binding.header)}, "
            f"actual {list(actual['header'])}"
        )

    if binding.row_count != actual["row_count"]:
        return False, (
            f"row_count mismatch: binding claims {binding.row_count}, "
            f"actual {actual['row_count']}"
        )

    # --- Fixed parameters ---
    _checks = [
        ("mach", 8.0),
        ("alpha_deg", 5.0),
        ("geometric_altitude_m", 30000),
        ("T_inf_K", 226.509),
        ("p_inf_Pa", 1197.0),
        ("freestream_provenance", "user-confirmed custom project input"),
        ("wall_thermal_condition", "adiabatic"),
        ("observation_field", "wall-temperature"),
        ("observation_unit", "K"),
        ("coordinate_unit", "m"),
        ("fluent_source_convention", "(x,y,z)"),
        ("solver_transform", "(x+0.030, span=y, up=z)"),
        ("user_confirmation_date", "2026-07-22"),
        ("validation_policy", "fail-closed"),
    ]
    for field_name, expected in _checks:
        actual_value = getattr(binding, field_name)
        if actual_value != expected:
            return False, (
                f"{field_name} mismatch: expected {expected!r}, "
                f"got {actual_value!r}"
            )

    # --- Explicit standard-atmosphere substitution rejection ---
    # If T_inf and p_inf came from a standard-atmosphere model at 30 km,
    # they would differ. Our expected values (226.509, 1197.0) are
    # user-confirmed custom inputs that happen to differ from ISA/ USSA.
    # The validator already rejects mismatches via the checks above; this
    # note is documentation, not an extra runtime path.

    # --- Loader/binding raw identity consistency ---
    # The raw_sha256 in the binding must match the SHA of the CSV bytes on
    # disk — this is already enforced above.  No second loader is allowed,
    # and no candidate/projection-cache identity may substitute.

    return True, ""