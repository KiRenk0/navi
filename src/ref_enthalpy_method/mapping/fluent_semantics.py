"""Deterministic Phase 4B integration of Fluent projection and geometry semantics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from typing import Any

import numpy as np

from ref_enthalpy_method.geometry.local_incidence import (
    NORMAL_SOURCE_ANALYTIC_FALLBACK_NO_STL_COVERAGE,
    NORMAL_SOURCE_INVALID,
    NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER,
    NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION,
    SURFACE_CLASS_INVALID,
    SURFACE_CLASS_LEEWARD,
    SURFACE_CLASS_NEAR_TANGENT,
    SURFACE_CLASS_WINDWARD,
)
from ref_enthalpy_method.geometry.projected_semantics import (
    GEOMETRIC_SHEET_INVALID,
    GEOMETRIC_SHEET_LOWER,
    GEOMETRIC_SHEET_OTHER,
    GEOMETRIC_SHEET_UPPER,
    ProjectedGeometrySemantics,
    build_projected_geometry_semantics,
)
from ref_enthalpy_method.mapping.fluent_projection import (
    FluentSurfaceProjection,
    canonical_values_to_source_order,
)
from ref_enthalpy_method.mapping.fluent_surface import FluentSurfaceGeometry

_SEMANTIC_VALID_DEFINITION = (
    "normal_source in {1,2}, geometric_sheet in {UPPER,LOWER}, finite outward_normal "
    "and incidence_s, and surface_class != invalid; projection gate and planform validity "
    "are intentionally excluded"
)


@dataclass(frozen=True)
class FluentProjectedSemanticsIntegration:
    projection: FluentSurfaceProjection
    semantics: ProjectedGeometrySemantics
    geometry_qa: dict[str, Any]
    ordering_round_trip: dict[str, bool]

    def deterministic_qa_json(self) -> str:
        identity = {
            key: value
            for key, value in self.geometry_qa["identity"].items()
            if key != "geometry_source_sha256"
        }
        deterministic = {**self.geometry_qa, "identity": identity}
        return json.dumps(
            deterministic,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )


def _count_ratio(values: np.ndarray, codes: tuple[tuple[str, int], ...]) -> dict[str, dict[str, float | int]]:
    total = int(values.size)
    return {
        name: {
            "count": int(np.count_nonzero(values == code)),
            "ratio": float(np.count_nonzero(values == code) / total),
        }
        for name, code in codes
    }


def _parameter_statistics(values: np.ndarray) -> dict[str, float | int | None]:
    array = np.asarray(values, dtype=np.float64)
    finite = np.isfinite(array)
    selected = array[finite]
    percentiles = np.percentile(selected, [1.0, 5.0, 50.0, 95.0, 99.0]) if selected.size else None
    return {
        "total_count": int(array.size),
        "finite_count": int(selected.size),
        "non_finite_count": int(array.size - selected.size),
        "min": float(np.min(selected)) if selected.size else None,
        "max": float(np.max(selected)) if selected.size else None,
        "p01": float(percentiles[0]) if percentiles is not None else None,
        "p05": float(percentiles[1]) if percentiles is not None else None,
        "p50": float(percentiles[2]) if percentiles is not None else None,
        "p95": float(percentiles[3]) if percentiles is not None else None,
        "p99": float(percentiles[4]) if percentiles is not None else None,
        "less_than_zero_count": int(np.count_nonzero(selected < 0.0)),
        "greater_than_one_count": int(np.count_nonzero(selected > 1.0)),
    }


def semantic_valid_mask(semantics: ProjectedGeometrySemantics) -> np.ndarray:
    return (
        np.isin(
            semantics.normal_source,
            [
                NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER,
                NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION,
            ],
        )
        & np.isin(semantics.geometric_sheet, [GEOMETRIC_SHEET_UPPER, GEOMETRIC_SHEET_LOWER])
        & np.all(np.isfinite(semantics.outward_normal), axis=1)
        & np.isfinite(semantics.incidence_s)
        & (semantics.surface_class != SURFACE_CLASS_INVALID)
    )


_semantic_valid_mask = semantic_valid_mask


def _cross_table(
    rows: np.ndarray,
    row_codes: tuple[tuple[str, int], ...],
    columns: np.ndarray,
    column_codes: tuple[tuple[str, int], ...],
) -> dict[str, dict[str, int]]:
    return {
        row_name: {
            column_name: int(np.count_nonzero((rows == row_code) & (columns == column_code)))
            for column_name, column_code in column_codes
        }
        for row_name, row_code in row_codes
    }


def _exact_equal(left: np.ndarray, right: np.ndarray) -> bool:
    return (
        left.shape == right.shape
        and left.dtype == right.dtype
        and left.tobytes(order="C") == right.tobytes(order="C")
    )


def _require_projection_array(
    value: np.ndarray,
    *,
    name: str,
    dtype: np.dtype | type,
    shape: tuple[int, ...],
) -> np.ndarray:
    array = np.asarray(value)
    expected_dtype = np.dtype(dtype)
    if array.dtype != expected_dtype:
        raise ValueError(f"projection {name} must have dtype {expected_dtype}, got {array.dtype}")
    if array.shape != shape:
        raise ValueError(f"projection {name} must have shape {shape}, got {array.shape}")
    if not array.flags.c_contiguous:
        raise ValueError(f"projection {name} must be C-contiguous")
    if array.flags.writeable:
        raise ValueError(f"projection {name} must be read-only")
    if not array.flags.owndata:
        raise ValueError(f"projection {name} must own its data")
    return array


def _validate_projection_identity(
    geometry: FluentSurfaceGeometry,
    projection: FluentSurfaceProjection,
    triangles: np.ndarray,
) -> np.ndarray:
    triangle_array = np.asarray(triangles)
    if triangle_array.dtype != np.dtype(np.float64):
        raise ValueError(f"triangles must have dtype float64, got {triangle_array.dtype}")
    if triangle_array.ndim != 3 or triangle_array.shape[1:] != (3, 3) or triangle_array.shape[0] == 0:
        raise ValueError("triangles must have shape (M, 3, 3) with M > 0")
    if not np.all(np.isfinite(triangle_array)):
        raise ValueError("triangles must contain only finite values")

    canonical_xyz = geometry.canonical_solver_xyz
    count = canonical_xyz.shape[0]
    canonical_index = _require_projection_array(
        projection.canonical_index,
        name="canonical_index",
        dtype=np.int64,
        shape=(count,),
    )
    solver_xyz = _require_projection_array(
        projection.solver_xyz,
        name="solver_xyz",
        dtype=np.float64,
        shape=(count, 3),
    )
    projected_xyz = _require_projection_array(
        projection.projected_xyz,
        name="projected_xyz",
        dtype=np.float64,
        shape=(count, 3),
    )
    triangle_id = _require_projection_array(
        projection.triangle_id,
        name="triangle_id",
        dtype=np.int64,
        shape=(count,),
    )
    distance = _require_projection_array(
        projection.projection_distance_m,
        name="projection_distance_m",
        dtype=np.float64,
        shape=(count,),
    )
    raw_normal = _require_projection_array(
        projection.raw_normal,
        name="raw_normal",
        dtype=np.float64,
        shape=(count, 3),
    )
    gate_pass = _require_projection_array(
        projection.projection_gate_pass,
        name="projection_gate_pass",
        dtype=np.bool_,
        shape=(count,),
    )

    if not np.array_equal(canonical_index, np.arange(count, dtype=np.int64)):
        raise ValueError("projection canonical_index must be 0..N-1")
    if not np.all(np.isfinite(solver_xyz)):
        raise ValueError("projection solver_xyz must contain only finite values")
    if not _exact_equal(solver_xyz, canonical_xyz):
        raise ValueError("projection solver_xyz does not match geometry canonical ordering")
    expected_canonical_hash = hashlib.sha256(solver_xyz.tobytes(order="C")).hexdigest()
    if projection.canonical_geometry_sha256 != expected_canonical_hash:
        raise ValueError("projection canonical geometry SHA-256 does not match solver_xyz")
    if projection.geometry_source_sha256 != geometry.source_sha256:
        raise ValueError("projection geometry source SHA-256 does not match geometry")
    if projection.triangle_count != triangle_array.shape[0]:
        raise ValueError("projection triangle_count does not match triangles")

    if not np.all(np.isfinite(projected_xyz)):
        raise ValueError("projection projected_xyz must contain only finite values")
    if np.any(triangle_id < 0) or np.any(triangle_id >= projection.triangle_count):
        raise ValueError("projection triangle_id contains an index outside the triangle mesh")
    if not np.all(np.isfinite(distance)) or np.any(distance < 0.0):
        raise ValueError("projection distance must contain only finite nonnegative values")
    if raw_normal.shape != (count, 3):
        raise ValueError(f"projection raw_normal must have shape ({count}, 3)")

    try:
        gate = float(projection.projection_gate_m)
    except (TypeError, ValueError) as error:
        raise ValueError("projection gate must be a finite scalar greater than zero") from error
    if not np.isfinite(gate) or gate <= 0.0:
        raise ValueError("projection gate must be a finite scalar greater than zero")
    if not np.array_equal(gate_pass, distance <= gate):
        raise ValueError("projection gate-pass mask does not match distance <= gate")
    return triangle_array


def _ordering_round_trip(
    semantics: ProjectedGeometrySemantics,
    geometry: FluentSurfaceGeometry,
) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    for item in fields(semantics):
        canonical = getattr(semantics, item.name)
        source = canonical_values_to_source_order(canonical, geometry.source_to_canonical_row)
        restored = np.ascontiguousarray(source[geometry.canonical_to_source_row])
        checks[item.name] = _exact_equal(canonical, restored)
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError(f"canonical/source/canonical round-trip failed: {failed}")
    return checks


def _consistency_checks(
    projection: FluentSurfaceProjection,
    semantics: ProjectedGeometrySemantics,
    round_trip: dict[str, bool],
) -> dict[str, bool | float]:
    semantic_valid = semantic_valid_mask(semantics)
    valid_normals = semantics.outward_normal[semantic_valid]
    norm_error = (
        float(np.max(np.abs(np.linalg.norm(valid_normals, axis=1) - 1.0), initial=0.0))
        if valid_normals.size
        else 0.0
    )
    upper = semantics.geometric_sheet == GEOMETRIC_SHEET_UPPER
    lower = semantics.geometric_sheet == GEOMETRIC_SHEET_LOWER
    source_1 = semantics.normal_source == NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER
    source_2 = semantics.normal_source == NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION
    invalid = semantics.normal_source == NORMAL_SOURCE_INVALID
    checks: dict[str, bool | float] = {
        "triangle_id_exact": _exact_equal(semantics.triangle_id, projection.triangle_id),
        "projected_xyz_byte_exact": _exact_equal(semantics.projected_xyz, projection.projected_xyz),
        "valid_outward_normals_finite": bool(np.all(np.isfinite(valid_normals))),
        "valid_outward_normals_unit_max_abs_error": norm_error,
        "valid_outward_normals_near_unit": norm_error <= 1.0e-12,
        "upper_outward_direction": bool(np.all(semantics.outward_normal[upper, 2] > 0.0)),
        "lower_outward_direction": bool(np.all(semantics.outward_normal[lower, 2] < 0.0)),
        "qchain_accepted_matches_source_1": bool(np.array_equal(semantics.qchain_stl_accepted, source_1)),
        "qchain_rejected_valid_matches_source_2": bool(np.array_equal((~semantics.qchain_stl_accepted) & semantic_valid, source_2)),
        "invalid_source_contract": bool(
            np.all(semantics.surface_class[invalid] == SURFACE_CLASS_INVALID)
            and np.all(np.isnan(semantics.incidence_s[invalid]))
            and np.all(np.isnan(semantics.outward_normal[invalid]))
        ),
        "projected_stl_source_3_absent": int(np.count_nonzero(semantics.normal_source == NORMAL_SOURCE_ANALYTIC_FALLBACK_NO_STL_COVERAGE)) == 0,
        "all_ordering_round_trips": all(round_trip.values()),
    }
    boolean_checks = [value for value in checks.values() if isinstance(value, bool)]
    if not all(boolean_checks):
        failed = [name for name, passed in checks.items() if isinstance(passed, bool) and not passed]
        raise ValueError(f"projection/semantics consistency failed: {failed}")
    return checks


def _build_geometry_qa(
    projection: FluentSurfaceProjection,
    semantics: ProjectedGeometrySemantics,
    round_trip: dict[str, bool],
) -> dict[str, Any]:
    sheet_codes = (
        ("UPPER", GEOMETRIC_SHEET_UPPER),
        ("LOWER", GEOMETRIC_SHEET_LOWER),
        ("OTHER", GEOMETRIC_SHEET_OTHER),
        ("INVALID", GEOMETRIC_SHEET_INVALID),
    )
    source_codes = (
        ("0_invalid", NORMAL_SOURCE_INVALID),
        ("1_stl_accepted_by_qchain", NORMAL_SOURCE_STL_ACCEPTED_BY_QCHAIN_FILTER),
        ("2_stl_rejected_by_qchain_retained", NORMAL_SOURCE_STL_REJECTED_BY_QCHAIN_FILTER_BUT_USED_FOR_CLASSIFICATION),
        ("3_analytic_fallback", NORMAL_SOURCE_ANALYTIC_FALLBACK_NO_STL_COVERAGE),
    )
    class_codes = (
        ("windward", SURFACE_CLASS_WINDWARD),
        ("leeward", SURFACE_CLASS_LEEWARD),
        ("near_tangent", SURFACE_CLASS_NEAR_TANGENT),
        ("invalid", SURFACE_CLASS_INVALID),
    )
    semantic_valid = semantic_valid_mask(semantics)
    gate = projection.projection_gate_pass
    consistency = _consistency_checks(projection, semantics, round_trip)
    return {
        "schema": "faceted3d-phase4b-geometry-qa/v1",
        "identity": {
            "point_count": int(semantics.projected_xyz.shape[0]),
            "triangle_count": int(projection.triangle_count),
            "canonical_geometry_sha256": projection.canonical_geometry_sha256,
            "geometry_source_sha256": projection.geometry_source_sha256,
            "projection_gate_m": float(projection.projection_gate_m),
            "projection_gate_pass_count": int(np.count_nonzero(gate)),
            "projection_gate_fail_count": int(np.count_nonzero(~gate)),
        },
        "geometric_sheet": _count_ratio(semantics.geometric_sheet, sheet_codes),
        "normal_source": _count_ratio(semantics.normal_source, source_codes),
        "aerodynamic_surface_class": _count_ratio(semantics.surface_class, class_codes),
        "planform_parameters": {
            "x_over_c": _parameter_statistics(semantics.x_over_c),
            "y_over_b": _parameter_statistics(semantics.y_over_b),
            "planform_parameterization_invalid_count": int(
                np.count_nonzero(~semantics.planform_parameterization_valid)
            ),
        },
        "semantic_validity": {
            "definition": _SEMANTIC_VALID_DEFINITION,
            "valid_count": int(np.count_nonzero(semantic_valid)),
            "invalid_count": int(np.count_nonzero(~semantic_valid)),
        },
        "projection_gate_x_semantic_validity": {
            "gate_pass_semantic_valid": int(np.count_nonzero(gate & semantic_valid)),
            "gate_fail_semantic_valid": int(np.count_nonzero((~gate) & semantic_valid)),
            "gate_pass_semantic_invalid": int(np.count_nonzero(gate & (~semantic_valid))),
            "gate_fail_semantic_invalid": int(np.count_nonzero((~gate) & (~semantic_valid))),
        },
        "geometric_sheet_x_normal_source": _cross_table(
            semantics.geometric_sheet, sheet_codes, semantics.normal_source, source_codes
        ),
        "geometric_sheet_x_surface_class": _cross_table(
            semantics.geometric_sheet, sheet_codes, semantics.surface_class, class_codes
        ),
        "consistency": consistency,
        "canonical_source_round_trip": dict(round_trip),
    }


def integrate_fluent_projected_semantics(
    *,
    geometry: FluentSurfaceGeometry,
    projection: FluentSurfaceProjection,
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
) -> FluentProjectedSemanticsIntegration:
    """Connect exact canonical Fluent projection to raw projected geometry semantics."""

    triangle_array = _validate_projection_identity(geometry, projection, triangles)
    semantics = build_projected_geometry_semantics(
        projected_xyz=projection.projected_xyz,
        triangle_id=projection.triangle_id,
        triangles=triangle_array,
        alpha_deg=alpha_deg,
        planform_b_half_m=planform_b_half_m,
        chord_min_m=chord_min_m,
        upper_reference_normal_out=upper_reference_normal_out,
        lower_reference_normal_out=lower_reference_normal_out,
        outline_x_m=outline_x_m,
        outline_span_m=outline_span_m,
        c_root_m=c_root_m,
        planform_half_angle_deg=planform_half_angle_deg,
    )
    round_trip = _ordering_round_trip(semantics, geometry)
    qa = _build_geometry_qa(projection, semantics, round_trip)
    return FluentProjectedSemanticsIntegration(
        projection=projection,
        semantics=semantics,
        geometry_qa=qa,
        ordering_round_trip=round_trip,
    )