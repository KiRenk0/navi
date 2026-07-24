#!/usr/bin/env python3
"""Freeze or verify the post-2026-07-12 current TPG regression baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from ref_enthalpy_method.gas import make_fluent_tpg_thermo, mu_sutherland
from ref_enthalpy_method.geometry.local_incidence import SURFACE_CLASS_LEEWARD
from ref_enthalpy_method.mapping.observation_binding import (
    build_approved_observation_binding,
    exact_freestream_cli_arguments,
    validate_exact_freestream_summary,
    validate_observation_binding,
)

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "runs" / "current_baseline_snapshot"
CANDIDATE_RUNS_ROOT = ROOT / "runs"
RUNNER = ROOT / "scripts" / "run_case_rem.py"
VEHICLE = ROOT / "specs" / "vehicles" / "htv2_faceted3d_0629.yaml"
CASE = ROOT / "specs" / "cases" / "doc_ma6_alpha5_h30km_faceted3d.yaml"
SAMPLING = ROOT / "specs" / "sampling" / "engineering_full_wing_surface_grid_81x41.yaml"
DATE = "2026-07-14"
TOL = 1e-9
NX, NY = 81, 41
CASES = {
    "ma6_a5_h30km": (6.0, 5.0, 30000.0),
    "ma8_a5_h40km": (8.0, 5.0, 40000.0),
}
FORMAL_INPUTS = {"vehicle.yaml": VEHICLE, "case.yaml": CASE, "sampling.yaml": SAMPLING}
GROUPS = {
    "Group 1 Geometry / sampling": (
        "x_w_m", "span_w_m", "x_l_m", "span_l_m", "xc_grid", "yb_grid",
        "xc_w", "yb_w", "xc_l", "yb_l", "mask_w", "mask_l",
    ),
    "Group 2 Pressure / incidence": ("phi_w", "cp_w", "cp0_w"),
    "Group 3 Edge-state / transport": (
        "ma_e_w", "T_e_w", "p_e_w", "rho_e_w", "v_e_w", "mu_e_w", "h_e_w",
        "re_edge", "re_tri", "re_x_star", "re_x_over_re_tri",
    ),
    "Group 4 TPG / Taw": ("Taw_tpg_w",),
    "Group 5 q-chain": (
        "q_w", "q_lam_w", "q_turb_w", "w_tr", "T_r_lam_w", "T_r_turb_w",
        "h_r_lam_w", "h_r_turb_w", "h_star_lam_w", "h_star_turb_w",
    ),
    "Group 6 Leeward legacy fields": ("q_l", "St_l", "Re_ns_l", "Tw_l"),
    "Group 7 Local-incidence diagnostic": (
        "normal_x_upper", "normal_y_upper", "normal_z_upper",
        "normal_x_lower", "normal_y_lower", "normal_z_lower",
        "incidence_s_upper", "incidence_s_lower",
        "surface_class_upper", "surface_class_lower",
        "normal_source_upper", "normal_source_lower",
    ),
    "Group 8 Sheet-specific leeward freestream-recovery TPG Taw diagnostic": (
        "mask_leeward_upper", "mask_leeward_lower",
        "T_e_leeward_upper", "T_e_leeward_lower",
        "p_e_leeward_upper", "p_e_leeward_lower",
        "rho_e_leeward_upper", "rho_e_leeward_lower",
        "V_e_leeward_upper", "V_e_leeward_lower",
        "Ma_e_leeward_upper", "Ma_e_leeward_lower",
        "h_e_leeward_upper", "h_e_leeward_lower",
        "mu_e_leeward_upper", "mu_e_leeward_lower",
        "Taw_tpg_leeward_upper", "Taw_tpg_leeward_lower",
    ),
}
ADDITIONAL_FIELDS = {"Tw_w"}
GROUP8_MASK_FIELDS = {"upper": "mask_leeward_upper", "lower": "mask_leeward_lower"}
GROUP8_FLOAT_FIELDS = {
    sheet: tuple(
        f"{stem}_leeward_{sheet}"
        for stem in ("T_e", "p_e", "rho_e", "V_e", "Ma_e", "h_e", "mu_e", "Taw_tpg")
    )
    for sheet in ("upper", "lower")
}
EXPECTED_FIELD_COUNT = 72
FIELD_SHAPE = (NX * NY,)
METADATA_FIELDS = (
    "suite_type", "case", "freestream", "atmosphere", "thermo", "pressure", "grid",
    "endpoint_metadata", "local_incidence",
)
LOCAL_INCIDENCE_METADATA = {
    "local_incidence_status": "frozen_diagnostic",
    "local_incidence_formula": "-dot(u_hat, n_out)",
    "alpha_basis": "geometric_alpha",
    "epsilon": 0.05,
    "upper_normal_orientation": "nz_positive",
    "lower_normal_orientation": "nz_negative",
    "raw_stl_normal_preferred": True,
    "formal_alpha_sign_routing_unchanged": True,
    "taw_tpg_l_implemented": False,
}
LOCAL_INCIDENCE_EPSILON = 0.05
CANDIDATE_MANIFEST_SCHEMA = "tpg-candidate-manifest/v1"
CANDIDATE_PROVENANCE = (
    "Unregistered TPG candidate run manifest; source/artifact identity only; "
    "not baseline-admitted, not promoted, and not formal evidence."
)
CANDIDATE_MANIFEST_GENERATOR = (
    "scripts/tools/current_baseline_regression_check.py --candidate-manifest"
)
MANIFEST_SCHEMA = "current-tpg-baseline-regression/v5"
SOURCE_IDENTITY_SCHEMA = "git-head-tree-source-identity/v1"
SOURCE_IDENTITY_KEYS = (
    "schema",
    "authority",
    "canonical_bytes",
    "digest_algorithm",
    "path_format",
    "inventory_rule",
    "ordering",
    "inventory_paths_sha256",
    "aggregate_sha256",
)
FIXED_PRODUCTION_PATHS = (
    "scripts/run_case_rem.py",
    "scripts/tools/n6_exact_custom_formal_entry.py",
    "specs/vehicles/htv2_faceted3d_0629.yaml",
    "specs/cases/doc_ma6_alpha5_h30km_faceted3d.yaml",
    "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml",
    "new_spec/htv2_0628.stl",
    "new_spec/outline_xz_right_0629.csv",
)
PYTHON_SOURCE_PREFIX = "src/ref_enthalpy_method/"
EXPECTED_PRODUCTION_SOURCE_COUNT = 66
SOURCE_IDENTITY_MUTABLE_FIELDS = frozenset(
    {"source_hashes_sha256", "source_identity"}
)


class SourceIdentityError(RuntimeError):
    """Fail-closed source identity or repository-state defect."""


class ProductionSourceDirtyError(SourceIdentityError):
    def __init__(self, defects: Sequence[str]) -> None:
        self.defects = tuple(defects)
        super().__init__("; ".join(self.defects))


def _compact_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _run_git_bytes(
    repo_root: Path,
    args: Sequence[str],
    *,
    stage: str,
    source_path: str = "<repository>",
) -> bytes:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceIdentityError(
            f"GIT_COMMAND_FAILED path={source_path} stage={stage}"
        ) from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise SourceIdentityError(
            f"GIT_COMMAND_FAILED path={source_path} stage={stage} detail={detail!r}"
        )
    return result.stdout


def resolve_head_commit(repo_root: Path = ROOT) -> str:
    value = _run_git_bytes(
        repo_root,
        ["rev-parse", "--verify", "HEAD^{commit}"],
        stage="resolve-head-commit",
    ).strip()
    try:
        head = value.decode("ascii")
    except UnicodeDecodeError as exc:
        raise SourceIdentityError(
            "GIT_COMMAND_FAILED path=<repository> stage=decode-head-commit"
        ) from exc
    if re.fullmatch(r"[0-9a-f]{40,64}", head) is None:
        raise SourceIdentityError(
            "GIT_COMMAND_FAILED path=<repository> stage=validate-head-commit"
        )
    return head


def _parse_ls_tree_record(record: bytes) -> tuple[str, str, str, str]:
    try:
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split(" ", 2)
        path = raw_path.decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise SourceIdentityError(
            "INVALID_HEAD_TREE_ENTRY path=<unknown> stage=parse-ls-tree"
        ) from exc
    return mode, object_type, object_id, path


def _head_tree_entries(repo_root: Path, head_commit: str) -> dict[str, tuple[str, str, str]]:
    output = _run_git_bytes(
        repo_root,
        ["ls-tree", "-r", "-t", "-z", head_commit],
        stage="list-head-tree",
    )
    entries: dict[str, tuple[str, str, str]] = {}
    for record in output.split(b"\0"):
        if not record:
            continue
        mode, object_type, object_id, path = _parse_ls_tree_record(record)
        if path in entries:
            raise SourceIdentityError(
                f"INVALID_HEAD_TREE_ENTRY path={path} stage=duplicate-head-path"
            )
        entries[path] = (mode, object_type, object_id)
    return entries


def read_head_tree_entry(
    repo_root: Path,
    path: str,
    *,
    head_commit: str | None = None,
) -> tuple[str, str, str]:
    head = head_commit or resolve_head_commit(repo_root)
    output = _run_git_bytes(
        repo_root,
        ["ls-tree", "-z", head, "--", path],
        stage="read-head-tree-entry",
        source_path=path,
    )
    records = [record for record in output.split(b"\0") if record]
    if len(records) != 1:
        raise SourceIdentityError(
            f"MISSING_HEAD_SOURCE path={path} stage=read-head-tree-entry"
        )
    mode, object_type, object_id, actual_path = _parse_ls_tree_record(records[0])
    if actual_path != path:
        raise SourceIdentityError(
            f"INVALID_HEAD_TREE_ENTRY path={path} stage=path-mismatch"
        )
    return mode, object_type, object_id


def _is_inventory_python_path(path: str) -> bool:
    return (
        path.startswith(PYTHON_SOURCE_PREFIX)
        and path.endswith(".py")
        and len(path) > len(PYTHON_SOURCE_PREFIX) + 3
    )


def build_head_production_inventory(
    repo_root: Path = ROOT,
    *,
    fixed_paths: Sequence[str] = FIXED_PRODUCTION_PATHS,
    expected_count: int = EXPECTED_PRODUCTION_SOURCE_COUNT,
    head_commit: str | None = None,
) -> list[tuple[str, str]]:
    head = head_commit or resolve_head_commit(repo_root)
    entries = _head_tree_entries(repo_root, head)
    normalized_fixed = tuple(fixed_paths)
    if len(set(normalized_fixed)) != len(normalized_fixed):
        raise SourceIdentityError(
            "INVALID_HEAD_TREE_ENTRY path=<fixed-prefix> stage=duplicate-fixed-path"
        )
    missing = [path for path in normalized_fixed if path not in entries]
    if missing:
        raise SourceIdentityError(
            f"MISSING_HEAD_SOURCE path={missing[0]} stage=build-inventory"
        )
    python_paths = sorted(path for path in entries if _is_inventory_python_path(path))
    ordered_paths = [*normalized_fixed, *python_paths]
    if len(set(ordered_paths)) != len(ordered_paths):
        raise SourceIdentityError(
            "INVALID_HEAD_TREE_ENTRY path=<inventory> stage=duplicate-production-path"
        )

    inventory: list[tuple[str, str]] = []
    for path in ordered_paths:
        mode, object_type, object_id = entries[path]
        if mode not in {"100644", "100755"} or object_type != "blob":
            raise SourceIdentityError(
                "INVALID_HEAD_TREE_ENTRY "
                f"path={path} stage=validate-entry mode={mode} type={object_type}"
            )
        inventory.append((path, object_id))
    if len(inventory) != expected_count:
        raise SourceIdentityError(
            "INVENTORY_COUNT_DRIFT path=<inventory> stage=build-inventory "
            f"expected={expected_count} actual={len(inventory)}"
        )
    return inventory


def read_git_blob_bytes(repo_root: Path, path: str, object_id: str) -> bytes:
    return _run_git_bytes(
        repo_root,
        ["cat-file", "blob", object_id],
        stage="read-git-blob",
        source_path=path,
    )


def build_canonical_source_identity(
    repo_root: Path = ROOT,
    *,
    fixed_paths: Sequence[str] = FIXED_PRODUCTION_PATHS,
    expected_count: int = EXPECTED_PRODUCTION_SOURCE_COUNT,
) -> dict[str, Any]:
    head = resolve_head_commit(repo_root)
    inventory = build_head_production_inventory(
        repo_root,
        fixed_paths=fixed_paths,
        expected_count=expected_count,
        head_commit=head,
    )
    records: list[list[str]] = []
    source_hashes: dict[str, str] = {}
    for path, object_id in inventory:
        digest = hashlib.sha256(read_git_blob_bytes(repo_root, path, object_id)).hexdigest()
        source_hashes[path] = digest
        records.append([path, digest])
    paths = list(source_hashes)
    source_identity = {
        "schema": SOURCE_IDENTITY_SCHEMA,
        "authority": "git-head-tree",
        "canonical_bytes": "git-blob",
        "digest_algorithm": "sha256",
        "path_format": "repo-relative-posix",
        "inventory_rule": "production-source-inventory/v1",
        "ordering": "fixed-prefix-then-posix-lexicographic",
        "inventory_paths_sha256": hashlib.sha256(_compact_json(paths)).hexdigest(),
        "aggregate_sha256": hashlib.sha256(_compact_json(records)).hexdigest(),
    }
    contract = {
        "source_identity": source_identity,
        "source_hashes_sha256": source_hashes,
    }
    validate_source_identity_schema(
        contract,
        expected_count=expected_count,
        fixed_paths=fixed_paths,
    )
    return contract


def validate_source_identity_schema(
    manifest: dict[str, Any],
    *,
    expected_count: int = EXPECTED_PRODUCTION_SOURCE_COUNT,
    fixed_paths: Sequence[str] = FIXED_PRODUCTION_PATHS,
) -> None:
    source_identity = manifest.get("source_identity")
    source_hashes = manifest.get("source_hashes_sha256")
    if not isinstance(source_identity, dict) or tuple(source_identity) != SOURCE_IDENTITY_KEYS:
        raise SourceIdentityError(
            "SOURCE_IDENTITY_SCHEMA_MISMATCH path=<manifest> stage=source-identity-shape"
        )
    expected_constants = {
        "schema": SOURCE_IDENTITY_SCHEMA,
        "authority": "git-head-tree",
        "canonical_bytes": "git-blob",
        "digest_algorithm": "sha256",
        "path_format": "repo-relative-posix",
        "inventory_rule": "production-source-inventory/v1",
        "ordering": "fixed-prefix-then-posix-lexicographic",
    }
    if any(source_identity.get(key) != value for key, value in expected_constants.items()):
        raise SourceIdentityError(
            "SOURCE_IDENTITY_SCHEMA_MISMATCH path=<manifest> stage=source-identity-constants"
        )
    if not isinstance(source_hashes, dict) or len(source_hashes) != expected_count:
        raise SourceIdentityError(
            "SOURCE_IDENTITY_SCHEMA_MISMATCH path=<manifest> stage=source-map-count"
        )
    paths = list(source_hashes)
    fixed_prefix = list(fixed_paths)
    if (
        paths[: len(fixed_prefix)] != fixed_prefix
        or paths[len(fixed_prefix) :] != sorted(paths[len(fixed_prefix) :])
        or any(not _is_inventory_python_path(path) for path in paths[len(fixed_prefix) :])
    ):
        raise SourceIdentityError(
            "SOURCE_IDENTITY_SCHEMA_MISMATCH path=<manifest> stage=inventory-ordering"
        )
    if any(
        not isinstance(path, str)
        or path.startswith("/")
        or "\\" in path
        or Path(path).is_absolute()
        for path in paths
    ):
        raise SourceIdentityError(
            "SOURCE_IDENTITY_SCHEMA_MISMATCH path=<manifest> stage=path-format"
        )
    if any(
        not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        for digest in source_hashes.values()
    ):
        raise SourceIdentityError(
            "SOURCE_IDENTITY_SCHEMA_MISMATCH path=<manifest> stage=source-digest"
        )
    records = [[path, source_hashes[path]] for path in paths]
    expected_paths_digest = hashlib.sha256(_compact_json(paths)).hexdigest()
    expected_aggregate = hashlib.sha256(_compact_json(records)).hexdigest()
    if source_identity.get("inventory_paths_sha256") != expected_paths_digest:
        raise SourceIdentityError(
            "SOURCE_IDENTITY_SCHEMA_MISMATCH path=<manifest> stage=inventory-paths-digest"
        )
    if source_identity.get("aggregate_sha256") != expected_aggregate:
        raise SourceIdentityError(
            "SOURCE_IDENTITY_SCHEMA_MISMATCH path=<manifest> stage=aggregate-digest"
        )


def _parse_name_status(output: bytes, *, stage: str) -> list[tuple[str, tuple[str, ...]]]:
    try:
        if output and not output.endswith(b"\0"):
            raise ValueError("name-status output is not NUL terminated")
        tokens = output.split(b"\0")
        rows: list[tuple[str, tuple[str, ...]]] = []
        index = 0
        while index < len(tokens) and tokens[index]:
            status = tokens[index].decode("ascii")
            index += 1
            path_count = 2 if status.startswith(("R", "C")) else 1
            if index + path_count > len(tokens):
                raise ValueError("truncated name-status record")
            paths = tuple(tokens[index + offset].decode("utf-8") for offset in range(path_count))
            if any(not path for path in paths):
                raise ValueError("empty name-status path")
            index += path_count
            rows.append((status, paths))
    except (UnicodeDecodeError, ValueError, IndexError) as exc:
        raise SourceIdentityError(
            f"GIT_COMMAND_FAILED path=<repository> stage=parse-{stage}"
        ) from exc
    return rows


def _is_production_path(path: str, inventory_paths: set[str]) -> bool:
    return path in inventory_paths or _is_inventory_python_path(path)


def validate_production_source_clean(
    repo_root: Path = ROOT,
    *,
    fixed_paths: Sequence[str] = FIXED_PRODUCTION_PATHS,
    expected_count: int = EXPECTED_PRODUCTION_SOURCE_COUNT,
) -> None:
    inventory_paths = {
        path
        for path, _ in build_head_production_inventory(
            repo_root,
            fixed_paths=fixed_paths,
            expected_count=expected_count,
        )
    }
    defects: list[str] = []
    diff_specs = (
        (
            "staged",
            ["diff", "--cached", "--name-status", "-z", "-M", "HEAD"],
            "STAGED_PRODUCTION_SOURCE",
        ),
        (
            "unstaged",
            ["diff", "--name-status", "-z", "-M"],
            "UNSTAGED_PRODUCTION_SOURCE",
        ),
    )
    for stage, args, modification_code in diff_specs:
        rows = _parse_name_status(
            _run_git_bytes(repo_root, args, stage=f"production-{stage}-diff"),
            stage=stage,
        )
        for status, paths in rows:
            if not any(_is_production_path(path, inventory_paths) for path in paths):
                continue
            if status.startswith("R"):
                code = "RENAMED_PRODUCTION_SOURCE"
            elif status.startswith("D"):
                code = "DELETED_PRODUCTION_SOURCE"
            else:
                code = modification_code
            defects.append(
                f"{code} stage={stage} path={' -> '.join(paths)} status={status}"
            )

    untracked = _run_git_bytes(
        repo_root,
        [
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            PYTHON_SOURCE_PREFIX.rstrip("/"),
        ],
        stage="production-untracked-sources",
    )
    for raw_path in untracked.split(b"\0"):
        if not raw_path:
            continue
        try:
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceIdentityError(
                "GIT_COMMAND_FAILED path=<unknown> stage=decode-untracked-source"
            ) from exc
        if _is_inventory_python_path(path):
            defects.append(
                f"UNTRACKED_PRODUCTION_SOURCE stage=untracked path={path} status=?"
            )
    if defects:
        raise ProductionSourceDirtyError(defects)


def validate_current_source_contract(
    baseline_manifest: dict[str, Any],
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    validate_production_source_clean(repo_root)
    canonical_source = build_canonical_source_identity(repo_root)
    validate_source_identity_schema(baseline_manifest)
    if baseline_manifest["source_identity"] != canonical_source["source_identity"]:
        raise SourceIdentityError(
            "SOURCE_IDENTITY_MISMATCH path=<manifest> stage=official-comparison"
        )
    if baseline_manifest["source_hashes_sha256"] != canonical_source["source_hashes_sha256"]:
        raise SourceIdentityError(
            "SOURCE_HASH_MAP_MISMATCH path=<manifest> stage=official-comparison"
        )
    return canonical_source


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_artifact_hashes(
    case_id: str,
    baseline_dir: Path,
    manifest: dict[str, Any],
) -> tuple[bool, list[str]]:
    registered_hashes = manifest.get("artifact_hashes_sha256")
    if not isinstance(registered_hashes, dict) or not registered_hashes:
        return False, [
            f"case={case_id} artifact=<manifest:artifact_hashes_sha256> "
            f"registered={registered_hashes!r} actual=<not-computed> reason=missing-or-invalid-map"
        ]

    errors: list[str] = []
    required_artifacts = (
        {"fields.npz", "summary.json"}
        if manifest.get("manifest_schema") == "current-tpg-baseline-regression/v5"
        else set()
    )
    artifact_names = set(registered_hashes) | required_artifacts
    baseline_root = baseline_dir.resolve()

    for artifact_name in sorted(artifact_names, key=str):
        registered = registered_hashes.get(artifact_name, "<missing>")
        if not isinstance(artifact_name, str):
            errors.append(
                f"case={case_id} artifact={artifact_name!r} registered={registered!r} "
                "actual=<not-computed> reason=artifact-path-not-string"
            )
            continue

        artifact_path = (baseline_dir / artifact_name).resolve()
        try:
            artifact_path.relative_to(baseline_root)
        except ValueError:
            errors.append(
                f"case={case_id} artifact={artifact_name} registered={registered!r} "
                "actual=<not-computed> reason=artifact-path-outside-baseline"
            )
            continue

        actual = sha256(artifact_path) if artifact_path.is_file() else "<missing>"
        digest_valid = isinstance(registered, str) and re.fullmatch(r"[0-9a-f]{64}", registered) is not None
        if actual == "<missing>":
            reason = "artifact-file-missing"
        elif not digest_valid:
            reason = "registered-digest-not-lowercase-sha256"
        elif registered != actual:
            reason = "artifact-hash-mismatch"
        else:
            continue
        errors.append(
            f"case={case_id} artifact={artifact_name} registered={registered!r} "
            f"actual={actual} reason={reason}"
        )

    return not errors, errors


def _formal_observation_binding(case_id: str) -> Any:
    binding = build_approved_observation_binding(case_id, ROOT)
    passed, reason = validate_observation_binding(binding, repo_root=ROOT)
    if not passed:
        raise ValueError(f"formal observation binding rejected: {reason}")
    return binding


def formal_command(case_id: str, run_dir: Path) -> list[str]:
    mach, alpha, altitude = CASES[case_id]
    binding = _formal_observation_binding(case_id)
    if (
        binding.mach != Decimal(str(mach))
        or binding.alpha_deg != Decimal(str(alpha))
        or binding.geometric_altitude_m != Decimal(str(altitude))
    ):
        raise ValueError("formal case tuple does not exactly match observation identity")
    explicit_arguments = exact_freestream_cli_arguments(
        binding,
        T_inf_K=binding.T_inf_K,
        p_inf_Pa=binding.p_inf_Pa,
    )
    return [
        sys.executable, str(RUNNER), "--vehicle", str(VEHICLE), "--case", str(CASE),
        "--sampling", str(SAMPLING), "--run_dir", str(run_dir), "--mach", str(mach),
        "--alpha", str(alpha), "--h_m", str(altitude),
        *explicit_arguments,
        "--transition_weighting", "step", "--no_plots",
    ]


def run_formal(case_id: str, out: Path) -> list[str]:
    command = formal_command(case_id, out)
    subprocess.run(command, cwd=ROOT, check=True)
    for name in ("fields.npz", "summary.json"):
        if not (out / name).is_file():
            raise RuntimeError(f"formal runner did not produce {out / name}")
    return command


def baseline_replay_command(case_id: str, run_dir: Path) -> list[str]:
    mach, alpha, altitude = CASES[case_id]
    return [
        sys.executable, str(RUNNER), "--vehicle", str(VEHICLE), "--case", str(CASE),
        "--sampling", str(SAMPLING), "--run_dir", str(run_dir), "--mach", str(mach),
        "--alpha", str(alpha), "--h_m", str(altitude),
        "--transition_weighting", "step", "--no_plots",
    ]


def run_baseline_replay(case_id: str, out: Path) -> list[str]:
    command = baseline_replay_command(case_id, out)
    subprocess.run(command, cwd=ROOT, check=True)
    for name in ("fields.npz", "summary.json"):
        if not (out / name).is_file():
            raise RuntimeError(f"baseline replay did not produce {out / name}")
    return command


def nested(obj: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if not isinstance(obj, dict) or key not in obj:
            return default
        obj = obj[key]
    return obj


def endpoint_from_fields(fields: Any) -> dict[str, Any]:
    yb_grid = np.asarray(fields["yb_grid"], dtype=float).reshape(-1)
    span_w = np.asarray(fields["span_w_m"], dtype=float).reshape(NY, NX)
    x_w = np.asarray(fields["x_w_m"], dtype=float).reshape(NY, NX)
    mask_w = np.asarray(fields["mask_w"]).reshape(NY, NX).astype(bool)
    valid = mask_w[-1] & np.isfinite(x_w[-1]) & np.isfinite(span_w[-1])
    endpoint_span = float(np.nanmedian(span_w[-1][valid])) if np.any(valid) else None
    xc_grid = np.asarray(fields["xc_grid"], dtype=float).reshape(-1)
    sampled_dx = float(np.nanmax(x_w[-1][valid]) - np.nanmin(x_w[-1][valid])) if np.any(valid) else None
    sampled_dxc = float(np.nanmax(xc_grid) - np.nanmin(xc_grid))
    endpoint_chord = sampled_dx / sampled_dxc if sampled_dx is not None and sampled_dxc > 0.0 else None
    return {
        "row_index": NY - 1,
        "row_compared": True,
        "yb_grid_last": float(yb_grid[-1]),
        "physical_span_m": endpoint_span,
        "endpoint_chord_m": endpoint_chord,
        "row_valid_count": int(np.count_nonzero(valid)),
    }


def _finite_float(name: str, value: Any, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite float")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite float") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite float")
    if positive and result <= 0.0:
        raise ValueError(f"{name} must be greater than zero")
    return result


def _validate_explicit_freestream_pair(
    *,
    T_inf_K: float | None,
    p_inf_Pa: float | None,
) -> tuple[float | None, float | None]:
    if (T_inf_K is None) != (p_inf_Pa is None):
        raise ValueError(
            "T_inf_K and p_inf_Pa must be provided together or both omitted"
        )
    if T_inf_K is None:
        return None, None
    return (
        _finite_float("T_inf_K", T_inf_K, positive=True),
        _finite_float("p_inf_Pa", p_inf_Pa, positive=True),
    )


def candidate_generator_command(
    *,
    mach: float,
    alpha_deg: float,
    geometric_altitude_m: float,
    run_dir: Path,
    T_inf_K: float | None = None,
    p_inf_Pa: float | None = None,
) -> list[str]:
    T_inf_value, p_inf_value = _validate_explicit_freestream_pair(
        T_inf_K=T_inf_K,
        p_inf_Pa=p_inf_Pa,
    )
    mach_value = _finite_float("mach", mach, positive=True)
    alpha_value = _finite_float("alpha_deg", alpha_deg)
    altitude_value = _finite_float(
        "geometric_altitude_m", geometric_altitude_m, positive=True
    )
    command = [
        sys.executable, str(RUNNER), "--vehicle", str(VEHICLE), "--case", str(CASE),
        "--sampling", str(SAMPLING), "--run_dir", str(run_dir), "--mach", str(mach_value),
        "--alpha", str(alpha_value), "--h_m", str(altitude_value),
    ]
    if T_inf_value is not None and p_inf_value is not None:
        command.extend(
            ["--T_inf_K", str(T_inf_value), "--p_inf_Pa", str(p_inf_value)]
        )
    command.extend(["--transition_weighting", "step", "--no_plots"])
    return command


def _required_mapping(summary: dict[str, Any], key: str) -> dict[str, Any]:
    value = summary.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"summary.json missing required object: {key}")
    return value


def _required_values(mapping: dict[str, Any], *, scope: str, keys: Sequence[str]) -> None:
    missing = [key for key in keys if key not in mapping or mapping[key] is None]
    if missing:
        raise ValueError(f"{scope} missing required values: {', '.join(missing)}")


def _require_requested_summary_value(
    *,
    name: str,
    actual: Any,
    expected: float,
) -> float:
    actual_value = _finite_float(name, actual, positive=True)
    if Decimal(str(actual_value)) != Decimal(str(expected)):
        raise ValueError(
            f"{name} does not match requested explicit freestream value: "
            f"actual={actual_value!r} expected={expected!r}"
        )
    return actual_value


def _validate_candidate_freestream_provenance(
    *,
    summary: dict[str, Any],
    freestream: dict[str, Any],
    T_inf_K: float | None,
    p_inf_Pa: float | None,
) -> bool:
    T_inf_value, p_inf_value = _validate_explicit_freestream_pair(
        T_inf_K=T_inf_K,
        p_inf_Pa=p_inf_Pa,
    )
    inputs = summary.get("inputs")
    recorded_overrides = (
        isinstance(inputs, dict)
        and (
            inputs.get("T_inf_K_override") is not None
            or inputs.get("p_inf_Pa_override") is not None
        )
    )
    explicit_summary = (
        freestream.get("freestream_source") == "explicit_override"
        or recorded_overrides
    )

    if T_inf_value is None or p_inf_value is None:
        if explicit_summary:
            raise ValueError(
                "explicit freestream run requires explicit T_inf_K and p_inf_Pa "
                "provenance inputs"
            )
        return False

    inputs = _required_mapping(summary, "inputs")
    _required_values(
        inputs,
        scope="summary.inputs",
        keys=("T_inf_K_override", "p_inf_Pa_override"),
    )
    if freestream.get("freestream_source") != "explicit_override":
        raise ValueError(
            "summary.freestream.freestream_source must be explicit_override "
            "when explicit freestream provenance inputs are provided"
        )
    _require_requested_summary_value(
        name="summary.inputs.T_inf_K_override",
        actual=inputs["T_inf_K_override"],
        expected=T_inf_value,
    )
    _require_requested_summary_value(
        name="summary.inputs.p_inf_Pa_override",
        actual=inputs["p_inf_Pa_override"],
        expected=p_inf_value,
    )
    _require_requested_summary_value(
        name="summary.freestream.T_inf_K",
        actual=freestream.get("T_inf_K"),
        expected=T_inf_value,
    )
    _require_requested_summary_value(
        name="summary.freestream.p_inf_Pa",
        actual=freestream.get("p_inf_Pa"),
        expected=p_inf_value,
    )
    return True


def build_candidate_manifest(
    *,
    case_id: str,
    mach: float,
    alpha_deg: float,
    geometric_altitude_m: float,
    run_dir: Path,
    generator_command: Sequence[str],
    T_inf_K: float | None = None,
    p_inf_Pa: float | None = None,
) -> dict[str, Any]:
    T_inf_value, p_inf_value = _validate_explicit_freestream_pair(
        T_inf_K=T_inf_K,
        p_inf_Pa=p_inf_Pa,
    )
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("case_id must be a non-empty string")
    mach_value = _finite_float("mach", mach, positive=True)
    alpha_value = _finite_float("alpha_deg", alpha_deg)
    altitude_value = _finite_float(
        "geometric_altitude_m", geometric_altitude_m, positive=True
    )
    if isinstance(generator_command, (str, bytes)) or not generator_command:
        raise ValueError("generator_command must be a non-empty sequence of strings")
    if any(not isinstance(item, str) for item in generator_command):
        raise ValueError("generator_command must contain only strings")

    candidate_dir = Path(run_dir)
    if not candidate_dir.is_dir():
        raise FileNotFoundError(f"candidate run directory does not exist: {candidate_dir}")
    fields_path = candidate_dir / "fields.npz"
    summary_path = candidate_dir / "summary.json"
    if not fields_path.is_file():
        raise FileNotFoundError(f"candidate artifact missing: {fields_path}")
    if not summary_path.is_file():
        raise FileNotFoundError(f"candidate artifact missing: {summary_path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError("summary.json must contain a JSON object")
    freestream = _required_mapping(summary, "freestream")
    faceted3d = _required_mapping(summary, "faceted3d")
    _required_values(
        freestream,
        scope="summary.freestream",
        keys=(
            "T_inf_K", "p_inf_Pa", "rho_inf_kg_m3", "freestream_source",
            "atmosphere_model",
        ),
    )
    _required_values(
        summary,
        scope="summary",
        keys=("actual_cp_model", "actual_cp_newtonian_A", "actual_cp_newtonian_n"),
    )
    _required_values(faceted3d, scope="summary.faceted3d", keys=("chord_min_m",))
    explicit_freestream_override = _validate_candidate_freestream_provenance(
        summary=summary,
        freestream=freestream,
        T_inf_K=T_inf_value,
        p_inf_Pa=p_inf_value,
    )
    if explicit_freestream_override:
        _finite_float(
            "summary.freestream.rho_inf_kg_m3",
            freestream["rho_inf_kg_m3"],
            positive=True,
        )

    expected_generator_command = candidate_generator_command(
        mach=mach_value,
        alpha_deg=alpha_value,
        geometric_altitude_m=altitude_value,
        run_dir=candidate_dir,
        T_inf_K=T_inf_value,
        p_inf_Pa=p_inf_value,
    )
    if (
        explicit_freestream_override
        and list(generator_command) != expected_generator_command
    ):
        raise ValueError(
            "generator_command must match the complete candidate runner command "
            "for the supplied provenance inputs"
        )

    required_fields = {"yb_grid", "span_w_m", "x_w_m", "mask_w", "xc_grid"}
    with np.load(fields_path, allow_pickle=False) as fields:
        missing_fields = sorted(required_fields - set(fields.files))
        if missing_fields:
            raise ValueError(
                f"fields.npz missing required arrays: {', '.join(missing_fields)}"
            )
        schema = {
            key: {"shape": list(fields[key].shape), "dtype": str(fields[key].dtype)}
            for key in sorted(fields.files)
        }
        mask_w = np.asarray(fields["mask_w"]).astype(bool)
        endpoint = endpoint_from_fields(fields)

    canonical_source = build_canonical_source_identity(ROOT)
    return {
        "manifest_schema": CANDIDATE_MANIFEST_SCHEMA,
        "provenance": CANDIDATE_PROVENANCE,
        "suite_type": "TPG candidate",
        "admission_status": "unregistered_candidate",
        "case_id": case_id,
        "case": {
            "mach": mach_value,
            "alpha_deg": alpha_value,
            "geometric_altitude_m": altitude_value,
        },
        "freestream": {
            "actual_T_inf_K": freestream["T_inf_K"],
            "actual_p_inf_Pa": freestream["p_inf_Pa"],
            "actual_rho_inf_kg_m3": freestream["rho_inf_kg_m3"],
            "source": freestream["freestream_source"],
        },
        "atmosphere": {
            "model": freestream["atmosphere_model"],
            "altitude_semantics": "geometric altitude converted to geopotential altitude before 1976 layer evaluation",
            "explicit_freestream_override": explicit_freestream_override,
        },
        "thermo": {
            "model": "tpg",
            "Taw_recovery": "fixed fully turbulent Pr^(1/3)",
        },
        "pressure": {
            "model": summary["actual_cp_model"],
            "A": summary["actual_cp_newtonian_A"],
            "n": summary["actual_cp_newtonian_n"],
        },
        "grid": {
            "ny": NY,
            "nx": NX,
            "n_valid": int(np.count_nonzero(mask_w)),
            "chord_min_m": faceted3d["chord_min_m"],
        },
        "endpoint_metadata": endpoint,
        "local_incidence": LOCAL_INCIDENCE_METADATA,
        "fields_schema": schema,
        "source_identity": canonical_source["source_identity"],
        "source_hashes_sha256": canonical_source["source_hashes_sha256"],
        "artifact_hashes_sha256": {
            name: sha256(candidate_dir / name) for name in ("fields.npz", "summary.json")
        },
        "manifest_generator": CANDIDATE_MANIFEST_GENERATOR,
        "generator_cli_template": subprocess.list2cmdline(list(generator_command)),
    }


def _validate_candidate_run_dir(
    run_dir: Path,
    *,
    allowed_runs_root: Path,
) -> Path:
    runs_root = Path(allowed_runs_root).resolve(strict=True)
    candidate_dir = Path(run_dir).resolve(strict=True)
    if not candidate_dir.is_dir():
        raise ValueError(f"candidate run path is not a directory: {candidate_dir}")
    try:
        candidate_dir.relative_to(runs_root)
    except ValueError as exc:
        raise ValueError(f"candidate run directory must be inside {runs_root}") from exc

    for forbidden_name in ("current_baseline_snapshot", "leeward_source_evidence"):
        forbidden_root = (runs_root / forbidden_name).resolve(strict=False)
        try:
            candidate_dir.relative_to(forbidden_root)
        except ValueError:
            continue
        raise ValueError(f"candidate run directory is inside forbidden area: {forbidden_root}")

    if "candidate" not in candidate_dir.name.casefold():
        raise ValueError("candidate run directory name must contain 'candidate'")
    for artifact_name in ("fields.npz", "summary.json"):
        artifact = candidate_dir / artifact_name
        if not artifact.is_file():
            raise FileNotFoundError(f"candidate artifact missing: {artifact}")
        resolved_artifact = artifact.resolve(strict=True)
        try:
            resolved_artifact.relative_to(candidate_dir)
        except ValueError as exc:
            raise ValueError(f"candidate artifact escapes run directory: {artifact}") from exc
    return candidate_dir


def _write_candidate_manifest_atomically(
    run_dir: Path,
    manifest: dict[str, Any],
) -> Path:
    target = run_dir / "manifest.json"
    if target.exists():
        raise FileExistsError(f"candidate manifest already exists: {target}")

    temporary_path: Path | None = None
    published = False
    try:
        with tempfile.NamedTemporaryFile(
            mode="x",
            encoding="utf-8",
            dir=run_dir,
            prefix=".candidate-manifest-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(manifest, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        if json.loads(temporary_path.read_text(encoding="utf-8")) != manifest:
            raise RuntimeError("candidate manifest temporary-file verification failed")
        if target.exists():
            raise FileExistsError(f"candidate manifest appeared during write: {target}")
        os.link(temporary_path, target)
        published = True
        temporary_path.unlink()
        return target
    except Exception:
        if published:
            target.unlink(missing_ok=True)
        raise
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def validate_source_migration_preflight(
    repo_root: Path = ROOT,
    *,
    fixed_paths: Sequence[str] = FIXED_PRODUCTION_PATHS,
    expected_count: int = EXPECTED_PRODUCTION_SOURCE_COUNT,
) -> str:
    head = resolve_head_commit(repo_root)
    branch = _run_git_bytes(
        repo_root,
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        stage="migration-branch",
    ).strip()
    if not branch:
        raise SourceIdentityError(
            "MIGRATION_PREFLIGHT_FAILED path=<repository> stage=detached-head"
        )

    unmerged = _run_git_bytes(
        repo_root,
        ["diff", "--name-only", "--diff-filter=U", "-z"],
        stage="migration-unmerged",
    )
    if unmerged:
        raise SourceIdentityError(
            "MIGRATION_PREFLIGHT_FAILED path=<repository> stage=unmerged"
        )
    staged = _run_git_bytes(
        repo_root,
        ["diff", "--cached", "--name-status", "-z", "HEAD"],
        stage="migration-staged",
    )
    unstaged = _run_git_bytes(
        repo_root,
        ["diff", "--name-status", "-z"],
        stage="migration-unstaged",
    )
    if staged or unstaged:
        raise SourceIdentityError(
            "MIGRATION_PREFLIGHT_FAILED path=<repository> stage=tracked-dirty"
        )

    validate_production_source_clean(
        repo_root,
        fixed_paths=fixed_paths,
        expected_count=expected_count,
    )
    operation_names = (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG",
        "rebase-merge",
        "rebase-apply",
        "sequencer",
    )
    for name in operation_names:
        raw_path = _run_git_bytes(
            repo_root,
            ["rev-parse", "--git-path", name],
            stage="migration-git-operation",
        ).strip()
        operation_path = Path(raw_path.decode("utf-8"))
        if not operation_path.is_absolute():
            operation_path = repo_root / operation_path
        if operation_path.exists():
            raise SourceIdentityError(
                "MIGRATION_PREFLIGHT_FAILED "
                f"path=<repository> stage=git-operation operation={name}"
            )

    worktrees = _run_git_bytes(
        repo_root,
        ["worktree", "list", "--porcelain", "-z"],
        stage="migration-worktrees",
    )
    worktree_count = sum(
        1 for token in worktrees.split(b"\0") if token.startswith(b"worktree ")
    )
    if worktree_count != 1:
        raise SourceIdentityError(
            "MIGRATION_PREFLIGHT_FAILED path=<repository> stage=additional-worktree "
            f"count={worktree_count}"
        )
    return head


def _manifest_with_source_identity(
    manifest: dict[str, Any],
    canonical_source: dict[str, Any],
) -> dict[str, Any]:
    updated: dict[str, Any] = {}
    inserted = False
    for key, value in manifest.items():
        if key in SOURCE_IDENTITY_MUTABLE_FIELDS:
            if not inserted:
                updated["source_identity"] = canonical_source["source_identity"]
                updated["source_hashes_sha256"] = canonical_source["source_hashes_sha256"]
                inserted = True
            continue
        updated[key] = value
    if not inserted:
        updated["source_identity"] = canonical_source["source_identity"]
        updated["source_hashes_sha256"] = canonical_source["source_hashes_sha256"]
    return updated


def _validate_source_only_change(
    original: dict[str, Any],
    updated: dict[str, Any],
) -> None:
    original_stable = {
        key: value
        for key, value in original.items()
        if key not in SOURCE_IDENTITY_MUTABLE_FIELDS
    }
    updated_stable = {
        key: value
        for key, value in updated.items()
        if key not in SOURCE_IDENTITY_MUTABLE_FIELDS
    }
    if original_stable != updated_stable:
        raise SourceIdentityError(
            "MIGRATION_FIELD_SCOPE_VIOLATION path=<manifest> stage=source-only-diff"
        )


def _serialize_manifest(manifest: dict[str, Any]) -> bytes:
    return (
        json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _prepare_fsynced_file(path: Path, payload: bytes, *, require_json: bool) -> Path:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="xb",
            dir=path.parent,
            prefix=f".{path.name}.source-identity-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary_path.read_bytes() != payload:
            raise SourceIdentityError(
                f"MIGRATION_TEMP_VERIFY_FAILED path={path} stage=byte-roundtrip"
            )
        if require_json:
            parsed = json.loads(payload.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise SourceIdentityError(
                    f"MIGRATION_TEMP_VERIFY_FAILED path={path} stage=json-object"
                )
        return temporary_path
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def migrate_source_identity(
    manifest_paths: Sequence[Path],
    *,
    repo_root: Path = ROOT,
    fixed_paths: Sequence[str] = FIXED_PRODUCTION_PATHS,
    expected_count: int = EXPECTED_PRODUCTION_SOURCE_COUNT,
) -> dict[str, Any]:
    paths = tuple(Path(path) for path in manifest_paths)
    resolved_paths = tuple(path.resolve(strict=False) for path in paths)
    if len(paths) != 2 or len(set(resolved_paths)) != 2:
        raise SourceIdentityError(
            "MIGRATION_MANIFEST_SET_INVALID path=<manifests> stage=manifest-count"
        )
    validate_source_migration_preflight(
        repo_root,
        fixed_paths=fixed_paths,
        expected_count=expected_count,
    )

    original_bytes: dict[Path, bytes] = {}
    originals: dict[Path, dict[str, Any]] = {}
    for path in paths:
        try:
            raw = path.read_bytes()
            manifest = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceIdentityError(
                f"MIGRATION_MANIFEST_INVALID path={path} stage=read-original"
            ) from exc
        if not isinstance(manifest, dict) or manifest.get("manifest_schema") != MANIFEST_SCHEMA:
            raise SourceIdentityError(
                f"MIGRATION_MANIFEST_INVALID path={path} stage=manifest-schema"
            )
        source_map = manifest.get("source_hashes_sha256")
        if not isinstance(source_map, dict) or not source_map:
            raise SourceIdentityError(
                f"MIGRATION_MANIFEST_INVALID path={path} stage=legacy-source-map"
            )
        original_bytes[path] = raw
        originals[path] = manifest
    first_map = originals[paths[0]]["source_hashes_sha256"]
    if originals[paths[1]]["source_hashes_sha256"] != first_map:
        raise SourceIdentityError(
            "LEGACY_SOURCE_MAP_MISMATCH path=<manifests> stage=precompute"
        )

    canonical_source = build_canonical_source_identity(
        repo_root,
        fixed_paths=fixed_paths,
        expected_count=expected_count,
    )
    updated = {
        path: _manifest_with_source_identity(originals[path], canonical_source)
        for path in paths
    }
    for path in paths:
        _validate_source_only_change(originals[path], updated[path])
        validate_source_identity_schema(
            updated[path],
            expected_count=expected_count,
            fixed_paths=fixed_paths,
        )

    prepared: dict[Path, Path] = {}
    try:
        for path in paths:
            prepared[path] = _prepare_fsynced_file(
                path,
                _serialize_manifest(updated[path]),
                require_json=True,
            )
        for path in paths:
            os.replace(prepared[path], path)
            prepared.pop(path, None)

        for path in paths:
            persisted = json.loads(path.read_text(encoding="utf-8"))
            _validate_source_only_change(originals[path], persisted)
            validate_source_identity_schema(
                persisted,
                expected_count=expected_count,
                fixed_paths=fixed_paths,
            )
            if persisted != updated[path]:
                raise SourceIdentityError(
                    f"MIGRATION_POST_VALIDATION_FAILED path={path} stage=content-mismatch"
                )
        return canonical_source
    except Exception as exc:
        rollback_errors: list[str] = []
        for path in paths:
            rollback_temp: Path | None = None
            try:
                rollback_temp = _prepare_fsynced_file(
                    path,
                    original_bytes[path],
                    require_json=False,
                )
                os.replace(rollback_temp, path)
                rollback_temp = None
                if path.read_bytes() != original_bytes[path]:
                    raise OSError("restored bytes do not match original")
            except Exception as rollback_exc:
                rollback_errors.append(f"{path}: {rollback_exc}")
            finally:
                if rollback_temp is not None:
                    rollback_temp.unlink(missing_ok=True)
        if rollback_errors:
            raise SourceIdentityError(
                "MIGRATION_ROLLBACK_FAILED " + " | ".join(rollback_errors)
            ) from exc
        raise
    finally:
        for temporary_path in prepared.values():
            temporary_path.unlink(missing_ok=True)


def _build_current_manifest(
    case_id: str,
    run_dir: Path,
    command: list[str],
    *,
    exact_observation_freestream: bool,
) -> dict[str, Any]:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    expected_command = (
        formal_command(case_id, run_dir)
        if exact_observation_freestream
        else baseline_replay_command(case_id, run_dir)
    )
    if command != expected_command:
        role = "formal" if exact_observation_freestream else "baseline replay"
        raise ValueError(f"{role} generator command does not match its input contract")
    if exact_observation_freestream:
        binding = _formal_observation_binding(case_id)
        validate_exact_freestream_summary(binding, summary)

    with np.load(run_dir / "fields.npz", allow_pickle=False) as fields:
        schema = {key: {"shape": list(fields[key].shape), "dtype": str(fields[key].dtype)} for key in sorted(fields.files)}
        mask_w = np.asarray(fields["mask_w"]).astype(bool)
        endpoint = endpoint_from_fields(fields)
    freestream = summary.get("freestream", {})
    faceted3d = summary.get("faceted3d", {})
    mach, alpha, altitude = CASES[case_id]
    canonical_source = build_canonical_source_identity(ROOT)
    atmosphere = (
        {
            "model": "none / unverified",
            "altitude_semantics": "nominal historical label; no atmosphere qualification inferred",
            "explicit_freestream_override": True,
        }
        if exact_observation_freestream
        else {
            "model": freestream.get("atmosphere_model"),
            "altitude_semantics": "geometric altitude converted to geopotential altitude before 1976 layer evaluation",
            "explicit_freestream_override": False,
        }
    )
    command_template = (
        formal_command(case_id, Path("<run_dir>"))
        if exact_observation_freestream
        else baseline_replay_command(case_id, Path("<run_dir>"))
    )
    return {
        "manifest_schema": "current-tpg-baseline-regression/v5",
        "provenance": "CURRENT TPG-only post-2026-07-14 official regression baseline with local-incidence and sheet-specific leeward freestream-recovery diagnostics; historical 0630 snapshot is a separate contract",
        "baseline_date": DATE,
        "suite_type": "TPG official",
        "case_id": case_id,
        "case": {"mach": mach, "alpha_deg": alpha, "geometric_altitude_m": altitude},
        "freestream": {
            "actual_T_inf_K": freestream.get("T_inf_K"),
            "actual_p_inf_Pa": freestream.get("p_inf_Pa"),
            "actual_rho_inf_kg_m3": freestream.get("rho_inf_kg_m3"),
            "source": freestream.get("freestream_source"),
        },
        "atmosphere": atmosphere,
        "thermo": {
            "model": "tpg",
            "Taw_recovery": "fixed fully turbulent Pr^(1/3)",
        },
        "pressure": {
            "model": summary.get("actual_cp_model"),
            "A": summary.get("actual_cp_newtonian_A"),
            "n": summary.get("actual_cp_newtonian_n"),
        },
        "grid": {
            "ny": NY, "nx": NX,
            "n_valid": int(np.count_nonzero(mask_w)),
            "chord_min_m": faceted3d.get("chord_min_m"),
        },
        "endpoint_metadata": endpoint,
        "local_incidence": LOCAL_INCIDENCE_METADATA,
        "fields_schema": schema,
        "source_identity": canonical_source["source_identity"],
        "source_hashes_sha256": canonical_source["source_hashes_sha256"],
        "artifact_hashes_sha256": {name: sha256(run_dir / name) for name in ("fields.npz", "summary.json")},
        "baseline_generator": "scripts/tools/current_baseline_regression_check.py --freeze",
        "generator_cli_template": subprocess.list2cmdline(command_template),
    }


def build_manifest(case_id: str, run_dir: Path, command: list[str]) -> dict[str, Any]:
    return _build_current_manifest(
        case_id,
        run_dir,
        command,
        exact_observation_freestream=True,
    )


def build_baseline_replay_manifest(
    case_id: str,
    run_dir: Path,
    command: list[str],
) -> dict[str, Any]:
    return _build_current_manifest(
        case_id,
        run_dir,
        command,
        exact_observation_freestream=False,
    )


def _pre_freeze_gate(case_id: str, candidate_dir: Path) -> tuple[bool, dict[str, Any]]:
    baseline_dir = SNAPSHOT / "tpg" / case_id
    baseline_manifest = json.loads((baseline_dir / "manifest.json").read_text(encoding="utf-8"))
    candidate_summary = json.loads((candidate_dir / "summary.json").read_text(encoding="utf-8"))
    candidate_manifest = build_manifest(case_id, candidate_dir, formal_command(case_id, candidate_dir))
    old_contract_fields = set().union(*(set(fields) for name, fields in GROUPS.items() if not name.startswith("Group 8"))) | ADDITIONAL_FIELDS
    group8_fields = set(next(fields for name, fields in GROUPS.items() if name.startswith("Group 8")))
    expected_fields = old_contract_fields | group8_fields
    rows: list[tuple[str, bool, str]] = []
    with np.load(baseline_dir / "fields.npz", allow_pickle=False) as baseline, np.load(candidate_dir / "fields.npz", allow_pickle=False) as candidate:
        baseline_fields, candidate_fields = set(baseline.files), set(candidate.files)
        rows.append(("baseline.v4_field_count", len(baseline_fields) == 54, f"actual={len(baseline_fields)}"))
        rows.append(("candidate.v5_field_count", len(candidate_fields) == EXPECTED_FIELD_COUNT, f"actual={len(candidate_fields)}"))
        rows.append(("old_fields.present", baseline_fields == old_contract_fields and baseline_fields <= candidate_fields,
                     f"baseline={len(baseline_fields)} old_contract={len(old_contract_fields)}"))
        rows.append(("new_fields.exact", candidate_fields - baseline_fields == group8_fields,
                     f"new={sorted(candidate_fields - baseline_fields)}"))
        rows.append(("unexpected_fields.zero", candidate_fields == expected_fields,
                     f"unexpected={sorted(candidate_fields - expected_fields)} missing={sorted(expected_fields - candidate_fields)}"))
        for field in sorted(baseline_fields):
            ok, detail, _ = compare_array(np.asarray(baseline[field]), np.asarray(candidate[field]))
            rows.append((f"old.{field}", ok, detail))
        semantic_rows, metrics = _group8_semantic_quality(candidate, candidate_manifest, candidate_summary)
        rows.extend((f"semantic.{name}", ok, detail) for name, ok, detail in semantic_rows)
    ok = all(row[1] for row in rows)
    max_old_diff = 0.0 if all(row[1] for row in rows if row[0].startswith("old.")) else None
    print(f"[tpg/{case_id}] PRE-FREEZE {'PASS' if ok else 'FAIL'} old_fields=54 new_fields=18 total=72 max_abs_diff={max_old_diff}")
    print(f"  command={subprocess.list2cmdline(formal_command(case_id, candidate_dir))}")
    print("  exit_code=0")
    for name, row_ok, detail in rows:
        if not row_ok:
            print(f"  {name}: FAIL {detail}")
    print(f"  Group 8 metrics={metrics}")
    return ok, {"manifest": candidate_manifest, "metrics": metrics}


def freeze_all() -> bool:
    validate_production_source_clean(ROOT)
    candidates: dict[str, Path] = {}
    gate_data: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="baseline_v5_prefreeze_") as temp:
        work = Path(temp)
        for case_id in CASES:
            candidate_dir = work / case_id
            command = run_formal(case_id, candidate_dir)
            print(f"[tpg/{case_id}] official CLI completed: {subprocess.list2cmdline(command)} exit_code=0")
            candidates[case_id] = candidate_dir
            gate_ok, data = _pre_freeze_gate(case_id, candidate_dir)
            if not gate_ok:
                print("BASELINE PROMOTION: BLOCKED")
                return False
            gate_data[case_id] = data

        backups = work / "v4_backups"
        backups.mkdir()
        promoted: list[str] = []
        try:
            for case_id, candidate_dir in candidates.items():
                destination = SNAPSHOT / "tpg" / case_id
                backup = backups / case_id
                backup.mkdir()
                shutil.copy2(destination / "fields.npz", backup / "fields.npz")
                shutil.copy2(destination / "manifest.json", backup / "manifest.json")
                summary_hash = sha256(destination / "summary.json")
                manifest = gate_data[case_id]["manifest"]
                manifest["artifact_hashes_sha256"]["summary.json"] = summary_hash
                staged_fields = destination / "fields.npz.v5-staging"
                staged_manifest = destination / "manifest.json.v5-staging"
                shutil.copy2(candidate_dir / "fields.npz", staged_fields)
                staged_manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                staged_fields.replace(destination / "fields.npz")
                staged_manifest.replace(destination / "manifest.json")
                promoted.append(case_id)
            print("BASELINE PROMOTION: PASS official CLI candidates promoted; summaries unchanged")
            return True
        except Exception:
            for case_id in promoted:
                destination = SNAPSHOT / "tpg" / case_id
                backup = backups / case_id
                shutil.copy2(backup / "fields.npz", destination / "fields.npz")
                shutil.copy2(backup / "manifest.json", destination / "manifest.json")
            raise


def freeze_case(case_id: str) -> None:
    validate_production_source_clean(ROOT)
    destination = SNAPSHOT / "tpg" / case_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"baseline_freeze_tpg_{case_id}_") as temp:
        work = Path(temp)
        command = run_formal(case_id, work)
        manifest = build_manifest(case_id, work, command)
        staging = destination.parent / f"{destination.name}.staging"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        for name, source in FORMAL_INPUTS.items():
            shutil.copy2(source, staging / name)
        for name in ("fields.npz", "summary.json"):
            shutil.copy2(work / name, staging / name)
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        shutil.rmtree(destination, ignore_errors=True)
        staging.replace(destination)
    print(f"[tpg/{case_id}] snapshot frozen: {destination}")


def compare_array(baseline: np.ndarray, current: np.ndarray) -> tuple[bool, str, float | None]:
    if baseline.shape != current.shape:
        return False, f"shape baseline={baseline.shape} current={current.shape}", None
    if baseline.dtype != current.dtype:
        return False, f"dtype baseline={baseline.dtype} current={current.dtype}", None
    if baseline.dtype.kind in "bui" or current.dtype.kind in "bui":
        ok = np.array_equal(baseline, current) and baseline.tobytes(order="C") == current.tobytes(order="C")
        return ok, "exact C-order bytes" if ok else "exact value/C-order byte mismatch", 0.0 if ok else None
    if baseline.dtype.kind not in "fc" or current.dtype.kind not in "fc":
        ok = np.array_equal(baseline, current) and baseline.tobytes(order="C") == current.tobytes(order="C")
        return ok, "exact C-order bytes" if ok else "non-numeric value/C-order byte mismatch", 0.0 if ok else None
    if not np.array_equal(np.isnan(baseline), np.isnan(current)):
        return False, "NaN mask mismatch", None
    if not np.array_equal(np.isinf(baseline), np.isinf(current)):
        return False, "Inf mask mismatch", None
    finite = np.isfinite(baseline) & np.isfinite(current)
    diff = float(np.max(np.abs(baseline[finite].astype(float) - current[finite].astype(float)))) if np.any(finite) else 0.0
    bytes_ok = baseline.tobytes(order="C") == current.tobytes(order="C")
    ok = diff == 0.0 and bytes_ok
    return ok, f"max_abs_diff={diff:.3e} C-order-bytes={'exact' if bytes_ok else 'mismatch'}", diff


def _group8_semantic_quality(fields: Any, manifest: dict[str, Any], summary: dict[str, Any]) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    rows: list[tuple[str, bool, str]] = []
    metrics: dict[str, Any] = {}
    freestream = manifest["freestream"]
    gas_contract = summary["case"]
    T_inf = float(freestream["actual_T_inf_K"])
    p_inf = float(freestream["actual_p_inf_Pa"])
    rho_inf = float(freestream["actual_rho_inf_kg_m3"])
    mach = float(manifest["case"]["mach"])
    V_inf = float(summary["freestream"]["V_inf_m_s"])
    tpg = make_fluent_tpg_thermo(R=float(gas_contract["R_J_per_kgK"]))
    h_inf = float(tpg.h_from_T(T_inf))
    mu_inf = float(mu_sutherland(T_inf))
    h_aw = h_inf + float(gas_contract["pr"]) ** (1.0 / 3.0) * V_inf**2 / 2.0
    expected_taw = float(tpg.T_from_h(h_aw))
    expected = {
        "T_e": T_inf, "p_e": p_inf, "rho_e": rho_inf, "V_e": V_inf,
        "Ma_e": mach, "h_e": h_inf, "mu_e": mu_inf, "Taw_tpg": expected_taw,
    }

    for sheet, expected_true in (("upper", 256), ("lower", 0)):
        mask_name = GROUP8_MASK_FIELDS[sheet]
        mask = np.asarray(fields[mask_name])
        class_mask = np.asarray(fields[f"surface_class_{sheet}"]) == SURFACE_CLASS_LEEWARD
        true_count = int(np.count_nonzero(mask))
        false_count = int(mask.size - true_count)
        metrics[f"{sheet}_true"] = true_count
        metrics[f"{sheet}_false"] = false_count
        rows.append((f"{sheet}.mask_contract", mask.dtype == np.dtype(bool) and mask.shape == FIELD_SHAPE,
                     f"dtype={mask.dtype} shape={mask.shape}"))
        rows.append((f"{sheet}.mask_vs_surface_class", np.array_equal(mask, class_mask),
                     "raw local-incidence classification"))
        rows.append((f"{sheet}.mask_count", true_count == expected_true and false_count == FIELD_SHAPE[0] - expected_true,
                     f"true={true_count} false={false_count}"))
        for field in GROUP8_FLOAT_FIELDS[sheet]:
            values = np.asarray(fields[field])
            finite_ok = np.array_equal(np.isfinite(values), mask)
            nan_ok = np.array_equal(np.isnan(values), ~mask)
            rows.append((f"{field}.domain", values.dtype == np.dtype(np.float64) and values.shape == FIELD_SHAPE and finite_ok and nan_ok,
                         f"dtype={values.dtype} shape={values.shape} finite_mask={finite_ok} NaN_mask={nan_ok}"))
        for stem, expected_value in expected.items():
            actual = np.asarray(fields[f"{stem}_leeward_{sheet}"])[mask]
            target = np.full(true_count, expected_value, dtype=np.float64)
            rows.append((f"{sheet}.{stem}.independent", np.array_equal(actual, target),
                         f"points={true_count} expected={expected_value:.17g}"))

    upper_taw = np.asarray(fields["Taw_tpg_leeward_upper"])[np.asarray(fields["mask_leeward_upper"])]
    metrics["upper_taw_min"] = float(np.min(upper_taw)) if upper_taw.size else None
    metrics["upper_taw_max"] = float(np.max(upper_taw)) if upper_taw.size else None
    metrics["lower_taw_nan"] = int(np.count_nonzero(np.isnan(fields["Taw_tpg_leeward_lower"])))
    rows.append(("upper.nonempty_coverage", upper_taw.size > 0, f"points={upper_taw.size}"))
    rows.append(("lower.empty_sheet_isolation", metrics["lower_taw_nan"] == FIELD_SHAPE[0],
                 f"NaN={metrics['lower_taw_nan']}; nonempty lower isolation is covered by synthetic provider tests"))
    return rows, metrics


def compare_metadata(baseline: dict[str, Any], current: dict[str, Any]) -> list[tuple[str, bool, str]]:
    rows = []
    for field in METADATA_FIELDS:
        b_value, c_value = baseline.get(field), current.get(field)
        ok = b_value == c_value
        rows.append((field, ok, "exact" if ok else f"baseline={b_value!r} current={c_value!r}"))
    expected = {
        "n_valid": 3321,
        "ny": NY,
        "nx": NX,
        "row_valid_count": NX,
        "row_compared": True,
    }
    checks = {
        "grid.n_valid": nested(current, "grid", "n_valid"),
        "grid.ny": nested(current, "grid", "ny"),
        "grid.nx": nested(current, "grid", "nx"),
        "endpoint.row_valid_count": nested(current, "endpoint_metadata", "row_valid_count"),
        "endpoint.row_compared": nested(current, "endpoint_metadata", "row_compared"),
    }
    for (name, value), expected_value in zip(checks.items(), expected.values()):
        rows.append((name, value == expected_value, f"actual={value!r} expected={expected_value!r}"))
    rows.append(
        (
            "atmosphere.no_override",
            nested(current, "atmosphere", "explicit_freestream_override") is False,
            "must be false for historical baseline replay",
        )
    )
    return rows


def _check_local_incidence_quality(fields: Any) -> list[tuple[str, bool, str]]:
    """Extra quality checks on local-incidence diagnostic fields."""
    results: list[tuple[str, bool, str]] = []

    # Check each sheet
    for sheet, expected_nz_sign in (("upper", 1.0), ("lower", -1.0)):
        nx = np.asarray(fields[f"normal_x_{sheet}"], dtype=float)
        ny = np.asarray(fields[f"normal_y_{sheet}"], dtype=float)
        nz = np.asarray(fields[f"normal_z_{sheet}"], dtype=float)
        finite = np.isfinite(nx) & np.isfinite(ny) & np.isfinite(nz)

        # Unit length check
        norm = np.sqrt(nx[finite] ** 2 + ny[finite] ** 2 + nz[finite] ** 2)
        norm_ok = bool(np.any(finite)) and bool(np.max(np.abs(norm - 1.0)) <= 1e-12)
        results.append((f"{sheet}.normal_unit_length", norm_ok,
                       f"valid={int(np.count_nonzero(finite))} max_dev={float(np.max(np.abs(norm-1.0))) if np.any(finite) else 'N/A'}"))

        # n_z orientation check
        orientation_ok = bool(np.any(finite)) and bool(np.all(nz[finite] * expected_nz_sign > 0.0))
        results.append((f"{sheet}.nz_orientation", orientation_ok,
                       f"expected_sign={expected_nz_sign:+} all_correct={orientation_ok}"))

        # surface_class vs s/epsilon consistency
        s = np.asarray(fields[f"incidence_s_{sheet}"], dtype=float)
        cls = np.asarray(fields[f"surface_class_{sheet}"], dtype=np.int8)
        s_valid = np.isfinite(s)

        # windward: s > epsilon
        windward_ok = np.all(s[s_valid & (cls == 1)] > LOCAL_INCIDENCE_EPSILON) if np.any(s_valid & (cls == 1)) else True
        # leeward: s < -epsilon
        leeward_ok = np.all(s[s_valid & (cls == -1)] < -LOCAL_INCIDENCE_EPSILON) if np.any(s_valid & (cls == -1)) else True
        # near-tangent: |s| <= epsilon
        nt_ok = np.all(np.abs(s[s_valid & (cls == 0)]) <= LOCAL_INCIDENCE_EPSILON) if np.any(s_valid & (cls == 0)) else True
        class_ok = windward_ok and leeward_ok and nt_ok
        results.append((f"{sheet}.surface_class_vs_s_consistency", class_ok,
                       f"windward_ok={windward_ok} leeward_ok={leeward_ok} near_tangent_ok={nt_ok}"))

        # source encoding validity
        source = np.asarray(fields[f"normal_source_{sheet}"], dtype=np.int8)
        source_valid = set(np.unique(source)).issubset({0, 1, 2, 3})
        results.append((f"{sheet}.normal_source_encoding", source_valid,
                       f"values={sorted(set(np.unique(source)))}"))

        # source=3 exists (analytic fallback is used for some points)
        source3_count = int(np.count_nonzero(source == 3))
        results.append((f"{sheet}.source3_analytic_fallback_exists", source3_count > 0,
                       f"source3_points={source3_count} (analytic fallback working as expected)"))

    return results


def compare_case(case_id: str) -> bool:
    baseline_dir = SNAPSHOT / "tpg" / case_id
    artifacts = [*FORMAL_INPUTS, "manifest.json"]
    missing_artifacts = [name for name in artifacts if not (baseline_dir / name).is_file()]
    if missing_artifacts:
        print(f"[tpg/{case_id}] FAIL mandatory baseline artifacts missing: {', '.join(missing_artifacts)}")
        return False
    baseline_manifest = json.loads((baseline_dir / "manifest.json").read_text(encoding="utf-8"))
    validate_current_source_contract(baseline_manifest, ROOT)
    artifact_hashes_ok, artifact_hash_errors = verify_artifact_hashes(case_id, baseline_dir, baseline_manifest)
    print(f"  Artifact hashes: {'PASS' if artifact_hashes_ok else 'FAIL'}")
    for error in artifact_hash_errors:
        print(f"    {error}")
    if not artifact_hashes_ok:
        print(f"[tpg/{case_id}] TPG OFFICIAL FAIL")
        return False
    with tempfile.TemporaryDirectory(prefix=f"baseline_compare_tpg_{case_id}_") as temp:
        current_dir = Path(temp)
        command = run_baseline_replay(case_id, current_dir)
        current_manifest = build_baseline_replay_manifest(
            case_id,
            current_dir,
            command,
        )
        groups = GROUPS
        overall = True
        all_contract_fields = set().union(*(set(fields) for fields in groups.values()))
        with np.load(baseline_dir / "fields.npz", allow_pickle=False) as baseline, np.load(current_dir / "fields.npz", allow_pickle=False) as current:
            baseline_fields = set(baseline.files)
            current_fields = set(current.files)
            expected_fields = all_contract_fields | ADDITIONAL_FIELDS
            field_schema_ok = (
                baseline_fields == current_fields == expected_fields
                and len(baseline_fields) == len(current_fields) == EXPECTED_FIELD_COUNT
            )
            overall = field_schema_ok and overall
            print(
                f"  Schema v5 field parity: {'PASS' if field_schema_ok else 'FAIL'} "
                f"baseline={len(baseline_fields)} current={len(current_fields)} "
                f"missing={sorted(expected_fields - current_fields)} unexpected={sorted(current_fields - expected_fields)}"
            )
            for group_name, fields in groups.items():
                rows = []
                max_diff = 0.0
                for field in fields:
                    if field not in baseline.files or field not in current.files:
                        rows.append((field, False, f"mandatory missing baseline={field in baseline.files} current={field in current.files}"))
                        continue
                    ok, detail, diff = compare_array(np.asarray(baseline[field]), np.asarray(current[field]))
                    rows.append((field, ok, detail))
                    if diff is not None:
                        max_diff = max(max_diff, diff)
                group_ok = all(row[1] for row in rows)
                overall = group_ok and overall
                print(f"  {group_name}: {'PASS' if group_ok else 'FAIL'} max_abs_diff={max_diff:.3e}")
                for field, ok, detail in rows:
                    print(f"    {field}: {'PASS' if ok else 'FAIL'} {detail}")

            # ── additional parity (registered fields are never treated as extras) ──
            extra_baseline = sorted(baseline_fields - all_contract_fields)
            extra_current = sorted(current_fields - all_contract_fields)
            extras_ok = set(extra_baseline) == set(extra_current) == ADDITIONAL_FIELDS
            overall = extras_ok and overall
            print(f"  Existing additional schema parity: {'PASS' if extras_ok else 'FAIL'} baseline={extra_baseline} current={extra_current}")

            semantic_rows, semantic_metrics = _group8_semantic_quality(current, current_manifest, json.loads((current_dir / "summary.json").read_text(encoding="utf-8")))
            semantic_ok = all(row[1] for row in semantic_rows)
            overall = semantic_ok and overall
            print(f"  Group 8 semantic QA: {'PASS' if semantic_ok else 'FAIL'} metrics={semantic_metrics}")
            for field, ok, detail in semantic_rows:
                print(f"    {field}: {'PASS' if ok else 'FAIL'} {detail}")

            # ── local-incidence quality checks ──
            li_quality = _check_local_incidence_quality(current)
            li_quality_ok = all(row[1] for row in li_quality)
            overall = li_quality_ok and overall
            print(f"  Local-incidence quality checks: {'PASS' if li_quality_ok else 'FAIL'}")
            for field, ok, detail in li_quality:
                print(f"    {field}: {'PASS' if ok else 'FAIL'} {detail}")

        schema_ok = baseline_manifest.get("manifest_schema") == current_manifest.get("manifest_schema") == "current-tpg-baseline-regression/v5"
        overall = schema_ok and overall
        print(f"  Manifest schema: {'PASS' if schema_ok else 'FAIL'} baseline={baseline_manifest.get('manifest_schema')} current={current_manifest.get('manifest_schema')}")

        metadata_rows = compare_metadata(baseline_manifest, current_manifest)
        metadata_ok = all(row[1] for row in metadata_rows)
        overall = metadata_ok and overall
        print(f"  Endpoint / manifest metadata: {'PASS' if metadata_ok else 'FAIL'}")
        for field, ok, detail in metadata_rows:
            print(f"    {field}: {'PASS' if ok else 'FAIL'} {detail}")

        # ── source hashes check ──
        current_hashes = current_manifest.get("source_hashes_sha256", {})
        expected_hashes = baseline_manifest.get("source_hashes_sha256", {})
        hash_ok = current_hashes == expected_hashes
        overall = hash_ok and overall
        print(f"  Source hashes: {'PASS' if hash_ok else 'FAIL'}")

    print(f"[tpg/{case_id}] TPG OFFICIAL {'PASS' if overall else 'FAIL'}")
    return overall


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--freeze", action="store_true", help="atomically generate or replace current TPG snapshots")
    mode.add_argument(
        "--candidate-manifest",
        action="store_true",
        help="write identity-only manifest.json for an existing unregistered candidate run",
    )
    mode.add_argument(
        "--migrate-source-identity",
        action="store_true",
        help=(
            "replace source identity fields in exactly two explicitly supplied v5 manifests; "
            "requires a clean committed HEAD"
        ),
    )
    parser.add_argument(
        "--manifest-path",
        action="append",
        type=Path,
        help="manifest path for --migrate-source-identity; provide exactly twice",
    )
    parser.add_argument("--case-id")
    parser.add_argument("--mach", type=float)
    parser.add_argument("--alpha", type=float)
    parser.add_argument("--h-m", type=float)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument(
        "--t-inf-k",
        type=float,
        help=(
            "explicit freestream static temperature (K) provenance; "
            "must be provided together with --p-inf-pa"
        ),
    )
    parser.add_argument(
        "--p-inf-pa",
        type=float,
        help=(
            "explicit freestream static pressure (Pa) provenance; "
            "must be provided together with --t-inf-k"
        ),
    )
    args = parser.parse_args()

    candidate_values = {
        "--case-id": args.case_id,
        "--mach": args.mach,
        "--alpha": args.alpha,
        "--h-m": args.h_m,
        "--run-dir": args.run_dir,
        "--t-inf-k": args.t_inf_k,
        "--p-inf-pa": args.p_inf_pa,
    }
    supplied_candidate_values = [
        name for name, value in candidate_values.items() if value is not None
    ]
    if args.migrate_source_identity:
        if supplied_candidate_values:
            parser.error(
                "candidate arguments are not allowed with --migrate-source-identity: "
                + ", ".join(supplied_candidate_values)
            )
        if len(args.manifest_path or ()) != 2:
            parser.error(
                "--migrate-source-identity requires exactly two --manifest-path values"
            )
        migrate_source_identity(args.manifest_path, repo_root=ROOT)
        print("source identity migration completed for two explicit manifests")
        return 0
    if args.manifest_path:
        parser.error("--manifest-path requires --migrate-source-identity")

    required_candidate_values = {
        name: value
        for name, value in candidate_values.items()
        if name in {"--case-id", "--mach", "--alpha", "--h-m", "--run-dir"}
    }
    if args.candidate_manifest:
        missing = [
            name for name, value in required_candidate_values.items() if value is None
        ]
        if missing:
            parser.error(
                "--candidate-manifest requires "
                + ", ".join(required_candidate_values)
            )
        if (args.t_inf_k is None) != (args.p_inf_pa is None):
            parser.error(
                "--t-inf-k and --p-inf-pa must be provided together or both omitted"
            )
        try:
            T_inf_value, p_inf_value = _validate_explicit_freestream_pair(
                T_inf_K=args.t_inf_k,
                p_inf_Pa=args.p_inf_pa,
            )
        except ValueError as exc:
            parser.error(str(exc))
        candidate_dir = _validate_candidate_run_dir(
            args.run_dir,
            allowed_runs_root=CANDIDATE_RUNS_ROOT,
        )
        command = candidate_generator_command(
            mach=args.mach,
            alpha_deg=args.alpha,
            geometric_altitude_m=args.h_m,
            run_dir=candidate_dir,
            T_inf_K=T_inf_value,
            p_inf_Pa=p_inf_value,
        )
        manifest = build_candidate_manifest(
            case_id=args.case_id,
            mach=args.mach,
            alpha_deg=args.alpha,
            geometric_altitude_m=args.h_m,
            run_dir=candidate_dir,
            generator_command=command,
            T_inf_K=T_inf_value,
            p_inf_Pa=p_inf_value,
        )
        target = _write_candidate_manifest_atomically(candidate_dir, manifest)
        print(f"candidate manifest written: {target}")
        return 0

    supplied_candidate_values = [
        name for name, value in candidate_values.items() if value is not None
    ]
    if supplied_candidate_values:
        parser.error(
            "candidate arguments require --candidate-manifest: "
            + ", ".join(supplied_candidate_values)
        )
    if args.freeze:
        return 0 if freeze_all() else 1
    overall = True
    results: list[bool] = []
    for case_id in CASES:
        case_ok = compare_case(case_id)
        results.append(case_ok)
        overall = case_ok and overall
    print(f"CURRENT TPG OFFICIAL: {'PASS' if all(results) else 'FAIL'}")
    print(f"CURRENT REGRESSION OVERALL: {'PASS' if overall else 'FAIL'}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())