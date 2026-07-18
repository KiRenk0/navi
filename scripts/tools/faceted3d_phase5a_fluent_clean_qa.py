#!/usr/bin/env python3
"""Run the formal Phase 5A geometry-only Fluent clean-mask QA."""

from __future__ import annotations

import json
import sys
from dataclasses import fields, replace
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for import_root in (ROOT, SRC):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from ref_enthalpy_method.geometry.faceted3d import load_outline_csv
from ref_enthalpy_method.geometry.local_incidence import (
    NORMAL_SOURCE_ANALYTIC_FALLBACK_NO_STL_COVERAGE,
    NORMAL_SOURCE_INVALID,
    SURFACE_CLASS_LEEWARD,
    outward_normal_from_slopes,
)
from ref_enthalpy_method.geometry.projected_semantics import GEOMETRIC_SHEET_UPPER
from ref_enthalpy_method.geometry.stl_surface import AsciiStlMesh
from ref_enthalpy_method.mapping.fluent_clean import (
    FluentCleanLeewardMasks,
    build_fluent_clean_leeward_masks,
    fluent_clean_qa,
)
from ref_enthalpy_method.mapping.fluent_surface import (
    compare_canonical_geometry,
    read_fluent_surface_geometry_csv,
)
from scripts.tools.faceted3d_phase4b_geometry_qa import (
    ALPHA_DEG,
    CASES,
    CHORD_MIN_M,
    OUTLINE_PATH,
    PLANFORM_B_HALF_M,
    PROJECTION_GATE_M,
    STL_PATH,
    X_OFFSET_M,
    _comparison_dict,
    _execution_metadata,
    _integrate,
    _project_parallel,
)

EXPECTED = {
    "point_count": 21250,
    "projection_gate_valid_count": 21250,
    "semantic_valid_count": 14841,
    "planform_domain_valid_count": 21240,
    "clean_upper_count": 186,
    "clean_lower_count": 0,
    "clean_any_count": 186,
    "clean_upper_source_1_count": 15,
    "clean_upper_source_2_count": 171,
    "clean_lower_source_1_count": 0,
    "clean_lower_source_2_count": 0,
    "upper_lower_overlap_count": 0,
}


def _mask_fields_byte_equal(
    left: FluentCleanLeewardMasks,
    right: FluentCleanLeewardMasks,
) -> dict[str, bool]:
    return {
        item.name: (
            getattr(left, item.name).dtype == getattr(right, item.name).dtype
            and getattr(left, item.name).shape == getattr(right, item.name).shape
            and getattr(left, item.name).tobytes(order="C")
            == getattr(right, item.name).tobytes(order="C")
        )
        for item in fields(left)
    }


def _deterministic_json(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def _validate_case(
    integration: Any,
    masks: FluentCleanLeewardMasks,
    qa: dict[str, Any],
) -> dict[str, bool | int]:
    mismatches = {
        key: {"actual": qa.get(key), "expected": expected}
        for key, expected in EXPECTED.items()
        if qa.get(key) != expected
    }
    if mismatches:
        raise RuntimeError(f"formal clean counts do not match the frozen contract: {mismatches}")

    semantics = integration.semantics
    raw_upper_leeward = (
        (semantics.geometric_sheet == GEOMETRIC_SHEET_UPPER)
        & (semantics.surface_class == SURFACE_CLASS_LEEWARD)
    )
    source_0 = int(np.count_nonzero(masks.clean_leeward_upper & (semantics.normal_source == NORMAL_SOURCE_INVALID)))
    source_3 = int(
        np.count_nonzero(
            masks.clean_leeward_upper
            & (semantics.normal_source == NORMAL_SOURCE_ANALYTIC_FALLBACK_NO_STL_COVERAGE)
        )
    )
    checks: dict[str, bool | int] = {
        "clean_upper_equals_raw_upper_leeward": bool(
            np.array_equal(masks.clean_leeward_upper, raw_upper_leeward)
        ),
        "clean_upper_source_0_count": source_0,
        "clean_upper_source_3_count": source_3,
        "clean_upper_subset_clean_eligible": bool(
            np.all(~masks.clean_leeward_upper | masks.clean_eligible)
        ),
        "clean_lower_subset_clean_eligible": bool(
            np.all(~masks.clean_leeward_lower | masks.clean_eligible)
        ),
        "clean_upper_lower_disjoint": not bool(
            np.any(masks.clean_leeward_upper & masks.clean_leeward_lower)
        ),
        "clean_any_exact_union": bool(
            np.array_equal(
                masks.clean_leeward_any,
                masks.clean_leeward_upper | masks.clean_leeward_lower,
            )
        ),
    }
    if source_0 != 0 or source_3 != 0 or not all(
        value for value in checks.values() if isinstance(value, bool)
    ):
        raise RuntimeError(f"formal clean invariants failed: {checks}")
    return checks


def main() -> int:
    mesh = AsciiStlMesh.load(
        stl_path=STL_PATH,
        unit="mm",
        span_sign=-1.0,
        right_half_only=True,
    )
    triangles = np.ascontiguousarray(
        np.stack([mesh.v0, mesh.v1, mesh.v2], axis=1),
        dtype=np.float64,
    )
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

    left_projection, projection_chunk_count = _project_parallel(left_geometry, triangles)
    right_projection = replace(
        left_projection,
        geometry_source_path=right_geometry.source_path,
        geometry_source_sha256=right_geometry.source_sha256,
    )
    left_integration = _integrate(
        left_geometry,
        left_projection,
        triangles,
        outline_x_m,
        outline_span_m,
        upper_reference,
        lower_reference,
    )
    right_integration = _integrate(
        right_geometry,
        right_projection,
        triangles,
        outline_x_m,
        outline_span_m,
        upper_reference,
        lower_reference,
    )
    left_masks = build_fluent_clean_leeward_masks(left_integration)
    right_masks = build_fluent_clean_leeward_masks(right_integration)
    left_qa = fluent_clean_qa(left_integration, left_masks)
    right_qa = fluent_clean_qa(right_integration, right_masks)
    left_checks = _validate_case(left_integration, left_masks, left_qa)
    right_checks = _validate_case(right_integration, right_masks, right_qa)

    mask_equality = _mask_fields_byte_equal(left_masks, right_masks)
    deterministic_qa_equal = _deterministic_json(left_qa) == _deterministic_json(right_qa)
    if not all(mask_equality.values()) or not deterministic_qa_equal or left_checks != right_checks:
        raise RuntimeError("formal cross-case clean determinism check failed")

    execution = _execution_metadata(projection_chunk_count)
    execution.update(
        {
            "semantics_adapter_invocation_count": 2,
            "clean_builder_invocation_count": 2,
        }
    )
    output = {
        "schema": "faceted3d-phase5a-fluent-clean-qa/v1",
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
        "clean_definition": {
            "planform_domain": "planform_parameterization_valid AND finite(x_over_c) AND finite(y_over_b) AND 0 <= x_over_c <= 1 AND 0 <= y_over_b <= 1",
            "eligibility": "projection_gate_pass AND semantic_valid_mask(semantics) AND planform_domain_valid",
            "sheet_specific": "clean_eligible AND requested geometric_sheet AND surface_class == LEEWARD",
            "normal_source_policy": "source 1 and source 2 are both eligible",
            "qchain_policy": "qchain_stl_accepted is not a clean predicate",
            "edge_policy": "no nose or trailing-edge buffer is applied",
            "scope": "geometry-only; no temperature or other physical result field is read",
        },
        "execution": execution,
        "clean_qa": left_qa,
        "contract_checks": left_checks,
        "cross_case_determinism": {
            "canonical_geometry": _comparison_dict(geometry_comparison),
            "all_seven_clean_arrays_byte_exact": all(mask_equality.values()),
            "clean_array_field_byte_equality": mask_equality,
            "clean_qa_deterministic_json_byte_exact_excluding_provenance": deterministic_qa_equal,
            "only_source_path_and_source_sha256_differ": True,
            "left_geometry_source_path": str(left_projection.geometry_source_path),
            "left_geometry_source_sha256": left_projection.geometry_source_sha256,
            "right_geometry_source_path": str(right_projection.geometry_source_path),
            "right_geometry_source_sha256": right_projection.geometry_source_sha256,
            "reason": "both formal cases have canonical geometry identity and identical alpha-dependent inputs",
        },
    }
    print(json.dumps(output, ensure_ascii=True, allow_nan=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
