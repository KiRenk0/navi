from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from ref_enthalpy_method.mapping.observation_binding import (
    build_approved_observation_binding,
)
from scripts.tools import n6_exact_custom_formal_entry as entry


_CREATED = datetime(2026, 7, 24, 1, 2, 3, tzinfo=timezone.utc)
_HEAD = "a" * 40


def _source_contract() -> dict[str, Any]:
    return {
        "source_identity": {
            "schema": "git-head-tree-source-identity/v1",
            "authority": "git-head-tree",
            "canonical_bytes": "git-blob",
            "digest_algorithm": "sha256",
            "path_format": "repo-relative-posix",
            "inventory_rule": "production-source-inventory/v1",
            "ordering": "fixed-prefix-then-posix-lexicographic",
            "inventory_paths_sha256": "b" * 64,
            "aggregate_sha256": "c" * 64,
        },
        "source_hashes_sha256": {f"source-{index:02d}": "d" * 64 for index in range(66)},
    }


def _plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> entry.FormalExecutionPlan:
    monkeypatch.setattr(entry, "validate_production_source_clean", lambda _root: None)
    monkeypatch.setattr(entry, "validate_source_identity_schema", lambda _manifest: None)
    return entry.build_preflight_plan(
        output_root=tmp_path / "formal-output",
        created_utc=_CREATED,
        git_clean_validator=lambda: _HEAD,
        source_contract_builder=_source_contract,
    )


def _exact_summary(case_id: str) -> dict[str, Any]:
    binding = build_approved_observation_binding(case_id, entry.ROOT)
    T = float(binding.T_inf_K)
    p = float(binding.p_inf_Pa)
    return {
        "inputs": {"T_inf_K_override": T, "p_inf_Pa_override": p},
        "freestream": {
            "T_inf_K": T,
            "p_inf_Pa": p,
            "freestream_source": "explicit_override",
        },
    }


def _fake_runner(command: list[str] | tuple[str, ...], _cwd: Path) -> None:
    run_dir = Path(command[command.index("--run_dir") + 1])
    case_id = run_dir.name
    run_dir.mkdir(parents=True)
    np.savez_compressed(run_dir / "fields.npz", marker=np.array([1.0]))
    (run_dir / "summary.json").write_text(
        json.dumps(_exact_summary(case_id)) + "\n",
        encoding="utf-8",
    )


def _fake_evidence(**kwargs: Any) -> Path:
    bundles = kwargs["lf_inputs"]
    assert set(bundles) == set(entry.FORMAL_CASE_IDS)
    assert all(bundle.fields_path.is_file() for bundle in bundles.values())
    assert all(bundle.summary_path.is_file() for bundle in bundles.values())
    assert all(bundle.manifest_path.is_file() for bundle in bundles.values())
    target = Path(kwargs["output_root"]) / "synthetic-evidence"
    target.mkdir(parents=True)
    (target / "contract.json").write_text(
        json.dumps(
            {
                "upper_source_rows": 186,
                "upper_unique_targets": 80,
                "many_to_one": True,
                "lower_typed_empty": True,
                "comparison_type": "FluentLfTawComparison",
                "comparison_builder": "build_fluent_lf_taw_comparison",
                "model_performance_assessment": "not_performed",
            }
        ),
        encoding="utf-8",
    )
    return target


def _prepare_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(entry, "validate_git_semantic_clean", lambda: _HEAD)
    monkeypatch.setattr(entry, "validate_source_identity_schema", lambda _manifest: None)


def _assert_no_publication(plan: entry.FormalExecutionPlan) -> None:
    assert not Path(plan.publication_path).exists()
    assert not Path(plan.staging_path).exists()
    root = Path(plan.output_root)
    assert not root.exists() or list(root.iterdir()) == []


@pytest.mark.parametrize("case_id", entry.FORMAL_CASE_IDS)
def test_only_frozen_formal_cases_are_accepted(case_id: str) -> None:
    assert entry.validate_formal_case_selection((case_id,)) == (case_id,)


@pytest.mark.parametrize(
    "case_ids",
    (
        ("ma8_a5_h30km",),
        ("ma8_a5_h45km",),
        ("unknown",),
        ("ma6_a5_h30km", "ma6_a5_h30km"),
        (),
    ),
)
def test_nonformal_duplicate_and_empty_selections_are_rejected(case_ids: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        entry.validate_formal_case_selection(case_ids)


def test_preflight_plan_preserves_raw_tokens_and_has_no_historical_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(tmp_path, monkeypatch)

    assert plan.case_ids == entry.FORMAL_CASE_IDS
    assert plan.historical_fallback is False
    assert not Path(plan.output_root).exists()
    with pytest.raises(TypeError):
        plan.source_identity["schema"] = "mutable"  # type: ignore[index]
    with pytest.raises(TypeError):
        plan.source_hashes_sha256["new"] = "0" * 64  # type: ignore[index]
    serialized = entry.plan_as_dict(plan)
    assert serialized["source_identity"] == dict(plan.source_identity)
    assert serialized["source_hashes_sha256"] == dict(plan.source_hashes_sha256)
    commands = {case.case_id: list(case.solver_command) for case in plan.cases}
    expected = {
        "ma6_a5_h30km": ("226.509", "1197"),
        "ma8_a5_h40km": ("251", "287"),
    }
    forbidden = {
        "226.50908361133003",
        "1196.0495613543349",
        "250.3496461024211",
        "286.83264199835946",
    }
    for case_id, command in commands.items():
        T_token, p_token = expected[case_id]
        assert command[command.index("--T_inf_K") + 1] == T_token
        assert command[command.index("--p_inf_Pa") + 1] == p_token
        assert "--no_plots" in command
        assert "--no_dump_intermediate" in command
        assert "current_baseline_snapshot" not in " ".join(command)
        assert forbidden.isdisjoint(command)


@pytest.mark.parametrize("failure", ("bad-case", "dirty-source", "wrong-binding", "legacy-path", "missing-builder", "invalid-pair"))
def test_preflight_failures_are_zero_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    output_root = tmp_path / "zero-write"
    monkeypatch.setattr(entry, "validate_source_identity_schema", lambda _manifest: None)
    monkeypatch.setattr(entry, "validate_production_source_clean", lambda _root: None)
    kwargs: dict[str, Any] = {
        "output_root": output_root,
        "created_utc": _CREATED,
        "git_clean_validator": lambda: _HEAD,
        "source_contract_builder": _source_contract,
    }
    if failure == "bad-case":
        kwargs["case_ids"] = ("unknown",)
    elif failure == "dirty-source":
        monkeypatch.setattr(
            entry,
            "validate_production_source_clean",
            lambda _root: (_ for _ in ()).throw(RuntimeError("dirty production source")),
        )
    elif failure == "wrong-binding":
        kwargs["case_ids"] = ("ma6_a5_h30km",)
        kwargs["observation_builder"] = lambda _case, root: build_approved_observation_binding("ma8_a5_h40km", root)
    elif failure == "legacy-path":
        kwargs["output_root"] = tmp_path / "current_baseline_snapshot" / "forbidden"
    elif failure == "missing-builder":
        kwargs["manifest_builder"] = 0
    else:
        def invalid_pair(case_id: str, root: Path):
            binding = build_approved_observation_binding(case_id, root)
            bad_identity = replace(binding.filename_identity, T_inf_K=Decimal("999"))
            return replace(binding, filename_identity=bad_identity)
        kwargs["observation_builder"] = invalid_pair

    with pytest.raises((ValueError, RuntimeError)):
        entry.build_preflight_plan(**kwargs)
    assert not output_root.exists()
    assert list(tmp_path.rglob("*.staging")) == []


def test_execution_plan_drift_fails_before_first_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(tmp_path, monkeypatch)

    def reject_drift(_plan: entry.FormalExecutionPlan, _builder: entry.ManifestBuilder) -> None:
        raise RuntimeError("formal execution plan changed after preflight")

    with pytest.raises(RuntimeError, match="changed after preflight"):
        entry.execute_formal_plan(plan, plan_validator=reject_drift)
    _assert_no_publication(plan)


def test_output_collision_preflight_does_not_change_existing_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(tmp_path, monkeypatch)
    target = Path(plan.publication_path)
    target.mkdir(parents=True)
    marker = target / "existing.txt"
    marker.write_bytes(b"keep")

    with pytest.raises(FileExistsError):
        _plan(tmp_path, monkeypatch)
    assert marker.read_bytes() == b"keep"
    assert list(target.iterdir()) == [marker]


def test_formal_manifest_binds_source_observation_command_and_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(tmp_path, monkeypatch)
    _prepare_execution(monkeypatch)
    case = plan.cases[0]
    _fake_runner(case.solver_command, entry.ROOT)
    run_dir = Path(case.staging_run_dir)
    binding = build_approved_observation_binding(case.case_id, entry.ROOT)
    summary = _exact_summary(case.case_id)
    source = _source_contract()
    manifest = entry.build_formal_lf_manifest(case, binding, summary, source)

    assert manifest["manifest_schema"] == entry.FORMAL_LF_MANIFEST_SCHEMA
    assert manifest["git_sha"] == _HEAD
    assert manifest["source_identity"] == source["source_identity"]
    assert manifest["observation"]["path"] == binding.csv_path
    assert manifest["observation"]["raw_sha256"] == binding.raw_sha256
    assert manifest["observation"]["filename_tokens"]["T_inf_K"] == "226.509"
    assert manifest["solver"]["command"] == list(case.solver_command)
    assert manifest["freestream"]["source"] == "explicit_override"
    assert manifest["artifact_hashes_sha256"] == {
        "fields.npz": entry.sha256(run_dir / "fields.npz"),
        "summary.json": entry.sha256(run_dir / "summary.json"),
    }
    assert manifest["model_performance_assessment"] == "not_performed"


@pytest.mark.parametrize("fault", ("missing", "source", "pair", "artifact"))
def test_formal_manifest_validation_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    plan = _plan(tmp_path, monkeypatch)
    _prepare_execution(monkeypatch)
    case = plan.cases[0]
    _fake_runner(case.solver_command, entry.ROOT)
    run_dir = Path(case.staging_run_dir)
    binding = build_approved_observation_binding(case.case_id, entry.ROOT)
    summary = _exact_summary(case.case_id)
    source = _source_contract()
    manifest = entry.build_formal_lf_manifest(case, binding, summary, source)
    if fault == "missing":
        del manifest["solver"]
    elif fault == "source":
        manifest["source_identity"] = {"schema": "wrong"}
    elif fault == "pair":
        manifest["freestream"]["actual_T_inf_K"] = "999"
    else:
        (run_dir / "fields.npz").write_bytes(b"tampered")

    with pytest.raises(ValueError):
        entry.validate_formal_lf_manifest(
            manifest,
            case=case,
            binding=binding,
            summary=summary,
            source_contract=source,
            run_dir=run_dir,
        )


@pytest.mark.parametrize("failure", ("second-solver", "manifest", "evidence", "package-hash"))
def test_atomic_failures_clean_only_owned_staging_and_never_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    plan = _plan(tmp_path, monkeypatch)
    _prepare_execution(monkeypatch)
    outside = tmp_path / "existing-asset.txt"
    outside.write_bytes(b"untouched")
    calls = 0

    def runner(command: list[str] | tuple[str, ...], cwd: Path) -> None:
        nonlocal calls
        calls += 1
        if failure == "second-solver" and calls == 2:
            raise RuntimeError("second solver failed")
        _fake_runner(command, cwd)

    def manifest_builder(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if failure == "manifest":
            raise RuntimeError("manifest failed")
        return entry.build_formal_lf_manifest(*args, **kwargs)

    def evidence_generator(**kwargs: Any) -> Path:
        if failure == "evidence":
            raise RuntimeError("evidence failed")
        return _fake_evidence(**kwargs)

    if failure == "package-hash":
        real_inventory = entry._package_inventory
        def wrong_inventory(staging: Path) -> list[dict[str, Any]]:
            result = real_inventory(staging)
            result[0]["raw_sha256"] = "0" * 64
            return result
        monkeypatch.setattr(entry, "_package_inventory", wrong_inventory)

    with pytest.raises(RuntimeError):
        entry.execute_formal_plan(
            plan,
            runner=runner,
            manifest_builder=manifest_builder,
            evidence_generator=evidence_generator,
            plan_validator=lambda _plan, _builder: None,
        )
    _assert_no_publication(plan)
    assert outside.read_bytes() == b"untouched"


def test_fake_execution_publishes_once_and_preserves_contract_markers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(tmp_path, monkeypatch)
    _prepare_execution(monkeypatch)
    published = entry.execute_formal_plan(
        plan,
        runner=_fake_runner,
        evidence_generator=_fake_evidence,
        plan_validator=lambda _plan, _builder: None,
    )

    assert published == Path(plan.publication_path)
    assert published.is_dir()
    assert not Path(plan.staging_path).exists()
    package = json.loads((published / "package_manifest.json").read_text(encoding="utf-8"))
    assert package["case_ids"] == list(entry.FORMAL_CASE_IDS)
    assert package["historical_fallback"] is False
    assert package["model_performance_assessment"] == "not_performed"
    contract = json.loads(next((published / "evidence").rglob("contract.json")).read_text(encoding="utf-8"))
    assert contract == {
        "upper_source_rows": 186,
        "upper_unique_targets": 80,
        "many_to_one": True,
        "lower_typed_empty": True,
        "comparison_type": "FluentLfTawComparison",
        "comparison_builder": "build_fluent_lf_taw_comparison",
        "model_performance_assessment": "not_performed",
    }