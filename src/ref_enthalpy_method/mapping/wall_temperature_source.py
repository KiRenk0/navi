"""Strict source-order reader for adiabatic-wall-temperature observations."""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

import numpy as np


def read_fluent_wall_temperature_source(csv_path: str | Path) -> tuple[np.ndarray, str]:
    """Return positive finite wall temperatures and the raw-file SHA-256."""
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
    matches = [index for index, name in enumerate(header) if name.strip() == "wall-temperature"]
    if len(matches) != 1:
        raise ValueError("wall-temperature column must exist exactly once")
    column_index = matches[0]
    temperatures: list[np.float64] = []
    for line_number, row in enumerate(rows, start=2):
        if column_index >= len(row) or not row[column_index].strip():
            raise ValueError(f"missing wall-temperature value at CSV line {line_number}")
        try:
            value = np.float64(row[column_index].strip())
        except ValueError as error:
            raise ValueError(f"non-numeric wall-temperature value at CSV line {line_number}") from error
        if not np.isfinite(value) or value <= 0.0:
            raise ValueError(f"wall-temperature must be finite and greater than zero K at CSV line {line_number}")
        temperatures.append(value)
    result = np.array(temperatures, dtype=np.float64, copy=True, order="C")
    result.setflags(write=False)
    return result, source_sha256
