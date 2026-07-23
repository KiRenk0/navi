"""Contract and isolation tests for the unregistered TPG candidate manifest."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from scripts.tools import current_baseline_regression_check as manifest_tool


CANDIDATE_SCHEMA = "tpg-candidate-manifest/v1"
CANDIDATE_PROVENANCE = (
    "Unregistered TPG candidate run manifest; source/artifact identity only; "
    "not baseline-admitted, not promoted, and not formal evidence."
)
CANDIDATE_KEYS = [
    "manifest_schema",
    "provenance",
    "suite_type",
    "admission_status",
    "case_id",
    "case",
    "freestream",
    "atmosphere",
    "thermo",
    "pressure",
    "grid",
    "endpoint_metadata",
    "local_incidence",
    "fields_schema",
    "source_identity",
    "source_hashes_sha256",
    "artifact_hashes_sha256",
    "manifest_generator",
    "generator_cli_template",
]
EXPECTED_CASES = {
    "ma6_a5_h30km": (6.0, 5.0, 30000.0),
    "ma8_a5_h40km": (8.0, 5.0, 40000.0),
}
EXPECTED_V5_KEYS = [
    "manifest_schema",
    "provenance",
    "baseline_date",
    "suite_type",
    "case_id",
    "case",
    "freestream",
    "atmosphere",
    "thermo",
    "pressure",
    "grid",
    "endpoint_metadata",
    "local_incidence",
    "fields_schema",
    "source_identity",
    "source_hashes_sha256",
    "artifact_hashes_sha256",
    "baseline_generator",
    "generator_cli_template",
]
EXPECTED_SOURCE_PATHS_HASH = (
    "81f50d9015c3df397923352d3adb5b0d45dd85e01f3e9a66685c49a3fbf6a428"
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_candidate_artifacts(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    xc_grid = np.linspace(0.0, 1.0, manifest_tool.NX)
    yb_grid = np.linspace(0.0, 1.0, manifest_tool.NY)
    x_w = np.tile(xc_grid, manifest_tool.NY)
    span_w = np.repeat(yb_grid, manifest_tool.NX)
    np.savez_compressed(
        run_dir / "fields.npz",
        mask_w=np.ones(manifest_tool.NX * manifest_tool.NY, dtype=bool),
        span_w_m=span_w,
        x_w_m=x_w,
        xc_grid=xc_grid,
        yb_grid=yb_grid,
    )
    summary = {
        "freestream": {
            "T_inf_K": 230.0,
            "p_inf_Pa": 900.0,
            "rho_inf_kg_m3": 0.014,
            "freestream_source": "atmosphere",
            "atmosphere_model": "isa1976",
        },
        "actual_cp_model": "newtonian_like",
        "actual_cp_newtonian_A": 0.38,
        "actual_cp_newtonian_n": 1.15,
        "faceted3d": {"chord_min_m": 0.02},
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_summary(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))


def _write_summary(run_dir: Path, summary: dict[str, Any]) -> None:
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _set_explicit_summary(
    run_dir: Path,
    *,
    T_inf_K: float = 226.509,
    p_inf_Pa: float = 1197.0,
) -> None:
    summary = _read_summary(run_dir)
    summary["inputs"] = {
        "T_inf_K_override": T_inf_K,
        "p_inf_Pa_override": p_inf_Pa,
    }
    summary["freestream"].update(
        {
            "T_inf_K": T_inf_K,
            "p_inf_Pa": p_inf_Pa,
            "freestream_source": "explicit_override",
        }
    )
    _write_summary(run_dir, summary)


def _candidate_command(
    run_dir: Path,
    *,
    mach: float = 7.25,
    alpha_deg: float = -1.5,
    geometric_altitude_m: float = 35000.0,
    T_inf_K: float | None = None,
    p_inf_Pa: float | None = None,
) -> list[str]:
    return manifest_tool.candidate_generator_command(
        mach=mach,
        alpha_deg=alpha_deg,
        geometric_altitude_m=geometric_altitude_m,
        run_dir=run_dir,
        T_inf_K=T_inf_K,
        p_inf_Pa=p_inf_Pa,
    )


def _build_candidate(
    run_dir: Path,
    *,
    mach: float = 7.25,
    alpha_deg: float = -1.5,
    geometric_altitude_m: float = 35000.0,
    T_inf_K: float | None = None,
    p_inf_Pa: float | None = None,
) -> dict[str, Any]:
    return manifest_tool.build_candidate_manifest(
        case_id="candidate_not_in_registry",
        mach=mach,
        alpha_deg=alpha_deg,
        geometric_altitude_m=geometric_altitude_m,
        run_dir=run_dir,
        generator_command=_candidate_command(
            run_dir,
            mach=mach,
            alpha_deg=alpha_deg,
            geometric_altitude_m=geometric_altitude_m,
            T_inf_K=T_inf_K,
            p_inf_Pa=p_inf_Pa,
        ),
        T_inf_K=T_inf_K,
        p_inf_Pa=p_inf_Pa,
    )


@pytest.fixture
def candidate_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "n3a_candidate_unit"
    _write_candidate_artifacts(run_dir)
    return run_dir


def test_candidate_manifest_contract_and_identity(candidate_run: Path) -> None:
    manifest = _build_candidate(candidate_run)

    assert list(manifest) == CANDIDATE_KEYS
    assert manifest["manifest_schema"] == CANDIDATE_SCHEMA
    assert manifest["suite_type"] == "TPG candidate"
    assert manifest["admission_status"] == "unregistered_candidate"
    assert manifest["provenance"] == CANDIDATE_PROVENANCE
    assert manifest["manifest_generator"] == (
        "scripts/tools/current_baseline_regression_check.py --candidate-manifest"
    )
    assert manifest["case_id"] == "candidate_not_in_registry"
    assert manifest["case"] == {
        "mach": 7.25,
        "alpha_deg": -1.5,
        "geometric_altitude_m": 35000.0,
    }

    forbidden = {
        "baseline_date",
        "baseline_generator",
        "git_sha",
        "commit_sha",
        "branch",
        "registry_membership",
        "performance_status",
        "formal_evidence_admission",
    }
    assert forbidden.isdisjoint(manifest)
    assert manifest["artifact_hashes_sha256"] == {
        name: manifest_tool.sha256(candidate_run / name)
        for name in ("fields.npz", "summary.json")
    }
    canonical_source = manifest_tool.build_canonical_source_identity(manifest_tool.ROOT)
    assert manifest["source_identity"] == canonical_source["source_identity"]
    assert manifest["source_hashes_sha256"] == canonical_source["source_hashes_sha256"]
    manifest_tool.validate_source_identity_schema(manifest)


def test_candidate_case_id_does_not_require_cases_membership(candidate_run: Path) -> None:
    assert "candidate_not_in_registry" not in manifest_tool.CASES
    assert _build_candidate(candidate_run)["case_id"] == "candidate_not_in_registry"


def test_candidate_generator_command_is_unregistered_and_formal(candidate_run: Path) -> None:
    command = _candidate_command(candidate_run)

    assert command == [
        sys.executable,
        str(manifest_tool.RUNNER),
        "--vehicle",
        str(manifest_tool.VEHICLE),
        "--case",
        str(manifest_tool.CASE),
        "--sampling",
        str(manifest_tool.SAMPLING),
        "--run_dir",
        str(candidate_run),
        "--mach",
        "7.25",
        "--alpha",
        "-1.5",
        "--h_m",
        "35000.0",
        "--transition_weighting",
        "step",
        "--no_plots",
    ]
    assert all(case_id not in command for case_id in manifest_tool.CASES)
    assert "--T_inf_K" not in command
    assert "--p_inf_Pa" not in command


def test_candidate_generator_command_includes_explicit_freestream_pair(
    candidate_run: Path,
) -> None:
    command = _candidate_command(
        candidate_run,
        mach=8.0,
        alpha_deg=5.0,
        geometric_altitude_m=30000.0,
        T_inf_K=226.509,
        p_inf_Pa=1197.0,
    )

    assert command[-7:] == [
        "--T_inf_K",
        "226.509",
        "--p_inf_Pa",
        "1197.0",
        "--transition_weighting",
        "step",
        "--no_plots",
    ]
    for option in (
        "--vehicle",
        "--case",
        "--sampling",
        "--run_dir",
        "--mach",
        "--alpha",
        "--h_m",
    ):
        assert option in command


@pytest.mark.parametrize(
    ("T_inf_K", "p_inf_Pa"),
    [(226.509, None), (None, 1197.0)],
)
def test_candidate_generator_command_requires_explicit_freestream_pair(
    candidate_run: Path,
    T_inf_K: float | None,
    p_inf_Pa: float | None,
) -> None:
    with pytest.raises(ValueError, match="T_inf_K.*p_inf_Pa.*together"):
        _candidate_command(
            candidate_run,
            T_inf_K=T_inf_K,
            p_inf_Pa=p_inf_Pa,
        )


@pytest.mark.parametrize(
    ("T_inf_K", "p_inf_Pa"),
    [(226.509, None), (None, 1197.0)],
)
def test_build_candidate_manifest_requires_explicit_freestream_pair(
    candidate_run: Path,
    T_inf_K: float | None,
    p_inf_Pa: float | None,
) -> None:
    with pytest.raises(ValueError, match="T_inf_K.*p_inf_Pa.*together"):
        manifest_tool.build_candidate_manifest(
            case_id="candidate",
            mach=8.0,
            alpha_deg=5.0,
            geometric_altitude_m=30000.0,
            run_dir=candidate_run,
            generator_command=["solver"],
            T_inf_K=T_inf_K,
            p_inf_Pa=p_inf_Pa,
        )


@pytest.mark.parametrize(
    ("T_inf_K", "p_inf_Pa"),
    [
        (float("nan"), 1197.0),
        (float("inf"), 1197.0),
        (0.0, 1197.0),
        (-1.0, 1197.0),
        (226.509, float("nan")),
        (226.509, float("inf")),
        (226.509, 0.0),
        (226.509, -1.0),
    ],
)
def test_explicit_freestream_values_must_be_finite_and_positive(
    candidate_run: Path,
    T_inf_K: float,
    p_inf_Pa: float,
) -> None:
    with pytest.raises(ValueError, match="T_inf_K|p_inf_Pa"):
        _candidate_command(
            candidate_run,
            T_inf_K=T_inf_K,
            p_inf_Pa=p_inf_Pa,
        )


@pytest.mark.parametrize(
    ("T_inf_K", "p_inf_Pa"),
    [
        (float("nan"), 1197.0),
        (0.0, 1197.0),
        (226.509, float("inf")),
        (226.509, -1.0),
    ],
)
def test_build_candidate_manifest_rejects_invalid_explicit_values(
    candidate_run: Path,
    T_inf_K: float,
    p_inf_Pa: float,
) -> None:
    with pytest.raises(ValueError, match="T_inf_K|p_inf_Pa"):
        manifest_tool.build_candidate_manifest(
            case_id="candidate",
            mach=8.0,
            alpha_deg=5.0,
            geometric_altitude_m=30000.0,
            run_dir=candidate_run,
            generator_command=["solver"],
            T_inf_K=T_inf_K,
            p_inf_Pa=p_inf_Pa,
        )


def test_explicit_m8_h30_candidate_manifest_records_complete_provenance(
    candidate_run: Path,
) -> None:
    _set_explicit_summary(candidate_run)

    manifest = _build_candidate(
        candidate_run,
        mach=8.0,
        alpha_deg=5.0,
        geometric_altitude_m=30000.0,
        T_inf_K=226.509,
        p_inf_Pa=1197.0,
    )

    assert list(manifest) == CANDIDATE_KEYS
    assert manifest["case"] == {
        "mach": 8.0,
        "alpha_deg": 5.0,
        "geometric_altitude_m": 30000.0,
    }
    assert manifest["atmosphere"]["explicit_freestream_override"] is True
    assert manifest["freestream"]["actual_T_inf_K"] == 226.509
    assert manifest["freestream"]["actual_p_inf_Pa"] == 1197.0
    assert manifest["freestream"]["source"] == "explicit_override"
    assert "--T_inf_K 226.509" in manifest["generator_cli_template"]
    assert "--p_inf_Pa 1197.0" in manifest["generator_cli_template"]


def test_explicit_summary_without_provenance_pair_is_rejected(
    candidate_run: Path,
) -> None:
    _set_explicit_summary(candidate_run)

    with pytest.raises(
        ValueError,
        match="explicit freestream run requires explicit T_inf_K and p_inf_Pa provenance inputs",
    ):
        _build_candidate(candidate_run)


@pytest.mark.parametrize(
    ("scope", "key", "value"),
    [
        ("inputs", "T_inf_K_override", 226.5),
        ("inputs", "p_inf_Pa_override", 1196.0),
        ("freestream", "T_inf_K", 226.5),
        ("freestream", "p_inf_Pa", 1196.0),
    ],
)
def test_explicit_summary_value_mismatch_is_rejected(
    candidate_run: Path,
    scope: str,
    key: str,
    value: float,
) -> None:
    _set_explicit_summary(candidate_run)
    summary = _read_summary(candidate_run)
    summary[scope][key] = value
    _write_summary(candidate_run, summary)

    with pytest.raises(ValueError, match=key):
        _build_candidate(candidate_run, T_inf_K=226.509, p_inf_Pa=1197.0)


@pytest.mark.parametrize(
    ("scope", "key", "value"),
    [
        ("inputs", "T_inf_K_override", float("nan")),
        ("inputs", "p_inf_Pa_override", 0.0),
        ("freestream", "T_inf_K", float("inf")),
        ("freestream", "p_inf_Pa", -1.0),
        ("freestream", "rho_inf_kg_m3", 0.0),
    ],
)
def test_explicit_summary_values_must_be_finite_and_positive(
    candidate_run: Path,
    scope: str,
    key: str,
    value: float,
) -> None:
    _set_explicit_summary(candidate_run)
    summary = _read_summary(candidate_run)
    summary[scope][key] = value
    _write_summary(candidate_run, summary)

    with pytest.raises(ValueError, match=key):
        _build_candidate(candidate_run, T_inf_K=226.509, p_inf_Pa=1197.0)


def test_explicit_summary_source_mismatch_is_rejected(candidate_run: Path) -> None:
    _set_explicit_summary(candidate_run)
    summary = _read_summary(candidate_run)
    summary["freestream"]["freestream_source"] = "atmosphere"
    _write_summary(candidate_run, summary)

    with pytest.raises(ValueError, match="freestream_source.*explicit_override"):
        _build_candidate(candidate_run, T_inf_K=226.509, p_inf_Pa=1197.0)


@pytest.mark.parametrize("missing_key", ["T_inf_K_override", "p_inf_Pa_override"])
def test_explicit_pair_requires_both_summary_override_fields(
    candidate_run: Path,
    missing_key: str,
) -> None:
    _set_explicit_summary(candidate_run)
    summary = _read_summary(candidate_run)
    del summary["inputs"][missing_key]
    _write_summary(candidate_run, summary)

    with pytest.raises(ValueError, match=missing_key):
        _build_candidate(candidate_run, T_inf_K=226.509, p_inf_Pa=1197.0)


def test_explicit_pair_requires_summary_override_object(candidate_run: Path) -> None:
    summary = _read_summary(candidate_run)
    summary["freestream"].update(
        {
            "T_inf_K": 226.509,
            "p_inf_Pa": 1197.0,
            "freestream_source": "explicit_override",
        }
    )
    _write_summary(candidate_run, summary)

    with pytest.raises(ValueError, match="summary.json missing required object: inputs"):
        _build_candidate(candidate_run, T_inf_K=226.509, p_inf_Pa=1197.0)


def test_explicit_pair_rejects_incomplete_generator_command(
    candidate_run: Path,
) -> None:
    _set_explicit_summary(candidate_run)

    with pytest.raises(ValueError, match="complete candidate runner command"):
        manifest_tool.build_candidate_manifest(
            case_id="candidate_m8_h30",
            mach=8.0,
            alpha_deg=5.0,
            geometric_altitude_m=30000.0,
            run_dir=candidate_run,
            generator_command=["solver"],
            T_inf_K=226.509,
            p_inf_Pa=1197.0,
        )


def test_non_explicit_summary_remains_backward_compatible(candidate_run: Path) -> None:
    manifest = _build_candidate(candidate_run)

    assert manifest["atmosphere"]["explicit_freestream_override"] is False
    assert manifest["freestream"] == {
        "actual_T_inf_K": 230.0,
        "actual_p_inf_Pa": 900.0,
        "actual_rho_inf_kg_m3": 0.014,
        "source": "atmosphere",
    }
    assert "--T_inf_K" not in manifest["generator_cli_template"]
    assert "--p_inf_Pa" not in manifest["generator_cli_template"]


def test_non_explicit_builder_preserves_supplied_generator_command(
    candidate_run: Path,
) -> None:
    manifest = manifest_tool.build_candidate_manifest(
        case_id="candidate",
        mach=7.25,
        alpha_deg=-1.5,
        geometric_altitude_m=35000.0,
        run_dir=candidate_run,
        generator_command=["existing-non-explicit-command"],
    )

    assert manifest["generator_cli_template"] == "existing-non-explicit-command"
    assert manifest["atmosphere"]["explicit_freestream_override"] is False


def test_empty_case_id_fails(candidate_run: Path) -> None:
    with pytest.raises(ValueError, match="case_id"):
        manifest_tool.build_candidate_manifest(
            case_id="  ",
            mach=7.25,
            alpha_deg=-1.5,
            geometric_altitude_m=35000.0,
            run_dir=candidate_run,
            generator_command=_candidate_command(candidate_run),
        )


@pytest.mark.parametrize("mach", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_mach_fails(candidate_run: Path, mach: float) -> None:
    with pytest.raises(ValueError, match="mach"):
        manifest_tool.build_candidate_manifest(
            case_id="candidate",
            mach=mach,
            alpha_deg=0.0,
            geometric_altitude_m=35000.0,
            run_dir=candidate_run,
            generator_command=["solver"],
        )


@pytest.mark.parametrize("altitude", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_altitude_fails(candidate_run: Path, altitude: float) -> None:
    with pytest.raises(ValueError, match="geometric_altitude_m"):
        manifest_tool.build_candidate_manifest(
            case_id="candidate",
            mach=7.0,
            alpha_deg=0.0,
            geometric_altitude_m=altitude,
            run_dir=candidate_run,
            generator_command=["solver"],
        )


@pytest.mark.parametrize("alpha", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_alpha_fails(candidate_run: Path, alpha: float) -> None:
    with pytest.raises(ValueError, match="alpha_deg"):
        manifest_tool.build_candidate_manifest(
            case_id="candidate",
            mach=7.0,
            alpha_deg=alpha,
            geometric_altitude_m=35000.0,
            run_dir=candidate_run,
            generator_command=["solver"],
        )


@pytest.mark.parametrize("command", [[], ["solver", 7]])
def test_invalid_generator_command_fails(
    candidate_run: Path,
    command: list[Any],
) -> None:
    with pytest.raises(ValueError, match="generator_command"):
        manifest_tool.build_candidate_manifest(
            case_id="candidate",
            mach=7.0,
            alpha_deg=0.0,
            geometric_altitude_m=35000.0,
            run_dir=candidate_run,
            generator_command=command,
        )


@pytest.mark.parametrize("missing_name", ["fields.npz", "summary.json"])
def test_missing_candidate_artifact_fails(
    candidate_run: Path,
    missing_name: str,
) -> None:
    (candidate_run / missing_name).unlink()
    with pytest.raises(FileNotFoundError, match=missing_name):
        _build_candidate(candidate_run)


def test_invalid_summary_json_fails(candidate_run: Path) -> None:
    (candidate_run / "summary.json").write_text("{not-json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        _build_candidate(candidate_run)


def test_unreadable_or_incomplete_fields_fail(candidate_run: Path) -> None:
    (candidate_run / "fields.npz").write_bytes(b"not-an-npz")
    with pytest.raises((OSError, ValueError)):
        _build_candidate(candidate_run)

    np.savez_compressed(candidate_run / "fields.npz", mask_w=np.ones(3))
    with pytest.raises(ValueError, match="missing required arrays"):
        _build_candidate(candidate_run)


def test_incomplete_summary_fails(candidate_run: Path) -> None:
    (candidate_run / "summary.json").write_text(
        json.dumps({"freestream": {}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="required"):
        _build_candidate(candidate_run)


@pytest.mark.parametrize(
    "relative_path, expected_message",
    [
        (
            Path("current_baseline_snapshot") / "candidate_snapshot",
            "forbidden area",
        ),
        (
            Path("leeward_source_evidence") / "candidate_evidence",
            "forbidden area",
        ),
        (Path("ordinary_run"), "must contain 'candidate'"),
    ],
)
def test_candidate_path_restrictions(
    tmp_path: Path,
    relative_path: Path,
    expected_message: str,
) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / relative_path
    _write_candidate_artifacts(run_dir)

    with pytest.raises(ValueError, match=expected_message):
        manifest_tool._validate_candidate_run_dir(
            run_dir,
            allowed_runs_root=runs_root,
        )


def test_candidate_path_escape_is_rejected(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    outside = tmp_path / "outside_candidate"
    _write_candidate_artifacts(outside)

    with pytest.raises(ValueError, match="must be inside"):
        manifest_tool._validate_candidate_run_dir(
            runs_root / ".." / outside.name,
            allowed_runs_root=runs_root,
        )


def test_existing_manifest_is_never_overwritten(candidate_run: Path) -> None:
    target = candidate_run / "manifest.json"
    target.write_bytes(b"existing-manifest")

    with pytest.raises(FileExistsError):
        manifest_tool._write_candidate_manifest_atomically(
            candidate_run,
            _build_candidate(candidate_run),
        )
    assert target.read_bytes() == b"existing-manifest"
    assert not list(candidate_run.glob(".candidate-manifest-*.tmp"))


def test_candidate_cli_requires_all_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["candidate-manifest", "--candidate-manifest"])
    with pytest.raises(SystemExit) as exc_info:
        manifest_tool.main()
    assert exc_info.value.code == 2


def test_candidate_cli_help_documents_explicit_freestream_pair(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["candidate-manifest", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        manifest_tool.main()

    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "--t-inf-k" in help_text
    assert "--p-inf-pa" in help_text
    assert "K" in help_text
    assert "Pa" in help_text
    assert "together" in help_text


@pytest.mark.parametrize(
    "explicit_args",
    [
        ["--t-inf-k", "226.509"],
        ["--p-inf-pa", "1197.0"],
    ],
)
def test_candidate_cli_rejects_unpaired_explicit_freestream_argument(
    candidate_run: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    explicit_args: list[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "candidate-manifest",
            "--candidate-manifest",
            "--case-id",
            "candidate",
            "--mach",
            "8",
            "--alpha",
            "5",
            "--h-m",
            "30000",
            "--run-dir",
            str(candidate_run),
            *explicit_args,
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        manifest_tool.main()

    assert exc_info.value.code == 2
    assert "--t-inf-k and --p-inf-pa must be provided together" in capsys.readouterr().err


def test_candidate_cli_rejects_invalid_explicit_freestream_pair(
    candidate_run: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "candidate-manifest",
            "--candidate-manifest",
            "--case-id",
            "candidate",
            "--mach",
            "8",
            "--alpha",
            "5",
            "--h-m",
            "30000",
            "--run-dir",
            str(candidate_run),
            "--t-inf-k",
            "nan",
            "--p-inf-pa",
            "1197.0",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        manifest_tool.main()

    assert exc_info.value.code == 2
    assert "T_inf_K must be a finite float" in capsys.readouterr().err


def test_candidate_cli_maps_explicit_freestream_pair(
    candidate_run: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_explicit_summary(candidate_run)
    monkeypatch.setattr(manifest_tool, "CANDIDATE_RUNS_ROOT", candidate_run.parents[1])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "candidate-manifest",
            "--candidate-manifest",
            "--case-id",
            "candidate_m8_h30",
            "--mach",
            "8",
            "--alpha",
            "5",
            "--h-m",
            "30000",
            "--run-dir",
            str(candidate_run),
            "--t-inf-k",
            "226.509",
            "--p-inf-pa",
            "1197.0",
        ],
    )

    assert manifest_tool.main() == 0
    manifest = json.loads((candidate_run / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["atmosphere"]["explicit_freestream_override"] is True
    assert manifest["freestream"]["source"] == "explicit_override"
    assert "--T_inf_K 226.509" in manifest["generator_cli_template"]
    assert "--p_inf_Pa 1197.0" in manifest["generator_cli_template"]


def test_candidate_cli_only_writes_manifest(
    candidate_run: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = candidate_run.parents[1]
    before = {
        name: (candidate_run / name).read_bytes()
        for name in ("fields.npz", "summary.json")
    }

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("candidate CLI crossed into solver/freeze/check flow")

    monkeypatch.setattr(manifest_tool, "CANDIDATE_RUNS_ROOT", runs_root)
    monkeypatch.setattr(manifest_tool, "freeze_all", forbidden)
    monkeypatch.setattr(manifest_tool, "freeze_case", forbidden)
    monkeypatch.setattr(manifest_tool, "compare_case", forbidden)
    monkeypatch.setattr(manifest_tool, "run_formal", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "candidate-manifest",
            "--candidate-manifest",
            "--case-id",
            "candidate_not_in_registry",
            "--mach",
            "7.25",
            "--alpha",
            "-1.5",
            "--h-m",
            "35000",
            "--run-dir",
            str(candidate_run),
        ],
    )

    assert manifest_tool.main() == 0
    manifest_path = candidate_run / "manifest.json"
    assert manifest_path.is_file()
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["manifest_schema"] == CANDIDATE_SCHEMA
    assert {
        name: (candidate_run / name).read_bytes()
        for name in ("fields.npz", "summary.json")
    } == before
    assert sorted(path.name for path in candidate_run.iterdir()) == [
        "fields.npz",
        "manifest.json",
        "summary.json",
    ]


def test_atomic_write_failure_leaves_no_output_or_temp(
    candidate_run: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_publish(source: Path, target: Path) -> None:
        raise OSError("simulated atomic publish failure")

    monkeypatch.setattr(manifest_tool.os, "link", fail_publish)
    with pytest.raises(OSError, match="simulated atomic publish failure"):
        manifest_tool._write_candidate_manifest_atomically(
            candidate_run,
            _build_candidate(candidate_run),
        )
    assert not (candidate_run / "manifest.json").exists()
    assert not list(candidate_run.glob(".candidate-manifest-*.tmp"))


def test_candidate_schema_is_not_treated_as_v5(candidate_run: Path) -> None:
    summary_hash = manifest_tool.sha256(candidate_run / "summary.json")
    candidate_identity = {
        "manifest_schema": CANDIDATE_SCHEMA,
        "artifact_hashes_sha256": {"summary.json": summary_hash},
    }
    v5_identity = {
        "manifest_schema": "current-tpg-baseline-regression/v5",
        "artifact_hashes_sha256": {"summary.json": summary_hash},
    }

    candidate_ok, candidate_errors = manifest_tool.verify_artifact_hashes(
        "candidate", candidate_run, candidate_identity
    )
    v5_ok, v5_errors = manifest_tool.verify_artifact_hashes(
        "baseline", candidate_run, v5_identity
    )
    assert candidate_ok and candidate_errors == []
    assert not v5_ok
    assert any("artifact=fields.npz" in error for error in v5_errors)


def _git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def _commit_all(repo: Path, message: str = "fixture") -> None:
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", message)


def _init_source_repo(
    root: Path,
    *,
    fixed_paths: tuple[str, ...] = ("fixed.txt",),
    python_count: int = 1,
) -> tuple[Path, tuple[str, ...], int]:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "N3b Test")
    _git(repo, "config", "user.email", "n3b@example.invalid")
    for index, path in enumerate(fixed_paths):
        target = repo / Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"fixed-{index}\n".encode())
    for index in range(python_count):
        target = repo / "src" / "ref_enthalpy_method" / f"module_{index:02d}.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"VALUE = {index}\n".encode())
    (repo / ".gitattributes").write_text("*.py text eol=crlf\n", encoding="utf-8")
    (repo / "notes.txt").write_text("clean\n", encoding="utf-8")
    _commit_all(repo)
    return repo, fixed_paths, len(fixed_paths) + python_count


@pytest.fixture
def source_repo(tmp_path: Path) -> tuple[Path, tuple[str, ...], int]:
    return _init_source_repo(tmp_path)


def _source_identity(
    fixture: tuple[Path, tuple[str, ...], int],
) -> dict[str, Any]:
    repo, fixed_paths, expected_count = fixture
    return manifest_tool.build_canonical_source_identity(
        repo,
        fixed_paths=fixed_paths,
        expected_count=expected_count,
    )


def test_head_blob_identity_is_binary_exact_and_worktree_independent(
    source_repo: tuple[Path, tuple[str, ...], int],
) -> None:
    repo, fixed_paths, expected_count = source_repo
    before = _source_identity(source_repo)
    path = "src/ref_enthalpy_method/module_00.py"
    mode, object_type, object_id = manifest_tool.read_head_tree_entry(repo, path)
    independent_blob = _git(repo, "cat-file", "blob", object_id)

    assert (mode, object_type) == ("100644", "blob")
    assert manifest_tool.read_git_blob_bytes(repo, path, object_id) == independent_blob
    assert before["source_hashes_sha256"][path] == hashlib.sha256(independent_blob).hexdigest()

    (repo / path).write_bytes(b"WORKTREE_ONLY = True\r\n")
    assert _source_identity(source_repo) == before
    with pytest.raises(manifest_tool.ProductionSourceDirtyError, match="UNSTAGED_PRODUCTION_SOURCE"):
        manifest_tool.validate_production_source_clean(
            repo,
            fixed_paths=fixed_paths,
            expected_count=expected_count,
        )


def test_real_head_inventory_schema_order_and_aggregate_contract() -> None:
    canonical = manifest_tool.build_canonical_source_identity(manifest_tool.ROOT)
    paths = list(canonical["source_hashes_sha256"])
    records = [[path, canonical["source_hashes_sha256"][path]] for path in paths]

    assert len(paths) == len(set(paths)) == 65
    assert paths[:6] == list(manifest_tool.FIXED_PRODUCTION_PATHS)
    assert paths[6:] == sorted(paths[6:])
    assert all("\\" not in path and not Path(path).is_absolute() for path in paths)
    assert canonical["source_identity"]["inventory_paths_sha256"] == hashlib.sha256(
        _canonical(paths)
    ).hexdigest()
    assert canonical["source_identity"]["aggregate_sha256"] == hashlib.sha256(
        _canonical(records)
    ).hexdigest()
    assert not {
        "commit_oid", "tree_oid", "branch", "checkout_path", "platform"
    }.intersection(canonical["source_identity"])
    manifest_tool.validate_source_identity_schema(canonical)


def test_crlf_semantic_clean_checkout_preserves_identity(
    source_repo: tuple[Path, tuple[str, ...], int],
) -> None:
    repo, fixed_paths, expected_count = source_repo
    before = _source_identity(source_repo)
    python_path = repo / "src" / "ref_enthalpy_method" / "module_00.py"
    python_path.unlink()
    _git(repo, "checkout-index", "--force", "--", "src/ref_enthalpy_method/module_00.py")

    assert b"\r\n" in python_path.read_bytes()
    assert _git(repo, "diff", "--name-only") == b""
    manifest_tool.validate_production_source_clean(
        repo,
        fixed_paths=fixed_paths,
        expected_count=expected_count,
    )
    assert _source_identity(source_repo) == before


@pytest.mark.parametrize(
    ("state", "expected_code"),
    [
        ("staged", "STAGED_PRODUCTION_SOURCE"),
        ("unstaged", "UNSTAGED_PRODUCTION_SOURCE"),
        ("both", "STAGED_PRODUCTION_SOURCE.*UNSTAGED_PRODUCTION_SOURCE"),
        ("deleted", "DELETED_PRODUCTION_SOURCE"),
        ("renamed", "RENAMED_PRODUCTION_SOURCE"),
        ("untracked", "UNTRACKED_PRODUCTION_SOURCE"),
    ],
)
def test_production_dirty_matrix_fails_closed(
    tmp_path: Path,
    state: str,
    expected_code: str,
) -> None:
    repo, fixed_paths, expected_count = _init_source_repo(tmp_path)
    relative = "src/ref_enthalpy_method/module_00.py"
    source = repo / relative
    if state == "staged":
        source.write_text("VALUE = 10\n", encoding="utf-8")
        _git(repo, "add", relative)
    elif state == "unstaged":
        source.write_text("VALUE = 11\n", encoding="utf-8")
    elif state == "both":
        source.write_text("VALUE = 12\n", encoding="utf-8")
        _git(repo, "add", relative)
        source.write_text("VALUE = 13\n", encoding="utf-8")
    elif state == "deleted":
        source.unlink()
    elif state == "renamed":
        _git(repo, "mv", relative, "src/ref_enthalpy_method/renamed.py")
    else:
        (repo / "src" / "ref_enthalpy_method" / "untracked.py").write_text(
            "VALUE = 14\n", encoding="utf-8"
        )

    with pytest.raises(manifest_tool.ProductionSourceDirtyError, match=expected_code):
        manifest_tool.validate_production_source_clean(
            repo,
            fixed_paths=fixed_paths,
            expected_count=expected_count,
        )


def test_nonproduction_and_ordinary_untracked_are_ignored_by_source_gate(
    source_repo: tuple[Path, tuple[str, ...], int],
) -> None:
    repo, fixed_paths, expected_count = source_repo
    (repo / "notes.txt").write_text("dirty\n", encoding="utf-8")
    csv_path = repo / "ordinary.csv"
    csv_path.write_bytes(b"must-not-be-read")

    manifest_tool.validate_production_source_clean(
        repo,
        fixed_paths=fixed_paths,
        expected_count=expected_count,
    )
    with pytest.raises(manifest_tool.SourceIdentityError, match="tracked-dirty"):
        manifest_tool.validate_source_migration_preflight(
            repo,
            fixed_paths=fixed_paths,
            expected_count=expected_count,
        )
    assert csv_path.read_bytes() == b"must-not-be-read"


def test_missing_invalid_tree_entries_and_count_drift_fail_closed(tmp_path: Path) -> None:
    repo, fixed_paths, expected_count = _init_source_repo(tmp_path)
    with pytest.raises(manifest_tool.SourceIdentityError, match="MISSING_HEAD_SOURCE"):
        manifest_tool.build_head_production_inventory(
            repo,
            fixed_paths=("missing.txt",),
            expected_count=expected_count,
        )
    with pytest.raises(manifest_tool.SourceIdentityError, match="INVENTORY_COUNT_DRIFT"):
        manifest_tool.build_head_production_inventory(
            repo,
            fixed_paths=fixed_paths,
            expected_count=expected_count + 1,
        )

    tree_file = repo / "src" / "ref_enthalpy_method" / "tree.py" / "child.txt"
    tree_file.parent.mkdir()
    tree_file.write_text("child\n", encoding="utf-8")
    _commit_all(repo, "tree-like py path")
    with pytest.raises(manifest_tool.SourceIdentityError, match="INVALID_HEAD_TREE_ENTRY.*tree.py"):
        manifest_tool.build_head_production_inventory(
            repo,
            fixed_paths=fixed_paths,
            expected_count=expected_count + 1,
        )


@pytest.mark.parametrize(("mode", "object_type"), [("120000", "blob"), ("160000", "commit")])
def test_symlink_and_submodule_inventory_entries_fail_closed(
    tmp_path: Path,
    mode: str,
    object_type: str,
) -> None:
    repo, fixed_paths, expected_count = _init_source_repo(tmp_path)
    path = "src/ref_enthalpy_method/module_00.py"
    if mode == "120000":
        object_id = _git(repo, "hash-object", "-w", "--stdin", input_bytes=b"target").strip().decode()
    else:
        object_id = _git(repo, "rev-parse", "HEAD").strip().decode()
    _git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{object_id},{path}")
    _git(repo, "commit", "-m", f"invalid {object_type}")

    with pytest.raises(manifest_tool.SourceIdentityError, match="INVALID_HEAD_TREE_ENTRY"):
        manifest_tool.build_head_production_inventory(
            repo,
            fixed_paths=fixed_paths,
            expected_count=expected_count,
        )


def test_git_plumbing_and_schema_corruption_fail_closed(
    source_repo: tuple[Path, tuple[str, ...], int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, fixed_paths, expected_count = source_repo
    canonical = _source_identity(source_repo)
    broken = json.loads(json.dumps(canonical))
    broken["source_identity"]["schema"] = "wrong"
    with pytest.raises(manifest_tool.SourceIdentityError, match="SCHEMA_MISMATCH"):
        manifest_tool.validate_source_identity_schema(
            broken,
            expected_count=expected_count,
            fixed_paths=fixed_paths,
        )

    real_run = manifest_tool.subprocess.run

    def fail_cat_file(*args: Any, **kwargs: Any) -> Any:
        if args[0][1:3] == ["cat-file", "blob"]:
            return subprocess.CompletedProcess(args[0], 1, b"", b"missing object")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(manifest_tool.subprocess, "run", fail_cat_file)
    with pytest.raises(manifest_tool.SourceIdentityError, match="GIT_COMMAND_FAILED.*read-git-blob"):
        manifest_tool.build_canonical_source_identity(
            repo,
            fixed_paths=fixed_paths,
            expected_count=expected_count,
        )


def test_candidate_and_current_builder_share_canonical_source_contract(
    candidate_run: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = manifest_tool.build_canonical_source_identity(manifest_tool.ROOT)
    calls: list[Path] = []

    def shared_builder(repo_root: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append(repo_root)
        return canonical

    monkeypatch.setattr(manifest_tool, "build_canonical_source_identity", shared_builder)
    candidate = _build_candidate(candidate_run)
    current = manifest_tool.build_manifest(
        "ma6_a5_h30km",
        candidate_run,
        manifest_tool.formal_command("ma6_a5_h30km", candidate_run),
    )
    assert calls == [manifest_tool.ROOT, manifest_tool.ROOT]
    assert candidate["source_identity"] is current["source_identity"]
    assert candidate["source_hashes_sha256"] is current["source_hashes_sha256"]


def test_official_source_contract_fails_before_solver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = tmp_path / "snapshot" / "tpg" / "ma6_a5_h30km"
    baseline.mkdir(parents=True)
    for name in (*manifest_tool.FORMAL_INPUTS, "manifest.json"):
        (baseline / name).write_text("{}\n", encoding="utf-8")

    def source_failure(*args: Any, **kwargs: Any) -> Any:
        raise manifest_tool.SourceIdentityError("SOURCE_IDENTITY_MISMATCH")

    def forbidden_solver(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("solver must not run after source preflight failure")

    monkeypatch.setattr(manifest_tool, "SNAPSHOT", tmp_path / "snapshot")
    monkeypatch.setattr(manifest_tool, "validate_current_source_contract", source_failure)
    monkeypatch.setattr(manifest_tool, "run_formal", forbidden_solver)
    with pytest.raises(manifest_tool.SourceIdentityError, match="SOURCE_IDENTITY_MISMATCH"):
        manifest_tool.compare_case("ma6_a5_h30km")


def _write_legacy_manifests(root: Path, count: int = 61) -> tuple[tuple[Path, Path], dict[Path, bytes]]:
    source_map = {f"legacy/source_{index:02d}.py": f"{index:064x}" for index in range(count)}
    paths = (root / "case-a" / "manifest.json", root / "case-b" / "manifest.json")
    originals: dict[Path, bytes] = {}
    for index, path in enumerate(paths):
        path.parent.mkdir(parents=True)
        manifest = {
            "manifest_schema": manifest_tool.MANIFEST_SCHEMA,
            "case_id": f"case-{index}",
            "source_hashes_sha256": source_map,
            "artifact_hashes_sha256": {
                "fields.npz": "a" * 64,
                "summary.json": "b" * 64,
            },
            "groups": {"count": 72},
        }
        raw = (json.dumps(manifest, indent=4) + "\n").encode()
        path.write_bytes(raw)
        (path.parent / "fields.npz").write_bytes(b"fields-fixture")
        (path.parent / "summary.json").write_bytes(b"summary-fixture")
        originals[path] = raw
    return paths, originals


@pytest.fixture
def migration_repo(tmp_path: Path) -> tuple[Path, tuple[str, ...], int, tuple[Path, Path], dict[Path, bytes]]:
    fixed_paths = tuple(f"fixed/source_{index}.txt" for index in range(6))
    repo, fixed_paths, expected_count = _init_source_repo(
        tmp_path,
        fixed_paths=fixed_paths,
        python_count=59,
    )
    paths, originals = _write_legacy_manifests(tmp_path / "manifests")
    return repo, fixed_paths, expected_count, paths, originals


def test_synthetic_61_to_65_source_only_migration_preserves_other_assets(
    migration_repo: tuple[Path, tuple[str, ...], int, tuple[Path, Path], dict[Path, bytes]],
) -> None:
    repo, fixed_paths, expected_count, paths, originals = migration_repo
    stable_assets = {
        path.parent: (
            (path.parent / "fields.npz").read_bytes(),
            (path.parent / "summary.json").read_bytes(),
        )
        for path in paths
    }
    canonical = manifest_tool.migrate_source_identity(
        paths,
        repo_root=repo,
        fixed_paths=fixed_paths,
        expected_count=expected_count,
    )

    assert len(canonical["source_hashes_sha256"]) == 65
    for path in paths:
        before = json.loads(originals[path])
        after = json.loads(path.read_text(encoding="utf-8"))
        manifest_tool._validate_source_only_change(before, after)
        manifest_tool.validate_source_identity_schema(
            after,
            expected_count=65,
            fixed_paths=fixed_paths,
        )
        assert after["case_id"] == before["case_id"]
        assert after["artifact_hashes_sha256"] == before["artifact_hashes_sha256"]
        assert after["groups"] == before["groups"]
        assert (
            (path.parent / "fields.npz").read_bytes(),
            (path.parent / "summary.json").read_bytes(),
        ) == stable_assets[path.parent]


def test_migration_rejects_mismatched_legacy_source_maps(
    migration_repo: tuple[Path, tuple[str, ...], int, tuple[Path, Path], dict[Path, bytes]],
) -> None:
    repo, fixed_paths, expected_count, paths, originals = migration_repo
    second = json.loads(paths[1].read_text(encoding="utf-8"))
    second["source_hashes_sha256"]["legacy/source_00.py"] = "f" * 64
    paths[1].write_text(json.dumps(second), encoding="utf-8")

    with pytest.raises(manifest_tool.SourceIdentityError, match="LEGACY_SOURCE_MAP_MISMATCH"):
        manifest_tool.migrate_source_identity(
            paths,
            repo_root=repo,
            fixed_paths=fixed_paths,
            expected_count=expected_count,
        )
    assert paths[0].read_bytes() == originals[paths[0]]


@pytest.mark.parametrize("failure", ["second-replace", "post-validation"])
def test_migration_failure_restores_both_original_manifest_bytes(
    migration_repo: tuple[Path, tuple[str, ...], int, tuple[Path, Path], dict[Path, bytes]],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    repo, fixed_paths, expected_count, paths, originals = migration_repo
    if failure == "second-replace":
        real_replace = manifest_tool.os.replace
        calls = 0

        def fail_second_replace(source: Path, target: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected second replace failure")
            real_replace(source, target)

        monkeypatch.setattr(manifest_tool.os, "replace", fail_second_replace)
    else:
        real_validate = manifest_tool.validate_source_identity_schema
        calls = 0

        def fail_post_validation(*args: Any, **kwargs: Any) -> None:
            nonlocal calls
            calls += 1
            if calls == 4:
                raise manifest_tool.SourceIdentityError("injected post validation failure")
            real_validate(*args, **kwargs)

        monkeypatch.setattr(manifest_tool, "validate_source_identity_schema", fail_post_validation)

    with pytest.raises((OSError, manifest_tool.SourceIdentityError)):
        manifest_tool.migrate_source_identity(
            paths,
            repo_root=repo,
            fixed_paths=fixed_paths,
            expected_count=expected_count,
        )
    assert {path: path.read_bytes() for path in paths} == originals
    assert not list(paths[0].parent.glob(".*.source-identity-*.tmp"))
    assert not list(paths[1].parent.glob(".*.source-identity-*.tmp"))


def test_migration_cli_requires_two_explicit_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["source-migration", "--migrate-source-identity"])
    with pytest.raises(SystemExit) as exc_info:
        manifest_tool.main()
    assert exc_info.value.code == 2


def test_migration_rejects_aliases_of_the_same_manifest(
    migration_repo: tuple[Path, tuple[str, ...], int, tuple[Path, Path], dict[Path, bytes]],
) -> None:
    repo, fixed_paths, expected_count, paths, _ = migration_repo
    alias = paths[0].parent / "." / paths[0].name
    with pytest.raises(manifest_tool.SourceIdentityError, match="MANIFEST_SET_INVALID"):
        manifest_tool.migrate_source_identity(
            (paths[0], alias),
            repo_root=repo,
            fixed_paths=fixed_paths,
            expected_count=expected_count,
        )


def test_migration_cli_rejects_candidate_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "source-migration",
            "--migrate-source-identity",
            "--manifest-path",
            "a.json",
            "--manifest-path",
            "b.json",
            "--case-id",
            "forbidden",
        ],
    )
    with pytest.raises(SystemExit) as exc_info:
        manifest_tool.main()
    assert exc_info.value.code == 2


def test_truncated_name_status_output_fails_closed() -> None:
    for output in (
        b"R100\x00only-old-path\x00",
        b"M\x00src/ref_enthalpy_method/module.py",
    ):
        with pytest.raises(manifest_tool.SourceIdentityError, match="parse-staged"):
            manifest_tool._parse_name_status(output, stage="staged")


def test_formal_command_cases_and_head_source_inventory_are_frozen() -> None:
    assert manifest_tool.CASES == EXPECTED_CASES
    for case_id, (mach, alpha, altitude) in EXPECTED_CASES.items():
        run_dir = manifest_tool.SNAPSHOT / "tpg" / case_id
        assert manifest_tool.formal_command(case_id, run_dir) == [
            sys.executable,
            str(manifest_tool.ROOT / "scripts" / "run_case_rem.py"),
            "--vehicle",
            str(manifest_tool.ROOT / "specs" / "vehicles" / "htv2_faceted3d_0629.yaml"),
            "--case",
            str(manifest_tool.ROOT / "specs" / "cases" / "doc_ma6_alpha5_h30km_faceted3d.yaml"),
            "--sampling",
            str(manifest_tool.ROOT / "specs" / "sampling" / "engineering_full_wing_surface_grid_81x41.yaml"),
            "--run_dir",
            str(run_dir),
            "--mach",
            str(mach),
            "--alpha",
            str(alpha),
            "--h_m",
            str(altitude),
            "--transition_weighting",
            "step",
            "--no_plots",
        ]

    source_paths = list(
        manifest_tool.build_canonical_source_identity(manifest_tool.ROOT)[
            "source_hashes_sha256"
        ]
    )
    assert len(source_paths) == 65
    assert hashlib.sha256(_canonical(source_paths)).hexdigest() == EXPECTED_SOURCE_PATHS_HASH
