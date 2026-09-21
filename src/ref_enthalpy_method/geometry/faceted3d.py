"""Geometry inputs used by the formal 0920 Taw calculation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Faceted3DConfig:
    """Single-authority direct-slope and source-geometry configuration."""

    slope_x_up: float
    slope_y_up: float
    slope_x_lo: float
    slope_y_lo: float
    chord_min_m: float
    outline_csv_path: str
    outline_x_col: str
    outline_span_col: str
    outline_span_sign: float
    surface_stl_path: str
    stl_unit: str
    stl_span_sign: float
    stl_right_half_only: bool
    edge_use_effective_alpha: bool
    edge_use_effective_mach: bool
    cp_newtonian_A: float
    cp_newtonian_n: float

    @classmethod
    def from_faceted3d_spec(cls, value: dict) -> Faceted3DConfig:
        if not isinstance(value, dict):
            raise TypeError("faceted3d spec must be a mapping")
        expected = {
            "sx_up",
            "sy_up",
            "sx_lo",
            "sy_lo",
            "edge_state",
            "cp_model",
            "cp_newtonian_A",
            "cp_newtonian_n",
            "chord_min_m",
            "planform",
            "surface",
        }
        if set(value) != expected:
            raise ValueError(
                "faceted3d fields must be exactly "
                f"{sorted(expected)}; got {sorted(value)}"
            )
        if value["cp_model"] != "newtonian_like":
            raise ValueError("formal 0920 cp_model must be exactly 'newtonian_like'")

        edge_state = value["edge_state"]
        planform = value["planform"]
        surface = value["surface"]
        if not isinstance(edge_state, dict) or set(edge_state) != {
            "use_effective_alpha",
            "use_effective_mach",
        }:
            raise ValueError("faceted3d.edge_state has unexpected fields")
        if not isinstance(planform, dict) or set(planform) != {
            "outline_csv",
            "outline_x_col",
            "outline_span_col",
            "outline_span_sign",
        }:
            raise ValueError("faceted3d.planform has unexpected fields")
        if not isinstance(surface, dict) or set(surface) != {
            "stl",
            "unit",
            "span_sign",
            "right_half_only",
        }:
            raise ValueError("faceted3d.surface has unexpected fields")

        result = cls(
            slope_x_up=float(value["sx_up"]),
            slope_y_up=float(value["sy_up"]),
            slope_x_lo=float(value["sx_lo"]),
            slope_y_lo=float(value["sy_lo"]),
            chord_min_m=float(value["chord_min_m"]),
            outline_csv_path=str(planform["outline_csv"]),
            outline_x_col=str(planform["outline_x_col"]),
            outline_span_col=str(planform["outline_span_col"]),
            outline_span_sign=float(planform["outline_span_sign"]),
            surface_stl_path=str(surface["stl"]),
            stl_unit=str(surface["unit"]),
            stl_span_sign=float(surface["span_sign"]),
            stl_right_half_only=bool(surface["right_half_only"]),
            edge_use_effective_alpha=bool(edge_state["use_effective_alpha"]),
            edge_use_effective_mach=bool(edge_state["use_effective_mach"]),
            cp_newtonian_A=float(value["cp_newtonian_A"]),
            cp_newtonian_n=float(value["cp_newtonian_n"]),
        )
        numeric = np.asarray(
            (
                result.slope_x_up,
                result.slope_y_up,
                result.slope_x_lo,
                result.slope_y_lo,
                result.chord_min_m,
                result.outline_span_sign,
                result.stl_span_sign,
                result.cp_newtonian_A,
                result.cp_newtonian_n,
            ),
            dtype=float,
        )
        if not np.all(np.isfinite(numeric)) or result.chord_min_m <= 0.0:
            raise ValueError("faceted3d numeric fields must be finite and chord_min_m positive")
        if not result.outline_csv_path or not result.surface_stl_path:
            raise ValueError("formal 0920 outline and STL paths are required")
        return result

    def slopes(self) -> tuple[float, float, float, float]:
        return (
            self.slope_x_up,
            self.slope_y_up,
            self.slope_x_lo,
            self.slope_y_lo,
        )


def load_outline_csv(
    *,
    csv_path: str | Path,
    x_col: str = "x_m",
    span_col: str = "y_m",
    span_sign: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Load the required 0920 half-planform outline in metres."""
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"required 0920 outline not found: {path}")
    data = np.genfromtxt(path, delimiter=",", names=True, dtype=float, encoding="utf-8")
    if data is None or getattr(data, "dtype", None) is None or data.dtype.names is None:
        raise ValueError(f"failed to parse 0920 outline CSV: {path}")
    names = {str(name) for name in data.dtype.names}
    if x_col not in names or span_col not in names:
        raise KeyError(
            f"outline CSV missing columns; have={sorted(names)}, need=({x_col},{span_col})"
        )
    x = np.asarray(data[x_col], dtype=float).reshape(-1)
    span = np.asarray(data[span_col], dtype=float).reshape(-1) * float(span_sign)
    finite = np.isfinite(x) & np.isfinite(span)
    x = x[finite]
    span = span[finite]
    if x.size < 3:
        raise ValueError(f"0920 outline CSV is too short: {path}")
    return x, span


def _close_polyline(
    x: np.ndarray, span: np.ndarray, tol: float = 1e-9
) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float).reshape(-1)
    span = np.asarray(span, dtype=float).reshape(-1)
    if x.size != span.size or x.size < 3:
        raise ValueError("outline coordinates must have equal length of at least three")
    if abs(float(x[0]) - float(x[-1])) <= tol and abs(
        float(span[0]) - float(span[-1])
    ) <= tol:
        return x, span
    return np.concatenate([x, x[:1]]), np.concatenate([span, span[:1]])


def outline_planform_xle_chord(
    *,
    span_m: float,
    outline_x_m: np.ndarray,
    outline_span_m: np.ndarray,
) -> tuple[float, float]:
    """Resolve leading edge and chord from the required 0920 outline."""
    y_m = float(span_m)
    if not np.isfinite(y_m):
        return float("nan"), float("nan")
    x, span = _close_polyline(outline_x_m, outline_span_m)
    y_min = float(np.nanmin(span))
    y_max = float(np.nanmax(span))
    if not (y_min - 1e-9 <= y_m <= y_max + 1e-9):
        return float("nan"), float("nan")
    epsilon = max(1e-9, 1e-6 * abs(y_max - y_min))
    y_eval = min(max(y_m, y_min + epsilon), y_max - epsilon)

    intersections: list[float] = []
    for index in range(x.size - 1):
        x0, y0 = float(x[index]), float(span[index])
        x1, y1 = float(x[index + 1]), float(span[index + 1])
        if abs(y1 - y0) < 1e-12 or y_eval < min(y0, y1) or y_eval >= max(y0, y1):
            continue
        fraction = (y_eval - y0) / (y1 - y0)
        if 0.0 <= fraction <= 1.0:
            intersections.append(x0 + fraction * (x1 - x0))
    finite = np.asarray(intersections, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size < 2:
        return float("nan"), float("nan")
    x_le = float(np.min(finite))
    return x_le, float(np.max(finite) - x_le)
