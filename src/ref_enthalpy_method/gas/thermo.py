"""Thermodynamic properties matching the Fluent air material definition."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class NASA9PiecewiseCp:
    """Fluent's seven-coefficient NASA-9 Cp polynomial for one material."""

    bounds_K: tuple[tuple[float, float], ...]
    coefficients: tuple[tuple[float, ...], ...]

    # Fluent's material defines Cp only on [200, 6000] K.  Outside that fit
    # range the model is extended with the endpoint Cp held constant, and h
    # and s0 are integrated consistently (dh/dT = cp, ds0/dT = cp/T).  Callers
    # that care whether a state lies in the fitted range use ``in_fit_range``;
    # nothing here clips a state silently.
    extension_bounds_K: tuple[float, float] = (20.0, 50000.0)

    @property
    def fit_range_K(self) -> tuple[float, float]:
        return (float(self.bounds_K[0][0]), float(self.bounds_K[-1][1]))

    def in_fit_range(self, T: float) -> bool:
        lower, upper = self.fit_range_K
        return bool(lower <= float(T) <= upper)

    def _checked_temperature(self, T: float) -> float:
        value = float(T)
        if not np.isfinite(value):
            raise ValueError("temperature must be finite")
        lower, upper = self.extension_bounds_K
        if not lower <= value <= upper:
            raise ValueError(
                f"temperature {value} K is outside the supported thermodynamic "
                f"extension range [{lower}, {upper}] K"
            )
        return value

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

    def _polynomial_cp(self, T: float) -> float:
        a1, a2, a3, a4, a5, a6, a7 = self._coefficients_at(T)
        return float(a1 / T**2 + a2 / T + a3 + a4 * T
                     + a5 * T**2 + a6 * T**3 + a7 * T**4)

    def cp(self, T: float) -> float:
        value = self._checked_temperature(T)
        lower, upper = self.fit_range_K
        return self._polynomial_cp(float(np.clip(value, lower, upper)))

    def _fit_integral(self, T: float, primitive: str) -> float:
        value = float(T)
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
        value = self._checked_temperature(T)
        lower, upper = self.fit_range_K
        if value < lower:
            return float(self._polynomial_cp(lower) * (value - lower))
        if value > upper:
            return float(self._fit_integral(upper, "enthalpy")
                         + self._polynomial_cp(upper) * (value - upper))
        return self._fit_integral(value, "enthalpy")

    def s0_from_T(self, T: float) -> float:
        value = self._checked_temperature(T)
        lower, upper = self.fit_range_K
        if value < lower:
            return float(self._polynomial_cp(lower) * np.log(value / lower))
        if value > upper:
            return float(self._fit_integral(upper, "entropy")
                         + self._polynomial_cp(upper) * np.log(value / upper))
        return self._fit_integral(value, "entropy")

    def _invert(self, value: float, *, quantity: str) -> float:
        target = float(value)
        if not np.isfinite(target):
            raise ValueError(f"{quantity} must be finite")
        lower, upper = self.extension_bounds_K
        function = self.h_from_T if quantity == "enthalpy" else self.s0_from_T
        if not function(lower) <= target <= function(upper):
            raise ValueError(
                f"{quantity} {target} is outside the supported thermodynamic "
                f"extension range [{lower}, {upper}] K"
            )
        for _ in range(100):
            middle = 0.5 * (lower + upper)
            if function(middle) < target:
                lower = middle
            else:
                upper = middle
            if upper - lower <= 1.0e-12 * upper:
                break
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
        value = float(T)
        return float(np.sqrt(self.gamma_T(value) * self.R * value))

    def in_fit_range(self, T: float) -> bool:
        return self.cp_model.in_fit_range(T)

    @property
    def fit_range_K(self) -> tuple[float, float]:
        return self.cp_model.fit_range_K

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
