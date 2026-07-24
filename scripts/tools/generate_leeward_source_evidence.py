#!/usr/bin/env python3
"""Generate immutable source-row leeward comparison evidence."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, Normalize, TwoSlopeNorm
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for _path in (ROOT, SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from ref_enthalpy_method.mapping.fluent_clean import build_fluent_clean_leeward_masks
from ref_enthalpy_method.mapping.fluent_lf_pairing import build_fluent_lf_clean_pairing
from ref_enthalpy_method.mapping.fluent_lf_taw_comparison import (
    FluentLfTawComparison,
    build_fluent_lf_taw_comparison,
)
from ref_enthalpy_method.mapping.fluent_wall_temperature import (
    build_fluent_wall_temperature_observations,
)
from ref_enthalpy_method.mapping.lf_clean import build_lf_clean_leeward_masks
from ref_enthalpy_method.mapping.observation_binding import (
    APPROVED_FORMAL_OBSERVATION_REGISTRY,
    build_approved_observation_binding,
    validate_exact_freestream_manifest,
    validate_exact_freestream_summary,
    validate_observation_binding,
)
from scripts.tools.faceted3d_phase5c_fluent_lf_pairing_qa import (
    _build_fluent_integrations,
)

COMPARISON_CONTRACT_ID = "fluent-lf-taw-comparison/v1"
SUMMARY_SCHEMA = "faceted3d-leeward-source-summary/v1"
MANIFEST_SCHEMA = "faceted3d-leeward-source-evidence-manifest/v1"
STATUS_SEMANTICS = "program_contract_asset_integrity_only"
PAIRING_METRIC = "projected_physical_x_span_euclidean_m"
DEFAULT_OUTPUT_ROOT = ROOT / "runs" / "leeward_source_evidence"

CASE_REGISTRY: dict[str, dict[str, Any]] = {
    "ma6_a5_h30km": {
        "mach": 6.0,
        "alpha_deg": 5.0,
        "geometric_altitude_m": 30000.0,
        "fluent_csv": APPROVED_FORMAL_OBSERVATION_REGISTRY["ma6_a5_h30km"],
        "lf_fields": "runs/current_baseline_snapshot/tpg/ma6_a5_h30km/fields.npz",
        "lf_summary": "runs/current_baseline_snapshot/tpg/ma6_a5_h30km/summary.json",
        "lf_manifest": "runs/current_baseline_snapshot/tpg/ma6_a5_h30km/manifest.json",
        "expectation": {"upper_source_rows": 186, "upper_unique_targets": 80, "lower_typed_empty": True},
    },
    "ma8_a5_h40km": {
        "mach": 8.0,
        "alpha_deg": 5.0,
        "geometric_altitude_m": 40000.0,
        "fluent_csv": APPROVED_FORMAL_OBSERVATION_REGISTRY["ma8_a5_h40km"],
        "lf_fields": "runs/current_baseline_snapshot/tpg/ma8_a5_h40km/fields.npz",
        "lf_summary": "runs/current_baseline_snapshot/tpg/ma8_a5_h40km/summary.json",
        "lf_manifest": "runs/current_baseline_snapshot/tpg/ma8_a5_h40km/manifest.json",
        "expectation": {"upper_source_rows": 186, "upper_unique_targets": 80, "lower_typed_empty": True},
    },
}


@dataclass(frozen=True)
class LFInputBundle:
    """Explicit immutable LF artifacts for one approved formal case."""

    case_id: str
    fields_path: Path
    summary_path: Path
    manifest_path: Path

    def __post_init__(self) -> None:
        if self.case_id not in CASE_REGISTRY:
            raise ValueError(f"case outside formal LF input registry: {self.case_id}")
        for name in ("fields_path", "summary_path", "manifest_path"):
            path = getattr(self, name)
            if not isinstance(path, Path) or not path.is_absolute():
                raise ValueError(f"{name} must be an explicit absolute Path")


RAW_FIELD_DTYPES: tuple[tuple[str, str], ...] = (
    ("case_id", "<U16"), ("sheet", "<U5"),
    ("comparison_contract_id", "<U48"), ("source_csv_sha256", "<U64"),
    ("observation_field_name", "<U32"), ("prediction_field_name", "<U32"),
    ("prediction_provider", "<U128"), ("pairing_metric", "<U64"),
    ("source_canonical_index", "int64"), ("source_row_index", "int64"),
    ("target_canonical_index", "int64"), ("source_projected_x_m", "float64"),
    ("source_projected_span_m", "float64"), ("source_projected_up_m", "float64"),
    ("wall_temperature_K", "float64"), ("Taw_tpg_leeward_K", "float64"),
    ("signed_error_K", "float64"), ("signed_relative_error_pct", "float64"),
    ("absolute_error_K", "float64"), ("absolute_relative_error_pct", "float64"),
    ("diagnostic_pairing_distance_m", "float64"),
    ("diagnostic_pairing_dx_m", "float64"),
    ("diagnostic_pairing_dspan_m", "float64"),
    ("diagnostic_target_multiplicity", "int64"),
)
RAW_FIELD_NAMES = tuple(name for name, _ in RAW_FIELD_DTYPES)
SCALAR_FIELDS = frozenset(RAW_FIELD_NAMES[:8])
ERROR_FIELDS = (
    "signed_error_K", "signed_relative_error_pct",
    "absolute_error_K", "absolute_relative_error_pct",
)
SOURCE_MODULE_PATHS = (
    "scripts/tools/generate_leeward_source_evidence.py",
    "src/ref_enthalpy_method/mapping/fluent_lf_taw_comparison.py",
    "src/ref_enthalpy_method/mapping/fluent_wall_temperature.py",
    "src/ref_enthalpy_method/mapping/fluent_lf_pairing.py",
    "src/ref_enthalpy_method/mapping/fluent_clean.py",
    "src/ref_enthalpy_method/mapping/lf_clean.py",
    "src/ref_enthalpy_method/mapping/fluent_surface.py",
    "src/ref_enthalpy_method/mapping/fluent_projection.py",
    "src/ref_enthalpy_method/mapping/fluent_semantics.py",
    "src/ref_enthalpy_method/mapping/observation_binding.py",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=False) + "\n").encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _fixed_string(value: str, dtype: str, name: str) -> np.ndarray:
    capacity = np.dtype(dtype).itemsize // 4
    _require(len(value) <= capacity, f"{name} exceeds fixed string dtype {dtype}")
    result = np.asarray(value, dtype=np.dtype(dtype))
    _require(str(result.item()) == value, f"{name} was truncated by fixed string dtype")
    return result


def build_raw_evidence_arrays(
    *, case_id: str, sheet: str, comparison: FluentLfTawComparison,
    pairing: Any, projected_xyz: np.ndarray,
) -> OrderedDict[str, np.ndarray]:
    _require(case_id in CASE_REGISTRY, f"case outside registry: {case_id}")
    _require(sheet in ("upper", "lower"), f"invalid sheet: {sheet}")
    _require(comparison.sheet == pairing.sheet == sheet, "sheet identity mismatch")
    _require(comparison.pairing_metric == pairing.metric == PAIRING_METRIC, "pairing metric mismatch")
    source = np.asarray(comparison.source_canonical_index)
    _require(np.array_equal(source, pairing.source_canonical_index), "comparison/pairing source identity mismatch")
    projection = np.asarray(projected_xyz)
    _require(projection.dtype == np.dtype(np.float64), "projected_xyz dtype must be float64")
    _require(projection.ndim == 2 and projection.shape[1] == 3, "projected_xyz shape must be (N, 3)")
    _require(np.all(np.isfinite(projection)), "projected_xyz must be finite")
    _require(not source.size or (np.min(source) >= 0 and np.max(source) < projection.shape[0]), "source canonical index outside projection")
    coordinates = projection[source]

    scalar_values = {
        "case_id": case_id, "sheet": sheet,
        "comparison_contract_id": COMPARISON_CONTRACT_ID,
        "source_csv_sha256": comparison.source_csv_sha256,
        "observation_field_name": comparison.observation_field_name,
        "prediction_field_name": comparison.prediction_field_name,
        "prediction_provider": comparison.prediction_provider,
        "pairing_metric": comparison.pairing_metric,
    }
    row_values = {
        "source_canonical_index": comparison.source_canonical_index,
        "source_row_index": comparison.source_row_index,
        "target_canonical_index": comparison.target_canonical_index,
        "source_projected_x_m": coordinates[:, 0],
        "source_projected_span_m": coordinates[:, 1],
        "source_projected_up_m": coordinates[:, 2],
        "wall_temperature_K": comparison.wall_temperature_K,
        "Taw_tpg_leeward_K": comparison.Taw_tpg_leeward_K,
        "signed_error_K": comparison.signed_error_K,
        "signed_relative_error_pct": comparison.signed_relative_error_pct,
        "absolute_error_K": comparison.absolute_error_K,
        "absolute_relative_error_pct": comparison.absolute_relative_error_pct,
        "diagnostic_pairing_distance_m": pairing.distance_m,
        "diagnostic_pairing_dx_m": pairing.dx_m,
        "diagnostic_pairing_dspan_m": pairing.dspan_m,
        "diagnostic_target_multiplicity": pairing.target_multiplicity,
    }
    result: OrderedDict[str, np.ndarray] = OrderedDict()
    count = source.size
    for name, dtype_text in RAW_FIELD_DTYPES:
        dtype = np.dtype(dtype_text)
        if name in SCALAR_FIELDS:
            result[name] = _fixed_string(scalar_values[name], dtype_text, name)
        else:
            value = np.asarray(row_values[name])
            _require(value.dtype == dtype, f"{name} dtype mismatch: {value.dtype} != {dtype}")
            _require(value.shape == (count,), f"{name} shape mismatch")
            if np.issubdtype(dtype, np.floating):
                _require(np.all(np.isfinite(value)), f"{name} contains non-finite values")
            result[name] = np.array(value, dtype=dtype, copy=True, order="C")
    _require(tuple(result) == RAW_FIELD_NAMES, "raw evidence field order changed")
    return result


def deterministic_npz_bytes(arrays: Mapping[str, np.ndarray]) -> bytes:
    _require(tuple(arrays) == RAW_FIELD_NAMES, "NPZ member order must match raw contract")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, value in arrays.items():
            array = np.asarray(value)
            _require(not array.dtype.hasobject, f"{name} object dtype is prohibited")
            member = io.BytesIO()
            np.lib.format.write_array(member, array, allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, member.getvalue(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def write_deterministic_npz(path: Path, arrays: Mapping[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(deterministic_npz_bytes(arrays))
    with np.load(path, allow_pickle=False) as loaded:
        _require(tuple(loaded.files) == RAW_FIELD_NAMES, "written NPZ member order changed")
        for name, expected in arrays.items():
            actual = loaded[name]
            _require(actual.dtype == expected.dtype and actual.shape == expected.shape, f"written NPZ contract changed: {name}")
            _require(actual.tobytes(order="C") == expected.tobytes(order="C"), f"written NPZ bytes changed: {name}")


def build_sheet_summary(arrays: Mapping[str, np.ndarray]) -> dict[str, Any]:
    count = int(arrays["source_canonical_index"].size)
    unique_targets = int(np.unique(arrays["target_canonical_index"]).size)
    if count == 0:
        return {
            "sheet": str(arrays["sheet"].item()), "typed_empty": True,
            "source_row_count": 0, "unique_target_count": 0,
            "target_multiplicity": {"status": "typed_empty", "diagnostic_only": True, "histogram": {}},
            "error_statistics": {name: {"count": 0, "status": "typed_empty"} for name in ERROR_FIELDS},
            "prediction_direction": {"count": 0, "status": "typed_empty"},
        }
    statistics: dict[str, Any] = {}
    for name in ERROR_FIELDS:
        values = arrays[name]
        quantiles = np.quantile(values, [0.05, 0.25, 0.50, 0.75, 0.95])
        statistics[name] = {
            "count": count, "mean": float(np.mean(values)), "median": float(quantiles[2]),
            "min": float(np.min(values)), "max": float(np.max(values)),
            "p05": float(quantiles[0]), "p25": float(quantiles[1]),
            "p50": float(quantiles[2]), "p75": float(quantiles[3]), "p95": float(quantiles[4]),
        }
    signed = arrays["signed_error_K"]
    over, under, zero = int(np.count_nonzero(signed > 0)), int(np.count_nonzero(signed < 0)), int(np.count_nonzero(signed == 0.0))
    _require(over + under + zero == count, "prediction direction counts do not conserve population")
    multiplicities, multiplicity_counts = np.unique(arrays["diagnostic_target_multiplicity"], return_counts=True)
    return {
        "sheet": str(arrays["sheet"].item()), "typed_empty": False,
        "source_row_count": count, "unique_target_count": unique_targets,
        "target_multiplicity": {
            "diagnostic_only": True,
            "histogram": {str(int(k)): int(v) for k, v in zip(multiplicities, multiplicity_counts)},
        },
        "error_statistics": statistics,
        "prediction_direction": {
            "overprediction_count": over, "overprediction_fraction": over / count,
            "underprediction_count": under, "underprediction_fraction": under / count,
            "exact_zero_count": zero, "exact_zero_fraction": zero / count,
        },
    }


def build_case_summary(case_id: str, sheets: Mapping[str, Mapping[str, np.ndarray]]) -> dict[str, Any]:
    _require(tuple(sheets) == ("upper", "lower"), "case sheets must be upper then lower")
    return {
        "summary_schema": SUMMARY_SCHEMA, "case_id": case_id,
        "comparison_contract_id": COMPARISON_CONTRACT_ID,
        "population": "fluent_source_rows_equal_weight", "relative_error_unit": "percent",
        "provenance_ref": "../../manifest.json", "run_status": "PASS",
        "status_semantics": STATUS_SEMANTICS, "model_performance_assessment": "not_performed",
        "sheets": {name: build_sheet_summary(value) for name, value in sheets.items()},
    }


def _png_metadata(*, case_id: str, sheet: str, plotted_field: str, scale_mode: str,
                  limits: str, run_id: str, evidence_role: str) -> dict[str, str]:
    return {
        "case_id": case_id, "sheet": sheet, "plotted_field": plotted_field,
        "coordinate_fields": "source_projected_x_m,source_projected_span_m",
        "scale_mode": scale_mode, "limits": limits,
        "comparison_contract_id": COMPARISON_CONTRACT_ID, "run_id": run_id,
        "evidence_role": evidence_role, "manifest_relative_reference": "../../../../../manifest.json",
    }


def _plot_errors(arrays: Mapping[str, np.ndarray], path: Path, *, run_id: str, mode: str) -> None:
    case_id, sheet = str(arrays["case_id"].item()), str(arrays["sheet"].item())
    x, y = arrays["source_projected_x_m"], arrays["source_projected_span_m"]
    specs = (
        ("signed_error_K", (-1000.0, 1000.0), "coolwarm"),
        ("signed_relative_error_pct", (-100.0, 100.0), "coolwarm"),
        ("absolute_error_K", (0.0, 1000.0), "viridis"),
        ("absolute_relative_error_pct", (0.0, 100.0), "viridis"),
    )
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    real_limits: dict[str, list[float]] = {}
    for axis, (field, fixed, cmap) in zip(axes.flat, specs):
        values = arrays[field]
        real_limits[field] = [float(np.min(values)), float(np.max(values))]
        if mode == "fixed":
            norm = Normalize(vmin=fixed[0], vmax=fixed[1], clip=False)
            limits = fixed
        elif field.startswith("signed"):
            extent = max(abs(real_limits[field][0]), abs(real_limits[field][1]))
            extent = extent if extent > 0 else 1.0
            norm = TwoSlopeNorm(vmin=-extent, vcenter=0.0, vmax=extent)
            limits = (-extent, extent)
        else:
            maximum = real_limits[field][1]
            display_max = maximum if maximum > 0 else 1.0
            norm = Normalize(vmin=0.0, vmax=display_max)
            limits = (0.0, display_max)
        scatter = axis.scatter(x, y, c=values, s=18, cmap=cmap, norm=norm)
        fig.colorbar(scatter, ax=axis, extend="both" if field.startswith("signed") else "max")
        axis.set(title=field, xlabel="source_projected_x_m", ylabel="source_projected_span_m")
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = _png_metadata(case_id=case_id, sheet=sheet, plotted_field=",".join(ERROR_FIELDS),
        scale_mode=mode, limits=json.dumps({"display": mode, "actual": real_limits}, separators=(",", ":")),
        run_id=run_id, evidence_role="formal_evidence")
    fig.savefig(path, dpi=170, metadata=metadata)
    plt.close(fig)


def _plot_multiplicity(arrays: Mapping[str, np.ndarray], path: Path, *, run_id: str) -> None:
    case_id, sheet = str(arrays["case_id"].item()), str(arrays["sheet"].item())
    values = arrays["diagnostic_target_multiplicity"]
    bounds = np.arange(int(values.min()), int(values.max()) + 2) - 0.5
    fig, axis = plt.subplots(figsize=(7.8, 4.8), constrained_layout=True)
    scatter = axis.scatter(arrays["source_projected_x_m"], arrays["source_projected_span_m"],
                           c=values, cmap="viridis", norm=BoundaryNorm(bounds, 256), s=20)
    fig.colorbar(scatter, ax=axis, ticks=np.arange(int(values.min()), int(values.max()) + 1))
    axis.set(title="Diagnostic source-target multiplicity", xlabel="source_projected_x_m", ylabel="source_projected_span_m")
    metadata = _png_metadata(case_id=case_id, sheet=sheet, plotted_field="diagnostic_target_multiplicity",
        scale_mode="discrete", limits=f"{int(values.min())},{int(values.max())}", run_id=run_id,
        evidence_role="diagnostic_only")
    fig.savefig(path, dpi=170, metadata=metadata)
    plt.close(fig)


def _artifact_entry(run_dir: Path, path: Path, *, role: str, media_type: str,
                    identity: str, evidence_role: str) -> dict[str, Any]:
    relative = path.relative_to(run_dir).as_posix()
    return {"filename": relative, "role": role, "media_type": media_type,
            "schema_or_figure_identity": identity, "byte_size": path.stat().st_size,
            "raw_sha256": sha256_file(path), "evidence_role": evidence_role}


def validate_formal_case_freestream(
    case_id: str,
    summary: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> None:
    binding = build_approved_observation_binding(case_id, ROOT)
    passed, reason = validate_observation_binding(binding, repo_root=ROOT)
    _require(passed, f"{case_id}: formal observation binding rejected: {reason}")
    validate_exact_freestream_summary(binding, summary)
    validate_exact_freestream_manifest(binding, manifest)


def _load_case_inputs(
    case_id: str,
    lf_input: LFInputBundle | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, Any], dict[str, Any]]:
    if lf_input is None:
        entry = CASE_REGISTRY[case_id]
        fields_path, summary_path, manifest_path = (
            ROOT / entry[key] for key in ("lf_fields", "lf_summary", "lf_manifest")
        )
    else:
        _require(lf_input.case_id == case_id, f"{case_id}: explicit LF bundle case mismatch")
        fields_path, summary_path, manifest_path = (
            lf_input.fields_path,
            lf_input.summary_path,
            lf_input.manifest_path,
        )
    for label, path in (
        ("fields", fields_path),
        ("summary", summary_path),
        ("manifest", manifest_path),
    ):
        _require(path.is_file(), f"{case_id}: missing explicit LF {label}: {path}")
    with np.load(fields_path, allow_pickle=False) as loaded:
        fields = {name: np.array(loaded[name], copy=True) for name in loaded.files}
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(isinstance(summary, dict), f"{case_id}: LF summary must be an object")
    _require(isinstance(manifest, dict), f"{case_id}: LF manifest must be an object")
    validate_formal_case_freestream(case_id, summary, manifest)
    return fields, summary, manifest


def _input_identity(path: str | Path, *, reference_dir: Path | None = None) -> dict[str, Any]:
    full_path = ROOT / path if isinstance(path, str) else path
    _require(full_path.is_file(), f"missing registered input: {path}")
    if reference_dir is None:
        display_path = str(path).replace("\\", "/")
    else:
        display_path = os.path.relpath(full_path, start=reference_dir).replace("\\", "/")
    return {
        "path": display_path,
        "raw_sha256": sha256_file(full_path),
        "byte_size": full_path.stat().st_size,
    }


def _validate_projection(integration: Any) -> np.ndarray:
    projection = integration.projection
    xyz = np.asarray(projection.projected_xyz)
    count = xyz.shape[0] if xyz.ndim == 2 else -1
    _require(xyz.dtype == np.dtype(np.float64) and xyz.shape == (count, 3), "authoritative projection contract invalid")
    _require(np.array_equal(projection.canonical_index, np.arange(count, dtype=np.int64)), "projection canonical identity invalid")
    _require(np.all(np.isfinite(xyz)), "authoritative projection contains non-finite coordinates")
    return xyz


def _build_formal_case(
    case_id: str,
    integration: Any,
    *,
    lf_input: LFInputBundle | None = None,
    evidence_target: Path | None = None,
) -> tuple[dict[str, OrderedDict[str, np.ndarray]], dict[str, Any]]:
    entry = CASE_REGISTRY[case_id]
    fields, _baseline_summary, baseline_manifest = _load_case_inputs(case_id, lf_input)
    lf_masks = build_lf_clean_leeward_masks(fields)
    fluent_masks = build_fluent_clean_leeward_masks(integration)
    projected_xyz = _validate_projection(integration)
    sheet_arrays: dict[str, OrderedDict[str, np.ndarray]] = {}
    sheet_provenance: dict[str, Any] = {}
    for sheet in ("upper", "lower"):
        pairing = build_fluent_lf_clean_pairing(integration=integration, fluent_masks=fluent_masks,
            lf_fields=fields, lf_masks=lf_masks, sheet=sheet)
        observation = build_fluent_wall_temperature_observations(csv_path=ROOT / entry["fluent_csv"],
            integration=integration, fluent_masks=fluent_masks, pairing=pairing, sheet=sheet)
        comparison = build_fluent_lf_taw_comparison(observation=observation, pairing=pairing,
            lf_fields=fields, lf_masks=lf_masks, sheet=sheet)
        arrays = build_raw_evidence_arrays(case_id=case_id, sheet=sheet, comparison=comparison,
            pairing=pairing, projected_xyz=projected_xyz)
        sheet_arrays[sheet] = arrays
        sheet_provenance[sheet] = {
            "sheet": sheet, "source_row_count": int(comparison.source_canonical_index.size),
            "unique_target_count": int(np.unique(comparison.target_canonical_index).size),
            "typed_empty": comparison.source_canonical_index.size == 0,
            "observation_field": comparison.observation_field_name,
            "prediction_field": comparison.prediction_field_name,
            "prediction_provider": comparison.prediction_provider, "pairing_metric": comparison.pairing_metric,
        }
    expected = entry["expectation"]
    _require(sheet_provenance["upper"]["source_row_count"] == expected["upper_source_rows"], f"{case_id}: upper source rows changed")
    _require(sheet_provenance["upper"]["unique_target_count"] == expected["upper_unique_targets"], f"{case_id}: upper unique targets changed")
    _require(sheet_provenance["lower"]["typed_empty"] is expected["lower_typed_empty"], f"{case_id}: lower typed-empty changed")
    if lf_input is None:
        input_paths: dict[str, str | Path] = {
            name: entry[name] for name in ("fluent_csv", "lf_fields", "lf_summary", "lf_manifest")
        }
    else:
        input_paths = {
            "fluent_csv": entry["fluent_csv"],
            "lf_fields": lf_input.fields_path,
            "lf_summary": lf_input.summary_path,
            "lf_manifest": lf_input.manifest_path,
        }
    provenance = {
        "case_id": case_id, "mach": entry["mach"], "alpha_deg": entry["alpha_deg"],
        "geometric_altitude_m": entry["geometric_altitude_m"],
        "inputs": {
            name: _input_identity(
                path,
                reference_dir=evidence_target if lf_input is not None else None,
            )
            for name, path in input_paths.items()
        },
        "lf_input_mode": "explicit_bundle" if lf_input is not None else "legacy_registered",
        "baseline_artifact_hashes_sha256": baseline_manifest.get("artifact_hashes_sha256", {}),
        "comparison_api": {"type": "FluentLfTawComparison", "builder": "build_fluent_lf_taw_comparison",
                           "contract_id": COMPARISON_CONTRACT_ID},
        "sheets": sheet_provenance,
    }
    for artifact, registered_hash in provenance["baseline_artifact_hashes_sha256"].items():
        key = "lf_fields" if artifact == "fields.npz" else "lf_summary" if artifact == "summary.json" else None
        if key:
            _require(provenance["inputs"][key]["raw_sha256"] == registered_hash, f"{case_id}: baseline artifact hash mismatch: {artifact}")
    return sheet_arrays, provenance


def create_run_id(*, created_utc: datetime | None = None, git_sha: str | None = None) -> tuple[str, str, str]:
    created = (created_utc or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    sha = git_sha or subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                    capture_output=True, text=True).stdout.strip()
    _require(len(sha) == 40 and all(ch in "0123456789abcdef" for ch in sha), "invalid Git SHA")
    created_text = created.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{created.strftime('%Y%m%dT%H%M%SZ')}_{sha[:12]}", created_text, sha


def generate_evidence(*, output_root: str | Path = DEFAULT_OUTPUT_ROOT,
                      case_ids: Iterable[str] = tuple(CASE_REGISTRY),
                      run_id: str | None = None, created_utc: datetime | None = None,
                      git_sha: str | None = None, integrations: Mapping[str, Any] | None = None,
                      lf_inputs: Mapping[str, LFInputBundle] | None = None) -> Path:
    selected = tuple(case_ids)
    _require(selected and len(selected) == len(set(selected)), "case selection must be nonempty and unique")
    for case_id in selected:
        _require(case_id in CASE_REGISTRY, f"case outside registry: {case_id}")
    explicit_inputs: dict[str, LFInputBundle] | None = None
    if lf_inputs is not None:
        explicit_inputs = dict(lf_inputs)
        _require(set(explicit_inputs) == set(selected), "explicit LF inputs must exactly match selected formal cases")
        for case_id, bundle in explicit_inputs.items():
            _require(isinstance(bundle, LFInputBundle), f"{case_id}: explicit LF input must be LFInputBundle")
            _require(bundle.case_id == case_id, f"{case_id}: explicit LF input mapping key mismatch")

    generated_id, created_text, actual_sha = create_run_id(created_utc=created_utc, git_sha=git_sha)
    if run_id is not None:
        _require(run_id == generated_id, "explicit run_id does not match UTC/Git identity")
    run_id = generated_id
    root = Path(output_root).resolve()
    target = root / run_id
    _require(not target.exists(), f"run target already exists: {target}")
    if any(root.glob(f".{run_id}.staging-*")):
        raise RuntimeError(f"staging for run id already exists: {run_id}")

    formal_integrations = dict(integrations) if integrations is not None else _build_fluent_integrations()
    _require(set(selected).issubset(formal_integrations), "missing registered Fluent integration")
    prepared_cases: dict[str, tuple[dict[str, OrderedDict[str, np.ndarray]], dict[str, Any]]] = {}
    for case_id in selected:
        prepared_cases[case_id] = _build_formal_case(
            case_id,
            formal_integrations[case_id],
            lf_input=None if explicit_inputs is None else explicit_inputs[case_id],
            evidence_target=target,
        )

    root_created = not root.exists()
    root.mkdir(parents=True, exist_ok=True)
    staging = root / f".{run_id}.staging-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        artifacts: list[dict[str, Any]] = []
        case_provenance: dict[str, Any] = {}
        for case_id in selected:
            sheets, provenance = prepared_cases[case_id]
            case_provenance[case_id] = provenance
            case_dir = staging / "cases" / case_id
            for sheet, arrays in sheets.items():
                sheet_dir = case_dir / "sheets" / sheet
                raw_path = sheet_dir / "raw_evidence.npz"
                write_deterministic_npz(raw_path, arrays)
                artifacts.append(_artifact_entry(staging, raw_path, role="raw_source_evidence",
                    media_type="application/x-npz", identity="faceted3d-leeward-source-raw/v1", evidence_role="formal_evidence"))
                if arrays["source_canonical_index"].size:
                    fixed = sheet_dir / "figures" / "source_errors_fixed.png"
                    adaptive = sheet_dir / "figures" / "source_errors_adaptive.png"
                    multiplicity = sheet_dir / "figures" / "diagnostic_source_target_multiplicity.png"
                    _plot_errors(arrays, fixed, run_id=run_id, mode="fixed")
                    _plot_errors(arrays, adaptive, run_id=run_id, mode="adaptive")
                    _plot_multiplicity(arrays, multiplicity, run_id=run_id)
                    artifacts.extend((
                        _artifact_entry(staging, fixed, role="source_error_figure", media_type="image/png", identity="source-errors-fixed/v1", evidence_role="formal_evidence"),
                        _artifact_entry(staging, adaptive, role="source_error_figure", media_type="image/png", identity="source-errors-adaptive/v1", evidence_role="formal_evidence"),
                        _artifact_entry(staging, multiplicity, role="source_target_multiplicity", media_type="image/png", identity="diagnostic-source-target-multiplicity/v1", evidence_role="diagnostic_only"),
                    ))
            summary_path = case_dir / "summary.json"
            _write_json(summary_path, build_case_summary(case_id, sheets))
            artifacts.append(_artifact_entry(staging, summary_path, role="case_summary", media_type="application/json",
                identity=SUMMARY_SCHEMA, evidence_role="formal_evidence"))
        generator = {path: {"path": path, "raw_sha256": sha256_file(ROOT / path)} for path in SOURCE_MODULE_PATHS}
        if explicit_inputs is None:
            manifest_registry = {case_id: CASE_REGISTRY[case_id] for case_id in selected}
        else:
            manifest_registry = {
                case_id: {
                    "mach": CASE_REGISTRY[case_id]["mach"],
                    "alpha_deg": CASE_REGISTRY[case_id]["alpha_deg"],
                    "geometric_altitude_m": CASE_REGISTRY[case_id]["geometric_altitude_m"],
                    "fluent_csv": CASE_REGISTRY[case_id]["fluent_csv"],
                    "lf_input_mode": "explicit_bundle",
                    "expectation": CASE_REGISTRY[case_id]["expectation"],
                }
                for case_id in selected
            }
        manifest = {
            "manifest_schema": MANIFEST_SCHEMA, "run_id": run_id, "created_utc": created_text,
            "git_sha": actual_sha, "generator": generator,
            "case_registry": manifest_registry,
            "cases": case_provenance, "artifact_hashes_sha256": artifacts,
            "run_status": "PASS", "status_semantics": STATUS_SEMANTICS,
            "model_performance_assessment": "not_performed",
        }
        for artifact in artifacts:
            artifact_path = staging / artifact["filename"]
            _require(artifact_path.stat().st_size == artifact["byte_size"], "artifact size changed before publication")
            _require(sha256_file(artifact_path) == artifact["raw_sha256"], "artifact hash changed before publication")
        manifest_path = staging / "manifest.json"
        _write_json(manifest_path, manifest)
        manifest_hash = sha256_file(manifest_path)
        (staging / "manifest.sha256").write_text(f"{manifest_hash}  manifest.json\n", encoding="ascii", newline="\n")
        _require(sha256_file(manifest_path) == (staging / "manifest.sha256").read_text(encoding="ascii").split()[0], "detached manifest hash mismatch")
        os.replace(staging, target)
        return target
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if root_created and root.exists() and not any(root.iterdir()):
            root.rmdir()
        raise


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--case", action="append", dest="cases", choices=tuple(CASE_REGISTRY))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    published = generate_evidence(output_root=args.output_root, case_ids=args.cases or tuple(CASE_REGISTRY))
    print(published)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())