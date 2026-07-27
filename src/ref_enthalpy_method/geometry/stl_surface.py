"""ASCII STL surface sampling helpers.

Goal:
- Use CAD-derived faceted geometry (STL triangles) as a robust source of local planar slopes.
- Avoid any image interpretation; the STL is treated as the ground truth.

Coordinate mapping (per user Creo export in this project):
- STL vertex fields are (x_cad, y_cad, z_cad)
- x_cad: nose -> tail  (matches solver x)
- y_cad: up            (maps to solver z_up)
- z_cad: centerline -> LEFT wing (symmetry plane at z_cad=0)

We solve the right half only, where z_cad <= 0. With span_sign=-1:
    span_m = -z_cad  (right half becomes span>=0)

Plane representation:
For a local planar patch z(x, y) (z is up, y is span), the unnormalized plane normal is:
    n = (nx, ny, nz)
and the slopes are:
    sx = dz/dx = -nx/nz
    sy = dz/dy = -ny/nz

Triangles with |nz| ~ 0 are side faces (near-vertical) and are ignored for slope sampling.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


def _auto_unit_scale(*, v_abs_max: float, unit: str) -> float:
    u = str(unit).strip().lower()
    if u == "m":
        return 1.0
    if u == "mm":
        return 1e-3
    # auto
    # In this project, geometry in meters is O(1..10). If values are O(1000),
    # it is almost certainly millimeters.
    return 1e-3 if float(v_abs_max) > 50.0 else 1.0


def _parse_vertex_line(line: str) -> tuple[float, float, float] | None:
    line = line.strip()
    if not line.startswith("vertex"):
        return None
    parts = line.split()
    if len(parts) < 4:
        return None
    try:
        return float(parts[1]), float(parts[2]), float(parts[3])
    except ValueError:
        return None


@dataclass(frozen=True)
class AsciiStlMesh:
    """Triangle soup from an ASCII STL in solver coords (x, span, up)."""

    # Triangle vertices
    v0: np.ndarray  # (nt,3)
    v1: np.ndarray  # (nt,3)
    v2: np.ndarray  # (nt,3)

    # Precomputed 2D projection (x, span) for point-in-triangle checks
    p0: np.ndarray  # (nt,2)
    p1: np.ndarray  # (nt,2)
    p2: np.ndarray  # (nt,2)

    # Bounding boxes in (x, span)
    bb_min: np.ndarray  # (nt,2)
    bb_max: np.ndarray  # (nt,2)

    @classmethod
    def load(
        cls,
        *,
        stl_path: str | Path,
        unit: str = "auto",
        span_sign: float = -1.0,
        right_half_only: bool = True,
        eps_span: float = 1e-9,
    ) -> AsciiStlMesh:
        p = Path(stl_path)
        if not p.exists():
            raise FileNotFoundError(f"STL not found: {p}")

        # First pass: parse triangles and collect coords in CAD axes
        tris: list[list[tuple[float, float, float]]] = []
        cur: list[tuple[float, float, float]] = []
        v_abs_max = 0.0
        with open(p, encoding="utf-8", errors="ignore") as f:
            for line in f:
                v = _parse_vertex_line(line)
                if v is None:
                    continue
                x, y, z = v
                v_abs_max = max(v_abs_max, abs(x), abs(y), abs(z))
                cur.append((x, y, z))
                if len(cur) == 3:  # 凑够三个顶点=一个三角形
                    tris.append(cur)
                    cur = []

        if len(tris) == 0:
            raise ValueError(f"No triangles parsed from STL: {p}")

        scale = float(_auto_unit_scale(v_abs_max=v_abs_max, unit=unit))  # 统一坐标

        # Convert to solver coords[坐标转换]: (x, span, up) = (x_cad, span_sign*z_cad, y_cad)
        arr = np.asarray(tris, dtype=float) * scale  # (nt,3,3) in CAD order
        x_cad = arr[:, :, 0]
        y_cad = arr[:, :, 1]
        z_cad = arr[:, :, 2]

        x = x_cad
        span = float(span_sign) * z_cad
        up = y_cad

        # Optionally keep right half only (span>=0)
        if bool(right_half_only):
            keep = np.all(span >= -float(eps_span), axis=1)
            x = x[keep, :]
            span = span[keep, :]
            up = up[keep, :]

        v0 = np.stack([x[:, 0], span[:, 0], up[:, 0]], axis=1)
        v1 = np.stack([x[:, 1], span[:, 1], up[:, 1]], axis=1)
        v2 = np.stack([x[:, 2], span[:, 2], up[:, 2]], axis=1)

        p0 = v0[:, :2].copy()
        p1 = v1[:, :2].copy()
        p2 = v2[:, :2].copy()

        bb_min = np.stack(
            [
                np.minimum.reduce([p0[:, 0], p1[:, 0], p2[:, 0]]),
                np.minimum.reduce([p0[:, 1], p1[:, 1], p2[:, 1]]),
            ],
            axis=1,
        )
        bb_max = np.stack(
            [
                np.maximum.reduce([p0[:, 0], p1[:, 0], p2[:, 0]]),
                np.maximum.reduce([p0[:, 1], p1[:, 1], p2[:, 1]]),
            ],
            axis=1,
        )

        return cls(
            v0=v0, v1=v1, v2=v2, p0=p0, p1=p1, p2=p2, bb_min=bb_min, bb_max=bb_max
        )


def _point_in_tri_2d(
    px: float, py: float, a: np.ndarray, b: np.ndarray, c: np.ndarray
) -> bool:
    """Barycentric test in 2D. a,b,c are (2,) arrays."""
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    cx, cy = float(c[0]), float(c[1])
    v0x, v0y = cx - ax, cy - ay
    v1x, v1y = bx - ax, by - ay
    v2x, v2y = px - ax, py - ay

    den = v0x * v1y - v1x * v0y
    if abs(den) < 1e-18:
        return False
    inv = 1.0 / den
    u = (v2x * v1y - v1x * v2y) * inv
    v = (v0x * v2y - v2x * v0y) * inv
    return (u >= -1e-12) and (v >= -1e-12) and (u + v <= 1.0 + 1e-12)


@dataclass
class SurfaceSlopeSampler:
    """Sample (sx, sy, z) on upper/lower surfaces from an STL mesh."""

    mesh: AsciiStlMesh
    nx_bin: int = 128
    ny_bin: int = 96
    nz_eps: float = 1e-10
    # Treat triangles with very small |n_hat_z| as side/cap faces rather than
    # the aerodynamic upper/lower skin whenever an alternative exists.
    surface_abs_nz_min: float = 0.45

    def __post_init__(self) -> None:
        bb0 = self.mesh.bb_min
        bb1 = self.mesh.bb_max
        self.x_min = float(np.nanmin(bb0[:, 0]))
        self.x_max = float(np.nanmax(bb1[:, 0]))
        self.y_min = float(np.nanmin(bb0[:, 1]))
        self.y_max = float(np.nanmax(bb1[:, 1]))
        self.nx_bin = int(max(8, self.nx_bin))
        self.ny_bin = int(max(8, self.ny_bin))
        self._bins: list[list[int]] = [[] for _ in range(self.nx_bin * self.ny_bin)]
        self._build_bins()

    def _bin_id(self, x: float, y: float) -> int:
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            return 0
        fx = (float(x) - self.x_min) / (self.x_max - self.x_min)
        fy = (float(y) - self.y_min) / (self.y_max - self.y_min)
        ix = int(np.clip(np.floor(fx * self.nx_bin), 0, self.nx_bin - 1))
        iy = int(np.clip(np.floor(fy * self.ny_bin), 0, self.ny_bin - 1))
        return iy * self.nx_bin + ix

    def _build_bins(self) -> None:
        bb0 = self.mesh.bb_min
        bb1 = self.mesh.bb_max
        for i in range(bb0.shape[0]):
            x0, y0 = float(bb0[i, 0]), float(bb0[i, 1])
            x1, y1 = float(bb1[i, 0]), float(bb1[i, 1])
            if not (
                np.isfinite(x0)
                and np.isfinite(y0)
                and np.isfinite(x1)
                and np.isfinite(y1)
            ):
                continue
            id0 = self._bin_id(x0, y0)
            id1 = self._bin_id(x1, y1)
            ix0 = id0 % self.nx_bin
            iy0 = id0 // self.nx_bin
            ix1 = id1 % self.nx_bin
            iy1 = id1 // self.nx_bin
            for iy in range(min(iy0, iy1), max(iy0, iy1) + 1):
                base = iy * self.nx_bin
                for ix in range(min(ix0, ix1), max(ix0, ix1) + 1):
                    self._bins[base + ix].append(i)

    def sample_upper_lower(
        self, *, x: float, span: float
    ) -> tuple[
        tuple[float, float, float, float, float, float] | None,
        tuple[float, float, float, float, float, float] | None,
    ]:
        """Return the existing six-field upper/lower sampling contract."""
        upper, lower = self.sample_upper_lower_with_triangle_id(x=x, span=span)
        return (
            None if upper is None else upper[:6],
            None if lower is None else lower[:6],
        )

    def sample_upper_lower_with_triangle_id(
        self,
        *,
        x: float,
        span: float,
        triangle_sheet: np.ndarray | None = None,
        upper_sheet_code: int = 1,
        lower_sheet_code: int = 2,
    ) -> tuple[
        tuple[float, float, float, float, float, float, int] | None,
        tuple[float, float, float, float, float, float, int] | None,
    ]:
        """Return selected skin samples plus the exact source triangle ID.

        When triangle_sheet is provided, upper/lower candidates are filtered
        by the requested geometric sheet before height ordering. This prevents
        a surviving triangle from one sheet being returned for both requests.
        """
        sheets: np.ndarray | None = None
        if triangle_sheet is not None:
            sheets = np.asarray(triangle_sheet)
            if sheets.shape != (self.mesh.v0.shape[0],):
                raise ValueError("triangle_sheet must have one code per STL triangle")
        bid = self._bin_id(float(x), float(span))
        cand = self._bins[bid]
        if not cand:
            return None, None

        px = float(x)
        py = float(span)
        candidates: list[dict[str, float]] = []

        for ti in cand:
            # Quick bb reject
            if (
                px < float(self.mesh.bb_min[ti, 0]) - 1e-12
                or px > float(self.mesh.bb_max[ti, 0]) + 1e-12
            ):
                continue
            if (
                py < float(self.mesh.bb_min[ti, 1]) - 1e-12
                or py > float(self.mesh.bb_max[ti, 1]) + 1e-12
            ):
                continue
            if not _point_in_tri_2d(
                px, py, self.mesh.p0[ti], self.mesh.p1[ti], self.mesh.p2[ti]
            ):
                continue

            v0 = self.mesh.v0[ti]
            v1 = self.mesh.v1[ti]
            v2 = self.mesh.v2[ti]
            n = np.cross(v1 - v0, v2 - v0)  # (3,)叉乘
            n_norm = float(np.linalg.norm(n))
            if not (n_norm > float(self.nz_eps)):
                continue
            nz = float(n[2])
            if abs(nz) < float(self.nz_eps):
                continue
            # Plane: n·(p - v0) = 0 -> z = z0 - (nx(x-x0) + ny(y-y0))/nz
            nx = float(n[0])
            ny = float(n[1])
            x0, y0, z0 = float(v0[0]), float(v0[1]), float(v0[2])
            z = z0 - (nx * (px - x0) + ny * (py - y0)) / nz
            sx = -nx / nz
            sy = -ny / nz
            abs_nz_hat = abs(nz) / n_norm

            candidates.append(
                {
                    "sx": float(sx),
                    "sy": float(sy),
                    "z": float(z),
                    "nx": float(nx),
                    "ny": float(ny),
                    "nz": float(nz),
                    "abs_nz_hat": float(abs_nz_hat),
                    "triangle_id": int(ti),
                }
            )

        if not candidates:
            return None, None

        def _pick_surface(
            *, want_upper: bool
        ) -> tuple[float, float, float, float, float, float, int] | None:
            requested_code = int(upper_sheet_code if want_upper else lower_sheet_code)
            ordered = sorted(
                (
                    candidate
                    for candidate in candidates
                    if sheets is None
                    or int(sheets[int(candidate["triangle_id"])]) == requested_code
                ),
                key=lambda c: (
                    (-1.0 if want_upper else 1.0) * float(c["z"]),
                    int(c["triangle_id"]),
                ),
            )
            for c in ordered:
                if float(c["abs_nz_hat"]) >= float(self.surface_abs_nz_min):
                    return (
                        float(c["sx"]),
                        float(c["sy"]),
                        float(c["z"]),
                        float(c["nx"]),
                        float(c["ny"]),
                        float(c["nz"]),
                        int(c["triangle_id"]),
                    )
            return None

        upper = _pick_surface(want_upper=True)
        lower = _pick_surface(want_upper=False)
        return upper, lower


def _corner_angle(vertices: np.ndarray, corner: int) -> float:
    origin = vertices[corner]
    first = vertices[(corner + 1) % 3] - origin
    second = vertices[(corner + 2) % 3] - origin
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    if denominator <= 0.0:
        return 0.0
    cosine = float(np.clip(np.dot(first, second) / denominator, -1.0, 1.0))
    return float(np.arccos(cosine))


def _barycentric_coordinates_2d(
    *,
    point: np.ndarray,
    triangle: np.ndarray,
) -> np.ndarray:
    px, py = np.asarray(point, dtype=np.float64)
    (ax, ay), (bx, by), (cx, cy) = np.asarray(triangle, dtype=np.float64)
    denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(float(denominator)) <= 1.0e-18:
        return np.full(3, np.nan, dtype=np.float64)
    first = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / denominator
    second = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / denominator
    return np.asarray([first, second, 1.0 - first - second], dtype=np.float64)


@dataclass
class ContinuousStlNormalField:
    """Angle-weighted, crease-preserving vertex normals for an STL triangle soup.

    Triangle selection and surface height remain owned by SurfaceSlopeSampler.
    This field only replaces piecewise-constant face normals where a consumer
    requires a continuous normal on a design surface intended to be smooth.
    """

    mesh: AsciiStlMesh
    triangle_sheet: np.ndarray
    crease_angle_deg: float = 20.0
    upper_sheet_code: int = 1
    lower_sheet_code: int = 2
    vertex_round_decimals: int = 12

    def __post_init__(self) -> None:
        triangles = np.stack((self.mesh.v0, self.mesh.v1, self.mesh.v2), axis=1).astype(
            np.float64, copy=False
        )
        sheets = np.asarray(self.triangle_sheet)
        if sheets.shape != (triangles.shape[0],):
            raise ValueError("triangle_sheet must have one code per STL triangle")
        crease = float(self.crease_angle_deg)
        if not np.isfinite(crease) or not 0.0 < crease < 180.0:
            raise ValueError("crease_angle_deg must be finite and between 0 and 180")

        raw = np.cross(
            triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
        )
        magnitude = np.linalg.norm(raw, axis=1)
        face_normals = np.full(raw.shape, np.nan, dtype=np.float64)
        valid = magnitude > 1.0e-12
        face_normals[valid] = raw[valid] / magnitude[valid, None]
        for code, z_sign in (
            (int(self.upper_sheet_code), 1.0),
            (int(self.lower_sheet_code), -1.0),
        ):
            flip = (sheets == code) & valid & (face_normals[:, 2] * z_sign < 0.0)
            face_normals[flip] *= -1.0

        corner_angles = np.zeros((triangles.shape[0], 3), dtype=np.float64)
        adjacency: dict[
            tuple[int, tuple[float, float, float]], list[tuple[int, int]]
        ] = {}
        skin_codes = {int(self.upper_sheet_code), int(self.lower_sheet_code)}
        for triangle_id, vertices in enumerate(triangles):
            sheet_code = int(sheets[triangle_id])
            if sheet_code not in skin_codes or not valid[triangle_id]:
                continue
            for corner in range(3):
                corner_angles[triangle_id, corner] = _corner_angle(vertices, corner)
                vertex_key = tuple(
                    np.round(vertices[corner], int(self.vertex_round_decimals)).tolist()
                )
                adjacency.setdefault((sheet_code, vertex_key), []).append(
                    (triangle_id, corner)
                )

        cosine_limit = float(np.cos(np.deg2rad(crease)))
        corner_normals = np.full((*corner_angles.shape, 3), np.nan, dtype=np.float64)
        for triangle_id, vertices in enumerate(triangles):
            sheet_code = int(sheets[triangle_id])
            if sheet_code not in skin_codes or not valid[triangle_id]:
                continue
            reference = face_normals[triangle_id]
            for corner in range(3):
                vertex_key = tuple(
                    np.round(vertices[corner], int(self.vertex_round_decimals)).tolist()
                )
                weighted = np.zeros(3, dtype=np.float64)
                for adjacent_id, adjacent_corner in adjacency[(sheet_code, vertex_key)]:
                    candidate = face_normals[adjacent_id]
                    if float(np.dot(reference, candidate)) < cosine_limit:
                        continue
                    weight = float(corner_angles[adjacent_id, adjacent_corner])
                    weighted += weight * candidate
                weighted_norm = float(np.linalg.norm(weighted))
                if weighted_norm <= 1.0e-12:
                    corner_normals[triangle_id, corner] = reference
                else:
                    corner_normals[triangle_id, corner] = weighted / weighted_norm

        self.face_normals = face_normals
        self.corner_normals = corner_normals

    def sample_outward_normal(
        self,
        *,
        triangle_id: int,
        x: float,
        span: float,
    ) -> np.ndarray:
        """Interpolate the crease-aware vertex normal inside one selected triangle."""

        index = int(triangle_id)
        if index < 0 or index >= self.face_normals.shape[0]:
            raise IndexError("triangle_id is outside the STL triangle array")
        corners = self.corner_normals[index]
        if not np.all(np.isfinite(corners)):
            return np.full(3, np.nan, dtype=np.float64)
        projected = np.stack(
            (self.mesh.p0[index], self.mesh.p1[index], self.mesh.p2[index])
        )
        barycentric = _barycentric_coordinates_2d(
            point=np.asarray([x, span], dtype=np.float64),
            triangle=projected,
        )
        if not np.all(np.isfinite(barycentric)) or np.any(barycentric < -1.0e-8):
            return np.full(3, np.nan, dtype=np.float64)
        interpolated = barycentric @ corners
        magnitude = float(np.linalg.norm(interpolated))
        if magnitude <= 1.0e-12:
            return np.full(3, np.nan, dtype=np.float64)
        return np.asarray(interpolated / magnitude, dtype=np.float64)
