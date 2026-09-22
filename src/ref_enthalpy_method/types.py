"""Shared gas and edge-state datatypes for the Taw pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GasModel:
    """Thermally-perfect-gas hooks used by the active solver chain."""

    gamma: float
    R: float
    cp_gas: Callable[[float], float]  # cp(T) -> J/kg/K
    h_from_T: Callable[[float], float]  # h(T) -> J/kg
    T_from_h: Callable[[float], float]  # inverse mapping
    mu: Callable[[float], float]  # mu(T) -> Pa*s
    rho: Callable[[float, float], float]  # rho(p, T) -> kg/m^3
    k: Callable[[float], float]  # k(T) -> W/(m K)
    tpg: Any  # TPGThermo instance
    prandtl: float = 0.72

    def prandtl_at_T(self, T: float) -> float:
        """Return the local Prandtl number from the active transport models."""

        conductivity = float(self.k(float(T)))
        value = float(self.mu(float(T)) * self.cp_gas(float(T)) / conductivity)
        if conductivity <= 0.0 or value <= 0.0:
            raise ValueError("gas transport properties must produce positive Prandtl number")
        return value


@dataclass(frozen=True)
class EdgeConditions:
    """Boundary-layer edge quantities at a surface point."""

    p_e: float
    rho_e: float
    T_e: float
    ma_e: float
    a_e: float
    v_e: float
    mu_e: float
