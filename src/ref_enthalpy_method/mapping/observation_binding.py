"""Strict Fluent CSV filename identity and fail-closed observation binding."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

_BINDING_SCHEMA = "faceted3d-observation-binding/v2"
_FILENAME_PATTERN = re.compile(
    r"(?P<p_inf>(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)pa_"
    r"(?P<T_inf>(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)k_"
    r"(?P<altitude>(?:0|[1-9][0-9]*))km_"
    r"(?P<alpha>(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)alpha_"
    r"(?P<mach>(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)ma\.csv"
)

_CSV_DIRECTORY = "fluent_export/adiabatic_wall_csv"
APPROVED_FORMAL_OBSERVATION_REGISTRY: Mapping[str, str] = MappingProxyType(
    {
        "ma6_a5_h30km": (
            f"{_CSV_DIRECTORY}/1197pa_226.509k_30km_5alpha_6ma.csv"
        ),
        "ma8_a5_h40km": f"{_CSV_DIRECTORY}/287pa_251k_40km_5alpha_8ma.csv",
    }
)
SUPPLEMENTAL_OBSERVATION_REGISTRY: Mapping[str, str] = MappingProxyType(
    {
        "ma8_a5_h30km": (
            f"{_CSV_DIRECTORY}/1197pa_226.509k_30km_5alpha_8ma.csv"
        ),
    }
)

_ALLOWED_FIELDS = frozenset(
    {
        "schema",
        "csv_path",
        "filename_identity",
        "raw_sha256",
        "byte_size",
        "header",
        "row_count",
        "freestream_provenance",
        "wall_thermal_condition",
        "observation_field",
        "observation_unit",
        "coordinate_unit",
        "fluent_source_convention",
        "solver_transform",
        "user_confirmation_date",
        "validation_policy",
    }
)


def _canonical_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _parse_decimal_token(token: str, *, name: str, positive: bool) -> Decimal:
    try:
        value = Decimal(token)
    except InvalidOperation as exc:
        raise ValueError(f"{name} token is not a finite decimal") from exc
    if not value.is_finite():
        raise ValueError(f"{name} token must be finite")
    if positive and value <= 0:
        raise ValueError(f"{name} token must be positive")
    return value


@dataclass(frozen=True)
class ObservationFilenameIdentity:
    """Immutable observation identity derived only from one CSV basename."""

    basename: str
    p_inf_Pa_token: str
    T_inf_K_token: str
    nominal_altitude_km_token: str
    alpha_deg_token: str
    mach_token: str
    p_inf_Pa: Decimal
    T_inf_K: Decimal
    nominal_altitude_km: Decimal
    alpha_deg: Decimal
    mach: Decimal
    case_key: str

    @property
    def geometric_altitude_m(self) -> Decimal:
        return self.nominal_altitude_km * Decimal("1000")

    @property
    def numeric_identity(self) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
        return (
            self.p_inf_Pa,
            self.T_inf_K,
            self.nominal_altitude_km,
            self.alpha_deg,
            self.mach,
        )


def parse_observation_filename(basename: str) -> ObservationFilenameIdentity:
    """Parse the current approved basename schema without performing admission."""
    if not isinstance(basename, str) or not basename:
        raise ValueError("observation basename must be a non-empty string")
    if basename != PurePosixPath(basename).name or "/" in basename or "\\" in basename:
        raise ValueError("observation parser accepts a basename, not a path")
    if basename.strip() != basename or any(character.isspace() for character in basename):
        raise ValueError("observation basename must not contain whitespace")

    match = _FILENAME_PATTERN.fullmatch(basename)
    if match is None:
        raise ValueError("observation basename does not match the current strict schema")

    tokens = match.groupdict()
    p_inf = _parse_decimal_token(tokens["p_inf"], name="p_inf_Pa", positive=True)
    T_inf = _parse_decimal_token(tokens["T_inf"], name="T_inf_K", positive=True)
    altitude = _parse_decimal_token(
        tokens["altitude"], name="nominal_altitude_km", positive=False
    )
    alpha = _parse_decimal_token(tokens["alpha"], name="alpha_deg", positive=False)
    mach = _parse_decimal_token(tokens["mach"], name="mach", positive=True)
    case_key = (
        f"ma{_canonical_decimal(mach)}_a{_canonical_decimal(alpha)}_"
        f"h{_canonical_decimal(altitude)}km"
    )
    return ObservationFilenameIdentity(
        basename=basename,
        p_inf_Pa_token=tokens["p_inf"],
        T_inf_K_token=tokens["T_inf"],
        nominal_altitude_km_token=tokens["altitude"],
        alpha_deg_token=tokens["alpha"],
        mach_token=tokens["mach"],
        p_inf_Pa=p_inf,
        T_inf_K=T_inf,
        nominal_altitude_km=altitude,
        alpha_deg=alpha,
        mach=mach,
        case_key=case_key,
    )


def validate_observation_identity_set(
    identities: Iterable[ObservationFilenameIdentity],
) -> tuple[ObservationFilenameIdentity, ...]:
    """Reject duplicate numeric identities and conflicting pairs per case key."""
    result = tuple(identities)
    seen_numeric: set[tuple[Decimal, Decimal, Decimal, Decimal, Decimal]] = set()
    pair_by_case: dict[str, tuple[Decimal, Decimal]] = {}
    for identity in result:
        if not isinstance(identity, ObservationFilenameIdentity):
            raise ValueError("identity set contains a non-filename identity")
        if identity.numeric_identity in seen_numeric:
            raise ValueError(
                f"duplicate complete observation identity: {identity.basename}"
            )
        seen_numeric.add(identity.numeric_identity)
        pair = (identity.T_inf_K, identity.p_inf_Pa)
        previous = pair_by_case.setdefault(identity.case_key, pair)
        if previous != pair:
            raise ValueError(
                f"conflicting freestream pair for case key {identity.case_key}"
            )
    return result


def _validate_repo_relative_path(csv_path: str) -> None:
    if not isinstance(csv_path, str) or not csv_path or csv_path.strip() != csv_path:
        raise ValueError("csv_path must be a non-empty canonical string")
    if "\\" in csv_path or csv_path.startswith("/"):
        raise ValueError("csv_path must be POSIX-style and repo-relative")
    if len(csv_path) >= 2 and csv_path[1] == ":":
        raise ValueError("csv_path must be repo-relative")
    path = PurePosixPath(csv_path)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError("csv_path must not contain absolute or dot components")
    if path.suffix != ".csv":
        raise ValueError("csv_path must identify a CSV file")


def _identity_from_csv_path(csv_path: str) -> ObservationFilenameIdentity:
    _validate_repo_relative_path(csv_path)
    return parse_observation_filename(PurePosixPath(csv_path).name)


def _validate_explicit_registry(registry: Mapping[str, str], *, label: str) -> None:
    identities: list[ObservationFilenameIdentity] = []
    for case_key, csv_path in registry.items():
        identity = _identity_from_csv_path(csv_path)
        if identity.case_key != case_key:
            raise RuntimeError(
                f"{label} registry key/path mismatch: {case_key} != {identity.case_key}"
            )
        identities.append(identity)
    validate_observation_identity_set(identities)


_validate_explicit_registry(
    APPROVED_FORMAL_OBSERVATION_REGISTRY, label="approved formal observation"
)
_validate_explicit_registry(
    SUPPLEMENTAL_OBSERVATION_REGISTRY, label="supplemental observation"
)


@dataclass(frozen=True)
class FluentObservationBinding:
    """Raw CSV identity directly bound to its filename-derived authority."""

    schema: str
    csv_path: str
    filename_identity: ObservationFilenameIdentity
    raw_sha256: str
    byte_size: int
    header: tuple[str, ...]
    row_count: int
    freestream_provenance: str
    wall_thermal_condition: str
    observation_field: str
    observation_unit: str
    coordinate_unit: str
    fluent_source_convention: str
    solver_transform: str
    user_confirmation_date: str
    validation_policy: str

    def __post_init__(self) -> None:
        if self.schema != _BINDING_SCHEMA:
            raise ValueError(f"schema must be exactly {_BINDING_SCHEMA!r}")
        _validate_repo_relative_path(self.csv_path)
        parsed = _identity_from_csv_path(self.csv_path)
        if self.filename_identity != parsed:
            raise ValueError("filename_identity must exactly match csv_path basename")
        if (
            len(self.raw_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.raw_sha256)
        ):
            raise ValueError("raw_sha256 must be lowercase hexadecimal SHA-256")
        for name in ("byte_size", "row_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if (
            not isinstance(self.header, tuple)
            or not self.header
            or not all(isinstance(field, str) for field in self.header)
        ):
            raise ValueError("header must be a non-empty tuple of strings")
        required_text = (
            "freestream_provenance",
            "wall_thermal_condition",
            "observation_field",
            "observation_unit",
            "coordinate_unit",
            "fluent_source_convention",
            "solver_transform",
        )
        for name in required_text:
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        date = self.user_confirmation_date
        if len(date) != 10 or date[4] != "-" or date[7] != "-":
            raise ValueError("user_confirmation_date must use YYYY-MM-DD")
        if self.validation_policy != "fail-closed":
            raise ValueError("validation_policy must be exactly 'fail-closed'")

    @property
    def case_key(self) -> str:
        return self.filename_identity.case_key

    @property
    def mach(self) -> Decimal:
        return self.filename_identity.mach

    @property
    def alpha_deg(self) -> Decimal:
        return self.filename_identity.alpha_deg

    @property
    def geometric_altitude_m(self) -> Decimal:
        return self.filename_identity.geometric_altitude_m

    @property
    def T_inf_K(self) -> Decimal:
        return self.filename_identity.T_inf_K

    @property
    def p_inf_Pa(self) -> Decimal:
        return self.filename_identity.p_inf_Pa


def _read_csv_raw_identity(repo_root: str | Path, csv_path: str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    full_path = (root / PurePosixPath(csv_path)).resolve()
    try:
        full_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"csv_path {csv_path!r} escapes repository root") from exc

    source_bytes = full_path.read_bytes()
    try:
        source_text = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"CSV must be UTF-8 text: {full_path}") from exc
    rows = csv.reader(io.StringIO(source_text, newline=""))
    try:
        header = tuple(next(rows))
    except StopIteration as exc:
        raise ValueError("CSV is empty") from exc
    if not header or all(not field for field in header):
        raise ValueError("CSV has no header")
    return {
        "raw_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "byte_size": len(source_bytes),
        "header": header,
        "row_count": sum(1 for _ in rows),
    }


def build_observation_binding(
    repo_root: str | Path,
    *,
    csv_path: str,
) -> FluentObservationBinding:
    filename_identity = _identity_from_csv_path(csv_path)
    raw_identity = _read_csv_raw_identity(repo_root, csv_path)
    return FluentObservationBinding(
        schema=_BINDING_SCHEMA,
        csv_path=csv_path,
        filename_identity=filename_identity,
        raw_sha256=raw_identity["raw_sha256"],
        byte_size=raw_identity["byte_size"],
        header=raw_identity["header"],
        row_count=raw_identity["row_count"],
        freestream_provenance="historical user-defined comparison input",
        wall_thermal_condition="adiabatic",
        observation_field="wall-temperature",
        observation_unit="K",
        coordinate_unit="m",
        fluent_source_convention="(x,y,z)",
        solver_transform="(x+0.030, span=y, up=z)",
        user_confirmation_date="2026-07-22",
        validation_policy="fail-closed",
    )


def build_approved_observation_binding(
    case_key: str,
    repo_root: str | Path,
) -> FluentObservationBinding:
    try:
        csv_path = APPROVED_FORMAL_OBSERVATION_REGISTRY[case_key]
    except KeyError as exc:
        raise ValueError(f"case is not in approved formal observation registry: {case_key}") from exc
    return build_observation_binding(repo_root, csv_path=csv_path)


def build_supplemental_observation_binding(
    case_key: str,
    repo_root: str | Path,
) -> FluentObservationBinding:
    try:
        csv_path = SUPPLEMENTAL_OBSERVATION_REGISTRY[case_key]
    except KeyError as exc:
        raise ValueError(f"case is not in supplemental observation registry: {case_key}") from exc
    return build_observation_binding(repo_root, csv_path=csv_path)


def build_m8h30_observation_binding(
    repo_root: str | Path,
    *,
    csv_path: str = SUPPLEMENTAL_OBSERVATION_REGISTRY["ma8_a5_h30km"],
) -> FluentObservationBinding:
    expected = SUPPLEMENTAL_OBSERVATION_REGISTRY["ma8_a5_h30km"]
    if csv_path != expected:
        raise ValueError(f"M8/30 supplemental binding path must be exactly {expected!r}")
    return build_supplemental_observation_binding("ma8_a5_h30km", repo_root)


def validate_observation_binding(
    binding: FluentObservationBinding | dict[str, Any],
    *,
    repo_root: str | Path,
) -> tuple[bool, str]:
    if isinstance(binding, dict):
        extra = set(binding) - _ALLOWED_FIELDS
        missing = _ALLOWED_FIELDS - set(binding)
        if extra:
            return False, f"unknown field(s): {sorted(extra)}"
        if missing:
            return False, f"missing required field(s): {sorted(missing)}"
        try:
            binding = FluentObservationBinding(**binding)
        except Exception as exc:
            return False, f"binding construction failed: {exc}"
    if not isinstance(binding, FluentObservationBinding):
        return False, "binding must be a FluentObservationBinding or dict"

    try:
        parsed = _identity_from_csv_path(binding.csv_path)
        if binding.filename_identity != parsed:
            return False, "filename identity does not match csv_path"
        actual = _read_csv_raw_identity(repo_root, binding.csv_path)
    except Exception as exc:
        return False, f"CSV identity read failed: {exc}"

    for name in ("raw_sha256", "byte_size", "header", "row_count"):
        if getattr(binding, name) != actual[name]:
            return False, f"{name} mismatch"
    expected_metadata = {
        "freestream_provenance": "historical user-defined comparison input",
        "wall_thermal_condition": "adiabatic",
        "observation_field": "wall-temperature",
        "observation_unit": "K",
        "coordinate_unit": "m",
        "fluent_source_convention": "(x,y,z)",
        "solver_transform": "(x+0.030, span=y, up=z)",
        "user_confirmation_date": "2026-07-22",
        "validation_policy": "fail-closed",
    }
    for name, expected in expected_metadata.items():
        if getattr(binding, name) != expected:
            return False, f"{name} mismatch"
    return True, ""


def _runtime_decimal(name: str, value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{name} must be an explicit finite positive decimal")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (str, int, float)):
        try:
            result = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"{name} must be an explicit finite positive decimal") from exc
    else:
        raise ValueError(f"{name} must be an explicit finite positive decimal")
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{name} must be an explicit finite positive decimal")
    return result


def _validated_authority_identity(
    authority: ObservationFilenameIdentity | FluentObservationBinding,
) -> ObservationFilenameIdentity:
    identity = (
        authority.filename_identity
        if isinstance(authority, FluentObservationBinding)
        else authority
    )
    if not isinstance(identity, ObservationFilenameIdentity):
        raise ValueError("exact freestream authority must be a filename identity or binding")
    parsed = parse_observation_filename(identity.basename)
    if identity != parsed:
        raise ValueError("exact freestream authority must be parser-derived")
    return identity


def require_exact_freestream_pair(
    authority: ObservationFilenameIdentity | FluentObservationBinding,
    *,
    T_inf_K: Any,
    p_inf_Pa: Any,
) -> None:
    identity = _validated_authority_identity(authority)
    actual_T = _runtime_decimal("T_inf_K", T_inf_K)
    actual_p = _runtime_decimal("p_inf_Pa", p_inf_Pa)
    if actual_T != identity.T_inf_K or actual_p != identity.p_inf_Pa:
        raise ValueError(
            "explicit freestream pair does not exactly match observation filename identity"
        )


def exact_freestream_cli_arguments(
    authority: ObservationFilenameIdentity | FluentObservationBinding,
    *,
    T_inf_K: Any,
    p_inf_Pa: Any,
) -> tuple[str, str, str, str]:
    require_exact_freestream_pair(
        authority,
        T_inf_K=T_inf_K,
        p_inf_Pa=p_inf_Pa,
    )
    identity = _validated_authority_identity(authority)
    return (
        "--T_inf_K",
        identity.T_inf_K_token,
        "--p_inf_Pa",
        identity.p_inf_Pa_token,
    )


def validate_exact_freestream_summary(
    authority: ObservationFilenameIdentity | FluentObservationBinding,
    summary: Mapping[str, Any],
) -> None:
    inputs = summary.get("inputs")
    freestream = summary.get("freestream")
    if not isinstance(inputs, Mapping):
        raise ValueError("summary.inputs must contain explicit freestream overrides")
    if not isinstance(freestream, Mapping):
        raise ValueError("summary.freestream must be an object")
    if freestream.get("freestream_source") != "explicit_override":
        raise ValueError("summary freestream source must be explicit_override")
    for T_value, p_value in (
        (inputs.get("T_inf_K_override"), inputs.get("p_inf_Pa_override")),
        (freestream.get("T_inf_K"), freestream.get("p_inf_Pa")),
    ):
        require_exact_freestream_pair(
            authority,
            T_inf_K=T_value,
            p_inf_Pa=p_value,
        )


def validate_exact_freestream_manifest(
    authority: ObservationFilenameIdentity | FluentObservationBinding,
    manifest: Mapping[str, Any],
) -> None:
    freestream = manifest.get("freestream")
    atmosphere = manifest.get("atmosphere")
    if not isinstance(freestream, Mapping):
        raise ValueError("manifest.freestream must be an object")
    if freestream.get("source") != "explicit_override":
        raise ValueError("manifest freestream source must be explicit_override")
    if not isinstance(atmosphere, Mapping) or atmosphere.get(
        "explicit_freestream_override"
    ) is not True:
        raise ValueError("manifest must record explicit_freestream_override=true")
    require_exact_freestream_pair(
        authority,
        T_inf_K=freestream.get("actual_T_inf_K"),
        p_inf_Pa=freestream.get("actual_p_inf_Pa"),
    )