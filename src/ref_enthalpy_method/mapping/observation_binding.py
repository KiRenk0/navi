"""Byte identity of a Fluent wall-temperature export.

The flow condition of a run comes from its case spec, never from the export
filename, so any export path (for example ``fenqu1/fenqu1.csv``) is accepted.
The binding records what was read: SHA-256, byte size, header and row count.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_BINDING_SCHEMA = "taw-observation-binding/v2"


@dataclass(frozen=True)
class FluentObservationBinding:
    schema: str
    csv_path: str
    raw_sha256: str
    byte_size: int
    header: tuple[str, ...]
    row_count: int


def _validate_repo_relative_path(csv_path: str) -> None:
    if not isinstance(csv_path, str) or not csv_path or csv_path.strip() != csv_path:
        raise ValueError("csv_path must be a non-empty canonical string")
    if "\\" in csv_path or csv_path.startswith("/") or (len(csv_path) >= 2 and csv_path[1] == ":"):
        raise ValueError("csv_path must be POSIX-style and repo-relative")
    path = PurePosixPath(csv_path)
    if ".." in path.parts or "." in path.parts:
        raise ValueError("csv_path must not contain dot components")
    if path.suffix != ".csv":
        raise ValueError("csv_path must identify a CSV file")


def build_observation_binding(repo_root: str | Path, *, csv_path: str) -> FluentObservationBinding:
    _validate_repo_relative_path(csv_path)
    root = Path(repo_root).resolve()
    full_path = (root / PurePosixPath(csv_path)).resolve()
    try:
        full_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"csv_path {csv_path!r} escapes repository root") from exc
    source_bytes = full_path.read_bytes()
    try:
        text = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"CSV must be UTF-8 text: {full_path}") from exc
    rows = csv.reader(io.StringIO(text, newline=""))
    try:
        header = tuple(next(rows))
    except StopIteration as exc:
        raise ValueError("CSV is empty") from exc
    if not header or all(not field for field in header):
        raise ValueError("CSV has no header")
    row_count = sum(1 for _ in rows)
    if row_count <= 0:
        raise ValueError("CSV has no data rows")
    return FluentObservationBinding(
        schema=_BINDING_SCHEMA,
        csv_path=csv_path,
        raw_sha256=hashlib.sha256(source_bytes).hexdigest(),
        byte_size=len(source_bytes),
        header=header,
        row_count=row_count,
    )
