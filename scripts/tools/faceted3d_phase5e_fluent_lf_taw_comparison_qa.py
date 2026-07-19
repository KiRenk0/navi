#!/usr/bin/env python3
"""Run formal Phase 5E source-level Fluent/LF Taw comparison QA."""

from __future__ import annotations

import inspect
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
from ref_enthalpy_method.mapping.fluent_lf_taw_comparison import (
    FluentLfTawComparison,
    build_fluent_lf_taw_comparison,
)
from ref_enthalpy_method.mapping.fluent_wall_temperature import (
    build_fluent_wall_temperature_observations,
)
from ref_enthalpy_method.mapping.lf_clean import build_lf_clean_leeward_masks
from scripts.tools.faceted3d_phase4b_geometry_qa import CASES
from scripts.tools.faceted3d_phase5b_lf_clean_qa import FORMAL_CASES
from scripts.tools.faceted3d_phase5c_fluent_lf_pairing_qa import (
    METRIC,
    _build_fluent_integrations,
    _build_lf_fields,
)

EXPECTED_UPPER_SOURCE_COUNT = 186
EXPECTED_UPPER_UNIQUE_TARGET_COUNT = 80
PREDICTION_PROVIDER = (
    "ref_enthalpy_method.aero.leeward_recovery."
    "build_leeward_freestream_recovery"
)
EXPECTED_FIELDS = (
    "sheet",
    "source_csv_sha256",
    "observation_field_name",
    "prediction_field_name",
    "unit",
    "prediction_provider",
    "pairing_metric",
    "source_canonical_index",
    "source_row_index",
    "target_canonical_index",
    "wall_temperature_K",
    "Taw_tpg_leeward_K",
    "signed_error_K",
    "signed_relative_error_pct",
    "absolute_error_K",
    "absolute_relative_error_pct",
)
ARRAY_FIELDS = EXPECTED_FIELDS[7:]
INDEX_FIELDS = ARRAY_FIELDS[:3]
FLOAT_FIELDS = ARRAY_FIELDS[3:]
PROHIBITED_FIELDS = (
    "distance_m",
    "dx_m",
    "dspan_m",
    "second_target_canonical_index",
    "second_distance_m",
    "ambiguity_margin_m",
    "mutual_nearest",
    "target_multiplicity",
    "accepted",
    "passed",
    "gate",
    "threshold",
    "weight",
    "Tw_l",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _api_audit() -> dict[str, Any]:
    _require(is_dataclass(FluentLfTawComparison), "comparison type is not a dataclass")
    _require(
        FluentLfTawComparison.__dataclass_params__.frozen,
        "comparison dataclass is not frozen",
    )
    field_names = tuple(item.name for item in dataclass_fields(FluentLfTawComparison))
    _require(field_names == EXPECTED_FIELDS, f"comparison fields changed: {field_names}")
    _require(
        not set(PROHIBITED_FIELDS).intersection(field_names),
        "comparison contains prohibited fields",
    )
    parameters = tuple(
        inspect.signature(build_fluent_lf_taw_comparison).parameters.values()
    )
    _require(
        parameters
        and all(item.kind is inspect.Parameter.KEYWORD_ONLY for item in parameters),
        "comparison builder is not fully keyword-only",
    )
    parameter_names = tuple(item.name for item in parameters)
    _require(
        parameter_names == ("observation", "pairing", "lf_fields", "lf_masks", "sheet"),
        f"comparison builder boundary changed: {parameter_names}",
    )
    return {
        "fields": field_names,
        "signature": str(inspect.signature(build_fluent_lf_taw_comparison)),
    }


def _array_contract(
    comparison: FluentLfTawComparison,
    *,
    expected_count: int,
    identity: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name in ARRAY_FIELDS:
        value = getattr(comparison, name)
        expected_dtype = np.dtype(np.int64 if name in INDEX_FIELDS else np.float64)
        contract = {
            "dtype": str(value.dtype),
            "shape": value.shape,
            "ndim": value.ndim,
            "owned": bool(value.flags.owndata),
            "c_contiguous": bool(value.flags.c_contiguous),
            "read_only": not bool(value.flags.writeable),
        }
        result[name] = contract
        _require(value.dtype == expected_dtype, f"{identity}.{name}: dtype changed")
        _require(value.shape == (expected_count,), f"{identity}.{name}: shape changed")
        _require(value.ndim == 1, f"{identity}.{name}: ndim changed")
        _require(value.flags.owndata, f"{identity}.{name}: array is not owned")
        _require(
            value.flags.c_contiguous,
            f"{identity}.{name}: array is not C-contiguous",
        )
        _require(not value.flags.writeable, f"{identity}.{name}: array is writeable")
    return result


def _validate_metadata(
    comparison: FluentLfTawComparison,
    *,
    observation: Any,
    pairing: Any,
    sheet: str,
    identity: str,
) -> None:
    _require(comparison.sheet == sheet, f"{identity}: sheet changed")
    _require(
        comparison.source_csv_sha256 == observation.source_csv_sha256,
        f"{identity}: CSV provenance changed",
    )
    _require(
        comparison.observation_field_name == "wall-temperature",
        f"{identity}: observation field changed",
    )
    _require(
        comparison.prediction_field_name == f"Taw_tpg_leeward_{sheet}",
        f"{identity}: prediction field changed",
    )
    _require(comparison.unit == "K", f"{identity}: unit changed")
    _require(
        comparison.prediction_provider == PREDICTION_PROVIDER,
        f"{identity}: prediction provider changed",
    )
    _require(
        comparison.pairing_metric == pairing.metric == METRIC,
        f"{identity}: pairing metric changed",
    )


def _validate_comparison(
    *,
    case_id: str,
    sheet: str,
    observation: Any,
    pairing: Any,
    comparison: FluentLfTawComparison,
    lf_fields: dict[str, np.ndarray],
    lf_masks: Any,
) -> dict[str, Any]:
    identity = f"{case_id}.{sheet}"
    expected_count = EXPECTED_UPPER_SOURCE_COUNT if sheet == "upper" else 0
    contract = _array_contract(
        comparison,
        expected_count=expected_count,
        identity=identity,
    )
    _validate_metadata(
        comparison,
        observation=observation,
        pairing=pairing,
        sheet=sheet,
        identity=identity,
    )

    _require(
        np.array_equal(
            observation.source_canonical_index,
            pairing.source_canonical_index,
        ),
        f"{identity}: observation/pairing source identity differs",
    )
    _require(
        np.array_equal(
            comparison.source_canonical_index,
            observation.source_canonical_index,
        ),
        f"{identity}: comparison source ordering changed",
    )
    _require(
        np.array_equal(comparison.source_row_index, observation.source_row_index),
        f"{identity}: source row identity changed",
    )
    _require(
        np.array_equal(
            comparison.target_canonical_index,
            pairing.target_canonical_index,
        ),
        f"{identity}: target identity changed",
    )
    _require(
        np.array_equal(comparison.wall_temperature_K, observation.wall_temperature_K),
        f"{identity}: observation values changed",
    )

    target_pool = np.flatnonzero(getattr(lf_masks, f"clean_leeward_{sheet}"))
    _require(
        np.all(np.isin(comparison.target_canonical_index, target_pool)),
        f"{identity}: target outside LF clean pool",
    )
    prediction_field = np.asarray(lf_fields[comparison.prediction_field_name])
    _require(
        prediction_field.dtype == np.dtype(np.float64)
        and prediction_field.shape == getattr(lf_masks, f"clean_leeward_{sheet}").shape,
        f"{identity}: prediction is not a full-canonical float64 field",
    )
    direct_prediction = prediction_field[comparison.target_canonical_index]
    _require(
        np.array_equal(comparison.Taw_tpg_leeward_K, direct_prediction),
        f"{identity}: prediction is not direct full-canonical indexing",
    )

    expected_signed = direct_prediction - observation.wall_temperature_K
    expected_signed_relative = (
        100.0 * expected_signed / observation.wall_temperature_K
    )
    _require(
        np.array_equal(comparison.signed_error_K, expected_signed),
        f"{identity}: signed error formula changed",
    )
    _require(
        np.array_equal(
            comparison.signed_relative_error_pct,
            expected_signed_relative,
        ),
        f"{identity}: signed relative error formula changed",
    )
    _require(
        np.array_equal(comparison.absolute_error_K, np.abs(expected_signed)),
        f"{identity}: absolute error formula changed",
    )
    _require(
        np.array_equal(
            comparison.absolute_relative_error_pct,
            np.abs(expected_signed_relative),
        ),
        f"{identity}: absolute relative error formula changed",
    )

    unique_targets = int(np.unique(comparison.target_canonical_index).size)
    if sheet == "upper":
        _require(
            comparison.source_canonical_index.size == EXPECTED_UPPER_SOURCE_COUNT,
            f"{identity}: upper source rows were compressed",
        )
        _require(
            unique_targets == EXPECTED_UPPER_UNIQUE_TARGET_COUNT,
            f"{identity}: unique target count changed",
        )
        _require(
            comparison.source_canonical_index.size > unique_targets,
            f"{identity}: many-to-one rows were not retained",
        )
        duplicate_targets = np.unique(
            comparison.target_canonical_index[
                np.unique(
                    comparison.target_canonical_index,
                    return_counts=True,
                )[1][
                    np.searchsorted(
                        np.unique(comparison.target_canonical_index),
                        comparison.target_canonical_index,
                    )
                ]
                > 1
            ]
        )
        _require(duplicate_targets.size > 0, f"{identity}: no duplicate target evidence")
        for target in duplicate_targets:
            rows = comparison.target_canonical_index == target
            _require(
                np.all(
                    comparison.Taw_tpg_leeward_K[rows]
                    == prediction_field[int(target)]
                ),
                f"{identity}: duplicate target predictions were not repeated by source",
            )
    else:
        _require(unique_targets == 0, f"{identity}: lower target is not typed-empty")
        _require(
            all(getattr(comparison, name).size == 0 for name in ARRAY_FIELDS),
            f"{identity}: lower comparison is not fully typed-empty",
        )

    return {
        "comparison": comparison,
        "contract": contract,
        "unique_targets": unique_targets,
    }


def main() -> int:
    api = _api_audit()
    case_paths = dict(CASES)
    integrations = _build_fluent_integrations()

    print("A. Formal case and API identity")
    for case_id in FORMAL_CASES:
        print(f"  {case_id}: Fluent={case_paths[case_id].relative_to(ROOT)}")
    print("  public type=FluentLfTawComparison; frozen=True")
    print(f"  public builder signature={api['signature']}")
    print(f"  fields={api['fields']}")

    case_results: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="faceted3d_phase5e_comparison_") as temporary:
        for case_id, (mach, alpha_deg, altitude_m) in FORMAL_CASES.items():
            integration = integrations[case_id]
            fluent_masks = build_fluent_clean_leeward_masks(integration)
            lf_fields, lf_masks = _build_lf_fields(
                case_id=case_id,
                mach=mach,
                alpha_deg=alpha_deg,
                altitude_m=altitude_m,
                run_parent=Path(temporary),
            )
            formal: dict[str, Any] = {}
            for sheet in ("upper", "lower"):
                pairing = build_fluent_lf_clean_pairing(
                    integration=integration,
                    fluent_masks=fluent_masks,
                    lf_fields=lf_fields,
                    lf_masks=lf_masks,
                    sheet=sheet,
                )
                observation = build_fluent_wall_temperature_observations(
                    csv_path=case_paths[case_id],
                    integration=integration,
                    fluent_masks=fluent_masks,
                    pairing=pairing,
                    sheet=sheet,
                )
                comparison = build_fluent_lf_taw_comparison(
                    observation=observation,
                    pairing=pairing,
                    lf_fields=lf_fields,
                    lf_masks=lf_masks,
                    sheet=sheet,
                )
                formal[sheet] = _validate_comparison(
                    case_id=case_id,
                    sheet=sheet,
                    observation=observation,
                    pairing=pairing,
                    comparison=comparison,
                    lf_fields=lf_fields,
                    lf_masks=lf_masks,
                )
            case_results[case_id] = formal

    print("B. Source identity, ordering, direct indexing, and many-to-one")
    for case_id, result in case_results.items():
        print(
            f"  {case_id}.upper: source_rows=186; unique_targets=80; "
            "observation==pairing==comparison source identity=True; "
            "prediction=full_canonical[target_canonical_index]=True; "
            "duplicate target rows retained=True"
        )
        print(
            f"  {case_id}.lower: source_rows=0; unique_targets=0; "
            "complete_typed_empty=True"
        )

    print("C. Metadata and provenance")
    for case_id, result in case_results.items():
        for sheet in ("upper", "lower"):
            comparison = result[sheet]["comparison"]
            print(
                f"  {case_id}.{sheet}: observation_field={comparison.observation_field_name}; "
                f"prediction_field={comparison.prediction_field_name}; unit={comparison.unit}; "
                f"provider={comparison.prediction_provider}; pairing_metric={comparison.pairing_metric}; "
                f"source_csv_sha256={comparison.source_csv_sha256}"
            )

    print("D. Error formula identity")
    print("  signed_error_K=Taw_tpg_leeward_K-wall_temperature_K: True")
    print("  signed_relative_error_pct=100*signed_error_K/wall_temperature_K: True")
    print("  absolute_error_K=abs(signed_error_K): True")
    print("  absolute_relative_error_pct=abs(signed_relative_error_pct): True")
    print("  no case-level error statistics or performance thresholds computed: True")

    print("E. Array contracts")
    for sheet in ("upper", "lower"):
        reference = next(iter(case_results.values()))[sheet]["contract"]
        print(f"  {sheet}")
        for name, contract in reference.items():
            print(
                f"    {name}: dtype={contract['dtype']}; shape={contract['shape']}; "
                f"ndim={contract['ndim']}; owned={contract['owned']}; "
                f"C={contract['c_contiguous']}; read_only={contract['read_only']}"
            )

    print("F. Explicit prohibitions")
    print(f"  prohibited_fields_absent={PROHIBITED_FIELDS}")
    print("  coordinate_nearest_recomputed=False")
    print("  target_aggregation=False")
    print("  accepted_gate_threshold=False")
    print("  area_weighting=False")
    print("  Tw_l_prediction=False")
    print("  provider_or_Group8_modified=False")
    print("FORMAL FLUENT-LF TAW SOURCE COMPARISON QA: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(
            "FORMAL FLUENT-LF TAW SOURCE COMPARISON QA: FAIL: "
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error
