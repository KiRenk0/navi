from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import numpy as np
import pytest

from ref_enthalpy_method.geometry.faceted3d import load_outline_csv
from ref_enthalpy_method.mapping.fluent_surface import read_fluent_surface_geometry_csv
from ref_enthalpy_method.n8_taw_surface import (
    load_n8_sampling_spec,
    load_n8_taw_case_spec,
    validate_n8_run_artifacts,
)

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "baselines/0920_fully_turbulent_taw"
VEHICLE = "specs/vehicles/htv2_faceted3d_0920.yaml"
SAMPLING = "specs/sampling/n8_taw_surface_grid_81x41.yaml"
STL = "data/geometry/0920/htv2_0920_aligned_clean_ascii.stl"
OUTLINE = "data/geometry/0920/outline_xz_right_0920.csv"
PROJECTION_CACHE = (
    "baselines/0920_fully_turbulent_taw/projection_cache/"
    "946a8a57d1249eec9a0996ce296c409f4055b39457d85aec8236a120c73b799f.npz"
)
CASE_PATHS = tuple(sorted((ROOT / "specs/cases").glob("n8_taw_*.yaml")))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _subprocess_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    return environment


@pytest.mark.parametrize("case_path", CASE_PATHS, ids=lambda path: path.stem)
def test_all_13_cases_use_the_single_0920_authority(case_path: Path) -> None:
    assert len(CASE_PATHS) == 13
    case = load_n8_taw_case_spec(case_path, repo_root=ROOT)
    assert case.vehicle_spec == VEHICLE
    assert case.sampling_spec == SAMPLING
    assert (ROOT / case.observation_csv).is_file()
    text = case_path.read_text(encoding="utf-8").lower()
    for forbidden in (
        "transition",
        "laminar",
        "radiative",
        "fixed_wall",
        "transient",
        "0628",
        "0629",
        "candidate",
    ):
        assert forbidden not in text


def test_0920_geometry_assets_have_one_active_location() -> None:
    assert (ROOT / STL).is_file()
    assert (ROOT / OUTLINE).is_file()
    assert not (ROOT / "new_spec").exists()


def test_missing_required_outline_fails_explicitly() -> None:
    with pytest.raises(FileNotFoundError, match="required 0920 outline"):
        load_outline_csv(csv_path=ROOT / "data/geometry/0920/missing.csv")


@pytest.mark.parametrize("case_path", CASE_PATHS, ids=lambda path: path.stem)
def test_case_fluent_geometry_matches_formal_projection_identity(case_path: Path) -> None:
    case = load_n8_taw_case_spec(case_path, repo_root=ROOT)
    source = read_fluent_surface_geometry_csv(
        ROOT / case.observation_csv, x_offset_m=case.fluent_x_offset_m
    )
    canonical = np.ascontiguousarray(source.canonical_solver_xyz)
    identity = json.loads((BASELINE / "manifest.json").read_text(encoding="utf-8"))[
        "projection_cache_identity"
    ]["identity"]
    assert hashlib.sha256(canonical.tobytes(order="C")).hexdigest() == identity[
        "fluent_canonical_geometry_sha256"
    ]


def test_missing_case_fails_fast() -> None:
    with pytest.raises(ValueError, match="failed to load YAML"):
        load_n8_taw_case_spec(ROOT / "specs/cases/missing.yaml", repo_root=ROOT)


def test_sampling_schema_has_no_mode_fallback() -> None:
    path = Path(__file__).with_name("invalid_sampling_mode.yaml")
    with pytest.raises(ValueError, match="fields must be exactly"):
        load_n8_sampling_spec(path, repo_root=ROOT)


def test_source_identity_matches_baseline_manifest() -> None:
    manifest = json.loads((BASELINE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_schema"] == "0920-fully-turbulent-taw-baseline/v1"
    assert manifest["geometry_authority"] == "0920"
    assert manifest["flow_regime"] == "fully_turbulent"
    assert manifest["thermal_target"] == "adiabatic_wall_temperature"
    paths = {
        "case_spec": ROOT
        / "specs/cases/n8_taw_ma8_a5_h40km_geometry0920_smoke.yaml",
        "vehicle_spec": ROOT / VEHICLE,
        "stl": ROOT / STL,
        "outline": ROOT / OUTLINE,
        "sampling_spec": ROOT / SAMPLING,
        "projection_cache": ROOT / PROJECTION_CACHE,
    }
    assert set(manifest["source_hashes_sha256"]) == set(paths)
    for label, path in paths.items():
        assert _sha256(path) == manifest["source_hashes_sha256"][label]

    summary = json.loads((BASELINE / "run/summary.json").read_text(encoding="utf-8"))
    cache = summary["contracts"]["projection_cache"]
    assert cache["path"] == PROJECTION_CACHE
    assert cache["key"] == Path(PROJECTION_CACHE).stem
    assert cache["sha256"] == _sha256(ROOT / PROJECTION_CACHE)


def test_baseline_manifest_verification_cli_has_one_run_authority() -> None:
    help_result = subprocess.run(
        [sys.executable, "scripts/tools/0920_taw_baseline.py", "--help"],
        cwd=ROOT,
        env=_subprocess_environment(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "--run-dir" not in help_result.stdout

    verify_result = subprocess.run(
        [
            sys.executable,
            "scripts/tools/0920_taw_baseline.py",
            "--manifest",
            str(BASELINE / "manifest.json"),
        ],
        cwd=ROOT,
        env=_subprocess_environment(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert verify_result.returncode == 0, verify_result.stderr


def test_baseline_artifact_contract() -> None:
    fields_path = BASELINE / "run/Taw_surface_fields.npz"
    with np.load(fields_path, allow_pickle=False) as fields:
        assert len(fields.files) == 88
        forbidden = {"w_tr", "q_lam_w", "q_turb_w", "transition_x", "transition_index"}
        assert forbidden.isdisjoint(fields.files)
        assert all("legacy" not in field.lower() for field in fields.files)

        taw = np.asarray(fields["Taw_prediction_K"], dtype=float)
        valid = np.asarray(fields["valid"], dtype=bool)
        provider = np.asarray(fields["provider"])
        assert taw.ndim == 1
        assert taw.shape == valid.shape == provider.shape
        assert np.any(valid)
        assert np.all(np.isfinite(taw[valid]))
        assert set(np.unique(provider[valid])) <= {
            "windward_turbulent",
            "leeward_recovery",
            "near_tangent_blend",
        }
    assert validate_n8_run_artifacts(BASELINE / "run")["status"] == "PASS"


@pytest.mark.integration
def test_official_cli_produces_valid_taw_artifacts() -> None:
    run_dir = ROOT / "runs/n8_taw_surface" / f"pytest_official_{uuid.uuid4().hex}"
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/run_n8_taw_case.py",
                "--case",
                "specs/cases/n8_taw_ma8_a5_h40km.yaml",
                "--mach",
                "8",
                "--alpha_deg",
                "5",
                "--h_m",
                "40000",
                "--run_dir",
                str(run_dir.relative_to(ROOT)),
            ],
            cwd=ROOT,
            env=_subprocess_environment(),
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert validate_n8_run_artifacts(run_dir)["status"] == "PASS"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


@pytest.mark.integration
def test_baseline_replay_recomputes_and_compares_every_npz_field() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/tools/0920_taw_baseline.py",
            "--manifest",
            str(BASELINE / "manifest.json"),
            "--replay",
        ],
        cwd=ROOT,
        env=_subprocess_environment(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
