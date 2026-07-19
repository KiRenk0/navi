from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from ref_enthalpy_method.mapping.fluent_lf_pairing import FluentLfCleanPairing
from ref_enthalpy_method.mapping.fluent_lf_taw_comparison import FluentLfTawComparison
from scripts.tools import generate_leeward_source_evidence as evidence


def _readonly(value, dtype):
    result = np.array(value, dtype=dtype, copy=True, order="C")
    result.setflags(write=False)
    return result


def _comparison(count=186, *, sheet="upper", targets=None):
    source = np.arange(count, dtype=np.int64)
    target = np.asarray(targets if targets is not None else source % 80, dtype=np.int64)
    wall = np.linspace(200.0, 400.0, count, dtype=np.float64)
    prediction = np.linspace(300.0, 500.0, count, dtype=np.float64)
    signed = prediction - wall
    signed_relative = 100.0 * signed / wall
    return FluentLfTawComparison(
        sheet=sheet,
        source_csv_sha256="a" * 64,
        observation_field_name="wall-temperature",
        prediction_field_name=f"Taw_tpg_leeward_{sheet}",
        unit="K",
        prediction_provider="ref_enthalpy_method.aero.leeward_recovery.build_leeward_freestream_recovery",
        pairing_metric=evidence.PAIRING_METRIC,
        source_canonical_index=_readonly(source, np.int64),
        source_row_index=_readonly(source[::-1], np.int64),
        target_canonical_index=_readonly(target, np.int64),
        wall_temperature_K=_readonly(wall, np.float64),
        Taw_tpg_leeward_K=_readonly(prediction, np.float64),
        signed_error_K=_readonly(signed, np.float64),
        signed_relative_error_pct=_readonly(signed_relative, np.float64),
        absolute_error_K=_readonly(np.abs(signed), np.float64),
        absolute_relative_error_pct=_readonly(np.abs(signed_relative), np.float64),
    )


def _pairing(comparison):
    count = comparison.source_canonical_index.size
    target = comparison.target_canonical_index
    if count:
        _, inverse, counts = np.unique(target, return_inverse=True, return_counts=True)
        multiplicity = counts[inverse]
    else:
        multiplicity = np.empty(0, dtype=np.int64)
    return FluentLfCleanPairing(
        sheet=comparison.sheet,
        metric=evidence.PAIRING_METRIC,
        target_pool_size=80 if count else 0,
        source_canonical_index=_readonly(comparison.source_canonical_index, np.int64),
        target_canonical_index=_readonly(target, np.int64),
        distance_m=_readonly(np.linspace(0.0, 0.02, count), np.float64),
        dx_m=_readonly(np.zeros(count), np.float64),
        dspan_m=_readonly(np.zeros(count), np.float64),
        second_target_canonical_index=_readonly(np.zeros(count), np.int64),
        second_distance_m=_readonly(np.ones(count), np.float64),
        ambiguity_margin_m=_readonly(np.ones(count), np.float64),
        mutual_nearest=_readonly(np.zeros(count), np.bool_),
        target_multiplicity=_readonly(multiplicity, np.int64),
    )


def _arrays(count=186, *, sheet="upper"):
    comparison = _comparison(count, sheet=sheet, targets=np.arange(count) % 80 if count else [])
    projected = np.column_stack((np.arange(max(count, 1)), np.arange(max(count, 1)) * 2, np.arange(max(count, 1)) * 3)).astype(np.float64)
    return evidence.build_raw_evidence_arrays(
        case_id="ma6_a5_h30km", sheet=sheet, comparison=comparison,
        pairing=_pairing(comparison), projected_xyz=projected,
    )


def _fake_case(case_id, _integration):
    upper = _arrays()
    upper["case_id"] = np.asarray(case_id, dtype="<U16")
    lower = _arrays(0, sheet="lower")
    lower["case_id"] = np.asarray(case_id, dtype="<U16")
    provenance = {
        "case_id": case_id,
        "inputs": {"synthetic": {"path": "synthetic", "raw_sha256": "b" * 64}},
        "sheets": {
            "upper": {"source_row_count": 186, "unique_target_count": 80, "typed_empty": False},
            "lower": {"source_row_count": 0, "unique_target_count": 0, "typed_empty": True},
        },
    }
    return {"upper": upper, "lower": lower}, provenance


def _generate(tmp_path, monkeypatch, **updates):
    monkeypatch.setattr(evidence, "_build_formal_case", _fake_case)
    monkeypatch.setattr(evidence, "SOURCE_MODULE_PATHS", ("scripts/tools/generate_leeward_source_evidence.py",))
    arguments = {
        "output_root": tmp_path,
        "case_ids": ("ma6_a5_h30km",),
        "created_utc": datetime(2026, 7, 20, 1, 2, 3, tzinfo=timezone.utc),
        "git_sha": "1" * 40,
        "integrations": {"ma6_a5_h30km": object()},
    }
    arguments.update(updates)
    return evidence.generate_evidence(**arguments)


def test_fields_order_scalars_and_per_row_contract():
    arrays = _arrays()
    assert tuple(arrays) == evidence.RAW_FIELD_NAMES
    assert tuple(arrays) == tuple(name for name, _ in evidence.RAW_FIELD_DTYPES)
    for name, dtype in evidence.RAW_FIELD_DTYPES:
        assert arrays[name].dtype == np.dtype(dtype)
        assert arrays[name].shape == (() if name in evidence.SCALAR_FIELDS else (186,))
        if name not in evidence.SCALAR_FIELDS and np.issubdtype(arrays[name].dtype, np.floating):
            assert np.all(np.isfinite(arrays[name]))


def test_source_order_preservation_many_to_one_and_error_passthrough():
    comparison = _comparison()
    arrays = evidence.build_raw_evidence_arrays(
        case_id="ma6_a5_h30km", sheet="upper", comparison=comparison,
        pairing=_pairing(comparison), projected_xyz=np.arange(186 * 3, dtype=np.float64).reshape(186, 3),
    )
    assert arrays["source_row_index"].tolist() == list(range(185, -1, -1))
    assert arrays["source_canonical_index"].size == 186
    assert np.unique(arrays["target_canonical_index"]).size == 80
    for name in evidence.ERROR_FIELDS:
        assert np.array_equal(arrays[name], getattr(comparison, name))
    assert set(evidence.ERROR_FIELDS).isdisjoint({"diagnostic_pairing_distance_m", "diagnostic_target_multiplicity"})


def test_coordinates_are_direct_canonical_indexing_not_source_row_or_nearest():
    comparison = _comparison(3, targets=[2, 1, 0])
    projected = np.array([[10., 11., 12.], [20., 21., 22.], [30., 31., 32.]])
    arrays = evidence.build_raw_evidence_arrays(
        case_id="ma6_a5_h30km", sheet="upper", comparison=comparison,
        pairing=_pairing(comparison), projected_xyz=projected,
    )
    assert arrays["source_projected_x_m"].tolist() == [10., 20., 30.]
    assert arrays["source_projected_span_m"].tolist() == [11., 21., 31.]
    assert arrays["source_projected_up_m"].tolist() == [12., 22., 32.]


def test_lower_is_fully_typed_empty():
    arrays = _arrays(0, sheet="lower")
    assert all(arrays[name].shape == (0,) for name in evidence.RAW_FIELD_NAMES[8:])
    assert all(arrays[name].dtype == np.dtype(dtype) for name, dtype in evidence.RAW_FIELD_DTYPES)
    summary = evidence.build_sheet_summary(arrays)
    assert summary["typed_empty"] is True
    assert summary["source_row_count"] == summary["unique_target_count"] == 0
    assert all(block == {"count": 0, "status": "typed_empty"} for block in summary["error_statistics"].values())
    assert summary["prediction_direction"] == {"count": 0, "status": "typed_empty"}
    assert "null" not in json.dumps(summary)


def test_deterministic_npz_round_trip_order_and_no_pickle(tmp_path):
    arrays = _arrays()
    first = evidence.deterministic_npz_bytes(arrays)
    second = evidence.deterministic_npz_bytes(arrays)
    assert first == second
    path = tmp_path / "evidence.npz"
    evidence.write_deterministic_npz(path, arrays)
    with zipfile.ZipFile(path) as archive:
        assert archive.namelist() == [f"{name}.npy" for name in evidence.RAW_FIELD_NAMES]
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())
    with np.load(path, allow_pickle=False) as loaded:
        assert loaded.files == list(evidence.RAW_FIELD_NAMES)
        assert all(not loaded[name].dtype.hasobject for name in loaded.files)


def test_summary_equal_source_weight_quantiles_and_direction_conservation():
    arrays = _arrays()
    summary = evidence.build_sheet_summary(arrays)
    assert summary["source_row_count"] == 186
    assert summary["unique_target_count"] == 80
    assert summary["target_multiplicity"]["diagnostic_only"] is True
    expected_keys = {"count", "mean", "median", "min", "max", "p05", "p25", "p50", "p75", "p95"}
    for block in summary["error_statistics"].values():
        assert set(block) == expected_keys
        assert block["median"] == block["p50"]
    direction = summary["prediction_direction"]
    assert direction["overprediction_count"] + direction["underprediction_count"] + direction["exact_zero_count"] == 186
    assert direction["overprediction_fraction"] + direction["underprediction_fraction"] + direction["exact_zero_fraction"] == pytest.approx(1.0)


def test_case_summary_status_has_no_performance_assessment():
    summary = evidence.build_case_summary("ma6_a5_h30km", {"upper": _arrays(), "lower": _arrays(0, sheet="lower")})
    assert summary["population"] == "fluent_source_rows_equal_weight"
    assert summary["run_status"] == "PASS"
    assert summary["status_semantics"] == evidence.STATUS_SEMANTICS
    assert summary["model_performance_assessment"] == "not_performed"
    text = json.dumps(summary)
    assert "threshold" not in text and "acceptable_error" not in text


def test_fixed_string_truncation_and_identity_fail_closed():
    comparison = _comparison(1)
    object.__setattr__(comparison, "prediction_provider", "x" * 129)
    with pytest.raises(RuntimeError, match="exceeds fixed string"):
        evidence.build_raw_evidence_arrays(
            case_id="ma6_a5_h30km", sheet="upper", comparison=comparison,
            pairing=_pairing(comparison), projected_xyz=np.zeros((1, 3), dtype=np.float64),
        )
    with pytest.raises(RuntimeError, match="outside registry"):
        evidence.build_raw_evidence_arrays(
            case_id="unknown", sheet="upper", comparison=_comparison(1),
            pairing=_pairing(_comparison(1)), projected_xyz=np.zeros((1, 3), dtype=np.float64),
        )


@pytest.mark.parametrize("fault", ["dtype", "shape", "finite", "source"])
def test_projection_and_source_identity_fail_closed(fault):
    comparison = _comparison(2)
    pairing = _pairing(comparison)
    projected = np.zeros((2, 3), dtype=np.float64)
    if fault == "dtype": projected = projected.astype(np.float32)
    elif fault == "shape": projected = projected[:, :2]
    elif fault == "finite": projected[0, 0] = np.nan
    else: object.__setattr__(pairing, "source_canonical_index", _readonly([0, 2], np.int64))
    with pytest.raises(RuntimeError):
        evidence.build_raw_evidence_arrays(
            case_id="ma6_a5_h30km", sheet="upper", comparison=comparison,
            pairing=pairing, projected_xyz=projected,
        )


def test_visualization_smoke_metadata_and_raw_unchanged(tmp_path):
    arrays = _arrays()
    raw_before = {name: value.tobytes() for name, value in arrays.items()}
    fixed, adaptive, diagnostic = tmp_path / "fixed.png", tmp_path / "adaptive.png", tmp_path / "diagnostic.png"
    evidence._plot_errors(arrays, fixed, run_id="run", mode="fixed")
    evidence._plot_errors(arrays, adaptive, run_id="run", mode="adaptive")
    evidence._plot_multiplicity(arrays, diagnostic, run_id="run")
    for path, role in ((fixed, "formal_evidence"), (adaptive, "formal_evidence"), (diagnostic, "diagnostic_only")):
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            assert image.info["evidence_role"] == role
            assert image.info["comparison_contract_id"] == evidence.COMPARISON_CONTRACT_ID
    assert raw_before == {name: value.tobytes() for name, value in arrays.items()}


def test_atomic_publication_structure_hashes_lower_no_png_and_override(tmp_path, monkeypatch):
    published = _generate(tmp_path, monkeypatch)
    assert published.parent == tmp_path.resolve()
    assert published.name == "20260720T010203Z_111111111111"
    assert (published / "cases/ma6_a5_h30km/sheets/upper/raw_evidence.npz").is_file()
    assert (published / "cases/ma6_a5_h30km/sheets/lower/raw_evidence.npz").is_file()
    assert not (published / "cases/ma6_a5_h30km/sheets/lower/figures").exists()
    manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
    required = {"manifest_schema", "run_id", "created_utc", "git_sha", "generator", "case_registry", "cases", "artifact_hashes_sha256", "run_status", "status_semantics", "model_performance_assessment"}
    assert required.issubset(manifest)
    for item in manifest["artifact_hashes_sha256"]:
        path = published / item["filename"]
        assert path.stat().st_size == item["byte_size"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["raw_sha256"]
    detached = (published / "manifest.sha256").read_text(encoding="ascii").split()[0]
    assert detached == hashlib.sha256((published / "manifest.json").read_bytes()).hexdigest()
    assert not list(tmp_path.glob(".*.staging-*"))


def test_existing_run_and_existing_staging_fail_closed(tmp_path, monkeypatch):
    published = _generate(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="already exists"):
        _generate(tmp_path, monkeypatch)
    assert published.is_dir()
    other = tmp_path / ".20260720T010204Z_111111111111.staging-unknown"
    other.mkdir()
    with pytest.raises(RuntimeError, match="staging"):
        _generate(tmp_path, monkeypatch, created_utc=datetime(2026, 7, 20, 1, 2, 4, tzinfo=timezone.utc))
    assert other.is_dir()


def test_handled_failure_does_not_publish_and_removes_only_own_staging(tmp_path, monkeypatch):
    def fail(*_args):
        raise RuntimeError("injected")
    monkeypatch.setattr(evidence, "_build_formal_case", fail)
    monkeypatch.setattr(evidence, "SOURCE_MODULE_PATHS", ("scripts/tools/generate_leeward_source_evidence.py",))
    unknown = tmp_path / ".unrelated.staging-keep"
    unknown.mkdir()
    with pytest.raises(RuntimeError, match="injected"):
        evidence.generate_evidence(
            output_root=tmp_path, case_ids=("ma6_a5_h30km",),
            created_utc=datetime(2026, 7, 20, 1, 2, 3, tzinfo=timezone.utc),
            git_sha="1" * 40, integrations={"ma6_a5_h30km": object()},
        )
    assert not (tmp_path / "20260720T010203Z_111111111111").exists()
    assert unknown.is_dir()
    assert list(tmp_path.glob(".20260720T010203Z_111111111111.staging-*")) == []


def test_registry_fail_closed_before_publication(tmp_path):
    with pytest.raises(RuntimeError, match="outside registry"):
        evidence.generate_evidence(output_root=tmp_path, case_ids=("unknown",), git_sha="1" * 40)
    assert list(tmp_path.iterdir()) == []