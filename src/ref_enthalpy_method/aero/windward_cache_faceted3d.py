"""Windward edge-cache for faceted 3D (sx, sy) slopes.

This is a minimal 3D upgrade that preserves the original solver architecture:
- keep the same reference-enthalpy "soup"
- replace the 2D windward slope dz/dx with a facet-normal based inflow angle phi(sx, sy)

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

from ..aero.edge_conditions import compute_edge_conditions
from ..aero.pressure_coefficient import (
    modified_newtonian_cp,
    modified_newtonian_cp_max,
)
from ..geometry.local_incidence import (
    classify_incidence,
    outward_normal_from_slopes,
)
from ..types import EdgeConditions, GasModel


@dataclass(frozen=True)
class WindwardEdgeCacheFaceted3D:
    edges: list[EdgeConditions]  # length nx
    alpha_rad: float = float("nan")
    mach: float = float("nan")
    pressure_incidence_arr: np.ndarray | None = None  # (nx,) signed -u.n
    cp_arr: np.ndarray | None = None  # (nx,) pressure coefficient
    cp_max: float = float("nan")
    cp0: float = float("nan")
    taw_tpg: np.ndarray | None = None  # (nx,) Route A-TPG adiabatic wall temp
    h0_tpg: float | None = None  # total enthalpy (J/kg) from TPG thermo


def build_windward_edge_cache_faceted3d(
    *,
    gas: GasModel,
    mach: float,
    alpha_deg: float,
    p_inf: float,
    rho_inf: float,
    T_inf: float,
    xc_grid: np.ndarray,
    sx_arr: np.ndarray,
    sy_arr: np.ndarray,
    sheet: Literal["upper", "lower"] = "upper",
) -> WindwardEdgeCacheFaceted3D:
    """Compute modified-Newtonian edge conditions along a faceted 3D strip."""

    if sheet not in {"upper", "lower"}:
        raise ValueError("sheet must be 'upper' or 'lower'")

    mach_value = float(mach)
    alpha_rad = float(np.deg2rad(float(alpha_deg)))

    x_over_c = np.asarray(xc_grid, dtype=float).reshape(-1)
    sx_arr = np.asarray(sx_arr, dtype=float).reshape(-1)
    sy_arr = np.asarray(sy_arr, dtype=float).reshape(-1)
    if sx_arr.size != x_over_c.size or sy_arr.size != x_over_c.size:
        raise ValueError("sx_arr and sy_arr must have the same length as xc_grid")
    if x_over_c.size == 0 or not (
        np.all(np.isfinite(x_over_c))
        and np.all(np.isfinite(sx_arr))
        and np.all(np.isfinite(sy_arr))
    ):
        raise ValueError("xc_grid, sx_arr, and sy_arr must be nonempty and finite")

    # Cp0 at leading edge should not depend on the first sampling point.
    # If x/c does not start at 0, extrapolate (sx, sy) to x/c=0 using the first two points.
    sx0 = float(sx_arr[0])
    sy0 = float(sy_arr[0])
    if x_over_c.size >= 2 and float(x_over_c[0]) > 0.0:
        x0 = float(x_over_c[0])
        x1 = float(x_over_c[1])
        if x1 != x0:
            sx0 = float(
                sx_arr[0] - x0 * (float(sx_arr[1]) - float(sx_arr[0])) / (x1 - x0)
            )
            sy0 = float(
                sy_arr[0] - x0 * (float(sy_arr[1]) - float(sy_arr[0])) / (x1 - x0)
            )

    # The 3D normal already contains sweep, so pressure incidence uses the
    # actual body-axis angle rather than the strip-theory effective angle.
    normal0 = outward_normal_from_slopes(
        sx=np.asarray(sx0), sy=np.asarray(sy0), sheet=sheet
    )
    incidence0 = float(classify_incidence(normal_out=normal0, alpha_deg=alpha_deg)[0])
    cp_max = modified_newtonian_cp_max(mach=mach_value, gamma=float(gas.gamma))
    cp0 = modified_newtonian_cp(
        incidence_s=incidence0,
        mach=mach_value,
        gamma=float(gas.gamma),
    )

    normals = outward_normal_from_slopes(sx=sx_arr, sy=sy_arr, sheet=sheet)
    incidence_arr = np.asarray(
        classify_incidence(normal_out=normals, alpha_deg=alpha_deg)[0],
        dtype=float,
    )
    cp_arr = np.asarray(
        [
            modified_newtonian_cp(
                incidence_s=float(incidence),
                mach=mach_value,
                gamma=float(gas.gamma),
            )
            for incidence in incidence_arr
        ],
        dtype=float,
    )

    # Subsonic and stagnation edge states are physical near a blunt nose; do
    # not reduce cp0 merely to force Ma_e >= 1.
    edges = [
        compute_edge_conditions(
            gas=gas,
            ma_inf=mach_value,
            p_inf=float(p_inf),
            T_inf=float(T_inf),
            rho_inf=float(rho_inf),
            cp_pressure=float(cp_pressure),
            cp0_pressure=float(cp0),
        )
        for cp_pressure in cp_arr
    ]

    taw_tpg: np.ndarray | None = None
    h0_tpg: float | None = None
    if getattr(gas, "tpg", None) is not None:
        tpg = gas.tpg
        a_inf = float(tpg.a_T(float(T_inf)))
        v_inf = mach_value * a_inf
        h_inf_tpg = float(tpg.h_from_T(float(T_inf)))
        h0_val = h_inf_tpg + 0.5 * v_inf * v_inf
        h0_tpg = h0_val

        nx_val = len(edges)
        taw_arr = np.full(nx_val, np.nan, dtype=float)
        for i in range(nx_val):
            e = edges[i]
            T_e_i = float(e.T_e)
            V_e_i = float(e.v_e)
            if not (np.isfinite(T_e_i) and np.isfinite(V_e_i)):
                continue

            r_aw = float(gas.prandtl_at_T(T_e_i)) ** (1.0 / 3.0)
            h_e_val = float(tpg.h_from_T(T_e_i))
            h_aw_val = h_e_val + r_aw * 0.5 * V_e_i * V_e_i
            taw_arr[i] = float(tpg.T_from_h(h_aw_val))

        taw_tpg = taw_arr

    return WindwardEdgeCacheFaceted3D(
        edges=edges,
        alpha_rad=alpha_rad,
        mach=mach_value,
        pressure_incidence_arr=np.asarray(incidence_arr, dtype=float),
        cp_arr=np.asarray(cp_arr, dtype=float),
        cp_max=float(cp_max),
        cp0=float(cp0),
        taw_tpg=taw_tpg,
        h0_tpg=h0_tpg,
    )
