"""Explicit graph-skin topology for the N8 Taw product."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .stl_surface import AsciiStlMesh


@dataclass(frozen=True)
class N8DomainTopology:
    node_x_m: np.ndarray
    node_span_m: np.ndarray
    node_x_over_c: np.ndarray
    node_y_over_b: np.ndarray
    parameter_row: np.ndarray
    parameter_column: np.ndarray
    legacy_phase9_canonical_index: np.ndarray
    domain_role: np.ndarray
    source_stl_triangle_id: np.ndarray
    source_stl_edge_id: np.ndarray
    interpolation_legacy_indices: np.ndarray
    interpolation_weights: np.ndarray
    triangle_node_ids: np.ndarray
    triangle_source_stl_triangle_id: np.ndarray


def _signed_area(polygon: np.ndarray) -> float:
    points = np.asarray(polygon, dtype=np.float64)
    return 0.5 * float(
        np.sum(
            points[:, 0] * np.roll(points[:, 1], -1)
            - points[:, 1] * np.roll(points[:, 0], -1)
        )
    )


def _line_intersection(
    first: np.ndarray,
    second: np.ndarray,
    clip_first: np.ndarray,
    clip_second: np.ndarray,
) -> np.ndarray:
    direction = second - first
    clip_direction = clip_second - clip_first
    denominator = float(
        direction[0] * clip_direction[1] - direction[1] * clip_direction[0]
    )
    if abs(denominator) <= 1.0e-18:
        return np.asarray(0.5 * (first + second), dtype=np.float64)
    offset = clip_first - first
    fraction = float(
        (offset[0] * clip_direction[1] - offset[1] * clip_direction[0])
        / denominator
    )
    return np.asarray(first + np.clip(fraction, 0.0, 1.0) * direction)


def clip_polygon_to_triangle(
    polygon: np.ndarray,
    triangle: np.ndarray,
    *,
    tolerance: float = 1.0e-12,
) -> np.ndarray:
    """Clip a convex polygon to a projected triangle."""

    result = np.asarray(polygon, dtype=np.float64)
    clipper = np.asarray(triangle, dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != 2:
        raise ValueError("polygon must have shape (N, 2)")
    if clipper.shape != (3, 2):
        raise ValueError("triangle must have shape (3, 2)")
    orientation = 1.0 if _signed_area(clipper) >= 0.0 else -1.0
    for edge_index in range(3):
        if result.size == 0:
            break
        edge_first = clipper[edge_index]
        edge_second = clipper[(edge_index + 1) % 3]

        def inside(
            point: np.ndarray,
            first: np.ndarray = edge_first,
            second: np.ndarray = edge_second,
        ) -> bool:
            cross = float(
                (second[0] - first[0]) * (point[1] - first[1])
                - (second[1] - first[1]) * (point[0] - first[0])
            )
            return orientation * cross >= -float(tolerance)

        clipped: list[np.ndarray] = []
        previous = result[-1]
        previous_inside = inside(previous)
        for current in result:
            current_inside = inside(current)
            if current_inside != previous_inside:
                clipped.append(
                    _line_intersection(previous, current, edge_first, edge_second)
                )
            if current_inside:
                clipped.append(np.asarray(current, dtype=np.float64))
            previous = current
            previous_inside = current_inside
        result = (
            np.asarray(clipped, dtype=np.float64).reshape(-1, 2)
            if clipped
            else np.empty((0, 2), dtype=np.float64)
        )
    if result.shape[0] > 1:
        keep = np.ones(result.shape[0], dtype=np.bool_)
        keep[1:] = np.linalg.norm(np.diff(result, axis=0), axis=1) > tolerance
        result = result[keep]
        if result.shape[0] > 1 and np.linalg.norm(result[0] - result[-1]) <= tolerance:
            result = result[:-1]
    return result


def _barycentric(point: np.ndarray, triangle: np.ndarray) -> np.ndarray:
    matrix = np.column_stack(
        (triangle[1] - triangle[0], triangle[2] - triangle[0])
    )
    determinant = float(np.linalg.det(matrix))
    if abs(determinant) <= 1.0e-18:
        return np.full(3, np.nan, dtype=np.float64)
    second, third = np.linalg.solve(matrix, point - triangle[0])
    return np.asarray([1.0 - second - third, second, third], dtype=np.float64)


def _edge_key(
    first: np.ndarray, second: np.ndarray
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    endpoints = sorted(
        (
            tuple(np.round(first, 12).tolist()),
            tuple(np.round(second, 12).tolist()),
        )
    )
    return endpoints[0], endpoints[1]


def _sheet_edge_metadata(
    mesh: AsciiStlMesh,
    triangle_sheet: np.ndarray,
    sheet_code: int,
) -> tuple[np.ndarray, dict[int, list[tuple[int, np.ndarray, np.ndarray]]]]:
    triangles = np.stack((mesh.v0, mesh.v1, mesh.v2), axis=1)
    sheets = np.asarray(triangle_sheet, dtype=np.int8)
    edge_owners: dict[
        tuple[tuple[float, float, float], tuple[float, float, float]], list[int]
    ] = {}
    for triangle_id, vertices in enumerate(triangles):
        for first, second in ((0, 1), (1, 2), (2, 0)):
            edge_owners.setdefault(
                _edge_key(vertices[first], vertices[second]), []
            ).append(triangle_id)

    edge_ids = {key: index for index, key in enumerate(sorted(edge_owners))}
    boundary_by_triangle: dict[int, list[tuple[int, np.ndarray, np.ndarray]]] = {}
    for key, owners in edge_owners.items():
        sheet_owners = [owner for owner in owners if int(sheets[owner]) == sheet_code]
        if len(sheet_owners) != 1:
            continue
        owner = int(sheet_owners[0])
        boundary_by_triangle.setdefault(owner, []).append(
            (
                int(edge_ids[key]),
                np.asarray(key[0][:2], dtype=np.float64),
                np.asarray(key[1][:2], dtype=np.float64),
            )
        )

    parent = np.arange(triangles.shape[0], dtype=np.int64)

    def find(index: int) -> int:
        while int(parent[index]) != index:
            parent[index] = parent[int(parent[index])]
            index = int(parent[index])
        return index

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parent[max(first_root, second_root)] = min(first_root, second_root)

    raw = np.cross(
        triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    )
    magnitude = np.linalg.norm(raw, axis=1)
    normal = np.full_like(raw, np.nan)
    valid = magnitude > 1.0e-12
    normal[valid] = raw[valid] / magnitude[valid, None]
    cosine_limit = float(np.cos(np.deg2rad(20.0)))
    for owners in edge_owners.values():
        sheet_owners = [owner for owner in owners if int(sheets[owner]) == sheet_code]
        if len(sheet_owners) != 2:
            continue
        first, second = map(int, sheet_owners)
        if float(abs(np.dot(normal[first], normal[second]))) >= cosine_limit:
            union(first, second)
    smooth_group = np.asarray([find(index) for index in range(len(parent))])
    return smooth_group, boundary_by_triangle


def _point_on_segment(
    point: np.ndarray,
    first: np.ndarray,
    second: np.ndarray,
    *,
    tolerance: float = 2.0e-10,
) -> bool:
    direction = second - first
    length = float(np.linalg.norm(direction))
    if length <= tolerance:
        return float(np.linalg.norm(point - first)) <= tolerance
    cross = abs(
        float(
            direction[0] * (point[1] - first[1])
            - direction[1] * (point[0] - first[0])
        )
    )
    if cross > tolerance * length:
        return False
    projection = float(np.dot(point - first, direction) / (length * length))
    return -tolerance <= projection <= 1.0 + tolerance


def build_n8_domain_topology(
    *,
    x_m: np.ndarray,
    span_m: np.ndarray,
    x_over_c: np.ndarray,
    y_over_b: np.ndarray,
    geometry_valid: np.ndarray,
    legacy_source_stl_triangle_id: np.ndarray,
    mesh: AsciiStlMesh,
    triangle_sheet: np.ndarray,
    sheet_code: int,
    legacy_sheet_offset: int,
) -> N8DomainTopology:
    """Intersect the structured sampling mesh with one authoritative STL sheet."""

    x = np.asarray(x_m, dtype=np.float64)
    span = np.asarray(span_m, dtype=np.float64)
    xc = np.asarray(x_over_c, dtype=np.float64)
    yb = np.asarray(y_over_b, dtype=np.float64)
    geometry = np.asarray(geometry_valid, dtype=np.bool_)
    legacy_source = np.asarray(legacy_source_stl_triangle_id, dtype=np.int64)
    if x.ndim != 2 or not (
        x.shape == span.shape == xc.shape == yb.shape == geometry.shape
        == legacy_source.shape
    ):
        raise ValueError("structured parameter grids must be matching 2D arrays")
    sheets = np.asarray(triangle_sheet, dtype=np.int8)
    if sheets.shape != (mesh.v0.shape[0],):
        raise ValueError("triangle_sheet must have one code per STL triangle")

    stl_projected = np.stack((mesh.p0, mesh.p1, mesh.p2), axis=1)
    stl_ids = np.flatnonzero(sheets == int(sheet_code)).astype(np.int64)
    if stl_ids.size == 0:
        raise ValueError("requested sheet has no authoritative STL triangles")
    stl_min = np.min(stl_projected[stl_ids], axis=1)
    stl_max = np.max(stl_projected[stl_ids], axis=1)
    smooth_group, boundary_by_triangle = _sheet_edge_metadata(
        mesh, sheets, int(sheet_code)
    )

    ny, nx = x.shape
    structured_triangles: list[tuple[int, int, int]] = []
    for row in range(ny - 1):
        for column in range(nx - 1):
            top_left = row * nx + column
            top_right = top_left + 1
            bottom_left = (row + 1) * nx + column
            bottom_right = bottom_left + 1
            structured_triangles.append((top_left, top_right, bottom_right))
            structured_triangles.append((top_left, bottom_right, bottom_left))

    flat_xy = np.column_stack((x.reshape(-1), span.reshape(-1)))
    flat_xc = xc.reshape(-1)
    flat_yb = yb.reshape(-1)
    flat_geometry = geometry.reshape(-1)
    flat_legacy_source = legacy_source.reshape(-1)
    node_records: list[dict[str, object]] = []
    node_lookup: dict[tuple[float, float, int], int] = {}
    product_triangles: list[tuple[int, int, int]] = []
    product_sources: list[int] = []
    triangle_signatures: set[tuple[int, int, int]] = set()

    for legacy_vertices in structured_triangles:
        legacy = np.asarray(legacy_vertices, dtype=np.int64)
        subject = flat_xy[legacy]
        if not np.all(np.isfinite(subject)) or abs(_signed_area(subject)) <= 1.0e-16:
            continue
        fully_supported = bool(np.all(flat_geometry[legacy]))
        if fully_supported:
            source_candidates = flat_legacy_source[legacy]
            source_candidates = source_candidates[source_candidates >= 0]
            if source_candidates.size == 0:
                raise ValueError("supported structured triangle has no STL source")
            values, counts = np.unique(source_candidates, return_counts=True)
            source_ids = np.asarray(
                [values[np.flatnonzero(counts == np.max(counts))[0]]],
                dtype=np.int64,
            )
        else:
            subject_min = np.min(subject, axis=0)
            subject_max = np.max(subject, axis=0)
            overlap = np.all(stl_max >= subject_min - 1.0e-12, axis=1) & np.all(
                stl_min <= subject_max + 1.0e-12, axis=1
            )
            source_ids = stl_ids[overlap]
        for source_triangle_id in source_ids:
            source_id = int(source_triangle_id)
            polygon = (
                subject.copy()
                if fully_supported
                else clip_polygon_to_triangle(
                    subject, stl_projected[source_id], tolerance=1.0e-12
                )
            )
            if polygon.shape[0] < 3 or abs(_signed_area(polygon)) <= 1.0e-16:
                continue
            polygon_node_ids: list[int] = []
            for point in polygon:
                weights = _barycentric(point, subject)
                if not np.all(np.isfinite(weights)):
                    continue
                direct_candidates = np.flatnonzero(weights >= 1.0 - 2.0e-10)
                direct_local = (
                    int(legacy[int(direct_candidates[0])])
                    if direct_candidates.size
                    else -1
                )
                key = (
                    round(float(point[0]), 12),
                    round(float(point[1]), 12),
                    int(smooth_group[source_id]),
                )
                node_id = node_lookup.get(key)
                if node_id is None:
                    source_edge_id = -1
                    for edge_id, first, second in boundary_by_triangle.get(
                        source_id, []
                    ):
                        if _point_on_segment(point, first, second):
                            source_edge_id = int(edge_id)
                            break
                    node_id = len(node_records)
                    node_lookup[key] = node_id
                    node_records.append(
                        {
                            "x_m": float(point[0]),
                            "span_m": float(point[1]),
                            "x_over_c": float(weights @ flat_xc[legacy]),
                            "y_over_b": float(weights @ flat_yb[legacy]),
                            "parameter_row": (
                                direct_local // nx if direct_local >= 0 else -1
                            ),
                            "parameter_column": (
                                direct_local % nx if direct_local >= 0 else -1
                            ),
                            "legacy_index": (
                                int(legacy_sheet_offset + direct_local)
                                if direct_local >= 0
                                else -1
                            ),
                            "domain_role": (
                                "skin_boundary" if source_edge_id >= 0 else "interior"
                            ),
                            "source_triangle_id": source_id,
                            "source_edge_id": source_edge_id,
                            "interpolation_indices": legacy + int(legacy_sheet_offset),
                            "interpolation_weights": weights,
                        }
                    )
                polygon_node_ids.append(node_id)
            if len(polygon_node_ids) < 3:
                continue
            for index in range(1, len(polygon_node_ids) - 1):
                triangle = (
                    polygon_node_ids[0],
                    polygon_node_ids[index],
                    polygon_node_ids[index + 1],
                )
                coordinates = np.asarray(
                    [
                        [node_records[node]["x_m"], node_records[node]["span_m"]]
                        for node in triangle
                    ],
                    dtype=np.float64,
                )
                if abs(_signed_area(coordinates)) <= 1.0e-16:
                    continue
                signature = tuple(sorted(triangle))
                if signature in triangle_signatures:
                    continue
                triangle_signatures.add(signature)
                product_triangles.append(triangle)
                product_sources.append(source_id)

    if not product_triangles:
        raise ValueError("domain clipping produced no product triangles")
    used = np.unique(np.asarray(product_triangles, dtype=np.int64))
    remap = np.full(len(node_records), -1, dtype=np.int64)
    remap[used] = np.arange(used.size, dtype=np.int64)
    records = [node_records[int(index)] for index in used]
    triangles = remap[np.asarray(product_triangles, dtype=np.int64)]

    def array(name: str, dtype: np.dtype | type) -> np.ndarray:
        return np.asarray([record[name] for record in records], dtype=dtype)

    return N8DomainTopology(
        node_x_m=array("x_m", np.float64),
        node_span_m=array("span_m", np.float64),
        node_x_over_c=array("x_over_c", np.float64),
        node_y_over_b=array("y_over_b", np.float64),
        parameter_row=array("parameter_row", np.int64),
        parameter_column=array("parameter_column", np.int64),
        legacy_phase9_canonical_index=array("legacy_index", np.int64),
        domain_role=array("domain_role", "<U16"),
        source_stl_triangle_id=array("source_triangle_id", np.int64),
        source_stl_edge_id=array("source_edge_id", np.int64),
        interpolation_legacy_indices=np.asarray(
            [record["interpolation_indices"] for record in records], dtype=np.int64
        ),
        interpolation_weights=np.asarray(
            [record["interpolation_weights"] for record in records], dtype=np.float64
        ),
        triangle_node_ids=triangles,
        triangle_source_stl_triangle_id=np.asarray(
            product_sources, dtype=np.int64
        ),
    )
