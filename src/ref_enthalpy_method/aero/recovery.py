"""Fully turbulent adiabatic recovery with Eckert reference-enthalpy properties.

Eckert reference enthalpy::

    h* = h_e + 0.5 (h_w - h_e) + 0.22 (h_r - h_e)

For an adiabatic wall ``h_w = h_aw = h_r``, so ``h* = h_e + 0.72 (h_aw - h_e)``.
The turbulent recovery factor is evaluated at the reference state,
``r = Pr(T*)^(1/3)`` with ``T* = T(h*)``, and ``h_aw = h_e + r V_e^2 / 2``.
``h_aw`` and ``T*`` depend on each other, so the pair is solved by fixed-point
iteration (``Pr`` varies slowly with ``T``; the map contracts strongly).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..types import GasModel

ECKERT_WALL_WEIGHT = 0.5
ECKERT_RECOVERY_WEIGHT = 0.22
RECOVERY_MODEL = "eckert-reference-enthalpy Pr(T*)^(1/3), adiabatic h_w = h_aw"


@dataclass(frozen=True)
class RecoveryState:
    h_aw_J_kg: float
    T_aw_K: float
    T_star_K: float
    recovery_factor: float
    iterations: int


def reference_enthalpy_recovery(
    *, gas: GasModel, h_e: float, V_e: float, tol_J_kg: float = 1.0e-6
) -> RecoveryState:
    h_e = float(h_e)
    kinetic = 0.5 * float(V_e) ** 2
    weight = ECKERT_WALL_WEIGHT + ECKERT_RECOVERY_WEIGHT
    T_e = float(gas.T_from_h(h_e))
    r = float(gas.prandtl_at_T(T_e)) ** (1.0 / 3.0)
    h_aw = h_e + r * kinetic
    for iteration in range(1, 101):
        T_star = float(gas.T_from_h(h_e + weight * (h_aw - h_e)))
        r = float(gas.prandtl_at_T(T_star)) ** (1.0 / 3.0)
        h_new = h_e + r * kinetic
        if abs(h_new - h_aw) <= tol_J_kg:
            h_aw = h_new
            break
        h_aw = h_new
    else:
        raise RuntimeError("reference-enthalpy recovery did not converge")
    T_star = float(gas.T_from_h(h_e + weight * (h_aw - h_e)))
    return RecoveryState(
        h_aw_J_kg=float(h_aw),
        T_aw_K=float(gas.T_from_h(h_aw)),
        T_star_K=T_star,
        recovery_factor=float(r),
        iterations=iteration,
    )
