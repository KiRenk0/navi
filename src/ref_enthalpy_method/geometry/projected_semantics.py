"""Pure projected-point geometry semantics independent of Fluent and solver state."""

from __future__ import annotations

from dataclasses import dataclass, fields

import numpy as np

from .faceted3d import outline_planform_xle_chord, triangle_planform_xle_chord
from .local_incidence import (
    INCIDENCE_EPSILON,
    NORMAL_SOURCE_INVALID,
    NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER,
    NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION,
    SURFACE_CLASS_INVALID,
    classify_incidence,
    orient_outward_normal,
)
from .qchain_surface import qchain_stl_acceptance
from .stl_surface import AsciiStlMesh, SurfaceSlopeSampler

GEOMETRIC_SHEET_INVALID = -1
GEOMETRIC_SHEET_OTHER = 0
GEOMETRIC_SHEET_UPPER = 1
GEOMETRIC_SHEET_LOWER = 2


def _readonly(value: np.ndarray, *, dtype: np.dtype | type) -> np.ndarray:
    result = np.array(value, dtype=dtype, copy=True, order="C")
    result.setflags(write=False)
    return result


def _validate_triangles(triangles: np.ndarray) -> np.ndarray:
    result = np.asarray(triangles, dtype=np.float64)
    if result.ndim != 3 or result.shape[1:] != (3, 3) or result.shape[0] == 0:
        raise ValueError("triangles must have shape (M, 3, 3) with M > 0")
    if not np.all(np.isfinite(result)):
        raise ValueError("triangles must contain only finite values")
    return result


def _mesh_from_triangles(triangles: np.ndarray) -> AsciiStlMesh:
    v0, v1, v2 = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    p0, p1, p2 = v0[:, :2].copy(), v1[:, :2].copy(), v2[:, :2].copy()
    return AsciiStlMesh(
        v0=v0.copy(),
        v1=v1.copy(),
        v2=v2.copy(),
        p0=p0,
        p1=p1,
        p2=p2,
        bb_min=np.minimum.reduce([p0, p1, p2]),
        bb_max=np.maximum.reduce([p0, p1, p2]),
    )


def classify_triangle_geometric_sheets(
    triangles: np.ndarray,
    *,
    surface_abs_nz_min: float = 0.45,
) -> np.ndarray:
    """Assign stable upper/lower identity through the formal sampler selection semantics."""

    triangle_array = _validate_triangles(triangles)
    sampler = SurfaceSlopeSampler(
        mesh=_mesh_from_triangles(triangle_array),
        surface_abs_nz_min=float(surface_abs_nz_min),
    )
    result = np.full(triangle_array.shape[0], GEOMETRIC_SHEET_INVALID, dtype=np.int8)
    raw = np.cross(triangle_array[:, 1] - triangle_array[:, 0], triangle_array[:, 2] - triangle_array[:, 0])
    norm = np.linalg.norm(raw, axis=1)
    nondegenerate = norm > 1e-12
    result[nondegenerate] = GEOMETRIC_SHEET_OTHER
    skin = nondegenerate & (np.abs(raw[:, 2]) / np.where(nondegenerate, norm, 1.0) >= float(surface_abs_nz_min))

    centroids = np.mean(triangle_array, axis=1)
    for triangle_index in np.flatnonzero(skin):
        upper, lower = sampler.sample_upper_lower_with_triangle_id(
            x=float(centroids[triangle_index, 0]),
            span=float(centroids[triangle_index, 1]),
        )
        is_upper = upper is not None and int(upper[6]) == int(triangle_index)
        is_lower = lower is not None and int(lower[6]) == int(triangle_index)
        if is_upper != is_lower:
            result[triangle_index] = GEOMETRIC_SHEET_UPPER if is_upper else GEOMETRIC_SHEET_LOWER
        elif is_upper and is_lower:
            result[triangle_index] = GEOMETRIC_SHEET_INVALID
    return _readonly(result, dtype=np.int8)


@dataclass(frozen=True)
class ProjectedGeometrySemantics:
    projected_xyz: np.ndarray
    triangle_id: np.ndarray
    geometric_sheet: np.ndarray
    outward_normal: np.ndarray
    incidence_s: np.ndarray
    surface_class: np.ndarray
    qchain_stl_accepted: np.ndarray
    normal_source: np.ndarray
    x_over_c: np.ndarray
    y_over_b: np.ndarray
    planform_parameterization_valid: np.ndarray

    def __post_init__(self) -> None:
        if any(getattr(self, item.name).flags.writeable for item in fields(self)):
            raise ValueError("all semantic result arrays must be read-only")


def build_projected_geometry_semantics(
    *,
    projected_xyz: np.ndarray,
    triangle_id: np.ndarray,
    triangles: np.ndarray,
    alpha_deg: float,
    planform_b_half_m: float,
    chord_min_m: float,
    upper_reference_normal_out: np.ndarray,
    lower_reference_normal_out: np.ndarray,
    outline_x_m: np.ndarray | None = None,
    outline_span_m: np.ndarray | None = None,
    c_root_m: float | None = None,
    planform_half_angle_deg: float | None = None,
) -> ProjectedGeometrySemantics:
    """Build immutable semantics in exact input point ordering."""

    points = np.asarray(projected_xyz, dtype=np.float64)
    ids = np.asarray(triangle_id)
    triangle_array = _validate_triangles(triangles)
    if points.ndim != 2 or points.shape[1:] != (3,) or not np.all(np.isfinite(points)):
        raise ValueError("projected_xyz must have shape (N, 3) and contain only finite values")
    if ids.shape != (points.shape[0],) or not np.issubdtype(ids.dtype, np.integer):
        raise ValueError("triangle_id must be an integer array with shape (N,)")
    ids = np.asarray(ids, dtype=np.int64)
    if np.any(ids < 0) or np.any(ids >= triangle_array.shape[0]):
        raise ValueError("triangle_id contains an index outside triangles")
    b_half = float(planform_b_half_m)
    chord_min = float(chord_min_m)
    if not np.isfinite(b_half) or b_half <= 0.0:
        raise ValueError("planform_b_half_m must be finite and greater than zero")
    if not np.isfinite(chord_min) or chord_min <= 0.0:
        raise ValueError("chord_min_m must be finite and greater than zero")
    has_outline = outline_x_m is not None or outline_span_m is not None
    if has_outline and (outline_x_m is None or outline_span_m is None):
        raise ValueError("outline_x_m and outline_span_m must be provided together")
    if not has_outline and (c_root_m is None or planform_half_angle_deg is None):
        raise ValueError("triangular fallback requires c_root_m and planform_half_angle_deg")

    triangle_sheet = classify_triangle_geometric_sheets(triangle_array)
    sheet = np.asarray(triangle_sheet[ids], dtype=np.int8)
    selected_raw = np.cross(
        triangle_array[ids, 1] - triangle_array[ids, 0],
        triangle_array[ids, 2] - triangle_array[ids, 0],
    )
    outward = np.full(points.shape, np.nan, dtype=np.float64)
    references = {
        GEOMETRIC_SHEET_UPPER: ("upper", np.asarray(upper_reference_normal_out, dtype=float)),
        GEOMETRIC_SHEET_LOWER: ("lower", np.asarray(lower_reference_normal_out, dtype=float)),
    }
    accepted = np.zeros(points.shape[0], dtype=bool)
    source = np.full(points.shape[0], NORMAL_SOURCE_INVALID, dtype=np.int8)
    for code, (name, reference_raw) in references.items():
        mask = sheet == code
        if not np.any(mask):
            continue
        oriented = orient_outward_normal(normal=selected_raw[mask], sheet=name)
        outward[mask] = oriented
        reference = orient_outward_normal(normal=reference_raw, sheet=name)
        mask_accepted = qchain_stl_acceptance(
            candidate_normal_out=oriented,
            reference_normal_out=reference,
        )
        valid_normal = np.all(np.isfinite(oriented), axis=1)
        accepted[mask] = mask_accepted
        local_source = np.full(mask_accepted.shape, NORMAL_SOURCE_INVALID, dtype=np.int8)
        local_source[valid_normal & mask_accepted] = NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER
        local_source[valid_normal & ~mask_accepted] = NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION
        source[mask] = local_source

    incidence_s, surface_class = classify_incidence(
        normal_out=outward,
        alpha_deg=float(alpha_deg),
        epsilon=INCIDENCE_EPSILON,
    )
    invalid_geometry = source == NORMAL_SOURCE_INVALID
    surface_class[invalid_geometry] = SURFACE_CLASS_INVALID
    incidence_s[invalid_geometry] = np.nan

    y_over_b = points[:, 1] / b_half
    x_over_c = np.full(points.shape[0], np.nan, dtype=np.float64)
    parameterization_valid = np.zeros(points.shape[0], dtype=bool)
    for index, (x_m, span_m) in enumerate(points[:, :2]):
        if has_outline:
            x_le, chord = outline_planform_xle_chord(
                span_m=float(span_m),
                outline_x_m=np.asarray(outline_x_m, dtype=float),
                outline_span_m=np.asarray(outline_span_m, dtype=float),
            )
        else:
            x_le, chord = triangle_planform_xle_chord(
                span_m=float(span_m),
                c_root_m=float(c_root_m),
                half_angle_deg=float(planform_half_angle_deg),
            )
        valid = np.isfinite(x_le) and np.isfinite(chord) and chord >= chord_min and chord > 0.0
        if valid:
            x_over_c[index] = (float(x_m) - x_le) / chord
            parameterization_valid[index] = True

    return ProjectedGeometrySemantics(
        projected_xyz=_readonly(points, dtype=np.float64),
        triangle_id=_readonly(ids, dtype=np.int64),
        geometric_sheet=_readonly(sheet, dtype=np.int8),
        outward_normal=_readonly(outward, dtype=np.float64),
        incidence_s=_readonly(incidence_s, dtype=np.float64),
        surface_class=_readonly(surface_class, dtype=np.int8),
        qchain_stl_accepted=_readonly(accepted, dtype=np.bool_),
        normal_source=_readonly(source, dtype=np.int8),
        x_over_c=_readonly(x_over_c, dtype=np.float64),
        y_over_b=_readonly(y_over_b, dtype=np.float64),
        planform_parameterization_valid=_readonly(parameterization_valid, dtype=np.bool_),
    )