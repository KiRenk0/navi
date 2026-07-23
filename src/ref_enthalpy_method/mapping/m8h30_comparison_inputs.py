"""Fail-closed preparation of exact M8/30 Fluent/LF comparison inputs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

import numpy as np

from ref_enthalpy_method.geometry.faceted3d import load_outline_csv
from ref_enthalpy_method.geometry.local_incidence import outward_normal_from_slopes
from ref_enthalpy_method.geometry.projection_cache import (
    ALGORITHM_VERSION,
    CACHE_SCHEMA_VERSION,
    COORDINATE_CONVENTION,
    TIE_BREAK_IDENTITY,
    build_geometry_identity,
)
from ref_enthalpy_method.geometry.stl_surface import AsciiStlMesh
from ref_enthalpy_method.mapping.fluent_clean import (
    FluentCleanLeewardMasks,
    build_fluent_clean_leeward_masks,
)
from ref_enthalpy_method.mapping.fluent_lf_pairing import (
    FluentLfCleanPairing,
    build_fluent_lf_clean_pairing,
)
from ref_enthalpy_method.mapping.fluent_projection import (
    FluentSurfaceProjection,
    project_fluent_surface_with_cache,
)
from ref_enthalpy_method.mapping.fluent_semantics import (
    FluentProjectedSemanticsIntegration,
    integrate_fluent_projected_semantics,
)
from ref_enthalpy_method.mapping.fluent_surface import (
    FluentSurfaceGeometry,
    read_fluent_surface_geometry_csv,
)
from ref_enthalpy_method.mapping.fluent_wall_temperature import (
    FluentWallTemperatureObservations,
    build_fluent_wall_temperature_observations,
)
from ref_enthalpy_method.mapping.lf_clean import (
    LfCleanLeewardMasks,
    build_lf_clean_leeward_masks,
)
from ref_enthalpy_method.mapping.observation_binding import (
    FluentObservationBinding,
    build_m8h30_observation_binding,
    validate_observation_binding,
)

_REPO_ROOT = Path(r"E:\navi_clean")
_CSV_RELATIVE_PATH = "fluent_export/adiabatic_wall_csv/30km_5alpha_8ma.csv"
_CANDIDATE_RELATIVE_PATH = "runs/ma8_a5_h30km_tpg_candidate_20260721"
_CACHE_RELATIVE_PATH = (
    "runs/fluent_projection_cache/"
    "f8e831b08dd86283bb69dc2f5be5fdb636e160a801ce97ec4d9382098b611c23/"
    "projection_cache.npz"
)
_STL_RELATIVE_PATH = "new_spec/htv2_0628.stl"
_OUTLINE_RELATIVE_PATH = "new_spec/outline_xz_right_0629.csv"
_VEHICLE_RELATIVE_PATH = "specs/vehicles/htv2_faceted3d_0629.yaml"
_SAMPLING_RELATIVE_PATH = (
    "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml"
)

_CSV_SHA256 = "5dc84e2dea4dc49a5f6ce777e71b8121c148b9490afeb83c98bd5ce022b3b865"
_CSV_SIZE = 3_123_901
_CSV_HEADER = (
    "cellnumber",
    "    x-coordinate",
    "    y-coordinate",
    "    z-coordinate",
    "absolute-pressure",
    "wall-temperature",
    "          y-plus",
    "       heat-flux",
    "face-area-magnitude",
)
_CSV_ROW_COUNT = 21_250

_CANDIDATE_SCHEMA = "tpg-candidate-manifest/v1"
_CANDIDATE_STATUS = "unregistered_candidate"
_CANDIDATE_ARTIFACTS = MappingProxyType(
    {
        "fields.npz": (473_772, "48cb596ffb3ba09afa459664e4b2d39e6022c7b9b34580eac8aa877dce0abc7c"),
        "lf_warnings.log": (125, "6e66b807e8e01734dcd535d2b76acb738840c47d1d19a11428aabfac1a66e640"),
        "manifest.json": (17_106, "f9a629471a6c68d9311acae161584a8c4673e3c2067b8b58acb6ff9da99da8c6"),
        "summary.json": (2_639_732, "631232780bec5a80b27ab7e126b603d02fff212db0b99d4122bcbd6fbc27e0b4"),
    }
)

_CACHE_SIZE = 786_521
_CACHE_SHA256 = "a82d7d56b01aaae8067cdfa2c3ba439f4d3cc7fcd537c0dedbb573cf4d6be3a7"
_CACHE_SCHEMA = "exact-projection-cache/v1"
_CACHE_ALGORITHM = "n3a.5b-exact-bvh/v1"
_CANONICAL_GEOMETRY_SHA256 = (
    "f8e831b08dd86283bb69dc2f5be5fdb636e160a801ce97ec4d9382098b611c23"
)
_FLUENT_GEOMETRY_SHA256 = (
    "a449b2367c10631eac7161c84393318911e1f21554429a6f69092d2c877b6c0b"
)

_X_OFFSET_M = 0.030
_PROJECTION_GATE_M = 0.005
_PLANFORM_B_HALF_M = 1.031027
_CHORD_MIN_M = 0.02


@dataclass(frozen=True)
class M8H30CandidateIdentity:
    run_path: Path
    manifest_schema: str
    status: str
    case_id: str
    mach: float
    alpha_deg: float
    geometric_altitude_m: float
    T_inf_K: float
    p_inf_Pa: float
    freestream_provenance: str
    artifact_byte_size: Mapping[str, int]
    artifact_sha256: Mapping[str, str]


@dataclass(frozen=True)
class M8H30ProjectionCacheIdentity:
    cache_path: Path
    raw_sha256: str
    byte_size: int
    schema: str
    algorithm: str
    fluent_geometry_sha256: str
    canonical_geometry_sha256: str
    canonical_point_count: int
    x_offset_m: float
    stl_raw_sha256: str
    triangle_canonical_sha256: str
    vehicle_spec_raw_sha256: str
    sampling_spec_raw_sha256: str
    outline_geometry_sha256: str
    projection_gate_m: float
    coordinate_convention: str
    tie_break_identity: str


@dataclass(frozen=True)
class FluentLfTawComparisonInputs:
    sheet: Literal["upper", "lower"]
    observation: FluentWallTemperatureObservations
    pairing: FluentLfCleanPairing
    lf_fields: Mapping[str, np.ndarray]
    lf_masks: LfCleanLeewardMasks
    prediction_field_name: str

    def __post_init__(self) -> None:
        if self.sheet not in ("upper", "lower"):
            raise ValueError("sheet must be exactly 'upper' or 'lower'")
        if self.observation.sheet != self.sheet or self.pairing.sheet != self.sheet:
            raise ValueError("observation and pairing sheet identities must match")
        expected_prediction = f"Taw_tpg_leeward_{self.sheet}"
        if self.prediction_field_name != expected_prediction:
            raise ValueError(f"prediction_field_name must be exactly {expected_prediction!r}")
        if expected_prediction not in self.lf_fields:
            raise ValueError(f"missing required LF prediction field: {expected_prediction}")

        observation_index = np.asarray(self.observation.source_canonical_index)
        pairing_index = np.asarray(self.pairing.source_canonical_index)
        if observation_index.shape != pairing_index.shape:
            raise ValueError("observation and pairing source_canonical_index shapes differ")
        if not np.array_equal(observation_index, pairing_index):
            raise ValueError("observation and pairing source_canonical_index identities differ")

        prediction = np.asarray(self.lf_fields[expected_prediction])
        target_domain = np.asarray(self.lf_masks.clean_leeward_any).size
        if prediction.dtype != np.dtype(np.float64) or prediction.shape != (target_domain,):
            raise ValueError(
                f"{expected_prediction} must have dtype float64 and shape ({target_domain},)"
            )
        target_index = np.asarray(self.pairing.target_canonical_index)
        if target_index.dtype != np.dtype(np.int64) or target_index.ndim != 1:
            raise ValueError("pairing target_canonical_index must have shape (N,) and dtype int64")
        if target_index.size and (
            np.any(target_index < 0) or np.any(target_index >= target_domain)
        ):
            raise ValueError("pairing target_canonical_index is outside the LF domain")
        selected_prediction = prediction[target_index]
        if not np.all(np.isfinite(selected_prediction)) or np.any(selected_prediction <= 0.0):
            raise ValueError(
                f"selected {expected_prediction} must contain finite positive K values"
            )


@dataclass(frozen=True)
class M8H30ComparisonInputs:
    observation_binding: FluentObservationBinding
    candidate_identity: M8H30CandidateIdentity
    projection_cache_identity: M8H30ProjectionCacheIdentity
    geometry: FluentSurfaceGeometry
    projection: FluentSurfaceProjection
    integration: FluentProjectedSemanticsIntegration
    fluent_masks: FluentCleanLeewardMasks
    upper: FluentLfTawComparisonInputs
    lower: FluentLfTawComparisonInputs

    def __post_init__(self) -> None:
        if self.upper.sheet != "upper" or self.lower.sheet != "lower":
            raise ValueError("upper/lower comparison inputs are not strictly separated")
        if self.upper.observation.source_canonical_index.size == 0:
            raise ValueError("M8/30 upper comparison inputs must be nonempty")
        if self.lower.observation.source_canonical_index.size != 0:
            raise ValueError("M8/30 lower comparison inputs must be typed-empty")
        if self.lower.pairing.source_canonical_index.size != 0:
            raise ValueError("M8/30 lower pairing must be typed-empty")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_exact_file(path: Path, *, size: int, sha256: str, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    actual_size = path.stat().st_size
    if actual_size != size:
        raise ValueError(f"{label} size mismatch: expected {size}, got {actual_size}")
    actual_sha256 = _sha256_file(path)
    if actual_sha256 != sha256:
        raise ValueError(
            f"{label} SHA-256 mismatch: expected {sha256}, got {actual_sha256}"
        )


def _require_exact_repo_root(repo_root: str | Path) -> Path:
    root = Path(repo_root).resolve()
    if root != _REPO_ROOT.resolve():
        raise ValueError(f"repo_root must be exactly {_REPO_ROOT.resolve()}, got {root}")
    return root


def _validate_binding(root: Path) -> FluentObservationBinding:
    binding = build_m8h30_observation_binding(root, csv_path=_CSV_RELATIVE_PATH)
    passed, reason = validate_observation_binding(binding, repo_root=root)
    if not passed:
        raise ValueError(f"M8/30 observation binding rejected: {reason}")
    if (
        binding.csv_path != _CSV_RELATIVE_PATH
        or binding.raw_sha256 != _CSV_SHA256
        or binding.byte_size != _CSV_SIZE
        or binding.header != _CSV_HEADER
        or binding.row_count != _CSV_ROW_COUNT
    ):
        raise ValueError("M8/30 observation binding does not match the exact CSV identity")
    return binding


def _require_mapping(value: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"candidate manifest {name} must be an object")
    return value


def _validate_candidate(root: Path) -> tuple[M8H30CandidateIdentity, Mapping[str, np.ndarray]]:
    run_path = (root / _CANDIDATE_RELATIVE_PATH).resolve()
    if run_path != (_REPO_ROOT / _CANDIDATE_RELATIVE_PATH).resolve():
        raise ValueError("candidate path identity mismatch")

    artifact_hashes: dict[str, str] = {}
    artifact_sizes: dict[str, int] = {}
    for name, (size, sha256) in _CANDIDATE_ARTIFACTS.items():
        artifact_path = run_path / name
        _require_exact_file(
            artifact_path,
            size=size,
            sha256=sha256,
            label=f"candidate {name}",
        )
        artifact_sizes[name] = size
        artifact_hashes[name] = sha256

    try:
        manifest = json.loads((run_path / "manifest.json").read_text(encoding="utf-8"))
        summary = json.loads((run_path / "summary.json").read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("candidate JSON is not valid UTF-8 JSON") from error
    manifest = _require_mapping(manifest, name="root")
    summary = _require_mapping(summary, name="summary")

    expected_case = {
        "mach": 8.0,
        "alpha_deg": 5.0,
        "geometric_altitude_m": 30000.0,
    }
    if manifest.get("manifest_schema") != _CANDIDATE_SCHEMA:
        raise ValueError("candidate manifest schema mismatch")
    if manifest.get("admission_status") != _CANDIDATE_STATUS:
        raise ValueError("candidate status must remain unregistered_candidate")
    if manifest.get("case_id") != "ma8_a5_h30km" or manifest.get("case") != expected_case:
        raise ValueError("candidate M8/30 case identity mismatch")

    freestream = _require_mapping(manifest.get("freestream"), name="freestream")
    atmosphere = _require_mapping(manifest.get("atmosphere"), name="atmosphere")
    if (
        freestream.get("actual_T_inf_K") != 226.509
        or freestream.get("actual_p_inf_Pa") != 1197.0
        or freestream.get("source") != "explicit_override"
        or atmosphere.get("explicit_freestream_override") is not True
    ):
        raise ValueError("candidate custom freestream identity mismatch")

    manifest_artifacts = _require_mapping(
        manifest.get("artifact_hashes_sha256"), name="artifact_hashes_sha256"
    )
    for name in ("fields.npz", "summary.json"):
        if manifest_artifacts.get(name) != artifact_hashes[name]:
            raise ValueError(f"candidate manifest artifact hash mismatch: {name}")

    inputs = _require_mapping(summary.get("inputs"), name="summary.inputs")
    summary_freestream = _require_mapping(
        summary.get("freestream"), name="summary.freestream"
    )
    if (
        inputs.get("mach") != 8.0
        or inputs.get("alpha_deg") != 5.0
        or inputs.get("h_m_override") != 30000.0
        or inputs.get("T_inf_K_override") != 226.509
        or inputs.get("p_inf_Pa_override") != 1197.0
        or summary_freestream.get("T_inf_K") != 226.509
        or summary_freestream.get("p_inf_Pa") != 1197.0
        or summary_freestream.get("freestream_source") != "explicit_override"
    ):
        raise ValueError("candidate summary M8/30 custom freestream identity mismatch")

    fields_path = run_path / "fields.npz"
    try:
        with np.load(fields_path, allow_pickle=False) as archive:
            fields = {
                name: _readonly_array(archive[name])
                for name in archive.files
            }
    except (OSError, ValueError) as error:
        raise ValueError("candidate fields.npz failed safe loading") from error

    identity = M8H30CandidateIdentity(
        run_path=run_path,
        manifest_schema=_CANDIDATE_SCHEMA,
        status=_CANDIDATE_STATUS,
        case_id="ma8_a5_h30km",
        mach=8.0,
        alpha_deg=5.0,
        geometric_altitude_m=30000.0,
        T_inf_K=226.509,
        p_inf_Pa=1197.0,
        freestream_provenance="user-confirmed custom project input",
        artifact_byte_size=MappingProxyType(artifact_sizes),
        artifact_sha256=MappingProxyType(artifact_hashes),
    )
    return identity, MappingProxyType(fields)


def _readonly_array(value: np.ndarray) -> np.ndarray:
    result = np.array(value, copy=True, order="C")
    result.setflags(write=False)
    return result


def _load_geometry_and_projection(
    root: Path,
) -> tuple[
    M8H30ProjectionCacheIdentity,
    FluentSurfaceGeometry,
    FluentSurfaceProjection,
    np.ndarray,
]:
    csv_path = (root / _CSV_RELATIVE_PATH).resolve()
    cache_path = (root / _CACHE_RELATIVE_PATH).resolve()
    _require_exact_file(
        cache_path,
        size=_CACHE_SIZE,
        sha256=_CACHE_SHA256,
        label="exact projection cache",
    )

    geometry = read_fluent_surface_geometry_csv(csv_path, x_offset_m=_X_OFFSET_M)
    if (
        geometry.source_sha256 != _CSV_SHA256
        or geometry.canonical_solver_xyz.shape != (_CSV_ROW_COUNT, 3)
    ):
        raise ValueError("Fluent CSV geometry provenance identity mismatch")

    mesh = AsciiStlMesh.load(
        stl_path=root / _STL_RELATIVE_PATH,
        unit="mm",
        span_sign=-1.0,
        right_half_only=True,
    )
    triangles = np.ascontiguousarray(
        np.stack([mesh.v0, mesh.v1, mesh.v2], axis=1), dtype=np.float64
    )
    geometry_identity_kwargs = {
        "x_offset_m": _X_OFFSET_M,
        "stl_path": root / _STL_RELATIVE_PATH,
        "vehicle_spec_path": root / _VEHICLE_RELATIVE_PATH,
        "sampling_spec_path": root / _SAMPLING_RELATIVE_PATH,
        "outline_path": root / _OUTLINE_RELATIVE_PATH,
    }
    projection = project_fluent_surface_with_cache(
        geometry,
        triangles,
        projection_gate_m=_PROJECTION_GATE_M,
        use_bvh=True,
        cache_path=cache_path,
        write_cache=False,
        geometry_identity_kwargs=geometry_identity_kwargs,
    )
    if projection.canonical_geometry_sha256 != _CANONICAL_GEOMETRY_SHA256:
        raise ValueError("exact projection cache canonical geometry identity mismatch")

    geometry_identity = build_geometry_identity(
        fluent_geometry_source_path=csv_path,
        fluent_canonical_geometry_sha256=projection.canonical_geometry_sha256,
        canonical_point_count=geometry.canonical_solver_xyz.shape[0],
        triangles=triangles,
        projection_gate_m=_PROJECTION_GATE_M,
        **geometry_identity_kwargs,
    )
    if (
        CACHE_SCHEMA_VERSION != _CACHE_SCHEMA
        or ALGORITHM_VERSION != _CACHE_ALGORITHM
        or geometry_identity["fluent_source_geometry_sha256"]
        != _FLUENT_GEOMETRY_SHA256
        or geometry_identity["fluent_canonical_geometry_sha256"]
        != _CANONICAL_GEOMETRY_SHA256
    ):
        raise ValueError("exact projection cache formal identity mismatch")
    identity = M8H30ProjectionCacheIdentity(
        cache_path=cache_path,
        raw_sha256=_CACHE_SHA256,
        byte_size=_CACHE_SIZE,
        schema=CACHE_SCHEMA_VERSION,
        algorithm=ALGORITHM_VERSION,
        fluent_geometry_sha256=str(
            geometry_identity["fluent_source_geometry_sha256"]
        ),
        canonical_geometry_sha256=str(
            geometry_identity["fluent_canonical_geometry_sha256"]
        ),
        canonical_point_count=int(geometry_identity["canonical_point_count"]),
        x_offset_m=float(geometry_identity["x_offset_m"]),
        stl_raw_sha256=str(geometry_identity["stl_raw_sha256"]),
        triangle_canonical_sha256=str(
            geometry_identity["triangle_canonical_sha256"]
        ),
        vehicle_spec_raw_sha256=str(
            geometry_identity["vehicle_spec_raw_sha256"]
        ),
        sampling_spec_raw_sha256=str(
            geometry_identity["sampling_spec_raw_sha256"]
        ),
        outline_geometry_sha256=str(
            geometry_identity["outline_geometry_sha256"]
        ),
        projection_gate_m=float(geometry_identity["projection_gate_m"]),
        coordinate_convention=COORDINATE_CONVENTION,
        tie_break_identity=TIE_BREAK_IDENTITY,
    )
    return identity, geometry, projection, triangles


def _build_integration(
    root: Path,
    geometry: FluentSurfaceGeometry,
    projection: FluentSurfaceProjection,
    triangles: np.ndarray,
) -> FluentProjectedSemanticsIntegration:
    outline_x_m, outline_span_m = load_outline_csv(
        csv_path=root / _OUTLINE_RELATIVE_PATH,
        x_col="x_m",
        span_col="z_m",
        span_sign=-1.0,
    )
    upper_reference = outward_normal_from_slopes(
        sx=np.asarray(0.17632698070846498),
        sy=np.asarray(-0.5426786456862612),
        sheet="upper",
    )
    lower_reference = outward_normal_from_slopes(
        sx=np.asarray(-0.05240777928304121),
        sy=np.asarray(0.16129455951933025),
        sheet="lower",
    )
    return integrate_fluent_projected_semantics(
        geometry=geometry,
        projection=projection,
        triangles=triangles,
        alpha_deg=5.0,
        planform_b_half_m=_PLANFORM_B_HALF_M,
        chord_min_m=_CHORD_MIN_M,
        upper_reference_normal_out=upper_reference,
        lower_reference_normal_out=lower_reference,
        outline_x_m=outline_x_m,
        outline_span_m=outline_span_m,
    )


def _build_sheet_inputs(
    *,
    csv_path: Path,
    integration: FluentProjectedSemanticsIntegration,
    fluent_masks: FluentCleanLeewardMasks,
    lf_fields: Mapping[str, np.ndarray],
    lf_masks: LfCleanLeewardMasks,
    sheet: Literal["upper", "lower"],
) -> FluentLfTawComparisonInputs:
    pairing = build_fluent_lf_clean_pairing(
        integration=integration,
        fluent_masks=fluent_masks,
        lf_fields=lf_fields,
        lf_masks=lf_masks,
        sheet=sheet,
    )
    observation = build_fluent_wall_temperature_observations(
        csv_path=csv_path,
        integration=integration,
        fluent_masks=fluent_masks,
        pairing=pairing,
        sheet=sheet,
    )
    return FluentLfTawComparisonInputs(
        sheet=sheet,
        observation=observation,
        pairing=pairing,
        lf_fields=lf_fields,
        lf_masks=lf_masks,
        prediction_field_name=f"Taw_tpg_leeward_{sheet}",
    )


def build_m8h30_comparison_inputs(
    repo_root: str | Path = _REPO_ROOT,
) -> M8H30ComparisonInputs:
    """Prepare exact M8/30 inputs without running comparison or writing assets."""
    root = _require_exact_repo_root(repo_root)
    binding = _validate_binding(root)
    candidate_identity, lf_fields = _validate_candidate(root)
    cache_identity, geometry, projection, triangles = _load_geometry_and_projection(root)
    integration = _build_integration(root, geometry, projection, triangles)
    fluent_masks = build_fluent_clean_leeward_masks(integration)
    lf_masks = build_lf_clean_leeward_masks(lf_fields)
    csv_path = root / _CSV_RELATIVE_PATH

    upper = _build_sheet_inputs(
        csv_path=csv_path,
        integration=integration,
        fluent_masks=fluent_masks,
        lf_fields=lf_fields,
        lf_masks=lf_masks,
        sheet="upper",
    )
    lower = _build_sheet_inputs(
        csv_path=csv_path,
        integration=integration,
        fluent_masks=fluent_masks,
        lf_fields=lf_fields,
        lf_masks=lf_masks,
        sheet="lower",
    )
    return M8H30ComparisonInputs(
        observation_binding=binding,
        candidate_identity=candidate_identity,
        projection_cache_identity=cache_identity,
        geometry=geometry,
        projection=projection,
        integration=integration,
        fluent_masks=fluent_masks,
        upper=upper,
        lower=lower,
    )