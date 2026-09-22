"""Thermodynamic properties matching the Fluent air material definition."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class NASA9PiecewiseCp:
    """Fluent's seven-coefficient NASA-9 Cp polynomial for one material."""

    bounds_K: tuple[tuple[float, float], ...]
    coefficients: tuple[tuple[float, ...], ...]

    def _temperature(self, T: float) -> float:
        value = float(T)
        if not np.isfinite(value):
            raise ValueError("temperature must be finite")
        return float(np.clip(value, self.bounds_K[0][0], self.bounds_K[-1][1]))

    def _range_index(self, T: float) -> int:
        for index, (_, upper) in enumerate(self.bounds_K):
            if T <= upper:
                return index
        return len(self.bounds_K) - 1

    def _coefficients_at(self, T: float) -> tuple[float, ...]:
        return self.coefficients[self._range_index(T)]

    @staticmethod
    def _cp_primitive(coefficients: tuple[float, ...], T: float) -> float:
        a1, a2, a3, a4, a5, a6, a7 = coefficients
        return (-a1 / T + a2 * np.log(T) + a3 * T + 0.5 * a4 * T**2
                + (a5 / 3.0) * T**3 + 0.25 * a6 * T**4 + 0.2 * a7 * T**5)

    @staticmethod
    def _entropy_primitive(coefficients: tuple[float, ...], T: float) -> float:
        a1, a2, a3, a4, a5, a6, a7 = coefficients
        return (-0.5 * a1 / T**2 - a2 / T + a3 * np.log(T) + a4 * T
                + 0.5 * a5 * T**2 + (a6 / 3.0) * T**3 + 0.25 * a7 * T**4)

    def cp(self, T: float) -> float:
        value = self._temperature(T)
        a1, a2, a3, a4, a5, a6, a7 = self._coefficients_at(value)
        return float(a1 / value**2 + a2 / value + a3 + a4 * value
                     + a5 * value**2 + a6 * value**3 + a7 * value**4)

    def _integral(self, T: float, primitive: str) -> float:
        value = self._temperature(T)
        reference = self.bounds_K[0][0]
        primitive_fn = self._cp_primitive if primitive == "enthalpy" else self._entropy_primitive
        integral = 0.0
        for index, (lower, upper) in enumerate(self.bounds_K):
            if value <= lower:
                break
            end = min(value, upper)
            start = max(reference, lower)
            coefficients = self.coefficients[index]
            integral += primitive_fn(coefficients, end) - primitive_fn(coefficients, start)
            if value <= upper:
                break
        return float(integral)

    def h_from_T(self, T: float) -> float:
        return self._integral(T, "enthalpy")

    def s0_from_T(self, T: float) -> float:
        return self._integral(T, "entropy")

    def _invert(self, value: float, *, quantity: str) -> float:
        target = float(value)
        if not np.isfinite(target):
            raise ValueError(f"{quantity} must be finite")
        lower = self.bounds_K[0][0]
        upper = self.bounds_K[-1][1]
        function = self.h_from_T if quantity == "enthalpy" else self.s0_from_T
        target = float(np.clip(target, function(lower), function(upper)))
        for _ in range(64):
            middle = 0.5 * (lower + upper)
            if function(middle) < target:
                lower = middle
            else:
                upper = middle
        return float(0.5 * (lower + upper))

    def T_from_h(self, h: float) -> float:
        return self._invert(h, quantity="enthalpy")

    def T_from_s0(self, s0: float) -> float:
        return self._invert(s0, quantity="entropy")


_FLUENT_AIR_NASA9_CP = NASA9PiecewiseCp(
    bounds_K=((200.0, 1000.0), (1000.0, 6000.0)),
    coefficients=(
        (2.898903e6, -5.649626e4, 1.437799e3, -1.653609,
         3.062254e-3, -2.279138e-6, 6.272365e-10),
        (6.932494e7, -3.610532e5, 1.476665e3, -6.138349e-2,
         2.027963e-5, -3.075525e-9, 1.888054e-13),
    ),
)


@dataclass(frozen=True)
class TPGThermo:
    """Thermally-perfect gas derived from Fluent's NASA-9 Cp definition."""

    cp_model: NASA9PiecewiseCp
    R: float = 287.0

    def h_from_T(self, T: float) -> float:
        return self.cp_model.h_from_T(T)

    def T_from_h(self, h: float) -> float:
        return self.cp_model.T_from_h(h)

    def s0_from_T(self, T: float) -> float:
        return self.cp_model.s0_from_T(T)

    def T_from_s0(self, s0: float) -> float:
        return self.cp_model.T_from_s0(s0)

    def cp(self, T: float) -> float:
        return self.cp_model.cp(T)

    def gamma_T(self, T: float) -> float:
        cp_value = self.cp(T)
        return float(cp_value / (cp_value - self.R))

    def a_T(self, T: float) -> float:
        value = self.cp_model._temperature(T)
        return float(np.sqrt(self.gamma_T(value) * self.R * value))

    def vector_h_from_T(self, T: np.ndarray) -> np.ndarray:
        return np.asarray([self.h_from_T(value) for value in np.asarray(T).ravel()])

    def vector_T_from_h(self, h: np.ndarray) -> np.ndarray:
        return np.asarray([self.T_from_h(value) for value in np.asarray(h).ravel()])

    def vector_gamma_T(self, T: np.ndarray) -> np.ndarray:
        return np.asarray([self.gamma_T(value) for value in np.asarray(T).ravel()])

    def vector_a_T(self, T: np.ndarray) -> np.ndarray:
        return np.asarray([self.a_T(value) for value in np.asarray(T).ravel()])


def make_fluent_tpg_thermo(R: float = 287.0) -> TPGThermo:
    return TPGThermo(cp_model=_FLUENT_AIR_NASA9_CP, R=float(R))
