"""Deterministic geometry mapping input contracts."""

from .fluent_surface import (
    CanonicalGeometryComparison,
    FluentSurfaceGeometry,
    compare_canonical_geometry,
    read_fluent_surface_geometry_csv,
    transform_fluent_xyz_to_solver,
)

from .observation_binding import (
    FluentObservationBinding,
    build_m8h30_observation_binding,
    validate_observation_binding,
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
    "FluentObservationBinding",
    "build_m8h30_observation_binding",
    "validate_observation_binding",
    "FluentLfTawComparisonInputs",
    "M8H30CandidateIdentity",
    "M8H30ComparisonInputs",
    "M8H30ProjectionCacheIdentity",
    "build_m8h30_comparison_inputs",
]
