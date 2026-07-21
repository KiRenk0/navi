"""Contract and isolation tests for the unregistered TPG candidate manifest."""

from __future__ import annotations

import hashlib
import json
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
    "source_hashes_sha256",
    "artifact_hashes_sha256",
    "manifest_generator",
    "generator_cli_template",
]
EXPECTED_CASES = {
    "ma6_a5_h30km": (6.0, 5.0, 30000.0),
    "ma8_a5_h40km": (8.0, 5.0, 40000.0),
}
EXPECTED_V5_CANONICAL_HASHES = {
    "ma6_a5_h30km": "67ae41058a997c076874f7fc6fad96cbd4b0b4bcb6c750eb282b175a0c2e2564",
    "ma8_a5_h40km": "932c2bff9e5406f5d12faa72f397f23978eaf87ca74a847284886d91b1749b23",
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
    "source_hashes_sha256",
    "artifact_hashes_sha256",
    "baseline_generator",
    "generator_cli_template",
]
EXPECTED_SOURCE_PATHS_HASH = (
    "cfe02f0f9ada5a464121b840297d1aa6d62d56b8619d3d9634c9cf1649b13fa1"
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
    assert manifest["source_hashes_sha256"] == {
        str(path.relative_to(manifest_tool.ROOT)).replace("\\", "/"): manifest_tool.sha256(path)
        for path in manifest_tool.source_files()
    }


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
    monkeypatch.setattr(manifest_tool.subprocess, "run", forbidden)
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


def test_v5_builder_canonical_output_is_frozen() -> None:
    for case_id, expected_hash in EXPECTED_V5_CANONICAL_HASHES.items():
        run_dir = manifest_tool.SNAPSHOT / "tpg" / case_id
        command = manifest_tool.formal_command(case_id, run_dir)
        manifest = manifest_tool.build_manifest(case_id, run_dir, command)
        assert list(manifest) == EXPECTED_V5_KEYS
        assert manifest["manifest_schema"] == "current-tpg-baseline-regression/v5"
        assert hashlib.sha256(_canonical(manifest)).hexdigest() == expected_hash


def test_formal_command_cases_and_source_inventory_are_frozen() -> None:
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

    source_paths = [
        str(path.relative_to(manifest_tool.ROOT)).replace("\\", "/")
        for path in manifest_tool.source_files()
    ]
    assert len(source_paths) == 61
    assert hashlib.sha256(_canonical(source_paths)).hexdigest() == EXPECTED_SOURCE_PATHS_HASH
