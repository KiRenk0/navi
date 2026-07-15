"""Leeward freestream-recovery TPG Taw diagnostic — pure provider.

Does not depend on windward cache, fixed-wall heat-flux, or any legacy leeward functions.
The same pure function is intended to be called separately for upper and lower sheets later.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ref_enthalpy_method.geometry.local_incidence import SURFACE_CLASS_LEEWARD
from ref_enthalpy_method.types import GasModel


@dataclass(frozen=True)
class LeewardFreestreamRecoveryFields:
    """Freestream-recovery edge-state and Taw for leeward points only.

    All float arrays have the same 1-D shape as `surface_class`.
    Values are NaN everywhere outside `mask`.
    """

    mask: np.ndarray        # bool, True where surface_class == SURFACE_CLASS_LEEWARD
    T_e: np.ndarray         # K
    p_e: np.ndarray         # Pa
    rho_e: np.ndarray       # kg/m^3
    V_e: np.ndarray         # m/s
    Ma_e: np.ndarray
    h_e: np.ndarray         # J/kg
    mu_e: np.ndarray        # Pa*s
    Taw_tpg: np.ndarray     # K, adiabatic-wall temperature via TPG recovery


def build_leeward_freestream_recovery(
    *,
    surface_class: np.ndarray,
    T_inf_K: float,
    p_inf_Pa: float,
    rho_inf_kg_m3: float,
    V_inf_m_s: float,
    Ma_inf: float,
    gas: GasModel,
) -> LeewardFreestreamRecoveryFields:
    """Return freestream-recovery fields for every leeward-classified point.

    Mask rule (the only formal definition):
        mask = surface_class == SURFACE_CLASS_LEEWARD  (-1)

    Inside mask:  T_e = T_inf, p_e = p_inf, rho_e = rho_inf, V_e = V_inf,
                  Ma_e = Ma_inf, h_e = gas.h_from_T(T_inf), mu_e = gas.mu(T_inf).

    Recovery:
        r_aw   = gas.prandtl ** (1/3)
        h_aw   = h_e + r_aw * V_e**2 / 2
        Taw_tpg = gas.T_from_h(h_aw)

    Outside mask: every float field is NaN.
    All float outputs have shape == surface_class.shape, dtype=float64.
    Input ``surface_class`` is never modified.
    """

    # ── input validation ───────────────────────────────────────────────
    surface_class = np.asarray(surface_class)

    if surface_class.ndim != 1:
        raise ValueError(
            f"surface_class must be 1-D; got ndim={surface_class.ndim}"
        )

    _validate_scalar("T_inf_K", T_inf_K, positive=True)
    _validate_scalar("p_inf_Pa", p_inf_Pa, positive=True)
    _validate_scalar("rho_inf_kg_m3", rho_inf_kg_m3, positive=True)
    _validate_scalar("V_inf_m_s", V_inf_m_s, non_negative=True)
    _validate_scalar("Ma_inf", Ma_inf, non_negative=True)

    # gas-model sanity
    if gas.tpg is None:
        raise ValueError("gas.tpg must not be None")
    if not callable(gas.h_from_T):
        raise TypeError("gas.h_from_T must be callable")
    if not callable(gas.T_from_h):
        raise TypeError("gas.T_from_h must be callable")
    if not callable(gas.mu):
        raise TypeError("gas.mu must be callable")

    # ── mask ───────────────────────────────────────────────────────────
    mask: np.ndarray = (surface_class == SURFACE_CLASS_LEEWARD)  # type: ignore[assignment]

    n = surface_class.shape[0]
    float_template = np.full(n, np.nan, dtype=np.float64)

    # ── fill edge-state inside mask ────────────────────────────────────
    T_e = float_template.copy()
    p_e = float_template.copy()
    rho_e = float_template.copy()
    V_e = float_template.copy()
    Ma_e = float_template.copy()

    T_inf = float(T_inf_K)
    p_inf = float(p_inf_Pa)
    rho_inf = float(rho_inf_kg_m3)
    V_inf = float(V_inf_m_s)
    Ma_inf_f = float(Ma_inf)

    if np.any(mask):
        T_e[mask] = T_inf
        p_e[mask] = p_inf
        rho_e[mask] = rho_inf
        V_e[mask] = V_inf
        Ma_e[mask] = Ma_inf_f

    # ── TPG properties inside mask ─────────────────────────────────────
    h_e = float_template.copy()
    mu_e = float_template.copy()

    if np.any(mask):
        h_inf = float(gas.h_from_T(T_inf))
        mu_inf = float(gas.mu(T_inf))
        h_e[mask] = h_inf
        mu_e[mask] = mu_inf

    # ── recovery ───────────────────────────────────────────────────────
    Taw_tpg = float_template.copy()

    if np.any(mask):
        pr = float(gas.prandtl)
        r_aw = pr ** (1.0 / 3.0)
        # h_aw = h_e + r_aw * V_e^2 / 2
        h_aw_arr = h_e[mask] + r_aw * 0.5 * V_e[mask] * V_e[mask]
        # vectorised T_from_h — one call per element to stay within
        # the scalar-API contract (T_from_h accepts float, not array)
        taw_vals = np.array([float(gas.T_from_h(float(hv))) for hv in h_aw_arr], dtype=np.float64)
        Taw_tpg[mask] = taw_vals

    return LeewardFreestreamRecoveryFields(
        mask=mask,
        T_e=T_e,
        p_e=p_e,
        rho_e=rho_e,
        V_e=V_e,
        Ma_e=Ma_e,
        h_e=h_e,
        mu_e=mu_e,
        Taw_tpg=Taw_tpg,
    )


# ── helpers ───────────────────────────────────────────────────────────────

def _validate_scalar(
    name: str,
    value: float,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> None:
    val = float(value)
    if not np.isfinite(val):
        raise ValueError(f"{name} must be finite; got {value!r}")
    if positive and val <= 0.0:
        raise ValueError(f"{name} must be > 0; got {value!r}")
    if non_negative and val < 0.0:
        raise ValueError(f"{name} must be >= 0; got {value!r}")