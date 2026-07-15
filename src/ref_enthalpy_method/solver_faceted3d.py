"""Faceted 3D branch solver (strong-3D minimal upgrade).

Design goals (per 鏂扮考鍨?md):
- Do not contaminate the baseline 2D solver in `solver.py`
- Reuse the same physical "soup" (gas, atmosphere, heatflux, outputs)
- Replace ONLY the windward edge-chain angle definition (phi) to depend on (sx, sy)
- Apply a planform mask (triangle) for a lifting-body half planform
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from .aero.leeward_recovery import build_leeward_freestream_recovery
from .aero.windward_cache_faceted3d import (
    WindwardEdgeCacheFaceted3D,
    build_windward_edge_cache_faceted3d,
    resolve_faceted3d_edge_inflow,
    windward_q_at_index,
    windward_q_distribution_from_Tw,
)
from .aero.transition import transition_reynolds, transition_weight
from .config.lf_qw import LfQwConfig
from .gas.thermo import make_fluent_tpg_thermo
from .gas.transport import mu_sutherland
from .geometry.faceted3d import (
    Faceted3DConfig,
    facet_normal_from_slopes,
    load_outline_csv,
    outline_strip_xle_chord_mask,
    triangle_strip_xle_chord_mask,
)
from .geometry.local_incidence import (
    INCIDENCE_EPSILON,
    NORMAL_SOURCE_INVALID,
    diagnose_sheet_from_geometry,
)
from .geometry.stl_surface import AsciiStlMesh, SurfaceSlopeSampler
from .heatflux.leading_edge import kemp_riddell_modified_qsph_baseline, leading_edge_heat_flux_baseline
from .heatflux.leeward import (
    leeward_heat_flux_distribution,
    leeward_re_ns,
    leeward_stanton_distribution,
    normal_shock_temperature_ratio,
)
from .heatflux.windward import windward_ref_enthalpy_branches
from .sampling.grid import make_sampling_grids
from .specs.loader import load_yaml
from .specs.models import CaseSpec, SamplingSpec, VehicleSpec
from .thermal.leeward_equilibrium import solve_leeward_radiative_equilibrium_coupled
from .thermal.transient import march_explicit_balance, march_explicit_balance_final, require_transient_material
from .thermal.windward_equilibrium import solve_windward_radiative_equilibrium
from .types import GasModel
from .utils.warnings import WarningLog


def _smooth_spanwise_slope_columns(
    *,
    sx_cols: np.ndarray,
    sy_cols: np.ndarray,
    valid_mask: np.ndarray,
    passes: int = 2,
) -> tuple[np.ndarray, np.ndarray]:
    """Smooth STL-derived leading-edge slopes across span using neighboring normals.

    We smooth *normals* instead of raw slope values so that occasional steep
    facet samples near the leading edge are blended in a more geometric way.
    """

    sx = np.asarray(sx_cols, dtype=float).copy()
    sy = np.asarray(sy_cols, dtype=float).copy()
    valid = np.asarray(valid_mask, dtype=bool)
    if sx.shape != sy.shape or sx.shape != valid.shape:
        raise ValueError("sx_cols, sy_cols, and valid_mask must have the same shape")
    if sx.ndim != 2:
        raise ValueError("slope smoothing expects 2D (ny, nx_sel) arrays")
    if sx.size == 0 or int(passes) <= 0 or sx.shape[0] < 2:
        return sx, sy

    normals = facet_normal_from_slopes(sx=sx, sy=sy)
    normals = np.where(valid[..., None], normals, np.nan)

    for _ in range(int(passes)):
        out = normals.copy()
        for j in range(normals.shape[0]):
            row_valid = valid[j]
            if not np.any(row_valid):
                continue
            for i in range(normals.shape[1]):
                if not bool(row_valid[i]):
                    continue
                vec = 2.0 * normals[j, i]
                w = 2.0
                if j > 0 and bool(valid[j - 1, i]):
                    vec = vec + normals[j - 1, i]
                    w += 1.0
                if j + 1 < normals.shape[0] and bool(valid[j + 1, i]):
                    vec = vec + normals[j + 1, i]
                    w += 1.0
                vec = vec / max(w, 1.0)
                norm = float(np.linalg.norm(vec))
                if norm > 1e-12:
                    out[j, i] = vec / norm
        normals = out

    nz = normals[..., 2]
    mask = valid & np.isfinite(nz) & (np.abs(nz) > 1e-10)
    sx[mask] = -normals[..., 0][mask] / nz[mask]
    sy[mask] = -normals[..., 1][mask] / nz[mask]
    return sx, sy


def _smooth_spanwise_scalar_series(*, values: np.ndarray, valid_mask: np.ndarray, passes: int = 2) -> np.ndarray:
    """Light 1D spanwise smoothing for stripwise scalar diagnostics such as cp0."""

    out = np.asarray(values, dtype=float).copy()
    valid = np.asarray(valid_mask, dtype=bool).reshape(-1)
    if out.ndim != 1 or valid.ndim != 1 or out.size != valid.size:
        raise ValueError("scalar smoothing expects matching 1D arrays")
    if out.size < 2 or int(passes) <= 0:
        return out

    for _ in range(int(passes)):
        new = out.copy()
        for j in range(out.size):
            if not bool(valid[j]) or not np.isfinite(float(out[j])):
                continue
            acc = 2.0 * float(out[j])
            w = 2.0
            if j > 0 and bool(valid[j - 1]) and np.isfinite(float(out[j - 1])):
                acc += float(out[j - 1])
                w += 1.0
            if j + 1 < out.size and bool(valid[j + 1]) and np.isfinite(float(out[j + 1])):
                acc += float(out[j + 1])
                w += 1.0
            new[j] = acc / max(w, 1.0)
        out = new
    return out


def _radius_aware_x_floor_m(*, x_min_over_c: float, chord_m: float, rn_local_m: float, rn_floor_factor: float = 0.15) -> float:
    """Minimum streamwise distance for strip-theory behind a rounded leading edge.

    The reference-enthalpy strip closure is not reliable essentially on top of the
    rounded leading edge. When the local strip chord becomes very small near the tip,
    a pure x/c floor can place the first off-leading-edge sample *inside* the local
    nose-radius zone and create a false hotspot that overtops the Kemp-Riddell peak.
    """

    chord_floor = max(max(float(x_min_over_c), 0.0) * float(chord_m), 1e-6)
    rn_floor = max(float(rn_floor_factor), 0.0) * max(float(rn_local_m), 0.0)
    return float(max(chord_floor, rn_floor, 1e-6))


def _reject_stl_surface_outliers(
    *,
    sx_arr: np.ndarray,
    sy_arr: np.ndarray,
    ref_sx: float,
    ref_sy: float,
    max_normal_angle_deg: float = 20.0,
    min_abs_nz: float = 0.45,
) -> tuple[np.ndarray, np.ndarray]:
    """Reject STL samples that are inconsistent with the expected skin direction.

    The faceted3d branch still assumes a nominal upper/lower skin family. If the
    sampled STL normal deviates too far from that family, the point is usually a
    side/cap/transition face rather than the intended aerodynamic skin.
    """

    sx = np.asarray(sx_arr, dtype=float).copy()
    sy = np.asarray(sy_arr, dtype=float).copy()
    if sx.shape != sy.shape:
        raise ValueError("sx_arr and sy_arr must have the same shape")
    if sx.size == 0:
        return sx, sy

    valid = np.isfinite(sx) & np.isfinite(sy)
    if not np.any(valid):
        return sx, sy

    normals = facet_normal_from_slopes(sx=sx, sy=sy)
    ref_normal = facet_normal_from_slopes(sx=np.array([float(ref_sx)]), sy=np.array([float(ref_sy)]))[0]
    dot = np.sum(normals * ref_normal.reshape((1,) * (normals.ndim - 1) + (3,)), axis=-1)
    dot = np.clip(dot, -1.0, 1.0)
    keep = valid & (dot >= math.cos(math.radians(float(max_normal_angle_deg)))) & (np.abs(normals[..., 2]) >= float(min_abs_nz))
    sx[~keep] = np.nan
    sy[~keep] = np.nan
    return sx, sy


class WingLowFidelitySolverFaceted3D:
    """Baseline-compatible solver fa莽ade, faceted 3D windward branch."""

    def __init__(self, *, vehicle_config: str, case_config: str, sampling_config: str, run_dir: str):
        self.project_root = self._resolve_project_root()
        self.veh_path = (self.project_root / vehicle_config).resolve()
        self.case_path = (self.project_root / case_config).resolve()
        self.samp_path = (self.project_root / sampling_config).resolve()
        self.run_dir = (self.project_root / run_dir).resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)

        # Warnings file (baseline-style)
        self.warning_log = WarningLog(path=self.run_dir / "lf_warnings.log", enabled=True)
        self.warning_log.reset_file()

        # Loaded specs
        self.veh_spec_raw = load_yaml(self.veh_path)
        self.case_spec_raw = load_yaml(self.case_path)
        self.sampling_spec_raw = load_yaml(self.samp_path)

        self.vehicle = VehicleSpec.from_yaml_dict(self.veh_spec_raw)
        self.case = CaseSpec.from_yaml_dict(self.case_spec_raw)
        self.sampling = SamplingSpec.from_yaml_dict(self.sampling_spec_raw)
        self.lf_cfg = LfQwConfig.from_case(self.case)

        # Faceted3D config (required for this solver branch)
        vs = self.veh_spec_raw.get("vehicle_spec", {}) if isinstance(self.veh_spec_raw, dict) else {}
        f3 = vs.get("faceted3d", {}) if isinstance(vs, dict) else {}
        self.f3_cfg = Faceted3DConfig.from_faceted3d_spec(dict(f3))
        if (not bool(self.f3_cfg.edge_use_effective_alpha)) or bool(self.f3_cfg.edge_use_effective_mach):
            self._warn(
                "faceted3d edge-state override active"
                f" | use_effective_alpha={bool(self.f3_cfg.edge_use_effective_alpha)}"
                f" | use_effective_mach={bool(self.f3_cfg.edge_use_effective_mach)}"
            )
        if str(self.f3_cfg.x_length_mode).strip().lower() != "streamline":
            self._warn(f"faceted3d x-length override active | mode={str(self.f3_cfg.x_length_mode).strip().lower()}")

        # Optional: load planform outline CSV (most robust geometry source).
        self.outline_x_m: np.ndarray | None = None
        self.outline_span_m: np.ndarray | None = None
        self.slope_sampler: SurfaceSlopeSampler | None = None
        self.planform_b_half_m: float = float(self.vehicle.b_half_m)
        if self.f3_cfg.outline_csv_path:
            p = (self.veh_path.parent / str(self.f3_cfg.outline_csv_path)).resolve()
            ox, oy = load_outline_csv(
                csv_path=p,
                x_col=str(self.f3_cfg.outline_x_col),
                span_col=str(self.f3_cfg.outline_span_col),
                span_sign=float(self.f3_cfg.outline_span_sign),
            )
            # Use non-negative span only for half-planform (we can mirror externally).
            span = np.asarray(oy, dtype=float)
            if np.nanmax(span) < 0:
                span = -span
            span = np.abs(span)
            self.outline_x_m = np.asarray(ox, dtype=float)
            self.outline_span_m = np.asarray(span, dtype=float)
            b_half_outline = float(np.nanmax(self.outline_span_m))
            if np.isfinite(b_half_outline) and b_half_outline > 0:
                self.planform_b_half_m = b_half_outline
                # Warn if mismatch is large (helps catch wrong units)
                b_spec = float(self.vehicle.b_half_m)
                if np.isfinite(b_spec) and b_spec > 0:
                    rel = abs(b_half_outline - b_spec) / b_spec
                    if rel > 0.05:
                        self._warn(
                            f"planform b_half mismatch: outline={b_half_outline:.6g} m vs spec={b_spec:.6g} m (rel={rel:.2%}). "
                            f"Using outline value for sampling."
                        )

        # Optional: load ASCII STL surface for local slope sampling.
        if self.f3_cfg.surface_stl_path:
            stl_path = (self.veh_path.parent / str(self.f3_cfg.surface_stl_path)).resolve()
            mesh = AsciiStlMesh.load(
                stl_path=stl_path,
                unit=str(self.f3_cfg.stl_unit),
                span_sign=float(self.f3_cfg.stl_span_sign),
                right_half_only=bool(self.f3_cfg.stl_right_half_only),
            )
            self.slope_sampler = SurfaceSlopeSampler(mesh=mesh)

        # Gas model (thermally perfect gas + Sutherland)
        tpg_instance = make_fluent_tpg_thermo(R=self.case.R_J_per_kgK)
        self.gas = GasModel(
            gamma=self.case.gamma,
            R=self.case.R_J_per_kgK,
            cp_gas=tpg_instance.cp,
            h_from_T=tpg_instance.h_from_T,
            T_from_h=tpg_instance.T_from_h,
            mu=mu_sutherland,
            prandtl=self.case.pr,
            tpg=tpg_instance,
        )

        # Sampling grids
        grids = make_sampling_grids(self.sampling)
        self.xc_grid = grids.xc_grid
        self.yb_grid = grids.yb_grid
        self.nx = int(self.xc_grid.size)
        self.ny = int(self.yb_grid.size)
        self._tip_endpoint_regularized = False
        self._regularize_degenerate_tip_endpoint()

        # Default facet slopes (constants); if STL is provided, these can be overridden per-point.
        self.sx_up, self.sy_up, self.sx_lo, self.sy_lo = self.f3_cfg.slopes()

        # Public result cache (baseline-style)
        self.last_fields: dict[str, Any] = {}
        self._edge_cache_warning_keys: set[tuple[Any, ...]] = set()
        self._cp0_override_by_strip: list[float | None] = []
        self._x_phys_override_by_strip: list[np.ndarray | None] = []

    def _warn(self, msg: str) -> None:
        self.warning_log.warn(msg)

    def _resolve_edge_inflow(self, *, mach: float, alpha_deg: float):
        return resolve_faceted3d_edge_inflow(
            mach=float(mach),
            alpha_deg=float(alpha_deg),
            sweep_le_deg=float(self.vehicle.sweep_le_deg),
            use_effective_alpha=bool(self.f3_cfg.edge_use_effective_alpha),
            use_effective_mach=bool(self.f3_cfg.edge_use_effective_mach),
        )

    def _x_length_mode(self) -> str:
        mode = str(getattr(self.f3_cfg, "x_length_mode", "streamline")).strip().lower()
        if mode not in {"local", "global", "streamline"}:
            return "streamline"
        return mode

    def _x_eval_floor_m(self, *, chord_m: float, y_over_b: float) -> float:
        x_min_over_c = float(getattr(self.lf_cfg, "x_model").x_min_over_c) if hasattr(self.lf_cfg, "x_model") else 0.003
        rn_local = float(self._rn_local(chord_m=float(chord_m), y_over_b=float(y_over_b)))
        return _radius_aware_x_floor_m(
            x_min_over_c=float(x_min_over_c),
            chord_m=float(chord_m),
            rn_local_m=float(rn_local),
            rn_floor_factor=0.15,
        )

    @staticmethod
    def _interp_x_le_clamped(*, y_m: float, span_nodes_m: np.ndarray, x_le_nodes_m: np.ndarray) -> float:
        return float(
            np.interp(
                float(np.clip(float(y_m), float(span_nodes_m[0]), float(span_nodes_m[-1]))),
                np.asarray(span_nodes_m, dtype=float),
                np.asarray(x_le_nodes_m, dtype=float),
            )
        )

    def _streamline_length_to_le(
        self,
        *,
        x_m: float,
        y_m: float,
        sx: float,
        sy: float,
        alpha_edge_rad: float,
        span_nodes_m: np.ndarray,
        x_le_nodes_m: np.ndarray,
    ) -> float | None:
        """Approximate surface streamline distance back to the planform leading edge.

        The streamline direction is taken as the incoming-flow projection onto the
        local surface tangent plane. This is an engineering approximation for the
        development length on strong-3D faceted surfaces; it is intentionally kept
        local and lightweight rather than solving a full surface-streamline field.
        """

        denom_n = math.sqrt(1.0 + float(sx) * float(sx) + float(sy) * float(sy))
        if not (denom_n > 1e-12):
            return None
        nx = -float(sx) / denom_n
        ny = -float(sy) / denom_n
        nz = 1.0 / denom_n

        ux = math.cos(float(alpha_edge_rad))
        uy = 0.0
        uz = -math.sin(float(alpha_edge_rad))
        dot = ux * nx + uy * ny + uz * nz
        tx = ux - dot * nx
        ty = uy - dot * ny
        tz = uz - dot * nz
        tnorm = math.sqrt(tx * tx + ty * ty + tz * tz)
        if not (tnorm > 1e-12):
            return None
        tx /= tnorm
        ty /= tnorm
        if not (tx > 1e-10):
            return None

        def _f(s_m: float) -> float:
            yy = float(y_m) - float(s_m) * ty
            xx = float(x_m) - float(s_m) * tx
            x_le = self._interp_x_le_clamped(y_m=yy, span_nodes_m=span_nodes_m, x_le_nodes_m=x_le_nodes_m)
            return float(xx - x_le)

        f0 = _f(0.0)
        if f0 < 0.0:
            return 0.0

        s_lo = 0.0
        s_hi = 1e-6
        f_hi = _f(s_hi)
        s_hi_cap = max(10.0, abs(float(x_m)) + 2.0 * abs(float(y_m)) + float(self.vehicle.c_root_m) + 1.0)
        n_expand = 0
        while f_hi > 0.0 and s_hi < s_hi_cap and n_expand < 80:
            s_hi *= 2.0
            f_hi = _f(s_hi)
            n_expand += 1
        if f_hi > 0.0:
            return None

        for _ in range(80):
            s_mid = 0.5 * (s_lo + s_hi)
            f_mid = _f(s_mid)
            if f_mid > 0.0:
                s_lo = s_mid
            else:
                s_hi = s_mid
        return float(0.5 * (s_lo + s_hi))

    def _assign_x_phys_overrides(self, *, strip_payloads: list[dict[str, Any]], mach: float, alpha: float) -> None:
        mode = self._x_length_mode()
        x_over_c = np.asarray(self.xc_grid, dtype=float).reshape(-1)
        self._x_phys_override_by_strip = [None for _ in range(self.ny)]
        if mode == "local":
            for j, payload in enumerate(strip_payloads):
                if not bool(payload.get("valid", False)):
                    continue
                chord_eff = float(payload["chord_eff"])
                x_floor = self._x_eval_floor_m(chord_m=chord_eff, y_over_b=float(payload["y_over_b"]))
                x_phys = np.maximum(x_over_c * chord_eff, x_floor)
                payload["x_phys_eval_arr"] = np.asarray(x_phys, dtype=float)
                self._x_phys_override_by_strip[j] = np.asarray(x_phys, dtype=float)
            return

        inflow = self._resolve_edge_inflow(mach=float(mach), alpha_deg=float(alpha))
        alpha_edge_rad = float(inflow.alpha_edge_rad)

        valid_span_nodes: list[float] = []
        valid_xle_nodes: list[float] = []
        for payload in strip_payloads:
            if not bool(payload.get("valid", False)) or bool(payload.get("endpoint_regularized", False)):
                continue
            valid_span_nodes.append(float(payload["y_over_b"]) * float(self.planform_b_half_m))
            valid_xle_nodes.append(float(payload["x_le"]))
        if len(valid_span_nodes) == 0:
            for j, payload in enumerate(strip_payloads):
                if not bool(payload.get("valid", False)):
                    continue
                chord_eff = float(payload["chord_eff"])
                x_floor = self._x_eval_floor_m(chord_m=chord_eff, y_over_b=float(payload["y_over_b"]))
                x_phys = np.maximum(x_over_c * chord_eff, x_floor)
                payload["x_phys_eval_arr"] = np.asarray(x_phys, dtype=float)
                self._x_phys_override_by_strip[j] = np.asarray(x_phys, dtype=float)
            return
        span_nodes_m = np.asarray(valid_span_nodes, dtype=float)
        x_le_nodes_m = np.asarray(valid_xle_nodes, dtype=float)
        order = np.argsort(span_nodes_m)
        span_nodes_m = span_nodes_m[order]
        x_le_nodes_m = x_le_nodes_m[order]

        streamline_fallback_count = 0
        for j, payload in enumerate(strip_payloads):
            if not bool(payload.get("valid", False)):
                continue
            mask_x = np.asarray(payload["mask_x"], dtype=bool).reshape(-1)
            chord = float(payload["chord"])
            chord_eff = float(payload["chord_eff"])
            x_le = float(payload["x_le"])
            y_m = float(payload["y_over_b"]) * float(self.planform_b_half_m)
            x_floor = self._x_eval_floor_m(chord_m=chord_eff, y_over_b=float(payload["y_over_b"]))
            x_local = np.maximum(x_over_c * chord_eff, x_floor)
            if mode == "global":
                x_phys = np.maximum(x_le + x_over_c * chord, x_floor)
            else:
                x_phys = np.array(x_local, copy=True)
                for i in range(self.nx):
                    if not bool(mask_x[i]):
                        continue
                    x_m = float(x_le + x_over_c[i] * chord)
                    s_eff = self._streamline_length_to_le(
                        x_m=x_m,
                        y_m=float(y_m),
                        sx=float(payload["sx_w_arr"][i]),
                        sy=float(payload["sy_w_arr"][i]),
                        alpha_edge_rad=float(alpha_edge_rad),
                        span_nodes_m=span_nodes_m,
                        x_le_nodes_m=x_le_nodes_m,
                    )
                    if s_eff is None or not np.isfinite(float(s_eff)):
                        streamline_fallback_count += 1
                        s_eff = float(x_local[i])
                    x_phys[i] = float(max(float(s_eff), x_floor))
            payload["x_phys_eval_arr"] = np.asarray(x_phys, dtype=float)
            self._x_phys_override_by_strip[j] = np.asarray(x_phys, dtype=float)

        if mode == "streamline" and streamline_fallback_count > 0:
            self._warn(f"faceted3d streamline x-length fallback to local at {int(streamline_fallback_count)} points")

    def _build_windward_edge_cache(
        self,
        *,
        mach: float,
        alpha_deg: float,
        p_inf: float,
        rho_inf: float,
        T_inf: float,
        chord_m: float,
        sx_arr: np.ndarray,
        sy_arr: np.ndarray,
        transition_x_over_c: float | None,
        cp0_override: float | None = None,
        x_phys_override: np.ndarray | None = None,
    ) -> WindwardEdgeCacheFaceted3D:
        return build_windward_edge_cache_faceted3d(
            gas=self.gas,
            lf_cfg=self.lf_cfg,
            mach=float(mach),
            alpha_deg=float(alpha_deg),
            sweep_le_deg=float(self.vehicle.sweep_le_deg),
            p_inf=float(p_inf),
            rho_inf=float(rho_inf),
            T_inf=float(T_inf),
            chord_m=float(chord_m),
            xc_grid=np.asarray(self.xc_grid, dtype=float),
            sx_arr=np.asarray(sx_arr, dtype=float),
            sy_arr=np.asarray(sy_arr, dtype=float),
            transition_x_over_c=transition_x_over_c,
            cp0_override=cp0_override,
            use_effective_alpha=bool(self.f3_cfg.edge_use_effective_alpha),
            use_effective_mach=bool(self.f3_cfg.edge_use_effective_mach),
            x_phys_override=(None if x_phys_override is None else np.asarray(x_phys_override, dtype=float)),
            cp_model=str(self.f3_cfg.cp_model),
            cp_newtonian_A=float(self.f3_cfg.cp_newtonian_A),
            cp_newtonian_n=float(self.f3_cfg.cp_newtonian_n),
        )

    def _warn_windward_edge_cache(
        self,
        *,
        cache: WindwardEdgeCacheFaceted3D,
        mach: float,
        alpha_deg: float,
        y_over_b: float,
    ) -> None:
        if bool(cache.cp0_regularized):
            key = (
                "cp0_regularized",
                round(float(mach), 6),
                round(float(alpha_deg), 6),
                round(float(y_over_b), 6),
                round(float(cache.cp0_raw), 6),
                round(float(cache.cp0_used), 6),
            )
            if key not in self._edge_cache_warning_keys:
                self._edge_cache_warning_keys.add(key)
                self._warn(
                    "cp0 regularized to keep windward edge supersonic"
                    f" | M={mach:.2f}, alpha={alpha_deg:.2f}, y/b={y_over_b:.3f}"
                    f" | cp0 raw={cache.cp0_raw:.6g}, used={cache.cp0_used:.6g}"
                    f" | min Ma_e raw={cache.min_ma_e_raw:.6g}, used={cache.min_ma_e_used:.6g}"
                    f" | collapsed raw={cache.collapsed_edge_count_raw}, used={cache.collapsed_edge_count_used}"
                )
        elif int(cache.collapsed_edge_count_used) > 0:
            key = (
                "edge_collapse",
                round(float(mach), 6),
                round(float(alpha_deg), 6),
                round(float(y_over_b), 6),
                int(cache.collapsed_edge_count_used),
            )
            if key not in self._edge_cache_warning_keys:
                self._edge_cache_warning_keys.add(key)
                self._warn(
                    "windward edge state collapsed to Ma_e<=0"
                    f" | M={mach:.2f}, alpha={alpha_deg:.2f}, y/b={y_over_b:.3f}"
                    f" | cp0={cache.cp0_used:.6g}, min Ma_e={cache.min_ma_e_used:.6g}"
                    f" | collapsed points={cache.collapsed_edge_count_used}"
                )


    def _build_spanwise_cp0_overrides(
        self,
        *,
        mach: float,
        alpha: float,
        strip_payloads: list[dict[str, Any]],
    ) -> list[float | None]:
        seeds = np.full((self.ny,), np.nan, dtype=float)
        fallback = np.full((self.ny,), np.nan, dtype=float)
        yb_vals = np.asarray(self.yb_grid, dtype=float).reshape(-1)

        p_inf, rho_inf, T_inf, _v_inf = self._freestream(float(mach))

        for payload in strip_payloads:
            j = int(payload["j"])
            if not bool(payload.get("valid", False)):
                continue
            cache = self._build_windward_edge_cache(
                mach=float(mach),
                alpha_deg=float(alpha),
                p_inf=float(p_inf),
                rho_inf=float(rho_inf),
                T_inf=float(T_inf),
                chord_m=float(payload["chord_eff"]),
                sx_arr=np.asarray(payload["sx_w_arr"], dtype=float),
                sy_arr=np.asarray(payload["sy_w_arr"], dtype=float),
                transition_x_over_c=self.case.transition_x_over_c,
            )
            fallback[j] = float(cache.cp0_used)
            if int(cache.collapsed_edge_count_raw) == 0 and np.isfinite(float(cache.cp0_raw)):
                seeds[j] = float(cache.cp0_raw)

        overrides = np.array(fallback, copy=True)
        valid = np.isfinite(seeds)
        if np.any(valid):
            overrides = np.interp(yb_vals, yb_vals[valid], seeds[valid], left=float(seeds[valid][0]), right=float(seeds[valid][-1]))
            overrides = np.where(valid, seeds, overrides)

        if self.slope_sampler is not None:
            valid_payloads = np.array([bool(p.get("valid", False)) for p in strip_payloads], dtype=bool)
            finite_override = np.isfinite(overrides)
            smooth_mask = valid_payloads & finite_override
            if np.any(smooth_mask):
                overrides = _smooth_spanwise_scalar_series(values=overrides, valid_mask=smooth_mask, passes=2)

        result: list[float | None] = []
        for j in range(self.ny):
            payload = strip_payloads[j]
            if not bool(payload.get("valid", False)):
                result.append(None)
                continue
            val = float(overrides[j])
            if not np.isfinite(val):
                fb = float(fallback[j])
                result.append(fb if np.isfinite(fb) else None)
            else:
                result.append(val)
        return result

    def _smooth_stl_leading_edge_slopes(self, *, strip_payloads: list[dict[str, Any]]) -> None:
        """Light spanwise anti-aliasing for STL-derived windward slopes near the leading edge.

        This targets the first few x/c columns only, where single-triangle STL hits can
        create alternating strip-to-strip cp0 jumps that look like comb teeth in q_w.
        """

        x_over_c = np.asarray(self.xc_grid, dtype=float).reshape(-1)
        smooth_idx = np.where(x_over_c <= 0.05 + 1e-12)[0]
        if smooth_idx.size == 0 or self.ny < 2:
            return

        sx_cols = np.full((self.ny, smooth_idx.size), np.nan, dtype=float)
        sy_cols = np.full((self.ny, smooth_idx.size), np.nan, dtype=float)
        valid = np.zeros((self.ny, smooth_idx.size), dtype=bool)

        for j, payload in enumerate(strip_payloads):
            if not bool(payload.get("valid", False)) or bool(payload.get("endpoint_regularized", False)):
                continue
            mask_x = np.asarray(payload["mask_x"], dtype=bool).reshape(-1)
            sx_arr = np.asarray(payload.get("sx_w_arr"), dtype=float).reshape(-1)
            sy_arr = np.asarray(payload.get("sy_w_arr"), dtype=float).reshape(-1)
            if sx_arr.size != self.nx or sy_arr.size != self.nx or mask_x.size != self.nx:
                continue
            for k, i in enumerate(smooth_idx.tolist()):
                if bool(mask_x[i]) and np.isfinite(float(sx_arr[i])) and np.isfinite(float(sy_arr[i])):
                    sx_cols[j, k] = float(sx_arr[i])
                    sy_cols[j, k] = float(sy_arr[i])
                    valid[j, k] = True

        if not np.any(valid):
            return

        sx_s, sy_s = _smooth_spanwise_slope_columns(sx_cols=sx_cols, sy_cols=sy_cols, valid_mask=valid, passes=2)

        for j, payload in enumerate(strip_payloads):
            if not bool(payload.get("valid", False)):
                continue
            sx_arr = np.asarray(payload.get("sx_w_arr"), dtype=float).reshape(-1).copy()
            sy_arr = np.asarray(payload.get("sy_w_arr"), dtype=float).reshape(-1).copy()
            for k, i in enumerate(smooth_idx.tolist()):
                if bool(valid[j, k]):
                    sx_arr[i] = float(sx_s[j, k])
                    sy_arr[i] = float(sy_s[j, k])
            payload["sx_w_arr"] = sx_arr
            payload["sy_w_arr"] = sy_arr

    def _prepare_strip_payloads(self, *, mach: float, alpha: float) -> list[dict[str, Any]]:
        use_stl = self.slope_sampler is not None
        strip_payloads: list[dict[str, Any]] = []

        for j in range(self.ny):
            yb = float(self.yb_grid[j])
            x_le, chord, mask_x = self._strip_xle_chord_mask(y_over_b=yb)
            mask_x = np.asarray(mask_x, dtype=bool).reshape(-1)
            if mask_x.size != self.nx:
                raise ValueError("triangle mask must have length nx")

            payload: dict[str, Any] = {
                "j": int(j),
                "y_over_b": float(yb),
                "x_le": float(x_le),
                "chord": float(chord),
                "mask_x": mask_x,
                "valid": bool(np.any(mask_x) and (float(chord) > 0.0) and np.isfinite(float(x_le))),
                "endpoint_regularized": bool(self._tip_endpoint_regularized and j == self.ny - 1),
                "cp0_override": None,
            }

            if not bool(payload["valid"]):
                strip_payloads.append(payload)
                continue

            chord_eff = float(max(float(chord), float(self.f3_cfg.chord_min_m)))
            payload["chord_eff"] = float(chord_eff)

            if use_stl:
                assert self.slope_sampler is not None
                span_m = float(yb) * float(self.planform_b_half_m)
                x_pts = float(x_le) + np.asarray(self.xc_grid, dtype=float) * float(chord)
                sx_up_arr = np.full((self.nx,), np.nan, dtype=float)
                sy_up_arr = np.full((self.nx,), np.nan, dtype=float)
                sx_lo_arr = np.full((self.nx,), np.nan, dtype=float)
                sy_lo_arr = np.full((self.nx,), np.nan, dtype=float)
                raw_normal_up = np.full((self.nx, 3), np.nan, dtype=float)
                raw_normal_lo = np.full((self.nx, 3), np.nan, dtype=float)
                for i in range(self.nx):
                    if not bool(mask_x[i]):
                        continue
                    up_s, lo_s = self.slope_sampler.sample_upper_lower(x=float(x_pts[i]), span=float(span_m))
                    if up_s is not None:
                        sx_up_arr[i], sy_up_arr[i] = float(up_s[0]), float(up_s[1])
                        raw_normal_up[i] = np.asarray(up_s[3:6], dtype=float)
                    if lo_s is not None:
                        sx_lo_arr[i], sy_lo_arr[i] = float(lo_s[0]), float(lo_s[1])
                        raw_normal_lo[i] = np.asarray(lo_s[3:6], dtype=float)
                sx_up_arr, sy_up_arr = _reject_stl_surface_outliers(
                    sx_arr=sx_up_arr,
                    sy_arr=sy_up_arr,
                    ref_sx=float(self.sx_up),
                    ref_sy=float(self.sy_up),
                )
                sx_lo_arr, sy_lo_arr = _reject_stl_surface_outliers(
                    sx_arr=sx_lo_arr,
                    sy_arr=sy_lo_arr,
                    ref_sx=float(self.sx_lo),
                    ref_sy=float(self.sy_lo),
                )
                up_stl_accepted = mask_x & np.isfinite(sx_up_arr) & np.isfinite(sy_up_arr)
                lo_stl_accepted = mask_x & np.isfinite(sx_lo_arr) & np.isfinite(sy_lo_arr)
                sx_up_arr = np.where(np.isfinite(sx_up_arr), sx_up_arr, float(self.sx_up))
                sy_up_arr = np.where(np.isfinite(sy_up_arr), sy_up_arr, float(self.sy_up))
                sx_lo_arr = np.where(np.isfinite(sx_lo_arr), sx_lo_arr, float(self.sx_lo))
                sy_lo_arr = np.where(np.isfinite(sy_lo_arr), sy_lo_arr, float(self.sy_lo))
            else:
                sx_up_arr = np.full((self.nx,), float(self.sx_up), dtype=float)
                sy_up_arr = np.full((self.nx,), float(self.sy_up), dtype=float)
                sx_lo_arr = np.full((self.nx,), float(self.sx_lo), dtype=float)
                sy_lo_arr = np.full((self.nx,), float(self.sy_lo), dtype=float)
                raw_normal_up = np.full((self.nx, 3), np.nan, dtype=float)
                raw_normal_lo = np.full((self.nx, 3), np.nan, dtype=float)
                up_stl_accepted = np.zeros((self.nx,), dtype=bool)
                lo_stl_accepted = np.zeros((self.nx,), dtype=bool)

            if float(alpha) >= 0.0:
                sx_w_arr, sy_w_arr = sx_lo_arr, sy_lo_arr
                sx_l_arr, sy_l_arr = sx_up_arr, sy_up_arr
            else:
                sx_w_arr, sy_w_arr = sx_up_arr, sy_up_arr
                sx_l_arr, sy_l_arr = sx_lo_arr, sy_lo_arr

            payload.update(
                {
                    "sx_w_arr": np.asarray(sx_w_arr, dtype=float),
                    "sy_w_arr": np.asarray(sy_w_arr, dtype=float),
                    "sx_l_arr": np.asarray(sx_l_arr, dtype=float),
                    "sy_l_arr": np.asarray(sy_l_arr, dtype=float),
                    "sx_upper_arr": np.asarray(sx_up_arr, dtype=float),
                    "sy_upper_arr": np.asarray(sy_up_arr, dtype=float),
                    "sx_lower_arr": np.asarray(sx_lo_arr, dtype=float),
                    "sy_lower_arr": np.asarray(sy_lo_arr, dtype=float),
                    "diagnostic_raw_normal_upper": np.asarray(raw_normal_up, dtype=float),
                    "diagnostic_raw_normal_lower": np.asarray(raw_normal_lo, dtype=float),
                    "diagnostic_qchain_stl_accepted_upper": np.asarray(up_stl_accepted, dtype=bool),
                    "diagnostic_qchain_stl_accepted_lower": np.asarray(lo_stl_accepted, dtype=bool),
                }
            )
            strip_payloads.append(payload)

        if use_stl:
            self._smooth_stl_leading_edge_slopes(strip_payloads=strip_payloads)

        for payload in strip_payloads:
            if not bool(payload.get("valid", False)):
                continue
            mask_x = np.asarray(payload["mask_x"], dtype=bool)
            analytic_sx_upper = np.full((self.nx,), float(self.sx_up), dtype=float)
            analytic_sy_upper = np.full((self.nx,), float(self.sy_up), dtype=float)
            analytic_sx_lower = np.full((self.nx,), float(self.sx_lo), dtype=float)
            analytic_sy_lower = np.full((self.nx,), float(self.sy_lo), dtype=float)
            normal_upper, incidence_upper, class_upper, source_upper = diagnose_sheet_from_geometry(
                raw_facet_normal=np.asarray(payload["diagnostic_raw_normal_upper"], dtype=float),
                qchain_stl_accepted=np.asarray(payload["diagnostic_qchain_stl_accepted_upper"], dtype=bool),
                analytic_sx=analytic_sx_upper,
                analytic_sy=analytic_sy_upper,
                sheet="upper",
                alpha_deg=float(alpha),
                epsilon=INCIDENCE_EPSILON,
            )
            normal_lower, incidence_lower, class_lower, source_lower = diagnose_sheet_from_geometry(
                raw_facet_normal=np.asarray(payload["diagnostic_raw_normal_lower"], dtype=float),
                qchain_stl_accepted=np.asarray(payload["diagnostic_qchain_stl_accepted_lower"], dtype=bool),
                analytic_sx=analytic_sx_lower,
                analytic_sy=analytic_sy_lower,
                sheet="lower",
                alpha_deg=float(alpha),
                epsilon=INCIDENCE_EPSILON,
            )
            payload["normal_upper"] = np.where(mask_x[:, None], normal_upper, np.nan)
            payload["normal_lower"] = np.where(mask_x[:, None], normal_lower, np.nan)
            payload["incidence_s_upper"] = np.where(mask_x, incidence_upper, np.nan)
            payload["incidence_s_lower"] = np.where(mask_x, incidence_lower, np.nan)
            payload["surface_class_upper"] = np.where(mask_x, class_upper, -2).astype(np.int8)
            payload["surface_class_lower"] = np.where(mask_x, class_lower, -2).astype(np.int8)
            payload["normal_source_upper"] = np.where(mask_x, source_upper, NORMAL_SOURCE_INVALID).astype(np.int8)
            payload["normal_source_lower"] = np.where(mask_x, source_lower, NORMAL_SOURCE_INVALID).astype(np.int8)

        # Prefer fixing the local leading-edge surface selection itself over
        # borrowing cp0 from neighboring strips. Keep the regularization safety
        # net downstream, but stop applying spanwise cp0 overrides by default.
        self._cp0_override_by_strip = [None for _ in range(self.ny)]
        for payload in strip_payloads:
            payload["cp0_override"] = None

        self._assign_x_phys_overrides(strip_payloads=strip_payloads, mach=float(mach), alpha=float(alpha))
        return strip_payloads

    @staticmethod
    def _resolve_project_root() -> Path:
        here = Path(__file__).resolve()
        if len(here.parents) >= 3:
            return here.parents[2]
        return here.parent

    def _freestream(self, mach: float) -> tuple[float, float, float, float]:
        # Explicit override: skip atmosphere model, use user-provided T_inf/p_inf
        if self.case.T_inf_override_K is not None and self.case.p_inf_override_Pa is not None:
            T_inf = float(self.case.T_inf_override_K)
            p_inf = float(self.case.p_inf_override_Pa)
            rho_inf = float(p_inf / (float(self.case.R_J_per_kgK) * T_inf))
        else:
            model = str(self.case.atmosphere_model).strip().lower()
            if model == "ussa1976":
                from .atmosphere.ussa1976 import ussa1976_0_32km

                p_inf, rho_inf, T_inf = ussa1976_0_32km(h_m=self.case.fixed_h_m, R_gas_J_per_kgK=self.case.R_J_per_kgK)
            else:
                from .atmosphere.isa1976 import isa1976

                atm = isa1976(self.case.fixed_h_m, R=self.case.R_J_per_kgK)
                T_inf, p_inf, rho_inf = atm.T, atm.p, atm.rho
        a_inf = float(self.gas.tpg.a_T(float(T_inf)))
        v_inf = float(mach) * a_inf
        return float(p_inf), float(rho_inf), float(T_inf), float(v_inf)

    def _leading_edge_rn_span_m(self, *, y_over_b: float) -> float:
        r0 = float(self.f3_cfg.leading_edge_rn_root_m)
        if not (r0 > 0.0):
            r0 = float(self.vehicle.rn_m)
        r1 = float(self.f3_cfg.leading_edge_rn_tip_m)
        if not (r1 > 0.0):
            r1 = float(r0)
        t = float(np.clip(abs(float(y_over_b)), 0.0, 1.0))
        return float(r0 + (r1 - r0) * t)

    def _rn_local(self, *, chord_m: float, y_over_b: float) -> float:
        rn_span = float(self._leading_edge_rn_span_m(y_over_b=float(y_over_b)))
        if not bool(self.f3_cfg.rn_scale_with_chord):
            return float(rn_span)
        return float(rn_span) * float(chord_m) / float(self.vehicle.c_root_m)

    def _leading_edge_q(
        self,
        *,
        rho_inf: float,
        v_inf: float,
        h0: float,
        h_w: float,
        alpha_rad: float,
        chi_rad: float,
        rn_local_m: float,
    ) -> float:
        h_300K = float(self.gas.h_from_T(300.0))
        return leading_edge_heat_flux_baseline(
            rn_le_m=float(rn_local_m),
            c_root_m=1.0,
            chord_m=1.0,
            rn_unit=str(self.lf_cfg.stagnation.rn_unit),
            sweep_exponent_n=float(self.lf_cfg.stagnation.sweep_exponent_n),
            rho_inf=float(rho_inf),
            v_inf=float(v_inf),
            h0=float(h0),
            h_w=float(h_w),
            h_300K=float(h_300K),
            chi_w_rad=float(chi_rad),
            alpha_rad=float(alpha_rad),
        )

    def _leeward_R_ref(self, *, chord_m: float) -> float:
        rn = float(self.vehicle.rn_m)
        if rn > 0.0:
            return rn
        return max(float(chord_m), 1e-6)

    def _regularize_degenerate_tip_endpoint(self) -> None:
        """Move only a degenerate terminal span station to the outermost valid strip."""

        if self.ny < 2 or self.yb_grid.size != self.ny:
            return
        y_tip = float(self.yb_grid[-1])
        outline_tip = 1.0
        endpoint_tol = 1e-12
        if not np.isfinite(y_tip) or abs(y_tip - outline_tip) > endpoint_tol:
            return

        _x_tip, chord_tip, _mask_tip = self._strip_xle_chord_mask(y_over_b=y_tip)
        chord_min = float(self.f3_cfg.chord_min_m)
        if np.isfinite(chord_tip) and float(chord_tip) >= chord_min:
            return

        y_lo = float(self.yb_grid[-2])
        _x_lo, chord_lo, mask_lo = self._strip_xle_chord_mask(y_over_b=y_lo)
        if not (np.isfinite(chord_lo) and float(chord_lo) >= chord_min and np.any(mask_lo)):
            raise ValueError(
                "Cannot regularize degenerate tip endpoint: no valid bracket below the terminal station "
                f"(y/b={y_lo:.17g}, chord={float(chord_lo):.17g} m, chord_min={chord_min:.17g} m)"
            )

        span_tol_m = 1e-10
        max_iterations = 80
        for _ in range(max_iterations):
            y_mid = 0.5 * (y_lo + y_tip)
            _x_mid, chord_mid, _mask_mid = self._strip_xle_chord_mask(y_over_b=y_mid)
            if np.isfinite(chord_mid) and float(chord_mid) >= chord_min:
                y_lo = y_mid
            else:
                y_tip = y_mid
            if (y_tip - y_lo) * float(self.planform_b_half_m) <= span_tol_m:
                break
        else:
            raise ValueError("Degenerate tip endpoint solve did not converge")

        _x_final, chord_final, mask_final = self._strip_xle_chord_mask(y_over_b=y_lo)
        if not (np.isfinite(chord_final) and float(chord_final) >= chord_min and np.all(mask_final)):
            raise ValueError(
                "Degenerate tip endpoint solve produced an invalid station "
                f"(y/b={y_lo:.17g}, chord={float(chord_final):.17g} m, chord_min={chord_min:.17g} m)"
            )

        self.yb_grid = np.asarray(self.yb_grid, dtype=float).copy()
        self.yb_grid[-1] = float(y_lo)
        self._tip_endpoint_regularized = True

    def _strip_xle_chord_mask(self, *, y_over_b: float) -> tuple[float, float, np.ndarray]:
        if self.outline_x_m is not None and self.outline_span_m is not None:
            return outline_strip_xle_chord_mask(
                x_over_c=np.asarray(self.xc_grid, dtype=float),
                y_over_b=float(y_over_b),
                b_half_m=float(self.planform_b_half_m),
                outline_x_m=np.asarray(self.outline_x_m, dtype=float),
                outline_span_m=np.asarray(self.outline_span_m, dtype=float),
                chord_min_m=float(self.f3_cfg.chord_min_m),
            )
        return triangle_strip_xle_chord_mask(
            x_over_c=np.asarray(self.xc_grid, dtype=float),
            y_over_b=float(y_over_b),
            c_root_m=float(self.vehicle.c_root_m),
            b_half_m=float(self.vehicle.b_half_m),
            half_angle_deg=float(self.f3_cfg.planform_half_angle_deg),
            chord_min_m=float(self.f3_cfg.chord_min_m),
        )

    def calc_strip_heat_flux_fixed_wall(
        self,
        *,
        mach: float,
        alpha_deg: float,
        chord_m: float,
        y_over_b: float,
        side: str,
        T_wall_K: float,
        sx_arr: np.ndarray,
        sy_arr: np.ndarray,
        cp0_override: float | None = None,
        x_phys_override: np.ndarray | None = None,
    ) -> np.ndarray:
        """Compute q(x) for one strip with fixed wall temperature."""

        if side not in {"windward", "leeward"}:
            raise ValueError(f"Invalid side={side!r}")

        p_inf, rho_inf, T_inf, v_inf = self._freestream(mach)
        h_inf = float(self.gas.h_from_T(T_inf))
        h0 = h_inf + 0.5 * (v_inf**2)
        h_w = float(self.gas.h_from_T(float(T_wall_K)))

        # Leeward is a mean correlation and does not depend on (sx, sy) here.
        if side == "leeward":
            h_s = float(h0)
            ratio_T = normal_shock_temperature_ratio(gamma=float(self.case.gamma), mach=float(mach))
            T_ns = float(T_inf) * float(ratio_T)
            mu_ns = float(self.gas.mu(T_ns))
            Re_ns = leeward_re_ns(rho_inf=rho_inf, v_inf=v_inf, R_ref=self._leeward_R_ref(chord_m=chord_m), mu_ns=mu_ns)
            h_wwd_dist = np.full((self.nx,), h_w, dtype=float)
            St_dist = leeward_stanton_distribution(Re_ns=float(Re_ns), h_wwd_dist=h_wwd_dist, h_s=float(h_s))
            q_dist = leeward_heat_flux_distribution(rho_inf=rho_inf, v_inf=v_inf, St_dist=St_dist, h_s=float(h_s), h_w=h_w)
            # Store for export to fields.npz
            self._last_leeward_Re_ns = float(Re_ns)
            self._last_leeward_St_dist = np.asarray(St_dist, dtype=float)
            if not np.all(np.isfinite(q_dist)):
                bad = np.where(~np.isfinite(q_dist))[0]
                self._warn(f"NaN/Inf in leeward heat flux | M={mach:.2f}, indices={bad.tolist()}")
            return q_dist

        # Windward (uses 3D edge cache)
        # Precompute phi clamp warning preview to match baseline behavior.
        phi_clamp_enable = bool(self.lf_cfg.phi_clamp.enable)
        phi_warn = bool(self.lf_cfg.phi_clamp.warn)
        phi_min = float(self.lf_cfg.phi_clamp.phi_min_rad)
        chi_rad = float(np.deg2rad(self.vehicle.sweep_le_deg))
        alpha_rad = float(np.deg2rad(alpha_deg))
        inflow = self._resolve_edge_inflow(mach=float(mach), alpha_deg=float(alpha_deg))
        alpha_edge_rad = float(inflow.alpha_edge_rad)
        # phi = asin( -u路n_hat ) where n_hat uses (sx, sy)
        denom = np.sqrt(1.0 + np.asarray(sx_arr, dtype=float) ** 2 + np.asarray(sy_arr, dtype=float) ** 2)
        denom = np.where(denom <= 0.0, 1.0, denom)
        s = (np.sin(alpha_edge_rad) - np.asarray(sx_arr, dtype=float) * np.cos(alpha_edge_rad)) / denom
        s = np.clip(s, -1.0, 1.0)
        phi_arr = np.arcsin(s)
        clamped_idx = np.where(phi_clamp_enable & (phi_arr <= phi_min))[0]
        if phi_warn and clamped_idx.size > 0:
            preview = ", ".join([f"{float(self.xc_grid[i]):.4f}" for i in clamped_idx[:6].tolist()])
            self._warn(
                f"phi clamped at {int(clamped_idx.size)} points | M={mach:.2f}, alpha={alpha_deg:.2f}, side=windward | first x/c: [{preview}]"
            )

        cache = self._build_windward_edge_cache(
            mach=float(mach),
            alpha_deg=float(alpha_deg),
            p_inf=float(p_inf),
            rho_inf=float(rho_inf),
            T_inf=float(T_inf),
            chord_m=float(chord_m),
            sx_arr=np.asarray(sx_arr, dtype=float),
            sy_arr=np.asarray(sy_arr, dtype=float),
            transition_x_over_c=self.case.transition_x_over_c,
            cp0_override=cp0_override,
            x_phys_override=x_phys_override,
        )
        self._warn_windward_edge_cache(cache=cache, mach=float(mach), alpha_deg=float(alpha_deg), y_over_b=float(y_over_b))

        Tw = np.full((self.nx,), float(T_wall_K), dtype=float)
        q_dist = windward_q_distribution_from_Tw(gas=self.gas, cache=cache, Tw=Tw)

        # Leading edge (index 0)
        if float(self.vehicle.rn_m) > 0.0:
            rn_local_m = self._rn_local(chord_m=chord_m, y_over_b=float(y_over_b))
            q_dist[0] = self._leading_edge_q(
                rho_inf=rho_inf,
                v_inf=v_inf,
                h0=h0,
                h_w=h_w,
                alpha_rad=alpha_rad,
                chi_rad=chi_rad,
                rn_local_m=rn_local_m,
            )
        else:
            q_dist[0] = windward_q_at_index(gas=self.gas, cache=cache, i=0, Tw_i=float(T_wall_K))

        if not np.all(np.isfinite(q_dist)):
            bad = np.where(~np.isfinite(q_dist))[0]
            self._warn(
                f"NaN/Inf in heat flux | M={mach:.2f}, alpha={alpha_deg:.2f}, side=windward | indices={bad.tolist()}"
            )
        return q_dist

    def calc_strip_radiative_equilibrium(
        self,
        *,
        mach: float,
        alpha_deg: float,
        chord_m: float,
        y_over_b: float,
        sx_arr: np.ndarray,
        sy_arr: np.ndarray,
        cp0_override: float | None = None,
        x_phys_override: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute (Tw(x), q(x)) using steady radiative equilibrium (windward only)."""

        p_inf, rho_inf, T_inf, v_inf = self._freestream(mach)
        h_inf = float(self.gas.h_from_T(T_inf))
        h0 = h_inf + 0.5 * (float(v_inf) ** 2)
        chi_rad = float(np.deg2rad(self.vehicle.sweep_le_deg))
        alpha_rad = float(np.deg2rad(alpha_deg))

        cache = self._build_windward_edge_cache(
            mach=float(mach),
            alpha_deg=float(alpha_deg),
            p_inf=float(p_inf),
            rho_inf=float(rho_inf),
            T_inf=float(T_inf),
            chord_m=float(chord_m),
            sx_arr=np.asarray(sx_arr, dtype=float),
            sy_arr=np.asarray(sy_arr, dtype=float),
            transition_x_over_c=self.case.transition_x_over_c,
            cp0_override=cp0_override,
            x_phys_override=x_phys_override,
        )
        self._warn_windward_edge_cache(cache=cache, mach=float(mach), alpha_deg=float(alpha_deg), y_over_b=float(y_over_b))

        rn_local_m = self._rn_local(chord_m=chord_m, y_over_b=float(y_over_b))

        def q_leading_edge_of_Tw(Tw0: float) -> float:
            if float(self.vehicle.rn_m) > 0.0:
                h_w0 = float(self.gas.h_from_T(float(Tw0)))
                return self._leading_edge_q(
                    rho_inf=float(rho_inf),
                    v_inf=float(v_inf),
                    h0=float(h0),
                    h_w=float(h_w0),
                    alpha_rad=float(alpha_rad),
                    chi_rad=float(chi_rad),
                    rn_local_m=float(rn_local_m),
                )
            return windward_q_at_index(gas=self.gas, cache=cache, i=0, Tw_i=float(Tw0))

        return solve_windward_radiative_equilibrium(
            gas=self.gas,
            cache=cache,  # type: ignore[arg-type]
            emissivity=float(self.vehicle.emissivity),
            sigma_W_m2_K4=float(self.case.sigma_W_m2_K4),
            q_leading_edge_of_Tw=q_leading_edge_of_Tw,
        )

    def compute_snapshot(self, *, mach: float, alpha: float) -> np.ndarray:
        self.last_fields = {}
        self._edge_cache_warning_keys = set()
        tw_type = str(self.case.tw_model_type or "").strip().lower()

        q_w_list = []
        q_l_list = []
        Tw_w_list = []
        Tw_l_list = []
        w_tr_list = []
        re_edge_list = []
        re_tri_list = []
        re_x_star_list = []
        re_x_star_turb_list = []
        distance_from_transition_list = []
        re_x_over_re_tri_list = []
        T_e_w_list = []
        p_e_w_list = []
        rho_e_w_list = []
        ma_e_w_list = []
        v_e_w_list = []
        mu_e_w_list = []
        phi_w_list = []
        cp_w_list = []
        cp0_w_list = []
        h_e_w_list = []
        T_r_lam_w_list = []
        h_r_lam_w_list = []
        h_star_lam_w_list = []
        T_r_turb_w_list = []
        h_r_turb_w_list = []
        h_star_turb_w_list = []
        q_lam_w_list = []
        q_turb_w_list = []
        St_l_list = []
        Re_ns_l_list = []
        x_w_list = []
        span_w_list = []
        xc_w_list = []
        yb_w_list = []
        Taw_tpg_w_list = []
        tpg_ve2_neg_list: list[int] = []

        strip_payloads = self._prepare_strip_payloads(mach=float(mach), alpha=float(alpha))

        for j, payload in enumerate(strip_payloads):
            yb = float(payload["y_over_b"])
            x_le = float(payload["x_le"])
            chord = float(payload["chord"])
            mask_x = np.asarray(payload["mask_x"], dtype=bool).reshape(-1)
            cp0_override = payload.get("cp0_override", None)

            # Build coordinate arrays for this strip
            xc_strip = np.asarray(self.xc_grid, dtype=float).reshape(-1)
            span_strip = np.full((self.nx,), float(yb) * float(self.planform_b_half_m), dtype=float)
            x_strip = float(x_le) + xc_strip * float(chord)
            yb_strip = np.full((self.nx,), yb, dtype=float)

            # Pre-initialize all strip-local arrays to NaN
            nan_nx = np.full((self.nx,), float("nan"), dtype=float)
            q_w = nan_nx.copy()
            q_l = nan_nx.copy()
            Tw_w = nan_nx.copy()
            Tw_l = nan_nx.copy()
            w_tr = nan_nx.copy()
            re_edge = nan_nx.copy()
            re_tri = nan_nx.copy()
            T_e_w = nan_nx.copy()
            p_e_w = nan_nx.copy()
            rho_e_w = nan_nx.copy()
            ma_e_w = nan_nx.copy()
            v_e_w = nan_nx.copy()
            mu_e_w = nan_nx.copy()
            phi_w = nan_nx.copy()
            cp_w = nan_nx.copy()
            cp0_w = nan_nx.copy()
            h_e_w = nan_nx.copy()
            T_r_lam_w = nan_nx.copy()
            h_r_lam_w = nan_nx.copy()
            h_star_lam_w = nan_nx.copy()
            T_r_turb_w = nan_nx.copy()
            h_r_turb_w = nan_nx.copy()
            h_star_turb_w = nan_nx.copy()
            q_lam_w = nan_nx.copy()
            q_turb_w = nan_nx.copy()
            St_l = nan_nx.copy()
            Re_ns_l = nan_nx.copy()
            Taw_tpg_w_invalid = nan_nx.copy()

            # Default invalid strip: fill NaNs and continue
            if not bool(payload.get("valid", False)):
                q_w_list.append(q_w)
                q_l_list.append(q_l)
                Tw_w_list.append(Tw_w)
                Tw_l_list.append(Tw_l)
                w_tr_list.append(w_tr)
                re_edge_list.append(re_edge)
                T_e_w_list.append(T_e_w)
                p_e_w_list.append(p_e_w)
                rho_e_w_list.append(rho_e_w)
                ma_e_w_list.append(ma_e_w)
                v_e_w_list.append(v_e_w)
                mu_e_w_list.append(mu_e_w)
                phi_w_list.append(phi_w)
                cp_w_list.append(cp_w)
                cp0_w_list.append(cp0_w)
                h_e_w_list.append(h_e_w)
                T_r_lam_w_list.append(T_r_lam_w)
                h_r_lam_w_list.append(h_r_lam_w)
                h_star_lam_w_list.append(h_star_lam_w)
                T_r_turb_w_list.append(T_r_turb_w)
                h_r_turb_w_list.append(h_r_turb_w)
                h_star_turb_w_list.append(h_star_turb_w)
                q_lam_w_list.append(q_lam_w)
                q_turb_w_list.append(q_turb_w)
                St_l_list.append(St_l)
                Re_ns_l_list.append(Re_ns_l)
                re_tri_list.append(re_tri)
                x_w_list.append(x_strip)
                span_w_list.append(span_strip)
                xc_w_list.append(xc_strip)
                yb_w_list.append(yb_strip)
                Taw_tpg_w_list.append(Taw_tpg_w_invalid)
                tpg_ve2_neg_list.append(0)
                continue

            chord_eff = float(payload["chord_eff"])
            sx_w_arr = np.asarray(payload["sx_w_arr"], dtype=float)
            sy_w_arr = np.asarray(payload["sy_w_arr"], dtype=float)
            sx_l_arr = np.asarray(payload["sx_l_arr"], dtype=float)
            sy_l_arr = np.asarray(payload["sy_l_arr"], dtype=float)
            x_phys_eval_arr = np.asarray(payload["x_phys_eval_arr"], dtype=float)

            if tw_type == "transient_balance":
                cfg = dict(self.case.tw_transient or {})
                require_transient_material(cfg)

                rho_wall = float(cfg["rho_wall_kg_m3"])
                c_wall = float(cfg["c_wall_J_per_kgK"])
                delta_wall = float(cfg["delta_wall_m"])
                cap = float(rho_wall * c_wall * delta_wall)

                dt = float(cfg.get("dt_s", 0.01))
                t_end = float(cfg.get("t_end_s", 10.0))
                n_steps = int(np.ceil(t_end / dt)) if t_end > 0 else 0
                t_s = np.linspace(0.0, n_steps * dt, n_steps + 1)

                Tw_init = cfg.get("Tw_init_K", self.case.wall_temperature_K if self.case.wall_temperature_K is not None else 300.0)
                if np.isscalar(Tw_init):
                    Tw0 = np.full((self.nx,), float(Tw_init), dtype=float)
                else:
                    Tw0 = np.asarray(Tw_init, dtype=float).reshape(-1)
                    if Tw0.size != self.nx:
                        raise ValueError(f"Tw_init_K must be scalar or length nx={self.nx}")

                Tw_min = float(cfg.get("Tw_min_K", 150.0))
                Tw_max = float(cfg.get("Tw_max_K", 6000.0))
                eps = float(self.vehicle.emissivity)
                sigma = float(self.case.sigma_W_m2_K4)

                # Precompute cache for eval_q_a
                p_inf, rho_inf, T_inf, v_inf = self._freestream(mach)
                cache = self._build_windward_edge_cache(
                    mach=float(mach),
                    alpha_deg=float(alpha),
                    p_inf=float(p_inf),
                    rho_inf=float(rho_inf),
                    T_inf=float(T_inf),
                    chord_m=float(chord_eff),
                    sx_arr=sx_w_arr,
                    sy_arr=sy_w_arr,
                    transition_x_over_c=self.case.transition_x_over_c,
                    cp0_override=cp0_override,
                    x_phys_override=x_phys_eval_arr,
                )
                self._warn_windward_edge_cache(cache=cache, mach=float(mach), alpha_deg=float(alpha), y_over_b=float(yb))
                rn_local_m = self._rn_local(chord_m=chord_eff, y_over_b=float(yb))
                h_inf = float(self.gas.h_from_T(T_inf))
                h0 = h_inf + 0.5 * (float(v_inf) ** 2)
                chi_rad = float(np.deg2rad(self.vehicle.sweep_le_deg))
                alpha_rad = float(np.deg2rad(alpha))

                def eval_q_a(Tw_k: np.ndarray) -> np.ndarray:
                    Tw_k = np.asarray(Tw_k, dtype=float).reshape(-1)
                    qk = windward_q_distribution_from_Tw(gas=self.gas, cache=cache, Tw=Tw_k)
                    # leading edge (index 0)
                    Tw0i = float(Tw_k[0]) if Tw_k.size > 0 else float("nan")
                    if np.isfinite(Tw0i):
                        if float(self.vehicle.rn_m) > 0.0:
                            h_w0 = float(self.gas.h_from_T(Tw0i))
                            qk[0] = self._leading_edge_q(
                                rho_inf=float(rho_inf),
                                v_inf=float(v_inf),
                                h0=float(h0),
                                h_w=float(h_w0),
                                alpha_rad=float(alpha_rad),
                                chi_rad=float(chi_rad),
                                rn_local_m=float(rn_local_m),
                            )
                        else:
                            qk[0] = windward_q_at_index(gas=self.gas, cache=cache, i=0, Tw_i=float(Tw0i))
                    return np.asarray(qk, dtype=float)

                save_time = bool(cfg.get("save_time_history", False))
                if self.ny > 1 and save_time:
                    self._warn("transient_balance with ny>1: save_time_history forced to root strip only to avoid huge outputs.")

                if save_time and j == 0 and self.ny == 1:
                    Tw_time, q_time = march_explicit_balance(
                        Tw0=np.asarray(Tw0, dtype=float),
                        dt_s=float(dt),
                        n_steps=int(n_steps),
                        cap_J_per_m2K=float(cap),
                        emissivity=float(eps),
                        sigma_W_m2_K4=float(sigma),
                        Tw_min_K=float(Tw_min),
                        Tw_max_K=float(Tw_max),
                        eval_q_a=eval_q_a,
                    )
                    self.last_fields.update({"t_s": t_s, "Tw_w_time": Tw_time, "q_w_time": q_time})
                    Tw_w = Tw_time[-1, :].copy()
                    q_w = q_time[-1, :].copy()
                else:
                    Tw_w, q_w = march_explicit_balance_final(
                        Tw0=np.asarray(Tw0, dtype=float),
                        dt_s=float(dt),
                        n_steps=int(n_steps),
                        cap_J_per_m2K=float(cap),
                        emissivity=float(eps),
                        sigma_W_m2_K4=float(sigma),
                        Tw_min_K=float(Tw_min),
                        Tw_max_K=float(Tw_max),
                        eval_q_a=eval_q_a,
                    )

                # Leeward: baseline fixed-wall behavior for transient mode
                T_wall = float(self.case.wall_temperature_K if self.case.wall_temperature_K is not None else 300.0)
                q_l = self.calc_strip_heat_flux_fixed_wall(
                    mach=mach,
                    alpha_deg=alpha,
                    chord_m=chord_eff,
                    y_over_b=float(yb),
                    side="leeward",
                    T_wall_K=T_wall,
                    sx_arr=sx_l_arr,
                    sy_arr=sy_l_arr,
                )
                Tw_l = np.full_like(q_l, T_wall, dtype=float)

            elif tw_type == "radiative_equilibrium":
                Tw_w, q_w = self.calc_strip_radiative_equilibrium(
                    mach=mach,
                    alpha_deg=alpha,
                    chord_m=chord_eff,
                    y_over_b=float(yb),
                    sx_arr=sx_w_arr,
                    sy_arr=sy_w_arr,
                    cp0_override=cp0_override,
                    x_phys_override=x_phys_eval_arr,
                )
                # couple leeward with windward enthalpy (baseline behavior)
                h_wwd = np.full((self.nx,), np.nan, dtype=float)
                for i in range(self.nx):
                    if np.isfinite(Tw_w[i]):
                        h_wwd[i] = float(self.gas.h_from_T(float(Tw_w[i])))
                p_inf, rho_inf, T_inf, v_inf = self._freestream(mach)
                h_inf = float(self.gas.h_from_T(T_inf))
                h0 = h_inf + 0.5 * (float(v_inf) ** 2)
                h_s = float(h0)
                ratio_T = normal_shock_temperature_ratio(gamma=float(self.case.gamma), mach=float(mach))
                T_ns = float(T_inf) * float(ratio_T)
                mu_ns = float(self.gas.mu(T_ns))
                Re_ns = leeward_re_ns(
                    rho_inf=rho_inf, v_inf=v_inf, R_ref=self._leeward_R_ref(chord_m=chord_eff), mu_ns=mu_ns
                )
                St_dist = leeward_stanton_distribution(Re_ns=float(Re_ns), h_wwd_dist=h_wwd, h_s=float(h_s))
                self._last_leeward_Re_ns = float(Re_ns)
                self._last_leeward_St_dist = np.asarray(St_dist, dtype=float)
                Tw_l, q_l = solve_leeward_radiative_equilibrium_coupled(
                    gas=self.gas,
                    rho_inf=rho_inf,
                    v_inf=v_inf,
                    St_dist=St_dist,
                    h_s=float(h_s),
                    emissivity=float(self.vehicle.emissivity),
                    sigma_W_m2_K4=float(self.case.sigma_W_m2_K4),
                )
            else:
                # fixed wall temperature model
                T_wall = float(self.case.wall_temperature_K if self.case.wall_temperature_K is not None else 300.0)
                q_w = self.calc_strip_heat_flux_fixed_wall(
                    mach=mach,
                    alpha_deg=alpha,
                    chord_m=chord_eff,
                    y_over_b=float(yb),
                    side="windward",
                    T_wall_K=T_wall,
                    sx_arr=sx_w_arr,
                    sy_arr=sy_w_arr,
                    cp0_override=cp0_override,
                    x_phys_override=x_phys_eval_arr,
                )
                q_l = self.calc_strip_heat_flux_fixed_wall(
                    mach=mach,
                    alpha_deg=alpha,
                    chord_m=chord_eff,
                    y_over_b=float(yb),
                    side="leeward",
                    T_wall_K=T_wall,
                    sx_arr=sx_l_arr,
                    sy_arr=sy_l_arr,
                )
                Tw_w = np.full_like(q_w, T_wall, dtype=float)
                Tw_l = np.full_like(q_l, T_wall, dtype=float)

            # Fill leeward diagnostics (available after either transient_balance or fixed_wall path)
            if hasattr(self, "_last_leeward_St_dist") and self._last_leeward_St_dist is not None:
                St_l[:] = np.where(mask_x, self._last_leeward_St_dist, np.nan)
            if hasattr(self, "_last_leeward_Re_ns") and np.isfinite(self._last_leeward_Re_ns):
                Re_ns_l[:] = np.where(mask_x, float(self._last_leeward_Re_ns), np.nan)

            if float(self.f3_cfg.nose_cap_radius_m) > 0.0:
                r_cap = float(self.f3_cfg.nose_cap_radius_m)
                y_m = float(yb) * float(self.planform_b_half_m)
                x_m = float(x_le) + np.asarray(self.xc_grid, dtype=float) * float(chord)
                cap_mask = (x_m * x_m + (y_m * y_m)) <= (r_cap * r_cap)
                if np.any(cap_mask):
                    p_inf, rho_inf, T_inf, v_inf = self._freestream(mach)
                    h_inf = float(self.gas.h_from_T(T_inf))
                    h0 = h_inf + 0.5 * (float(v_inf) ** 2)
                    h_300K = float(self.gas.h_from_T(300.0))
                    for i in range(self.nx):
                        if not bool(cap_mask[i]):
                            continue
                        Tw_i = float(Tw_w[i])
                        if not np.isfinite(Tw_i):
                            continue
                        h_w = float(self.gas.h_from_T(Tw_i))
                        q_cap = kemp_riddell_modified_qsph_baseline(
                            R_N_m=float(self._leading_edge_rn_span_m(y_over_b=float(yb))),
                            rn_unit=str(self.lf_cfg.stagnation.rn_unit),
                            rho_inf=float(rho_inf),
                            v_inf=float(v_inf),
                            h0=float(h0),
                            h_w=float(h_w),
                            h_300K=float(h_300K),
                        )
                        if np.isfinite(q_cap):
                            q_w[i] = float(max(q_w[i], q_cap))

            # Apply planform mask
            q_w = np.asarray(q_w, dtype=float)
            q_l = np.asarray(q_l, dtype=float)
            Tw_w = np.asarray(Tw_w, dtype=float)
            Tw_l = np.asarray(Tw_l, dtype=float)
            q_w = np.where(mask_x, q_w, np.nan)
            q_l = np.where(mask_x, q_l, np.nan)
            Tw_w = np.where(mask_x, Tw_w, np.nan)
            Tw_l = np.where(mask_x, Tw_l, np.nan)

            q_w_list.append(q_w)
            q_l_list.append(q_l)
            Tw_w_list.append(Tw_w)
            Tw_l_list.append(Tw_l)

            # Diagnostics: transition weighting and Reynolds ratio along windward surface.
            p_inf, rho_inf, T_inf, _v_inf = self._freestream(mach)
            cache = self._build_windward_edge_cache(
                mach=float(mach),
                alpha_deg=float(alpha),
                p_inf=float(p_inf),
                rho_inf=float(rho_inf),
                T_inf=float(T_inf),
                chord_m=float(chord_eff),
                sx_arr=sx_w_arr,
                sy_arr=sy_w_arr,
                transition_x_over_c=self.case.transition_x_over_c,
                cp0_override=cp0_override,
                x_phys_override=x_phys_eval_arr,
            )
            Taw_tpg_w = np.full((self.nx,), float("nan"), dtype=float)
            if cache.taw_tpg is not None:
                Taw_tpg_w = np.asarray(cache.taw_tpg, dtype=float).reshape(-1)
            tpg_ve2_neg_list.append(int(cache.tpg_ve2_neg_count))
            re_edge = np.full((self.nx,), np.nan, dtype=float)
            re_tri = np.full((self.nx,), np.nan, dtype=float)
            re_x_star = np.full((self.nx,), float("nan"), dtype=float)
            re_x_star_turb = np.full((self.nx,), float("nan"), dtype=float)
            distance_from_transition = np.full((self.nx,), float("nan"), dtype=float)
            re_x_over_re_tri = np.full((self.nx,), float("nan"), dtype=float)
            w_tr = np.full((self.nx,), np.nan, dtype=float)
            T_e_w = np.full((self.nx,), float("nan"), dtype=float)
            p_e_w = np.full((self.nx,), float("nan"), dtype=float)
            rho_e_w = np.full((self.nx,), float("nan"), dtype=float)
            ma_e_w = np.full((self.nx,), float("nan"), dtype=float)
            v_e_w = np.full((self.nx,), float("nan"), dtype=float)
            mu_e_w = np.full((self.nx,), float("nan"), dtype=float)
            phi_w = np.full((self.nx,), float("nan"), dtype=float)
            cp_w = np.full((self.nx,), float("nan"), dtype=float)
            cp0_w = np.full((self.nx,), float(cache.cp0_used), dtype=float)
            for i in range(self.nx):
                if not bool(mask_x[i]):
                    continue
                edge = cache.edges[i]
                re_edge[i] = float(edge.rho_e) * float(edge.v_e) * float(cache.x_phys[i]) / float(edge.mu_e)
                re_tri[i] = float(transition_reynolds(ma_e=float(edge.ma_e)))
                T_e_w[i] = float(edge.T_e)
                p_e_w[i] = float(edge.p_e)
                rho_e_w[i] = float(edge.rho_e)
                ma_e_w[i] = float(edge.ma_e)
                v_e_w[i] = float(edge.v_e)
                mu_e_w[i] = float(edge.mu_e)
                if cache.phi_arr is not None:
                    phi_w[i] = float(cache.phi_arr[i])
                if cache.cp_arr is not None:
                    cp_w[i] = float(cache.cp_arr[i])
                Tw_i = float(Tw_w[i])
                if not np.isfinite(Tw_i):
                    w_tr[i] = float("nan")
                    continue
                h_w = float(self.gas.h_from_T(Tw_i))
                branches = windward_ref_enthalpy_branches(
                    gas=self.gas,
                    edge=edge,
                    x=float(cache.x_phys[i]),
                    h_w=h_w,
                )
                re_x_star[i] = float(branches.Re_x_star_lam)
                re_x_star_turb[i] = float(branches.Re_x_star_turb)
                h_e_w[i] = float(branches.h_e)
                T_r_lam_w[i] = float(branches.T_r_lam)
                h_r_lam_w[i] = float(branches.h_r_lam)
                h_star_lam_w[i] = float(branches.h_star_lam)
                T_r_turb_w[i] = float(branches.T_r_turb)
                h_r_turb_w[i] = float(branches.h_r_turb)
                h_star_turb_w[i] = float(branches.h_star_turb)
                q_lam_w[i] = float(branches.q_lam)
                q_turb_w[i] = float(branches.q_turb)
                if np.isfinite(re_tri[i]) and re_tri[i] > 0:
                    re_x_over_re_tri[i] = float(branches.Re_x_star_lam) / float(re_tri[i])
                if i == 0:
                    w_tr[i] = 0.0
                    continue
                w_tr[i] = float(
                    transition_weight(
                        enable=bool(self.lf_cfg.transition.enable),
                        re_measure=float(branches.Re_x_star_lam),
                        re_tri=float(re_tri[i]),
                        weighting=str(self.lf_cfg.transition.weighting),
                        width_decades=float(self.lf_cfg.transition.width_decades),
                        delta_decades=float(self.lf_cfg.transition.delta_decades),
                        x_over_c=float(cache.x_over_c[i]),
                        transition_x_over_c=self.case.transition_x_over_c,
                    )
                )
            # diagnostic-only: find transition index per strip and compute distance_from_transition
            x_phys_arr = np.asarray(cache.x_phys, dtype=float).reshape(-1)
            x_tr_idx = None
            for ii in range(self.nx):
                if not bool(mask_x[ii]):
                    continue
                if np.isfinite(re_x_star[ii]) and np.isfinite(re_tri[ii]) and float(re_tri[ii]) > 0:
                    if float(re_x_star[ii]) >= float(re_tri[ii]):
                        x_tr_idx = ii
                        break
            if x_tr_idx is not None:
                x_tr_val = float(x_phys_arr[x_tr_idx])
                for ii in range(self.nx):
                    if np.isfinite(x_phys_arr[ii]):
                        distance_from_transition[ii] = float(x_phys_arr[ii]) - x_tr_val

            # Phase 3-A diagnostic-only: Dhawan-Narasimha w_tr override.
            # Only fires when weighting == "dhawan_narasimha" and onset is detected.
            # All intermediates are local to this diagnostic block; no physical q path touched.
            dn_weighting = str(self.lf_cfg.transition.weighting).strip().lower()
            if dn_weighting == "dhawan_narasimha" and x_tr_idx is not None:
                x_tr_phys = float(x_phys_arr[x_tr_idx])
                rho_e_tr = float(rho_e_w[x_tr_idx])
                v_e_tr = float(v_e_w[x_tr_idx])
                mu_e_tr = float(mu_e_w[x_tr_idx])
                Re_x_tr = rho_e_tr * v_e_tr * x_tr_phys / mu_e_tr
                if Re_x_tr > 0 and rho_e_tr > 0 and v_e_tr > 0 and mu_e_tr > 0 and x_tr_phys > 0:
                    Re_theta_tr = 0.664 * math.sqrt(Re_x_tr)
                    Re_L_tr = 124.0 * (Re_theta_tr ** 1.5)
                    L_tr = Re_L_tr * mu_e_tr / (rho_e_tr * v_e_tr)
                    xi_99 = math.sqrt(-math.log(0.01) / 0.412)
                    lambda_m = L_tr / xi_99
                    for ii in range(self.nx):
                        if not bool(mask_x[ii]):
                            continue
                        if ii == 0:
                            continue
                        if not np.isfinite(float(w_tr[ii])):
                            continue
                        w_tr[ii] = float(
                            transition_weight(
                                enable=True,
                                re_measure=1.0,
                                re_tri=1.0,
                                weighting="dhawan_narasimha",
                                x_phys=float(x_phys_arr[ii]),
                                x_tr_phys=float(x_tr_phys),
                                lambda_m=float(lambda_m),
                            )
                        )

            w_tr_list.append(w_tr)
            re_edge_list.append(re_edge)
            re_tri_list.append(re_tri)
            T_e_w_list.append(T_e_w)
            p_e_w_list.append(p_e_w)
            rho_e_w_list.append(rho_e_w)
            ma_e_w_list.append(ma_e_w)
            v_e_w_list.append(v_e_w)
            mu_e_w_list.append(mu_e_w)
            phi_w_list.append(phi_w)
            cp_w_list.append(cp_w)
            cp0_w_list.append(cp0_w)
            h_e_w_list.append(h_e_w)
            T_r_lam_w_list.append(T_r_lam_w)
            h_r_lam_w_list.append(h_r_lam_w)
            h_star_lam_w_list.append(h_star_lam_w)
            T_r_turb_w_list.append(T_r_turb_w)
            h_r_turb_w_list.append(h_r_turb_w)
            h_star_turb_w_list.append(h_star_turb_w)
            q_lam_w_list.append(q_lam_w)
            q_turb_w_list.append(q_turb_w)
            St_l_list.append(St_l)
            Re_ns_l_list.append(Re_ns_l)
            re_x_star_list.append(re_x_star)
            re_x_star_turb_list.append(re_x_star_turb)
            distance_from_transition_list.append(distance_from_transition)
            re_x_over_re_tri_list.append(re_x_over_re_tri)
            x_w_list.append(x_strip)
            span_w_list.append(span_strip)
            xc_w_list.append(xc_strip)
            yb_w_list.append(yb_strip)
            Taw_tpg_w_list.append(Taw_tpg_w)

        q_w_arr = np.array(q_w_list, dtype=float).reshape(-1)
        q_l_arr = np.array(q_l_list, dtype=float).reshape(-1)
        Tw_w_arr = np.array(Tw_w_list, dtype=float).reshape(-1)
        Tw_l_arr = np.array(Tw_l_list, dtype=float).reshape(-1)
        w_tr_arr = np.array(w_tr_list, dtype=float).reshape(-1)
        re_edge_arr = np.array(re_edge_list, dtype=float).reshape(-1)
        re_tri_arr = np.array(re_tri_list, dtype=float).reshape(-1)
        re_x_star_arr = np.array(re_x_star_list, dtype=float).reshape(-1)
        re_x_star_turb_arr = np.array(re_x_star_turb_list, dtype=float).reshape(-1)
        distance_from_transition_arr = np.array(distance_from_transition_list, dtype=float).reshape(-1)
        re_x_over_re_tri_arr = np.array(re_x_over_re_tri_list, dtype=float).reshape(-1)
        T_e_w_arr = np.array(T_e_w_list, dtype=float).reshape(-1)
        p_e_w_arr = np.array(p_e_w_list, dtype=float).reshape(-1)
        rho_e_w_arr = np.array(rho_e_w_list, dtype=float).reshape(-1)
        ma_e_w_arr = np.array(ma_e_w_list, dtype=float).reshape(-1)
        v_e_w_arr = np.array(v_e_w_list, dtype=float).reshape(-1)
        mu_e_w_arr = np.array(mu_e_w_list, dtype=float).reshape(-1)
        phi_w_arr = np.array(phi_w_list, dtype=float).reshape(-1)
        cp_w_arr = np.array(cp_w_list, dtype=float).reshape(-1)
        cp0_w_arr = np.array(cp0_w_list, dtype=float).reshape(-1)
        h_e_w_arr = np.array(h_e_w_list, dtype=float).reshape(-1)
        T_r_lam_w_arr = np.array(T_r_lam_w_list, dtype=float).reshape(-1)
        h_r_lam_w_arr = np.array(h_r_lam_w_list, dtype=float).reshape(-1)
        h_star_lam_w_arr = np.array(h_star_lam_w_list, dtype=float).reshape(-1)
        T_r_turb_w_arr = np.array(T_r_turb_w_list, dtype=float).reshape(-1)
        h_r_turb_w_arr = np.array(h_r_turb_w_list, dtype=float).reshape(-1)
        h_star_turb_w_arr = np.array(h_star_turb_w_list, dtype=float).reshape(-1)
        q_lam_w_arr = np.array(q_lam_w_list, dtype=float).reshape(-1)
        q_turb_w_arr = np.array(q_turb_w_list, dtype=float).reshape(-1)
        St_l_arr = np.array(St_l_list, dtype=float).reshape(-1)
        Re_ns_l_arr = np.array(Re_ns_l_list, dtype=float).reshape(-1)
        x_w_arr = np.array(x_w_list, dtype=float).reshape(-1)
        span_w_arr = np.array(span_w_list, dtype=float).reshape(-1)
        xc_w_arr = np.array(xc_w_list, dtype=float).reshape(-1)
        yb_w_arr = np.array(yb_w_list, dtype=float).reshape(-1)
        Taw_tpg_w_arr = np.array(Taw_tpg_w_list, dtype=float).reshape(-1)

        def _payload_field(name: str, *, dtype: Any, fill: float | int) -> np.ndarray:
            rows = []
            for payload in strip_payloads:
                value = payload.get(name)
                if value is None:
                    rows.append(np.full((self.nx,), fill, dtype=dtype))
                else:
                    rows.append(np.asarray(value, dtype=dtype))
            return np.asarray(rows, dtype=dtype).reshape(-1)

        normal_upper = np.asarray(
            [np.asarray(p.get("normal_upper", np.full((self.nx, 3), np.nan)), dtype=float) for p in strip_payloads],
            dtype=float,
        ).reshape(-1, 3)
        normal_lower = np.asarray(
            [np.asarray(p.get("normal_lower", np.full((self.nx, 3), np.nan)), dtype=float) for p in strip_payloads],
            dtype=float,
        ).reshape(-1, 3)
        incidence_s_upper = _payload_field("incidence_s_upper", dtype=float, fill=np.nan)
        incidence_s_lower = _payload_field("incidence_s_lower", dtype=float, fill=np.nan)
        surface_class_upper = _payload_field("surface_class_upper", dtype=np.int8, fill=-2)
        surface_class_lower = _payload_field("surface_class_lower", dtype=np.int8, fill=-2)
        normal_source_upper = _payload_field("normal_source_upper", dtype=np.int8, fill=NORMAL_SOURCE_INVALID)
        normal_source_lower = _payload_field("normal_source_lower", dtype=np.int8, fill=NORMAL_SOURCE_INVALID)

        upper_recovery = build_leeward_freestream_recovery(
            surface_class=surface_class_upper,
            T_inf_K=float(T_inf),
            p_inf_Pa=float(p_inf),
            rho_inf_kg_m3=float(rho_inf),
            V_inf_m_s=float(_v_inf),
            Ma_inf=float(mach),
            gas=self.gas,
        )
        lower_recovery = build_leeward_freestream_recovery(
            surface_class=surface_class_lower,
            T_inf_K=float(T_inf),
            p_inf_Pa=float(p_inf),
            rho_inf_kg_m3=float(rho_inf),
            V_inf_m_s=float(_v_inf),
            Ma_inf=float(mach),
            gas=self.gas,
        )

        self.last_fields.update(
            {
                "q_w": q_w_arr,
                "q_l": q_l_arr,
                "Tw_w": Tw_w_arr,
                "Tw_l": Tw_l_arr,
                "w_tr": w_tr_arr,
                "re_edge": re_edge_arr,
                "re_tri": re_tri_arr,
                "re_x_star": re_x_star_arr,
                "re_x_star_turb": re_x_star_turb_arr,
                "distance_from_transition": distance_from_transition_arr,
                "re_x_over_re_tri": re_x_over_re_tri_arr,
                "T_e_w": T_e_w_arr,
                "p_e_w": p_e_w_arr,
                "rho_e_w": rho_e_w_arr,
                "ma_e_w": ma_e_w_arr,
                "v_e_w": v_e_w_arr,
                "mu_e_w": mu_e_w_arr,
                "phi_w": phi_w_arr,
                "cp_w": cp_w_arr,
                "cp0_w": cp0_w_arr,
                "h_e_w": h_e_w_arr,
                "T_r_lam_w": T_r_lam_w_arr,
                "h_r_lam_w": h_r_lam_w_arr,
                "h_star_lam_w": h_star_lam_w_arr,
                "T_r_turb_w": T_r_turb_w_arr,
                "h_r_turb_w": h_r_turb_w_arr,
                "h_star_turb_w": h_star_turb_w_arr,
                "q_lam_w": q_lam_w_arr,
                "q_turb_w": q_turb_w_arr,
                "St_l": St_l_arr,
                "Re_ns_l": Re_ns_l_arr,
                "x_w_m": x_w_arr,
                "span_w_m": span_w_arr,
                "x_l_m": x_w_arr,
                "span_l_m": span_w_arr,
                "xc_w": xc_w_arr,
                "yb_w": yb_w_arr,
                "xc_l": xc_w_arr,
                "yb_l": yb_w_arr,
                "Taw_tpg_w": Taw_tpg_w_arr,
                "normal_x_upper": normal_upper[:, 0],
                "normal_y_upper": normal_upper[:, 1],
                "normal_z_upper": normal_upper[:, 2],
                "normal_x_lower": normal_lower[:, 0],
                "normal_y_lower": normal_lower[:, 1],
                "normal_z_lower": normal_lower[:, 2],
                "incidence_s_upper": incidence_s_upper,
                "incidence_s_lower": incidence_s_lower,
                "surface_class_upper": surface_class_upper,
                "surface_class_lower": surface_class_lower,
                "normal_source_upper": normal_source_upper,
                "normal_source_lower": normal_source_lower,
                "mask_leeward_upper": upper_recovery.mask,
                "mask_leeward_lower": lower_recovery.mask,
                "T_e_leeward_upper": upper_recovery.T_e,
                "T_e_leeward_lower": lower_recovery.T_e,
                "p_e_leeward_upper": upper_recovery.p_e,
                "p_e_leeward_lower": lower_recovery.p_e,
                "rho_e_leeward_upper": upper_recovery.rho_e,
                "rho_e_leeward_lower": lower_recovery.rho_e,
                "V_e_leeward_upper": upper_recovery.V_e,
                "V_e_leeward_lower": lower_recovery.V_e,
                "Ma_e_leeward_upper": upper_recovery.Ma_e,
                "Ma_e_leeward_lower": lower_recovery.Ma_e,
                "h_e_leeward_upper": upper_recovery.h_e,
                "h_e_leeward_lower": lower_recovery.h_e,
                "mu_e_leeward_upper": upper_recovery.mu_e,
                "mu_e_leeward_lower": lower_recovery.mu_e,
                "Taw_tpg_leeward_upper": upper_recovery.Taw_tpg,
                "Taw_tpg_leeward_lower": lower_recovery.Taw_tpg,
                "mask_w": np.isfinite(q_w_arr),
                "mask_l": np.isfinite(q_l_arr),
                "xc_grid": np.asarray(self.xc_grid, dtype=float),
                "yb_grid": np.asarray(self.yb_grid, dtype=float),
            }
        )

        chunks = []
        for name in list(self.sampling.concat_order):
            if name not in self.last_fields:
                raise KeyError(f"Requested output field {name!r} not available. Available={list(self.last_fields.keys())}")
            chunks.append(np.asarray(self.last_fields[name], dtype=float).reshape(-1))
        return np.concatenate(chunks) if len(chunks) > 1 else chunks[0]