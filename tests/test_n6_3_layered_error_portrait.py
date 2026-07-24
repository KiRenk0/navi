from __future__ import annotations

import hashlib
import json
import shutil
from collections import OrderedDict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

from ref_enthalpy_method.analysis import n6_3_layered_error_portrait as portrait


_FIXED_IDENTITY = portrait.ExecutionIdentity(
    created_at_utc="2026-07-24T12:34:56Z",
    generation_git_sha="1" * 40,
    source_identity={"schema": "git-head-tree-source-identity/v1"},
    source_hashes_sha256={path: "2" * 64 for path in portrait.IMPLEMENTATION_PATHS},
    exact_execution_command=(
        "python",
        "-B",
        "scripts/tools/n6_3_layered_error_portrait.py",
        "--execute",
        "--package-root",
        portrait.CANONICAL_PACKAGE_PATH,
        "--output-root",
        "runs/n6_3_layered_error_portrait",
    ),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _copy_package(tmp_path: Path) -> Path:
    target = tmp_path / "source-package"
    shutil.copytree(portrait.ROOT / portrait.CANONICAL_PACKAGE_PATH, target)
    return target


def _evidence_root(package: Path) -> Path:
    roots = list((package / "evidence").iterdir())
    assert len(roots) == 1
    return roots[0]


def _rechain(package: Path) -> portrait.SourcePackageExpectation:
    evidence_root = _evidence_root(package)
    evidence_path = evidence_root / "manifest.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    for entry in evidence["artifact_hashes_sha256"]:
        path = evidence_root / entry["filename"]
        entry["byte_size"] = path.stat().st_size
        entry["raw_sha256"] = _sha256(path)
    _write_json(evidence_path, evidence)
    evidence_hash = _sha256(evidence_path)
    (evidence_root / "manifest.sha256").write_text(
        f"{evidence_hash}  manifest.json\n", encoding="ascii", newline="\n"
    )

    package_path = package / "package_manifest.json"
    manifest = json.loads(package_path.read_text(encoding="utf-8"))
    for entry in manifest["artifact_inventory"]:
        path = package / entry["path"]
        entry["byte_size"] = path.stat().st_size
        entry["raw_sha256"] = _sha256(path)
    _write_json(package_path, manifest)
    raw_hashes = {
        case_id: {
            sheet: _sha256(
                evidence_root
                / "cases"
                / case_id
                / "sheets"
                / sheet
                / "raw_evidence.npz"
            )
            for sheet in portrait.SHEET_ORDER
        }
        for case_id in portrait.FORMAL_CASE_IDS
    }
    return portrait.SourcePackageExpectation(
        package_manifest_sha256=_sha256(package_path),
        evidence_manifest_sha256=evidence_hash,
        source_generation_git_sha=portrait.SOURCE_PACKAGE_GENERATION_SHA,
        raw_sha256=raw_hashes,
    )


def _rewrite_raw(
    package: Path,
    *,
    case_id: str = "ma6_a5_h30km",
    sheet: str = "upper",
    mutate: Callable[[OrderedDict[str, np.ndarray]], OrderedDict[str, np.ndarray] | None],
) -> Path:
    path = _evidence_root(package) / "cases" / case_id / "sheets" / sheet / "raw_evidence.npz"
    with np.load(path, allow_pickle=False) as archive:
        arrays = OrderedDict((name, np.array(archive[name], copy=True)) for name in archive.files)
    replacement = mutate(arrays)
    np.savez_compressed(path, **(replacement or arrays))
    return path


@pytest.fixture(scope="module")
def canonical_source() -> portrait.ValidatedSourcePackage:
    return portrait.validate_source_package()


@pytest.fixture(scope="module")
def generated_runs(tmp_path_factory: pytest.TempPathFactory) -> tuple[portrait.AnalysisPublication, portrait.AnalysisPublication]:
    root = tmp_path_factory.mktemp("n6-3-determinism")
    first = portrait.execute_analysis(
        output_root=root / "first",
        exact_execution_command=_FIXED_IDENTITY.exact_execution_command,
        identity=_FIXED_IDENTITY,
    )
    second = portrait.execute_analysis(
        output_root=root / "second",
        exact_execution_command=_FIXED_IDENTITY.exact_execution_command,
        identity=_FIXED_IDENTITY,
    )
    return first, second


def test_canonical_package_happy_path_and_lower_typed_empty(
    canonical_source: portrait.ValidatedSourcePackage,
) -> None:
    assert tuple(canonical_source.arrays) == portrait.FORMAL_CASE_IDS
    for case_id in portrait.FORMAL_CASE_IDS:
        upper = canonical_source.arrays[case_id]["upper"]
        lower = canonical_source.arrays[case_id]["lower"]
        assert upper["source_canonical_index"].size == 186
        assert np.unique(upper["target_canonical_index"]).size == 80
        assert lower["source_canonical_index"].shape == (0,)
        assert portrait.build_source_profiles(canonical_source)["cases"][case_id]["sheets"]["lower"] == {
            "typed_empty": True,
            "population": "fluent_source_rows_equal_weight",
            "source_row_count": 0,
            "unique_target_count": 0,
            "statistics": {},
        }


def test_package_manifest_hash_mismatch_fails_closed() -> None:
    with pytest.raises(portrait.AnalysisContractError, match="package manifest SHA-256 mismatch"):
        portrait.validate_source_package(
            expectation=replace(
                portrait.SourcePackageExpectation(), package_manifest_sha256="0" * 64
            )
        )


def test_evidence_manifest_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    evidence_path = _evidence_root(package) / "manifest.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["unused_tamper_marker"] = True
    _write_json(evidence_path, evidence)
    expectation = _rechain(package)
    expectation = replace(
        expectation,
        evidence_manifest_sha256=portrait.EVIDENCE_MANIFEST_SHA256,
    )
    with pytest.raises(portrait.AnalysisContractError, match="evidence manifest SHA-256 mismatch"):
        portrait.validate_source_package(package, expectation=expectation)


def test_package_artifact_inventory_tamper_is_rejected(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    (package / "lf/ma6_a5_h30km/lf_warnings.log").write_text("tampered", encoding="utf-8")
    expectation = replace(
        portrait.SourcePackageExpectation(), package_manifest_sha256=_sha256(package / "package_manifest.json")
    )
    with pytest.raises(portrait.AnalysisContractError, match="artifact inventory"):
        portrait.validate_source_package(package, expectation=expectation)


@pytest.mark.parametrize(
    ("name", "mutate", "message"),
    (
        (
            "member-order",
            lambda arrays: OrderedDict(reversed(tuple(arrays.items()))),
            "member order mismatch",
        ),
        (
            "dtype",
            lambda arrays: arrays.__setitem__(
                "source_projected_x_m", arrays["source_projected_x_m"].astype(np.float32)
            ),
            "dtype mismatch",
        ),
        (
            "shape",
            lambda arrays: arrays.__setitem__(
                "source_projected_x_m", arrays["source_projected_x_m"][:-1]
            ),
            "shape mismatch",
        ),
        (
            "scalar",
            lambda arrays: arrays.__setitem__(
                "case_id", np.asarray("wrong", dtype=np.dtype("<U16"))
            ),
            "scalar identity mismatch",
        ),
        (
            "source-index",
            lambda arrays: arrays["source_canonical_index"].__setitem__(
                1, arrays["source_canonical_index"][0]
            ),
            "not strictly increasing and unique",
        ),
        (
            "formula",
            lambda arrays: arrays["signed_error_K"].__setitem__(
                0, arrays["signed_error_K"][0] + 1.0
            ),
            "frozen error formula mismatch",
        ),
        (
            "many-to-one",
            lambda arrays: arrays["diagnostic_target_multiplicity"].__setitem__(0, 99),
            "many-to-one multiplicity was not preserved",
        ),
    ),
)
def test_raw_contract_tampering_fails_closed(
    tmp_path: Path,
    name: str,
    mutate: Callable[[OrderedDict[str, np.ndarray]], OrderedDict[str, np.ndarray] | None],
    message: str,
) -> None:
    package = _copy_package(tmp_path / name)
    _rewrite_raw(package, mutate=mutate)
    expectation = _rechain(package)
    with pytest.raises(portrait.AnalysisContractError, match=message):
        portrait.validate_source_package(package, expectation=expectation)


def test_summary_raw_mismatch_fails_closed(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    summary_path = _evidence_root(package) / "cases/ma6_a5_h30km/summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["sheets"]["upper"]["source_row_count"] = 185
    _write_json(summary_path, summary)
    expectation = _rechain(package)
    with pytest.raises(portrait.AnalysisContractError, match="summary/raw row mismatch"):
        portrait.validate_source_package(package, expectation=expectation)


def test_error_statistics_use_frozen_formulas_ddof_zero_linear_quantiles_and_source_rows(
    canonical_source: portrait.ValidatedSourcePackage,
) -> None:
    arrays = canonical_source.arrays["ma6_a5_h30km"]["upper"]
    statistics = portrait.build_error_statistics(arrays)
    signed = arrays["Taw_tpg_leeward_K"] - arrays["wall_temperature_K"]
    relative = 100.0 * signed / arrays["wall_temperature_K"]
    np.testing.assert_array_equal(arrays["signed_error_K"], signed)
    np.testing.assert_array_equal(arrays["signed_relative_error_pct"], relative)
    assert statistics["error_fields"]["signed_error_K"]["population_std"] == np.std(signed, ddof=0)
    assert statistics["error_fields"]["signed_error_K"]["p95"] == np.quantile(signed, 0.95, method="linear")
    assert statistics["MAE_K"] == np.mean(np.abs(signed))
    assert statistics["RMSE_K"] == np.sqrt(np.mean(signed**2))
    assert statistics["error_fields"]["signed_error_K"]["count"] == 186


def test_many_to_one_diagnostic_never_replaces_formal_population(
    canonical_source: portrait.ValidatedSourcePackage,
) -> None:
    formal = portrait.build_source_profiles(canonical_source)
    diagnostic = portrait.build_multiplicity_profiles(canonical_source)
    for case_id in portrait.FORMAL_CASE_IDS:
        assert formal["cases"][case_id]["sheets"]["upper"]["source_row_count"] == 186
        assert formal["cases"][case_id]["sheets"]["upper"]["unique_target_count"] == 80
        assert diagnostic["cases"][case_id]["source_row_count_denominator"] == 186
        assert sum(diagnostic["cases"][case_id]["source_row_count_by_multiplicity"].values()) == 186
    assert diagnostic["role"] == "diagnostic_only"
    assert diagnostic["acceptance_gate"] is False
    assert diagnostic["formal_core_aggregation"] == "prohibited"


def test_common_edges_final_bin_and_empty_bin_contract(
    canonical_source: portrait.ValidatedSourcePackage,
) -> None:
    spatial = portrait.build_spatial_bin_profiles(canonical_source)
    for case_id in portrait.FORMAL_CASE_IDS:
        assert [row["left_edge_m"] for row in spatial["cases"][case_id]["x"]] == spatial["bin_contract"]["x_edges_m"][:-1]
        assert spatial["cases"][case_id]["x"][-1]["right_edge_inclusive"] is True
        assert all(row["right_edge_inclusive"] is False for row in spatial["cases"][case_id]["x"][:-1])
    synthetic = {
        "signed_error_K": np.asarray([1.0, 2.0]),
        "absolute_error_K": np.asarray([1.0, 2.0]),
        "signed_relative_error_pct": np.asarray([1.0, 2.0]),
        "absolute_relative_error_pct": np.asarray([1.0, 2.0]),
    }
    rows = portrait._bin_rows(
        "x",
        np.asarray([0.0, 5.0]),
        synthetic,
        np.linspace(0.0, 5.0, 6),
    )
    assert rows[-1]["source_row_count"] == 1
    assert rows[-1]["right_edge_inclusive"] is True
    assert rows[1]["typed_empty"] is True
    assert rows[1]["statistics"] == {}
    with pytest.raises(
        portrait.AnalysisContractError,
        match="outside the shared physical bin range",
    ):
        portrait._bin_rows(
            "x",
            np.asarray([-0.1, 5.0]),
            synthetic,
            np.linspace(0.0, 5.0, 6),
        )


def test_generated_formal_diagnostic_schema_isolation_and_no_threshold_pass(
    generated_runs: tuple[portrait.AnalysisPublication, portrait.AnalysisPublication],
) -> None:
    root = generated_runs[0].analysis_root
    formal = json.loads((root / "formal_core/source_profiles.json").read_text(encoding="utf-8"))
    bounded = json.loads((root / "formal_core/bounded_case_comparison.json").read_text(encoding="utf-8"))
    diagnostic = json.loads((root / "diagnostic_only/multiplicity_profiles.json").read_text(encoding="utf-8"))
    context = json.loads((root / "diagnostic_context/tier_references.json").read_text(encoding="utf-8"))
    assert formal["schema"] == portrait.FORMAL_PROFILE_SCHEMA
    assert diagnostic["schema"] == portrait.DIAGNOSTIC_PROFILE_SCHEMA
    assert context["schema"] == portrait.DIAGNOSTIC_CONTEXT_SCHEMA
    assert "ma8_a5_h30km" not in formal["cases"]
    assert context["m8_h30_supplemental"]["formal_admission"] is False
    assert context["windward"]["joint_population_with_leeward"] == "prohibited"
    assert bounded["performance_threshold"] == "none"
    assert bounded["model_performance_assessment"] == "not_performed"
    assert bounded["provider_systematic_bias_conclusion"] == "not_established"
    serialized = root.joinpath("analysis_manifest.json").read_text(encoding="utf-8")
    assert "NaN" not in serialized and "Infinity" not in serialized


def test_output_target_collision_and_staging_collision_are_rejected(tmp_path: Path) -> None:
    run_id = "20260724T123456Z_111111111111_n6_3_layered_error_portrait"
    output = tmp_path / "output"
    (output / run_id).mkdir(parents=True)
    with pytest.raises(portrait.AnalysisContractError, match="publication target already exists"):
        portrait.execute_analysis(
            output_root=output,
            exact_execution_command=_FIXED_IDENTITY.exact_execution_command,
            identity=_FIXED_IDENTITY,
        )
    shutil.rmtree(output / run_id)
    (output / f".{run_id}.staging").mkdir()
    with pytest.raises(portrait.AnalysisContractError, match="staging target already exists"):
        portrait.execute_analysis(
            output_root=output,
            exact_execution_command=_FIXED_IDENTITY.exact_execution_command,
            identity=_FIXED_IDENTITY,
        )


def test_preflight_failure_is_zero_write(tmp_path: Path) -> None:
    package = _copy_package(tmp_path / "tampered")
    (package / "package_manifest.json").write_text("{}\n", encoding="utf-8")
    output = tmp_path / "must-not-exist"
    with pytest.raises(portrait.AnalysisContractError, match="package manifest SHA-256 mismatch"):
        portrait.execute_analysis(
            package_root=package,
            output_root=output,
            exact_execution_command=_FIXED_IDENTITY.exact_execution_command,
            identity=_FIXED_IDENTITY,
            source_expectation=portrait.SourcePackageExpectation(),
        )
    assert not output.exists()


def test_repeated_temp_generation_is_byte_deterministic_and_validate_existing_passes(
    generated_runs: tuple[portrait.AnalysisPublication, portrait.AnalysisPublication],
) -> None:
    first, second = generated_runs
    assert first.run_id == second.run_id
    first_files = {
        path.relative_to(first.analysis_root).as_posix(): _sha256(path)
        for path in first.analysis_root.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second.analysis_root).as_posix(): _sha256(path)
        for path in second.analysis_root.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files
    validated = portrait.validate_analysis_root(first.analysis_root)
    assert validated.manifest_sha256 == first.manifest_sha256
    assert validated.artifact_inventory_count == len(portrait.EXPECTED_OUTPUT_PATHS)


def test_generated_artifact_tamper_is_rejected(
    generated_runs: tuple[portrait.AnalysisPublication, portrait.AnalysisPublication],
) -> None:
    root = generated_runs[1].analysis_root
    path = root / "formal_core/source_profiles.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(portrait.AnalysisContractError, match="artifact inventory"):
        portrait.validate_analysis_root(root)
