#!/usr/bin/env python3
"""Run the formal Phase 4B geometry-only Fluent semantics QA."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ref_enthalpy_method.geometry.faceted3d import load_outline_csv
from ref_enthalpy_method.geometry.local_incidence import outward_normal_from_slopes
from ref_enthalpy_method.geometry.stl_surface import AsciiStlMesh
from ref_enthalpy_method.mapping.observation_binding import (
    APPROVED_FORMAL_OBSERVATION_REGISTRY,
)
from ref_enthalpy_method.mapping.fluent_projection import (
    FluentSurfaceProjection,
    project_fluent_surface_exact,
)
from ref_enthalpy_method.mapping.fluent_semantics import (
    FluentProjectedSemanticsIntegration,
    integrate_fluent_projected_semantics,
)
from ref_enthalpy_method.mapping.fluent_surface import (
    CanonicalGeometryComparison,
    FluentSurfaceGeometry,
    compare_canonical_geometry,
    read_fluent_surface_geometry_csv,
)

CASES = tuple(
    (case_id, ROOT / csv_path)
    for case_id, csv_path in APPROVED_FORMAL_OBSERVATION_REGISTRY.items()
)
STL_PATH = ROOT / "new_spec" / "htv2_0628.stl"
OUTLINE_PATH = ROOT / "new_spec" / "outline_xz_right_0629.csv"
X_OFFSET_M = 0.030
PROJECTION_GATE_M = 0.005
ALPHA_DEG = 5.0
PLANFORM_B_HALF_M = 1.031027
CHORD_MIN_M = 0.02


def _comparison_dict(comparison: CanonicalGeometryComparison) -> dict[str, bool | float]:
    return {
        "shape_equal": comparison.shape_equal,
        "dtype_equal": comparison.dtype_equal,
        "numerical_exact_equal": comparison.numerical_exact_equal,
        "c_order_bytes_equal": comparison.c_order_bytes_equal,
        "maximum_absolute_coordinate_difference": comparison.maximum_absolute_coordinate_difference,
    }


def _array_fields_byte_equal(left: object, right: object) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    for name, left_value in vars(left).items():
        if not isinstance(left_value, np.ndarray):
            continue
        right_value = getattr(right, name)
        checks[name] = (
            left_value.shape == right_value.shape
            and left_value.dtype == right_value.dtype
            and left_value.tobytes(order="C") == right_value.tobytes(order="C")
        )
    return checks


def _readonly(value: np.ndarray, dtype: np.dtype | type) -> np.ndarray:
    result = np.array(value, dtype=dtype, copy=True, order="C")
    result.setflags(write=False)
    return result


def _chunk_geometry(geometry: FluentSurfaceGeometry, start: int, stop: int) -> FluentSurfaceGeometry:
    canonical_xyz = geometry.canonical_solver_xyz[start:stop]
    count = stop - start
    identity = _readonly(np.arange(count), np.int64)
    return FluentSurfaceGeometry(
        source_path=geometry.source_path,
        source_sha256=geometry.source_sha256,
        source_row_index=identity,
        cellnumber=_readonly(np.arange(count).astype(str), np.str_),
        raw_xyz=_readonly(canonical_xyz, np.float64),
        solver_xyz=_readonly(canonical_xyz, np.float64),
        canonical_index=identity,
        canonical_to_source_row=identity,
        source_to_canonical_row=identity,
    )


def _project_chunk(arguments: tuple[FluentSurfaceGeometry, np.ndarray]) -> FluentSurfaceProjection:
    geometry, triangles = arguments
    return project_fluent_surface_exact(
        geometry,
        triangles,
        projection_gate_m=PROJECTION_GATE_M,
    )


def _project_parallel(
    geometry: FluentSurfaceGeometry,
    triangles: np.ndarray,
) -> tuple[FluentSurfaceProjection, int]:
    count = geometry.canonical_solver_xyz.shape[0]
    worker_count = max(1, min(8, int(os.cpu_count() or 1)))
    boundaries = np.linspace(0, count, worker_count + 1, dtype=np.int64)
    chunks = [
        _chunk_geometry(geometry, int(start), int(stop))
        for start, stop in zip(boundaries[:-1], boundaries[1:])
        if stop > start
    ]
    with ProcessPoolExecutor(max_workers=len(chunks)) as executor:
        projections = list(executor.map(_project_chunk, ((chunk, triangles) for chunk in chunks)))

    solver_xyz = _readonly(np.concatenate([item.solver_xyz for item in projections]), np.float64)
    projected_xyz = _readonly(np.concatenate([item.projected_xyz for item in projections]), np.float64)
    triangle_id = _readonly(np.concatenate([item.triangle_id for item in projections]), np.int64)
    distance = _readonly(np.concatenate([item.projection_distance_m for item in projections]), np.float64)
    raw_normal = _readonly(np.concatenate([item.raw_normal for item in projections]), np.float64)
    gate_pass = _readonly(np.concatenate([item.projection_gate_pass for item in projections]), np.bool_)
    if solver_xyz.tobytes(order="C") != geometry.canonical_solver_xyz.tobytes(order="C"):
        raise RuntimeError("parallel projection did not preserve canonical ordering")
    return (
        FluentSurfaceProjection(
            canonical_index=_readonly(np.arange(count), np.int64),
            solver_xyz=solver_xyz,
            projected_xyz=projected_xyz,
            triangle_id=triangle_id,
            projection_distance_m=distance,
            raw_normal=raw_normal,
            projection_gate_m=PROJECTION_GATE_M,
            projection_gate_pass=gate_pass,
            geometry_source_path=geometry.source_path,
            geometry_source_sha256=geometry.source_sha256,
            canonical_geometry_sha256=hashlib.sha256(solver_xyz.tobytes(order="C")).hexdigest(),
            triangle_count=int(triangles.shape[0]),
        ),
        len(chunks),
    )


def _execution_metadata(projection_chunk_count: int) -> dict[str, int | bool | str]:
    return {
        "formal_projection_dataset_count": 1,
        "projection_chunk_count": projection_chunk_count,
        "exact_kernel_invocation_count": projection_chunk_count,
        "projection_reused_after_canonical_identity": True,
        "independent_second_projection_executed": False,
        "projection_reuse_reason": (
            "compare_canonical_geometry proved exact canonical identity before projection array reuse"
        ),
        "case_specific_provenance_replaced": True,
    }


def _integrate(
    geometry: Any,
    projection: Any,
    triangles: np.ndarray,
    outline_x_m: np.ndarray,
    outline_span_m: np.ndarray,
    upper_reference: np.ndarray,
    lower_reference: np.ndarray,
) -> FluentProjectedSemanticsIntegration:
    return integrate_fluent_projected_semantics(
        geometry=geometry,
        projection=projection,
        triangles=triangles,
        alpha_deg=ALPHA_DEG,
        planform_b_half_m=PLANFORM_B_HALF_M,
        chord_min_m=CHORD_MIN_M,
        upper_reference_normal_out=upper_reference,
        lower_reference_normal_out=lower_reference,
        outline_x_m=outline_x_m,
        outline_span_m=outline_span_m,
    )


def main() -> int:
    mesh = AsciiStlMesh.load(
        stl_path=STL_PATH,
        unit="mm",
        span_sign=-1.0,
        right_half_only=True,
    )
    triangles = np.ascontiguousarray(np.stack([mesh.v0, mesh.v1, mesh.v2], axis=1), dtype=np.float64)
    outline_x_m, outline_span_m = load_outline_csv(
        csv_path=OUTLINE_PATH,
        x_col="x_m",
        span_col="z_m",
        span_sign=-1.0,
    )
    upper_reference = outward_normal_from_slopes(
        sx=np.asarray(0.17632698070846498),
        sy=np.asarray(-0.5426786456862612),
        sheet="upper",
    )
    lower_reference = outward_normal_from_slopes(
        sx=np.asarray(-0.05240777928304121),
        sy=np.asarray(0.16129455951933025),
        sheet="lower",
    )

    left_id, left_path = CASES[0]
    right_id, right_path = CASES[1]
    left_geometry = read_fluent_surface_geometry_csv(left_path, x_offset_m=X_OFFSET_M)
    right_geometry = read_fluent_surface_geometry_csv(right_path, x_offset_m=X_OFFSET_M)
    geometry_comparison = compare_canonical_geometry(left_geometry, right_geometry)
    if not geometry_comparison.equal:
        raise RuntimeError("formal cases do not have identical canonical geometry")

    left_projection, projection_chunk_count = _project_parallel(
        left_geometry,
        triangles,
    )
    right_projection = replace(
        left_projection,
        geometry_source_path=right_geometry.source_path,
        geometry_source_sha256=right_geometry.source_sha256,
    )
    left = _integrate(
        left_geometry,
        left_projection,
        triangles,
        outline_x_m,
        outline_span_m,
        upper_reference,
        lower_reference,
    )
    right = _integrate(
        right_geometry,
        right_projection,
        triangles,
        outline_x_m,
        outline_span_m,
        upper_reference,
        lower_reference,
    )
    projection_equal = _array_fields_byte_equal(left.projection, right.projection)
    semantics_equal = _array_fields_byte_equal(left.semantics, right.semantics)
    deterministic_qa_equal = left.deterministic_qa_json() == right.deterministic_qa_json()
    if not (
        geometry_comparison.equal
        and all(projection_equal.values())
        and all(semantics_equal.values())
        and deterministic_qa_equal
    ):
        raise RuntimeError("formal cross-case geometry determinism check failed")

    output = {
        "schema": "faceted3d-phase4b-formal-qa-run/v1",
        "inputs": {
            "cases": [left_id, right_id],
            "alpha_deg": ALPHA_DEG,
            "x_offset_m": X_OFFSET_M,
            "projection_gate_m": PROJECTION_GATE_M,
            "planform_b_half_m": PLANFORM_B_HALF_M,
            "chord_min_m": CHORD_MIN_M,
            "stl_path": str(STL_PATH.relative_to(ROOT)),
            "outline_path": str(OUTLINE_PATH.relative_to(ROOT)),
        },
        "geometry_qa": left.geometry_qa,
        "cross_case_projection_reuse": {
            "canonical_geometry": _comparison_dict(geometry_comparison),
            **_execution_metadata(projection_chunk_count),
            "projection_arrays_equal_after_reuse": projection_equal,
            "semantic_arrays_equal_after_projection_reuse": all(semantics_equal.values()),
            "semantic_array_field_equality_after_projection_reuse": semantics_equal,
            "deterministic_qa_serialization_equal_after_projection_reuse": deterministic_qa_equal,
            "left_geometry_source_path": str(left_projection.geometry_source_path),
            "left_geometry_source_sha256": left_projection.geometry_source_sha256,
            "right_geometry_source_path": str(right_projection.geometry_source_path),
            "right_geometry_source_sha256": right_projection.geometry_source_sha256,
            "alpha_dependent_fields_compared": True,
            "reason": "both formal cases use identical alpha_deg and semantics inputs",
        },
    }
    print(json.dumps(output, ensure_ascii=True, allow_nan=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())