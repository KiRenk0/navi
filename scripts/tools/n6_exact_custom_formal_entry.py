#!/usr/bin/env python3
"""Preflight and execute the N6 exact-custom formal package atomically."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for _path in (ROOT, SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from ref_enthalpy_method.mapping.observation_binding import (
    FluentObservationBinding,
    build_approved_observation_binding,
    exact_freestream_cli_arguments,
    validate_exact_freestream_manifest,
    validate_exact_freestream_summary,
    validate_observation_binding,
)
from scripts.tools import generate_leeward_source_evidence as evidence
from scripts.tools.current_baseline_regression_check import (
    build_canonical_source_identity,
    sha256,
    validate_production_source_clean,
    validate_source_identity_schema,
)

FORMAL_CASE_IDS = ("ma6_a5_h30km", "ma8_a5_h40km")
FORMAL_LF_MANIFEST_SCHEMA = "faceted3d-exact-custom-lf-run-manifest/v1"
FORMAL_PACKAGE_MANIFEST_SCHEMA = "faceted3d-n6-exact-custom-package-manifest/v1"
VEHICLE_PATH = "specs/vehicles/htv2_faceted3d_0629.yaml"
CASE_PATH = "specs/cases/doc_ma6_alpha5_h30km_faceted3d.yaml"
SAMPLING_PATH = "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml"
RUNNER_PATH = "scripts/run_case_rem.py"
DEFAULT_OUTPUT_ROOT = ROOT / "runs" / "n6_exact_custom_formal"
LEGACY_PATH_PARTS = frozenset({"current_baseline_snapshot", "leeward_source_evidence"})


@dataclass(frozen=True)
class FormalCasePlan:
    case_id: str
    observation_path: str
    observation_raw_sha256: str
    observation_byte_size: int
    p_inf_Pa_token: str
    T_inf_K_token: str
    p_inf_Pa_decimal: str
    T_inf_K_decimal: str
    mach_token: str
    alpha_deg_token: str
    nominal_altitude_km_token: str
    mach_decimal: str
    alpha_deg_decimal: str
    nominal_geometric_altitude_m_decimal: str
    vehicle_path: str
    case_path: str
    sampling_path: str
    staging_run_dir: str
    published_run_dir: str
    fields_path: str
    summary_path: str
    manifest_path: str
    solver_command: tuple[str, ...]


@dataclass(frozen=True)
class FormalExecutionPlan:
    package_id: str
    created_utc: str
    git_sha: str
    output_root: str
    staging_path: str
    publication_path: str
    package_manifest_path: str
    case_ids: tuple[str, ...]
    historical_fallback: bool
    source_identity: Mapping[str, Any]
    source_hashes_sha256: Mapping[str, str]
    cases: tuple[FormalCasePlan, ...]


Runner = Callable[[Sequence[str], Path], None]
ManifestBuilder = Callable[[FormalCasePlan, FluentObservationBinding, Mapping[str, Any], Mapping[str, Any]], dict[str, Any]]
EvidenceGenerator = Callable[..., Path]
PlanValidator = Callable[[FormalExecutionPlan, ManifestBuilder], None]


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            key: _freeze_mapping(item) if isinstance(item, Mapping) else item
            for key, item in value.items()
        }
    )


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {
            field.name: _plain_value(getattr(value, field.name))
            for field in fields(value)
        }
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def validate_formal_case_selection(case_ids: Iterable[str]) -> tuple[str, ...]:
    selected = tuple(case_ids)
    if not selected:
        raise ValueError("formal case selection must be nonempty")
    if len(selected) != len(set(selected)):
        raise ValueError("formal case selection contains a duplicate case")
    rejected = [case_id for case_id in selected if case_id not in FORMAL_CASE_IDS]
    if rejected:
        raise ValueError(f"case is outside the N6 formal core: {rejected[0]}")
    return selected


def _resolve_repo_input(repo_relative: str) -> Path:
    if not isinstance(repo_relative, str) or not repo_relative or "\\" in repo_relative:
        raise ValueError("production input path must be POSIX-style and repo-relative")
    path = (ROOT / repo_relative).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError("production input path escapes repository root") from exc
    if not path.is_file():
        raise FileNotFoundError(f"missing production input: {repo_relative}")
    return path


def _resolve_output_root(output_root: str | Path) -> Path:
    root = Path(output_root).resolve()
    if root == ROOT or root.parent == root:
        raise ValueError("formal output root must be a dedicated directory")
    if LEGACY_PATH_PARTS.intersection(root.parts):
        raise ValueError("formal output root must not use a historical evidence or baseline path")
    return root


def _git_output(args: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def validate_git_semantic_clean() -> str:
    head = _git_output(("rev-parse", "HEAD"))
    if len(head) != 40 or any(character not in "0123456789abcdef" for character in head):
        raise RuntimeError("clean committed HEAD identity is invalid")
    status_lines = tuple(line for line in _git_output(("status", "--porcelain=v1")).splitlines() if line)
    unexpected = tuple(line for line in status_lines if line != "?? attachment/")
    if unexpected:
        raise RuntimeError(f"Git semantic clean gate failed: {unexpected[0]}")
    if _git_output(("diff", "--name-only")) or _git_output(("diff", "--cached", "--name-only")):
        raise RuntimeError("Git tracked worktree or index is not clean")
    return head


def _build_solver_command(binding: FluentObservationBinding, staging_run_dir: Path) -> tuple[str, ...]:
    identity = binding.filename_identity
    explicit = exact_freestream_cli_arguments(
        binding,
        T_inf_K=identity.T_inf_K,
        p_inf_Pa=identity.p_inf_Pa,
    )
    return (
        sys.executable,
        str(ROOT / RUNNER_PATH),
        "--vehicle",
        str(ROOT / VEHICLE_PATH),
        "--case",
        str(ROOT / CASE_PATH),
        "--sampling",
        str(ROOT / SAMPLING_PATH),
        "--run_dir",
        str(staging_run_dir),
        "--mach",
        identity.mach_token,
        "--alpha",
        identity.alpha_deg_token,
        "--h_m",
        _decimal_text(identity.geometric_altitude_m),
        *explicit,
        "--transition_weighting",
        "step",
        "--no_plots",
        "--no_dump_intermediate",
    )


def _build_case_plan(
    *,
    binding: FluentObservationBinding,
    staging_path: Path,
    publication_path: Path,
) -> FormalCasePlan:
    identity = binding.filename_identity
    staging_run_dir = staging_path / "lf" / binding.case_key
    published_run_dir = publication_path / "lf" / binding.case_key
    command = _build_solver_command(binding, staging_run_dir)
    return FormalCasePlan(
        case_id=binding.case_key,
        observation_path=binding.csv_path,
        observation_raw_sha256=binding.raw_sha256,
        observation_byte_size=binding.byte_size,
        p_inf_Pa_token=identity.p_inf_Pa_token,
        T_inf_K_token=identity.T_inf_K_token,
        p_inf_Pa_decimal=_decimal_text(identity.p_inf_Pa),
        T_inf_K_decimal=_decimal_text(identity.T_inf_K),
        mach_token=identity.mach_token,
        alpha_deg_token=identity.alpha_deg_token,
        nominal_altitude_km_token=identity.nominal_altitude_km_token,
        mach_decimal=_decimal_text(identity.mach),
        alpha_deg_decimal=_decimal_text(identity.alpha_deg),
        nominal_geometric_altitude_m_decimal=_decimal_text(identity.geometric_altitude_m),
        vehicle_path=VEHICLE_PATH,
        case_path=CASE_PATH,
        sampling_path=SAMPLING_PATH,
        staging_run_dir=str(staging_run_dir),
        published_run_dir=str(published_run_dir),
        fields_path=str(staging_run_dir / "fields.npz"),
        summary_path=str(staging_run_dir / "summary.json"),
        manifest_path=str(staging_run_dir / "manifest.json"),
        solver_command=command,
    )


def build_preflight_plan(
    *,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    case_ids: Iterable[str] = FORMAL_CASE_IDS,
    created_utc: datetime | None = None,
    git_clean_validator: Callable[[], str] = validate_git_semantic_clean,
    source_contract_builder: Callable[[], Mapping[str, Any]] | None = None,
    observation_builder: Callable[[str, Path], FluentObservationBinding] = build_approved_observation_binding,
    manifest_builder: ManifestBuilder | None = None,
) -> FormalExecutionPlan:
    selected = validate_formal_case_selection(case_ids)
    if manifest_builder is None:
        manifest_builder = build_formal_lf_manifest
    if not callable(manifest_builder):
        raise RuntimeError("formal LF manifest builder is unavailable")

    root = _resolve_output_root(output_root)
    head = git_clean_validator()
    validate_production_source_clean(ROOT)
    source_builder = source_contract_builder or (lambda: build_canonical_source_identity(ROOT))
    source_contract = dict(source_builder())
    validate_source_identity_schema(source_contract)

    for path in (RUNNER_PATH, VEHICLE_PATH, CASE_PATH, SAMPLING_PATH):
        _resolve_repo_input(path)

    created = (created_utc or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    created_text = created.strftime("%Y-%m-%dT%H:%M:%SZ")
    package_id = f"{created.strftime('%Y%m%dT%H%M%SZ')}_{head[:12]}_n6_exact_custom"
    publication_path = root / package_id
    staging_path = root / f".{package_id}.staging"
    if publication_path.exists():
        raise FileExistsError(f"formal publication target already exists: {publication_path}")
    if staging_path.exists():
        raise FileExistsError(f"formal staging target already exists: {staging_path}")

    bindings: list[FluentObservationBinding] = []
    for case_id in selected:
        binding = observation_builder(case_id, ROOT)
        passed, reason = validate_observation_binding(binding, repo_root=ROOT)
        if not passed:
            raise ValueError(f"{case_id}: approved observation binding rejected: {reason}")
        if binding.case_key != case_id:
            raise ValueError(f"{case_id}: observation binding case identity mismatch")
        bindings.append(binding)

    cases = tuple(
        _build_case_plan(binding=binding, staging_path=staging_path, publication_path=publication_path)
        for binding in bindings
    )
    for case in cases:
        command_text = " ".join(case.solver_command)
        if "current_baseline_snapshot" in command_text or "leeward_source_evidence" in command_text:
            raise ValueError("formal solver command references a historical path")
        if "--T_inf_K" not in case.solver_command or "--p_inf_Pa" not in case.solver_command:
            raise ValueError("formal solver command lacks paired explicit freestream overrides")

    return FormalExecutionPlan(
        package_id=package_id,
        created_utc=created_text,
        git_sha=head,
        output_root=str(root),
        staging_path=str(staging_path),
        publication_path=str(publication_path),
        package_manifest_path=str(publication_path / "package_manifest.json"),
        case_ids=selected,
        historical_fallback=False,
        source_identity=_freeze_mapping(source_contract["source_identity"]),
        source_hashes_sha256=_freeze_mapping(source_contract["source_hashes_sha256"]),
        cases=cases,
    )


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _observation_manifest_block(binding: FluentObservationBinding) -> dict[str, Any]:
    identity = binding.filename_identity
    return {
        "schema": binding.schema,
        "path": binding.csv_path,
        "raw_sha256": binding.raw_sha256,
        "byte_size": binding.byte_size,
        "filename_tokens": {
            "p_inf_Pa": identity.p_inf_Pa_token,
            "T_inf_K": identity.T_inf_K_token,
            "nominal_altitude_km": identity.nominal_altitude_km_token,
            "alpha_deg": identity.alpha_deg_token,
            "mach": identity.mach_token,
        },
        "decimal_identity": {
            "p_inf_Pa": _decimal_text(identity.p_inf_Pa),
            "T_inf_K": _decimal_text(identity.T_inf_K),
            "nominal_altitude_km": _decimal_text(identity.nominal_altitude_km),
            "alpha_deg": _decimal_text(identity.alpha_deg),
            "mach": _decimal_text(identity.mach),
        },
    }


def build_formal_lf_manifest(
    case: FormalCasePlan,
    binding: FluentObservationBinding,
    summary: Mapping[str, Any],
    source_contract: Mapping[str, Any],
) -> dict[str, Any]:
    run_dir = Path(case.staging_run_dir)
    fields_path = run_dir / "fields.npz"
    summary_path = run_dir / "summary.json"
    if not fields_path.is_file() or not summary_path.is_file():
        raise FileNotFoundError(f"{case.case_id}: solver artifacts are incomplete")
    validate_exact_freestream_summary(binding, summary)
    artifact_hashes = {
        "fields.npz": sha256(fields_path),
        "summary.json": sha256(summary_path),
    }
    artifact_inventory = [
        {
            "path": name,
            "raw_sha256": digest,
            "byte_size": (run_dir / name).stat().st_size,
        }
        for name, digest in artifact_hashes.items()
    ]
    manifest = {
        "manifest_schema": FORMAL_LF_MANIFEST_SCHEMA,
        "case_id": case.case_id,
        "git_sha": validate_git_semantic_clean(),
        "source_identity": source_contract["source_identity"],
        "source_hashes_sha256": source_contract["source_hashes_sha256"],
        "observation": _observation_manifest_block(binding),
        "solver": {
            "command": list(case.solver_command),
            "command_text": subprocess.list2cmdline(list(case.solver_command)),
            "vehicle_path": case.vehicle_path,
            "case_path": case.case_path,
            "sampling_path": case.sampling_path,
            "mach": case.mach_decimal,
            "alpha_deg": case.alpha_deg_decimal,
            "nominal_geometric_altitude_m": case.nominal_geometric_altitude_m_decimal,
        },
        "freestream": {
            "source": "explicit_override",
            "actual_T_inf_K": case.T_inf_K_decimal,
            "actual_p_inf_Pa": case.p_inf_Pa_decimal,
            "T_inf_K_token": case.T_inf_K_token,
            "p_inf_Pa_token": case.p_inf_Pa_token,
        },
        "atmosphere": {
            "model": "none / unverified",
            "nominal_altitude_semantics": "historical case identity only",
            "explicit_freestream_override": True,
        },
        "artifact_hashes_sha256": artifact_hashes,
        "artifact_inventory": artifact_inventory,
        "run_status": "PASS",
        "model_performance_assessment": "not_performed",
    }
    validate_formal_lf_manifest(
        manifest,
        case=case,
        binding=binding,
        summary=summary,
        source_contract=source_contract,
        run_dir=run_dir,
    )
    return manifest


def validate_formal_lf_manifest(
    manifest: Mapping[str, Any],
    *,
    case: FormalCasePlan,
    binding: FluentObservationBinding,
    summary: Mapping[str, Any],
    source_contract: Mapping[str, Any],
    run_dir: Path,
) -> None:
    required = {
        "manifest_schema", "case_id", "git_sha", "source_identity",
        "source_hashes_sha256", "observation", "solver", "freestream",
        "atmosphere", "artifact_hashes_sha256", "artifact_inventory",
        "run_status", "model_performance_assessment",
    }
    missing = required - set(manifest)
    if missing:
        raise ValueError(f"formal LF manifest missing field: {sorted(missing)[0]}")
    if manifest["manifest_schema"] != FORMAL_LF_MANIFEST_SCHEMA:
        raise ValueError("formal LF manifest schema mismatch")
    if manifest["case_id"] != case.case_id:
        raise ValueError("formal LF manifest case identity mismatch")
    if manifest["git_sha"] != validate_git_semantic_clean():
        raise ValueError("formal LF manifest Git SHA mismatch")
    if manifest["source_identity"] != source_contract["source_identity"] or manifest["source_hashes_sha256"] != source_contract["source_hashes_sha256"]:
        raise ValueError("formal LF manifest canonical source identity mismatch")
    validate_source_identity_schema(dict(manifest))
    if manifest["observation"] != _observation_manifest_block(binding):
        raise ValueError("formal LF manifest observation binding mismatch")
    solver = manifest["solver"]
    if not isinstance(solver, Mapping) or solver.get("command") != list(case.solver_command):
        raise ValueError("formal LF manifest solver command mismatch")
    expected_solver = {
        "vehicle_path": case.vehicle_path,
        "case_path": case.case_path,
        "sampling_path": case.sampling_path,
        "mach": case.mach_decimal,
        "alpha_deg": case.alpha_deg_decimal,
        "nominal_geometric_altitude_m": case.nominal_geometric_altitude_m_decimal,
    }
    if any(solver.get(key) != value for key, value in expected_solver.items()):
        raise ValueError("formal LF manifest solver identity mismatch")
    validate_exact_freestream_summary(binding, summary)
    validate_exact_freestream_manifest(binding, manifest)
    registered = manifest["artifact_hashes_sha256"]
    if not isinstance(registered, Mapping) or set(registered) != {"fields.npz", "summary.json"}:
        raise ValueError("formal LF manifest artifact hash map mismatch")
    for name, digest in registered.items():
        path = run_dir / name
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f"formal LF manifest artifact hash mismatch: {name}")
    if manifest["run_status"] != "PASS" or manifest["model_performance_assessment"] != "not_performed":
        raise ValueError("formal LF manifest status semantics mismatch")


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _default_runner(command: Sequence[str], cwd: Path) -> None:
    subprocess.run(list(command), cwd=cwd, check=True)


def _package_inventory(staging: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted((path for path in staging.rglob("*") if path.is_file()), key=lambda item: item.relative_to(staging).as_posix()):
        relative = path.relative_to(staging).as_posix()
        if relative == "package_manifest.json":
            continue
        entries.append({"path": relative, "byte_size": path.stat().st_size, "raw_sha256": sha256(path)})
    return entries


def _revalidate_plan(plan: FormalExecutionPlan, manifest_builder: ManifestBuilder) -> None:
    created = datetime.strptime(plan.created_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    refreshed = build_preflight_plan(
        output_root=plan.output_root,
        case_ids=plan.case_ids,
        created_utc=created,
        manifest_builder=manifest_builder,
    )
    if refreshed != plan:
        raise RuntimeError("formal execution plan changed after preflight")


def execute_formal_plan(
    plan: FormalExecutionPlan,
    *,
    runner: Runner = _default_runner,
    manifest_builder: ManifestBuilder = build_formal_lf_manifest,
    evidence_generator: EvidenceGenerator = evidence.generate_evidence,
    plan_validator: PlanValidator = _revalidate_plan,
) -> Path:
    if not callable(runner) or not callable(manifest_builder) or not callable(evidence_generator) or not callable(plan_validator):
        raise RuntimeError("formal execution dependencies are unavailable")
    if tuple(plan.case_ids) != FORMAL_CASE_IDS:
        raise ValueError("formal execution requires the complete frozen two-case core")
    if plan.historical_fallback:
        raise ValueError("historical fallback is prohibited for N6 exact-custom execution")
    plan_validator(plan, manifest_builder)
    created = datetime.strptime(plan.created_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    root = Path(plan.output_root)
    staging = Path(plan.staging_path)
    target = Path(plan.publication_path)
    if root.exists() and not root.is_dir():
        raise FileExistsError(f"formal output root is not a directory: {root}")
    if staging.exists() or target.exists():
        raise FileExistsError("formal staging or publication target already exists")

    root_created = not root.exists()
    root.mkdir(parents=True, exist_ok=True)
    staging.mkdir()
    source_contract = {
        "source_identity": dict(plan.source_identity),
        "source_hashes_sha256": dict(plan.source_hashes_sha256),
    }
    try:
        bundles: dict[str, evidence.LFInputBundle] = {}
        for case in plan.cases:
            runner(case.solver_command, ROOT)
            run_dir = Path(case.staging_run_dir)
            summary = _load_json_object(run_dir / "summary.json", label=f"{case.case_id} summary")
            binding = build_approved_observation_binding(case.case_id, ROOT)
            manifest = manifest_builder(case, binding, summary, source_contract)
            manifest_path = run_dir / "manifest.json"
            _write_json(manifest_path, manifest)
            persisted = _load_json_object(manifest_path, label=f"{case.case_id} manifest")
            validate_formal_lf_manifest(
                persisted,
                case=case,
                binding=binding,
                summary=summary,
                source_contract=source_contract,
                run_dir=run_dir,
            )
            bundles[case.case_id] = evidence.LFInputBundle(
                case_id=case.case_id,
                fields_path=run_dir / "fields.npz",
                summary_path=run_dir / "summary.json",
                manifest_path=manifest_path,
            )

        evidence_path = evidence_generator(
            output_root=staging / "evidence",
            case_ids=plan.case_ids,
            lf_inputs=bundles,
            created_utc=created,
            git_sha=plan.git_sha,
        )
        try:
            Path(evidence_path).resolve().relative_to(staging.resolve())
        except ValueError as exc:
            raise RuntimeError("evidence generator published outside formal staging") from exc

        inventory = _package_inventory(staging)
        package_manifest = {
            "manifest_schema": FORMAL_PACKAGE_MANIFEST_SCHEMA,
            "package_id": plan.package_id,
            "created_utc": plan.created_utc,
            "git_sha": plan.git_sha,
            "source_identity": dict(plan.source_identity),
            "case_ids": list(plan.case_ids),
            "historical_fallback": False,
            "artifact_inventory": inventory,
            "run_status": "PASS",
            "model_performance_assessment": "not_performed",
        }
        _write_json(staging / "package_manifest.json", package_manifest)
        for item in inventory:
            path = staging / item["path"]
            _require(path.stat().st_size == item["byte_size"], f"package artifact size changed: {item['path']}")
            _require(sha256(path) == item["raw_sha256"], f"package artifact hash changed: {item['path']}")
        os.replace(staging, target)
        return target
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if root_created and root.exists() and not any(root.iterdir()):
            root.rmdir()
        raise


def plan_as_dict(plan: FormalExecutionPlan) -> dict[str, Any]:
    return _plain_value(plan)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--execute", action="store_true", help="run both formal cases and atomically publish the package")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    plan = build_preflight_plan(
        output_root=args.output_root,
        case_ids=args.cases or FORMAL_CASE_IDS,
    )
    print(json.dumps(plan_as_dict(plan), ensure_ascii=False, indent=2))
    if not args.execute:
        return 0
    published = execute_formal_plan(plan)
    print(published)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())