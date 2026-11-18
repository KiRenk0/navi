"""Windward edge-cache for faceted 3D (sx, sy) slopes.

This is a minimal 3D upgrade that preserves the original solver architecture:
- keep the same reference-enthalpy "soup"
- replace the 2D windward slope dz/dx with a facet-normal based inflow angle phi(sx, sy)

Reference state: each point carries an explicit strip leading-edge reference
incidence supplied by the caller (see ``n8_taw_surface``); nothing here
extrapolates or reads the first sample of a strip.

Coordinate convention:
- x: streamwise (chordwise)
- y: spanwise
- z: upward

Definitions:
- surface slopes: sx = dz/dx, sy = dz/dy
- graph normal: (-sx, -sy, 1), oriented outward for the selected sheet
- body-axis flow direction (no sideslip): u = (cos(alpha), 0, sin(alpha))
- signed pressure incidence: s = -u dot n_out

The modified-Newtonian pressure model uses the actual body-axis angle of
attack and Mach number because the 3D outward normal already contains the
sweep geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from ..aero.edge_conditions import solve_edge_state
from ..aero.pressure_coefficient import (
    modified_newtonian_cp,
    modified_newtonian_cp_max,
)
from ..aero.recovery import reference_enthalpy_recovery
from ..geometry.local_incidence import (
    classify_incidence,
    outward_normal_from_slopes,
)
from ..types import EdgeConditions, GasModel


@dataclass(frozen=True)
class WindwardEdgeCacheFaceted3D:
    edges: list[EdgeConditions | None]  # length n; None where the edge state failed
    alpha_rad: float = float("nan")
    mach: float = float("nan")
    pressure_incidence_arr: np.ndarray | None = None  # (n,) signed -u.n
    cp_arr: np.ndarray | None = None  # (n,) pressure coefficient
    cp_max: float = float("nan")
    reference_incidence_arr: np.ndarray | None = None  # (n,) s_ref actually used
    taw_tpg: np.ndarray | None = None  # (n,) adiabatic wall temperature
    h0_tpg: float | None = None  # freestream total enthalpy (J/kg)
    edge_status: np.ndarray | None = None  # (n,) "ok" or failure reason
    T_e_K: np.ndarray | None = None
    p_e_Pa: np.ndarray | None = None
    V_e_m_s: np.ndarray | None = None
    energy_residual_J_kg: np.ndarray | None = None
    entropy_residual_J_kgK: np.ndarray | None = None
    property_in_fit_range: np.ndarray | None = None  # Te and Taw in NASA-9 range
    T_star_K: np.ndarray | None = None  # Eckert reference temperature
    recovery_factor: np.ndarray | None = None  # Pr(T*)^(1/3)


def build_windward_edge_cache_faceted3d(
    *,
    gas: GasModel,
    mach: float,
    alpha_deg: float,
    p_inf: float,
    T_inf: float,
    sx_arr: np.ndarray,
    sy_arr: np.ndarray,
    reference_incidence_s: np.ndarray,
    sheet: Literal["upper", "lower"] = "upper",
    rho_inf: float | None = None,
) -> WindwardEdgeCacheFaceted3D:
    """Compute modified-Newtonian edge states and Taw for surface points.

    ``reference_incidence_s`` is the strip leading-edge reference incidence
    supplied by the caller (one value per point).  It is never derived from
    the first sample of the arrays, so the result does not depend on how the
    points were generated.  The effective reference is
    ``max(reference_incidence_s, local incidence)`` so a point never sits on a
    weaker shock than its own normal-shock limit.
    """

    del rho_inf
    if sheet not in {"upper", "lower"}:
        raise ValueError("sheet must be 'upper' or 'lower'")

    mach_value = float(mach)
    alpha_rad = float(np.deg2rad(float(alpha_deg)))
    sx_arr = np.asarray(sx_arr, dtype=float).reshape(-1)
    sy_arr = np.asarray(sy_arr, dtype=float).reshape(-1)
    s_ref_in = np.asarray(reference_incidence_s, dtype=float).reshape(-1)
    if sx_arr.size == 0 or sy_arr.size != sx_arr.size or s_ref_in.size != sx_arr.size:
        raise ValueError("sx_arr, sy_arr and reference_incidence_s must have equal nonzero length")
    if not (np.all(np.isfinite(sx_arr)) and np.all(np.isfinite(sy_arr))
            and np.all(np.isfinite(s_ref_in))):
        raise ValueError("sx_arr, sy_arr and reference_incidence_s must be finite")

    cp_max = modified_newtonian_cp_max(mach=mach_value, gamma=float(gas.gamma))
    normals = outward_normal_from_slopes(sx=sx_arr, sy=sy_arr, sheet=sheet)
    incidence_arr = np.asarray(
        classify_incidence(normal_out=normals, alpha_deg=alpha_deg)[0], dtype=float
    )
    cp_arr = np.asarray(
        [
            modified_newtonian_cp(
                incidence_s=float(incidence), mach=mach_value, gamma=float(gas.gamma)
            )
            for incidence in incidence_arr
        ],
        dtype=float,
    )
    s_ref_eff = np.clip(np.maximum(s_ref_in, incidence_arr), 0.0, 1.0)

    tpg = gas.tpg
    n = sx_arr.size
    edges: list[EdgeConditions | None] = []
    status = np.full(n, "ok", dtype="<U40")
    T_e = np.full(n, np.nan)
    p_e = np.full(n, np.nan)
    V_e = np.full(n, np.nan)
    r_h = np.full(n, np.nan)
    r_s = np.full(n, np.nan)
    in_range = np.zeros(n, dtype=np.bool_)
    taw = np.full(n, np.nan)
    T_star = np.full(n, np.nan)
    r_factor = np.full(n, np.nan)
    h0_val = float("nan")
    for i in range(n):
        solution = solve_edge_state(
            gas=gas,
            ma_inf=mach_value,
            p_inf=float(p_inf),
            T_inf=float(T_inf),
            cp_pressure=float(cp_arr[i]),
            reference_incidence_s=float(s_ref_eff[i]),
        )
        h0_val = solution.h0_J_kg
        edges.append(solution.edge)
        status[i] = solution.status
        r_s[i] = solution.entropy_residual_J_kgK
        if solution.edge is None:
            continue
        e = solution.edge
        T_e[i], p_e[i], V_e[i] = e.T_e, e.p_e, e.v_e
        r_h[i] = solution.energy_residual_J_kg
        recovery = reference_enthalpy_recovery(
            gas=gas, h_e=solution.h_e_J_kg, V_e=e.v_e
        )
        taw[i] = recovery.T_aw_K
        T_star[i] = recovery.T_star_K
        r_factor[i] = recovery.recovery_factor
        in_range[i] = bool(solution.in_property_fit_range and tpg.in_fit_range(taw[i]))

    return WindwardEdgeCacheFaceted3D(
        edges=edges,
        alpha_rad=alpha_rad,
        mach=mach_value,
        pressure_incidence_arr=incidence_arr,
        cp_arr=cp_arr,
        cp_max=float(cp_max),
        reference_incidence_arr=s_ref_eff,
        taw_tpg=taw,
        h0_tpg=h0_val,
        edge_status=status,
        T_e_K=T_e,
        p_e_Pa=p_e,
        V_e_m_s=V_e,
        energy_residual_J_kg=r_h,
        entropy_residual_J_kgK=r_s,
        property_in_fit_range=in_range,
        T_star_K=T_star,
        recovery_factor=r_factor,
    )
