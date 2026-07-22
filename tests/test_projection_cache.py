"""Comprehensive tests for the geometry-identity projection cache.

Covers:
- Valid round-trip (write/load)
- Identity mismatch: geometry, STL, gate, algorithm version, x_offset
- Shape/dtype corruption
- Triangle index out of bounds
- Non-finite values
- Truncated/corrupted cache
- Temperature-only CSV change (same geometry) allows reuse
- Geometry column bit change rejects reuse
"""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from ref_enthalpy_method.geometry.projection_cache import (
    ALGORITHM_VERSION,
    CACHE_SCHEMA_VERSION,
    COORDINATE_CONVENTION,
    TIE_BREAK_IDENTITY,
    CacheIdentityMismatchError,
    CacheIntegrityError,
    build_cache_manifest,
    build_geometry_identity,
    load_projection_cache,
    write_projection_cache,
)
from ref_enthalpy_method.mapping.fluent_projection import (
    FluentSurfaceProjection,
    project_fluent_surface_exact,
    project_fluent_surface_with_cache,
)
from ref_enthalpy_method.mapping.fluent_surface import read_fluent_surface_geometry_csv


def _sha256_ndarray(arr: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(arr).tobytes(order="C")
    ).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_synthetic_identity() -> dict[str, str | int | float]:
    """Build identity dict matching the synthetic test data below."""
    return {
        "fluent_source_geometry_sha256": _sha256_text("source-geo"),
        "fluent_canonical_geometry_sha256": _sha256_text("canonical-geo"),
        "canonical_point_count": 3,
        "x_offset_m": 0.030,
        "stl_raw_sha256": _sha256_text("stl-raw"),
        "triangle_canonical_sha256": _sha256_text("tri-canonical"),
        "vehicle_spec_raw_sha256": _sha256_text("veh-spec"),
        "sampling_spec_raw_sha256": _sha256_text("samp-spec"),
        "outline_geometry_sha256": _sha256_text("outline-geo"),
        "projection_gate_m": 0.005,
    }


def _make_synthetic_arrays() -> dict[str, np.ndarray]:
    """Build synthetic projection arrays (canonical_point_count=3)."""
    return {
        "projected_xyz": np.array(
            [[0.0, 0.0, 0.0], [1.0, 1.0, 0.0], [2.0, 0.0, 0.0]],
            dtype=np.float64,
        ),
        "triangle_id": np.array([0, 42, 7], dtype=np.int64),
        "raw_normal": np.array(
            [[0.0, 0.0, 1.0], [0.0, 0.0, 1.0], [0.0, 0.0, -1.0]],
            dtype=np.float64,
        ),
        "projection_distance_m": np.array([0.001, 0.003, 0.002], dtype=np.float64),
        "projection_gate_pass": np.array([True, True, True], dtype=np.bool_),
    }


def _write_and_load(
    tmp_dir: str,
    identity_override: dict | None = None,
    arrays_override: dict | None = None,
    triangle_count: int | None = None,
) -> tuple[Path, object]:
    """Write a cache file and attempt to load it. Returns (path, result or exception)."""
    identity = _make_synthetic_identity()
    if identity_override is not None:
        identity.update(identity_override)

    arrays = _make_synthetic_arrays()
    if arrays_override is not None:
        arrays.update(arrays_override)

    manifest = build_cache_manifest(**identity, **arrays)
    path = Path(tmp_dir) / "test_cache.npz"

    write_projection_cache(
        target_path=path,
        manifest=manifest,
        **arrays,
    )

    try:
        result = load_projection_cache(
            path,
            **{k: v for k, v in identity.items()},
            triangle_count=triangle_count,
        )
        return path, result
    except Exception as exc:
        return path, exc


# ---------------------------------------------------------------------------
# Valid round-trip
# ---------------------------------------------------------------------------


class CacheRoundTripTest(unittest.TestCase):
    """Valid cache write/load round-trip."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_valid_round_trip_preserves_all_fields(self) -> None:
        _, result = _write_and_load(self.tmp.name, triangle_count=100)
        self.assertIsNotNone(result)
        arrays = _make_synthetic_arrays()
        np.testing.assert_array_equal(result.projected_xyz, arrays["projected_xyz"])
        np.testing.assert_array_equal(result.triangle_id, arrays["triangle_id"])
        np.testing.assert_array_equal(result.raw_normal, arrays["raw_normal"])
        np.testing.assert_array_equal(
            result.projection_distance_m, arrays["projection_distance_m"]
        )
        np.testing.assert_array_equal(
            result.projection_gate_pass, arrays["projection_gate_pass"]
        )

    def test_manifest_is_round_tripped(self) -> None:
        _, result = _write_and_load(self.tmp.name, triangle_count=100)
        m = result.manifest
        self.assertEqual(m["cache_schema_version"], CACHE_SCHEMA_VERSION)
        self.assertEqual(m["algorithm_version"], ALGORITHM_VERSION)
        self.assertEqual(m["coordinate_convention"], COORDINATE_CONVENTION)
        self.assertEqual(m["tie_break_identity"], TIE_BREAK_IDENTITY)
        self.assertEqual(m["canonical_point_count"], 3)
        self.assertEqual(m["x_offset_m"], 0.030)
        self.assertEqual(m["projection_gate_m"], 0.005)


# ---------------------------------------------------------------------------
# Identity mismatch tests
# ---------------------------------------------------------------------------


class CacheIdentityMismatchTest(unittest.TestCase):
    """Every identity field mismatch must reject loading."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_geometry_source_hash_mismatch(self) -> None:
        """Cache written with one geometry hash must reject loading with different hash."""
        # Write cache with hash "written"
        identity_written = _make_synthetic_identity()
        identity_written["fluent_source_geometry_sha256"] = _sha256_text("written")
        arrays = _make_synthetic_arrays()
        manifest = build_cache_manifest(**identity_written, **arrays)
        path = Path(self.tmp.name) / "test_geo_hash.npz"
        write_projection_cache(target_path=path, manifest=manifest, **arrays)

        # Try to load with different hash "loaded"
        identity_loaded = _make_synthetic_identity()
        identity_loaded["fluent_source_geometry_sha256"] = _sha256_text("loaded")
        with self.assertRaises(CacheIdentityMismatchError):
            load_projection_cache(path, **identity_loaded)

    def test_stl_hash_mismatch(self) -> None:
        path, _ = _write_and_load(self.tmp.name)
        identity = _make_synthetic_identity()
        identity["stl_raw_sha256"] = _sha256_text("different-stl")
        with self.assertRaises(CacheIdentityMismatchError):
            load_projection_cache(path, **identity)

    def test_projection_gate_mismatch(self) -> None:
        path, _ = _write_and_load(self.tmp.name)
        identity = _make_synthetic_identity()
        identity["projection_gate_m"] = 0.100  # different from 0.005
        with self.assertRaises(CacheIdentityMismatchError):
            load_projection_cache(path, **identity)

    def test_x_offset_mismatch(self) -> None:
        path, _ = _write_and_load(self.tmp.name)
        identity = _make_synthetic_identity()
        identity["x_offset_m"] = 0.050  # different from 0.030
        with self.assertRaises(CacheIdentityMismatchError):
            load_projection_cache(path, **identity)

    def test_canonical_point_count_mismatch(self) -> None:
        path, _ = _write_and_load(self.tmp.name)
        identity = _make_synthetic_identity()
        identity["canonical_point_count"] = 5  # different from 3
        with self.assertRaises(CacheIdentityMismatchError):
            load_projection_cache(path, **identity)

    def test_vehicle_spec_hash_mismatch(self) -> None:
        path, _ = _write_and_load(self.tmp.name)
        identity = _make_synthetic_identity()
        identity["vehicle_spec_raw_sha256"] = _sha256_text("diff-veh")
        with self.assertRaises(CacheIdentityMismatchError):
            load_projection_cache(path, **identity)

    def test_sampling_spec_hash_mismatch(self) -> None:
        path, _ = _write_and_load(self.tmp.name)
        identity = _make_synthetic_identity()
        identity["sampling_spec_raw_sha256"] = _sha256_text("diff-samp")
        with self.assertRaises(CacheIdentityMismatchError):
            load_projection_cache(path, **identity)

    def test_algorithm_version_would_be_rejected_if_changed(self) -> None:
        """Corrupted manifest with wrong algorithm_version must be rejected."""
        path, _ = _write_and_load(self.tmp.name)
        # Directly tamper with the npz to change algorithm_version
        data = dict(np.load(path, allow_pickle=True))
        manifest = json.loads(bytes(data["manifest_json"]).decode("utf-8"))
        manifest["algorithm_version"] = "wrong-version/v0"
        data["manifest_json"] = json.dumps(manifest, sort_keys=True).encode("utf-8")
        tampered = Path(self.tmp.name) / "tampered.npz"
        np.savez_compressed(tampered, **data)
        identity = _make_synthetic_identity()
        with self.assertRaises(CacheIdentityMismatchError):
            load_projection_cache(tampered, **identity)

    def test_schema_version_would_be_rejected_if_changed(self) -> None:
        path, _ = _write_and_load(self.tmp.name)
        data = dict(np.load(path, allow_pickle=True))
        manifest = json.loads(bytes(data["manifest_json"]).decode("utf-8"))
        manifest["cache_schema_version"] = "wrong-schema/v0"
        data["manifest_json"] = json.dumps(manifest, sort_keys=True).encode("utf-8")
        tampered = Path(self.tmp.name) / "tampered_schema.npz"
        np.savez_compressed(tampered, **data)
        identity = _make_synthetic_identity()
        with self.assertRaises(CacheIdentityMismatchError):
            load_projection_cache(tampered, **identity)


# ---------------------------------------------------------------------------
# Shape/dtype corruption tests
# ---------------------------------------------------------------------------


class CacheShapeDtypeCorruptionTest(unittest.TestCase):
    """Corrupted shape or dtype must reject loading."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_truncated_point_count(self) -> None:
        """Arrays with wrong shape (fewer rows than point_count) must fail."""
        identity = _make_synthetic_identity()
        arrays = _make_synthetic_arrays()
        # Truncate all arrays to 1 row but manifest says point_count=3
        arrays["projected_xyz"] = arrays["projected_xyz"][:1]
        arrays["triangle_id"] = arrays["triangle_id"][:1]
        arrays["raw_normal"] = arrays["raw_normal"][:1]
        arrays["projection_distance_m"] = arrays["projection_distance_m"][:1]
        arrays["projection_gate_pass"] = arrays["projection_gate_pass"][:1]
        manifest = build_cache_manifest(**identity, **arrays)
        manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        path = Path(self.tmp.name) / "truncated.npz"
        # Write directly (bypass write_projection_cache validation)
        np.savez_compressed(
            path,
            projected_xyz=arrays["projected_xyz"],
            triangle_id=arrays["triangle_id"],
            raw_normal=arrays["raw_normal"],
            projection_distance_m=arrays["projection_distance_m"],
            projection_gate_pass=arrays["projection_gate_pass"],
            manifest_json=manifest_json.encode("utf-8"),
        )
        # Load with original identity (point_count=3) should fail shape check
        identity_load = _make_synthetic_identity()  # point_count=3
        with self.assertRaises((CacheIntegrityError, CacheIdentityMismatchError)):
            load_projection_cache(path, **identity_load)

    def test_wrong_dtype(self) -> None:
        """Arrays with wrong dtype must fail hash checks."""
        identity = _make_synthetic_identity()
        arrays = _make_synthetic_arrays()
        arrays["projected_xyz"] = arrays["projected_xyz"].astype(np.float32)
        manifest = build_cache_manifest(**identity, **arrays)
        manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        path = Path(self.tmp.name) / "wrong_dtype.npz"
        # Write directly (bypass write_projection_cache validation)
        np.savez_compressed(
            path,
            projected_xyz=arrays["projected_xyz"],
            triangle_id=arrays["triangle_id"],
            raw_normal=arrays["raw_normal"],
            projection_distance_m=arrays["projection_distance_m"],
            projection_gate_pass=arrays["projection_gate_pass"],
            manifest_json=manifest_json.encode("utf-8"),
        )
        identity["canonical_point_count"] = 3
        with self.assertRaises((CacheIntegrityError, CacheIdentityMismatchError)):
            load_projection_cache(path, **identity)


# ---------------------------------------------------------------------------
# Triangle index bounds
# ---------------------------------------------------------------------------


class CacheTriangleBoundsTest(unittest.TestCase):
    """Triangle index out-of-bounds must fail."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_index_out_of_bounds(self) -> None:
        path, _ = _write_and_load(self.tmp.name)
        identity = _make_synthetic_identity()
        # Load with triangle_count=10, but triangle_id includes 42
        with self.assertRaises(CacheIntegrityError):
            load_projection_cache(path, **identity, triangle_count=10)

    def test_negative_index(self) -> None:
        identity = _make_synthetic_identity()
        arrays = _make_synthetic_arrays()
        arrays["triangle_id"] = np.array([0, -1, 7], dtype=np.int64)
        manifest = build_cache_manifest(**identity, **arrays)
        manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        path = Path(self.tmp.name) / "neg_idx.npz"
        # Write directly (bypass write_projection_cache validation)
        np.savez_compressed(
            path,
            projected_xyz=arrays["projected_xyz"],
            triangle_id=arrays["triangle_id"],
            raw_normal=arrays["raw_normal"],
            projection_distance_m=arrays["projection_distance_m"],
            projection_gate_pass=arrays["projection_gate_pass"],
            manifest_json=manifest_json.encode("utf-8"),
        )
        with self.assertRaises((CacheIntegrityError, CacheIdentityMismatchError)):
            load_projection_cache(path, **identity)


# ---------------------------------------------------------------------------
# Non-finite values
# ---------------------------------------------------------------------------


class CacheNonFiniteTest(unittest.TestCase):
    """Non-finite arrays must fail."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_nan_in_projected_xyz(self) -> None:
        identity = _make_synthetic_identity()
        arrays = _make_synthetic_arrays()
        arrays["projected_xyz"][0, 0] = np.nan
        manifest = build_cache_manifest(**identity, **arrays)
        manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        path = Path(self.tmp.name) / "nan_xyz.npz"
        # Write directly (bypass write_projection_cache validation)
        np.savez_compressed(
            path,
            projected_xyz=arrays["projected_xyz"],
            triangle_id=arrays["triangle_id"],
            raw_normal=arrays["raw_normal"],
            projection_distance_m=arrays["projection_distance_m"],
            projection_gate_pass=arrays["projection_gate_pass"],
            manifest_json=manifest_json.encode("utf-8"),
        )
        with self.assertRaises((CacheIntegrityError, CacheIdentityMismatchError)):
            load_projection_cache(path, **identity)

    def test_negative_distance(self) -> None:
        identity = _make_synthetic_identity()
        arrays = _make_synthetic_arrays()
        arrays["projection_distance_m"][1] = -0.001
        manifest = build_cache_manifest(**identity, **arrays)
        manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        path = Path(self.tmp.name) / "neg_dist.npz"
        # Write directly (bypass write_projection_cache validation)
        np.savez_compressed(
            path,
            projected_xyz=arrays["projected_xyz"],
            triangle_id=arrays["triangle_id"],
            raw_normal=arrays["raw_normal"],
            projection_distance_m=arrays["projection_distance_m"],
            projection_gate_pass=arrays["projection_gate_pass"],
            manifest_json=manifest_json.encode("utf-8"),
        )
        with self.assertRaises((CacheIntegrityError, CacheIdentityMismatchError)):
            load_projection_cache(path, **identity)


# ---------------------------------------------------------------------------
# Truncated / corrupted cache file
# ---------------------------------------------------------------------------


class CacheTruncatedCorruptedTest(unittest.TestCase):
    """Truncated or corrupted cache files must fail."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_truncated_file(self) -> None:
        path, _ = _write_and_load(self.tmp.name)
        truncated = Path(self.tmp.name) / "truncated.npz"
        data = path.read_bytes()[:50]  # truncate
        truncated.write_bytes(data)
        identity = _make_synthetic_identity()
        with self.assertRaises((CacheIntegrityError, CacheIdentityMismatchError, OSError)):
            load_projection_cache(truncated, **identity)

    def test_corrupted_manifest_json(self) -> None:
        path, _ = _write_and_load(self.tmp.name)
        data = dict(np.load(path, allow_pickle=True))
        data["manifest_json"] = b"this is not json"
        corrupted = Path(self.tmp.name) / "corrupted.npz"
        np.savez_compressed(corrupted, **data)
        identity = _make_synthetic_identity()
        with self.assertRaises(CacheIntegrityError):
            load_projection_cache(corrupted, **identity)


# ---------------------------------------------------------------------------
# Temperature-only CSV reuse (same geometry)
# ---------------------------------------------------------------------------


class CacheGeometryReuseTest(unittest.TestCase):
    """Same geometry hash, different temperature CSV — allowed reuse."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_same_geometry_different_temperature_csv_reuse(self) -> None:
        """If all geometry hashes match, different temp CSV is fine."""
        # Write with identity A
        identity_a = _make_synthetic_identity()
        arrays = _make_synthetic_arrays()
        manifest = build_cache_manifest(**identity_a, **arrays)
        path = Path(self.tmp.name) / "cache_a.npz"
        write_projection_cache(target_path=path, manifest=manifest, **arrays)

        # Load with identity B — same geometry hashes, only "wall temperature CSV"
        # would differ, but we don't hash wall temperature.
        identity_b = _make_synthetic_identity()  # identical keys
        # This should succeed — cache doesn't bind to temperature
        result = load_projection_cache(path, **identity_b, triangle_count=100)
        self.assertIsNotNone(result)

    def test_geometry_column_bit_change_rejects_reuse(self) -> None:
        """Any single bit change in geometry hash must reject."""
        path, _ = _write_and_load(self.tmp.name)
        identity = _make_synthetic_identity()
        # Flip one character in the canonical geometry hash
        original_hash = identity["fluent_canonical_geometry_sha256"]
        flipped = "0" + original_hash[1:] if original_hash[0] != "0" else "1" + original_hash[1:]
        identity["fluent_canonical_geometry_sha256"] = flipped
        with self.assertRaises(CacheIdentityMismatchError):
            load_projection_cache(path, **identity)


# ---------------------------------------------------------------------------
# build_geometry_identity convenience
# ---------------------------------------------------------------------------


class BuildGeometryIdentityTest(unittest.TestCase):
    """Convenience function produces consistent hashes."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_build_identity_from_files(self) -> None:
        tmp = Path(self.tmp.name)

        # Create dummy files
        geo_path = tmp / "fluent.csv"
        geo_path.write_text("cellnumber,x,y,z\n1,0,0,0\n", encoding="utf-8")

        stl_path = tmp / "mesh.stl"
        stl_path.write_text("solid test\nendsolid test\n", encoding="utf-8")

        veh_path = tmp / "vehicle.yaml"
        veh_path.write_text("vehicle_spec:\n  vehicle_id: test\n", encoding="utf-8")

        samp_path = tmp / "sampling.yaml"
        samp_path.write_text("mode: full_wing_surface_grid\n", encoding="utf-8")

        triangles = np.zeros((2, 3, 3), dtype=np.float64)

        identity = build_geometry_identity(
            fluent_geometry_source_path=geo_path,
            fluent_canonical_geometry_sha256=_sha256_text("canonical"),
            canonical_point_count=1,
            x_offset_m=0.030,
            stl_path=stl_path,
            triangles=triangles,
            vehicle_spec_path=veh_path,
            sampling_spec_path=samp_path,
            outline_path=None,
            projection_gate_m=0.005,
        )

        self.assertEqual(identity["canonical_point_count"], 1)
        self.assertEqual(identity["x_offset_m"], 0.030)
        self.assertEqual(identity["projection_gate_m"], 0.005)
        self.assertIsInstance(identity["fluent_source_geometry_sha256"], str)
        self.assertEqual(len(identity["fluent_source_geometry_sha256"]), 64)
        self.assertIsInstance(identity["triangle_canonical_sha256"], str)
        self.assertEqual(len(identity["triangle_canonical_sha256"]), 64)

    def test_build_identity_is_deterministic(self) -> None:
        tmp = Path(self.tmp.name)
        geo_path = tmp / "geo.csv"
        geo_path.write_text("a,b,c,d\n1,2,3,4\n", encoding="utf-8")
        stl_path = tmp / "m.stl"
        stl_path.write_text("solid\nendsolid\n", encoding="utf-8")
        veh_path = tmp / "v.yaml"
        veh_path.write_text("v: 1\n", encoding="utf-8")
        samp_path = tmp / "s.yaml"
        samp_path.write_text("s: 2\n", encoding="utf-8")
        triangles = np.eye(3).reshape(1, 3, 3)

        id1 = build_geometry_identity(
            fluent_geometry_source_path=geo_path,
            fluent_canonical_geometry_sha256=_sha256_text("c"),
            canonical_point_count=5,
            x_offset_m=0.1,
            stl_path=stl_path,
            triangles=triangles,
            vehicle_spec_path=veh_path,
            sampling_spec_path=samp_path,
            outline_path=None,
        )
        id2 = build_geometry_identity(
            fluent_geometry_source_path=geo_path,
            fluent_canonical_geometry_sha256=_sha256_text("c"),
            canonical_point_count=5,
            x_offset_m=0.1,
            stl_path=stl_path,
            triangles=triangles,
            vehicle_spec_path=veh_path,
            sampling_spec_path=samp_path,
            outline_path=None,
        )
        for key in id1:
            self.assertEqual(id1[key], id2[key], f"Mismatch on {key}")


class CacheOrchestrationTest(unittest.TestCase):
    """Public cache entry point distinguishes miss, mismatch, and corruption."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.geometry_path = self.root / "surface.csv"
        self.stl_path = self.root / "mesh.stl"
        self.vehicle_path = self.root / "vehicle.yaml"
        self.sampling_path = self.root / "sampling.yaml"
        self.cache_path = self.root / "projection.npz"
        self.stl_path.write_text("solid mesh\nendsolid mesh\n", encoding="utf-8")
        self.vehicle_path.write_text("vehicle: test\n", encoding="utf-8")
        self.sampling_path.write_text("sampling: test\n", encoding="utf-8")
        self._write_geometry(self.geometry_path, temperatures=(300.0, 400.0))
        self.geometry = read_fluent_surface_geometry_csv(
            self.geometry_path, x_offset_m=0.030
        )
        self.triangles = np.array(
            [[[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 2.0, 0.0]]],
            dtype=np.float64,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def _write_geometry(
        path: Path,
        *,
        temperatures: tuple[float, float],
        geometry_delta: float = 0.0,
    ) -> None:
        path.write_text(
            "cellnumber,x-coordinate,y-coordinate,z-coordinate,wall-temperature\n"
            f"1,{0.17 + geometry_delta},0.2,0.001,{temperatures[0]}\n"
            f"2,0.37,0.3,0.002,{temperatures[1]}\n",
            encoding="utf-8",
        )

    def _identity_kwargs(self) -> dict[str, object]:
        return {
            "x_offset_m": 0.030,
            "stl_path": self.stl_path,
            "vehicle_spec_path": self.vehicle_path,
            "sampling_spec_path": self.sampling_path,
            "outline_path": None,
        }

    def _call(
        self,
        *,
        geometry=None,
        cache_path: Path | None = None,
        write_cache: bool = False,
        use_bvh: bool = False,
        gate: float = 0.005,
    ) -> FluentSurfaceProjection:
        return project_fluent_surface_with_cache(
            self.geometry if geometry is None else geometry,
            self.triangles,
            projection_gate_m=gate,
            use_bvh=use_bvh,
            cache_path=cache_path,
            write_cache=write_cache,
            geometry_identity_kwargs=(
                None if cache_path is None else self._identity_kwargs()
            ),
        )

    def _create_valid_cache(self) -> FluentSurfaceProjection:
        return self._call(cache_path=self.cache_path, write_cache=True)

    def _read_npz(self) -> dict[str, np.ndarray]:
        with np.load(self.cache_path, allow_pickle=False) as loaded:
            return {
                name: np.array(loaded[name], copy=True)
                for name in loaded.files
            }

    def _rewrite_npz(self, data: dict[str, np.ndarray]) -> None:
        np.savez_compressed(self.cache_path, **data)

    def _tamper_manifest(self, key: str, value: object) -> None:
        data = self._read_npz()
        manifest = json.loads(bytes(data["manifest_json"]).decode("utf-8"))
        manifest[key] = value
        data["manifest_json"] = np.asarray(
            json.dumps(manifest, sort_keys=True).encode("utf-8")
        )
        self._rewrite_npz(data)

    def test_no_cache_path_and_missing_file_are_genuine_misses(self) -> None:
        with mock.patch(
            "ref_enthalpy_method.mapping.fluent_projection.project_fluent_surface_exact",
            wraps=project_fluent_surface_exact,
        ) as projector:
            no_path = self._call(cache_path=None)
            missing = self._call(cache_path=self.cache_path, write_cache=False)
        self.assertEqual(projector.call_count, 2)
        self.assertFalse(self.cache_path.exists())
        self.assertIsInstance(no_path, FluentSurfaceProjection)
        self.assertIsInstance(missing, FluentSurfaceProjection)

    def test_valid_hit_skips_projector_and_use_bvh_does_not_matter(self) -> None:
        expected = self._create_valid_cache()
        with mock.patch(
            "ref_enthalpy_method.mapping.fluent_projection.project_fluent_surface_exact",
            side_effect=AssertionError("cache hit must not project"),
        ):
            brute_flag = self._call(cache_path=self.cache_path, use_bvh=False)
            bvh_flag = self._call(cache_path=self.cache_path, use_bvh=True)
        for actual in (brute_flag, bvh_flag):
            self.assertIsInstance(actual, FluentSurfaceProjection)
            for field in (
                "canonical_index", "solver_xyz", "projected_xyz", "triangle_id",
                "projection_distance_m", "raw_normal", "projection_gate_pass",
            ):
                np.testing.assert_array_equal(
                    getattr(actual, field), getattr(expected, field)
                )

    def test_identity_mismatches_fail_closed(self) -> None:
        self._create_valid_cache()
        changed_geometry_path = self.root / "changed_geometry.csv"
        self._write_geometry(
            changed_geometry_path,
            temperatures=(300.0, 400.0),
            geometry_delta=np.spacing(0.17),
        )
        changed_geometry = read_fluent_surface_geometry_csv(
            changed_geometry_path, x_offset_m=0.030
        )
        with self.assertRaises(CacheIdentityMismatchError):
            self._call(geometry=changed_geometry, cache_path=self.cache_path)
        with self.assertRaises(CacheIdentityMismatchError):
            self._call(cache_path=self.cache_path, gate=0.006)

        for key in ("cache_schema_version", "algorithm_version"):
            with self.subTest(key=key):
                self._tamper_manifest(key, "v0")
                with self.assertRaises(CacheIdentityMismatchError):
                    self._call(cache_path=self.cache_path)
                self.cache_path.unlink()
                self._create_valid_cache()

        self.stl_path.write_text("solid changed\nendsolid changed\n", encoding="utf-8")
        with self.assertRaises(CacheIdentityMismatchError):
            self._call(cache_path=self.cache_path)

    def test_truncated_corrupt_hash_nonfinite_and_bounds_fail_closed(self) -> None:
        self._create_valid_cache()
        valid_bytes = self.cache_path.read_bytes()

        self.cache_path.write_bytes(valid_bytes[:50])
        with self.assertRaises(CacheIntegrityError):
            self._call(cache_path=self.cache_path)

        self.cache_path.write_bytes(valid_bytes)
        data = self._read_npz()
        data["projected_xyz"][0, 0] += 1.0
        self._rewrite_npz(data)
        with self.assertRaises(CacheIntegrityError):
            self._call(cache_path=self.cache_path)

        self.cache_path.write_bytes(valid_bytes)
        data = self._read_npz()
        data["projected_xyz"][0, 0] = np.nan
        manifest = json.loads(bytes(data["manifest_json"]).decode("utf-8"))
        manifest["projected_xyz_sha256"] = _sha256_ndarray(data["projected_xyz"])
        data["manifest_json"] = np.asarray(
            json.dumps(manifest, sort_keys=True).encode("utf-8")
        )
        self._rewrite_npz(data)
        with self.assertRaises(CacheIntegrityError):
            self._call(cache_path=self.cache_path)

        self.cache_path.write_bytes(valid_bytes)
        data = self._read_npz()
        data["triangle_id"][0] = self.triangles.shape[0]
        manifest = json.loads(bytes(data["manifest_json"]).decode("utf-8"))
        manifest["triangle_id_sha256"] = _sha256_ndarray(data["triangle_id"])
        data["manifest_json"] = np.asarray(
            json.dumps(manifest, sort_keys=True).encode("utf-8")
        )
        self._rewrite_npz(data)
        with self.assertRaises(CacheIntegrityError):
            self._call(cache_path=self.cache_path)

    def test_write_policy_and_corrupt_existing_cache_never_overwrites(self) -> None:
        self._call(cache_path=self.cache_path, write_cache=False)
        self.assertFalse(self.cache_path.exists())
        self._call(cache_path=self.cache_path, write_cache=True)
        self.assertTrue(self.cache_path.is_file())

        self.cache_path.write_bytes(b"corrupt-cache")
        corrupt_bytes = self.cache_path.read_bytes()
        with self.assertRaises(CacheIntegrityError):
            self._call(cache_path=self.cache_path, write_cache=True)
        self.assertEqual(self.cache_path.read_bytes(), corrupt_bytes)

    def test_temperature_only_change_hits_but_geometry_bit_change_rejects(self) -> None:
        self._create_valid_cache()
        temperature_path = self.root / "temperature_only.csv"
        self._write_geometry(temperature_path, temperatures=(900.0, 1100.0))
        temperature_geometry = read_fluent_surface_geometry_csv(
            temperature_path, x_offset_m=0.030
        )
        with mock.patch(
            "ref_enthalpy_method.mapping.fluent_projection.project_fluent_surface_exact",
            side_effect=AssertionError("temperature-only change must hit cache"),
        ):
            hit = self._call(
                geometry=temperature_geometry, cache_path=self.cache_path
            )
        self.assertIsInstance(hit, FluentSurfaceProjection)

        changed_path = self.root / "geometry_bit_change.csv"
        self._write_geometry(
            changed_path,
            temperatures=(900.0, 1100.0),
            geometry_delta=np.spacing(0.17),
        )
        changed_geometry = read_fluent_surface_geometry_csv(
            changed_path, x_offset_m=0.030
        )
        with self.assertRaises(CacheIdentityMismatchError):
            self._call(geometry=changed_geometry, cache_path=self.cache_path)


if __name__ == "__main__":
    unittest.main()