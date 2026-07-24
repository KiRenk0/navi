from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from scripts.tools import faceted3d_chapter3_leeward_source_evidence_qa as qa


CASE_ID = "ma6_a5_h30km"
INPUT_PATHS = {
    "fluent_csv": "../../../../../fluent_export/adiabatic_wall_csv/formal.csv",
    "lf_fields": f"../../lf/{CASE_ID}/fields.npz",
    "lf_summary": f"../../lf/{CASE_ID}/summary.json",
    "lf_manifest": f"../../lf/{CASE_ID}/manifest.json",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "manifest.sha256").write_text(
        f"{_sha256(manifest_path)}  manifest.json\n",
        encoding="ascii",
        newline="\n",
    )


def _rewrite_manifest(
    run_dir: Path,
    update: Callable[[dict[str, Any]], None],
) -> None:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    update(manifest)
    _write_manifest(run_dir, manifest)


def _provenance_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimpleNamespace:
    repo_root = tmp_path / "repo"
    package_root = repo_root / "runs" / "n6" / "package"
    run_dir = package_root / "evidence" / "synthetic-run"
    run_dir.mkdir(parents=True)

    resolved_inputs = {
        "fluent_csv": repo_root / "fluent_export" / "adiabatic_wall_csv" / "formal.csv",
        "lf_fields": package_root / "lf" / CASE_ID / "fields.npz",
        "lf_summary": package_root / "lf" / CASE_ID / "summary.json",
        "lf_manifest": package_root / "lf" / CASE_ID / "manifest.json",
    }
    payloads = {
        "fluent_csv": b"fluent",
        "lf_fields": b"fields",
        "lf_summary": b"summary",
        "lf_manifest": b"manifest",
    }
    for name, path in resolved_inputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payloads[name])

    generator_source = repo_root / "scripts" / "generator.py"
    generator_source.parent.mkdir(parents=True)
    generator_source.write_bytes(b"authoritative generator\n")

    inputs = {
        name: {
            "path": INPUT_PATHS[name],
            "raw_sha256": _sha256(path),
            "byte_size": path.stat().st_size,
        }
        for name, path in resolved_inputs.items()
    }
    manifest = {
        "manifest_schema": qa.MANIFEST_SCHEMA,
        "run_id": run_dir.name,
        "git_sha": "1" * 40,
        "generator": {
            "generator": {
                "path": "scripts/generator.py",
                "raw_sha256": _sha256(generator_source),
            }
        },
        "case_registry": {CASE_ID: {}},
        "cases": {
            CASE_ID: {
                "case_id": CASE_ID,
                "inputs": inputs,
                "baseline_artifact_hashes_sha256": {
                    "fields.npz": inputs["lf_fields"]["raw_sha256"],
                    "summary.json": inputs["lf_summary"]["raw_sha256"],
                },
            }
        },
        "artifact_hashes_sha256": [],
        "run_status": "PASS",
        "status_semantics": qa.STATUS_SEMANTICS,
        "model_performance_assessment": "not_performed",
    }
    _write_manifest(run_dir, manifest)

    monkeypatch.setattr(qa, "ROOT", repo_root)
    monkeypatch.setattr(qa, "EXPECTED", {CASE_ID: (2, 1)})

    def validate_raw(_path: Path, *, case_id: str, sheet: str) -> dict[str, Any]:
        assert case_id == CASE_ID
        return {
            "arrays": {},
            "source_rows": 2 if sheet == "upper" else 0,
            "unique_targets": 1 if sheet == "upper" else 0,
            "typed_empty": sheet == "lower",
        }

    monkeypatch.setattr(qa, "_validate_raw", validate_raw)
    monkeypatch.setattr(qa, "_validate_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(qa, "_validate_png", lambda *_args, **_kwargs: None)
    return SimpleNamespace(
        repo_root=repo_root,
        run_dir=run_dir,
        resolved_inputs=resolved_inputs,
        generator_source=generator_source,
    )


def test_case_provenance_resolves_from_manifest_parent_and_keeps_repo_source_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _provenance_run(tmp_path, monkeypatch)
    visited: list[Path] = []
    real_sha256_file = qa.sha256_file

    def recording_sha256(path: Path) -> str:
        resolved = path.resolve()
        visited.append(resolved)
        return real_sha256_file(resolved)

    monkeypatch.setattr(qa, "sha256_file", recording_sha256)
    result = qa.validate_run(fixture.run_dir)

    assert result["case_counts"][CASE_ID] == {
        "upper_source_rows": 2,
        "upper_unique_targets": 1,
        "lower_typed_empty": True,
    }
    assert set(fixture.resolved_inputs.values()).issubset(set(visited))
    assert fixture.generator_source in visited
    assert not (fixture.run_dir / "scripts" / "generator.py").exists()
    for name, serialized in INPUT_PATHS.items():
        assert (fixture.run_dir / serialized).resolve() == fixture.resolved_inputs[name]
        assert not (fixture.repo_root / serialized).resolve().is_file()


def test_validate_run_is_independent_of_caller_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _provenance_run(tmp_path, monkeypatch)
    first_cwd = tmp_path / "cwd-one"
    second_cwd = tmp_path / "cwd-two"
    first_cwd.mkdir()
    second_cwd.mkdir()

    monkeypatch.chdir(first_cwd)
    first = qa.validate_run(fixture.run_dir)
    monkeypatch.chdir(second_cwd)
    second = qa.validate_run(fixture.run_dir)

    assert first == second


def test_missing_manifest_relative_provenance_input_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _provenance_run(tmp_path, monkeypatch)

    def remove_input(manifest: dict[str, Any]) -> None:
        manifest["cases"][CASE_ID]["inputs"]["lf_fields"]["path"] = (
            f"../../lf/{CASE_ID}/missing-fields.npz"
        )

    _rewrite_manifest(fixture.run_dir, remove_input)
    with pytest.raises(RuntimeError, match="missing provenance input"):
        qa.validate_run(fixture.run_dir)


def test_modified_manifest_relative_provenance_input_fails_hash_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _provenance_run(tmp_path, monkeypatch)
    fixture.resolved_inputs["lf_summary"].write_bytes(b"SUMMARY")

    with pytest.raises(RuntimeError, match="input hash mismatch"):
        qa.validate_run(fixture.run_dir)
