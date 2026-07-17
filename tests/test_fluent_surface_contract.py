from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np

from ref_enthalpy_method.mapping.fluent_surface import (
    compare_canonical_geometry,
    read_fluent_surface_geometry_csv,
    transform_fluent_xyz_to_solver,
)


_HEADER = "cellnumber,x-coordinate,y-coordinate,z-coordinate,wall-temperature\n"
_ROWS = (
    "7,1.0,-2.0,3.0,900\n",
    "7,-4.0,5.0,-6.0,901\n",
    "9,0.25,-0.5,0.75,902\n",
)


class FluentSurfaceContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_csv(self, name: str, text: str) -> Path:
        path = self.root / name
        path.write_bytes(text.encode("utf-8"))
        return path

    def load(self, text: str = _HEADER + "".join(_ROWS)):
        return read_fluent_surface_geometry_csv(
            self.write_csv("surface.csv", text), x_offset_m=0.030
        )

    def test_required_fields_and_explicit_coordinate_contract(self) -> None:
        geometry = self.load()
        np.testing.assert_array_equal(geometry.source_row_index, [0, 1, 2])
        np.testing.assert_array_equal(geometry.cellnumber, ["7", "7", "9"])
        np.testing.assert_array_equal(
            geometry.raw_xyz,
            [[1.0, -2.0, 3.0], [-4.0, 5.0, -6.0], [0.25, -0.5, 0.75]],
        )
        np.testing.assert_array_equal(
            geometry.solver_xyz,
            [[1.03, -2.0, 3.0], [-3.97, 5.0, -6.0], [0.28, -0.5, 0.75]],
        )
        self.assertEqual(geometry.solver_xyz[0, 1], -2.0)
        self.assertEqual(geometry.solver_xyz[0, 2], 3.0)
        self.assertNotEqual(geometry.solver_xyz[0, 1], 3.0)
        self.assertNotEqual(geometry.solver_xyz[0, 2], -2.0)
        self.assertEqual(geometry.solver_xyz[2, 1], -0.5)
        self.assertEqual(geometry.solver_xyz[0, 0], 1.03)

    def test_header_normalization_is_limited_and_explicit(self) -> None:
        geometry = self.load(
            " CellNumber , X-Coordinate , Y-COORDINATE , z-coordinate \n"
            "4,1,2,3\n"
        )
        np.testing.assert_array_equal(geometry.raw_xyz, [[1.0, 2.0, 3.0]])

    def test_row_order_independent_canonical_identity_and_round_trip(self) -> None:
        first = self.load(_HEADER + "".join(_ROWS))
        second_path = self.write_csv("reordered.csv", _HEADER + "".join(reversed(_ROWS)))
        second = read_fluent_surface_geometry_csv(second_path, x_offset_m=0.030)
        comparison = compare_canonical_geometry(first, second)
        self.assertTrue(comparison.equal)
        self.assertEqual(comparison.maximum_absolute_coordinate_difference, 0.0)
        self.assertEqual(
            first.canonical_solver_xyz.tobytes(order="C"),
            second.canonical_solver_xyz.tobytes(order="C"),
        )
        for geometry in (first, second):
            expected = np.arange(geometry.raw_xyz.shape[0])
            np.testing.assert_array_equal(
                geometry.canonical_to_source_row[geometry.source_to_canonical_row], expected
            )
            np.testing.assert_array_equal(
                geometry.source_to_canonical_row[geometry.canonical_to_source_row], expected
            )
            np.testing.assert_array_equal(geometry.canonical_index, expected)

    def test_duplicate_cellnumber_is_allowed_but_not_identity(self) -> None:
        geometry = self.load()
        self.assertEqual(geometry.cellnumber[0], geometry.cellnumber[1])
        self.assertNotEqual(
            geometry.source_to_canonical_row[0], geometry.source_to_canonical_row[1]
        )

    def test_duplicate_coordinate_triples_fail_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate geometry coordinates"):
            self.load(_HEADER + "1,1,2,3,4\n2,1,2,3,5\n")

    def test_missing_required_column_has_no_numeric_fallback(self) -> None:
        with self.assertRaisesRegex(ValueError, "z-coordinate"):
            self.load("cellnumber,x-coordinate,y-coordinate,other\n1,2,3,4\n")

    def test_duplicate_normalized_header_fails_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate CSV header"):
            self.load("cellnumber,x-coordinate, X-COORDINATE ,y-coordinate,z-coordinate\n1,2,3,4,5\n")

    def test_empty_file_header_only_and_blank_data_row_fail(self) -> None:
        cases = (
            ("", "empty"),
            (_HEADER, "no data rows"),
            (_HEADER + "\n", "empty data row"),
        )
        for text, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self.load(text)

    def test_invalid_coordinates_fail(self) -> None:
        cases = (
            ("nan", "non-finite"),
            ("inf", "non-finite"),
            ("not-a-number", "non-numeric"),
        )
        for value, message in cases:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, message):
                    self.load(_HEADER + f"1,{value},2,3,4\n")

    def test_nonfinite_offset_and_invalid_transform_inputs_fail(self) -> None:
        raw = np.zeros((2, 3), dtype=np.float64)
        for offset in (np.nan, np.inf, -np.inf, "invalid"):
            with self.subTest(offset=offset):
                with self.assertRaisesRegex(ValueError, "x_offset_m"):
                    transform_fluent_xyz_to_solver(raw, x_offset_m=offset)
        with self.assertRaisesRegex(ValueError, "shape"):
            transform_fluent_xyz_to_solver(np.zeros(3), x_offset_m=0.03)
        with self.assertRaisesRegex(ValueError, "finite coordinates"):
            transform_fluent_xyz_to_solver(np.array([[0.0, np.nan, 0.0]]), x_offset_m=0.03)

    def test_transform_does_not_modify_or_share_input(self) -> None:
        raw = np.array([[1.0, -2.0, 3.0]], dtype=np.float64)
        original = raw.copy()
        original_bytes = raw.tobytes()
        transformed = transform_fluent_xyz_to_solver(raw, x_offset_m=0.03)
        transformed[0, 0] = 99.0
        np.testing.assert_array_equal(raw, original)
        self.assertEqual(raw.tobytes(), original_bytes)

    def test_result_arrays_are_owned_read_only_snapshots(self) -> None:
        geometry = self.load()
        for value in (
            geometry.source_row_index,
            geometry.cellnumber,
            geometry.raw_xyz,
            geometry.solver_xyz,
            geometry.canonical_index,
            geometry.canonical_to_source_row,
            geometry.source_to_canonical_row,
            geometry.canonical_solver_xyz,
        ):
            self.assertTrue(value.flags.c_contiguous)
            self.assertFalse(value.flags.writeable)
            self.assertTrue(value.flags.owndata)

    def test_repeated_runs_are_deterministic(self) -> None:
        path = self.write_csv("repeat.csv", _HEADER + "".join(_ROWS))
        first = read_fluent_surface_geometry_csv(path, x_offset_m=0.030)
        second = read_fluent_surface_geometry_csv(path, x_offset_m=0.030)
        for name in (
            "source_row_index",
            "cellnumber",
            "raw_xyz",
            "solver_xyz",
            "canonical_index",
            "canonical_to_source_row",
            "source_to_canonical_row",
        ):
            left = getattr(first, name)
            right = getattr(second, name)
            np.testing.assert_array_equal(left, right)
            self.assertEqual(left.tobytes(order="C"), right.tobytes(order="C"))

    def test_source_sha256_matches_exact_file_bytes(self) -> None:
        path = self.write_csv("hash.csv", _HEADER + "".join(_ROWS))
        geometry = read_fluent_surface_geometry_csv(path, x_offset_m=0.030)
        self.assertEqual(geometry.source_path, path.resolve())
        self.assertEqual(geometry.source_sha256, hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
