"""Focused tests for strict CSV filename identity and observation binding."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from ref_enthalpy_method.mapping.observation_binding import (
    APPROVED_FORMAL_OBSERVATION_REGISTRY,
    SUPPLEMENTAL_OBSERVATION_REGISTRY,
    build_approved_observation_binding,
    build_m8h30_observation_binding,
    exact_freestream_cli_arguments,
    parse_observation_filename,
    require_exact_freestream_pair,
    validate_exact_freestream_manifest,
    validate_exact_freestream_summary,
    validate_observation_binding,
    validate_observation_identity_set,
)

ROOT = Path(__file__).resolve().parents[1]
CSV_DIRECTORY = "fluent_export/adiabatic_wall_csv"
APPROVED_BASENAMES = (
    "1197pa_226.509k_30km_3alpha_6.5ma.csv",
    "1197pa_226.509k_30km_5alpha_6ma.csv",
    "1197pa_226.509k_30km_5alpha_8ma.csv",
    "558.9pa_237k_35km_8alpha_6.5ma.csv",
    "558.9pa_237k_35km_8alpha_9ma.csv",
    "287pa_251k_40km_10alpha_8ma.csv",
    "287pa_251k_40km_5alpha_6.5ma.csv",
    "287pa_251k_40km_5alpha_8ma.csv",
    "287pa_251k_40km_5alpha_9ma.csv",
    "131pa_241.65k_45km_10alpha_8ma.csv",
    "131pa_241.65k_45km_5alpha_8ma.csv",
    "131pa_241.65k_45km_5alpha_9ma.csv",
)


def test_current_twelve_basenames_parse_without_admission() -> None:
    identities = tuple(parse_observation_filename(name) for name in APPROVED_BASENAMES)

    assert len(identities) == 12
    assert {identity.basename for identity in identities} == set(APPROVED_BASENAMES)
    assert set(APPROVED_FORMAL_OBSERVATION_REGISTRY) == {
        "ma6_a5_h30km",
        "ma8_a5_h40km",
    }
    assert all(
        identity.case_key not in APPROVED_FORMAL_OBSERVATION_REGISTRY
        for identity in identities
        if identity.nominal_altitude_km == Decimal("45")
    )


@pytest.mark.parametrize(
    "basename",
    (
        " 1197pa_226.509k_30km_5alpha_6ma.csv",
        "1197pa_226.509k_30km_5alpha_6ma.csv ",
        "1197PA_226.509k_30km_5alpha_6ma.csv",
        "1197pa_226.509K_30km_5alpha_6ma.csv",
        "folder/1197pa_226.509k_30km_5alpha_6ma.csv",
        r"folder\1197pa_226.509k_30km_5alpha_6ma.csv",
        "../1197pa_226.509k_30km_5alpha_6ma.csv",
        "1197e0pa_226.509k_30km_5alpha_6ma.csv",
        "nanpa_226.509k_30km_5alpha_6ma.csv",
        "infpa_226.509k_30km_5alpha_6ma.csv",
        "1197pa_226.509k_30km_5alpha.csv",
        "1197pa_226.509k_30km_5alpha_6ma.txt",
    ),
)
def test_parser_rejects_non_schema_input(basename: str) -> None:
    with pytest.raises(ValueError):
        parse_observation_filename(basename)


@pytest.mark.parametrize(
    "basename",
    (
        "0pa_226.509k_30km_5alpha_6ma.csv",
        "-1pa_226.509k_30km_5alpha_6ma.csv",
        "1197pa_0k_30km_5alpha_6ma.csv",
        "1197pa_-1k_30km_5alpha_6ma.csv",
        "1197pa_226.509k_30km_5alpha_0ma.csv",
        "1197pa_226.509k_30km_5alpha_-1ma.csv",
    ),
)
def test_parser_rejects_nonpositive_freestream_or_mach(basename: str) -> None:
    with pytest.raises(ValueError):
        parse_observation_filename(basename)


def test_parser_preserves_raw_tokens_decimal_values_and_case_key() -> None:
    identity = parse_observation_filename(
        "1197pa_226.509k_30km_5alpha_6ma.csv"
    )

    assert identity.p_inf_Pa_token == "1197"
    assert identity.T_inf_K_token == "226.509"
    assert identity.nominal_altitude_km_token == "30"
    assert identity.alpha_deg_token == "5"
    assert identity.mach_token == "6"
    assert identity.p_inf_Pa == Decimal("1197")
    assert identity.T_inf_K == Decimal("226.509")
    assert identity.nominal_altitude_km == Decimal("30")
    assert identity.alpha_deg == Decimal("5")
    assert identity.mach == Decimal("6")
    assert identity.case_key == "ma6_a5_h30km"


def test_identity_set_rejects_conflicting_pair_for_same_case_key() -> None:
    identities = (
        parse_observation_filename("1197pa_226.509k_30km_5alpha_6ma.csv"),
        parse_observation_filename("1200pa_227k_30km_5alpha_6ma.csv"),
    )

    with pytest.raises(ValueError, match="conflicting freestream pair"):
        validate_observation_identity_set(identities)


def test_identity_set_rejects_duplicate_complete_identity() -> None:
    identity = parse_observation_filename("1197pa_226.509k_30km_5alpha_6ma.csv")

    with pytest.raises(ValueError, match="duplicate complete observation identity"):
        validate_observation_identity_set((identity, identity))


def test_approved_bindings_are_exact_filename_authority() -> None:
    m6 = build_approved_observation_binding("ma6_a5_h30km", ROOT)
    m8 = build_approved_observation_binding("ma8_a5_h40km", ROOT)

    assert (m6.T_inf_K, m6.p_inf_Pa) == (
        Decimal("226.509"),
        Decimal("1197"),
    )
    assert (m8.T_inf_K, m8.p_inf_Pa) == (Decimal("251"), Decimal("287"))
    assert m6.case_key == "ma6_a5_h30km"
    assert m8.case_key == "ma8_a5_h40km"
    for binding in (m6, m8):
        passed, reason = validate_observation_binding(binding, repo_root=ROOT)
        assert passed, reason


def test_m8h30_is_supplemental_only_and_uses_new_path() -> None:
    binding = build_m8h30_observation_binding(ROOT)

    assert binding.csv_path == (
        f"{CSV_DIRECTORY}/1197pa_226.509k_30km_5alpha_8ma.csv"
    )
    assert binding.case_key == "ma8_a5_h30km"
    assert binding.T_inf_K == Decimal("226.509")
    assert binding.p_inf_Pa == Decimal("1197")
    assert "ma8_a5_h30km" in SUPPLEMENTAL_OBSERVATION_REGISTRY
    assert "ma8_a5_h30km" not in APPROVED_FORMAL_OBSERVATION_REGISTRY
    with pytest.raises(ValueError, match="not in approved"):
        build_approved_observation_binding("ma8_a5_h30km", ROOT)


def test_binding_rejects_filename_identity_drift() -> None:
    binding = build_approved_observation_binding("ma6_a5_h30km", ROOT)
    wrong_identity = parse_observation_filename(
        "1200pa_226.509k_30km_5alpha_6ma.csv"
    )

    with pytest.raises(ValueError, match="filename_identity"):
        replace(binding, filename_identity=wrong_identity)


def test_exact_gate_rejects_handcrafted_identity_as_parallel_authority() -> None:
    parsed = parse_observation_filename(
        "1197pa_226.509k_30km_5alpha_6ma.csv"
    )
    handcrafted = replace(parsed, p_inf_Pa=Decimal("1200"))

    with pytest.raises(ValueError, match="parser-derived"):
        require_exact_freestream_pair(
            handcrafted,
            T_inf_K=Decimal("226.509"),
            p_inf_Pa=Decimal("1200"),
        )


@pytest.mark.parametrize(
    ("T_inf_K", "p_inf_Pa"),
    (
        (None, Decimal("1197")),
        (Decimal("226.509"), None),
        (Decimal("226.5"), Decimal("1197")),
        (Decimal("226.509"), Decimal("1196.0495613543349")),
        (Decimal("226.50908361133003"), Decimal("1197")),
    ),
)
def test_exact_pair_gate_rejects_missing_or_mismatched_values(
    T_inf_K: Decimal | None,
    p_inf_Pa: Decimal | None,
) -> None:
    binding = build_approved_observation_binding("ma6_a5_h30km", ROOT)

    with pytest.raises(ValueError):
        require_exact_freestream_pair(
            binding,
            T_inf_K=T_inf_K,
            p_inf_Pa=p_inf_Pa,
        )


def test_exact_cli_preserves_approved_decimal_tokens() -> None:
    m6 = build_approved_observation_binding("ma6_a5_h30km", ROOT)
    m8 = build_approved_observation_binding("ma8_a5_h40km", ROOT)

    assert exact_freestream_cli_arguments(
        m6, T_inf_K=Decimal("226.509"), p_inf_Pa=Decimal("1197")
    ) == ("--T_inf_K", "226.509", "--p_inf_Pa", "1197")
    assert exact_freestream_cli_arguments(
        m8, T_inf_K=Decimal("251"), p_inf_Pa=Decimal("287")
    ) == ("--T_inf_K", "251", "--p_inf_Pa", "287")


def _exact_summary(T_inf_K: object, p_inf_Pa: object, *, source: str) -> dict:
    return {
        "inputs": {
            "T_inf_K_override": T_inf_K,
            "p_inf_Pa_override": p_inf_Pa,
        },
        "freestream": {
            "T_inf_K": T_inf_K,
            "p_inf_Pa": p_inf_Pa,
            "freestream_source": source,
        },
    }


def test_summary_and_manifest_accept_only_exact_explicit_pair() -> None:
    binding = build_approved_observation_binding("ma8_a5_h40km", ROOT)
    summary = _exact_summary(251.0, 287.0, source="explicit_override")
    manifest = {
        "freestream": {
            "actual_T_inf_K": 251.0,
            "actual_p_inf_Pa": 287.0,
            "source": "explicit_override",
        },
        "atmosphere": {"explicit_freestream_override": True},
    }

    validate_exact_freestream_summary(binding, summary)
    validate_exact_freestream_manifest(binding, manifest)


@pytest.mark.parametrize(
    "summary",
    (
        _exact_summary(226.509, 1197.0, source="atmosphere"),
        _exact_summary(226.50908361133003, 1196.0495613543349, source="explicit_override"),
        {"freestream": {"T_inf_K": 226.509, "p_inf_Pa": 1197.0, "freestream_source": "explicit_override"}},
    ),
)
def test_summary_rejects_nonexplicit_historical_or_missing_override(
    summary: dict,
) -> None:
    binding = build_approved_observation_binding("ma6_a5_h30km", ROOT)

    with pytest.raises(ValueError):
        validate_exact_freestream_summary(binding, summary)


def test_parser_and_binding_do_not_modify_historical_manifest_bytes() -> None:
    manifest_path = (
        ROOT
        / "runs"
        / "leeward_source_evidence"
        / "20260720T055647Z_af1f1f5395a9"
        / "manifest.json"
    )
    before = manifest_path.read_bytes()

    parse_observation_filename(APPROVED_BASENAMES[0])
    build_m8h30_observation_binding(ROOT)

    assert manifest_path.read_bytes() == before