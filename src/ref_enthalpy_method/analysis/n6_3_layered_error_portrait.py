"""Build and validate the frozen N6.3 layered error portrait package.

The module consumes only the approved N6.2b raw evidence package.  It never
calls the solver, pairing builder, comparison builder, or an observation
provider.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from collections import Counter, OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, TwoSlopeNorm
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
CANONICAL_PACKAGE_PATH = (
    "runs/n6_exact_custom_formal/"
    "20260724T111443Z_79ed536fc8c1_n6_exact_custom"
)
DEFAULT_OUTPUT_ROOT = ROOT / "runs" / "n6_3_layered_error_portrait"
FORMAL_CASE_IDS = ("ma6_a5_h30km", "ma8_a5_h40km")
SHEET_ORDER = ("upper", "lower")
PACKAGE_MANIFEST_SHA256 = "dffd989a057c4481446482e0543e935209e8673f1a4468b343f1dfa5785bc314"
EVIDENCE_MANIFEST_SHA256 = "b161086640e0e1c922fd2c02670f7e43f9b01363a797dfabb39c195f34157ac3"
SOURCE_PACKAGE_GENERATION_SHA = "79ed536fc8c1c7e19811ca744a14b78a732ff71a"
RAW_SHA256 = {
    "ma6_a5_h30km": {
        "upper": "56e8feaf49904d1214d2350fa08c1a0753dcc9061d492e8ef154e1bdc3f1b01b",
        "lower": "a1487dff880d0200ff3bedb74f2e37eb8f798b5a216ba88761ed2ea2eec8e923",
    },
    "ma8_a5_h40km": {
        "upper": "208374a66dfa8445cc63c854d8174eefd2cb7d932013798624d41aac2fbf22a8",
        "lower": "e97b8b9e342908d4787e53bfc339d54947a5e2a3570f1e503ffc1e8172c10c3c",
    },
}
ANALYSIS_MANIFEST_SCHEMA = "faceted3d-n6-3-layered-error-portrait-manifest/v1"
FORMAL_PROFILE_SCHEMA = "faceted3d-n6-3-layered-error-profile/v1"
DIAGNOSTIC_PROFILE_SCHEMA = "faceted3d-n6-3-layered-error-diagnostic/v1"
DIAGNOSTIC_CONTEXT_SCHEMA = "faceted3d-n6-3-diagnostic-context/v1"
RAW_SCHEMA = "faceted3d-leeward-source-raw/v1"
RAW_FIELD_DTYPES = (
    ("case_id", "<U16"), ("sheet", "<U5"),
    ("comparison_contract_id", "<U48"), ("source_csv_sha256", "<U64"),
    ("observation_field_name", "<U32"), ("prediction_field_name", "<U32"),
    ("prediction_provider", "<U128"), ("pairing_metric", "<U64"),
    ("source_canonical_index", "int64"), ("source_row_index", "int64"),
    ("target_canonical_index", "int64"), ("source_projected_x_m", "float64"),
    ("source_projected_span_m", "float64"), ("source_projected_up_m", "float64"),
    ("wall_temperature_K", "float64"), ("Taw_tpg_leeward_K", "float64"),
    ("signed_error_K", "float64"), ("signed_relative_error_pct", "float64"),
    ("absolute_error_K", "float64"), ("absolute_relative_error_pct", "float64"),
    ("diagnostic_pairing_distance_m", "float64"),
    ("diagnostic_pairing_dx_m", "float64"),
    ("diagnostic_pairing_dspan_m", "float64"),
    ("diagnostic_target_multiplicity", "int64"),
)
RAW_FIELD_NAMES = tuple(name for name, _dtype in RAW_FIELD_DTYPES)
SCALAR_FIELDS = frozenset(RAW_FIELD_NAMES[:8])
ERROR_FIELDS = (
    "signed_error_K",
    "signed_relative_error_pct",
    "absolute_error_K",
    "absolute_relative_error_pct",
)
EXPECTED_OUTPUT_PATHS = (
    "diagnostic_context/tier_references.json",
    "diagnostic_only/multiplicity_profiles.json",
    "formal_core/bounded_case_comparison.json",
    "formal_core/figures/coordinate_bin_profiles.png",
    "formal_core/figures/error_distributions.png",
    "formal_core/figures/source_error_maps_fixed.png",
    "formal_core/source_profiles.json",
    "formal_core/spatial_bin_profiles.json",
)
IMPLEMENTATION_PATHS = (
    "src/ref_enthalpy_method/analysis/__init__.py",
    "src/ref_enthalpy_method/analysis/n6_3_layered_error_portrait.py",
    "scripts/tools/n6_3_layered_error_portrait.py",
)
CONTEXT_PATHS = (
    "src/ref_enthalpy_method/mapping/m8h30_comparison_inputs.py",
    "src/ref_enthalpy_method/mapping/observation_binding.py",
    "tests/test_m8h30_comparison_inputs.py",
    "runs/20260714_12case_windward_error_rerun/12case_windward_error_summary.json",
    "runs/20260714_12case_windward_error_rerun/ma8_a5_h30km__windward_error_stats.json",
    "scripts/viz/plot_windward_error_vs_fluent.py",
)
CASE_FACTS = OrderedDict(
    (
        (
            "ma6_a5_h30km",
            {
                "Mach": 6.0,
                "alpha_deg": 5.0,
                "nominal_altitude_label": "30 km",
                "exact_custom_T_inf_K": 226.509,
                "exact_custom_p_inf_Pa": 1197.0,
            },
        ),
        (
            "ma8_a5_h40km",
            {
                "Mach": 8.0,
                "alpha_deg": 5.0,
                "nominal_altitude_label": "40 km",
                "exact_custom_T_inf_K": 251.0,
                "exact_custom_p_inf_Pa": 287.0,
            },
        ),
    )
)


class AnalysisContractError(RuntimeError):
    """Fail-closed input, output, or publication contract failure."""


@dataclass(frozen=True)
class SourcePackageExpectation:
    package_manifest_sha256: str = PACKAGE_MANIFEST_SHA256
    evidence_manifest_sha256: str = EVIDENCE_MANIFEST_SHA256
    source_generation_git_sha: str = SOURCE_PACKAGE_GENERATION_SHA
    raw_sha256: Mapping[str, Mapping[str, str]] | None = None

    def raw_hashes(self) -> Mapping[str, Mapping[str, str]]:
        return self.raw_sha256 or RAW_SHA256


@dataclass(frozen=True)
class ValidatedSourcePackage:
    root: Path
    repo_relative_path: str
    package_manifest: Mapping[str, Any]
    evidence_manifest: Mapping[str, Any]
    evidence_root: Path
    arrays: Mapping[str, Mapping[str, Mapping[str, np.ndarray]]]
    summaries: Mapping[str, Mapping[str, Any]]
    raw_paths: Mapping[str, Mapping[str, str]]
    raw_sha256: Mapping[str, Mapping[str, str]]


@dataclass(frozen=True)
class ExecutionIdentity:
    created_at_utc: str
    generation_git_sha: str
    source_identity: Mapping[str, Any]
    source_hashes_sha256: Mapping[str, str]
    exact_execution_command: tuple[str, ...]


@dataclass(frozen=True)
class AnalysisPublication:
    analysis_root: Path
    run_id: str
    generation_git_sha: str
    manifest_sha256: str
    artifact_inventory_count: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AnalysisContractError(message)


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise AnalysisContractError(f"{label} is not strict UTF-8 JSON: {path}") from exc
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=False)
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise AnalysisContractError(f"path is outside repository: {path}") from exc


def _resolve_path(
    path: str | Path,
    *,
    must_exist: bool = True,
    repository_bound: bool = False,
) -> Path:
    candidate = Path(path)
    resolved = candidate.resolve() if candidate.is_absolute() else (ROOT / candidate).resolve()
    if repository_bound:
        _repo_relative(resolved)
    if must_exist and not resolved.exists():
        raise AnalysisContractError(f"path does not exist: {path}")
    return resolved


def _validate_hash(value: Any, *, label: str, length: int = 64) -> str:
    _require(
        isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None,
        f"{label} is not a lowercase hexadecimal digest",
    )
    return value


def _validate_inventory(root: Path, inventory: Any, *, excluded: frozenset[str]) -> None:
    _require(isinstance(inventory, list), "artifact inventory must be a list")
    paths: list[str] = []
    for entry in inventory:
        _require(isinstance(entry, dict), "artifact inventory entry must be an object")
        _require(tuple(entry) == ("path", "byte_size", "raw_sha256"), "artifact inventory entry schema mismatch")
        path_text = entry["path"]
        _require(
            isinstance(path_text, str)
            and path_text
            and "\\" not in path_text
            and not Path(path_text).is_absolute()
            and ".." not in Path(path_text).parts,
            "artifact inventory path is not safe repo-relative POSIX",
        )
        path = root / path_text
        _require(path.is_file(), f"artifact inventory file is missing: {path_text}")
        _require(path.stat().st_size == entry["byte_size"], f"artifact inventory size mismatch: {path_text}")
        _require(sha256_file(path) == entry["raw_sha256"], f"artifact inventory hash mismatch: {path_text}")
        paths.append(path_text)
    _require(paths == sorted(paths), "artifact inventory paths are not deterministic")
    _require(len(paths) == len(set(paths)), "artifact inventory contains duplicate paths")
    disk_paths = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() not in excluded
    )
    _require(paths == disk_paths, "artifact inventory does not exactly cover package files")


def _evidence_inventory_map(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    entries = manifest.get("artifact_hashes_sha256")
    _require(isinstance(entries, list), "evidence artifact inventory must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        _require(isinstance(entry, dict), "evidence artifact entry must be an object")
        filename = entry.get("filename")
        _require(isinstance(filename, str) and filename not in result, "evidence artifact filename invalid")
        result[filename] = entry
    return result


def _load_raw(
    path: Path,
    *,
    case_id: str,
    sheet: str,
    expected_sha256: str,
    evidence_case: Mapping[str, Any],
) -> dict[str, np.ndarray]:
    _require(sha256_file(path) == expected_sha256, f"{case_id}/{sheet}: raw artifact SHA-256 mismatch")
    try:
        with np.load(path, allow_pickle=False) as archive:
            _require(tuple(archive.files) == RAW_FIELD_NAMES, f"{case_id}/{sheet}: raw NPZ member order mismatch")
            arrays = {name: np.array(archive[name], copy=True, order="C") for name in archive.files}
    except (OSError, ValueError) as exc:
        raise AnalysisContractError(f"{case_id}/{sheet}: raw NPZ failed safe loading") from exc

    count = 186 if sheet == "upper" else 0
    for name, dtype_text in RAW_FIELD_DTYPES:
        value = arrays[name]
        expected_shape = () if name in SCALAR_FIELDS else (count,)
        _require(value.dtype == np.dtype(dtype_text), f"{case_id}/{sheet}: {name} dtype mismatch")
        _require(value.shape == expected_shape, f"{case_id}/{sheet}: {name} shape mismatch")
        if np.issubdtype(value.dtype, np.floating):
            _require(np.all(np.isfinite(value)), f"{case_id}/{sheet}: {name} contains non-finite values")

    sheet_manifest = evidence_case["sheets"][sheet]
    expected_scalars = {
        "case_id": case_id,
        "sheet": sheet,
        "comparison_contract_id": evidence_case["comparison_api"]["contract_id"],
        "source_csv_sha256": evidence_case["inputs"]["fluent_csv"]["raw_sha256"],
        "observation_field_name": sheet_manifest["observation_field"],
        "prediction_field_name": sheet_manifest["prediction_field"],
        "prediction_provider": sheet_manifest["prediction_provider"],
        "pairing_metric": sheet_manifest["pairing_metric"],
    }
    for name, expected in expected_scalars.items():
        _require(str(arrays[name].item()) == expected, f"{case_id}/{sheet}: {name} scalar identity mismatch")

    source_index = arrays["source_canonical_index"]
    _require(
        source_index.size == 0 or (np.all(np.diff(source_index) > 0) and np.unique(source_index).size == source_index.size),
        f"{case_id}/{sheet}: source_canonical_index is not strictly increasing and unique",
    )
    target = arrays["target_canonical_index"]
    unique_targets, target_counts = np.unique(target, return_counts=True)
    expected_unique = 80 if sheet == "upper" else 0
    _require(unique_targets.size == expected_unique, f"{case_id}/{sheet}: unique target count mismatch")
    if count:
        multiplicity = dict(zip(unique_targets.tolist(), target_counts.tolist()))
        actual = np.asarray([multiplicity[int(index)] for index in target], dtype=np.int64)
        _require(
            np.array_equal(actual, arrays["diagnostic_target_multiplicity"]),
            f"{case_id}/{sheet}: many-to-one multiplicity was not preserved",
        )

    wall = arrays["wall_temperature_K"]
    prediction = arrays["Taw_tpg_leeward_K"]
    _require(np.all(wall > 0.0), f"{case_id}/{sheet}: wall temperature must be positive")
    signed = prediction - wall
    relative = 100.0 * signed / wall
    formulas = {
        "signed_error_K": signed,
        "signed_relative_error_pct": relative,
        "absolute_error_K": np.abs(signed),
        "absolute_relative_error_pct": np.abs(relative),
    }
    for field, expected in formulas.items():
        _require(np.array_equal(arrays[field], expected), f"{case_id}/{sheet}: frozen error formula mismatch: {field}")
    for value in arrays.values():
        value.setflags(write=False)
    return arrays


def _legacy_statistics(values: np.ndarray) -> dict[str, Any]:
    quantiles = np.quantile(values, [0.05, 0.25, 0.50, 0.75, 0.95], method="linear")
    return {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "median": float(quantiles[2]),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "p05": float(quantiles[0]),
        "p25": float(quantiles[1]),
        "p50": float(quantiles[2]),
        "p75": float(quantiles[3]),
        "p95": float(quantiles[4]),
    }


def _validate_summary(case_id: str, summary: Mapping[str, Any], sheets: Mapping[str, Mapping[str, np.ndarray]]) -> None:
    _require(summary.get("summary_schema") == "faceted3d-leeward-source-summary/v1", f"{case_id}: summary schema mismatch")
    _require(summary.get("case_id") == case_id, f"{case_id}: summary case identity mismatch")
    _require(summary.get("comparison_contract_id") == "fluent-lf-taw-comparison/v1", f"{case_id}: comparison contract mismatch")
    _require(summary.get("population") == "fluent_source_rows_equal_weight", f"{case_id}: population mismatch")
    _require(summary.get("run_status") == "PASS", f"{case_id}: source summary status mismatch")
    _require(summary.get("model_performance_assessment") == "not_performed", f"{case_id}: source summary performance semantics mismatch")
    for sheet in SHEET_ORDER:
        arrays = sheets[sheet]
        observed = summary["sheets"][sheet]
        count = int(arrays["source_canonical_index"].size)
        unique = int(np.unique(arrays["target_canonical_index"]).size)
        _require(observed["source_row_count"] == count, f"{case_id}/{sheet}: summary/raw row mismatch")
        _require(observed["unique_target_count"] == unique, f"{case_id}/{sheet}: summary/raw target mismatch")
        _require(observed["typed_empty"] is (count == 0), f"{case_id}/{sheet}: summary/raw typed-empty mismatch")
        if count == 0:
            continue
        for field in ERROR_FIELDS:
            expected = _legacy_statistics(arrays[field])
            _require(observed["error_statistics"][field] == expected, f"{case_id}/{sheet}: summary/raw statistics mismatch: {field}")
        signed = arrays["signed_error_K"]
        over = int(np.count_nonzero(signed > 0.0))
        under = int(np.count_nonzero(signed < 0.0))
        zero = int(np.count_nonzero(signed == 0.0))
        direction = observed["prediction_direction"]
        _require(direction["overprediction_count"] == over, f"{case_id}: overprediction summary mismatch")
        _require(direction["underprediction_count"] == under, f"{case_id}: underprediction summary mismatch")
        _require(direction["exact_zero_count"] == zero, f"{case_id}: zero summary mismatch")
        _require(direction["overprediction_fraction"] == over / count, f"{case_id}: overprediction fraction mismatch")
        _require(direction["underprediction_fraction"] == under / count, f"{case_id}: underprediction fraction mismatch")
        _require(direction["exact_zero_fraction"] == zero / count, f"{case_id}: zero fraction mismatch")
        multiplicities, row_counts = np.unique(
            arrays["diagnostic_target_multiplicity"], return_counts=True
        )
        expected_histogram = {
            str(int(multiplicity)): int(row_count)
            for multiplicity, row_count in zip(multiplicities, row_counts)
        }
        _require(
            observed["target_multiplicity"] == {
                "diagnostic_only": True,
                "histogram": expected_histogram,
            },
            f"{case_id}: target multiplicity summary mismatch",
        )


def validate_source_package(
    package_root: str | Path = CANONICAL_PACKAGE_PATH,
    *,
    expectation: SourcePackageExpectation | None = None,
) -> ValidatedSourcePackage:
    expected = expectation or SourcePackageExpectation()
    root = _resolve_path(package_root, repository_bound=expectation is None)
    _require(root.is_dir(), "source package root is not a directory")
    if expectation is None:
        _require(_repo_relative(root) == CANONICAL_PACKAGE_PATH, "only the canonical N6.2b package is accepted")
        package_reference_path = CANONICAL_PACKAGE_PATH
    else:
        try:
            package_reference_path = _repo_relative(root)
        except AnalysisContractError:
            package_reference_path = "test-fixture/source-package"

    package_path = root / "package_manifest.json"
    _require(sha256_file(package_path) == expected.package_manifest_sha256, "package manifest SHA-256 mismatch")
    package = _load_json(package_path, label="package manifest")
    _require(package.get("manifest_schema") == "faceted3d-n6-exact-custom-package-manifest/v1", "package manifest schema mismatch")
    _require(package.get("git_sha") == expected.source_generation_git_sha, "source package generation SHA mismatch")
    _require(package.get("case_ids") == list(FORMAL_CASE_IDS), "formal case list drifted")
    _require(package.get("historical_fallback") is False, "historical fallback must remain false")
    _require(package.get("run_status") == "PASS", "source package run status mismatch")
    _require(package.get("model_performance_assessment") == "not_performed", "source package performance semantics mismatch")
    _validate_inventory(root, package.get("artifact_inventory"), excluded=frozenset({"package_manifest.json"}))

    manifest_items = [
        item for item in package["artifact_inventory"]
        if re.fullmatch(r"evidence/[^/]+/manifest\.json", item["path"])
    ]
    _require(len(manifest_items) == 1, "source package must contain one evidence manifest")
    evidence_path = root / manifest_items[0]["path"]
    _require(sha256_file(evidence_path) == expected.evidence_manifest_sha256, "evidence manifest SHA-256 mismatch")
    detached_path = evidence_path.with_name("manifest.sha256")
    detached_tokens = detached_path.read_text(encoding="ascii").split()
    _require(detached_tokens == [expected.evidence_manifest_sha256, "manifest.json"], "detached evidence manifest hash mismatch")
    evidence = _load_json(evidence_path, label="evidence manifest")
    _require(evidence.get("manifest_schema") == "faceted3d-leeward-source-evidence-manifest/v1", "evidence manifest schema mismatch")
    _require(tuple(evidence.get("case_registry", {})) == FORMAL_CASE_IDS, "evidence formal registry drifted")
    _require(tuple(evidence.get("cases", {})) == FORMAL_CASE_IDS, "evidence formal cases drifted")
    _require(evidence.get("git_sha") == expected.source_generation_git_sha, "evidence generation SHA mismatch")
    _require(evidence.get("run_status") == "PASS", "evidence run status mismatch")
    _require(evidence.get("model_performance_assessment") == "not_performed", "evidence performance semantics mismatch")

    evidence_root = evidence_path.parent
    evidence_inventory = _evidence_inventory_map(evidence)
    arrays: OrderedDict[str, Mapping[str, Mapping[str, np.ndarray]]] = OrderedDict()
    summaries: OrderedDict[str, Mapping[str, Any]] = OrderedDict()
    raw_paths: OrderedDict[str, Mapping[str, str]] = OrderedDict()
    raw_hashes: OrderedDict[str, Mapping[str, str]] = OrderedDict()
    for case_id in FORMAL_CASE_IDS:
        case_arrays: OrderedDict[str, Mapping[str, np.ndarray]] = OrderedDict()
        case_paths: OrderedDict[str, str] = OrderedDict()
        case_hashes: OrderedDict[str, str] = OrderedDict()
        evidence_case = evidence["cases"][case_id]
        _require(tuple(evidence_case["sheets"]) == SHEET_ORDER, f"{case_id}: sheet order drifted")
        for sheet in SHEET_ORDER:
            relative = f"cases/{case_id}/sheets/{sheet}/raw_evidence.npz"
            artifact = evidence_inventory.get(relative)
            _require(artifact is not None, f"{case_id}/{sheet}: raw artifact missing from evidence inventory")
            _require(artifact.get("schema_or_figure_identity") == RAW_SCHEMA, f"{case_id}/{sheet}: raw schema mismatch")
            _require(artifact.get("evidence_role") == "formal_evidence", f"{case_id}/{sheet}: raw evidence role mismatch")
            expected_raw_hash = expected.raw_hashes()[case_id][sheet]
            _require(artifact.get("raw_sha256") == expected_raw_hash, f"{case_id}/{sheet}: evidence manifest raw hash mismatch")
            raw_path = evidence_root / relative
            case_arrays[sheet] = _load_raw(
                raw_path,
                case_id=case_id,
                sheet=sheet,
                expected_sha256=expected_raw_hash,
                evidence_case=evidence_case,
            )
            case_paths[sheet] = (
                _repo_relative(raw_path)
                if expectation is None
                else f"{package_reference_path}/{relative}"
            )
            case_hashes[sheet] = expected_raw_hash
        summary_path = evidence_root / f"cases/{case_id}/summary.json"
        summary = _load_json(summary_path, label=f"{case_id} source summary")
        _validate_summary(case_id, summary, case_arrays)
        arrays[case_id] = case_arrays
        summaries[case_id] = summary
        raw_paths[case_id] = case_paths
        raw_hashes[case_id] = case_hashes

    return ValidatedSourcePackage(
        root=root,
        repo_relative_path=package_reference_path,
        package_manifest=package,
        evidence_manifest=evidence,
        evidence_root=evidence_root,
        arrays=arrays,
        summaries=summaries,
        raw_paths=raw_paths,
        raw_sha256=raw_hashes,
    )


def build_error_statistics(arrays: Mapping[str, np.ndarray]) -> dict[str, Any]:
    count = int(np.asarray(arrays["signed_error_K"]).size)
    _require(count > 0, "formal error statistics require a nonempty source-row population")
    fields: OrderedDict[str, Any] = OrderedDict()
    for field in ERROR_FIELDS:
        values = np.asarray(arrays[field])
        quantiles = np.quantile(values, [0.05, 0.25, 0.50, 0.75, 0.95], method="linear")
        fields[field] = {
            "count": count,
            "mean": float(np.mean(values)),
            "median": float(np.median(values)),
            "population_std": float(np.std(values, ddof=0)),
            "minimum": float(np.min(values)),
            "maximum": float(np.max(values)),
            "p05": float(quantiles[0]),
            "p25": float(quantiles[1]),
            "p50": float(quantiles[2]),
            "p75": float(quantiles[3]),
            "p95": float(quantiles[4]),
        }
    signed = np.asarray(arrays["signed_error_K"])
    absolute = np.asarray(arrays["absolute_error_K"])
    over = int(np.count_nonzero(signed > 0.0))
    under = int(np.count_nonzero(signed < 0.0))
    zero = int(np.count_nonzero(signed == 0.0))
    _require(over + under + zero == count, "error direction does not conserve source-row population")
    return {
        "error_fields": fields,
        "MAE_K": float(np.mean(absolute)),
        "RMSE_K": float(np.sqrt(np.mean(np.square(signed)))),
        "over_count": over,
        "under_count": under,
        "exact_zero_count": zero,
        "over_fraction": over / count,
        "under_fraction": under / count,
        "exact_zero_fraction": zero / count,
    }


def _lower_profile() -> dict[str, Any]:
    return {
        "typed_empty": True,
        "population": "fluent_source_rows_equal_weight",
        "source_row_count": 0,
        "unique_target_count": 0,
        "statistics": {},
    }


def build_source_profiles(source: ValidatedSourcePackage) -> dict[str, Any]:
    cases: OrderedDict[str, Any] = OrderedDict()
    for case_id in FORMAL_CASE_IDS:
        upper = source.arrays[case_id]["upper"]
        cases[case_id] = {
            "case_id": case_id,
            "raw_artifacts": OrderedDict(
                (
                    (
                        sheet,
                        {
                            "path": source.raw_paths[case_id][sheet],
                            "raw_sha256": source.raw_sha256[case_id][sheet],
                            "schema": RAW_SCHEMA,
                        },
                    )
                    for sheet in SHEET_ORDER
                )
            ),
            "sheets": OrderedDict(
                (
                    (
                        "upper",
                        {
                            "typed_empty": False,
                            "population": "fluent_source_rows_equal_weight",
                            "weighting": "one_fluent_source_row_equal_weight",
                            "row_order": "source_canonical_index_ascending",
                            "source_row_count": int(upper["source_canonical_index"].size),
                            "unique_target_count": int(np.unique(upper["target_canonical_index"]).size),
                            "many_to_one_preserved": True,
                            "raw_artifact": {
                                "path": source.raw_paths[case_id]["upper"],
                                "raw_sha256": source.raw_sha256[case_id]["upper"],
                                "schema": RAW_SCHEMA,
                            },
                            "statistics": build_error_statistics(upper),
                        },
                    ),
                    ("lower", _lower_profile()),
                )
            ),
        }
    return {
        "schema": FORMAL_PROFILE_SCHEMA,
        "role": "formal_core",
        "formal_cases": list(FORMAL_CASE_IDS),
        "population": "fluent_source_rows_equal_weight",
        "weighting": "one_fluent_source_row_equal_weight",
        "quantile_method": "numpy_linear",
        "std_semantics": "population_std_ddof_0",
        "error_contract": {
            "signed_error_K": "Taw_tpg_leeward_K - wall_temperature_K",
            "signed_relative_error_pct": "100 * signed_error_K / wall_temperature_K",
            "absolute_error_K": "abs(signed_error_K)",
            "absolute_relative_error_pct": "abs(signed_relative_error_pct)",
        },
        "cases": cases,
    }


def common_bin_edges(source: ValidatedSourcePackage) -> OrderedDict[str, np.ndarray]:
    fields = OrderedDict((("x", "source_projected_x_m"), ("span", "source_projected_span_m")))
    result: OrderedDict[str, np.ndarray] = OrderedDict()
    for axis, field in fields.items():
        union = np.concatenate([source.arrays[case_id]["upper"][field] for case_id in FORMAL_CASE_IDS])
        _require(float(np.max(union)) > float(np.min(union)), f"{axis}: physical coordinate range is degenerate")
        result[axis] = np.linspace(float(np.min(union)), float(np.max(union)), 6, dtype=np.float64)
    return result


def _bin_rows(axis: str, values: np.ndarray, arrays: Mapping[str, np.ndarray], edges: np.ndarray) -> list[dict[str, Any]]:
    _require(
        edges.dtype == np.dtype(np.float64)
        and edges.shape == (6,)
        and np.all(np.diff(edges) > 0.0),
        f"{axis}: bin edges must be six strictly increasing float64 values",
    )
    _require(
        np.all(values >= edges[0]) and np.all(values <= edges[-1]),
        f"{axis}: coordinate is outside the shared physical bin range",
    )
    bin_count = edges.size - 1
    membership = np.searchsorted(edges, values, side="right") - 1
    membership[values == edges[-1]] = bin_count - 1
    _require(
        np.all((membership >= 0) & (membership < bin_count)),
        f"{axis}: coordinate bin assignment failed",
    )
    rows: list[dict[str, Any]] = []
    for index in range(bin_count):
        selected = membership == index
        count = int(np.count_nonzero(selected))
        base = {
            "axis": axis,
            "bin_index": index,
            "left_edge_m": float(edges[index]),
            "right_edge_m": float(edges[index + 1]),
            "right_edge_inclusive": index == bin_count - 1,
            "source_row_count": count,
            "typed_empty": count == 0,
        }
        if count == 0:
            base["statistics"] = {}
        else:
            signed = arrays["signed_error_K"][selected]
            absolute = arrays["absolute_error_K"][selected]
            relative = arrays["signed_relative_error_pct"][selected]
            absolute_relative = arrays["absolute_relative_error_pct"][selected]
            base.update(
                {
                    "mean_signed_error_K": float(np.mean(signed)),
                    "MAE_K": float(np.mean(absolute)),
                    "RMSE_K": float(np.sqrt(np.mean(np.square(signed)))),
                    "mean_signed_relative_error_pct": float(np.mean(relative)),
                    "mean_absolute_relative_error_pct": float(np.mean(absolute_relative)),
                }
            )
        rows.append(base)
    _require(sum(row["source_row_count"] for row in rows) == values.size, f"{axis}: bin population is not conserved")
    return rows


def build_spatial_bin_profiles(source: ValidatedSourcePackage) -> dict[str, Any]:
    edges = common_bin_edges(source)
    cases: OrderedDict[str, Any] = OrderedDict()
    for case_id in FORMAL_CASE_IDS:
        arrays = source.arrays[case_id]["upper"]
        cases[case_id] = {
            "x": _bin_rows("x", arrays["source_projected_x_m"], arrays, edges["x"]),
            "span": _bin_rows("span", arrays["source_projected_span_m"], arrays, edges["span"]),
        }
    return {
        "schema": FORMAL_PROFILE_SCHEMA,
        "role": "formal_core",
        "population": "fluent_source_rows_equal_weight",
        "bin_contract": {
            "axes": ["source_projected_x_m", "source_projected_span_m"],
            "bin_count_per_axis": 5,
            "edge_source": "union_of_two_formal_upper_source_row_populations",
            "interval_semantics": "left_closed_right_open_except_final_right_closed",
            "x_edges_m": [float(value) for value in edges["x"]],
            "span_edges_m": [float(value) for value in edges["span"]],
        },
        "cases": cases,
    }


def build_multiplicity_profiles(source: ValidatedSourcePackage) -> dict[str, Any]:
    cases: OrderedDict[str, Any] = OrderedDict()
    for case_id in FORMAL_CASE_IDS:
        arrays = source.arrays[case_id]["upper"]
        targets, counts = np.unique(arrays["target_canonical_index"], return_counts=True)
        target_histogram = Counter(int(value) for value in counts)
        groups: list[dict[str, Any]] = []
        for multiplicity in sorted(target_histogram):
            selected_targets = targets[counts == multiplicity]
            selected_rows = np.isin(arrays["target_canonical_index"], selected_targets)
            groups.append(
                {
                    "multiplicity": multiplicity,
                    "unique_target_count": int(selected_targets.size),
                    "source_row_count": int(np.count_nonzero(selected_rows)),
                    "source_row_error_description": build_error_statistics(
                        {field: arrays[field][selected_rows] for field in ERROR_FIELDS}
                    ),
                }
            )
        cases[case_id] = {
            "case_id": case_id,
            "source_row_count_denominator": int(arrays["source_canonical_index"].size),
            "unique_target_count": int(targets.size),
            "target_multiplicity_histogram": {
                str(key): target_histogram[key] for key in sorted(target_histogram)
            },
            "source_row_count_by_multiplicity": {
                str(group["multiplicity"]): group["source_row_count"] for group in groups
            },
            "groups": groups,
        }
    return {
        "schema": DIAGNOSTIC_PROFILE_SCHEMA,
        "role": "diagnostic_only",
        "acceptance_gate": False,
        "formal_core_aggregation": "prohibited",
        "filtering": "none; pairing distance, mutual, second-nearest, ambiguity, and multiplicity are not filters",
        "interpretation": "unique-target deduplication must not replace formal source-row statistics",
        "cases": cases,
    }


def build_bounded_case_comparison(source_profiles: Mapping[str, Any]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for case_id in FORMAL_CASE_IDS:
        profile = source_profiles["cases"][case_id]["sheets"]["upper"]
        facts = dict(CASE_FACTS[case_id])
        cases.append(
            {
                "case_id": case_id,
                **facts,
                "atmosphere_model": "none / unverified",
                "freestream_semantics": "historical user-defined comparison input",
                "source_row_count": profile["source_row_count"],
                "unique_target_count": profile["unique_target_count"],
                "formal_source_level_statistics": profile["statistics"],
            }
        )
    first = cases[0]["formal_source_level_statistics"]
    second = cases[1]["formal_source_level_statistics"]
    differences = {
        "MAE_K": second["MAE_K"] - first["MAE_K"],
        "RMSE_K": second["RMSE_K"] - first["RMSE_K"],
        "mean_signed_error_K": (
            second["error_fields"]["signed_error_K"]["mean"]
            - first["error_fields"]["signed_error_K"]["mean"]
        ),
        "mean_signed_relative_error_pct": (
            second["error_fields"]["signed_relative_error_pct"]["mean"]
            - first["error_fields"]["signed_relative_error_pct"]["mean"]
        ),
    }
    return {
        "schema": FORMAL_PROFILE_SCHEMA,
        "role": "bounded_formal_core_descriptive_comparison",
        "formal_cases": list(FORMAL_CASE_IDS),
        "weighting": "one_fluent_source_row_equal_weight",
        "cases": cases,
        "case2_minus_case1_descriptive_differences": differences,
        "causal_attribution": "not_supported",
        "performance_threshold": "none",
        "model_performance_assessment": "not_performed",
        "provider_systematic_bias_conclusion": "not_established",
    }


def _tracked_reference(path_text: str) -> dict[str, Any]:
    path = ROOT / path_text
    _require(path.is_file(), f"diagnostic context reference is missing: {path_text}")
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path_text],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    _require(result.returncode == 0, f"diagnostic context reference is not tracked: {path_text}")
    return {"path": path_text, "raw_sha256": sha256_file(path), "byte_size": path.stat().st_size}


def build_diagnostic_context() -> dict[str, Any]:
    references = {path: _tracked_reference(path) for path in CONTEXT_PATHS}
    return {
        "schema": DIAGNOSTIC_CONTEXT_SCHEMA,
        "role": "metadata_reference_layer_only",
        "m8_h30_supplemental": {
            "case": "ma8_a5_h30km",
            "status": "unregistered_candidate",
            "role": "upper/leeward supplemental diagnostic only",
            "formal_admission": False,
            "baseline_identity": False,
            "formal_core_aggregation": "prohibited",
            "persistent_formal_evidence": False,
            "references": [
                references["src/ref_enthalpy_method/mapping/m8h30_comparison_inputs.py"],
                references["src/ref_enthalpy_method/mapping/observation_binding.py"],
                references["tests/test_m8h30_comparison_inputs.py"],
            ],
            "excluded_actions": [
                "comparison_execution",
                "new_raw_evidence",
                "persistent_comparison_asset",
                "formal_admission",
                "three_point_formal_trend",
            ],
        },
        "windward": {
            "role": "independent diagnostic context only",
            "population": "valid LF windward grid points",
            "joint_population_with_leeward": "prohibited",
            "joint_statistics": "prohibited",
            "direct_ranking": "prohibited",
            "references": [
                references["runs/20260714_12case_windward_error_rerun/12case_windward_error_summary.json"],
                references["runs/20260714_12case_windward_error_rerun/ma8_a5_h30km__windward_error_stats.json"],
                references["scripts/viz/plot_windward_error_vs_fluent.py"],
            ],
            "reference_semantics": "existing diagnostic assets only; no values recomputed",
        },
    }


def _configure_plotting() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "figure.dpi": 160,
            "savefig.dpi": 160,
        }
    )


def _save_figure(fig: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        path,
        dpi=160,
        facecolor="white",
        metadata={"Software": "Faceted3D N6.3", "Title": path.name},
    )
    plt.close(fig)


def _plot_source_maps(source: ValidatedSourcePackage, path: Path) -> dict[str, Any]:
    _configure_plotting()
    specs = (
        ("signed_error_K", "Signed error (K)"),
        ("signed_relative_error_pct", "Signed relative error (%)"),
    )
    limits: dict[str, list[float]] = {}
    for field, _label in specs:
        union = np.concatenate([source.arrays[case]["upper"][field] for case in FORMAL_CASE_IDS])
        extent = max(abs(float(np.min(union))), abs(float(np.max(union)))) or 1.0
        limits[field] = [-extent, extent]
    fig, axes = plt.subplots(2, 2, figsize=(10.8, 7.2), constrained_layout=True)
    for row, case_id in enumerate(FORMAL_CASE_IDS):
        arrays = source.arrays[case_id]["upper"]
        for column, (field, label) in enumerate(specs):
            axis = axes[row, column]
            extent = limits[field][1]
            scatter = axis.scatter(
                arrays["source_projected_x_m"],
                arrays["source_projected_span_m"],
                c=arrays[field],
                s=18,
                cmap="coolwarm",
                norm=TwoSlopeNorm(vmin=-extent, vcenter=0.0, vmax=extent),
                linewidths=0.0,
            )
            fig.colorbar(scatter, ax=axis, label=label, extend="both")
            axis.set_title(f"{case_id} — {label}")
            axis.set_xlabel("Projected x (m)")
            axis.set_ylabel("Projected span (m)")
            axis.set_aspect("equal", adjustable="box")
    _save_figure(fig, path)
    return {
        "role": "formal_source_row_error_map",
        "axes": ["source_projected_x_m", "source_projected_span_m"],
        "units": {"coordinates": "m", "signed_error_K": "K", "signed_relative_error_pct": "%"},
        "scale": {"mode": "shared_union_symmetric_about_zero", "limits": limits},
    }


def _shared_histogram_edges(source: ValidatedSourcePackage, field: str) -> np.ndarray:
    union = np.concatenate([source.arrays[case]["upper"][field] for case in FORMAL_CASE_IDS])
    minimum, maximum = float(np.min(union)), float(np.max(union))
    if minimum == maximum:
        padding = max(abs(minimum) * 1e-6, 1e-9)
        minimum, maximum = minimum - padding, maximum + padding
    return np.linspace(minimum, maximum, 21, dtype=np.float64)


def _plot_distributions(source: ValidatedSourcePackage, path: Path) -> dict[str, Any]:
    _configure_plotting()
    labels = {
        "signed_error_K": "Signed error (K)",
        "signed_relative_error_pct": "Signed relative error (%)",
        "absolute_error_K": "Absolute error (K)",
        "absolute_relative_error_pct": "Absolute relative error (%)",
    }
    fig, axes = plt.subplots(2, 2, figsize=(10.8, 7.2), constrained_layout=True)
    scales: dict[str, Any] = {}
    for axis, field in zip(axes.flat, ERROR_FIELDS):
        edges = _shared_histogram_edges(source, field)
        scales[field] = {"mode": "shared_union_equal_width", "edges": [float(value) for value in edges]}
        for case_id in FORMAL_CASE_IDS:
            axis.hist(
                source.arrays[case_id]["upper"][field],
                bins=edges,
                alpha=0.55,
                label=case_id,
                edgecolor="black",
                linewidth=0.35,
            )
        axis.set_title(labels[field])
        axis.set_xlabel(labels[field])
        axis.set_ylabel("Fluent source-row count")
        axis.legend()
    fig.suptitle("Formal population: Fluent source rows, equal weight", fontsize=11)
    _save_figure(fig, path)
    return {
        "role": "formal_source_row_error_distributions",
        "axes": list(ERROR_FIELDS),
        "units": {"temperature_error": "K", "relative_error": "%", "count": "source rows"},
        "scale": scales,
    }


def _plot_bin_profiles(spatial: Mapping[str, Any], path: Path) -> dict[str, Any]:
    _configure_plotting()
    fig, axes = plt.subplots(2, 2, figsize=(10.8, 7.2), constrained_layout=True)
    styles = {FORMAL_CASE_IDS[0]: ("o", "#1f77b4"), FORMAL_CASE_IDS[1]: ("s", "#d62728")}
    for row, axis_name in enumerate(("x", "span")):
        for column, (metric, label) in enumerate((("mean_signed_error_K", "Mean signed error (K)"), ("MAE_K", "MAE (K)"))):
            axis = axes[row, column]
            for case_id in FORMAL_CASE_IDS:
                rows = spatial["cases"][case_id][axis_name]
                centers = [(item["left_edge_m"] + item["right_edge_m"]) / 2.0 for item in rows]
                values = [item.get(metric, np.nan) for item in rows]
                marker, color = styles[case_id]
                axis.plot(centers, values, marker=marker, color=color, label=case_id)
            axis.axhline(0.0, color="black", linewidth=0.6)
            axis.set_title(f"{axis_name} bins — {label}")
            axis.set_xlabel(f"Projected {axis_name} bin center (m)")
            axis.set_ylabel(label)
            axis.legend()
    _save_figure(fig, path)
    return {
        "role": "formal_physical_coordinate_bin_profiles",
        "axes": ["source_projected_x_m", "source_projected_span_m"],
        "units": {"coordinates": "m", "mean_signed_error": "K", "MAE": "K"},
        "scale": {"mode": "shared_edges_and_shared_axes", "x_edges_m": spatial["bin_contract"]["x_edges_m"], "span_edges_m": spatial["bin_contract"]["span_edges_m"]},
    }


def _git_output(args: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return result.stdout.strip()


def validate_runtime_identity() -> str:
    package_file = Path(__import__("ref_enthalpy_method").__file__).resolve()
    _require(package_file.is_relative_to(ROOT / "src" / "ref_enthalpy_method"), "Python package identity is outside current repository")
    root = Path(_git_output(("rev-parse", "--show-toplevel"))).resolve()
    _require(root == ROOT.resolve(), "Git root identity mismatch")
    _require(_git_output(("remote", "get-url", "origin")) == "https://github.com/KiRenk0/navi.git", "Git origin identity mismatch")
    head = _git_output(("rev-parse", "HEAD"))
    _validate_hash(head, label="generation Git SHA", length=40)
    lines = tuple(line for line in _git_output(("status", "--porcelain=v1", "--untracked-files=normal")).splitlines() if line)
    unexpected = tuple(line for line in lines if line != "?? attachment/")
    _require(not unexpected, f"Git semantic clean gate failed: {unexpected[0] if unexpected else ''}")
    return head


def build_execution_identity(exact_execution_command: Sequence[str]) -> ExecutionIdentity:
    head = validate_runtime_identity()
    from scripts.tools.current_baseline_regression_check import (
        FIXED_PRODUCTION_PATHS,
        build_canonical_source_identity,
        validate_production_source_clean,
    )

    fixed_paths = (*FIXED_PRODUCTION_PATHS, "scripts/tools/n6_3_layered_error_portrait.py")
    validate_production_source_clean(ROOT, fixed_paths=fixed_paths, expected_count=69)
    contract = build_canonical_source_identity(ROOT, fixed_paths=fixed_paths, expected_count=69)
    command = tuple(str(token) for token in exact_execution_command)
    _require(command and all(token and not Path(token).is_absolute() for token in command), "execution command must contain nonempty relative tokens")
    created = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ExecutionIdentity(
        created_at_utc=created,
        generation_git_sha=head,
        source_identity=contract["source_identity"],
        source_hashes_sha256=contract["source_hashes_sha256"],
        exact_execution_command=command,
    )


def _inventory(root: Path) -> list[dict[str, Any]]:
    paths = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.relative_to(root).as_posix() != "analysis_manifest.json"
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "byte_size": path.stat().st_size,
            "raw_sha256": sha256_file(path),
        }
        for path in paths
    ]


def _artifact_metadata(inventory: Sequence[Mapping[str, Any]], figure_contracts: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    by_path = {item["path"]: item for item in inventory}
    formal_paths = [path for path in EXPECTED_OUTPUT_PATHS if path.startswith("formal_core/")]
    diagnostic_paths = [path for path in EXPECTED_OUTPUT_PATHS if path.startswith("diagnostic_only/")]
    context_paths = [path for path in EXPECTED_OUTPUT_PATHS if path.startswith("diagnostic_context/")]

    def entry(path: str, role: str) -> dict[str, Any]:
        result = {"path": path, "role": role, "byte_size": by_path[path]["byte_size"], "raw_sha256": by_path[path]["raw_sha256"]}
        if path in figure_contracts:
            result.update(figure_contracts[path])
        return result

    return (
        [entry(path, "formal_core") for path in formal_paths],
        [entry(path, "diagnostic_only") for path in diagnostic_paths],
        [entry(path, "diagnostic_context_reference_layer") for path in context_paths],
    )


def _build_manifest(
    *,
    run_id: str,
    identity: ExecutionIdentity,
    source: ValidatedSourcePackage,
    inventory: Sequence[Mapping[str, Any]],
    figure_contracts: Mapping[str, Any],
    spatial: Mapping[str, Any],
) -> dict[str, Any]:
    formal, diagnostic, context = _artifact_metadata(inventory, figure_contracts)
    implementation_hashes = {
        path: identity.source_hashes_sha256[path]
        for path in IMPLEMENTATION_PATHS
    }
    return {
        "schema": ANALYSIS_MANIFEST_SCHEMA,
        "run_id": run_id,
        "created_at_utc": identity.created_at_utc,
        "generation_git_sha": identity.generation_git_sha,
        "generation_source_identity": identity.source_identity,
        "generation_implementation_sources_sha256": implementation_hashes,
        "exact_execution_command": list(identity.exact_execution_command),
        "run_status": "PASS",
        "status_semantics": "program_contract_asset_integrity_only",
        "model_performance_assessment": "not_performed",
        "source_package_identity": {
            "path": source.repo_relative_path,
            "package_id": source.package_manifest["package_id"],
            "package_manifest_sha256": sha256_file(source.root / "package_manifest.json"),
            "evidence_manifest_sha256": sha256_file(source.evidence_root / "manifest.json"),
            "source_package_generation_git_sha": source.package_manifest["git_sha"],
        },
        "formal_cases": list(FORMAL_CASE_IDS),
        "formal_population_identity": "formal upper Fluent source rows; lower typed-empty",
        "weighting": "one_fluent_source_row_equal_weight",
        "error_contract": {
            "signed_error_K": "Taw_tpg_leeward_K - wall_temperature_K",
            "signed_relative_error_pct": "100 * signed_error_K / wall_temperature_K",
            "absolute_error_K": "abs(signed_error_K)",
            "absolute_relative_error_pct": "abs(signed_relative_error_pct)",
        },
        "quantile_method": "numpy_linear",
        "std_semantics": "population_std_ddof_0",
        "spatial_bin_contract": spatial["bin_contract"],
        "formal_core_artifacts": formal,
        "diagnostic_only_artifacts": diagnostic,
        "diagnostic_context_references": context,
        "artifact_inventory": list(inventory),
        "known_limitations": [
            "two bounded formal cases do not support causal attribution",
            "nominal altitude labels are historical case identities, not certified atmosphere variables",
            "lower sheets are typed-empty",
            "M8/30 and windward assets are reference-only diagnostic context",
        ],
        "prohibited_interpretations": [
            "performance PASS or FAIL",
            "provider ranking or systematic bias conclusion",
            "single-variable Mach, altitude, pressure, or temperature causality",
            "unique-target deduplication as formal source-row evidence",
            "joint windward and leeward population statistics",
        ],
    }


def _validate_no_absolute_strings(value: Any) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _validate_no_absolute_strings(item)
    elif isinstance(value, list):
        for item in value:
            _validate_no_absolute_strings(item)
    elif isinstance(value, str):
        _require(re.match(r"^[A-Za-z]:[\\/]", value) is None and not value.startswith("/"), "formal asset contains an absolute path")


def validate_analysis_root(
    analysis_root: str | Path,
    *,
    validate_source: bool = True,
    require_directory_identity: bool = True,
) -> AnalysisPublication:
    root = _resolve_path(analysis_root)
    _require(root.is_dir(), "analysis root is not a directory")
    manifest_path = root / "analysis_manifest.json"
    manifest = _load_json(manifest_path, label="analysis manifest")
    _require(manifest.get("schema") == ANALYSIS_MANIFEST_SCHEMA, "analysis manifest schema mismatch")
    run_id = manifest.get("run_id")
    _require(isinstance(run_id, str) and re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}_n6_3_layered_error_portrait", run_id) is not None, "analysis run ID mismatch")
    if require_directory_identity:
        _require(root.name == run_id, "analysis directory/run identity mismatch")
    _require(manifest.get("generation_git_sha", "")[:12] == run_id.split("_")[1], "analysis generation SHA/run identity mismatch")
    _require(manifest.get("run_status") == "PASS", "analysis run status mismatch")
    _require(manifest.get("status_semantics") == "program_contract_asset_integrity_only", "analysis status semantics mismatch")
    _require(manifest.get("model_performance_assessment") == "not_performed", "analysis performance semantics mismatch")
    _validate_inventory(root, manifest.get("artifact_inventory"), excluded=frozenset({"analysis_manifest.json"}))
    _require(tuple(item["path"] for item in manifest["artifact_inventory"]) == EXPECTED_OUTPUT_PATHS, "analysis output structure mismatch")

    source_profiles = _load_json(root / "formal_core/source_profiles.json", label="source profiles")
    spatial = _load_json(root / "formal_core/spatial_bin_profiles.json", label="spatial profiles")
    bounded = _load_json(root / "formal_core/bounded_case_comparison.json", label="bounded comparison")
    multiplicity = _load_json(root / "diagnostic_only/multiplicity_profiles.json", label="multiplicity profiles")
    context = _load_json(root / "diagnostic_context/tier_references.json", label="diagnostic context")
    _require(source_profiles.get("schema") == FORMAL_PROFILE_SCHEMA, "source profile schema mismatch")
    _require(spatial.get("schema") == FORMAL_PROFILE_SCHEMA, "spatial profile schema mismatch")
    _require(bounded.get("schema") == FORMAL_PROFILE_SCHEMA, "bounded comparison schema mismatch")
    _require(multiplicity.get("schema") == DIAGNOSTIC_PROFILE_SCHEMA, "diagnostic profile schema mismatch")
    _require(context.get("schema") == DIAGNOSTIC_CONTEXT_SCHEMA, "diagnostic context schema mismatch")
    _require(tuple(source_profiles.get("formal_cases", [])) == FORMAL_CASE_IDS, "source profile formal cases drifted")
    _require(tuple(bounded.get("formal_cases", [])) == FORMAL_CASE_IDS, "bounded comparison formal cases drifted")
    _require("ma8_a5_h30km" not in source_profiles["cases"], "M8/30 entered formal core")
    _require(multiplicity.get("formal_core_aggregation") == "prohibited", "multiplicity isolation mismatch")
    _require(context["windward"]["joint_population_with_leeward"] == "prohibited", "windward isolation mismatch")
    _require(bounded.get("performance_threshold") == "none", "bounded comparison threshold contract mismatch")
    _validate_no_absolute_strings(manifest)
    _validate_no_absolute_strings(source_profiles)
    _validate_no_absolute_strings(spatial)
    _validate_no_absolute_strings(bounded)
    _validate_no_absolute_strings(multiplicity)
    _validate_no_absolute_strings(context)

    if validate_source:
        identity = manifest["source_package_identity"]
        source = validate_source_package(identity["path"])
        _require(identity["package_id"] == source.package_manifest["package_id"], "analysis/source package ID mismatch")
        _require(identity["package_manifest_sha256"] == sha256_file(source.root / "package_manifest.json"), "analysis/source package manifest hash mismatch")
        _require(identity["evidence_manifest_sha256"] == sha256_file(source.evidence_root / "manifest.json"), "analysis/source evidence manifest hash mismatch")
        expected_source_profiles = build_source_profiles(source)
        expected_spatial = build_spatial_bin_profiles(source)
        expected_bounded = build_bounded_case_comparison(expected_source_profiles)
        expected_multiplicity = build_multiplicity_profiles(source)
        expected_context = build_diagnostic_context()
        _require(source_profiles == expected_source_profiles, "source profiles are not reproducible from canonical raw evidence")
        _require(spatial == expected_spatial, "spatial profiles are not reproducible from canonical raw evidence")
        _require(bounded == expected_bounded, "bounded comparison is not reproducible")
        _require(multiplicity == expected_multiplicity, "multiplicity diagnostics are not reproducible")
        _require(context == expected_context, "diagnostic context references drifted")

    return AnalysisPublication(
        analysis_root=root,
        run_id=run_id,
        generation_git_sha=manifest["generation_git_sha"],
        manifest_sha256=sha256_file(manifest_path),
        artifact_inventory_count=len(manifest["artifact_inventory"]),
    )


def execute_analysis(
    *,
    package_root: str | Path = CANONICAL_PACKAGE_PATH,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    exact_execution_command: Sequence[str],
    identity: ExecutionIdentity | None = None,
    source_expectation: SourcePackageExpectation | None = None,
) -> AnalysisPublication:
    execution = identity or build_execution_identity(exact_execution_command)
    _validate_hash(execution.generation_git_sha, label="generation Git SHA", length=40)
    created = datetime.strptime(execution.created_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    run_id = f"{created.strftime('%Y%m%dT%H%M%SZ')}_{execution.generation_git_sha[:12]}_n6_3_layered_error_portrait"
    source = validate_source_package(package_root, expectation=source_expectation)
    context = build_diagnostic_context()
    source_profiles = build_source_profiles(source)
    spatial = build_spatial_bin_profiles(source)
    bounded = build_bounded_case_comparison(source_profiles)
    multiplicity = build_multiplicity_profiles(source)

    output = _resolve_path(output_root, must_exist=False)
    _require(output != ROOT, "analysis output root must be dedicated")
    target = output / run_id
    staging = output / f".{run_id}.staging"
    _require(not target.exists(), f"analysis publication target already exists: {target}")
    _require(not staging.exists(), f"analysis staging target already exists: {staging}")

    output_created = not output.exists()
    output.mkdir(parents=True, exist_ok=True)
    staging.mkdir()
    try:
        _write_json(staging / "formal_core/source_profiles.json", source_profiles)
        _write_json(staging / "formal_core/spatial_bin_profiles.json", spatial)
        _write_json(staging / "formal_core/bounded_case_comparison.json", bounded)
        _write_json(staging / "diagnostic_only/multiplicity_profiles.json", multiplicity)
        _write_json(staging / "diagnostic_context/tier_references.json", context)
        figure_contracts = {
            "formal_core/figures/source_error_maps_fixed.png": _plot_source_maps(
                source, staging / "formal_core/figures/source_error_maps_fixed.png"
            ),
            "formal_core/figures/error_distributions.png": _plot_distributions(
                source, staging / "formal_core/figures/error_distributions.png"
            ),
            "formal_core/figures/coordinate_bin_profiles.png": _plot_bin_profiles(
                spatial, staging / "formal_core/figures/coordinate_bin_profiles.png"
            ),
        }
        inventory = _inventory(staging)
        _require(tuple(item["path"] for item in inventory) == EXPECTED_OUTPUT_PATHS, "staging output inventory mismatch")
        manifest = _build_manifest(
            run_id=run_id,
            identity=execution,
            source=source,
            inventory=inventory,
            figure_contracts=figure_contracts,
            spatial=spatial,
        )
        _write_json(staging / "analysis_manifest.json", manifest)
        validate_analysis_root(staging, validate_source=True, require_directory_identity=False)
        os.replace(staging, target)
        return validate_analysis_root(target, validate_source=True, require_directory_identity=True)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if output_created and output.exists() and not any(output.iterdir()):
            output.rmdir()
        raise
