"""Configuration required by the fully turbulent windward Taw provider."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PhiClampConfig:
    enable: bool = True
    phi_min_rad: float = 1.0e-8


@dataclass(frozen=True)
class WindwardTawConfig:
    phi_clamp: PhiClampConfig = field(default_factory=PhiClampConfig)
    x_min_over_c: float = 0.003

    def __post_init__(self) -> None:
        if self.x_min_over_c < 0.0:
            raise ValueError("x_min_over_c must be nonnegative")
