"""Thermodynamics utilities.

Used by:
- Reference enthalpy method: Eckert reference enthalpy (2.38)
- Wall enthalpy model: h_w = cp_gas * T_w (see note near 2.57-2.58)
- Route A-TPG: thermally-perfect-gas adiabatic wall temperature (Phase 2E-P2)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# Fluent Cp(T) table (ideal-gas air, piecewise-polynomial, no chemistry)
# Source: Phase 2E-P2 specification table (Fluent corrected adiabatic wall comparison)
_FLUENT_CP_T_K = np.array(
    [200.0, 226.509, 250.0, 300.0, 400.0, 500.0, 700.0, 1000.0,
     1500.0, 1857.0, 2000.0, 2232.0, 2500.0, 2700.0, 3000.0,
     3500.0, 4000.0, 4500.0, 5000.0, 5500.0, 6000.0],
    dtype=float,
)
_FLUENT_CP_J_kgK = np.array(
    [1002.4, 1002.6, 1003.1, 1004.9, 1013.5, 1029.5, 1075.0, 1140.7,
     1211.1, 1240.5, 1250.2, 1262.9, 1275.4, 1283.5, 1294.0,
     1308.0, 1319.2, 1328.8, 1338.0, 1348.1, 1360.1],
    dtype=float,
)


@dataclass(frozen=True)
class TPGThermo:
    """Thermally-perfect-gas thermo model from tabulated Cp(T).

    Constructs h(T) = integral Cp dT, s0(T) = integral Cp/T dT,
    gamma(T) = Cp/(Cp-R), a(T) = sqrt(gamma R T).

    All dimensional quantities in SI units.
    """

    T_table: np.ndarray  # K
    cp_table: np.ndarray  # J/(kg K)
    h_table: np.ndarray  # J/kg (cumulative from T[0])
    s0_table: np.ndarray  # J/(kg K) (cumulative from T[0])
    gamma_table: np.ndarray
    a_table: np.ndarray  # m/s
    R: float = 287.0

    def h_from_T(self, T: float) -> float:
        return float(np.interp(float(T), self.T_table.ravel(), self.h_table.ravel()))

    def T_from_h(self, h: float) -> float:
        return float(np.interp(float(h), self.h_table.ravel(), self.T_table.ravel()))

    def s0_from_T(self, T: float) -> float:
        return float(np.interp(float(T), self.T_table.ravel(), self.s0_table.ravel()))

    def T_from_s0(self, s0: float) -> float:
        return float(np.interp(float(s0), self.s0_table.ravel(), self.T_table.ravel()))

    def cp(self, T: float) -> float:
        return float(np.interp(float(T), self.T_table.ravel(), self.cp_table.ravel()))

    def gamma_T(self, T: float) -> float:
        cp_val = self.cp(float(T))
        return float(cp_val / (cp_val - self.R))

    def a_T(self, T: float) -> float:
        g = float(self.gamma_T(float(T)))
        return float(np.sqrt(g * float(self.R) * float(T)))

    def vector_h_from_T(self, T: np.ndarray) -> np.ndarray:
        return np.interp(np.asarray(T, dtype=float).ravel(), self.T_table.ravel(), self.h_table.ravel())

    def vector_T_from_h(self, h: np.ndarray) -> np.ndarray:
        return np.interp(np.asarray(h, dtype=float).ravel(), self.h_table.ravel(), self.T_table.ravel())

    def vector_gamma_T(self, T: np.ndarray) -> np.ndarray:
        cp_arr = np.interp(np.asarray(T, dtype=float).ravel(), self.T_table.ravel(), self.cp_table.ravel())
        return cp_arr / (cp_arr - self.R)

    def vector_a_T(self, T: np.ndarray) -> np.ndarray:
        g = self.vector_gamma_T(np.asarray(T, dtype=float).ravel())
        return np.sqrt(g * self.R * np.asarray(T, dtype=float).ravel())


def _cumulative_trapezoid(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    z = np.zeros_like(y, dtype=float)
    z[0] = 0.0
    for i in range(1, len(z)):
        z[i] = z[i - 1] + 0.5 * (float(y[i]) + float(y[i - 1])) * (float(x[i]) - float(x[i - 1]))
    return z


def make_fluent_tpg_thermo(R: float = 287.0) -> TPGThermo:
    T = _FLUENT_CP_T_K.copy()
    cp = _FLUENT_CP_J_kgK.copy()

    h = _cumulative_trapezoid(cp, T)
    h = h - h[0]

    integrand = cp / np.maximum(T, 1e-12)
    s0 = _cumulative_trapezoid(integrand, T)
    s0 = s0 - s0[0]

    gamma_arr = cp / (cp - R)
    a_arr = np.sqrt(gamma_arr * R * T)

    return TPGThermo(
        T_table=T,
        cp_table=cp,
        h_table=h,
        s0_table=s0,
        gamma_table=gamma_arr,
        a_table=a_arr,
        R=R,
    )
