#!/usr/bin/env python3
"""Freeze or verify the post-2026-07-12 current TPG regression baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from ref_enthalpy_method.gas import make_fluent_tpg_thermo, mu_sutherland
from ref_enthalpy_method.geometry.local_incidence import SURFACE_CLASS_LEEWARD

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "runs" / "current_baseline_snapshot"
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


def source_files() -> list[Path]:
    files = [
        RUNNER,
        VEHICLE, CASE, SAMPLING,
        ROOT / "new_spec" / "htv2_0628.stl",
        ROOT / "new_spec" / "outline_xz_right_0629.csv",
    ]
    files.extend(sorted((ROOT / "src" / "ref_enthalpy_method").rglob("*.py")))
    return files


def formal_command(case_id: str, run_dir: Path) -> list[str]:
    mach, alpha, altitude = CASES[case_id]
    return [
        sys.executable, str(RUNNER), "--vehicle", str(VEHICLE), "--case", str(CASE),
        "--sampling", str(SAMPLING), "--run_dir", str(run_dir), "--mach", str(mach),
        "--alpha", str(alpha), "--h_m", str(altitude),
        "--transition_weighting", "step", "--no_plots",
    ]


def run_formal(case_id: str, out: Path) -> list[str]:
    command = formal_command(case_id, out)
    subprocess.run(command, cwd=ROOT, check=True)
    for name in ("fields.npz", "summary.json"):
        if not (out / name).is_file():
            raise RuntimeError(f"formal runner did not produce {out / name}")
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


def build_manifest(case_id: str, run_dir: Path, command: list[str]) -> dict[str, Any]:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    with np.load(run_dir / "fields.npz", allow_pickle=False) as fields:
        schema = {key: {"shape": list(fields[key].shape), "dtype": str(fields[key].dtype)} for key in sorted(fields.files)}
        mask_w = np.asarray(fields["mask_w"]).astype(bool)
        endpoint = endpoint_from_fields(fields)
    freestream = summary.get("freestream", {})
    faceted3d = summary.get("faceted3d", {})
    mach, alpha, altitude = CASES[case_id]
    source_hashes = {
        str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path)
        for path in source_files()
    }
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
        "atmosphere": {
            "model": freestream.get("atmosphere_model"),
            "altitude_semantics": "geometric altitude converted to geopotential altitude before 1976 layer evaluation",
            "explicit_freestream_override": False,
        },
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
        "source_hashes_sha256": source_hashes,
        "artifact_hashes_sha256": {name: sha256(run_dir / name) for name in ("fields.npz", "summary.json")},
        "baseline_generator": "scripts/tools/current_baseline_regression_check.py --freeze",
        "generator_cli_template": subprocess.list2cmdline(formal_command(case_id, Path("<run_dir>"))),
    }


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
    rows.append(("atmosphere.no_override", nested(current, "atmosphere", "explicit_freestream_override") is False, "must be false"))
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
    artifact_hashes_ok, artifact_hash_errors = verify_artifact_hashes(case_id, baseline_dir, baseline_manifest)
    print(f"  Artifact hashes: {'PASS' if artifact_hashes_ok else 'FAIL'}")
    for error in artifact_hash_errors:
        print(f"    {error}")
    if not artifact_hashes_ok:
        print(f"[tpg/{case_id}] TPG OFFICIAL FAIL")
        return False
    with tempfile.TemporaryDirectory(prefix=f"baseline_compare_tpg_{case_id}_") as temp:
        current_dir = Path(temp)
        command = run_formal(case_id, current_dir)
        current_manifest = build_manifest(case_id, current_dir, command)
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
    parser.add_argument("--freeze", action="store_true", help="atomically generate or replace current TPG snapshots")
    args = parser.parse_args()
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