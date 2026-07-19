#!/usr/bin/env python3
"""Run formal Phase 5D Fluent wall-temperature canonical-ingestion QA."""

from __future__ import annotations

import csv
import hashlib
import inspect
import io
import sys
import tempfile
from dataclasses import fields as dataclass_fields, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for import_root in (ROOT, SRC):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from ref_enthalpy_method.mapping.fluent_clean import build_fluent_clean_leeward_masks
from ref_enthalpy_method.mapping.fluent_lf_pairing import build_fluent_lf_clean_pairing
from ref_enthalpy_method.mapping.fluent_surface import read_fluent_surface_geometry_csv
from ref_enthalpy_method.mapping.fluent_wall_temperature import (
    FluentWallTemperatureObservations,
    _read_wall_temperature_column,
    build_fluent_wall_temperature_observations,
)
from ref_enthalpy_method.mapping.lf_clean import build_lf_clean_leeward_masks
from scripts.tools.faceted3d_phase4b_geometry_qa import CASES, X_OFFSET_M
from scripts.tools.faceted3d_phase5b_lf_clean_qa import FORMAL_CASES
from scripts.tools.faceted3d_phase5c_fluent_lf_pairing_qa import (
    METRIC,
    _build_fluent_integrations,
    _build_lf_fields,
)

COLUMN_NAME = "wall-temperature"
UNIT = "K"
EXPECTED_ROWS = 21_250
EXPECTED_UPPER_COUNT = 186
EXPECTED_EXTREMA_6DP = {
    "ma6_a5_h30km": (1466.148388, 1692.476316),
    "ma8_a5_h40km": (2549.788388, 2978.452452),
}
OBSERVATION_ARRAY_FIELDS = (
    "source_canonical_index",
    "source_row_index",
    "wall_temperature_K",
)
EXPECTED_DTYPES = {
    "source_canonical_index": np.dtype(np.int64),
    "source_row_index": np.dtype(np.int64),
    "wall_temperature_K": np.dtype(np.float64),
}
EXPECTED_OBSERVATION_FIELDS = (
    "sheet",
    "column_name",
    "unit",
    "source_csv_sha256",
    "source_canonical_index",
    "source_row_index",
    "wall_temperature_K",
)
PROHIBITED_OUTPUT_SEMANTICS = (
    "LF prediction",
    "temperature error",
    "accepted / passed / gate",
    "area weighting",
    "target aggregation",
    "provider selection",
    "LF target identity",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _byte_exact(left: np.ndarray, right: np.ndarray) -> bool:
    return bool(
        left.dtype == right.dtype
        and left.shape == right.shape
        and left.tobytes(order="C") == right.tobytes(order="C")
    )


def _statistics(values: np.ndarray, *, include_p95: bool) -> dict[str, float]:
    result = {
        "min": float(np.min(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
    }
    if include_p95:
        result["p95"] = float(np.percentile(values, 95.0))
    result["max"] = float(np.max(values))
    return result


def _format_statistics(values: dict[str, float]) -> str:
    return "; ".join(f"{name}={value:.12g} K" for name, value in values.items())


def _read_csv_evidence(path: Path) -> dict[str, Any]:
    raw_bytes = path.read_bytes()
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    source_text = raw_bytes.decode("utf-8", errors="strict")
    rows = csv.reader(io.StringIO(source_text, newline=""))
    try:
        header = next(rows)
    except StopIteration as error:
        raise RuntimeError(f"{path}: CSV is empty") from error

    normalized_header = [field.strip() for field in header]
    matches = [index for index, name in enumerate(normalized_header) if name == COLUMN_NAME]
    _require(
        len(matches) == 1,
        f"{path}: trim-normalized {COLUMN_NAME!r} column count is {len(matches)}, expected 1",
    )
    column_index = matches[0]

    data_row_count = 0
    blank_count = 0
    parse_failure_count = 0
    nan_count = 0
    inf_count = 0
    non_positive_count = 0
    temperatures: list[float] = []
    for row in rows:
        data_row_count += 1
        if column_index >= len(row) or not row[column_index].strip():
            blank_count += 1
            temperatures.append(float("nan"))
            continue
        try:
            value = float(row[column_index].strip())
        except (TypeError, ValueError):
            parse_failure_count += 1
            temperatures.append(float("nan"))
            continue
        if np.isnan(value):
            nan_count += 1
        elif np.isinf(value):
            inf_count += 1
        elif value <= 0.0:
            non_positive_count += 1
        temperatures.append(value)

    source_temperature = np.array(temperatures, dtype=np.float64, copy=True, order="C")
    invalid_counts = {
        "blank": blank_count,
        "parse_failure": parse_failure_count,
        "NaN": nan_count,
        "Inf": inf_count,
        "non_positive": non_positive_count,
    }
    _require(data_row_count == EXPECTED_ROWS, f"{path}: data rows {data_row_count} != {EXPECTED_ROWS}")
    _require(
        source_temperature.dtype == np.dtype(np.float64)
        and source_temperature.shape == (EXPECTED_ROWS,),
        f"{path}: source temperature array contract changed",
    )
    _require(
        all(count == 0 for count in invalid_counts.values()),
        f"{path}: invalid wall-temperature counts are nonzero: {invalid_counts}",
    )

    return {
        "raw_byte_count": len(raw_bytes),
        "raw_sha256": raw_sha256,
        "header": header,
        "data_row_count": data_row_count,
        "column_index": column_index,
        "source_temperature": source_temperature,
        "invalid_counts": invalid_counts,
        "statistics": _statistics(source_temperature, include_p95=False),
    }


def _api_audit() -> dict[str, Any]:
    _require(is_dataclass(FluentWallTemperatureObservations), "observation type is not a dataclass")
    parameters = tuple(inspect.signature(build_fluent_wall_temperature_observations).parameters.values())
    keyword_only = bool(parameters) and all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in parameters
    )
    _require(keyword_only, "public builder is not fully keyword-only")
    frozen = bool(FluentWallTemperatureObservations.__dataclass_params__.frozen)
    _require(frozen, "observation dataclass is not frozen")
    field_names = tuple(item.name for item in dataclass_fields(FluentWallTemperatureObservations))
    _require(
        field_names == EXPECTED_OBSERVATION_FIELDS,
        f"observation fields changed: {field_names}",
    )
    _require("metric" not in field_names, "metric unexpectedly became an observation field")
    return {
        "keyword_only": keyword_only,
        "frozen": frozen,
        "field_names": field_names,
        "builder_signature": str(inspect.signature(build_fluent_wall_temperature_observations)),
    }


def _array_contract(
    observation: FluentWallTemperatureObservations,
    *,
    expected_count: int,
    identity: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name in OBSERVATION_ARRAY_FIELDS:
        value = getattr(observation, name)
        contract = {
            "dtype": str(value.dtype),
            "shape": value.shape,
            "ndim": value.ndim,
            "OWNDATA": bool(value.flags.owndata),
            "C_CONTIGUOUS": bool(value.flags.c_contiguous),
            "WRITEABLE": bool(value.flags.writeable),
        }
        result[name] = contract
        _require(value.dtype == EXPECTED_DTYPES[name], f"{identity}.{name}: dtype changed")
        _require(value.shape == (expected_count,), f"{identity}.{name}: shape changed")
        _require(value.ndim == 1, f"{identity}.{name}: ndim changed")
        _require(value.flags.owndata, f"{identity}.{name}: OWNDATA is false")
        _require(value.flags.c_contiguous, f"{identity}.{name}: C_CONTIGUOUS is false")
        _require(not value.flags.writeable, f"{identity}.{name}: WRITEABLE is true")
    return result


def _validate_provenance(
    observation: FluentWallTemperatureObservations,
    *,
    expected_sha256: str,
    identity: str,
) -> None:
    actual = observation.source_csv_sha256
    _require(actual == expected_sha256, f"{identity}: source CSV SHA-256 mismatch")
    _require(len(actual) == 64, f"{identity}: SHA-256 length is not 64")
    _require(
        all(character in "0123456789abcdef" for character in actual),
        f"{identity}: SHA-256 is not lowercase hexadecimal",
    )


def _validate_observation_metadata(
    observation: FluentWallTemperatureObservations,
    *,
    sheet: str,
    expected_sha256: str,
    identity: str,
) -> None:
    _require(observation.sheet == sheet, f"{identity}: sheet identity changed")
    _require(observation.column_name == COLUMN_NAME, f"{identity}: column_name changed")
    _require(observation.unit == UNIT, f"{identity}: unit changed")
    _validate_provenance(observation, expected_sha256=expected_sha256, identity=identity)


def _validate_case(
    *,
    case_id: str,
    csv_path: Path,
    integration: Any,
    lf_fields: dict[str, np.ndarray],
) -> dict[str, Any]:
    evidence = _read_csv_evidence(csv_path)
    source_temperature = evidence["source_temperature"]
    expected_min, expected_max = EXPECTED_EXTREMA_6DP[case_id]
    actual_statistics = evidence["statistics"]
    _require(
        round(actual_statistics["min"], 6) == expected_min,
        f"{case_id}: full-source minimum at 6dp changed: {actual_statistics['min']:.12g}",
    )
    _require(
        round(actual_statistics["max"], 6) == expected_max,
        f"{case_id}: full-source maximum at 6dp changed: {actual_statistics['max']:.12g}",
    )

    surface = read_fluent_surface_geometry_csv(csv_path, x_offset_m=X_OFFSET_M)
    canonical_to_source_row = surface.canonical_to_source_row
    source_to_canonical_row = surface.source_to_canonical_row
    _require(
        canonical_to_source_row.dtype == np.dtype(np.int64)
        and source_to_canonical_row.dtype == np.dtype(np.int64),
        f"{case_id}: formal canonical identity arrays are not int64",
    )
    canonical_temperature = source_temperature[canonical_to_source_row]
    _require(
        np.array_equal(canonical_temperature[source_to_canonical_row], source_temperature),
        f"{case_id}: canonical/source temperature permutation round-trip failed",
    )

    fluent_masks = build_fluent_clean_leeward_masks(integration)
    lf_masks = build_lf_clean_leeward_masks(lf_fields)
    observations: dict[str, FluentWallTemperatureObservations] = {}
    pairings: dict[str, Any] = {}
    contracts: dict[str, dict[str, dict[str, Any]]] = {}
    for sheet, expected_count in (("upper", EXPECTED_UPPER_COUNT), ("lower", 0)):
        pairing = build_fluent_lf_clean_pairing(
            integration=integration,
            fluent_masks=fluent_masks,
            lf_fields=lf_fields,
            lf_masks=lf_masks,
            sheet=sheet,
        )
        _require(pairing.metric == METRIC, f"{case_id}.{sheet}: pairing metric changed")
        observation = build_fluent_wall_temperature_observations(
            csv_path=csv_path,
            integration=integration,
            fluent_masks=fluent_masks,
            pairing=pairing,
            sheet=sheet,
        )
        identity = f"{case_id}.{sheet}"
        _validate_observation_metadata(
            observation,
            sheet=sheet,
            expected_sha256=evidence["raw_sha256"],
            identity=identity,
        )
        contracts[sheet] = _array_contract(
            observation,
            expected_count=expected_count,
            identity=identity,
        )
        pairings[sheet] = pairing
        observations[sheet] = observation

    upper = observations["upper"]
    expected_upper_source = np.flatnonzero(fluent_masks.clean_leeward_upper).astype(
        np.int64, copy=False
    )
    _require(
        np.array_equal(upper.source_canonical_index, pairings["upper"].source_canonical_index),
        f"{case_id}.upper: observation/pairing source identity differs",
    )
    _require(
        np.array_equal(upper.source_canonical_index, expected_upper_source),
        f"{case_id}.upper: observation/clean-mask source identity differs",
    )
    _require(
        np.all(upper.source_canonical_index[1:] > upper.source_canonical_index[:-1]),
        f"{case_id}.upper: source_canonical_index is not strictly increasing",
    )
    _require(
        np.unique(upper.source_canonical_index).size == EXPECTED_UPPER_COUNT,
        f"{case_id}.upper: source_canonical_index is not unique",
    )
    _require(
        np.unique(upper.source_row_index).size == EXPECTED_UPPER_COUNT,
        f"{case_id}.upper: source_row_index is not unique",
    )
    _require(
        np.all((upper.source_row_index >= 0) & (upper.source_row_index < EXPECTED_ROWS)),
        f"{case_id}.upper: source_row_index is outside the source domain",
    )
    _require(
        np.array_equal(
            upper.source_row_index,
            canonical_to_source_row[upper.source_canonical_index],
        ),
        f"{case_id}.upper: source row identity differs from canonical_to_source_row",
    )
    _require(
        np.all(np.isfinite(upper.wall_temperature_K)),
        f"{case_id}.upper: non-finite temperature",
    )
    _require(np.all(upper.wall_temperature_K > 0.0), f"{case_id}.upper: non-positive temperature")
    _require(
        np.array_equal(
            upper.wall_temperature_K,
            source_temperature[upper.source_row_index],
        ),
        f"{case_id}.upper: source-row temperature identity failed",
    )
    _require(
        np.array_equal(
            upper.wall_temperature_K,
            canonical_temperature[upper.source_canonical_index],
        ),
        f"{case_id}.upper: canonical temperature identity failed",
    )

    lower = observations["lower"]
    _require(
        lower.source_canonical_index.size == 0
        and lower.source_row_index.size == 0
        and lower.wall_temperature_K.size == 0,
        f"{case_id}.lower: typed-empty observation contains a sentinel or source row",
    )
    _require(
        upper.source_csv_sha256 == lower.source_csv_sha256,
        f"{case_id}: upper/lower CSV provenance differs",
    )

    return {
        "evidence": evidence,
        "surface": surface,
        "canonical_temperature": canonical_temperature,
        "fluent_masks": fluent_masks,
        "pairings": pairings,
        "observations": observations,
        "contracts": contracts,
        "upper_statistics": _statistics(upper.wall_temperature_K, include_p95=True),
    }


def _print_array_contracts(case_results: dict[str, dict[str, Any]]) -> None:
    print("K. dtype / shape / ownership / contiguity / immutability")
    for case_id, result in case_results.items():
        for sheet in ("upper", "lower"):
            print(f"  {case_id}.{sheet}")
            for name, contract in result["contracts"][sheet].items():
                print(
                    f"    {name}: dtype={contract['dtype']}; shape={contract['shape']}; "
                    f"ndim={contract['ndim']}; OWNDATA={contract['OWNDATA']}; "
                    f"C_CONTIGUOUS={contract['C_CONTIGUOUS']}; WRITEABLE={contract['WRITEABLE']}"
                )


def main() -> int:
    api = _api_audit()

    print("A. Starting case identity")
    for case_id, path in CASES:
        print(f"  {case_id}: {path.relative_to(ROOT)}")
    print("B. Formal construction chain")
    print(
        "  CSV geometry -> canonical projection / semantics -> Fluent clean -> "
        "formal LF fields / LF clean -> Fluent-to-LF pairing -> "
        "build_fluent_wall_temperature_observations(...)"
    )
    print("C. Actual dataclass/API")
    print("  public type=FluentWallTemperatureObservations")
    print("  public builder=build_fluent_wall_temperature_observations(...)")
    print("  private implementation=_read_wall_temperature_column(...)")
    print(f"  private parser object={_read_wall_temperature_column.__module__}._read_wall_temperature_column")
    print(f"  builder_signature={api['builder_signature']}")
    print(f"  builder_keyword_only={api['keyword_only']}")
    print(f"  dataclass=True; frozen={api['frozen']}; fields={api['field_names']}")
    print(f"  metric_field=False; pairing.metric={METRIC}")
    print(f"  observation_prohibited_outputs_absent={PROHIBITED_OUTPUT_SEMANTICS}")

    integrations = _build_fluent_integrations()
    case_paths = dict(CASES)
    case_results: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="faceted3d_phase5d_wall_temperature_") as temporary:
        for case_id, (mach, alpha_deg, altitude_m) in FORMAL_CASES.items():
            _require(case_id in integrations, f"formal integration missing for {case_id}")
            _require(case_id in case_paths, f"formal CSV path missing for {case_id}")
            lf_fields, _ = _build_lf_fields(
                case_id=case_id,
                mach=mach,
                alpha_deg=alpha_deg,
                altitude_m=altitude_m,
                run_parent=Path(temporary),
            )
            case_results[case_id] = _validate_case(
                case_id=case_id,
                csv_path=case_paths[case_id],
                integration=integrations[case_id],
                lf_fields=lf_fields,
            )

    print("D. CSV provenance, validity, and full-source statistics")
    for case_id, result in case_results.items():
        evidence = result["evidence"]
        temperature = evidence["source_temperature"]
        print(f"  {case_id}")
        print(f"    path={case_paths[case_id].relative_to(ROOT)}")
        print(f"    raw_bytes={evidence['raw_byte_count']}; SHA-256={evidence['raw_sha256']}")
        print(f"    decoded_header={evidence['header']}")
        print(
            f"    rows={evidence['data_row_count']}; wall-temperature_column_index={evidence['column_index']}; "
            f"dtype={temperature.dtype}; shape={temperature.shape}"
        )
        print(f"    invalid_counts={evidence['invalid_counts']}")
        print(f"    full_source={_format_statistics(evidence['statistics'])}")
        print("    unit=K (project input contract; not inferred from CSV header)")

    print("E. Upper observation exact identity and temperature statistics")
    for case_id, result in case_results.items():
        upper = result["observations"]["upper"]
        print(
            f"  {case_id}: source_count={upper.source_canonical_index.size}; "
            "observation==pairing==flatnonzero(clean_leeward_upper)=True; "
            "canonical_to_source_row=True; source_temperature[source_row_index]=True"
        )
        print(f"    clean_source={_format_statistics(result['upper_statistics'])}")

    print("F. Lower typed-empty")
    for case_id, result in case_results.items():
        lower = result["observations"]["lower"]
        print(
            f"  {case_id}: source_count=0; sheet={lower.sheet}; column_name={lower.column_name}; "
            f"unit={lower.unit}; SHA-256={lower.source_csv_sha256}; typed_empty=True"
        )

    print("G. Canonical identity round-trip")
    for case_id, result in case_results.items():
        surface = result["surface"]
        print(
            f"  {case_id}: actual_fields=(canonical_to_source_row, source_to_canonical_row); "
            f"permutation_round_trip=True; observation_canonical_lookup=True; domain={surface.canonical_index.size}"
        )

    case_ids = tuple(case_results)
    _require(len(case_ids) == 2, f"formal case count changed: {len(case_ids)}")
    left = case_results[case_ids[0]]["observations"]["upper"]
    right = case_results[case_ids[1]]["observations"]["upper"]
    source_canonical_equal = _byte_exact(left.source_canonical_index, right.source_canonical_index)
    source_row_equal = _byte_exact(left.source_row_index, right.source_row_index)
    temperature_equal = _byte_exact(left.wall_temperature_K, right.wall_temperature_K)
    hash_different = left.source_csv_sha256 != right.source_csv_sha256
    _require(source_canonical_equal, "cross-case upper source_canonical_index is not byte-exact")
    _require(left.sheet == right.sheet, "cross-case upper sheet differs")
    _require(left.column_name == right.column_name, "cross-case upper column_name differs")
    _require(left.unit == right.unit, "cross-case upper unit differs")
    for name in OBSERVATION_ARRAY_FIELDS:
        left_value = getattr(left, name)
        right_value = getattr(right, name)
        _require(left_value.dtype == right_value.dtype, f"cross-case {name} dtype differs")
        _require(left_value.shape == right_value.shape, f"cross-case {name} shape differs")
        _require(
            case_results[case_ids[0]]["contracts"]["upper"][name]
            == case_results[case_ids[1]]["contracts"]["upper"][name],
            f"cross-case {name} array contract differs",
        )
    _require(hash_different, "formal CSV hashes are unexpectedly identical")
    _require(not temperature_equal, "upper wall-temperature arrays were incorrectly reused byte-exactly")

    print("H. Cross-case comparison")
    print(f"  source_canonical_index_byte_exact={source_canonical_equal}")
    print(f"  source_row_index_byte_exact={source_row_equal} (reported, not required)")
    print("  sheet/column_name/unit byte-exact=True")
    print("  array dtype/shape/owned/C-contiguous/read-only contracts byte-exact=True")
    print(f"  CSV_hashes_different={hash_different}")
    print(f"  upper_temperature_arrays_byte_exact={temperature_equal} (required False)")

    print("I. CSV provenance")
    for case_id, result in case_results.items():
        upper = result["observations"]["upper"]
        lower = result["observations"]["lower"]
        print(
            f"  {case_id}: raw==upper==lower=True; lowercase_hex_64=True; "
            f"upper_lower_hash_same={upper.source_csv_sha256 == lower.source_csv_sha256}"
        )
    print("  cross_case_hash_different=True")

    print("J. Explicit prohibitions")
    print("  LF_temperature_prediction_read=False")
    print("  observation_prediction_error_computed=False")
    print("  accepted_passed_gate_created=False")
    print("  temperature_threshold_created=False")
    print("  area_weighting_created=False")
    print("  LF_target_aggregation_created=False")
    print("  observation_identity_uses_LF_target_cellnumber_nearest_tolerance=False")
    print("  provider_selection_created=False")

    _print_array_contracts(case_results)
    print("FORMAL FLUENT WALL-TEMPERATURE INGESTION QA: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(
            f"FORMAL FLUENT WALL-TEMPERATURE INGESTION QA: FAIL: "
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error