"""Deterministic geometry mapping input contracts."""

from .fluent_surface import (
    CanonicalGeometryComparison,
    FluentSurfaceGeometry,
    compare_canonical_geometry,
    read_fluent_surface_geometry_csv,
    transform_fluent_xyz_to_solver,
)
from .fluent_lf_taw_comparison import (
    FluentLfTawComparison,
    build_fluent_lf_taw_comparison,
)

from .observation_binding import (
    APPROVED_FORMAL_OBSERVATION_REGISTRY,
    SUPPLEMENTAL_OBSERVATION_REGISTRY,
    FluentObservationBinding,
    ObservationFilenameIdentity,
    build_approved_observation_binding,
    build_m8h30_observation_binding,
    build_observation_binding,
    build_supplemental_observation_binding,
    exact_freestream_cli_arguments,
    parse_observation_filename,
    require_exact_freestream_pair,
    validate_exact_freestream_manifest,
    validate_exact_freestream_summary,
    validate_observation_binding,
    validate_observation_identity_set,
)
from .m8h30_comparison_inputs import (
    FluentLfTawComparisonInputs,
    M8H30CandidateIdentity,
    M8H30ComparisonInputs,
    M8H30ProjectionCacheIdentity,
    build_m8h30_comparison_inputs,
)

__all__ = [
    "CanonicalGeometryComparison",
    "FluentSurfaceGeometry",
    "compare_canonical_geometry",
    "read_fluent_surface_geometry_csv",
    "transform_fluent_xyz_to_solver",
    "FluentLfTawComparison",
    "build_fluent_lf_taw_comparison",
    "APPROVED_FORMAL_OBSERVATION_REGISTRY",
    "SUPPLEMENTAL_OBSERVATION_REGISTRY",
    "FluentObservationBinding",
    "ObservationFilenameIdentity",
    "build_approved_observation_binding",
    "build_m8h30_observation_binding",
    "build_observation_binding",
    "build_supplemental_observation_binding",
    "exact_freestream_cli_arguments",
    "parse_observation_filename",
    "require_exact_freestream_pair",
    "validate_exact_freestream_manifest",
    "validate_exact_freestream_summary",
    "validate_observation_binding",
    "validate_observation_identity_set",
    "FluentLfTawComparisonInputs",
    "M8H30CandidateIdentity",
    "M8H30ComparisonInputs",
    "M8H30ProjectionCacheIdentity",
    "build_m8h30_comparison_inputs",
]
