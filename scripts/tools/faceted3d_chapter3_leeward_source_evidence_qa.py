#!/usr/bin/env python3
"""End-to-end formal QA for Chapter 3 leeward source evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for _path in (ROOT, SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.tools.generate_leeward_source_evidence import (
    CASE_REGISTRY,
    COMPARISON_CONTRACT_ID,
    ERROR_FIELDS,
    MANIFEST_SCHEMA,
    RAW_FIELD_DTYPES,
    RAW_FIELD_NAMES,
    STATUS_SEMANTICS,
    SUMMARY_SCHEMA,
    generate_evidence,
    sha256_file,
)

EXPECTED = {
    "ma6_a5_h30km": (186, 80),
    "ma8_a5_h40km": (186, 80),
}
PROHIBITED_STATUS_TERMS = (
    "acceptable_error", "threshold_passed", "model_performance_passed"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_raw(path: Path, *, case_id: str, sheet: str) -> dict[str, Any]:
    _require(path.is_file(), f"missing raw evidence: {path}")
    with np.load(path, allow_pickle=False) as raw:
        _require(tuple(raw.files) == RAW_FIELD_NAMES, f"{case_id}.{sheet}: raw member order changed")
        arrays = {name: np.array(raw[name], copy=True) for name in raw.files}
    count = arrays["source_canonical_index"].size
    for name, dtype_text in RAW_FIELD_DTYPES:
        expected_shape = () if name in RAW_FIELD_NAMES[:8] else (count,)
        _require(arrays[name].dtype == np.dtype(dtype_text), f"{case_id}.{sheet}.{name}: dtype changed")
        _require(arrays[name].shape == expected_shape, f"{case_id}.{sheet}.{name}: shape changed")
        _require(not arrays[name].dtype.hasobject, f"{case_id}.{sheet}.{name}: object dtype")
        if name not in RAW_FIELD_NAMES[:8] and np.issubdtype(arrays[name].dtype, np.floating):
            _require(np.all(np.isfinite(arrays[name])), f"{case_id}.{sheet}.{name}: non-finite")
    _require(str(arrays["case_id"].item()) == case_id, f"{case_id}.{sheet}: case identity changed")
    _require(str(arrays["sheet"].item()) == sheet, f"{case_id}.{sheet}: sheet identity changed")
    _require(str(arrays["comparison_contract_id"].item()) == COMPARISON_CONTRACT_ID, f"{case_id}.{sheet}: comparison contract changed")
    _require(str(arrays["observation_field_name"].item()) == "wall-temperature", f"{case_id}.{sheet}: observation field changed")
    _require(str(arrays["prediction_field_name"].item()) == f"Taw_tpg_leeward_{sheet}", f"{case_id}.{sheet}: prediction field changed")
    _require(str(arrays["pairing_metric"].item()) == "projected_physical_x_span_euclidean_m", f"{case_id}.{sheet}: metric changed")
    _require("leeward_recovery.build_leeward_freestream_recovery" in str(arrays["prediction_provider"].item()), f"{case_id}.{sheet}: provider changed")
    if count:
        _require(np.all(arrays["source_canonical_index"][1:] > arrays["source_canonical_index"][:-1]), f"{case_id}.{sheet}: comparison ordering changed")
        _require(np.unique(arrays["source_canonical_index"]).size == count, f"{case_id}.{sheet}: source rows not preserved")
        _require(np.unique(arrays["source_row_index"]).size == count, f"{case_id}.{sheet}: source-row identity duplicated")
        _require(np.all(arrays["diagnostic_target_multiplicity"] >= 1), f"{case_id}.{sheet}: invalid multiplicity")
    return {
        "arrays": arrays,
        "source_rows": int(count),
        "unique_targets": int(np.unique(arrays["target_canonical_index"]).size),
        "typed_empty": count == 0,
    }


def _validate_summary(path: Path, *, case_id: str, raw: dict[str, dict[str, Any]]) -> None:
    summary = _load_json(path)
    _require(summary.get("summary_schema") == SUMMARY_SCHEMA, f"{case_id}: summary schema changed")
    _require(summary.get("case_id") == case_id, f"{case_id}: summary identity changed")
    _require(summary.get("comparison_contract_id") == COMPARISON_CONTRACT_ID, f"{case_id}: summary comparison contract changed")
    _require(summary.get("population") == "fluent_source_rows_equal_weight", f"{case_id}: source-row weighting changed")
    _require(summary.get("provenance_ref") == "../../manifest.json", f"{case_id}: provenance reference changed")
    _require(summary.get("run_status") == "PASS" and summary.get("status_semantics") == STATUS_SEMANTICS, f"{case_id}: status semantics changed")
    _require(summary.get("model_performance_assessment") == "not_performed", f"{case_id}: model performance assessment introduced")
    serialized = json.dumps(summary, sort_keys=True)
    _require(not any(term in serialized for term in PROHIBITED_STATUS_TERMS), f"{case_id}: prohibited performance status")
    for sheet in ("upper", "lower"):
        sheet_summary = summary["sheets"][sheet]
        evidence = raw[sheet]
        _require(sheet_summary["source_row_count"] == evidence["source_rows"], f"{case_id}.{sheet}: summary row count mismatch")
        _require(sheet_summary["unique_target_count"] == evidence["unique_targets"], f"{case_id}.{sheet}: summary target count mismatch")
        _require(sheet_summary["typed_empty"] is evidence["typed_empty"], f"{case_id}.{sheet}: typed-empty mismatch")
        if evidence["typed_empty"]:
            _require(all(block == {"count": 0, "status": "typed_empty"} for block in sheet_summary["error_statistics"].values()), f"{case_id}.{sheet}: ambiguous empty statistics")
            _require(sheet_summary["prediction_direction"] == {"count": 0, "status": "typed_empty"}, f"{case_id}.{sheet}: empty direction fraction fabricated")
        else:
            arrays = evidence["arrays"]
            for name in ERROR_FIELDS:
                block = sheet_summary["error_statistics"][name]
                _require(block["count"] == evidence["source_rows"], f"{case_id}.{sheet}.{name}: statistic population changed")
                _require(block["median"] == block["p50"], f"{case_id}.{sheet}.{name}: quantile rule differs")
            direction = sheet_summary["prediction_direction"]
            _require(direction["overprediction_count"] + direction["underprediction_count"] + direction["exact_zero_count"] == evidence["source_rows"], f"{case_id}.{sheet}: direction conservation failed")
            signed = arrays["signed_error_K"]
            _require(direction["overprediction_count"] == int(np.count_nonzero(signed > 0)), f"{case_id}.{sheet}: overprediction changed")
            _require(direction["underprediction_count"] == int(np.count_nonzero(signed < 0)), f"{case_id}.{sheet}: underprediction changed")
            _require(direction["exact_zero_count"] == int(np.count_nonzero(signed == 0.0)), f"{case_id}.{sheet}: exact zero changed")


def _validate_png(path: Path, *, case_id: str, sheet: str, role: str, run_id: str) -> None:
    _require(path.is_file(), f"missing PNG: {path}")
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        info = image.info
        _require(info.get("case_id") == case_id and info.get("sheet") == sheet, f"{path}: PNG identity changed")
        _require(info.get("coordinate_fields") == "source_projected_x_m,source_projected_span_m", f"{path}: PNG coordinate identity changed")
        _require(info.get("comparison_contract_id") == COMPARISON_CONTRACT_ID, f"{path}: PNG comparison contract changed")
        _require(info.get("run_id") == run_id, f"{path}: PNG run identity changed")
        _require(info.get("evidence_role") == role, f"{path}: PNG evidence role changed")
        _require(info.get("manifest_relative_reference") == "../../../../../manifest.json", f"{path}: PNG manifest reference changed")


def validate_run(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    detached_path = run_dir / "manifest.sha256"
    manifest = _load_json(manifest_path)
    _require(manifest.get("manifest_schema") == MANIFEST_SCHEMA, "manifest schema changed")
    _require(manifest.get("run_id") == run_dir.name, "manifest/run directory identity mismatch")
    _require(manifest.get("run_status") == "PASS" and manifest.get("status_semantics") == STATUS_SEMANTICS, "manifest status semantics changed")
    _require(manifest.get("model_performance_assessment") == "not_performed", "manifest model performance assessment introduced")
    _require(tuple(manifest["case_registry"]) == tuple(EXPECTED), "formal registry changed")
    _require(tuple(manifest["cases"]) == tuple(EXPECTED), "formal case provenance changed")
    _require(not any(term in json.dumps(manifest, sort_keys=True) for term in PROHIBITED_STATUS_TERMS), "manifest contains performance threshold status")

    manifest_hash = _sha256(manifest_path)
    detached_parts = detached_path.read_text(encoding="ascii").split()
    _require(detached_parts == [manifest_hash, "manifest.json"], "detached manifest hash verification failed")

    for identity in manifest["generator"].values():
        path = ROOT / identity["path"]
        _require(path.is_file() and sha256_file(path) == identity["raw_sha256"], f"generator source hash mismatch: {identity['path']}")
    for case_id, provenance in manifest["cases"].items():
        _require(provenance["case_id"] == case_id, f"{case_id}: provenance identity changed")
        for input_identity in provenance["inputs"].values():
            path = ROOT / input_identity["path"]
            _require(path.is_file(), f"{case_id}: missing provenance input")
            _require(path.stat().st_size == input_identity["byte_size"], f"{case_id}: input size mismatch")
            _require(sha256_file(path) == input_identity["raw_sha256"], f"{case_id}: input hash mismatch")
        for artifact, registered in provenance["baseline_artifact_hashes_sha256"].items():
            key = "lf_fields" if artifact == "fields.npz" else "lf_summary" if artifact == "summary.json" else None
            if key:
                _require(provenance["inputs"][key]["raw_sha256"] == registered, f"{case_id}: baseline artifact registration mismatch")

    inventory = manifest["artifact_hashes_sha256"]
    _require(len({item["filename"] for item in inventory}) == len(inventory), "duplicate artifact inventory path")
    for item in inventory:
        path = run_dir / item["filename"]
        _require(path.is_file(), f"missing inventory artifact: {item['filename']}")
        _require(path.stat().st_size == item["byte_size"], f"artifact size mismatch: {item['filename']}")
        _require(_sha256(path) == item["raw_sha256"], f"artifact hash mismatch: {item['filename']}")
    _require("manifest.json" not in {item["filename"] for item in inventory}, "manifest self-hash introduced")
    _require("manifest.sha256" not in {item["filename"] for item in inventory}, "detached self-hash introduced")

    case_counts: dict[str, Any] = {}
    for case_id, (expected_rows, expected_targets) in EXPECTED.items():
        case_dir = run_dir / "cases" / case_id
        raw = {
            sheet: _validate_raw(case_dir / "sheets" / sheet / "raw_evidence.npz", case_id=case_id, sheet=sheet)
            for sheet in ("upper", "lower")
        }
        _require(raw["upper"]["source_rows"] == expected_rows, f"{case_id}: upper source rows changed")
        _require(raw["upper"]["unique_targets"] == expected_targets, f"{case_id}: upper unique targets changed")
        _require(expected_rows > expected_targets, f"{case_id}: many-to-one evidence absent")
        _require(raw["lower"]["typed_empty"] and raw["lower"]["unique_targets"] == 0, f"{case_id}: lower is not typed-empty")
        _validate_summary(case_dir / "summary.json", case_id=case_id, raw=raw)
        figures = case_dir / "sheets" / "upper" / "figures"
        _validate_png(figures / "source_errors_fixed.png", case_id=case_id, sheet="upper", role="formal_evidence", run_id=run_dir.name)
        _validate_png(figures / "source_errors_adaptive.png", case_id=case_id, sheet="upper", role="formal_evidence", run_id=run_dir.name)
        _validate_png(figures / "diagnostic_source_target_multiplicity.png", case_id=case_id, sheet="upper", role="diagnostic_only", run_id=run_dir.name)
        _require(not (case_dir / "sheets" / "lower" / "figures").exists(), f"{case_id}: lower fabricated PNG exists")
        case_counts[case_id] = {"upper_source_rows": expected_rows, "upper_unique_targets": expected_targets, "lower_typed_empty": True}

    formal_count = sum(item["evidence_role"] == "formal_evidence" for item in inventory)
    diagnostic_count = sum(item["evidence_role"] == "diagnostic_only" for item in inventory)
    return {
        "run_id": run_dir.name, "output_root": str(run_dir.parent), "case_counts": case_counts,
        "artifact_count": len(inventory), "manifest_sha256": manifest_hash,
        "detached_verified": True, "formal_evidence_count": formal_count,
        "diagnostic_count": diagnostic_count,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    run_dir = generate_evidence(output_root=args.output_root, case_ids=tuple(CASE_REGISTRY))
    result = validate_run(run_dir)
    print(f"validation run id: {result['run_id']}")
    print(f"validation output root: {result['output_root']}")
    for case_id, counts in result["case_counts"].items():
        print(f"{case_id}: upper source rows={counts['upper_source_rows']}; upper unique targets={counts['upper_unique_targets']}; lower typed-empty={counts['lower_typed_empty']}")
    print(f"artifact count: {result['artifact_count']}")
    print(f"manifest raw SHA-256: {result['manifest_sha256']}")
    print(f"detached manifest hash verification: {result['detached_verified']}")
    print(f"formal evidence assets: {result['formal_evidence_count']}")
    print(f"diagnostic-only assets: {result['diagnostic_count']}")
    print("model performance assessment: not_performed")
    print("Chapter 3 leeward source evidence QA: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Chapter 3 leeward source evidence QA: FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1) from error