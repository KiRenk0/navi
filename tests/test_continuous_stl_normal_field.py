from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from ref_enthalpy_method.geometry.projected_semantics import (
    GEOMETRIC_SHEET_LOWER,
    GEOMETRIC_SHEET_UPPER,
    classify_triangle_geometric_sheets,
)
from ref_enthalpy_method.geometry.stl_surface import (
    AsciiStlMesh,
    ContinuousStlNormalField,
)


def _mesh(triangles: np.ndarray) -> AsciiStlMesh:
    values = np.asarray(triangles, dtype=np.float64)
    v0, v1, v2 = values[:, 0], values[:, 1], values[:, 2]
    p0, p1, p2 = v0[:, :2], v1[:, :2], v2[:, :2]
    return AsciiStlMesh(
        v0=v0,
        v1=v1,
        v2=v2,
        p0=p0,
        p1=p1,
        p2=p2,
        bb_min=np.minimum.reduce((p0, p1, p2)),
        bb_max=np.maximum.reduce((p0, p1, p2)),
    )


class ContinuousStlNormalFieldTest(unittest.TestCase):
    def test_smooth_shared_edge_has_one_continuous_normal(self) -> None:
        triangles = np.asarray(
            [
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                [[1.0, 0.0, 0.0], [1.0, 1.0, 0.1], [0.0, 1.0, 0.0]],
            ],
            dtype=np.float64,
        )
        field = ContinuousStlNormalField(
            mesh=_mesh(triangles),
            triangle_sheet=np.asarray([1, 1], dtype=np.int8),
            crease_angle_deg=20.0,
        )
        first = field.sample_outward_normal(triangle_id=0, x=0.5, span=0.5)
        second = field.sample_outward_normal(triangle_id=1, x=0.5, span=0.5)
        np.testing.assert_allclose(first, second, rtol=0.0, atol=1.0e-14)
        np.testing.assert_allclose(np.linalg.norm(first), 1.0)
        self.assertLess(float(np.dot(first, field.face_normals[0])), 1.0)
        self.assertLess(float(np.dot(first, field.face_normals[1])), 1.0)

    def test_sharp_crease_is_not_smoothed_across(self) -> None:
        triangles = np.asarray(
            [
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                [[1.0, 0.0, 0.0], [1.0, 1.0, 1.0], [0.0, 1.0, 0.0]],
            ],
            dtype=np.float64,
        )
        field = ContinuousStlNormalField(
            mesh=_mesh(triangles),
            triangle_sheet=np.asarray([1, 1], dtype=np.int8),
            crease_angle_deg=20.0,
        )
        first = field.sample_outward_normal(triangle_id=0, x=0.5, span=0.5)
        second = field.sample_outward_normal(triangle_id=1, x=0.5, span=0.5)
        np.testing.assert_allclose(first, field.face_normals[0], atol=1.0e-14)
        np.testing.assert_allclose(second, field.face_normals[1], atol=1.0e-14)
        self.assertLess(float(np.dot(first, second)), np.cos(np.deg2rad(20.0)))

    def test_lower_normals_are_oriented_outward(self) -> None:
        triangles = np.asarray(
            [[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]],
            dtype=np.float64,
        )
        field = ContinuousStlNormalField(
            mesh=_mesh(triangles),
            triangle_sheet=np.asarray([2], dtype=np.int8),
        )
        sampled = field.sample_outward_normal(triangle_id=0, x=0.2, span=0.2)
        self.assertLess(sampled[2], 0.0)

    def test_invalid_domain_fails_closed(self) -> None:
        triangles = np.asarray(
            [[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]],
            dtype=np.float64,
        )
        with self.assertRaisesRegex(ValueError, "one code"):
            ContinuousStlNormalField(
                mesh=_mesh(triangles), triangle_sheet=np.asarray([], dtype=np.int8)
            )
        with self.assertRaisesRegex(ValueError, "crease_angle_deg"):
            ContinuousStlNormalField(
                mesh=_mesh(triangles),
                triangle_sheet=np.asarray([1], dtype=np.int8),
                crease_angle_deg=180.0,
            )

    def test_formal_stl_is_continuous_on_upper_edges_and_preserves_lower_crease(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[1]
        mesh = AsciiStlMesh.load(stl_path=root / "new_spec/htv2_0628.stl")
        triangles = np.stack((mesh.v0, mesh.v1, mesh.v2), axis=1)
        sheets = classify_triangle_geometric_sheets(triangles)
        field = ContinuousStlNormalField(
            mesh=mesh,
            triangle_sheet=sheets,
            crease_angle_deg=20.0,
        )

        edges: dict[tuple[tuple[float, ...], tuple[float, ...]], list[int]] = {}
        for triangle_id, vertices in enumerate(triangles):
            if sheets[triangle_id] not in (
                GEOMETRIC_SHEET_UPPER,
                GEOMETRIC_SHEET_LOWER,
            ):
                continue
            for first, second in ((0, 1), (1, 2), (2, 0)):
                endpoints = sorted(
                    (
                        tuple(np.round(vertices[first], 12)),
                        tuple(np.round(vertices[second], 12)),
                    )
                )
                edges.setdefault((endpoints[0], endpoints[1]), []).append(triangle_id)

        smooth_errors = []
        sharp_angles = []
        for edge, triangle_ids in edges.items():
            if len(triangle_ids) != 2:
                continue
            first_id, second_id = triangle_ids
            if sheets[first_id] != sheets[second_id]:
                continue
            face_angle = float(
                np.rad2deg(
                    np.arccos(
                        np.clip(
                            np.dot(
                                field.face_normals[first_id],
                                field.face_normals[second_id],
                            ),
                            -1.0,
                            1.0,
                        )
                    )
                )
            )
            midpoint = 0.5 * (
                np.asarray(edge[0], dtype=np.float64)
                + np.asarray(edge[1], dtype=np.float64)
            )
            first = field.sample_outward_normal(
                triangle_id=first_id, x=float(midpoint[0]), span=float(midpoint[1])
            )
            second = field.sample_outward_normal(
                triangle_id=second_id, x=float(midpoint[0]), span=float(midpoint[1])
            )
            if not np.all(np.isfinite(first)) or not np.all(np.isfinite(second)):
                continue
            if sheets[first_id] == GEOMETRIC_SHEET_UPPER:
                self.assertLess(face_angle, 20.0)
                smooth_errors.append(float(np.linalg.norm(first - second)))
            elif face_angle > 20.0:
                sharp_angles.append(
                    float(
                        np.rad2deg(np.arccos(np.clip(np.dot(first, second), -1.0, 1.0)))
                    )
                )

        self.assertGreater(len(smooth_errors), 1000)
        self.assertLess(max(smooth_errors), 1.0e-12)
        self.assertGreater(len(sharp_angles), 0)
        self.assertGreater(max(sharp_angles), 20.0)
