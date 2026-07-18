#!/usr/bin/env python3
"""Run formal Phase 5B1 LF clean-mask integration QA."""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import fields as dataclass_fields, replace
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for import_root in (ROOT, SRC):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from ref_enthalpy_method.mapping.lf_clean import (
    LfCleanLeewardMasks,
    build_lf_clean_leeward_masks,
    lf_clean_qa,
)
from ref_enthalpy_method.solver_faceted3d import WingLowFidelitySolverFaceted3D

SCHEMA = "faceted3d-phase5b-lf-clean-qa/v1"
VEHICLE = ROOT / "specs" / "vehicles" / "htv2_faceted3d_0629.yaml"
CASE = ROOT / "specs" / "cases" / "doc_ma6_alpha5_h30km_faceted3d.yaml"
SAMPLING = ROOT / "specs" / "sampling" / "engineering_full_wing_surface_grid_81x41.yaml"
FORMAL_CASES = {
    "ma6_a5_h30km": (6.0, 5.0, 30000.0),
    "ma8_a5_h40km": (8.0, 5.0, 40000.0),
}
SHAKEOUT = (6.0, -5.0, 30000.0)
EXPECTED_FORMAL = {
    "point_count": 3321,
    "clean_upper_count": 256,
    "clean_lower_count": 0,
    "clean_any_count": 256,
    "clean_upper_source_1_count": 22,
    "clean_upper_source_2_count": 234,
    "clean_upper_source_3_count": 0,
    "upper_lower_overlap_count": 0,
}
RUNTIME_LAST_FIELDS_COUNT = 74
FORMAL_SERIALIZED_FIELD_COUNT = 72
RUNTIME_ONLY_DIAGNOSTIC_FIELDS = (
    "re_x_star_turb",
    "distance_from_transition",
)
CLEAN_FIELD_NAMES = tuple(item.name for item in dataclass_fields(LfCleanLeewardMasks))


def _field_snapshot(
    fields: dict[str, np.ndarray],
) -> tuple[
    tuple[str, ...],
    frozenset[str],
    dict[str, tuple[tuple[int, ...], np.dtype, bytes, bool]],
]:
    return (
        tuple(fields),
        frozenset(fields),
        {
            name: (
                value.shape,
                value.dtype,
                value.tobytes(order="A"),
                bool(value.flags.writeable),
            )
            for name, value in fields.items()
        },
    )


def _mask_contract(masks: LfCleanLeewardMasks) -> dict[str, bool]:
    return {
        item.name: bool(
            (value := getattr(masks, item.name)).dtype == np.dtype(np.bool_)
            and value.ndim == 1
            and value.flags.owndata
            and value.flags.c_contiguous
            and not value.flags.writeable
        )
        for item in dataclass_fields(masks)
    }


def _mask_equality(
    left: LfCleanLeewardMasks,
    right: LfCleanLeewardMasks,
) -> dict[str, bool]:
    return {
        item.name: bool(
            (left_value := getattr(left, item.name)).dtype
            == (right_value := getattr(right, item.name)).dtype
            and left_value.shape == right_value.shape
            and left_value.tobytes(order="C") == right_value.tobytes(order="C")
        )
        for item in dataclass_fields(left)
    }


def _run_case(
    *,
    case_id: str,
    mach: float,
    alpha_deg: float,
    altitude_m: float,
    parent: Path,
) -> tuple[LfCleanLeewardMasks, dict[str, Any]]:
    run_dir = parent / case_id
    solver = WingLowFidelitySolverFaceted3D(
        vehicle_config=str(VEHICLE),
        case_config=str(CASE),
        sampling_config=str(SAMPLING),
        run_dir=str(run_dir),
    )
    solver.case = replace(solver.case, fixed_h_m=float(altitude_m))
    solver.compute_snapshot(mach=float(mach), alpha=float(alpha_deg))
    fields = solver.last_fields
    if len(fields) != RUNTIME_LAST_FIELDS_COUNT:
        raise RuntimeError(
            f"{case_id}: runtime last_fields count changed: {len(fields)}"
        )
    missing_diagnostics = [
        name for name in RUNTIME_ONLY_DIAGNOSTIC_FIELDS if name not in fields
    ]
    if missing_diagnostics:
        raise RuntimeError(
            f"{case_id}: runtime-only diagnostics missing: {missing_diagnostics}"
        )
    before = _field_snapshot(fields)

    masks = build_lf_clean_leeward_masks(fields)
    after = _field_snapshot(fields)
    if after != before:
        raise RuntimeError(f"{case_id}: LF clean builder modified runtime last_fields")
    clean_fields_added = [name for name in CLEAN_FIELD_NAMES if name in fields]
    if clean_fields_added:
        raise RuntimeError(
            f"{case_id}: LF clean builder polluted runtime last_fields: "
            f"{clean_fields_added}"
        )

    qa = lf_clean_qa(fields, masks)
    contract = _mask_contract(masks)
    if not all(contract.values()):
        raise RuntimeError(f"{case_id}: immutable output contract failed: {contract}")
    if not np.array_equal(
        masks.clean_leeward_any,
        masks.clean_leeward_upper | masks.clean_leeward_lower,
    ):
        raise RuntimeError(f"{case_id}: clean any is not the exact disjoint union")

    return masks, {
        "inputs": {
            "mach": float(mach),
            "alpha_deg": float(alpha_deg),
            "altitude_m": float(altitude_m),
        },
        "runtime_last_fields_count": len(fields),
        "formal_serialized_field_count": FORMAL_SERIALIZED_FIELD_COUNT,
        "runtime_only_diagnostic_fields": list(RUNTIME_ONLY_DIAGNOSTIC_FIELDS),
        "clean_fields_added_to_runtime_cache": False,
        "runtime_cache_unchanged": True,
        "clean_qa": qa,
        "immutable_mask_contract": contract,
        "all_masks_immutable": all(contract.values()),
        "clean_any_exact_union": True,
    }


def _validate_formal(case_id: str, result: dict[str, Any]) -> None:
    qa = result["clean_qa"]
    mismatches = {
        key: {"actual": qa.get(key), "expected": expected}
        for key, expected in EXPECTED_FORMAL.items()
        if qa.get(key) != expected
    }
    if mismatches:
        raise RuntimeError(
            f"{case_id}: formal LF clean counts violate frozen contract: {mismatches}"
        )


def _validate_shakeout(result: dict[str, Any]) -> None:
    qa = result["clean_qa"]
    checks = {
        "clean_lower_nonempty": qa["clean_lower_count"] > 0,
        "upper_lower_disjoint": qa["upper_lower_overlap_count"] == 0,
        "clean_source_3_excluded": (
            qa["clean_upper_source_3_count"] == 0
            and qa["clean_lower_source_3_count"] == 0
        ),
        "runtime_last_fields_still_74": (
            result["runtime_last_fields_count"] == RUNTIME_LAST_FIELDS_COUNT
        ),
        "runtime_cache_unchanged": result["runtime_cache_unchanged"],
        "clean_fields_not_added_to_runtime_cache": (
            not result["clean_fields_added_to_runtime_cache"]
        ),
        "all_masks_immutable": result["all_masks_immutable"],
        "clean_any_exact_union": result["clean_any_exact_union"],
    }
    result["shakeout_checks"] = checks
    if not all(checks.values()):
        raise RuntimeError(f"alpha=-5 shakeout failed: {checks}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="faceted3d_phase5b1_lf_clean_") as temporary:
        parent = Path(temporary)
        formal_masks: dict[str, LfCleanLeewardMasks] = {}
        formal_results: dict[str, dict[str, Any]] = {}
        for case_id, (mach, alpha_deg, altitude_m) in FORMAL_CASES.items():
            masks, result = _run_case(
                case_id=case_id,
                mach=mach,
                alpha_deg=alpha_deg,
                altitude_m=altitude_m,
                parent=parent,
            )
            _validate_formal(case_id, result)
            formal_masks[case_id] = masks
            formal_results[case_id] = result

        left_id, right_id = FORMAL_CASES
        equality = _mask_equality(formal_masks[left_id], formal_masks[right_id])
        if not all(equality.values()):
            raise RuntimeError(f"formal +5 masks are not byte-exact: {equality}")

        shakeout_masks, shakeout_result = _run_case(
            case_id="ma6_a-5_h30km_shakeout",
            mach=SHAKEOUT[0],
            alpha_deg=SHAKEOUT[1],
            altitude_m=SHAKEOUT[2],
            parent=parent,
        )
        _validate_shakeout(shakeout_result)
        del shakeout_masks

        output = {
            "schema": SCHEMA,
            "clean_definition": {
                "planform_domain": "finite canonical x/span/x_over_c/y_over_b AND closed unit x_over_c/y_over_b bounds",
                "semantic_valid": "normal source in {1,2} AND finite normal/incidence AND surface class != INVALID",
                "sheet_specific": "planform_domain_valid AND semantic_valid_sheet AND surface_class_sheet == LEEWARD",
                "source_policy": "source 1 eligible; source 2 eligible; source 0 and source 3 excluded",
                "condition_1": "point/strip geometry validity is fail-closed through formal semantic defaults",
                "excluded_predicates": [
                    "mask_w",
                    "mask_l",
                    "qchain_stl_accepted",
                    "endpoint/LE/TE filters",
                    "temperature and physical-result fields",
                ],
            },
            "formal_cases": formal_results,
            "formal_cross_case_masks": {
                "all_eight_masks_byte_exact": all(equality.values()),
                "field_byte_equality": equality,
            },
            "alpha_minus_5_non_baseline_shakeout": shakeout_result,
            "field_contract": {
                "runtime_last_fields_count": RUNTIME_LAST_FIELDS_COUNT,
                "formal_serialized_field_count": FORMAL_SERIALIZED_FIELD_COUNT,
                "runtime_only_diagnostic_fields": list(
                    RUNTIME_ONLY_DIAGNOSTIC_FIELDS
                ),
                "clean_fields_added_to_runtime_cache": False,
                "formal_schema_verified_by": (
                    "scripts/tools/current_baseline_regression_check.py"
                ),
            },
        }
    print(
        json.dumps(
            output,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())