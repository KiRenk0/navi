#!/usr/bin/env python3
"""Run formal Phase 5C Fluent-clean to LF-clean pairing QA."""

from __future__ import annotations

import hashlib
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

from ref_enthalpy_method.geometry.faceted3d import load_outline_csv
from ref_enthalpy_method.geometry.local_incidence import outward_normal_from_slopes
from ref_enthalpy_method.geometry.stl_surface import AsciiStlMesh
from ref_enthalpy_method.mapping.fluent_clean import build_fluent_clean_leeward_masks
from ref_enthalpy_method.mapping.fluent_lf_pairing import (
    FluentLfCleanPairing,
    build_fluent_lf_clean_pairing,
)
from ref_enthalpy_method.mapping.fluent_surface import (
    compare_canonical_geometry,
    read_fluent_surface_geometry_csv,
)
from ref_enthalpy_method.mapping.lf_clean import build_lf_clean_leeward_masks
from ref_enthalpy_method.solver_faceted3d import WingLowFidelitySolverFaceted3D
from scripts.tools.faceted3d_phase4b_geometry_qa import (
    CASES,
    CHORD_MIN_M,
    OUTLINE_PATH,
    PLANFORM_B_HALF_M,
    STL_PATH,
    X_OFFSET_M,
    _integrate,
    _project_parallel,
)
from scripts.tools.faceted3d_phase5b_lf_clean_qa import (
    CASE,
    FORMAL_CASES,
    SAMPLING,
    VEHICLE,
)

METRIC = "projected_physical_x_span_euclidean_m"
PAIRING_ARRAY_FIELDS = (
    "source_canonical_index",
    "target_canonical_index",
    "distance_m",
    "dx_m",
    "dspan_m",
    "second_target_canonical_index",
    "second_distance_m",
    "ambiguity_margin_m",
    "mutual_nearest",
    "target_multiplicity",
)
EXPECTED_DTYPES = {
    "source_canonical_index": np.dtype(np.int64),
    "target_canonical_index": np.dtype(np.int64),
    "distance_m": np.dtype(np.float64),
    "dx_m": np.dtype(np.float64),
    "dspan_m": np.dtype(np.float64),
    "second_target_canonical_index": np.dtype(np.int64),
    "second_distance_m": np.dtype(np.float64),
    "ambiguity_margin_m": np.dtype(np.float64),
    "mutual_nearest": np.dtype(np.bool_),
    "target_multiplicity": np.dtype(np.int64),
}
EXPECTED_DISTANCE_MM_3DP = {
    "min": 0.323,
    "mean": 8.180,
    "median": 7.349,
    "p95": 17.752,
    "max": 21.042,
}
PROHIBITED_SEMANTICS = (
    "accepted",
    "passed",
    "gate",
    "threshold",
    "edge_buffer",
    "temperature",
    "wall_temperature",
    "temperature_error",
    "provider",
    "residual",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _array_contract(pairing: FluentLfCleanPairing) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name in PAIRING_ARRAY_FIELDS:
        value = getattr(pairing, name)
        result[name] = {
            "dtype": str(value.dtype),
            "shape": value.shape,
            "owned": bool(value.flags.owndata),
            "c_contiguous": bool(value.flags.c_contiguous),
            "read_only": not bool(value.flags.writeable),
        }
        expected = EXPECTED_DTYPES[name]
        _require(value.dtype == expected, f"{pairing.sheet}.{name}: dtype {value.dtype} != {expected}")
        _require(value.flags.owndata, f"{pairing.sheet}.{name}: array is not owned")
        _require(value.flags.c_contiguous, f"{pairing.sheet}.{name}: array is not C-contiguous")
        _require(not value.flags.writeable, f"{pairing.sheet}.{name}: array is writeable")
    return result


def _validate_pairing_structure(
    pairing: FluentLfCleanPairing,
    *,
    sheet: str,
    source_count: int,
    target_pool_size: int,
) -> dict[str, dict[str, Any]]:
    _require(pairing.sheet == sheet, f"{sheet}: sheet identity changed")
    _require(pairing.metric == METRIC, f"{sheet}: metric changed: {pairing.metric}")
    _require(pairing.target_pool_size == target_pool_size, f"{sheet}: target pool size changed")
    for name in PAIRING_ARRAY_FIELDS:
        _require(getattr(pairing, name).shape == (source_count,), f"{sheet}.{name}: shape changed")
    return _array_contract(pairing)


def _validate_upper(
    pairing: FluentLfCleanPairing,
    *,
    lf_fields: dict[str, np.ndarray],
    lf_upper_mask: np.ndarray,
) -> dict[str, Any]:
    contract = _validate_pairing_structure(
        pairing,
        sheet="upper",
        source_count=186,
        target_pool_size=256,
    )
    source = pairing.source_canonical_index
    target_pool = np.flatnonzero(lf_upper_mask).astype(np.int64, copy=False)
    _require(np.all(source[1:] > source[:-1]), "upper: source canonical indices are not strictly increasing")
    _require(np.unique(source).size == source.size, "upper: source canonical indices are not unique")
    _require(np.all(np.isin(pairing.target_canonical_index, target_pool)), "upper: assigned target outside LF clean upper pool")
    _require(np.all(pairing.distance_m >= 0.0), "upper: negative primary distance")
    _require(
        np.array_equal(pairing.distance_m, np.hypot(pairing.dx_m, pairing.dspan_m)),
        "upper: distance_m is not byte-exact hypot(dx_m, dspan_m)",
    )
    _require(np.all(pairing.second_distance_m >= pairing.distance_m), "upper: second distance below primary distance")
    _require(
        np.array_equal(
            pairing.ambiguity_margin_m,
            pairing.second_distance_m - pairing.distance_m,
        ),
        "upper: ambiguity margin differs from second_distance_m - distance_m",
    )
    _require(np.all(pairing.target_multiplicity >= 1), "upper: nonpositive target multiplicity")
    _require(np.all(pairing.second_target_canonical_index != -1), "upper: unexpected single-target index sentinel")
    _require(np.all(np.isfinite(pairing.second_distance_m)), "upper: nonfinite second distance")
    _require(np.all(np.isfinite(pairing.ambiguity_margin_m)), "upper: nonfinite ambiguity margin")
    _require(np.all(np.isin(pairing.second_target_canonical_index, target_pool)), "upper: second target outside LF clean upper pool")
    _require(np.asarray(lf_fields["x_l_m"]).dtype == np.dtype(np.float64), "upper: x_l_m is not float64")
    _require(np.asarray(lf_fields["span_l_m"]).dtype == np.dtype(np.float64), "upper: span_l_m is not float64")
    return {"array_contract": contract, "target_pool": target_pool}


def _validate_lower(pairing: FluentLfCleanPairing) -> dict[str, dict[str, Any]]:
    return _validate_pairing_structure(
        pairing,
        sheet="lower",
        source_count=0,
        target_pool_size=0,
    )


def _distance_summary_mm(distance_m: np.ndarray) -> dict[str, float]:
    distance_mm = distance_m * 1000.0
    return {
        "min": float(np.min(distance_mm)),
        "mean": float(np.mean(distance_mm)),
        "median": float(np.median(distance_mm)),
        "p95": float(np.percentile(distance_mm, 95.0)),
        "max": float(np.max(distance_mm)),
    }


def _fingerprint(pairing: FluentLfCleanPairing) -> dict[str, Any]:
    assigned_targets, assignment_counts = np.unique(
        pairing.target_canonical_index,
        return_counts=True,
    )
    unique_assigned = int(assigned_targets.size)
    result = {
        "sources": int(pairing.source_canonical_index.size),
        "targets": int(pairing.target_pool_size),
        "unique_assigned_targets": unique_assigned,
        "target_coverage": unique_assigned / pairing.target_pool_size,
        "collision_excess": int(pairing.source_canonical_index.size - unique_assigned),
        "duplicate_targets": int(np.count_nonzero(assignment_counts > 1)),
        "max_multiplicity": int(np.max(pairing.target_multiplicity)),
        "mutual_pairs": int(np.count_nonzero(pairing.mutual_nearest)),
    }
    expected = {
        "sources": 186,
        "targets": 256,
        "unique_assigned_targets": 80,
        "target_coverage": 0.3125,
        "collision_excess": 106,
        "duplicate_targets": 60,
        "max_multiplicity": 4,
        "mutual_pairs": 80,
    }
    _require(result == expected, f"Candidate P structural fingerprint changed: {result} != {expected}")
    summary = _distance_summary_mm(pairing.distance_m)
    rounded = {name: float(np.round(value, 3)) for name, value in summary.items()}
    _require(
        rounded == EXPECTED_DISTANCE_MM_3DP,
        f"Candidate P distance fingerprint changed at published 0.001 mm precision: {rounded}",
    )
    result["distance_summary_mm"] = summary
    result["distance_summary_mm_3dp"] = rounded
    return result


def _exact_nearest_ties(
    integration: Any,
    fluent_upper_mask: np.ndarray,
    lf_fields: dict[str, np.ndarray],
    lf_upper_mask: np.ndarray,
) -> int:
    source = np.asarray(integration.projection.projected_xyz)[fluent_upper_mask][:, (0, 1)]
    target = np.column_stack(
        (
            np.asarray(lf_fields["x_l_m"])[lf_upper_mask],
            np.asarray(lf_fields["span_l_m"])[lf_upper_mask],
        )
    )
    _require(source.dtype == np.dtype(np.float64), "tie audit source coordinates are not float64")
    _require(target.dtype == np.dtype(np.float64), "tie audit target coordinates are not float64")
    delta = target[None, :, :] - source[:, None, :]
    distance_squared = np.sum(delta * delta, axis=2, dtype=np.float64)
    row_minimum = np.min(distance_squared, axis=1)
    minimum_counts = np.count_nonzero(distance_squared == row_minimum[:, None], axis=1)
    return int(np.count_nonzero(minimum_counts > 1))


def _sha256(value: np.ndarray) -> str:
    return hashlib.sha256(value.tobytes(order="C")).hexdigest()


def _byte_exact(
    reference: FluentLfCleanPairing,
    candidate: FluentLfCleanPairing,
) -> tuple[dict[str, bool], dict[str, bool]]:
    scalars = {
        name: getattr(reference, name) == getattr(candidate, name)
        for name in ("sheet", "metric", "target_pool_size")
    }
    arrays = {}
    for name in PAIRING_ARRAY_FIELDS:
        left = getattr(reference, name)
        right = getattr(candidate, name)
        arrays[name] = bool(
            left.dtype == right.dtype
            and left.shape == right.shape
            and left.tobytes(order="C") == right.tobytes(order="C")
        )
    return scalars, arrays


def _build_fluent_integrations() -> dict[str, Any]:
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
    geometries = {
        case_id: read_fluent_surface_geometry_csv(path, x_offset_m=X_OFFSET_M)
        for case_id, path in CASES
    }
    case_ids = tuple(geometries)
    comparison = compare_canonical_geometry(geometries[case_ids[0]], geometries[case_ids[1]])
    _require(comparison.equal, "formal Fluent cases do not have identical canonical geometry")
    projection, _ = _project_parallel(geometries[case_ids[0]], triangles)
    integrations = {}
    for case_id in case_ids:
        geometry = geometries[case_id]
        case_projection = replace(
            projection,
            geometry_source_path=geometry.source_path,
            geometry_source_sha256=geometry.source_sha256,
        )
        integrations[case_id] = _integrate(
            geometry,
            case_projection,
            triangles,
            outline_x_m,
            outline_span_m,
            upper_reference,
            lower_reference,
        )
    return integrations


def _build_lf_fields(
    *,
    case_id: str,
    mach: float,
    alpha_deg: float,
    altitude_m: float,
    run_parent: Path,
) -> tuple[dict[str, np.ndarray], Any]:
    solver = WingLowFidelitySolverFaceted3D(
        vehicle_config=str(VEHICLE),
        case_config=str(CASE),
        sampling_config=str(SAMPLING),
        run_dir=str(run_parent / case_id),
    )
    solver.case = replace(solver.case, fixed_h_m=float(altitude_m))
    solver.compute_snapshot(mach=float(mach), alpha=float(alpha_deg))
    lf_fields = solver.last_fields
    masks = build_lf_clean_leeward_masks(lf_fields)
    return lf_fields, masks


def _validate_prohibitions() -> tuple[str, ...]:
    field_names = tuple(item.name for item in dataclass_fields(FluentLfCleanPairing))
    normalized = tuple(name.lower().replace(" ", "_") for name in field_names)
    violations = tuple(
        prohibited
        for prohibited in PROHIBITED_SEMANTICS
        if any(prohibited in name for name in normalized)
    )
    _require(not violations, f"pairing dataclass contains prohibited semantics: {violations}")
    return field_names


def main() -> int:
    print("A. Formal case identity")
    for case_id, path in CASES:
        print(f"  {case_id}: Fluent={path.relative_to(ROOT)}")
    print(f"  LF vehicle={VEHICLE.relative_to(ROOT)}")
    print(f"  LF case={CASE.relative_to(ROOT)}")
    print(f"  LF sampling={SAMPLING.relative_to(ROOT)}")

    integrations = _build_fluent_integrations()
    case_results: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="faceted3d_phase5c_pairing_") as temporary:
        for case_id, (mach, alpha_deg, altitude_m) in FORMAL_CASES.items():
            _require(case_id in integrations, f"formal case identity mismatch: {case_id}")
            integration = integrations[case_id]
            fluent_masks = build_fluent_clean_leeward_masks(integration)
            lf_fields, lf_masks = _build_lf_fields(
                case_id=case_id,
                mach=mach,
                alpha_deg=alpha_deg,
                altitude_m=altitude_m,
                run_parent=Path(temporary),
            )
            upper = build_fluent_lf_clean_pairing(
                integration=integration,
                fluent_masks=fluent_masks,
                lf_fields=lf_fields,
                lf_masks=lf_masks,
                sheet="upper",
            )
            lower = build_fluent_lf_clean_pairing(
                integration=integration,
                fluent_masks=fluent_masks,
                lf_fields=lf_fields,
                lf_masks=lf_masks,
                sheet="lower",
            )
            upper_contract = _validate_upper(
                upper,
                lf_fields=lf_fields,
                lf_upper_mask=lf_masks.clean_leeward_upper,
            )
            lower_contract = _validate_lower(lower)
            tie_count = _exact_nearest_ties(
                integration,
                fluent_masks.clean_leeward_upper,
                lf_fields,
                lf_masks.clean_leeward_upper,
            )
            _require(tie_count == 0, f"{case_id}: exact nearest ties changed: {tie_count}")
            case_results[case_id] = {
                "upper": upper,
                "lower": lower,
                "upper_contract": upper_contract["array_contract"],
                "lower_contract": lower_contract,
                "exact_ties": tie_count,
            }

    reference_id = next(iter(FORMAL_CASES))
    reference = case_results[reference_id]
    fingerprint = _fingerprint(reference["upper"])
    field_names = _validate_prohibitions()

    print("B. Upper/lower source and target counts")
    for case_id, result in case_results.items():
        print(
            f"  {case_id}: upper={result['upper'].source_canonical_index.size}/{result['upper'].target_pool_size}; "
            f"lower={result['lower'].source_canonical_index.size}/{result['lower'].target_pool_size}"
        )

    print("C. Candidate P fingerprint")
    print(
        "  sources={sources}; targets={targets}; unique_assigned_targets={unique_assigned_targets}; "
        "target_coverage={target_coverage:.4%}; collision_excess={collision_excess}; "
        "duplicate_targets={duplicate_targets}; max_multiplicity={max_multiplicity}; "
        "mutual_pairs={mutual_pairs}".format(**fingerprint)
    )

    print("D. Distance summary in mm")
    for name in ("min", "mean", "median", "p95", "max"):
        actual = fingerprint["distance_summary_mm"][name]
        published = fingerprint["distance_summary_mm_3dp"][name]
        print(f"  {name}={actual:.12g} mm; published_3dp={published:.3f} mm")

    print("E. Exact nearest tie count")
    for case_id, result in case_results.items():
        print(f"  {case_id}: {result['exact_ties']}")

    print("F. Cross-case byte-exact result by field")
    reference_upper = reference["upper"]
    reference_lower = reference["lower"]
    for case_id, result in case_results.items():
        upper_scalars, upper_arrays = _byte_exact(reference_upper, result["upper"])
        lower_scalars, lower_arrays = _byte_exact(reference_lower, result["lower"])
        _require(all(upper_scalars.values()) and all(upper_arrays.values()), f"{case_id}: upper pairing is not byte-exact")
        _require(all(lower_scalars.values()) and all(lower_arrays.values()), f"{case_id}: lower pairing is not byte-exact")
        print(f"  {case_id} upper scalars: {upper_scalars}")
        print(f"  {case_id} upper arrays: {upper_arrays}")
        print(f"  {case_id} lower scalars: {lower_scalars}")
        print(f"  {case_id} lower arrays: {lower_arrays}")
    print("  Reference upper array SHA-256")
    for name in PAIRING_ARRAY_FIELDS:
        print(f"    {name}={_sha256(getattr(reference_upper, name))}")
    print("  Reference lower array SHA-256")
    for name in PAIRING_ARRAY_FIELDS:
        print(f"    {name}={_sha256(getattr(reference_lower, name))}")

    print("G. dtype / shape / owned / C-contiguous / read-only")
    for sheet in ("upper", "lower"):
        print(f"  {sheet}")
        for name, contract in reference[f"{sheet}_contract"].items():
            print(
                f"    {name}: dtype={contract['dtype']}; shape={contract['shape']}; "
                f"owned={contract['owned']}; C={contract['c_contiguous']}; read_only={contract['read_only']}"
            )

    print("H. Derived diagnostic invariants")
    print("  many_to_one_allowed=True")
    print("  non_mutual_sources_retained=True")
    print("  multiplicity_above_one_sources_retained=True")
    print("  distance_diagnostic_does_not_filter_sources=True")
    print("  collision_excess, duplicate_targets, and max_multiplicity are distinct=True")

    print("I. Fixed prohibitions")
    print(f"  pairing_dataclass_fields={field_names}")
    print(f"  prohibited_semantics_absent={PROHIBITED_SEMANTICS}")
    print("  temperature_fields_read=False")
    print("  gate_or_accepted_mask_created=False")

    print("J. Overall result")
    print("FORMAL FLUENT-LF PAIRING QA: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
