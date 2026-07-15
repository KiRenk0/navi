from __future__ import annotations

import numpy as np


def compute_adiabatic_wall_temperature(
    T_e: np.ndarray,
    M_e: np.ndarray,
    Pr: float,
    gamma_air: float,
    w_tr: np.ndarray,
    valid_mask: np.ndarray | None = None,
) -> dict[str, np.ndarray | float | dict[str, bool]]:
    T_e = np.asarray(T_e, dtype=float)
    M_e = np.asarray(M_e, dtype=float)
    w_tr = np.asarray(w_tr, dtype=float)

    if T_e.ndim != 1:
        raise ValueError("T_e must be 1-D")
    if M_e.shape != T_e.shape:
        raise ValueError(f"M_e shape {M_e.shape} != T_e shape {T_e.shape}")
    if w_tr.shape != T_e.shape:
        raise ValueError(f"w_tr shape {w_tr.shape} != T_e shape {T_e.shape}")

    n = T_e.shape[0]

    if valid_mask is None:
        valid_mask = np.isfinite(T_e) & np.isfinite(M_e) & np.isfinite(w_tr)
    valid_mask = np.asarray(valid_mask, dtype=bool).reshape(-1)
    if valid_mask.shape != (n,):
        raise ValueError(f"valid_mask shape {valid_mask.shape} != ({n},)")

    if Pr <= 0:
        raise ValueError(f"Pr must be positive, got {Pr}")
    if gamma_air <= 1:
        raise ValueError(f"gamma_air must be > 1, got {gamma_air}")

    r_lam = np.full(n, np.sqrt(Pr), dtype=float)
    r_turb = np.full(n, Pr ** (1.0 / 3.0), dtype=float)

    r_eff = np.where(valid_mask, (1.0 - w_tr) * r_lam + w_tr * r_turb, np.nan)

    g = gamma_air
    gm1_over_2 = (g - 1.0) / 2.0

    T0_edge = np.where(valid_mask, T_e * (1.0 + gm1_over_2 * M_e**2), np.nan)

    Taw_lam = np.where(
        valid_mask, T_e * (1.0 + r_lam * gm1_over_2 * M_e**2), np.nan
    )
    Taw_turb = np.where(
        valid_mask, T_e * (1.0 + r_turb * gm1_over_2 * M_e**2), np.nan
    )
    Taw = np.where(valid_mask, T_e * (1.0 + r_eff * gm1_over_2 * M_e**2), np.nan)

    checks: dict[str, bool] = {}
    fv = valid_mask
    eps = 1e-12

    mask_nan = np.isnan(Taw)
    checks["taw_nan_mask_matches_valid"] = bool(np.all(mask_nan == ~valid_mask))

    checks["taw_ge_te"] = bool(np.all((Taw[fv] >= T_e[fv] - eps)))
    checks["taw_le_t0_edge"] = bool(np.all((Taw[fv] <= T0_edge[fv] + eps)))
    checks["taw_lam_ge_te"] = bool(np.all((Taw_lam[fv] >= T_e[fv] - eps)))
    checks["taw_lam_le_t0_edge"] = bool(
        np.all((Taw_lam[fv] <= T0_edge[fv] + eps))
    )
    checks["taw_turb_ge_te"] = bool(np.all((Taw_turb[fv] >= T_e[fv] - eps)))
    checks["taw_turb_le_t0_edge"] = bool(
        np.all((Taw_turb[fv] <= T0_edge[fv] + eps))
    )
    checks["r_eff_in_01"] = bool(np.all((r_eff[fv] >= 0) & (r_eff[fv] <= 1)))
    checks["r_lam_is_sqrt_pr"] = bool(
        np.allclose(r_lam[fv], np.sqrt(Pr), atol=1e-15)
    )
    checks["r_turb_is_pr_cuberoot"] = bool(
        np.allclose(r_turb[fv], Pr ** (1.0 / 3.0), atol=1e-15)
    )

    all_pass = all(checks.values())

    return {
        "Taw": Taw,
        "Taw_lam": Taw_lam,
        "Taw_turb": Taw_turb,
        "r_eff": r_eff,
        "r_lam": r_lam,
        "r_turb": r_turb,
        "T0_edge": T0_edge,
        "valid_mask": valid_mask,
        "checks": checks,
        "all_pass": all_pass,
    }


def compute_adiabatic_wall_temperature_tpg(
    *,
    T_e: np.ndarray,
    V_e: np.ndarray,
    w_tr: np.ndarray,
    Pr: float,
    tpg,
    h0: float | None = None,
    valid_mask: np.ndarray | None = None,
) -> dict[str, np.ndarray | float]:
    T_e = np.asarray(T_e, dtype=float)
    V_e = np.asarray(V_e, dtype=float)
    w_tr = np.asarray(w_tr, dtype=float)

    n = T_e.shape[0]
    if V_e.shape != (n,):
        raise ValueError("V_e shape mismatch")
    if w_tr.shape != (n,):
        raise ValueError("w_tr shape mismatch")

    if valid_mask is None:
        valid_mask = np.isfinite(T_e) & np.isfinite(V_e) & np.isfinite(w_tr)
    valid_mask = np.asarray(valid_mask, dtype=bool).reshape(-1)

    r_lam = np.sqrt(float(Pr))
    r_turb = float(Pr) ** (1.0 / 3.0)
    r_eff = np.where(valid_mask, (1.0 - w_tr) * r_lam + w_tr * r_turb, np.nan)

    h_e = tpg.vector_h_from_T(T_e)
    h_aw = np.where(valid_mask, h_e + r_eff * 0.5 * V_e**2, np.nan)
    Taw = tpg.vector_T_from_h(h_aw)

    checks: dict[str, bool] = {}
    fv = valid_mask
    eps = 1e-12
    checks["taw_ge_te"] = bool(np.all((Taw[fv] >= T_e[fv] - eps)))
    checks["r_eff_in_01"] = bool(np.all((r_eff[fv] >= 0) & (r_eff[fv] <= 1)))
    all_pass = all(checks.values())

    return {
        "Taw": np.asarray(Taw, dtype=float),
        "Taw_lam": np.where(valid_mask, tpg.vector_T_from_h(h_e + r_lam * 0.5 * V_e**2), np.nan),
        "Taw_turb": np.where(valid_mask, tpg.vector_T_from_h(h_e + r_turb * 0.5 * V_e**2), np.nan),
        "r_eff": r_eff,
        "r_lam": np.full(n, r_lam, dtype=float),
        "r_turb": np.full(n, r_turb, dtype=float),
        "valid_mask": valid_mask,
        "checks": checks,
        "all_pass": all_pass,
    }
