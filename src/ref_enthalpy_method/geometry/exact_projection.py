"""Exact closest-point projection onto triangular surface meshes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_TIE_ABS_TOL = 1.0e-12
_TIE_REL_TOL = 1.0e-12
_DEGENERACY_EPSILON = np.finfo(np.float64).eps


@dataclass(frozen=True)
class TriangleProjection:
    closest_point: np.ndarray
    distance: float
    raw_normal: np.ndarray


@dataclass(frozen=True)
class SurfaceProjection:
    triangle_id: np.ndarray
    closest_point: np.ndarray
    distance: np.ndarray
    raw_normal: np.ndarray


def _finite_float64(value: np.ndarray, *, shape: tuple[int, ...], name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    return array


def _closest_point_on_segment(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    direction = end - start
    length_squared = float(np.dot(direction, direction))
    if length_squared == 0.0:
        return start.copy()
    parameter = float(np.dot(point - start, direction) / length_squared)
    return start + np.clip(parameter, 0.0, 1.0) * direction


def _closest_point_on_degenerate_triangle(point: np.ndarray, triangle: np.ndarray) -> np.ndarray:
    candidates = (
        _closest_point_on_segment(point, triangle[0], triangle[1]),
        _closest_point_on_segment(point, triangle[1], triangle[2]),
        _closest_point_on_segment(point, triangle[2], triangle[0]),
    )
    squared_distances = np.array([np.dot(point - candidate, point - candidate) for candidate in candidates])
    return candidates[int(np.argmin(squared_distances))].copy()


def _closest_point_on_nondegenerate_triangle(point: np.ndarray, triangle: np.ndarray) -> np.ndarray:
    a, b, c = triangle
    ab = b - a
    ac = c - a
    ap = point - a
    d1 = float(np.dot(ab, ap))
    d2 = float(np.dot(ac, ap))
    if d1 <= 0.0 and d2 <= 0.0:
        return a.copy()

    bp = point - b
    d3 = float(np.dot(ab, bp))
    d4 = float(np.dot(ac, bp))
    if d3 >= 0.0 and d4 <= d3:
        return b.copy()

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        parameter = d1 / (d1 - d3)
        return a + parameter * ab

    cp = point - c
    d5 = float(np.dot(ab, cp))
    d6 = float(np.dot(ac, cp))
    if d6 >= 0.0 and d5 <= d6:
        return c.copy()

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        parameter = d2 / (d2 - d6)
        return a + parameter * ac

    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        parameter = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return b + parameter * (c - b)

    denominator = 1.0 / (va + vb + vc)
    barycentric_b = vb * denominator
    barycentric_c = vc * denominator
    return a + ab * barycentric_b + ac * barycentric_c


def closest_point_on_triangle(point: np.ndarray, triangle: np.ndarray) -> TriangleProjection:
    """Project one point exactly onto one triangle, including degenerate triangles."""

    point_array = _finite_float64(point, shape=(3,), name="point")
    triangle_array = _finite_float64(triangle, shape=(3, 3), name="triangle")

    edge_ab = triangle_array[1] - triangle_array[0]
    edge_ac = triangle_array[2] - triangle_array[0]
    normal = np.cross(edge_ab, edge_ac)
    normal_norm = float(np.linalg.norm(normal))
    scale_squared = max(float(np.dot(edge_ab, edge_ab)), float(np.dot(edge_ac, edge_ac)))
    degenerate = scale_squared == 0.0 or normal_norm <= _DEGENERACY_EPSILON * scale_squared

    if degenerate:
        closest = _closest_point_on_degenerate_triangle(point_array, triangle_array)
        raw_normal = np.full(3, np.nan, dtype=np.float64)
    else:
        closest = _closest_point_on_nondegenerate_triangle(point_array, triangle_array)
        raw_normal = normal / normal_norm

    distance = float(np.linalg.norm(point_array - closest))
    return TriangleProjection(closest_point=closest, distance=distance, raw_normal=raw_normal)


def _distances_equivalent(left: float, right: float) -> bool:
    tolerance = _TIE_ABS_TOL + _TIE_REL_TOL * max(abs(left), abs(right))
    return abs(left - right) <= tolerance


def project_points_exact(points: np.ndarray, triangles: np.ndarray) -> SurfaceProjection:
    """Project every point by exhaustive search over every triangle in index order."""

    points_array = np.asarray(points, dtype=np.float64)
    triangles_array = np.asarray(triangles, dtype=np.float64)
    if points_array.ndim != 2 or points_array.shape[1:] != (3,):
        raise ValueError(f"points must have shape (N, 3), got {points_array.shape}")
    if triangles_array.ndim != 3 or triangles_array.shape[1:] != (3, 3):
        raise ValueError(f"triangles must have shape (M, 3, 3), got {triangles_array.shape}")
    if triangles_array.shape[0] == 0:
        raise ValueError("triangles must contain at least one triangle")
    if not np.all(np.isfinite(points_array)):
        raise ValueError("points must contain only finite values")
    if not np.all(np.isfinite(triangles_array)):
        raise ValueError("triangles must contain only finite values")

    count = points_array.shape[0]
    triangle_ids = np.empty(count, dtype=np.int64)
    closest_points = np.empty((count, 3), dtype=np.float64)
    distances = np.empty(count, dtype=np.float64)
    raw_normals = np.empty((count, 3), dtype=np.float64)

    for point_id, point in enumerate(points_array):
        best_id = 0
        best = closest_point_on_triangle(point, triangles_array[0])
        for triangle_id in range(1, triangles_array.shape[0]):
            candidate = closest_point_on_triangle(point, triangles_array[triangle_id])
            if candidate.distance < best.distance and not _distances_equivalent(candidate.distance, best.distance):
                best_id = triangle_id
                best = candidate
        triangle_ids[point_id] = best_id
        closest_points[point_id] = best.closest_point
        distances[point_id] = best.distance
        raw_normals[point_id] = best.raw_normal

    return SurfaceProjection(
        triangle_id=triangle_ids,
        closest_point=closest_points,
        distance=distances,
        raw_normal=raw_normals,
    )