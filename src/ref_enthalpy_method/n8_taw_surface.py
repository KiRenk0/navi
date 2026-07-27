"""N8 Taw-only single-case pipeline for geometric upper/lower surfaces."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import numpy as np
import yaml

from ref_enthalpy_method.aero.leeward_recovery import build_freestream_recovery
from ref_enthalpy_method.aero.windward_cache_faceted3d import (
    build_windward_edge_cache_faceted3d,
)
from ref_enthalpy_method.atmosphere.ussa1976 import ussa1976
from ref_enthalpy_method.config.lf_qw import (
    LfQwConfig,
    PhiClampConfig,
    StagnationConfig,
    TransitionBlendConfig,
    XModelConfig,
)
from ref_enthalpy_method.gas.thermo import make_fluent_tpg_thermo
from ref_enthalpy_method.gas.transport import mu_sutherland
from ref_enthalpy_method.geometry.faceted3d import (
    Faceted3DConfig,
    load_outline_csv,
    outline_planform_xle_chord,
)
from ref_enthalpy_method.geometry.local_incidence import (
    INCIDENCE_EPSILON,
    SURFACE_CLASS_INVALID,
    SURFACE_CLASS_LEEWARD,
    SURFACE_CLASS_NEAR_TANGENT,
    SURFACE_CLASS_WINDWARD,
    classify_incidence,
    orient_outward_normal,
    outward_normal_from_slopes,
)
from ref_enthalpy_method.geometry.n8_domain_topology import (
    N8DomainTopology,
    build_n8_domain_topology,
)
from ref_enthalpy_method.geometry.projected_semantics import (
    GEOMETRIC_SHEET_LOWER,
    GEOMETRIC_SHEET_UPPER,
    classify_triangle_geometric_sheets,
)
from ref_enthalpy_method.geometry.projection_cache import (
    ALGORITHM_VERSION as PROJECTION_ALGORITHM_VERSION,
)
from ref_enthalpy_method.geometry.projection_cache import (
    CACHE_SCHEMA_VERSION as PROJECTION_CACHE_SCHEMA,
)
from ref_enthalpy_method.geometry.projection_cache import (
    build_geometry_identity,
)
from ref_enthalpy_method.geometry.stl_surface import (
    AsciiStlMesh,
    ContinuousStlNormalField,
    SurfaceSlopeSampler,
)
from ref_enthalpy_method.mapping.fluent_projection import (
    project_fluent_surface_with_cache,
)
from ref_enthalpy_method.mapping.fluent_semantics import (
    integrate_fluent_projected_semantics,
    semantic_valid_mask,
)
from ref_enthalpy_method.mapping.fluent_surface import read_fluent_surface_geometry_csv
from ref_enthalpy_method.mapping.fluent_wall_temperature import (
    read_fluent_wall_temperature_source,
)
from ref_enthalpy_method.mapping.observation_binding import (
    build_observation_binding,
    require_exact_freestream_pair,
    validate_observation_binding,
)
from ref_enthalpy_method.types import GasModel

_CASE_SCHEMA = "n8-taw-case/v1"
_SAMPLING_SCHEMA = "n8-taw-sampling/v1"
_SUMMARY_SCHEMA = "n8-taw-run-summary/v4"
_STATS_SCHEMA = "n8-taw-error-stats/v1"
_EXPECTED_ARTIFACTS = (
    "summary.json",
    "Taw_surface_fields.npz",
    "Taw_error_stats.json",
    "Taw_surface_upper.png",
    "Taw_surface_lower.png",
    "Taw_provider_upper.png",
    "Taw_provider_lower.png",
    "Taw_validity_upper.png",
    "Taw_validity_lower.png",
    "Taw_error_vs_fluent_upper.png",
    "Taw_error_vs_fluent_lower.png",
    "Taw_error_vs_fluent_upper_auto_range.png",
    "Taw_error_vs_fluent_lower_auto_range.png",
)
_SHEETS = ("upper", "lower")
_DISPATCH_SCHEMA = "n8-taw-dispatch/v3"
_TOPOLOGY_SCHEMA = "n8-taw-domain-topology/v1"
_NORMAL_MODEL_SCHEMA = "stl-angle-weighted-continuous-normal/v1"
_NORMAL_CREASE_ANGLE_DEG = 20.0
_MAPPING_UNSUPPORTED = "MAPPING_UNSUPPORTED"


@dataclass(frozen=True)
class N8TawCaseSpec:
    case_id: str
    observation_csv: str
    mach: float
    alpha_deg: float
    T_inf_K: float
    p_inf_Pa: float
    h_label_km: float
    gamma: float
    R_J_per_kgK: float
    prandtl: float
    vehicle_spec: str
    fluent_x_offset_m: float
    projection_gate_m: float
    sampling_spec: str
    signed_relative_error_limit_pct: float


@dataclass(frozen=True)
class N8SamplingSpec:
    x_start: float
    x_end: float
    nx: int
    y_start: float
    y_end: float
    ny: int
    point_order: str


@dataclass(frozen=True)
class N8Pairing:
    sheet: Literal["upper", "lower"]
    source_canonical_index: np.ndarray
    target_canonical_index: np.ndarray
    distance_m: np.ndarray
    target_multiplicity: np.ndarray
    second_target_canonical_index: np.ndarray
    second_distance_m: np.ndarray
    mutual_nearest: np.ndarray
    support_limit_m: np.ndarray
    mapping_supported: np.ndarray
    target_pool_size: int


@dataclass(frozen=True)
class N8SheetComparison:
    sheet: Literal["upper", "lower"]
    source_csv_sha256: str
    source_canonical_index: np.ndarray
    source_row_index: np.ndarray
    source_surface_class: np.ndarray
    target_canonical_index: np.ndarray
    target_surface_class: np.ndarray
    pairing_distance_m: np.ndarray
    mapping_support_limit_m: np.ndarray
    comparison_valid: np.ndarray
    comparison_failure_reason: np.ndarray
    target_multiplicity: np.ndarray
    wall_temperature_K: np.ndarray
    Taw_prediction_K: np.ndarray
    signed_error_K: np.ndarray
    signed_relative_error_pct: np.ndarray
    absolute_error_K: np.ndarray
    absolute_relative_error_pct: np.ndarray


@dataclass(frozen=True)
class N8RunResult:
    run_dir: Path
    summary: Mapping[str, Any]


@dataclass(frozen=True)
class N8Freestream:
    source: Literal["explicit_custom", "ussa1976"]
    T_inf_K: float
    p_inf_Pa: float
    rho_inf_kg_m3: float
    altitude_input_m: float | None
    altitude_used_for_freestream: bool


@dataclass(frozen=True)
class _GeometryInputs:
    f3: Faceted3DConfig
    b_half_m: float
    c_root_m: float
    sweep_le_deg: float
    outline_x_m: np.ndarray
    outline_span_m: np.ndarray
    mesh: AsciiStlMesh
    vehicle_spec_path: Path
    sampling_spec_path: Path
    outline_path: Path
    stl_path: Path
    triangles: np.ndarray
    upper_reference_normal: np.ndarray
    lower_reference_normal: np.ndarray


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(
            f"{label} fields must be exactly {sorted(expected)}; "
            f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )


def _finite(value: Any, *, label: str, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{label} must be a finite number")
    result = float(value)
    if not np.isfinite(result) or (positive and result <= 0.0):
        qualifier = " greater than zero" if positive else ""
        raise ValueError(f"{label} must be finite{qualifier}")
    return result


def _positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{label} must be a positive integer")
    result = int(value)
    if result <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return result


def resolve_n8_freestream(
    *,
    h_m: float | None,
    T_inf_K: float | None,
    p_inf_Pa: float | None,
    R_J_per_kgK: float,
) -> N8Freestream:
    """Resolve N8 freestream with paired custom values taking precedence."""
    R = _finite(R_J_per_kgK, label="R_J_per_kgK", positive=True)
    if (T_inf_K is None) != (p_inf_Pa is None):
        raise ValueError(
            "T_inf_K and p_inf_Pa must be provided together or both omitted"
        )

    altitude_m = None
    if h_m is not None:
        altitude_m = _finite(h_m, label="h_m")
        if altitude_m < 0.0:
            raise ValueError("h_m must be nonnegative")

    if T_inf_K is not None and p_inf_Pa is not None:
        T_K = _finite(T_inf_K, label="T_inf_K", positive=True)
        p_Pa = _finite(p_inf_Pa, label="p_inf_Pa", positive=True)
        return N8Freestream(
            source="explicit_custom",
            T_inf_K=T_K,
            p_inf_Pa=p_Pa,
            rho_inf_kg_m3=float(p_Pa / (R * T_K)),
            altitude_input_m=altitude_m,
            altitude_used_for_freestream=False,
        )

    if altitude_m is None:
        raise ValueError(
            "provide either h_m for USSA1976 or the paired T_inf_K/p_inf_Pa override"
        )
    atmosphere = ussa1976(altitude_m, R=R)
    return N8Freestream(
        source="ussa1976",
        T_inf_K=float(atmosphere.T),
        p_inf_Pa=float(atmosphere.p),
        rho_inf_kg_m3=float(atmosphere.rho),
        altitude_input_m=altitude_m,
        altitude_used_for_freestream=True,
    )


def _load_yaml(path: Path) -> Mapping[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f"failed to load YAML: {path}") from error
    return _mapping(value, label=str(path))


def _repo_path(repo_root: Path, relative: str, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"{label} must be a nonempty repo-relative POSIX path")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"{label} must stay inside the repository")
    result = (repo_root / Path(*pure.parts)).resolve()
    try:
        result.relative_to(repo_root)
    except ValueError as error:
        raise ValueError(f"{label} escapes the repository") from error
    return result


def load_n8_taw_case_spec(path: str | Path, *, repo_root: str | Path) -> N8TawCaseSpec:
    root = Path(repo_root).resolve()
    spec_path = Path(path)
    if not spec_path.is_absolute():
        spec_path = _repo_path(root, spec_path.as_posix(), label="case spec path")
    raw = _load_yaml(spec_path)
    _exact_keys(
        raw,
        {"schema", "case", "gas", "geometry", "sampling", "plot"},
        label="N8 case root",
    )
    if raw["schema"] != _CASE_SCHEMA:
        raise ValueError(f"N8 case schema must be exactly {_CASE_SCHEMA!r}")

    case = _mapping(raw["case"], label="case")
    gas = _mapping(raw["gas"], label="gas")
    geometry = _mapping(raw["geometry"], label="geometry")
    sampling = _mapping(raw["sampling"], label="sampling")
    plot = _mapping(raw["plot"], label="plot")
    _exact_keys(
        case,
        {
            "case_id",
            "observation_csv",
            "mach",
            "alpha_deg",
            "T_inf_K",
            "p_inf_Pa",
            "h_label_km",
        },
        label="case",
    )
    _exact_keys(gas, {"gamma", "R_J_per_kgK", "prandtl"}, label="gas")
    _exact_keys(
        geometry,
        {"vehicle_spec", "fluent_x_offset_m", "projection_gate_m"},
        label="geometry",
    )
    _exact_keys(sampling, {"spec"}, label="sampling")
    _exact_keys(plot, {"signed_relative_error_limit_pct"}, label="plot")

    result = N8TawCaseSpec(
        case_id=str(case["case_id"]),
        observation_csv=str(case["observation_csv"]),
        mach=_finite(case["mach"], label="case.mach", positive=True),
        alpha_deg=_finite(case["alpha_deg"], label="case.alpha_deg"),
        T_inf_K=_finite(case["T_inf_K"], label="case.T_inf_K", positive=True),
        p_inf_Pa=_finite(case["p_inf_Pa"], label="case.p_inf_Pa", positive=True),
        h_label_km=_finite(case["h_label_km"], label="case.h_label_km"),
        gamma=_finite(gas["gamma"], label="gas.gamma", positive=True),
        R_J_per_kgK=_finite(gas["R_J_per_kgK"], label="gas.R_J_per_kgK", positive=True),
        prandtl=_finite(gas["prandtl"], label="gas.prandtl", positive=True),
        vehicle_spec=str(geometry["vehicle_spec"]),
        fluent_x_offset_m=_finite(
            geometry["fluent_x_offset_m"], label="geometry.fluent_x_offset_m"
        ),
        projection_gate_m=_finite(
            geometry["projection_gate_m"],
            label="geometry.projection_gate_m",
            positive=True,
        ),
        sampling_spec=str(sampling["spec"]),
        signed_relative_error_limit_pct=_finite(
            plot["signed_relative_error_limit_pct"],
            label="plot.signed_relative_error_limit_pct",
            positive=True,
        ),
    )
    if not result.case_id or result.h_label_km < 0.0:
        raise ValueError("case_id must be nonempty and h_label_km must be nonnegative")
    _repo_path(root, result.observation_csv, label="case.observation_csv")
    _repo_path(root, result.vehicle_spec, label="geometry.vehicle_spec")
    _repo_path(root, result.sampling_spec, label="sampling.spec")
    return result


def load_n8_sampling_spec(path: str | Path, *, repo_root: str | Path) -> N8SamplingSpec:
    root = Path(repo_root).resolve()
    spec_path = Path(path)
    if not spec_path.is_absolute():
        spec_path = _repo_path(root, spec_path.as_posix(), label="sampling spec path")
    raw = _load_yaml(spec_path)
    _exact_keys(raw, {"schema", "sampling"}, label="N8 sampling root")
    if raw["schema"] != _SAMPLING_SCHEMA:
        raise ValueError(f"N8 sampling schema must be exactly {_SAMPLING_SCHEMA!r}")
    sampling = _mapping(raw["sampling"], label="sampling")
    _exact_keys(sampling, {"x_over_c", "y_over_b", "point_order"}, label="sampling")
    x = _mapping(sampling["x_over_c"], label="sampling.x_over_c")
    y = _mapping(sampling["y_over_b"], label="sampling.y_over_b")
    _exact_keys(x, {"start", "end", "count"}, label="sampling.x_over_c")
    _exact_keys(y, {"start", "end", "count"}, label="sampling.y_over_b")
    result = N8SamplingSpec(
        x_start=_finite(x["start"], label="sampling.x_over_c.start"),
        x_end=_finite(x["end"], label="sampling.x_over_c.end"),
        nx=_positive_int(x["count"], label="sampling.x_over_c.count"),
        y_start=_finite(y["start"], label="sampling.y_over_b.start"),
        y_end=_finite(y["end"], label="sampling.y_over_b.end"),
        ny=_positive_int(y["count"], label="sampling.y_over_b.count"),
        point_order=str(sampling["point_order"]),
    )
    if not (
        0.0 <= result.x_start < result.x_end <= 1.0
        and 0.0 <= result.y_start < result.y_end <= 1.0
        and result.nx >= 2
        and result.ny >= 2
        and result.point_order == "sheet_then_y_over_b_then_x_over_c"
    ):
        raise ValueError("N8 sampling grid or point_order is invalid")
    return result


def _load_geometry_inputs(repo_root: Path, case: N8TawCaseSpec) -> _GeometryInputs:
    vehicle_path = _repo_path(
        repo_root, case.vehicle_spec, label="geometry.vehicle_spec"
    )
    raw = _load_yaml(vehicle_path)
    vehicle = _mapping(raw.get("vehicle_spec"), label="vehicle_spec")
    planform = _mapping(vehicle.get("planform"), label="vehicle_spec.planform")
    faceted = _mapping(vehicle.get("faceted3d"), label="vehicle_spec.faceted3d")
    f3 = Faceted3DConfig.from_faceted3d_spec(dict(faceted))
    if not f3.outline_csv_path or not f3.surface_stl_path:
        raise ValueError("N8 geometry requires explicit outline CSV and STL")
    outline_path = (vehicle_path.parent / f3.outline_csv_path).resolve()
    stl_path = (vehicle_path.parent / f3.surface_stl_path).resolve()
    for value, label in ((outline_path, "outline"), (stl_path, "STL")):
        try:
            value.relative_to(repo_root)
        except ValueError as error:
            raise ValueError(f"{label} path escapes repository") from error
    outline_x, outline_span = load_outline_csv(
        csv_path=outline_path,
        x_col=f3.outline_x_col,
        span_col=f3.outline_span_col,
        span_sign=f3.outline_span_sign,
    )
    outline_span = np.abs(np.asarray(outline_span, dtype=np.float64))
    b_half = float(np.max(outline_span))
    expected_b_half = _finite(
        planform.get("b_half_m"), label="vehicle planform.b_half_m", positive=True
    )
    if abs(b_half - expected_b_half) / expected_b_half > 0.05:
        raise ValueError(
            "outline and vehicle half-span identities differ by more than 5 percent"
        )
    mesh = AsciiStlMesh.load(
        stl_path=stl_path,
        unit=f3.stl_unit,
        span_sign=f3.stl_span_sign,
        right_half_only=f3.stl_right_half_only,
    )
    triangles = np.ascontiguousarray(
        np.stack([mesh.v0, mesh.v1, mesh.v2], axis=1), dtype=np.float64
    )
    sx_up, sy_up, sx_lo, sy_lo = f3.slopes()
    return _GeometryInputs(
        f3=f3,
        b_half_m=b_half,
        c_root_m=_finite(
            planform.get("c_root_m"), label="vehicle planform.c_root_m", positive=True
        ),
        sweep_le_deg=_finite(
            planform.get("sweep_le_deg"), label="vehicle planform.sweep_le_deg"
        ),
        outline_x_m=np.asarray(outline_x, dtype=np.float64),
        outline_span_m=outline_span,
        vehicle_spec_path=vehicle_path,
        sampling_spec_path=_repo_path(
            repo_root, case.sampling_spec, label="sampling.spec"
        ),
        outline_path=outline_path,
        stl_path=stl_path,
        mesh=mesh,
        triangles=triangles,
        upper_reference_normal=np.asarray(
            outward_normal_from_slopes(
                sx=np.asarray(sx_up), sy=np.asarray(sy_up), sheet="upper"
            ),
            dtype=np.float64,
        ),
        lower_reference_normal=np.asarray(
            outward_normal_from_slopes(
                sx=np.asarray(sx_lo), sy=np.asarray(sy_lo), sheet="lower"
            ),
            dtype=np.float64,
        ),
    )


def _gas_model(case: N8TawCaseSpec) -> GasModel:
    tpg = make_fluent_tpg_thermo(R=case.R_J_per_kgK)
    return GasModel(
        gamma=case.gamma,
        R=case.R_J_per_kgK,
        cp_gas=tpg.cp,
        h_from_T=tpg.h_from_T,
        T_from_h=tpg.T_from_h,
        mu=mu_sutherland,
        tpg=tpg,
        prandtl=case.prandtl,
    )


def _surface_class_names(codes: np.ndarray) -> np.ndarray:
    result = np.full(np.asarray(codes).shape, "invalid", dtype="<U12")
    result[np.asarray(codes) == SURFACE_CLASS_WINDWARD] = "windward"
    result[np.asarray(codes) == SURFACE_CLASS_LEEWARD] = "leeward"
    result[np.asarray(codes) == SURFACE_CLASS_NEAR_TANGENT] = "near_tangent"
    return result


def dispatch_taw_predictions(
    *,
    incidence_s: np.ndarray,
    geometry_valid: np.ndarray,
    windward_taw_K: np.ndarray,
    recovery_taw_K: np.ndarray,
    gas: GasModel,
    transition_epsilon: float = INCIDENCE_EPSILON,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Continuously dispatch Taw from recovery to the windward edge model.

    Negative and zero incidence use the freestream-recovery limit.  Positive
    near-tangent incidence transitions in enthalpy space with a C1 smoothstep;
    pure windward routing starts at the diagnostic incidence epsilon.
    """

    incidence = np.asarray(incidence_s, dtype=np.float64)
    geometry = np.asarray(geometry_valid, dtype=np.bool_)
    windward = np.asarray(windward_taw_K, dtype=np.float64)
    recovery = np.asarray(recovery_taw_K, dtype=np.float64)
    if not (incidence.shape == geometry.shape == windward.shape == recovery.shape):
        raise ValueError("Taw dispatch arrays must have identical shapes")
    epsilon = float(transition_epsilon)
    if not np.isfinite(epsilon) or epsilon <= 0.0:
        raise ValueError("transition_epsilon must be finite and positive")
    if not callable(gas.h_from_T) or not callable(gas.T_from_h):
        raise TypeError("gas enthalpy conversion functions must be callable")

    prediction = np.full(incidence.shape, np.nan, dtype=np.float64)
    provider = np.full(incidence.shape, "typed_invalid", dtype="<U24")
    valid = np.zeros(incidence.shape, dtype=np.bool_)
    reason = np.full(incidence.shape, "invalid_geometry", dtype="<U32")
    windward_weight = np.full(incidence.shape, np.nan, dtype=np.float64)

    finite_incidence = np.isfinite(incidence)
    dispatched = geometry & finite_incidence
    recovery_mask = dispatched & (incidence <= 0.0)
    transition_mask = dispatched & (incidence > 0.0) & (incidence < epsilon)
    windward_mask = dispatched & (incidence >= epsilon)

    windward_weight[recovery_mask] = 0.0
    scaled = np.clip(incidence[transition_mask] / epsilon, 0.0, 1.0)
    windward_weight[transition_mask] = scaled * scaled * (3.0 - 2.0 * scaled)
    windward_weight[windward_mask] = 1.0
    provider[recovery_mask] = "leeward_recovery"
    provider[transition_mask] = "near_tangent_blend"
    provider[windward_mask] = "windward_turbulent"
    reason[dispatched] = ""

    recovery_finite = np.isfinite(recovery) & (recovery > 0.0)
    windward_finite = np.isfinite(windward) & (windward > 0.0)
    prediction[recovery_mask & recovery_finite] = recovery[
        recovery_mask & recovery_finite
    ]
    prediction[windward_mask & windward_finite] = windward[
        windward_mask & windward_finite
    ]

    transition_ready = transition_mask & recovery_finite & windward_finite
    for index in np.flatnonzero(transition_ready):
        recovery_h = float(gas.h_from_T(float(recovery[index])))
        windward_h = float(gas.h_from_T(float(windward[index])))
        weight = float(windward_weight[index])
        prediction[index] = float(
            gas.T_from_h((1.0 - weight) * recovery_h + weight * windward_h)
        )

    needs_recovery = dispatched & (windward_weight < 1.0)
    needs_windward = dispatched & (windward_weight > 0.0)
    missing_recovery = needs_recovery & ~recovery_finite
    missing_windward = needs_windward & ~windward_finite
    reason[missing_recovery] = "recovery_nonfinite"
    reason[missing_windward] = "windward_nonfinite"
    reason[missing_recovery & missing_windward] = "candidate_nonfinite"
    finite_positive = np.isfinite(prediction) & (prediction > 0.0)
    valid[dispatched & finite_positive] = True
    reason[valid] = ""
    reason[geometry & ~finite_incidence] = "invalid_incidence"
    unresolved = dispatched & ~valid & (reason == "")
    reason[unresolved] = "provider_nonfinite"
    return prediction, provider, valid, reason, windward_weight


def _structured_mapping_support_radius(
    *,
    x_m: np.ndarray,
    span_m: np.ndarray,
    geometry_valid: np.ndarray,
) -> np.ndarray:
    """Return each vertex's largest incident valid-triangle support radius."""

    x = np.asarray(x_m, dtype=np.float64)
    span = np.asarray(span_m, dtype=np.float64)
    geometry = np.asarray(geometry_valid, dtype=np.bool_)
    if x.ndim != 2 or x.shape != span.shape or x.shape != geometry.shape:
        raise ValueError(
            "structured support inputs must be matching two-dimensional grids"
        )
    coordinate_valid = geometry & np.isfinite(x) & np.isfinite(span)
    support = np.full(x.shape, np.nan, dtype=np.float64)
    support[coordinate_valid] = 0.0
    _, nx = x.shape
    for triangle in _structured_cell_triangles(coordinate_valid):
        rows, columns = np.divmod(triangle, nx)
        coordinates = np.column_stack((x[rows, columns], span[rows, columns]))
        edge_lengths = (
            np.linalg.norm(coordinates[1] - coordinates[0]),
            np.linalg.norm(coordinates[2] - coordinates[1]),
            np.linalg.norm(coordinates[0] - coordinates[2]),
        )
        local_limit = 0.5 * float(max(edge_lengths))
        for row, column in zip(rows, columns, strict=True):
            support[row, column] = max(float(support[row, column]), local_limit)
    return support


def _build_lf_surface_fields(
    *,
    case: N8TawCaseSpec,
    sampling: N8SamplingSpec,
    geometry: _GeometryInputs,
    gas: GasModel,
) -> dict[str, np.ndarray]:
    xc = np.linspace(sampling.x_start, sampling.x_end, sampling.nx, dtype=np.float64)
    yb = np.linspace(sampling.y_start, sampling.y_end, sampling.ny, dtype=np.float64)
    shape = (sampling.ny, sampling.nx)
    sampler = SurfaceSlopeSampler(mesh=geometry.mesh)
    triangle_sheet = classify_triangle_geometric_sheets(geometry.triangles)
    legacy_normal_triangle_sheet = classify_triangle_geometric_sheets(
        geometry.triangles, propagate_components=False
    )
    normal_field = ContinuousStlNormalField(
        mesh=geometry.mesh,
        triangle_sheet=triangle_sheet,
        crease_angle_deg=_NORMAL_CREASE_ANGLE_DEG,
    )
    legacy_normal_field = ContinuousStlNormalField(
        mesh=geometry.mesh,
        triangle_sheet=legacy_normal_triangle_sheet,
        crease_angle_deg=_NORMAL_CREASE_ANGLE_DEG,
    )
    sheet_data: dict[str, dict[str, np.ndarray]] = {}
    slope_refs = {
        "upper": geometry.f3.slopes()[:2],
        "lower": geometry.f3.slopes()[2:],
    }
    sheet_codes = {"upper": GEOMETRIC_SHEET_UPPER, "lower": GEOMETRIC_SHEET_LOWER}

    for sheet in _SHEETS:
        data = {
            "x_m": np.full(shape, np.nan, dtype=np.float64),
            "span_m": np.full(shape, np.nan, dtype=np.float64),
            "z_m": np.full(shape, np.nan, dtype=np.float64),
            "sx": np.full(shape, np.nan, dtype=np.float64),
            "sy": np.full(shape, np.nan, dtype=np.float64),
            "normal": np.full((*shape, 3), np.nan, dtype=np.float64),
            "stl_face_normal": np.full((*shape, 3), np.nan, dtype=np.float64),
            "incidence_s": np.full(shape, np.nan, dtype=np.float64),
            "stl_face_incidence_s": np.full(shape, np.nan, dtype=np.float64),
            "normal_smoothing_angle_deg": np.full(shape, np.nan, dtype=np.float64),
            "triangle_id": np.full(shape, -1, dtype=np.int64),
            "surface_class_code": np.full(shape, SURFACE_CLASS_INVALID, dtype=np.int8),
            "geometry_valid": np.zeros(shape, dtype=np.bool_),
            "geometry_failure_reason": np.full(
                shape, "unresolved_geometry", dtype="<U32"
            ),
            "chord_m": np.full(sampling.ny, np.nan, dtype=np.float64),
        }
        for j, yb_value in enumerate(yb):
            span = float(yb_value) * geometry.b_half_m
            x_le, chord = outline_planform_xle_chord(
                span_m=span,
                outline_x_m=geometry.outline_x_m,
                outline_span_m=geometry.outline_span_m,
            )
            data["chord_m"][j] = chord
            if not np.isfinite(x_le) or not np.isfinite(chord):
                data["geometry_failure_reason"][j] = "invalid_planform_intersection"
                continue
            data["x_m"][j] = float(x_le) + xc * float(chord)
            data["span_m"][j] = span
            if chord < geometry.f3.chord_min_m:
                data["geometry_failure_reason"][j] = "degenerate_planform_chord"
                continue
            for i, xc_value in enumerate(xc):
                x_m = float(data["x_m"][j, i])
                upper, lower = sampler.sample_upper_lower_with_triangle_id(
                    x=x_m,
                    span=span,
                    triangle_sheet=triangle_sheet,
                )
                sample = upper if sheet == "upper" else lower
                if sample is None:
                    raw_upper, raw_lower = (
                        sampler.sample_upper_lower_with_triangle_id(
                            x=x_m, span=span
                        )
                    )
                    raw_sample = raw_upper if sheet == "upper" else raw_lower
                    if (
                        raw_sample is not None
                        and int(triangle_sheet[int(raw_sample[6])])
                        != sheet_codes[sheet]
                    ):
                        data["geometry_failure_reason"][j, i] = (
                            "geometric_sheet_mismatch"
                        )
                    else:
                        data["geometry_failure_reason"][j, i] = (
                            "outside_stl_support"
                        )
                    continue
                _sx, _sy, z_m, nx, ny, nz, triangle_id = sample
                if int(triangle_sheet[int(triangle_id)]) != sheet_codes[sheet]:
                    data["geometry_failure_reason"][j, i] = "geometric_sheet_mismatch"
                    continue
                face_outward = orient_outward_normal(
                    normal=np.asarray([nx, ny, nz], dtype=np.float64), sheet=sheet
                )
                if not np.all(np.isfinite(face_outward)):
                    data["geometry_failure_reason"][j, i] = "invalid_surface_normal"
                    continue
                selected_normal_field = (
                    legacy_normal_field
                    if int(legacy_normal_triangle_sheet[int(triangle_id)])
                    == sheet_codes[sheet]
                    else normal_field
                )
                outward = selected_normal_field.sample_outward_normal(
                    triangle_id=int(triangle_id), x=x_m, span=span
                )
                if not np.all(np.isfinite(outward)):
                    data["geometry_failure_reason"][j, i] = "invalid_continuous_normal"
                    continue
                if abs(float(outward[2])) <= 1.0e-12:
                    data["geometry_failure_reason"][j, i] = "continuous_normal_vertical"
                    continue
                incidence_s, class_code = classify_incidence(
                    normal_out=outward, alpha_deg=case.alpha_deg
                )
                face_incidence_s, _ = classify_incidence(
                    normal_out=face_outward, alpha_deg=case.alpha_deg
                )
                smoothing_angle_deg = float(
                    np.rad2deg(
                        np.arccos(np.clip(np.dot(face_outward, outward), -1.0, 1.0))
                    )
                )
                data["z_m"][j, i] = z_m
                data["sx"][j, i] = -float(outward[0]) / float(outward[2])
                data["sy"][j, i] = -float(outward[1]) / float(outward[2])
                data["normal"][j, i] = outward
                data["stl_face_normal"][j, i] = face_outward
                data["incidence_s"][j, i] = float(incidence_s)
                data["stl_face_incidence_s"][j, i] = float(face_incidence_s)
                data["normal_smoothing_angle_deg"][j, i] = smoothing_angle_deg
                data["triangle_id"][j, i] = int(triangle_id)
                data["surface_class_code"][j, i] = np.int8(class_code)
                data["geometry_valid"][j, i] = True
                data["geometry_failure_reason"][j, i] = ""
        sheet_data[sheet] = data

    rho_inf = case.p_inf_Pa / (case.R_J_per_kgK * case.T_inf_K)
    V_inf = case.mach * float(gas.tpg.a_T(case.T_inf_K))
    lf_cfg = LfQwConfig(
        phi_clamp=PhiClampConfig(enable=True, warn=False, phi_min_rad=1.0e-8),
        transition=TransitionBlendConfig(enable=False, weighting="step"),
        x_model=XModelConfig(x_min_over_c=0.003),
        stagnation=StagnationConfig(),
        q_stag_ratio_warn=2.0,
    )
    for sheet in _SHEETS:
        data = sheet_data[sheet]
        windward_taw = np.full(shape, np.nan, dtype=np.float64)
        ref_sx, ref_sy = slope_refs[sheet]
        for j in range(sampling.ny):
            incidence_row = data["incidence_s"][j]
            valid_row = data["geometry_valid"][j]
            if not np.any(valid_row & (incidence_row > 0.0)):
                continue
            chord = float(data["chord_m"][j])
            if not np.isfinite(chord) or chord <= 0.0:
                continue
            sx_row = np.where(np.isfinite(data["sx"][j]), data["sx"][j], ref_sx)
            sy_row = np.where(np.isfinite(data["sy"][j]), data["sy"][j], ref_sy)
            chord_eff = max(chord, geometry.f3.chord_min_m)
            x_phys = np.maximum(xc * chord_eff, max(0.003 * chord_eff, 1.0e-6))
            cache = build_windward_edge_cache_faceted3d(
                gas=gas,
                lf_cfg=lf_cfg,
                mach=case.mach,
                alpha_deg=case.alpha_deg,
                sweep_le_deg=geometry.sweep_le_deg,
                p_inf=case.p_inf_Pa,
                rho_inf=rho_inf,
                T_inf=case.T_inf_K,
                chord_m=chord_eff,
                xc_grid=xc,
                sx_arr=sx_row,
                sy_arr=sy_row,
                transition_x_over_c=None,
                use_effective_alpha=geometry.f3.edge_use_effective_alpha,
                use_effective_mach=geometry.f3.edge_use_effective_mach,
                x_phys_override=x_phys,
                cp_model=geometry.f3.cp_model,
                cp_newtonian_A=geometry.f3.cp_newtonian_A,
                cp_newtonian_n=geometry.f3.cp_newtonian_n,
            )
            if cache.taw_tpg is None:
                raise ValueError(
                    "windward fully-turbulent TPG Taw provider returned no field"
                )
            windward_taw[j] = np.asarray(cache.taw_tpg, dtype=np.float64)
        incidence_flat = data["incidence_s"].reshape(-1)
        geometry_flat = data["geometry_valid"].reshape(-1)
        recovery = build_freestream_recovery(
            mask=geometry_flat & np.isfinite(incidence_flat),
            T_inf_K=case.T_inf_K,
            p_inf_Pa=case.p_inf_Pa,
            rho_inf_kg_m3=rho_inf,
            V_inf_m_s=V_inf,
            Ma_inf=case.mach,
            gas=gas,
        )
        prediction, provider, valid, reason, windward_weight = dispatch_taw_predictions(
            incidence_s=incidence_flat,
            geometry_valid=geometry_flat,
            windward_taw_K=windward_taw.reshape(-1),
            recovery_taw_K=recovery.Taw_tpg,
            gas=gas,
        )
        geometry_reason = data["geometry_failure_reason"].reshape(-1)
        reason[~geometry_flat] = geometry_reason[~geometry_flat]
        data["Taw_windward_candidate_K"] = windward_taw
        data["Taw_recovery_candidate_K"] = recovery.Taw_tpg.reshape(shape)
        data["windward_blend_weight"] = windward_weight.reshape(shape)
        data["Taw_prediction_K"] = prediction.reshape(shape)
        data["provider"] = provider.reshape(shape)
        data["valid"] = valid.reshape(shape)
        data["failure_reason"] = reason.reshape(shape)
        data["mapping_support_radius_m"] = _structured_mapping_support_radius(
            x_m=data["x_m"],
            span_m=data["span_m"],
            geometry_valid=data["geometry_valid"],
        )

    count_per_sheet = sampling.nx * sampling.ny
    combined: dict[str, np.ndarray] = {
        "canonical_index": np.arange(2 * count_per_sheet, dtype=np.int64),
        "geometric_sheet": np.concatenate(
            [
                np.full(count_per_sheet, "upper", dtype="<U5"),
                np.full(count_per_sheet, "lower", dtype="<U5"),
            ]
        ),
        "x_over_c": np.tile(xc, 2 * sampling.ny),
        "y_over_b": np.tile(np.repeat(yb, sampling.nx), 2),
    }
    for key in (
        "x_m",
        "span_m",
        "z_m",
        "sx",
        "sy",
        "incidence_s",
        "stl_face_incidence_s",
        "normal_smoothing_angle_deg",
        "triangle_id",
        "geometry_valid",
        "mapping_support_radius_m",
        "Taw_prediction_K",
        "valid",
        "provider",
        "geometry_failure_reason",
        "Taw_windward_candidate_K",
        "Taw_recovery_candidate_K",
        "windward_blend_weight",
        "failure_reason",
    ):
        combined[key] = np.concatenate(
            [sheet_data[sheet][key].reshape(-1) for sheet in _SHEETS]
        )
    class_codes = np.concatenate(
        [sheet_data[sheet]["surface_class_code"].reshape(-1) for sheet in _SHEETS]
    )
    combined["surface_class_code"] = class_codes
    combined["surface_class"] = _surface_class_names(class_codes)
    combined["normal_out"] = np.concatenate(
        [sheet_data[sheet]["normal"].reshape(-1, 3) for sheet in _SHEETS], axis=0
    )
    combined["stl_face_normal_out"] = np.concatenate(
        [sheet_data[sheet]["stl_face_normal"].reshape(-1, 3) for sheet in _SHEETS],
        axis=0,
    )
    return combined


def _explicit_mapping_support_radius(
    *,
    x_m: np.ndarray,
    span_m: np.ndarray,
    triangle_node_ids: np.ndarray,
) -> np.ndarray:
    x = np.asarray(x_m, dtype=np.float64)
    span = np.asarray(span_m, dtype=np.float64)
    triangles = np.asarray(triangle_node_ids, dtype=np.int64)
    if x.ndim != 1 or span.shape != x.shape:
        raise ValueError("explicit support coordinates must be matching 1D arrays")
    if triangles.ndim != 2 or triangles.shape[1] != 3:
        raise ValueError("triangle_node_ids must have shape (M, 3)")
    if np.any(triangles < 0) or np.any(triangles >= x.size):
        raise ValueError("triangle_node_ids contains an invalid node ID")
    support = np.zeros(x.size, dtype=np.float64)
    for triangle in triangles:
        coordinates = np.column_stack((x[triangle], span[triangle]))
        edge_lengths = (
            np.linalg.norm(coordinates[1] - coordinates[0]),
            np.linalg.norm(coordinates[2] - coordinates[1]),
            np.linalg.norm(coordinates[0] - coordinates[2]),
        )
        local_limit = 0.5 * float(max(edge_lengths))
        support[triangle] = np.maximum(support[triangle], local_limit)
    if np.any(support <= 0.0):
        raise ValueError("explicit topology contains an unconnected node")
    return support


def _topology_hash(
    *,
    x_m: np.ndarray,
    span_m: np.ndarray,
    z_m: np.ndarray,
    triangle_node_ids: np.ndarray,
    triangle_geometric_sheet: np.ndarray,
    triangle_source_stl_triangle_id: np.ndarray,
) -> str:
    digest = hashlib.sha256()
    for value in (
        np.asarray(x_m, dtype=np.float64),
        np.asarray(span_m, dtype=np.float64),
        np.asarray(z_m, dtype=np.float64),
        np.asarray(triangle_node_ids, dtype=np.int64),
        np.asarray(triangle_geometric_sheet, dtype="<U5"),
        np.asarray(triangle_source_stl_triangle_id, dtype=np.int64),
    ):
        contiguous = np.ascontiguousarray(value)
        digest.update(str(contiguous.dtype).encode("ascii"))
        digest.update(np.asarray(contiguous.shape, dtype=np.int64).tobytes())
        digest.update(contiguous.tobytes(order="C"))
    return digest.hexdigest()


def _build_domain_conforming_product(
    *,
    legacy_fields: Mapping[str, np.ndarray],
    case: N8TawCaseSpec,
    sampling: N8SamplingSpec,
    geometry: _GeometryInputs,
    gas: GasModel,
) -> dict[str, np.ndarray]:
    count_per_sheet = sampling.nx * sampling.ny
    shape = (sampling.ny, sampling.nx)
    triangle_sheet = classify_triangle_geometric_sheets(geometry.triangles)
    if np.any(triangle_sheet == -1):
        raise ValueError("STL sheet classifier has unresolved triangles")
    normal_field = ContinuousStlNormalField(
        mesh=geometry.mesh,
        triangle_sheet=triangle_sheet,
        crease_angle_deg=_NORMAL_CREASE_ANGLE_DEG,
    )
    sheet_codes = {"upper": GEOMETRIC_SHEET_UPPER, "lower": GEOMETRIC_SHEET_LOWER}
    topologies: dict[str, N8DomainTopology] = {}
    for sheet in _SHEETS:
        offset = 0 if sheet == "upper" else count_per_sheet
        sheet_slice = slice(offset, offset + count_per_sheet)
        topologies[sheet] = build_n8_domain_topology(
            x_m=np.asarray(legacy_fields["x_m"])[sheet_slice].reshape(shape),
            span_m=np.asarray(legacy_fields["span_m"])[sheet_slice].reshape(shape),
            x_over_c=np.asarray(legacy_fields["x_over_c"])[sheet_slice].reshape(shape),
            y_over_b=np.asarray(legacy_fields["y_over_b"])[sheet_slice].reshape(shape),
            geometry_valid=np.asarray(legacy_fields["geometry_valid"])[
                sheet_slice
            ].reshape(shape),
            legacy_source_stl_triangle_id=np.asarray(legacy_fields["triangle_id"])[
                sheet_slice
            ].reshape(shape),
            mesh=geometry.mesh,
            triangle_sheet=triangle_sheet,
            sheet_code=sheet_codes[sheet],
            legacy_sheet_offset=offset,
        )

    node_offsets: dict[str, int] = {}
    running_offset = 0
    for sheet in _SHEETS:
        node_offsets[sheet] = running_offset
        running_offset += int(topologies[sheet].node_x_m.size)
    node_count = running_offset
    sheet_names = np.concatenate(
        [
            np.full(topologies[sheet].node_x_m.size, sheet, dtype="<U5")
            for sheet in _SHEETS
        ]
    )
    triangle_node_ids = np.concatenate(
        [
            topologies[sheet].triangle_node_ids + node_offsets[sheet]
            for sheet in _SHEETS
        ],
        axis=0,
    )
    triangle_geometric_sheet = np.concatenate(
        [
            np.full(
                topologies[sheet].triangle_node_ids.shape[0], sheet, dtype="<U5"
            )
            for sheet in _SHEETS
        ]
    )
    triangle_source = np.concatenate(
        [
            topologies[sheet].triangle_source_stl_triangle_id
            for sheet in _SHEETS
        ]
    )
    legacy_index = np.concatenate(
        [topologies[sheet].legacy_phase9_canonical_index for sheet in _SHEETS]
    )
    interpolation_indices = np.concatenate(
        [topologies[sheet].interpolation_legacy_indices for sheet in _SHEETS],
        axis=0,
    )
    interpolation_weights = np.concatenate(
        [topologies[sheet].interpolation_weights for sheet in _SHEETS],
        axis=0,
    )
    source_triangle = np.concatenate(
        [topologies[sheet].source_stl_triangle_id for sheet in _SHEETS]
    )
    direct = legacy_index >= 0
    inserted = ~direct

    product: dict[str, np.ndarray] = {
        "node_id": np.arange(node_count, dtype=np.int64),
        "geometric_sheet": sheet_names,
        "x_m": np.concatenate([topologies[sheet].node_x_m for sheet in _SHEETS]),
        "span_m": np.concatenate(
            [topologies[sheet].node_span_m for sheet in _SHEETS]
        ),
        "x_over_c": np.concatenate(
            [topologies[sheet].node_x_over_c for sheet in _SHEETS]
        ),
        "y_over_b": np.concatenate(
            [topologies[sheet].node_y_over_b for sheet in _SHEETS]
        ),
        "parameter_row": np.concatenate(
            [topologies[sheet].parameter_row for sheet in _SHEETS]
        ),
        "parameter_column": np.concatenate(
            [topologies[sheet].parameter_column for sheet in _SHEETS]
        ),
        "legacy_phase9_canonical_index": legacy_index,
        "domain_role": np.concatenate(
            [topologies[sheet].domain_role for sheet in _SHEETS]
        ),
        "source_stl_triangle_id": source_triangle.copy(),
        "source_stl_edge_id": np.concatenate(
            [topologies[sheet].source_stl_edge_id for sheet in _SHEETS]
        ),
        "triangle_id": np.arange(triangle_node_ids.shape[0], dtype=np.int64),
        "triangle_node_ids": triangle_node_ids,
        "triangle_geometric_sheet": triangle_geometric_sheet,
        "triangle_source_stl_triangle_id": triangle_source,
    }
    node_float_fields = (
        "z_m",
        "sx",
        "sy",
        "incidence_s",
        "stl_face_incidence_s",
        "normal_smoothing_angle_deg",
        "Taw_windward_candidate_K",
        "Taw_recovery_candidate_K",
    )
    for key in node_float_fields:
        product[key] = np.full(node_count, np.nan, dtype=np.float64)
    product["normal_out"] = np.full((node_count, 3), np.nan, dtype=np.float64)
    product["stl_face_normal_out"] = np.full(
        (node_count, 3), np.nan, dtype=np.float64
    )

    for key in node_float_fields:
        product[key][direct] = np.asarray(legacy_fields[key])[legacy_index[direct]]
    product["normal_out"][direct] = np.asarray(legacy_fields["normal_out"])[
        legacy_index[direct]
    ]
    product["stl_face_normal_out"][direct] = np.asarray(
        legacy_fields["stl_face_normal_out"]
    )[legacy_index[direct]]
    product["source_stl_triangle_id"][direct] = np.asarray(
        legacy_fields["triangle_id"], dtype=np.int64
    )[legacy_index[direct]]

    triangles = geometry.triangles
    for node_id in np.flatnonzero(inserted):
        source_id = int(product["source_stl_triangle_id"][node_id])
        source_vertices = triangles[source_id]
        projected = source_vertices[:, :2]
        point = np.asarray(
            [product["x_m"][node_id], product["span_m"][node_id]],
            dtype=np.float64,
        )
        matrix = np.column_stack(
            (projected[1] - projected[0], projected[2] - projected[0])
        )
        second, third = np.linalg.solve(matrix, point - projected[0])
        barycentric = np.asarray(
            [1.0 - second - third, second, third], dtype=np.float64
        )
        product["z_m"][node_id] = float(barycentric @ source_vertices[:, 2])
        raw_face = np.cross(
            source_vertices[1] - source_vertices[0],
            source_vertices[2] - source_vertices[0],
        )
        sheet = str(sheet_names[node_id])
        face_outward = orient_outward_normal(normal=raw_face, sheet=sheet)
        outward = normal_field.sample_outward_normal(
            triangle_id=source_id,
            x=float(point[0]),
            span=float(point[1]),
        )
        if not np.all(np.isfinite(outward)) or abs(float(outward[2])) <= 1.0e-12:
            raise ValueError("inserted boundary node has no valid continuous normal")
        incidence, _ = classify_incidence(
            normal_out=outward, alpha_deg=case.alpha_deg
        )
        face_incidence, _ = classify_incidence(
            normal_out=face_outward, alpha_deg=case.alpha_deg
        )
        product["normal_out"][node_id] = outward
        product["stl_face_normal_out"][node_id] = face_outward
        product["sx"][node_id] = -float(outward[0]) / float(outward[2])
        product["sy"][node_id] = -float(outward[1]) / float(outward[2])
        product["incidence_s"][node_id] = float(incidence)
        product["stl_face_incidence_s"][node_id] = float(face_incidence)
        product["normal_smoothing_angle_deg"][node_id] = float(
            np.rad2deg(
                np.arccos(np.clip(np.dot(face_outward, outward), -1.0, 1.0))
            )
        )

    rho_inf = case.p_inf_Pa / (case.R_J_per_kgK * case.T_inf_K)
    V_inf = case.mach * float(gas.tpg.a_T(case.T_inf_K))
    recovery = build_freestream_recovery(
        mask=np.ones(node_count, dtype=np.bool_),
        T_inf_K=case.T_inf_K,
        p_inf_Pa=case.p_inf_Pa,
        rho_inf_kg_m3=rho_inf,
        V_inf_m_s=V_inf,
        Ma_inf=case.mach,
        gas=gas,
    )
    product["Taw_recovery_candidate_K"][inserted] = recovery.Taw_tpg[inserted]

    parent_geometry = np.asarray(
        legacy_fields["geometry_valid"], dtype=np.bool_
    )[interpolation_indices]
    legacy_windward = np.asarray(
        legacy_fields["Taw_windward_candidate_K"], dtype=np.float64
    )
    for node_id in np.flatnonzero(inserted & (product["incidence_s"] > 0.0)):
        parent_indices = interpolation_indices[node_id]
        weights = interpolation_weights[node_id]
        parent_candidate = legacy_windward[parent_indices]
        if np.all(parent_geometry[node_id]) and np.all(np.isfinite(parent_candidate)):
            product["Taw_windward_candidate_K"][node_id] = float(
                weights @ parent_candidate
            )
            continue
        chord = float(
            outline_planform_xle_chord(
                span_m=float(product["span_m"][node_id]),
                outline_x_m=geometry.outline_x_m,
                outline_span_m=geometry.outline_span_m,
            )[1]
        )
        if not np.isfinite(chord) or chord <= 0.0:
            raise ValueError("inserted windward node has no planform chord")
        chord_eff = max(chord, geometry.f3.chord_min_m)
        node_xc = float(product["x_over_c"][node_id])
        lf_cfg = LfQwConfig(
            phi_clamp=PhiClampConfig(enable=True, warn=False, phi_min_rad=1.0e-8),
            transition=TransitionBlendConfig(enable=False, weighting="step"),
            x_model=XModelConfig(x_min_over_c=0.003),
            stagnation=StagnationConfig(),
            q_stag_ratio_warn=2.0,
        )
        cache = build_windward_edge_cache_faceted3d(
            gas=gas,
            lf_cfg=lf_cfg,
            mach=case.mach,
            alpha_deg=case.alpha_deg,
            sweep_le_deg=geometry.sweep_le_deg,
            p_inf=case.p_inf_Pa,
            rho_inf=rho_inf,
            T_inf=case.T_inf_K,
            chord_m=chord_eff,
            xc_grid=np.asarray([node_xc]),
            sx_arr=np.asarray([product["sx"][node_id]]),
            sy_arr=np.asarray([product["sy"][node_id]]),
            transition_x_over_c=None,
            use_effective_alpha=geometry.f3.edge_use_effective_alpha,
            use_effective_mach=geometry.f3.edge_use_effective_mach,
            x_phys_override=np.asarray(
                [max(node_xc * chord_eff, max(0.003 * chord_eff, 1.0e-6))]
            ),
            cp_model=geometry.f3.cp_model,
            cp_newtonian_A=geometry.f3.cp_newtonian_A,
            cp_newtonian_n=geometry.f3.cp_newtonian_n,
        )
        if cache.taw_tpg is None or not np.isfinite(cache.taw_tpg[0]):
            raise ValueError("inserted windward node has no Taw candidate")
        product["Taw_windward_candidate_K"][node_id] = float(cache.taw_tpg[0])

    geometry_valid = np.ones(node_count, dtype=np.bool_)
    prediction, provider, valid, reason, weight = dispatch_taw_predictions(
        incidence_s=product["incidence_s"],
        geometry_valid=geometry_valid,
        windward_taw_K=product["Taw_windward_candidate_K"],
        recovery_taw_K=product["Taw_recovery_candidate_K"],
        gas=gas,
    )
    if not np.all(valid):
        raise ValueError("domain-conforming product has an uncovered provider node")
    class_codes = classify_incidence(
        normal_out=product["normal_out"], alpha_deg=case.alpha_deg
    )[1]
    product.update(
        {
            "surface_class_code": class_codes,
            "surface_class": _surface_class_names(class_codes),
            "geometry_valid": geometry_valid,
            "geometry_failure_reason": np.full(node_count, "", dtype="<U1"),
            "Taw_prediction_K": prediction,
            "provider": provider,
            "valid": valid,
            "failure_reason": reason,
            "windward_blend_weight": weight,
            "mapping_support_radius_m": _explicit_mapping_support_radius(
                x_m=product["x_m"],
                span_m=product["span_m"],
                triangle_node_ids=triangle_node_ids,
            ),
        }
    )

    excluded = ~np.asarray(legacy_fields["geometry_valid"], dtype=np.bool_)
    excluded_reason = np.asarray(
        legacy_fields["geometry_failure_reason"], dtype="<U32"
    )[excluded].copy()

    product["excluded_legacy_phase9_canonical_index"] = np.flatnonzero(
        excluded
    ).astype(np.int64)
    product["excluded_geometric_sheet"] = np.asarray(
        legacy_fields["geometric_sheet"]
    )[excluded]
    product["excluded_x_m"] = np.asarray(legacy_fields["x_m"])[excluded]
    product["excluded_span_m"] = np.asarray(legacy_fields["span_m"])[excluded]
    product["excluded_x_over_c"] = np.asarray(legacy_fields["x_over_c"])[excluded]
    product["excluded_y_over_b"] = np.asarray(legacy_fields["y_over_b"])[excluded]
    product["excluded_geometry_failure_reason"] = excluded_reason
    product["excluded_domain_classification"] = np.full(
        np.count_nonzero(excluded),
        "outside_sheet_specific_graph_skin",
        dtype="<U40",
    )
    topology_hash = _topology_hash(
        x_m=product["x_m"],
        span_m=product["span_m"],
        z_m=product["z_m"],
        triangle_node_ids=triangle_node_ids,
        triangle_geometric_sheet=triangle_geometric_sheet,
        triangle_source_stl_triangle_id=triangle_source,
    )
    product["domain_topology_schema"] = np.asarray(_TOPOLOGY_SCHEMA)
    product["domain_topology_sha256"] = np.asarray(topology_hash)
    return product

def pair_projected_physical_points(
    *,
    sheet: Literal["upper", "lower"],
    source_canonical_index: np.ndarray,
    source_x_span_m: np.ndarray,
    target_canonical_index: np.ndarray,
    target_x_span_m: np.ndarray,
    target_support_radius_m: np.ndarray,
    chunk_size: int = 256,
) -> N8Pairing:
    """Pair every source row and gate comparison by local structured-grid support."""

    if sheet not in _SHEETS:
        raise ValueError("sheet must be exactly 'upper' or 'lower'")
    source_index = np.asarray(source_canonical_index, dtype=np.int64)
    target_index = np.asarray(target_canonical_index, dtype=np.int64)
    source_coords = np.asarray(source_x_span_m, dtype=np.float64)
    target_coords = np.asarray(target_x_span_m, dtype=np.float64)
    target_support = np.asarray(target_support_radius_m, dtype=np.float64)
    if source_index.ndim != 1 or target_index.ndim != 1:
        raise ValueError("pairing identities must be one-dimensional")
    if source_coords.shape != (source_index.size, 2) or target_coords.shape != (
        target_index.size,
        2,
    ):
        raise ValueError("pairing coordinates must have shape (N, 2)")
    if target_support.shape != (target_index.size,):
        raise ValueError("target support radii must match the target pool")
    if source_index.size == 0 or target_index.size == 0:
        raise ValueError(
            "both geometric sheets require nonempty source and target pools"
        )
    if not (np.all(np.isfinite(source_coords)) and np.all(np.isfinite(target_coords))):
        raise ValueError("pairing coordinates must be finite")
    if not np.all(np.isfinite(target_support)) or np.any(target_support < 0.0):
        raise ValueError("target support radii must be finite and nonnegative")
    if (
        np.unique(source_index).size != source_index.size
        or np.unique(target_index).size != target_index.size
    ):
        raise ValueError("pairing identities must be unique")
    source_order = np.argsort(source_index, kind="stable")
    target_order = np.argsort(target_index, kind="stable")
    source_index = source_index[source_order]
    source_coords = source_coords[source_order]
    target_index = target_index[target_order]
    target_coords = target_coords[target_order]
    target_support = target_support[target_order]
    if np.unique(target_coords, axis=0).shape[0] != target_coords.shape[0]:
        raise ValueError("target projected coordinates must be unique")
    chunk = _positive_int(chunk_size, label="chunk_size")

    source_count = source_index.size
    target_count = target_index.size
    nearest_row = np.empty(source_count, dtype=np.int64)
    nearest_d2 = np.empty(source_count, dtype=np.float64)
    second_row = np.full(source_count, -1, dtype=np.int64)
    second_d2 = np.full(source_count, np.inf, dtype=np.float64)
    reverse_best_d2 = np.full(target_count, np.inf, dtype=np.float64)
    reverse_best_source = np.full(target_count, -1, dtype=np.int64)

    for start in range(0, source_count, chunk):
        stop = min(start + chunk, source_count)
        delta = target_coords[None, :, :] - source_coords[start:stop, None, :]
        d2 = np.sum(delta * delta, axis=2, dtype=np.float64)
        if not np.all(np.isfinite(d2)):
            raise ValueError("pairwise squared distance must be finite")
        local_rows = np.arange(stop - start, dtype=np.int64)
        first = np.argmin(d2, axis=1)
        nearest_row[start:stop] = first
        nearest_d2[start:stop] = d2[local_rows, first]
        if target_count >= 2:
            second_search = d2.copy()
            second_search[local_rows, first] = np.inf
            second = np.argmin(second_search, axis=1)
            second_row[start:stop] = second
            second_d2[start:stop] = d2[local_rows, second]
        local_reverse = np.argmin(d2, axis=0)
        local_reverse_d2 = d2[local_reverse, np.arange(target_count)]
        update = local_reverse_d2 < reverse_best_d2
        reverse_best_d2[update] = local_reverse_d2[update]
        reverse_best_source[update] = start + local_reverse[update]

    multiplicity_by_target = np.bincount(nearest_row, minlength=target_count).astype(
        np.int64
    )
    source_rows = np.arange(source_count, dtype=np.int64)
    distance = np.sqrt(nearest_d2)
    support_limit = target_support[nearest_row]
    supported = distance <= support_limit * (1.0 + 1.0e-12)
    return N8Pairing(
        sheet=sheet,
        source_canonical_index=source_index.copy(),
        target_canonical_index=target_index[nearest_row].copy(),
        distance_m=distance,
        target_multiplicity=multiplicity_by_target[nearest_row].copy(),
        second_target_canonical_index=(
            target_index[second_row].copy()
            if target_count >= 2
            else np.full(source_count, -1, dtype=np.int64)
        ),
        second_distance_m=np.sqrt(second_d2),
        mutual_nearest=(reverse_best_source[nearest_row] == source_rows),
        support_limit_m=support_limit.copy(),
        mapping_supported=supported.copy(),
        target_pool_size=int(target_count),
    )


def _build_comparison(
    *,
    sheet: Literal["upper", "lower"],
    source_csv_sha256: str,
    source_canonical_index: np.ndarray,
    source_row_index: np.ndarray,
    source_surface_class: np.ndarray,
    source_wall_temperature_K: np.ndarray,
    source_x_span_m: np.ndarray,
    target_canonical_index: np.ndarray,
    target_surface_class: np.ndarray,
    target_Taw_K: np.ndarray,
    target_x_span_m: np.ndarray,
    target_support_radius_m: np.ndarray,
) -> tuple[N8SheetComparison, N8Pairing]:
    pairing = pair_projected_physical_points(
        sheet=sheet,
        source_canonical_index=source_canonical_index,
        source_x_span_m=source_x_span_m,
        target_canonical_index=target_canonical_index,
        target_x_span_m=target_x_span_m,
        target_support_radius_m=target_support_radius_m,
    )
    source_lookup = {
        int(value): index
        for index, value in enumerate(np.asarray(source_canonical_index))
    }
    source_order = np.asarray(
        [source_lookup[int(value)] for value in pairing.source_canonical_index],
        dtype=np.int64,
    )
    target_lookup = {
        int(value): index
        for index, value in enumerate(np.asarray(target_canonical_index))
    }
    target_rows = np.asarray(
        [target_lookup[int(value)] for value in pairing.target_canonical_index],
        dtype=np.int64,
    )
    observation = np.asarray(source_wall_temperature_K, dtype=np.float64)[source_order]
    paired_prediction = np.asarray(target_Taw_K, dtype=np.float64)[target_rows]
    if not (np.all(np.isfinite(observation)) and np.all(observation > 0.0)):
        raise ValueError(f"{sheet} observations must be finite positive K")
    if not (np.all(np.isfinite(paired_prediction)) and np.all(paired_prediction > 0.0)):
        raise ValueError(f"{sheet} paired predictions must be finite positive K")
    comparison_valid = pairing.mapping_supported.copy()
    failure_reason = np.full(comparison_valid.shape, _MAPPING_UNSUPPORTED, dtype="<U24")
    failure_reason[comparison_valid] = ""
    prediction = np.where(comparison_valid, paired_prediction, np.nan)
    signed = np.where(comparison_valid, prediction - observation, np.nan)
    signed_relative = np.where(comparison_valid, 100.0 * signed / observation, np.nan)
    comparison = N8SheetComparison(
        sheet=sheet,
        source_csv_sha256=source_csv_sha256,
        source_canonical_index=pairing.source_canonical_index.copy(),
        source_row_index=np.asarray(source_row_index, dtype=np.int64)[
            source_order
        ].copy(),
        source_surface_class=np.asarray(source_surface_class)[source_order].copy(),
        target_canonical_index=pairing.target_canonical_index.copy(),
        target_surface_class=np.asarray(target_surface_class)[target_rows].copy(),
        pairing_distance_m=pairing.distance_m.copy(),
        mapping_support_limit_m=pairing.support_limit_m.copy(),
        comparison_valid=comparison_valid,
        comparison_failure_reason=failure_reason,
        target_multiplicity=pairing.target_multiplicity.copy(),
        wall_temperature_K=observation.copy(),
        Taw_prediction_K=prediction.copy(),
        signed_error_K=signed,
        signed_relative_error_pct=signed_relative,
        absolute_error_K=np.abs(signed),
        absolute_relative_error_pct=np.abs(signed_relative),
    )
    return comparison, pairing


def _numeric_stats(values: np.ndarray) -> dict[str, float | int]:
    data = np.asarray(values, dtype=np.float64)
    if data.ndim != 1 or data.size == 0 or not np.all(np.isfinite(data)):
        raise ValueError("statistics require a nonempty finite vector")
    return {
        "count": int(data.size),
        "min": float(np.min(data)),
        "mean": float(np.mean(data)),
        "median": float(np.median(data)),
        "p95": float(np.percentile(data, 95.0)),
        "max": float(np.max(data)),
    }


def _class_counts(values: np.ndarray) -> dict[str, int]:
    names = _surface_class_names(np.asarray(values, dtype=np.int8))
    return {
        name: int(np.count_nonzero(names == name))
        for name in ("windward", "leeward", "near_tangent", "invalid")
    }


def _comparison_stats(
    *,
    comparison: N8SheetComparison,
    pairing: N8Pairing,
    raw_source_rows: int,
    geometric_sheet_source_rows: int,
    target_valid_count: int,
) -> dict[str, Any]:
    cross: dict[str, dict[str, int]] = {}
    source_names = _surface_class_names(comparison.source_surface_class)
    target_names = _surface_class_names(comparison.target_surface_class)
    for source_name in ("windward", "leeward", "near_tangent", "invalid"):
        cross[source_name] = {
            target_name: int(
                np.count_nonzero(
                    (source_names == source_name) & (target_names == target_name)
                )
            )
            for target_name in ("windward", "leeward", "near_tangent", "invalid")
        }
    supported = np.asarray(comparison.comparison_valid, dtype=np.bool_)
    if not np.any(supported):
        raise ValueError(f"{comparison.sheet} comparison has no locally supported rows")
    unsupported = ~supported
    return {
        "status": "PASS",
        "raw_fluent_source_rows": int(raw_source_rows),
        "geometric_sheet_source_rows": int(geometric_sheet_source_rows),
        "valid_observations": int(comparison.wall_temperature_K.size),
        "valid_predictions": int(np.count_nonzero(supported)),
        "paired_source_rows": int(comparison.source_row_index.size),
        "comparison_supported_rows": int(np.count_nonzero(supported)),
        "mapping_unsupported_rows": int(np.count_nonzero(unsupported)),
        "unique_lf_targets": int(np.unique(comparison.target_canonical_index).size),
        "target_pool_size": int(pairing.target_pool_size),
        "valid_lf_canonical_points": int(target_valid_count),
        "mapping_distance_m": _numeric_stats(comparison.pairing_distance_m),
        "mapping_support_limit_m": _numeric_stats(comparison.mapping_support_limit_m),
        "supported_mapping_distance_m": _numeric_stats(
            comparison.pairing_distance_m[supported]
        ),
        "fluent_surface_class_counts": _class_counts(comparison.source_surface_class),
        "target_surface_class_counts": _class_counts(comparison.target_surface_class),
        "surface_class_cross_counts": cross,
        "signed_error_K": _numeric_stats(comparison.signed_error_K[supported]),
        "absolute_error_K": _numeric_stats(comparison.absolute_error_K[supported]),
        "signed_relative_error_pct": _numeric_stats(
            comparison.signed_relative_error_pct[supported]
        ),
        "absolute_relative_error_pct": _numeric_stats(
            comparison.absolute_relative_error_pct[supported]
        ),
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _structured_cell_triangles(valid_vertices: np.ndarray) -> np.ndarray:
    """Build each valid original-grid triangle without masking its sibling."""

    valid = np.asarray(valid_vertices, dtype=np.bool_)
    if valid.ndim != 2:
        raise ValueError("structured plot validity must be two-dimensional")
    ny, nx = valid.shape
    triangles: list[tuple[int, int, int]] = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            top_left = j * nx + i
            top_right = top_left + 1
            bottom_left = (j + 1) * nx + i
            bottom_right = bottom_left + 1
            if valid[j, i] and valid[j, i + 1] and valid[j + 1, i + 1]:
                triangles.append((top_left, top_right, bottom_right))
            if valid[j, i] and valid[j + 1, i + 1] and valid[j + 1, i]:
                triangles.append((top_left, bottom_right, bottom_left))
    return np.asarray(triangles, dtype=np.int64).reshape(-1, 3)


def _plot_structured_surface(
    *,
    path: Path,
    x_m: np.ndarray,
    span_m: np.ndarray,
    values: np.ndarray,
    title: str,
    colorbar_label: str,
    cmap: str,
    vmin: float | None = None,
    vmax: float | None = None,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri

    x = np.asarray(x_m, dtype=np.float64)
    span = np.asarray(span_m, dtype=np.float64)
    z = np.asarray(values, dtype=np.float64)
    if x.ndim != 2 or x.shape != span.shape or x.shape != z.shape:
        raise ValueError(
            "structured surface plot inputs must be matching two-dimensional grids"
        )
    finite = np.isfinite(x) & np.isfinite(span) & np.isfinite(z)
    triangles = _structured_cell_triangles(finite)
    if triangles.size == 0:
        raise ValueError(f"plot {path.name} has no fully valid structured cells")
    used = np.unique(triangles)
    compact_index = np.full(x.size, -1, dtype=np.int64)
    compact_index[used] = np.arange(used.size, dtype=np.int64)
    compact_triangles = compact_index[triangles]
    x_used = x.reshape(-1)[used]
    span_used = span.reshape(-1)[used]
    z_used = z.reshape(-1)[used]
    fig, ax = plt.subplots(figsize=(8.0, 4.8), dpi=180)
    try:
        triangulation = mtri.Triangulation(
            x_used,
            span_used,
            triangles=compact_triangles,
        )
        artist = ax.tripcolor(
            triangulation,
            z_used,
            shading="flat",
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
        )
    except (RuntimeError, ValueError) as error:
        plt.close(fig)
        raise ValueError(f"structured contour failed for {path.name}") from error
    fig.colorbar(artist, ax=ax, label=colorbar_label)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("span (m)")
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_explicit_surface(
    *,
    path: Path,
    x_m: np.ndarray,
    span_m: np.ndarray,
    values: np.ndarray,
    triangle_node_ids: np.ndarray,
    title: str,
    colorbar_label: str,
    cmap: str,
    vmin: float | None = None,
    vmax: float | None = None,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri

    x = np.asarray(x_m, dtype=np.float64)
    span = np.asarray(span_m, dtype=np.float64)
    z = np.asarray(values, dtype=np.float64)
    triangles = np.asarray(triangle_node_ids, dtype=np.int64)
    if x.ndim != 1 or not (x.shape == span.shape == z.shape):
        raise ValueError("explicit plot node fields must be matching 1D arrays")
    if triangles.ndim != 2 or triangles.shape[1] != 3 or triangles.size == 0:
        raise ValueError("explicit plot requires triangle_node_ids with shape (M, 3)")
    used = np.unique(triangles)
    if not np.all(
        np.isfinite(x[used]) & np.isfinite(span[used]) & np.isfinite(z[used])
    ):
        raise ValueError(f"explicit plot {path.name} contains nonfinite triangle nodes")
    compact_index = np.full(x.size, -1, dtype=np.int64)
    compact_index[used] = np.arange(used.size, dtype=np.int64)
    triangulation = mtri.Triangulation(
        x[used],
        span[used],
        triangles=compact_index[triangles],
    )
    fig, ax = plt.subplots(figsize=(8.0, 4.8), dpi=180)
    try:
        artist = ax.tripcolor(
            triangulation,
            z[used],
            shading="flat",
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
        )
        fig.colorbar(artist, ax=ax, label=colorbar_label)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("x (m)")
        ax.set_ylabel("span (m)")
        ax.set_aspect("equal", adjustable="box")
        fig.tight_layout()
        fig.savefig(path)
    finally:
        plt.close(fig)

def _plot_categorical_surface(
    *,
    path: Path,
    x_m: np.ndarray,
    span_m: np.ndarray,
    triangle_node_ids: np.ndarray,
    categories: tuple[tuple[str, np.ndarray, str], ...],
    title: str,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri
    from matplotlib.colors import ListedColormap

    x = np.asarray(x_m, dtype=np.float64)
    span = np.asarray(span_m, dtype=np.float64)
    triangles = np.asarray(triangle_node_ids, dtype=np.int64)
    if x.ndim != 1 or span.shape != x.shape:
        raise ValueError("categorical node coordinates must be matching 1D arrays")
    if triangles.ndim != 2 or triangles.shape[1] != 3 or triangles.size == 0:
        raise ValueError("categorical plot requires explicit triangles")
    node_category = np.full(x.size, -1, dtype=np.int64)
    labels: list[str] = []
    colors: list[str] = []
    for category_id, (label, raw_mask, color) in enumerate(categories):
        mask = np.asarray(raw_mask, dtype=np.bool_)
        if mask.shape != x.shape:
            raise ValueError("categorical mask must have one value per product node")
        node_category[mask] = category_id
        labels.append(label)
        colors.append(color)
    if np.any(node_category[np.unique(triangles)] < 0):
        raise ValueError(f"categorical plot {path.name} has unclassified triangle nodes")
    face_category = np.asarray(
        [
            np.bincount(node_category[triangle], minlength=len(categories)).argmax()
            for triangle in triangles
        ],
        dtype=np.float64,
    )
    used = np.unique(triangles)
    compact_index = np.full(x.size, -1, dtype=np.int64)
    compact_index[used] = np.arange(used.size, dtype=np.int64)
    triangulation = mtri.Triangulation(
        x[used],
        span[used],
        triangles=compact_index[triangles],
    )
    fig, ax = plt.subplots(figsize=(8.0, 4.8), dpi=180)
    try:
        ax.tripcolor(
            triangulation,
            facecolors=face_category,
            shading="flat",
            cmap=ListedColormap(colors),
            vmin=-0.5,
            vmax=len(colors) - 0.5,
        )
        present = np.unique(face_category).astype(np.int64)
        ax.legend(
            handles=[
                mpatches.Patch(color=colors[index], label=labels[index])
                for index in present
            ],
            loc="best",
            fontsize=7,
            frameon=True,
        )
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("x (m)")
        ax.set_ylabel("span (m)")
        ax.set_aspect("equal", adjustable="box")
        fig.tight_layout()
        fig.savefig(path)
    finally:
        plt.close(fig)

def _build_comparison_contour_mesh(
    *,
    x_m: np.ndarray,
    span_m: np.ndarray,
    values: np.ndarray,
    comparison_valid: np.ndarray,
    mapping_support_limit_m: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build a Delaunay mesh from supported comparison samples."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.tri as mtri

    x = np.asarray(x_m, dtype=np.float64)
    span = np.asarray(span_m, dtype=np.float64)
    z = np.asarray(values, dtype=np.float64)
    valid = np.asarray(comparison_valid, dtype=np.bool_)
    support_limit = np.asarray(mapping_support_limit_m, dtype=np.float64)
    if not (x.shape == span.shape == z.shape == valid.shape == support_limit.shape):
        raise ValueError("comparison contour arrays must have identical shapes")
    if x.ndim != 1:
        raise ValueError("comparison contour arrays must be one-dimensional")

    coordinate_valid = np.isfinite(x) & np.isfinite(span)
    if np.count_nonzero(coordinate_valid) < 3:
        raise ValueError("comparison contour has fewer than three finite coordinates")
    coordinates = np.column_stack((x[coordinate_valid], span[coordinate_valid]))
    finite_values = z[coordinate_valid]
    finite_support = support_limit[coordinate_valid]
    row_supported = (
        valid[coordinate_valid]
        & np.isfinite(finite_values)
        & np.isfinite(finite_support)
        & (finite_support > 0.0)
    )
    supported_coordinates = coordinates[row_supported]
    if supported_coordinates.shape[0] < 3:
        raise ValueError("comparison contour has fewer than three supported coordinates")
    unique_coordinates, supported_inverse = np.unique(
        supported_coordinates, axis=0, return_inverse=True
    )
    if unique_coordinates.shape[0] < 3:
        raise ValueError("comparison contour has fewer than three supported coordinates")
    supported_count = np.bincount(
        supported_inverse, minlength=unique_coordinates.shape[0]
    )
    contour_values = np.bincount(
        supported_inverse,
        weights=finite_values[row_supported],
        minlength=unique_coordinates.shape[0],
    ) / supported_count

    try:
        triangles = np.asarray(
            mtri.Triangulation(
                unique_coordinates[:, 0], unique_coordinates[:, 1]
            ).triangles,
            dtype=np.int64,
        )
    except (RuntimeError, ValueError) as error:
        raise ValueError("comparison contour triangulation failed") from error
    triangle_mask = np.zeros(triangles.shape[0], dtype=np.bool_)
    return (
        unique_coordinates[:, 0],
        unique_coordinates[:, 1],
        contour_values,
        triangles,
        triangle_mask,
    )


def _comparison_auto_color_limits(
    *, values: np.ndarray, comparison_valid: np.ndarray
) -> tuple[float, float]:
    """Return finite supported extrema, padding only a constant field."""

    z = np.asarray(values, dtype=np.float64)
    valid = np.asarray(comparison_valid, dtype=np.bool_)
    if z.shape != valid.shape:
        raise ValueError("comparison values and validity mask must have identical shapes")
    supported_values = z[valid & np.isfinite(z)]
    if supported_values.size == 0:
        raise ValueError("comparison has no finite supported values")
    vmin = float(np.min(supported_values))
    vmax = float(np.max(supported_values))
    if vmin == vmax:
        padding = max(abs(vmin), 1.0) * 1.0e-9
        return vmin - padding, vmax + padding
    return vmin, vmax


def _plot_comparison_surface(
    *,
    path: Path,
    x_m: np.ndarray,
    span_m: np.ndarray,
    values: np.ndarray,
    comparison_valid: np.ndarray,
    mapping_support_limit_m: np.ndarray,
    title: str,
    colorbar_label: str,
    vmin: float,
    vmax: float,
    extend: Literal["neither", "both"] = "both",
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri

    x = np.asarray(x_m, dtype=np.float64)
    span = np.asarray(span_m, dtype=np.float64)
    z = np.asarray(values, dtype=np.float64)
    supported = np.asarray(comparison_valid, dtype=np.bool_)
    support_limit = np.asarray(mapping_support_limit_m, dtype=np.float64)
    if not (x.shape == span.shape == z.shape == supported.shape == support_limit.shape):
        raise ValueError("comparison plot arrays must have identical shapes")
    contour_x, contour_span, contour_z, triangles, triangle_mask = (
        _build_comparison_contour_mesh(
            x_m=x,
            span_m=span,
            values=z,
            comparison_valid=supported,
            mapping_support_limit_m=support_limit,
        )
    )
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin >= vmax:
        raise ValueError("comparison contour color limits must be finite and increasing")
    fig, ax = plt.subplots(figsize=(8.0, 4.8), dpi=180)
    try:
        triangulation = mtri.Triangulation(
            contour_x,
            contour_span,
            triangles=triangles,
            mask=triangle_mask,
        )
        artist = ax.tricontourf(
            triangulation,
            contour_z,
            levels=np.linspace(vmin, vmax, 41, dtype=np.float64),
            cmap="coolwarm",
            extend=extend,
        )
        colorbar = fig.colorbar(artist, ax=ax, label=colorbar_label, extend=extend)
        if extend == "neither":
            colorbar.set_ticks(np.linspace(vmin, vmax, 7, dtype=np.float64))
        ax.set_facecolor("#eeeeee")
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("x (m)")
        ax.set_ylabel("span (m)")
        ax.set_aspect("equal", adjustable="box")
        fig.tight_layout()
        fig.savefig(path)
    finally:
        plt.close(fig)


def validate_n8_run_artifacts(run_dir: str | Path) -> dict[str, Any]:
    directory = Path(run_dir).resolve()
    actual = tuple(sorted(path.name for path in directory.iterdir() if path.is_file()))
    if actual != tuple(sorted(_EXPECTED_ARTIFACTS)):
        raise ValueError(f"N8 run artifact set mismatch: {actual}")
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    stats = json.loads((directory / "Taw_error_stats.json").read_text(encoding="utf-8"))
    if summary.get("schema") != _SUMMARY_SCHEMA or summary.get("status") != "PASS":
        raise ValueError("N8 summary is not PASS")
    if stats.get("schema") != _STATS_SCHEMA or stats.get("status") != "PASS":
        raise ValueError("N8 error stats are not PASS")
    for sheet in _SHEETS:
        sheet_stats = stats.get("sheets", {}).get(sheet, {})
        if (
            sheet_stats.get("status") != "PASS"
            or int(sheet_stats.get("paired_source_rows", 0)) <= 0
        ):
            raise ValueError(f"{sheet} stats are empty or failed")
        if int(sheet_stats.get("comparison_supported_rows", 0)) <= 0:
            raise ValueError(f"{sheet} has no locally supported comparisons")
        if int(sheet_stats.get("unique_lf_targets", 0)) <= 0:
            raise ValueError(f"{sheet} has no unique LF target")
    projection_cache = summary.get("contracts", {}).get("projection_cache")
    if not isinstance(projection_cache, Mapping):
        raise TypeError("N8 summary has no projection-cache contract")
    if (
        projection_cache.get("schema") != PROJECTION_CACHE_SCHEMA
        or projection_cache.get("algorithm") != PROJECTION_ALGORITHM_VERSION
        or projection_cache.get("identity_scope") != "canonical_geometry"
        or not isinstance(projection_cache.get("hit"), bool)
    ):
        raise ValueError("N8 projection-cache contract version is invalid")
    for key in ("key", "sha256"):
        value = projection_cache.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"N8 projection-cache {key} is not a SHA-256 identity")
    cache_identity = projection_cache.get("identity")
    if not isinstance(cache_identity, Mapping) or set(cache_identity) != {
        "projection_input_geometry_sha256",
        "fluent_canonical_geometry_sha256",
        "triangle_canonical_sha256",
    }:
        raise ValueError("N8 projection-cache geometry identity is incomplete")
    if not all(
        isinstance(value, str) and len(value) == 64 for value in cache_identity.values()
    ):
        raise ValueError("N8 projection-cache geometry identity is malformed")
    with np.load(directory / "Taw_surface_fields.npz", allow_pickle=False) as archive:
        required = {
            "node_id",
            "legacy_phase9_canonical_index",
            "geometric_sheet",
            "domain_role",
            "source_stl_triangle_id",
            "source_stl_edge_id",
            "triangle_id",
            "triangle_node_ids",
            "triangle_geometric_sheet",
            "triangle_source_stl_triangle_id",
            "domain_topology_schema",
            "domain_topology_sha256",
            "excluded_legacy_phase9_canonical_index",
            "excluded_geometry_failure_reason",
            "surface_class",
            "surface_class_code",
            "incidence_s",
            "stl_face_incidence_s",
            "normal_out",
            "stl_face_normal_out",
            "normal_smoothing_angle_deg",
            "sx",
            "sy",
            "normal_crease_angle_deg",
            "normal_model_schema",
            "provider",
            "geometry_failure_reason",
            "Taw_windward_candidate_K",
            "Taw_recovery_candidate_K",
            "windward_blend_weight",
            "taw_dispatch_schema",
            "x_m",
            "span_m",
            "Taw_prediction_K",
            "geometry_valid",
            "valid",
            "failure_reason",
        }
        if not required.issubset(archive.files):
            raise ValueError("N8 fields NPZ is missing canonical fields")
        node_id = np.asarray(archive["node_id"], dtype=np.int64)
        triangle_id = np.asarray(archive["triangle_id"], dtype=np.int64)
        triangle_node_ids = np.asarray(archive["triangle_node_ids"], dtype=np.int64)
        triangle_sheet = np.asarray(archive["triangle_geometric_sheet"])
        node_sheet = np.asarray(archive["geometric_sheet"])
        source_triangle_id = np.asarray(
            archive["source_stl_triangle_id"], dtype=np.int64
        )
        if not np.array_equal(node_id, np.arange(node_id.size, dtype=np.int64)):
            raise ValueError("N8 product node IDs are not contiguous")
        if not np.array_equal(
            triangle_id, np.arange(triangle_id.size, dtype=np.int64)
        ):
            raise ValueError("N8 product triangle IDs are not contiguous")
        if (
            triangle_node_ids.ndim != 2
            or triangle_node_ids.shape != (triangle_id.size, 3)
            or np.any(triangle_node_ids < 0)
            or np.any(triangle_node_ids >= node_id.size)
        ):
            raise ValueError("N8 explicit triangle connectivity is invalid")
        if not np.all(node_sheet[triangle_node_ids] == triangle_sheet[:, None]):
            raise ValueError("N8 product triangle crosses geometric sheets")
        if str(np.asarray(archive["domain_topology_schema"]).item()) != _TOPOLOGY_SCHEMA:
            raise ValueError("N8 domain topology schema mismatch")
        topology_hash = _topology_hash(
            x_m=archive["x_m"],
            span_m=archive["span_m"],
            z_m=archive["z_m"],
            triangle_node_ids=triangle_node_ids,
            triangle_geometric_sheet=triangle_sheet,
            triangle_source_stl_triangle_id=archive[
                "triangle_source_stl_triangle_id"
            ],
        )
        if topology_hash != str(
            np.asarray(archive["domain_topology_sha256"]).item()
        ):
            raise ValueError("N8 domain topology hash mismatch")
        topology_contract = summary.get("contracts", {}).get("domain_topology", {})
        if (
            topology_contract.get("schema") != _TOPOLOGY_SCHEMA
            or topology_contract.get("sha256") != topology_hash
        ):
            raise ValueError("N8 summary domain topology identity mismatch")
        geometry_valid = np.asarray(archive["geometry_valid"], dtype=np.bool_)
        provider_valid = np.asarray(archive["valid"], dtype=np.bool_)
        if not np.all(geometry_valid):
            raise ValueError("N8 product node table contains excluded geometry")
        if np.any(source_triangle_id < 0):
            raise ValueError("N8 product node has no source STL triangle")
        if not np.array_equal(provider_valid, geometry_valid):
            raise ValueError("N8 provider coverage does not equal geometry coverage")
        if not np.all(np.isfinite(archive["Taw_prediction_K"][provider_valid])):
            raise ValueError("N8 provider-valid Taw contains nonfinite values")
        if str(np.asarray(archive["taw_dispatch_schema"]).item()) != _DISPATCH_SCHEMA:
            raise ValueError("N8 Taw dispatch schema mismatch")
        if (
            str(np.asarray(archive["normal_model_schema"]).item())
            != _NORMAL_MODEL_SCHEMA
        ):
            raise ValueError("N8 continuous-normal schema mismatch")
        crease_angle_deg = float(np.asarray(archive["normal_crease_angle_deg"]).item())
        if crease_angle_deg != _NORMAL_CREASE_ANGLE_DEG:
            raise ValueError("N8 continuous-normal crease threshold mismatch")
        incidence = np.asarray(archive["incidence_s"], dtype=np.float64)
        face_incidence = np.asarray(archive["stl_face_incidence_s"], dtype=np.float64)
        normal = np.asarray(archive["normal_out"], dtype=np.float64)
        face_normal = np.asarray(archive["stl_face_normal_out"], dtype=np.float64)
        smoothing_angle = np.asarray(
            archive["normal_smoothing_angle_deg"], dtype=np.float64
        )
        sx = np.asarray(archive["sx"], dtype=np.float64)
        sy = np.asarray(archive["sy"], dtype=np.float64)
        if not (
            np.all(np.isfinite(incidence[geometry_valid]))
            and np.all(np.isfinite(face_incidence[geometry_valid]))
            and np.all(np.isfinite(normal[geometry_valid]))
            and np.all(np.isfinite(face_normal[geometry_valid]))
            and np.all(np.isfinite(smoothing_angle[geometry_valid]))
            and np.all(np.isfinite(sx[geometry_valid]))
            and np.all(np.isfinite(sy[geometry_valid]))
        ):
            raise ValueError("N8 valid geometry has incomplete normal audit fields")
        if not (
            np.all(np.isnan(incidence[~geometry_valid]))
            and np.all(np.isnan(face_incidence[~geometry_valid]))
            and np.all(np.isnan(normal[~geometry_valid]))
            and np.all(np.isnan(face_normal[~geometry_valid]))
            and np.all(np.isnan(smoothing_angle[~geometry_valid]))
            and np.all(np.isnan(sx[~geometry_valid]))
            and np.all(np.isnan(sy[~geometry_valid]))
        ):
            raise ValueError("N8 invalid geometry has populated normal audit fields")
        if not (
            np.allclose(
                np.linalg.norm(normal[geometry_valid], axis=1), 1.0, atol=1.0e-10
            )
            and np.allclose(
                np.linalg.norm(face_normal[geometry_valid], axis=1),
                1.0,
                atol=1.0e-10,
            )
        ):
            raise ValueError("N8 surface normals are not unit vectors")
        if not np.all(
            (smoothing_angle[geometry_valid] >= 0.0)
            & (smoothing_angle[geometry_valid] <= crease_angle_deg + 1.0e-8)
        ):
            raise ValueError("N8 continuous-normal smoothing angle is out of bounds")
        expected_smoothing_angle = np.rad2deg(
            np.arccos(
                np.clip(
                    np.sum(
                        normal[geometry_valid] * face_normal[geometry_valid], axis=1
                    ),
                    -1.0,
                    1.0,
                )
            )
        )
        if not np.allclose(
            smoothing_angle[geometry_valid],
            expected_smoothing_angle,
            rtol=0.0,
            atol=1.0e-10,
        ):
            raise ValueError("N8 normal smoothing audit angle is inconsistent")
        if not (
            np.allclose(
                sx[geometry_valid],
                -normal[geometry_valid, 0] / normal[geometry_valid, 2],
                rtol=0.0,
                atol=1.0e-12,
            )
            and np.allclose(
                sy[geometry_valid],
                -normal[geometry_valid, 1] / normal[geometry_valid, 2],
                rtol=0.0,
                atol=1.0e-12,
            )
        ):
            raise ValueError("N8 windward slopes do not derive from continuous normals")
        if source_triangle_id.shape != geometry_valid.shape:
            raise ValueError("N8 source STL triangle identity is not node-aligned")
        expected_incidence, expected_class = classify_incidence(
            normal_out=normal, alpha_deg=float(summary["inputs"]["alpha_deg"])
        )
        expected_face_incidence, _ = classify_incidence(
            normal_out=face_normal, alpha_deg=float(summary["inputs"]["alpha_deg"])
        )
        if not (
            np.allclose(incidence, expected_incidence, equal_nan=True)
            and np.allclose(face_incidence, expected_face_incidence, equal_nan=True)
            and np.array_equal(
                np.asarray(archive["surface_class_code"], dtype=np.int8),
                expected_class,
            )
        ):
            raise ValueError(
                "N8 incidence fields do not derive from their declared normals"
            )
        provider = np.asarray(archive["provider"])
        failure_reason = np.asarray(archive["failure_reason"])
        geometry_reason = np.asarray(archive["geometry_failure_reason"])
        recovery = np.asarray(archive["Taw_recovery_candidate_K"], dtype=np.float64)
        windward = np.asarray(archive["Taw_windward_candidate_K"], dtype=np.float64)
        weight = np.asarray(archive["windward_blend_weight"], dtype=np.float64)
        if not np.all(np.isfinite(recovery[geometry_valid])):
            raise ValueError("N8 recovery candidate does not cover valid geometry")
        if not (
            np.all(np.isfinite(weight[geometry_valid]))
            and np.all(
                (weight[geometry_valid] >= 0.0) & (weight[geometry_valid] <= 1.0)
            )
            and np.all(np.isnan(weight[~geometry_valid]))
        ):
            raise ValueError("N8 blend weights violate domain or bounds")
        needs_windward = geometry_valid & (weight > 0.0)
        if not np.all(np.isfinite(windward[needs_windward])):
            raise ValueError(
                "N8 windward candidate does not cover its transition domain"
            )
        if not (
            np.all(provider[geometry_valid & (weight == 0.0)] == "leeward_recovery")
            and np.all(
                provider[geometry_valid & (weight == 1.0)] == "windward_turbulent"
            )
            and np.all(
                provider[geometry_valid & (weight > 0.0) & (weight < 1.0)]
                == "near_tangent_blend"
            )
        ):
            raise ValueError("N8 provider labels disagree with blend weights")
        if not (
            np.all(failure_reason[provider_valid] == "")
            and np.all(failure_reason[~provider_valid] != "")
            and np.all(geometry_reason[geometry_valid] == "")
            and np.all(geometry_reason[~geometry_valid] != "")
        ):
            raise ValueError("N8 provider or geometry reasons are inconsistent")
        auto_range_contract = summary.get("contracts", {}).get(
            "signed_relative_error_auto_range_pct"
        )
        if not isinstance(auto_range_contract, Mapping):
            raise TypeError("N8 summary has no automatic error-range contract")
        for sheet in _SHEETS:
            if (
                f"source_row_index_{sheet}" not in archive.files
                or archive[f"source_row_index_{sheet}"].size == 0
            ):
                raise ValueError(f"N8 fields NPZ has no {sheet} source-row comparison")
            comparison_valid = np.asarray(
                archive[f"comparison_valid_{sheet}"], dtype=np.bool_
            )
            failure_reason = np.asarray(archive[f"comparison_failure_reason_{sheet}"])
            signed_error = np.asarray(
                archive[f"signed_error_K_{sheet}"], dtype=np.float64
            )
            if not np.any(comparison_valid):
                raise ValueError(f"N8 fields NPZ has no supported {sheet} comparison")
            if not np.all(failure_reason[comparison_valid] == "") or not np.all(
                failure_reason[~comparison_valid] == _MAPPING_UNSUPPORTED
            ):
                raise ValueError(f"N8 {sheet} mapping support reasons are inconsistent")
            if not np.all(np.isfinite(signed_error[comparison_valid])) or not np.all(
                np.isnan(signed_error[~comparison_valid])
            ):
                raise ValueError(
                    f"N8 {sheet} unsupported errors are not explicitly masked"
                )
            signed_relative_error = np.asarray(
                archive[f"signed_relative_error_pct_{sheet}"], dtype=np.float64
            )
            expected_vmin, expected_vmax = _comparison_auto_color_limits(
                values=signed_relative_error,
                comparison_valid=comparison_valid,
            )
            sheet_auto_range = auto_range_contract.get(sheet)
            if not isinstance(sheet_auto_range, Mapping) or (
                sheet_auto_range.get("min") != expected_vmin
                or sheet_auto_range.get("max") != expected_vmax
            ):
                raise ValueError(f"N8 {sheet} automatic error range is inconsistent")
    import matplotlib.image as mpimg

    image_report: dict[str, Any] = {}
    for name in _EXPECTED_ARTIFACTS[3:]:
        path = directory / name
        pixels = np.asarray(mpimg.imread(path))
        if (
            path.stat().st_size <= 0
            or pixels.size == 0
            or not np.all(np.isfinite(pixels))
            or float(np.std(pixels)) <= 0.0
        ):
            raise ValueError(f"PNG is empty, unreadable, or blank: {name}")
        image_report[name] = {
            "byte_size": int(path.stat().st_size),
            "shape": list(pixels.shape),
            "pixel_std": float(np.std(pixels)),
        }
    return {
        "status": "PASS",
        "artifact_count": len(_EXPECTED_ARTIFACTS),
        "images": image_report,
    }


def _require_override(name: str, actual: float, expected: float) -> None:
    if Decimal(str(actual)) != Decimal(str(expected)):
        raise ValueError(f"explicit {name} does not exactly match the N8 case spec")


def run_n8_taw_case(
    *,
    repo_root: str | Path,
    case_spec_path: str | Path,
    run_dir: str | Path,
    mach: float,
    alpha_deg: float,
    T_inf_K: float | None = None,
    p_inf_Pa: float | None = None,
    h_m: float | None = None,
) -> N8RunResult:
    root = Path(repo_root).resolve()
    observation_case = load_n8_taw_case_spec(case_spec_path, repo_root=root)
    sampling = load_n8_sampling_spec(observation_case.sampling_spec, repo_root=root)
    for name, actual, expected in (
        ("mach", mach, observation_case.mach),
        ("alpha_deg", alpha_deg, observation_case.alpha_deg),
    ):
        _require_override(name, actual, expected)

    freestream = resolve_n8_freestream(
        h_m=h_m,
        T_inf_K=T_inf_K,
        p_inf_Pa=p_inf_Pa,
        R_J_per_kgK=observation_case.R_J_per_kgK,
    )
    if freestream.source == "explicit_custom":
        _require_override("T_inf_K", freestream.T_inf_K, observation_case.T_inf_K)
        _require_override("p_inf_Pa", freestream.p_inf_Pa, observation_case.p_inf_Pa)
    elif Decimal(str(float(freestream.altitude_input_m) / 1000.0)) != Decimal(
        str(observation_case.h_label_km)
    ):
        raise ValueError(
            "USSA1976 altitude does not match the observation height label"
        )

    case = replace(
        observation_case,
        T_inf_K=freestream.T_inf_K,
        p_inf_Pa=freestream.p_inf_Pa,
    )

    csv_path = _repo_path(root, case.observation_csv, label="case.observation_csv")
    binding = build_observation_binding(root, csv_path=case.observation_csv)
    binding_ok, binding_error = validate_observation_binding(binding, repo_root=root)
    if not binding_ok:
        raise ValueError(f"observation binding failed: {binding_error}")
    if freestream.source == "explicit_custom":
        require_exact_freestream_pair(
            binding,
            T_inf_K=freestream.T_inf_K,
            p_inf_Pa=freestream.p_inf_Pa,
        )
    identity = binding.filename_identity
    for name, actual, expected in (
        ("mach", identity.mach, case.mach),
        ("alpha_deg", identity.alpha_deg, case.alpha_deg),
        ("h_label_km", identity.nominal_altitude_km, case.h_label_km),
    ):
        if Decimal(str(actual)) != Decimal(str(expected)):
            raise ValueError(f"observation filename {name} does not match case spec")

    output_relative = Path(run_dir).as_posix()
    final_dir = _repo_path(root, output_relative, label="run_dir")
    runs_root = (root / "runs" / "n8_taw_surface").resolve()
    try:
        final_dir.relative_to(runs_root)
    except ValueError as error:
        raise ValueError("N8 run_dir must be under runs/n8_taw_surface") from error
    if final_dir.exists():
        raise ValueError(f"N8 run_dir already exists: {final_dir}")
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix=f".{final_dir.name}.tmp-", dir=final_dir.parent)
    )

    try:
        geometry_inputs = _load_geometry_inputs(root, case)
        gas = _gas_model(case)
        legacy_fields = _build_lf_surface_fields(
            case=case,
            sampling=sampling,
            geometry=geometry_inputs,
            gas=gas,
        )
        fields = _build_domain_conforming_product(
            legacy_fields=legacy_fields,
            case=case,
            sampling=sampling,
            geometry=geometry_inputs,
            gas=gas,
        )
        valid = np.asarray(fields["valid"], dtype=np.bool_)
        geometry_valid = np.asarray(fields["geometry_valid"], dtype=np.bool_)
        if not np.array_equal(valid, geometry_valid):
            missing = int(np.count_nonzero(geometry_valid & ~valid))
            extra = int(np.count_nonzero(valid & ~geometry_valid))
            raise ValueError(
                "N8 provider coverage must equal geometry coverage; "
                f"missing={missing} extra={extra}"
            )
        if not np.any(valid & (fields["geometric_sheet"] == "upper")) or not np.any(
            valid & (fields["geometric_sheet"] == "lower")
        ):
            raise ValueError("upper and lower LF Taw fields must both be nonempty")

        fluent_geometry = read_fluent_surface_geometry_csv(
            csv_path, x_offset_m=case.fluent_x_offset_m
        )
        canonical_geometry_sha256 = hashlib.sha256(
            np.ascontiguousarray(fluent_geometry.canonical_solver_xyz).tobytes(
                order="C"
            )
        ).hexdigest()
        projection_identity_kwargs = {
            "x_offset_m": case.fluent_x_offset_m,
            "stl_path": geometry_inputs.stl_path,
            "vehicle_spec_path": geometry_inputs.vehicle_spec_path,
            "sampling_spec_path": geometry_inputs.sampling_spec_path,
            "outline_path": geometry_inputs.outline_path,
        }
        projection_identity = build_geometry_identity(
            fluent_geometry_source_path=fluent_geometry.source_path,
            fluent_canonical_geometry_sha256=canonical_geometry_sha256,
            canonical_point_count=fluent_geometry.canonical_solver_xyz.shape[0],
            triangles=geometry_inputs.triangles,
            projection_gate_m=case.projection_gate_m,
            **projection_identity_kwargs,
        )
        projection_identity["fluent_source_geometry_sha256"] = canonical_geometry_sha256
        projection_cache_key = hashlib.sha256(
            json.dumps(
                projection_identity,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        projection_cache_path = (
            runs_root / "_projection_cache" / f"{projection_cache_key}.npz"
        )
        projection_cache_hit = projection_cache_path.is_file()
        projection = project_fluent_surface_with_cache(
            fluent_geometry,
            geometry_inputs.triangles,
            projection_gate_m=case.projection_gate_m,
            use_bvh=True,
            cache_path=projection_cache_path,
            write_cache=True,
            geometry_identity_kwargs=projection_identity_kwargs,
            cache_identity_scope="canonical_geometry",
        )
        integration = integrate_fluent_projected_semantics(
            geometry=fluent_geometry,
            projection=projection,
            triangles=geometry_inputs.triangles,
            alpha_deg=case.alpha_deg,
            planform_b_half_m=geometry_inputs.b_half_m,
            chord_min_m=geometry_inputs.f3.chord_min_m,
            upper_reference_normal_out=geometry_inputs.upper_reference_normal,
            lower_reference_normal_out=geometry_inputs.lower_reference_normal,
            outline_x_m=geometry_inputs.outline_x_m,
            outline_span_m=geometry_inputs.outline_span_m,
        )
        source_temperature, source_sha256 = read_fluent_wall_temperature_source(
            csv_path
        )
        if (
            source_sha256 != binding.raw_sha256
            or source_temperature.size != binding.row_count
        ):
            raise ValueError(
                "wall-temperature and observation binding identities differ"
            )
        canonical_temperature = source_temperature[
            fluent_geometry.canonical_to_source_row
        ]
        semantic_valid = semantic_valid_mask(integration.semantics)
        source_base_valid = (
            projection.projection_gate_pass
            & semantic_valid
            & integration.semantics.planform_parameterization_valid
        )

        comparisons: dict[str, N8SheetComparison] = {}
        pairings: dict[str, N8Pairing] = {}
        stats_by_sheet: dict[str, Any] = {}
        sheet_codes = {"upper": GEOMETRIC_SHEET_UPPER, "lower": GEOMETRIC_SHEET_LOWER}
        for sheet in _SHEETS:
            source_sheet_all = (
                integration.semantics.geometric_sheet == sheet_codes[sheet]
            )
            source_mask = source_base_valid & source_sheet_all
            source_index = np.flatnonzero(source_mask).astype(np.int64)
            target_mask = valid & (fields["geometric_sheet"] == sheet)
            target_index = np.flatnonzero(target_mask).astype(np.int64)
            comparison, pairing = _build_comparison(
                sheet=sheet,
                source_csv_sha256=source_sha256,
                source_canonical_index=source_index,
                source_row_index=fluent_geometry.canonical_to_source_row[source_index],
                source_surface_class=integration.semantics.surface_class[source_index],
                source_wall_temperature_K=canonical_temperature[source_index],
                source_x_span_m=projection.projected_xyz[source_index][:, (0, 1)],
                target_canonical_index=target_index,
                target_surface_class=fields["surface_class_code"][target_index],
                target_Taw_K=fields["Taw_prediction_K"][target_index],
                target_x_span_m=np.column_stack(
                    (fields["x_m"][target_index], fields["span_m"][target_index])
                ),
                target_support_radius_m=fields["mapping_support_radius_m"][
                    target_index
                ],
            )
            comparisons[sheet] = comparison
            pairings[sheet] = pairing
            stats_by_sheet[sheet] = _comparison_stats(
                comparison=comparison,
                pairing=pairing,
                raw_source_rows=binding.row_count,
                geometric_sheet_source_rows=int(np.count_nonzero(source_sheet_all)),
                target_valid_count=int(np.count_nonzero(target_mask)),
            )

        npz_fields: dict[str, np.ndarray] = {
            key: np.asarray(value) for key, value in fields.items()
        }
        for sheet, comparison in comparisons.items():
            for key in (
                "source_canonical_index",
                "source_row_index",
                "source_surface_class",
                "target_canonical_index",
                "target_surface_class",
                "pairing_distance_m",
                "mapping_support_limit_m",
                "comparison_valid",
                "comparison_failure_reason",
                "target_multiplicity",
                "wall_temperature_K",
                "Taw_prediction_K",
                "signed_error_K",
                "signed_relative_error_pct",
                "absolute_error_K",
                "absolute_relative_error_pct",
            ):
                npz_fields[f"{key}_{sheet}"] = np.asarray(getattr(comparison, key))
        npz_fields["source_csv_sha256"] = np.asarray(source_sha256)
        npz_fields["freestream_source"] = np.asarray(freestream.source)
        npz_fields["freestream_T_inf_K"] = np.asarray(freestream.T_inf_K)
        npz_fields["freestream_p_inf_Pa"] = np.asarray(freestream.p_inf_Pa)
        npz_fields["freestream_rho_inf_kg_m3"] = np.asarray(freestream.rho_inf_kg_m3)
        npz_fields["grid_nx"] = np.asarray(sampling.nx, dtype=np.int64)
        npz_fields["grid_ny"] = np.asarray(sampling.ny, dtype=np.int64)
        npz_fields["taw_dispatch_schema"] = np.asarray(_DISPATCH_SCHEMA)
        npz_fields["normal_model_schema"] = np.asarray(_NORMAL_MODEL_SCHEMA)
        npz_fields["normal_crease_angle_deg"] = np.asarray(
            _NORMAL_CREASE_ANGLE_DEG, dtype=np.float64
        )
        np.savez_compressed(temp_dir / "Taw_surface_fields.npz", **npz_fields)

        stats_document = {
            "schema": _STATS_SCHEMA,
            "status": "PASS",
            "case_id": case.case_id,
            "source_csv": case.observation_csv,
            "source_csv_sha256": source_sha256,
            "freestream": {
                "source": freestream.source,
                "T_inf_K": freestream.T_inf_K,
                "p_inf_Pa": freestream.p_inf_Pa,
                "rho_inf_kg_m3": freestream.rho_inf_kg_m3,
                "altitude_input_m": freestream.altitude_input_m,
                "altitude_used_for_freestream": freestream.altitude_used_for_freestream,
            },
            "sheets": stats_by_sheet,
        }
        _write_json(temp_dir / "Taw_error_stats.json", stats_document)

        title_context = (
            f"Ma={case.mach:g} | alpha={case.alpha_deg:g} deg | "
            f"T_inf={case.T_inf_K:g} K | p_inf={case.p_inf_Pa:g} Pa | "
            f"h_label={case.h_label_km:g} km"
        )
        auto_error_ranges: dict[str, dict[str, float]] = {}
        for sheet in _SHEETS:
            node_mask = np.asarray(fields["geometric_sheet"]) == sheet
            triangle_mask = (
                np.asarray(fields["triangle_geometric_sheet"]) == sheet
            )
            sheet_triangles = np.asarray(
                fields["triangle_node_ids"], dtype=np.int64
            )[triangle_mask]
            _plot_explicit_surface(
                path=temp_dir / f"Taw_surface_{sheet}.png",
                x_m=fields["x_m"],
                span_m=fields["span_m"],
                values=fields["Taw_prediction_K"],
                triangle_node_ids=sheet_triangles,
                title=f"Taw | geometric {sheet}\n{title_context}",
                colorbar_label="Taw prediction (K)",
                cmap="viridis",
            )
            _plot_categorical_surface(
                path=temp_dir / f"Taw_provider_{sheet}.png",
                x_m=fields["x_m"],
                span_m=fields["span_m"],
                triangle_node_ids=sheet_triangles,
                categories=(
                    (
                        "windward turbulent",
                        node_mask & (fields["provider"] == "windward_turbulent"),
                        "#d1495b",
                    ),
                    (
                        "leeward recovery",
                        node_mask & (fields["provider"] == "leeward_recovery"),
                        "#2c7fb8",
                    ),
                    (
                        "near-tangent enthalpy blend",
                        node_mask & (fields["provider"] == "near_tangent_blend"),
                        "#f2c14e",
                    ),
                ),
                title=f"Taw provider | geometric {sheet}\n{title_context}",
            )
            _plot_categorical_surface(
                path=temp_dir / f"Taw_validity_{sheet}.png",
                x_m=fields["x_m"],
                span_m=fields["span_m"],
                triangle_node_ids=sheet_triangles,
                categories=(("provider valid", node_mask & fields["valid"], "#2a9d8f"),),
                title=f"Taw validity | geometric {sheet}\n{title_context}",
            )
            comparison = comparisons[sheet]
            source_xy = projection.projected_xyz[comparison.source_canonical_index][
                :, (0, 1)
            ]
            _plot_comparison_surface(
                path=temp_dir / f"Taw_error_vs_fluent_{sheet}.png",
                x_m=source_xy[:, 0],
                span_m=source_xy[:, 1],
                values=comparison.signed_relative_error_pct,
                comparison_valid=comparison.comparison_valid,
                mapping_support_limit_m=comparison.mapping_support_limit_m,
                title=f"Taw signed relative error vs Fluent | geometric {sheet}\n{title_context}",
                colorbar_label="signed relative error (%)",
                vmin=-case.signed_relative_error_limit_pct,
                vmax=case.signed_relative_error_limit_pct,
            )
            auto_vmin, auto_vmax = _comparison_auto_color_limits(
                values=comparison.signed_relative_error_pct,
                comparison_valid=comparison.comparison_valid,
            )
            auto_error_ranges[sheet] = {"min": auto_vmin, "max": auto_vmax}
            _plot_comparison_surface(
                path=temp_dir / f"Taw_error_vs_fluent_{sheet}_auto_range.png",
                x_m=source_xy[:, 0],
                span_m=source_xy[:, 1],
                values=comparison.signed_relative_error_pct,
                comparison_valid=comparison.comparison_valid,
                mapping_support_limit_m=comparison.mapping_support_limit_m,
                title=(
                    "Taw signed relative error vs Fluent (actual range) | "
                    f"geometric {sheet}\n{title_context}"
                ),
                colorbar_label="signed relative error (%)",
                vmin=auto_vmin,
                vmax=auto_vmax,
                extend="neither",
            )

        artifact_identity = {}
        for name in _EXPECTED_ARTIFACTS[1:]:
            path = temp_dir / name
            artifact_identity[name] = {
                "byte_size": int(path.stat().st_size),
                "sha256": _sha256(path),
            }
        summary = {
            "schema": _SUMMARY_SCHEMA,
            "status": "PASS",
            "case_id": case.case_id,
            "inputs": {
                "mach": case.mach,
                "alpha_deg": case.alpha_deg,
                "T_inf_K": case.T_inf_K,
                "p_inf_Pa": case.p_inf_Pa,
                "h_label_km": case.h_label_km,
                "altitude_input_m": freestream.altitude_input_m,
                "altitude_used_for_freestream": freestream.altitude_used_for_freestream,
                "atmosphere_model": (
                    "ussa1976" if freestream.source == "ussa1976" else "none"
                ),
                "freestream_source": freestream.source,
                "freestream_semantics": (
                    "USSA1976 from geometric altitude"
                    if freestream.source == "ussa1976"
                    else "explicit custom pressure and temperature"
                ),
                "observation_freestream_identity": {
                    "T_inf_K": observation_case.T_inf_K,
                    "p_inf_Pa": observation_case.p_inf_Pa,
                    "h_label_km": observation_case.h_label_km,
                },
                "observation_csv": case.observation_csv,
                "source_csv_sha256": source_sha256,
            },
            "contracts": {
                "temperature": "Taw only",
                "flow_regime": "fully turbulent",
                "final_surfaces": ["geometric upper", "geometric lower"],
                "taw_dispatch_schema": _DISPATCH_SCHEMA,
                "surface_normal": (
                    "N8 incidence classification and windward candidate slopes use "
                    "angle-weighted continuous STL vertex normals"
                ),
                "normal_model_schema": _NORMAL_MODEL_SCHEMA,
                "normal_crease_angle_deg": _NORMAL_CREASE_ANGLE_DEG,
                "normal_responsibility": (
                    "STL faces retain position, geometric sheet, triangle identity, "
                    "support, and audit ownership; continuous normals own N8 incidence "
                    "and windward slopes; smoothing never crosses the crease threshold"
                ),
                "historical_scope": (
                    "frozen Group 8 and N6/N7 certification retain their original "
                    "normal semantics and are not retrospectively recomputed"
                ),
                "near_tangent": (
                    "s <= 0 uses freestream recovery; 0 < s < 0.05 uses a C1 "
                    "smoothstep blend in enthalpy space; s >= 0.05 uses the "
                    "fully turbulent windward candidate"
                ),
                "candidate_fields": (
                    "windward and freestream-recovery Taw candidates plus the windward "
                    "blend weight are serialized for every applicable geometry point"
                ),
                "geometry_failure_semantics": (
                    "the product node table contains only authoritative graph-skin "
                    "nodes; legacy phase9 exclusions remain in a typed audit table"
                ),
                "domain_topology": {
                    "schema": _TOPOLOGY_SCHEMA,
                    "sha256": str(fields["domain_topology_sha256"]),
                    "node_count": int(fields["node_id"].size),
                    "triangle_count": int(fields["triangle_id"].size),
                    "legacy_exclusion_count": int(
                        fields["excluded_legacy_phase9_canonical_index"].size
                    ),
                },
                "provider_coverage": "provider_valid equals geometry_valid",
                "surface_connectivity": (
                    "explicit graph-skin-clipped triangle_node_ids shared by plotting "
                    "and local mapping support; topology terminates on skin/cap edges"
                ),
                "pairing": (
                    "Fluent source rows preserved; comparison valid only within each "
                    "target vertex's local valid-triangle support radius"
                ),
                "surface_rendering": (
                    "flat colors on explicit domain triangles; no reshape or invalid "
                    "vertex mask defines the product boundary"
                ),
                "comparison_rendering": (
                    "filled triangular contours from supported Fluent projected samples; "
                    "sparse unsupported samples remain excluded from statistics and are "
                    "interpolated over within the supported-sample convex hull"
                ),
                "error_direction": "prediction - observation",
                "signed_relative_error_color_limit_pct": case.signed_relative_error_limit_pct,
                "signed_relative_error_auto_range_pct": auto_error_ranges,
                "projection_cache": {
                    "schema": PROJECTION_CACHE_SCHEMA,
                    "algorithm": PROJECTION_ALGORITHM_VERSION,
                    "identity_scope": "canonical_geometry",
                    "key": projection_cache_key,
                    "hit": projection_cache_hit,
                    "path": projection_cache_path.relative_to(root).as_posix(),
                    "sha256": _sha256(projection_cache_path),
                    "identity": {
                        "projection_input_geometry_sha256": projection_identity[
                            "fluent_source_geometry_sha256"
                        ],
                        "fluent_canonical_geometry_sha256": canonical_geometry_sha256,
                        "triangle_canonical_sha256": projection_identity[
                            "triangle_canonical_sha256"
                        ],
                    },
                },
            },
            "lf_product_nodes": int(fields["node_id"].size),
            "lf_product_triangles": int(fields["triangle_id"].size),
            "legacy_phase9_exclusions": int(
                fields["excluded_legacy_phase9_canonical_index"].size
            ),
            "lf_valid_points": {
                sheet: int(
                    np.count_nonzero(valid & (fields["geometric_sheet"] == sheet))
                )
                for sheet in _SHEETS
            },
            "lf_geometry_valid_points": {
                sheet: int(
                    np.count_nonzero(
                        geometry_valid & (fields["geometric_sheet"] == sheet)
                    )
                )
                for sheet in _SHEETS
            },
            "surface_status": {
                sheet: stats_by_sheet[sheet]["status"] for sheet in _SHEETS
            },
            "artifacts": artifact_identity,
        }
        _write_json(temp_dir / "summary.json", summary)
        validation = validate_n8_run_artifacts(temp_dir)
        if validation["status"] != "PASS":
            raise ValueError("N8 artifact validation did not pass")
        temp_dir.replace(final_dir)
        return N8RunResult(run_dir=final_dir, summary=summary)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
