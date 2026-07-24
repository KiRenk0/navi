from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pytest

import ref_enthalpy_method.mapping.m8h30_comparison_inputs as preparation
from ref_enthalpy_method.mapping import (
    FluentLfTawComparisonInputs,
    M8H30ComparisonInputs,
    build_m8h30_comparison_inputs,
)
from ref_enthalpy_method.mapping.fluent_lf_pairing import FluentLfCleanPairing
from ref_enthalpy_method.mapping.fluent_lf_taw_comparison import (
    build_fluent_lf_taw_comparison,
)
from ref_enthalpy_method.mapping.fluent_wall_temperature import (
    FluentWallTemperatureObservations,
)

_REPO_ROOT = Path(r"E:\navi_clean")


@pytest.fixture(scope="module")
def bundle() -> M8H30ComparisonInputs:
    return build_m8h30_comparison_inputs(_REPO_ROOT)


def _readonly(value: np.ndarray, dtype: np.dtype | type | None = None) -> np.ndarray:
    result = np.array(value, dtype=dtype, copy=True, order="C")
    result.setflags(write=False)
    return result


def test_happy_path_prepares_exact_auditable_inputs(bundle: M8H30ComparisonInputs) -> None:
    assert bundle.observation_binding.raw_sha256 == preparation._CSV_SHA256
    assert bundle.observation_binding.byte_size == preparation._CSV_SIZE
    assert bundle.observation_binding.row_count == preparation._CSV_ROW_COUNT
    assert bundle.candidate_identity.manifest_schema == "tpg-candidate-manifest/v1"
    assert bundle.candidate_identity.status == "unregistered_candidate"
    assert bundle.candidate_identity.case_id == "ma8_a5_h30km"
    assert bundle.candidate_identity.mach == 8.0
    assert bundle.candidate_identity.alpha_deg == 5.0
    assert bundle.candidate_identity.geometric_altitude_m == 30000.0
    assert bundle.candidate_identity.T_inf_K == 226.509
    assert bundle.candidate_identity.p_inf_Pa == 1197.0
    assert bundle.candidate_identity.freestream_provenance == (
        "user-confirmed custom project input"
    )
    assert bundle.candidate_identity.artifact_byte_size == {
        name: identity[0]
        for name, identity in preparation._CANDIDATE_ARTIFACTS.items()
    }
    cache_identity = bundle.projection_cache_identity
    assert cache_identity.raw_sha256 == preparation._CACHE_SHA256
    assert cache_identity.schema == "exact-projection-cache/v1"
    assert cache_identity.algorithm == "n3a.5b-exact-bvh/v1"
    assert cache_identity.fluent_geometry_sha256 == preparation._FLUENT_GEOMETRY_SHA256
    assert cache_identity.canonical_geometry_sha256 == preparation._CANONICAL_GEOMETRY_SHA256
    assert cache_identity.canonical_point_count == preparation._CSV_ROW_COUNT
    assert cache_identity.x_offset_m == preparation._X_OFFSET_M
    assert cache_identity.projection_gate_m == preparation._PROJECTION_GATE_M
    assert cache_identity.coordinate_convention == "solver-(x,span,up)-metres"
    assert cache_identity.tie_break_identity == (
        "smallest-triangle-index-among-equivalent-distances;"
        "tie_abs_tol=1e-12;tie_rel_tol=1e-12"
    )
    for digest in (
        cache_identity.stl_raw_sha256,
        cache_identity.triangle_canonical_sha256,
        cache_identity.vehicle_spec_raw_sha256,
        cache_identity.sampling_spec_raw_sha256,
        cache_identity.outline_geometry_sha256,
    ):
        assert len(digest) == 64
        assert set(digest) <= set("0123456789abcdef")

    assert isinstance(bundle.upper.observation, FluentWallTemperatureObservations)
    assert isinstance(bundle.upper.pairing, FluentLfCleanPairing)
    assert bundle.upper.observation.source_canonical_index.size == 186
    np.testing.assert_array_equal(
        bundle.upper.observation.source_canonical_index,
        bundle.upper.pairing.source_canonical_index,
    )
    assert bundle.upper.prediction_field_name == "Taw_tpg_leeward_upper"
    assert bundle.upper.prediction_field_name in bundle.upper.lf_fields


def test_lower_is_formal_typed_empty_and_strictly_separate(
    bundle: M8H30ComparisonInputs,
) -> None:
    assert bundle.upper.sheet == "upper"
    assert bundle.lower.sheet == "lower"
    assert isinstance(bundle.lower.observation, FluentWallTemperatureObservations)
    assert isinstance(bundle.lower.pairing, FluentLfCleanPairing)
    assert bundle.lower.observation.source_canonical_index.size == 0
    assert bundle.lower.pairing.source_canonical_index.size == 0
    assert bundle.lower.prediction_field_name == "Taw_tpg_leeward_lower"
    assert bundle.lower.prediction_field_name in bundle.lower.lf_fields
    assert bundle.lower.observation is not bundle.upper.observation
    assert bundle.lower.pairing is not bundle.upper.pairing


def test_bundle_exposes_exact_comparison_builder_arguments(
    bundle: M8H30ComparisonInputs,
) -> None:
    signature = {
        "observation": bundle.upper.observation,
        "pairing": bundle.upper.pairing,
        "lf_fields": bundle.upper.lf_fields,
        "lf_masks": bundle.upper.lf_masks,
        "sheet": bundle.upper.sheet,
    }
    assert set(signature) == {"observation", "pairing", "lf_fields", "lf_masks", "sheet"}


def test_preparation_never_calls_production_comparison_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comparison_module = __import__(
        "ref_enthalpy_method.mapping.fluent_lf_taw_comparison",
        fromlist=["build_fluent_lf_taw_comparison"],
    )
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("preparation must not execute comparison")

    monkeypatch.setattr(comparison_module, "build_fluent_lf_taw_comparison", forbidden)
    result = build_m8h30_comparison_inputs(_REPO_ROOT)
    assert isinstance(result, M8H30ComparisonInputs)
    assert calls == 0
    assert build_fluent_lf_taw_comparison is not forbidden


def test_cache_load_is_explicitly_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    original = preparation.project_fluent_surface_with_cache
    observed: list[bool] = []

    def recording(*args: object, **kwargs: object):
        observed.append(kwargs.get("write_cache"))
        return original(*args, **kwargs)

    monkeypatch.setattr(preparation, "project_fluent_surface_with_cache", recording)
    preparation._load_geometry_and_projection(_REPO_ROOT)
    assert observed == [False]


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("raw_sha256", "0" * 64),
        ("byte_size", 1),
        ("header", ("wrong",)),
        ("row_count", 1),
        ("T_inf_K", 226.5),
        ("p_inf_Pa", 1196.0),
        ("freestream_provenance", "standard atmosphere"),
        ("wall_thermal_condition", "isothermal"),
        ("observation_field", "heat-flux"),
        ("observation_unit", "Pa"),
        ("fluent_source_convention", "solver axes"),
        ("solver_transform", "(x, span=y, up=z)"),
    ],
)
def test_binding_and_csv_mismatches_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    replacement: object,
) -> None:
    valid = preparation.build_m8h30_observation_binding(_REPO_ROOT)
    if field in {"T_inf_K", "p_inf_Pa"}:
        identity_field = field
        identity = replace(
            valid.filename_identity,
            **{identity_field: Decimal(str(replacement))},
        )
        with pytest.raises(ValueError, match="filename_identity"):
            replace(valid, filename_identity=identity)
        return

    invalid = replace(valid, **{field: replacement})
    monkeypatch.setattr(preparation, "build_m8h30_observation_binding", lambda *args, **kwargs: invalid)
    with pytest.raises(ValueError, match="observation binding rejected|exact CSV identity"):
        preparation._validate_binding(_REPO_ROOT)


def _patch_candidate_json(
    monkeypatch: pytest.MonkeyPatch,
    *,
    manifest_update=None,
    summary_update=None,
) -> None:
    original_loads = json.loads

    def loads(payload: str):
        value = original_loads(payload)
        if isinstance(value, dict) and "manifest_schema" in value and manifest_update:
            manifest_update(value)
        if isinstance(value, dict) and "inputs" in value and summary_update:
            summary_update(value)
        return value

    monkeypatch.setattr(preparation.json, "loads", loads)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.__setitem__("manifest_schema", "wrong-schema"),
        lambda value: value.__setitem__("admission_status", "admitted"),
        lambda value: value["case"].__setitem__("mach", 7.0),
        lambda value: value["freestream"].__setitem__("source", "atmosphere"),
        lambda value: value["artifact_hashes_sha256"].__setitem__("fields.npz", "0" * 64),
    ],
)
def test_candidate_manifest_mismatches_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    mutate,
) -> None:
    _patch_candidate_json(monkeypatch, manifest_update=mutate)
    with pytest.raises(ValueError, match="candidate"):
        preparation._validate_candidate(_REPO_ROOT)


def test_candidate_summary_custom_freestream_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_candidate_json(
        monkeypatch,
        summary_update=lambda value: value["inputs"].__setitem__("T_inf_K_override", 226.5),
    )
    with pytest.raises(ValueError, match="candidate summary"):
        preparation._validate_candidate(_REPO_ROOT)


@pytest.mark.parametrize("identity_index", [0, 1])
def test_candidate_artifact_size_and_raw_hash_mismatch_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    identity_index: int,
) -> None:
    identities = dict(preparation._CANDIDATE_ARTIFACTS)
    size, sha256 = identities["fields.npz"]
    identities["fields.npz"] = (
        size + 1 if identity_index == 0 else size,
        "0" * 64 if identity_index == 1 else sha256,
    )
    monkeypatch.setattr(preparation, "_CANDIDATE_ARTIFACTS", MappingProxyType(identities))
    with pytest.raises(ValueError, match="candidate fields.npz (size|SHA-256) mismatch"):
        preparation._validate_candidate(_REPO_ROOT)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("_CACHE_SIZE", 1, "size mismatch"),
        ("_CACHE_SHA256", "0" * 64, "SHA-256 mismatch"),
    ],
)
def test_cache_raw_identity_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: object,
    message: str,
) -> None:
    monkeypatch.setattr(preparation, name, value)
    with pytest.raises(ValueError, match=message):
        preparation._load_geometry_and_projection(_REPO_ROOT)


@pytest.mark.parametrize("mode", ["length", "order", "value"])
def test_source_canonical_index_mismatch_fails_closed(
    bundle: M8H30ComparisonInputs,
    mode: str,
) -> None:
    source = bundle.upper.observation.source_canonical_index
    if mode == "length":
        invalid_index = _readonly(source[:-1], np.int64)
    elif mode == "order":
        invalid_index = _readonly(source[::-1], np.int64)
    else:
        invalid_index = _readonly(source, np.int64)
        invalid_index.setflags(write=True)
        invalid_index[0] += 1
        invalid_index.setflags(write=False)
    invalid_observation = replace(
        bundle.upper.observation,
        source_canonical_index=invalid_index,
        source_row_index=_readonly(
            bundle.upper.observation.source_row_index[: invalid_index.size], np.int64
        ),
        wall_temperature_K=_readonly(
            bundle.upper.observation.wall_temperature_K[: invalid_index.size], np.float64
        ),
    )
    with pytest.raises(ValueError, match="source_canonical_index"):
        replace(bundle.upper, observation=invalid_observation)


def test_missing_prediction_field_fails_closed(bundle: M8H30ComparisonInputs) -> None:
    fields = dict(bundle.upper.lf_fields)
    fields.pop("Taw_tpg_leeward_upper")
    assert "Tw_l" in fields
    with pytest.raises(ValueError, match="missing required LF prediction field"):
        FluentLfTawComparisonInputs(
            sheet="upper",
            observation=bundle.upper.observation,
            pairing=bundle.upper.pairing,
            lf_fields=MappingProxyType(fields),
            lf_masks=bundle.upper.lf_masks,
            prediction_field_name="Taw_tpg_leeward_upper",
        )


def test_public_import_surface_is_formal() -> None:
    from ref_enthalpy_method.mapping import (
        FluentLfTawComparisonInputs as PublicSheetInputs,
        M8H30ComparisonInputs as PublicBundle,
        build_m8h30_comparison_inputs as public_builder,
    )

    assert PublicSheetInputs is FluentLfTawComparisonInputs
    assert PublicBundle is M8H30ComparisonInputs
    assert public_builder is build_m8h30_comparison_inputs