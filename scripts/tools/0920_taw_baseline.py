#!/usr/bin/env python3
"""Freeze and verify the formal 0920 fully-turbulent Taw baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

CONTRACT = {
    "geometry_authority": "0920",
    "flow_regime": "fully_turbulent",
    "thermal_target": "adiabatic_wall_temperature",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required(path: Path, label: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def build_manifest(*, repo_root: Path, baseline_dir: Path) -> dict[str, Any]:
    run_dir = baseline_dir / "run"
    summary_path = _required(run_dir / "summary.json", "run summary")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    contracts = summary.get("contracts", {})
    if summary.get("status") != "PASS":
        raise ValueError("baseline run summary must have status PASS")
    if contracts.get("flow_regime") != "fully turbulent" or contracts.get("temperature") != "Taw only":
        raise ValueError("run is not the formal fully-turbulent Taw contract")

    source_paths = {
        "case_spec": repo_root / "specs/cases/n8_taw_ma5_a10_h60km.yaml",
        "vehicle_spec": repo_root / "specs/vehicles/htv2_faceted3d_0920.yaml",
        "stl": repo_root / "data/geometry/0920/htv2_0920_aligned_clean_ascii.stl",
        "outline": repo_root / "data/geometry/0920/outline_xz_right_0920.csv",
        "sampling_spec": repo_root / "specs/sampling/n8_taw_surface_grid_81x41.yaml",
    }
    source_hashes = {
        label: sha256(_required(path, label)) for label, path in source_paths.items()
    }
    projection = summary.get("contracts", {}).get("projection_cache", {})
    cache_path = (repo_root / str(projection.get("path", ""))).resolve()
    expected_cache_path = (
        baseline_dir
        / "projection_cache"
        / "122eb1679442ec614c1e87ba64be1ef30e3e291f163e3d46ad9521707dfc5269.npz"
    ).resolve()
    if cache_path != expected_cache_path:
        raise ValueError("run summary does not reference the formal baseline projection cache")
    source_hashes["projection_cache"] = sha256(_required(cache_path, "projection cache"))

    artifact_hashes = {
        path.name: sha256(path)
        for path in sorted(run_dir.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
    return {
        "manifest_schema": "0920-fully-turbulent-taw-baseline/v1",
        **CONTRACT,
        "case_id": summary["case_id"],
        "run_summary": "summary.json",
        "source_hashes_sha256": source_hashes,
        "artifact_hashes_sha256": artifact_hashes,
        "summary_sha256": sha256(summary_path),
        "projection_cache_identity": projection,
    }


def verify_manifest(*, repo_root: Path, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_schema") != "0920-fully-turbulent-taw-baseline/v1":
        raise ValueError("unexpected baseline manifest schema")
    for key, value in CONTRACT.items():
        if manifest.get(key) != value:
            raise ValueError(f"baseline contract mismatch for {key}: {manifest.get(key)!r}")
    expected = build_manifest(repo_root=repo_root, baseline_dir=manifest_path.parent)
    if expected != manifest:
        raise ValueError("baseline manifest does not match source or run artifacts")


def replay_and_compare(*, repo_root: Path, manifest_path: Path) -> None:
    from ref_enthalpy_method.n8_taw_surface import run_n8_taw_case

    baseline_run = manifest_path.parent / "run"
    run_root = repo_root / "runs/n8_taw_surface"
    run_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="baseline_replay_", dir=run_root) as directory:
        replay_dir = Path(directory) / "run"
        run_n8_taw_case(
            repo_root=repo_root,
            case_spec_path="specs/cases/n8_taw_ma5_a10_h60km.yaml",
            run_dir=replay_dir.relative_to(repo_root),
            mach=5.0,
            alpha_deg=10.0,
            T_inf_K=None,
            p_inf_Pa=None,
            h_m=60_000.0,
        )
        with np.load(baseline_run / "Taw_surface_fields.npz", allow_pickle=False) as baseline, np.load(
            replay_dir / "Taw_surface_fields.npz", allow_pickle=False
        ) as replay:
            if baseline.files != replay.files:
                raise ValueError("baseline field schema differs from replay")
            for field in baseline.files:
                expected = np.asarray(baseline[field])
                actual = np.asarray(replay[field])
                equal = (
                    np.array_equal(expected, actual, equal_nan=True)
                    if expected.dtype.kind in "fc"
                    else np.array_equal(expected, actual)
                )
                if not equal:
                    raise ValueError(f"baseline replay mismatch in field {field}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    manifest_path = args.manifest.resolve()
    manifest = build_manifest(repo_root=root, baseline_dir=manifest_path.parent)
    if args.freeze:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"baseline manifest written: {manifest_path}")
        return 0
    verify_manifest(repo_root=root, manifest_path=manifest_path)
    if args.replay:
        replay_and_compare(repo_root=root, manifest_path=manifest_path)
    print(f"0920 Taw baseline PASS: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
