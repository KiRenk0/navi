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
    tpg: Any  # TPGThermo instance
    prandtl: float = 0.72


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
