"""Fluent-compatible ideal-gas transport property correlations."""

from __future__ import annotations

from collections.abc import Callable


def density_ideal_gas(p_Pa: float, T_K: float, *, R: float = 287.0) -> float:
    """Return the Fluent ``ideal-gas`` density in kg/m^3."""

    pressure = float(p_Pa)
    temperature = float(T_K)
    gas_constant = float(R)
    if pressure <= 0.0 or temperature <= 0.0 or gas_constant <= 0.0:
        raise ValueError("pressure, temperature, and R must be greater than zero")
    return pressure / (gas_constant * temperature)


def mu_sutherland(
    T: float,
    *,
    C1: float = 1.716e-5,
    C2: float = 273.11,
    S: float = 110.56,
) -> float:
    """Return Fluent's two-coefficient Sutherland viscosity for air."""

    temperature = float(T)
    if temperature <= 0.0:
        raise ValueError("temperature must be greater than zero")
    return C1 * (temperature / C2) ** 1.5 * (C2 + S) / (temperature + S)


def k_kinetic_theory(
    T: float,
    *,
    cp: Callable[[float], float],
    mu: Callable[[float], float],
    R: float = 287.0,
) -> float:
    """Return Fluent's air ``kinetic-theory`` conductivity in W/(m K).

    For the selected Fluent combination (NASA-9 Cp and Sutherland viscosity),
    the kinetic-theory model uses the modified Eucken relation::

        k = mu * (Cp + 1.25 * R)

    The molecular weight and Lennard-Jones fields remain material metadata;
    they are not additional inputs to this conductivity branch.
    """

    temperature = float(T)
    gas_constant = float(R)
    cp_value = float(cp(temperature))
    mu_value = float(mu(temperature))
    if min(temperature, gas_constant, cp_value, mu_value) <= 0.0:
        raise ValueError("kinetic-theory inputs must be greater than zero")
    return mu_value * (cp_value + 1.25 * gas_constant)
