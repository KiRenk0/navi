from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from ref_enthalpy_method.atmosphere.ussa1976 import ussa1976
from ref_enthalpy_method.gas import make_fluent_tpg_thermo, mu_sutherland
from ref_enthalpy_method.geometry.local_incidence import (
    SURFACE_CLASS_LEEWARD,
    SURFACE_CLASS_NEAR_TANGENT,
    SURFACE_CLASS_WINDWARD,
)
from ref_enthalpy_method.geometry.projected_semantics import (
    GEOMETRIC_SHEET_LOWER,
    GEOMETRIC_SHEET_UPPER,
    classify_triangle_geometric_sheets,
)
from ref_enthalpy_method.geometry.stl_surface import SurfaceSlopeSampler
from ref_enthalpy_method.mapping.fluent_wall_temperature import (
    read_fluent_wall_temperature_source,
)
from ref_enthalpy_method.n8_taw_surface import (
    _build_comparison,
    _build_comparison_contour_mesh,
    _build_domain_conforming_product,
    _build_lf_surface_fields,
    _comparison_auto_color_limits,
    _explicit_mapping_support_radius,
    _gas_model,
    _load_geometry_inputs,
    _plot_comparison_surface,
    _structured_cell_triangles,
    _structured_mapping_support_radius,
    dispatch_taw_predictions,
    load_n8_sampling_spec,
    load_n8_taw_case_spec,
    pair_projected_physical_points,
    resolve_n8_freestream,
    run_n8_taw_case,
)
from ref_enthalpy_method.specs.loader import SpecError, load_yaml
from ref_enthalpy_method.specs.models import CaseSpec
from ref_enthalpy_method.types import GasModel


def _make_test_gas() -> GasModel:
    tpg = make_fluent_tpg_thermo(R=287.0)
    return GasModel(
        gamma=1.4,
        R=287.0,
        cp_gas=tpg.cp,
        h_from_T=tpg.h_from_T,
        T_from_h=tpg.T_from_h,
        mu=mu_sutherland,
        prandtl=0.72,
        tpg=tpg,
    )



class N8TawCaseSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]

    def test_case_specs_and_sampling_are_minimal_and_exact(self) -> None:
        expected_cases = {
            "specs/cases/n8_taw_ma6p5_a3_h30km.yaml": (
                "fluent_export/adiabatic_wall_csv/1197pa_226.509k_30km_3alpha_6.5ma.csv",
                6.5,
                3.0,
                226.509,
                1197.0,
                30.0,
            ),
            "specs/cases/n8_taw_ma6_a5_h30km.yaml": (
                "fluent_export/adiabatic_wall_csv/1197pa_226.509k_30km_5alpha_6ma.csv",
                6.0,
                5.0,
                226.509,
                1197.0,
                30.0,
            ),
            "specs/cases/n8_taw_ma8_a5_h30km.yaml": (
                "fluent_export/adiabatic_wall_csv/1197pa_226.509k_30km_5alpha_8ma.csv",
                8.0,
                5.0,
                226.509,
                1197.0,
                30.0,
            ),
            "specs/cases/n8_taw_ma8_a10_h45km.yaml": (
                "fluent_export/adiabatic_wall_csv/131pa_241.65k_45km_10alpha_8ma.csv",
                8.0,
                10.0,
                241.65,
                131.0,
                45.0,
            ),
            "specs/cases/n8_taw_ma8_a5_h45km.yaml": (
                "fluent_export/adiabatic_wall_csv/131pa_241.65k_45km_5alpha_8ma.csv",
                8.0,
                5.0,
                241.65,
                131.0,
                45.0,
            ),
            "specs/cases/n8_taw_ma9_a5_h45km.yaml": (
                "fluent_export/adiabatic_wall_csv/131pa_241.65k_45km_5alpha_9ma.csv",
                9.0,
                5.0,
                241.65,
                131.0,
                45.0,
            ),
            "specs/cases/n8_taw_ma8_a10_h40km.yaml": (
                "fluent_export/adiabatic_wall_csv/287pa_251k_40km_10alpha_8ma.csv",
                8.0,
                10.0,
                251.0,
                287.0,
                40.0,
            ),
            "specs/cases/n8_taw_ma6p5_a5_h40km.yaml": (
                "fluent_export/adiabatic_wall_csv/287pa_251k_40km_5alpha_6.5ma.csv",
                6.5,
                5.0,
                251.0,
                287.0,
                40.0,
            ),
            "specs/cases/n8_taw_ma8_a5_h40km.yaml": (
                "fluent_export/adiabatic_wall_csv/287pa_251k_40km_5alpha_8ma.csv",
                8.0,
                5.0,
                251.0,
                287.0,
                40.0,
            ),
            "specs/cases/n8_taw_ma9_a5_h40km.yaml": (
                "fluent_export/adiabatic_wall_csv/287pa_251k_40km_5alpha_9ma.csv",
                9.0,
                5.0,
                251.0,
                287.0,
                40.0,
            ),
            "specs/cases/n8_taw_ma6p5_a8_h35km.yaml": (
                "fluent_export/adiabatic_wall_csv/558.9pa_237k_35km_8alpha_6.5ma.csv",
                6.5,
                8.0,
                237.0,
                558.9,
                35.0,
            ),
            "specs/cases/n8_taw_ma9_a8_h35km.yaml": (
                "fluent_export/adiabatic_wall_csv/558.9pa_237k_35km_8alpha_9ma.csv",
                9.0,
                8.0,
                237.0,
                558.9,
                35.0,
            ),
        }
        self.assertEqual(len(expected_cases), 12)
        for spec_path, expected in expected_cases.items():
            with self.subTest(spec_path=spec_path):
                observation_csv, mach, alpha_deg, T_inf_K, p_inf_Pa, h_label_km = expected
                case = load_n8_taw_case_spec(spec_path, repo_root=self.root)
                sampling = load_n8_sampling_spec(
                    case.sampling_spec, repo_root=self.root
                )
                self.assertEqual(case.observation_csv, observation_csv)
                self.assertEqual((case.mach, case.alpha_deg), (mach, alpha_deg))
                self.assertEqual(
                    (case.T_inf_K, case.p_inf_Pa, case.h_label_km),
                    (T_inf_K, p_inf_Pa, h_label_km),
                )
                self.assertEqual((sampling.nx, sampling.ny), (81, 41))
                self.assertEqual(
                    sampling.point_order,
                    "sheet_then_y_over_b_then_x_over_c",
                )

    def test_old_thermal_responsibility_is_rejected_as_an_extra_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.yaml"
            source = (self.root / "specs/cases/n8_taw_ma6p5_a3_h30km.yaml").read_text(encoding="utf-8")
            path.write_text(source + "\nwall:\n  temperature_K: 300\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "extra=.*wall"):
                load_n8_taw_case_spec(path, repo_root=self.root)


class N8FreestreamResolutionTest(unittest.TestCase):
    def test_altitude_only_uses_ussa1976(self) -> None:
        expected = ussa1976(30_000.0, R=287.0)
        result = resolve_n8_freestream(
            h_m=30_000.0,
            T_inf_K=None,
            p_inf_Pa=None,
            R_J_per_kgK=287.0,
        )
        self.assertEqual(result.source, "ussa1976")
        self.assertTrue(result.altitude_used_for_freestream)
        self.assertEqual(result.altitude_input_m, 30_000.0)
        self.assertAlmostEqual(result.T_inf_K, expected.T)
        self.assertAlmostEqual(result.p_inf_Pa, expected.p)
        self.assertAlmostEqual(result.rho_inf_kg_m3, expected.rho)

    def test_explicit_pair_wins_even_when_altitude_is_present(self) -> None:
        result = resolve_n8_freestream(
            h_m=45_000.0,
            T_inf_K=241.65,
            p_inf_Pa=131.0,
            R_J_per_kgK=287.0,
        )
        self.assertEqual(result.source, "explicit_custom")
        self.assertFalse(result.altitude_used_for_freestream)
        self.assertEqual(result.altitude_input_m, 45_000.0)
        self.assertEqual((result.T_inf_K, result.p_inf_Pa), (241.65, 131.0))
        self.assertAlmostEqual(result.rho_inf_kg_m3, 131.0 / (287.0 * 241.65))

    def test_explicit_pair_does_not_require_altitude(self) -> None:
        result = resolve_n8_freestream(
            h_m=None,
            T_inf_K=226.509,
            p_inf_Pa=1197.0,
            R_J_per_kgK=287.0,
        )
        self.assertEqual(result.source, "explicit_custom")
        self.assertIsNone(result.altitude_input_m)

    def test_partial_pair_and_missing_source_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "provided together"):
            resolve_n8_freestream(
                h_m=30_000.0,
                T_inf_K=226.509,
                p_inf_Pa=None,
                R_J_per_kgK=287.0,
            )
        with self.assertRaisesRegex(ValueError, "provide either h_m"):
            resolve_n8_freestream(
                h_m=None,
                T_inf_K=None,
                p_inf_Pa=None,
                R_J_per_kgK=287.0,
            )

    def test_ussa_rejects_invalid_altitude_and_gas_constant(self) -> None:
        with self.assertRaisesRegex(ValueError, "altitude_m"):
            ussa1976(-1.0)
        with self.assertRaisesRegex(ValueError, "altitude_m"):
            ussa1976(float("nan"))
        with self.assertRaisesRegex(ValueError, "R must"):
            ussa1976(30_000.0, R=0.0)


class ActiveAtmosphereSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]

    def test_active_case_uses_ussa1976(self) -> None:
        raw = load_yaml(self.root / "specs/cases/doc_ma6_alpha5_h30km_faceted3d.yaml")
        case = CaseSpec.from_yaml_dict(raw)
        self.assertEqual(case.atmosphere_model, "ussa1976")

    def test_isa1976_model_is_rejected(self) -> None:
        raw = load_yaml(self.root / "specs/cases/doc_ma6_alpha5_h30km_faceted3d.yaml")
        raw["case_spec"]["atmosphere"]["model"] = "isa1976"
        with self.assertRaisesRegex(SpecError, "must be 'ussa1976'"):
            CaseSpec.from_yaml_dict(raw)


class N8FreestreamRunnerContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.runs_root = cls.root / "runs/n8_taw_surface"
        cls.runs_root.mkdir(parents=True, exist_ok=True)

    def _existing_run_dir(self, directory: str) -> str:
        return (Path("runs/n8_taw_surface") / Path(directory).name).as_posix()

    def test_custom_pair_without_altitude_reaches_runner(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="n8-custom-contract-", dir=self.runs_root
        ) as directory, self.assertRaisesRegex(ValueError, "run_dir already exists"):
            run_n8_taw_case(
                repo_root=self.root,
                case_spec_path="specs/cases/n8_taw_ma6p5_a3_h30km.yaml",
                run_dir=self._existing_run_dir(directory),
                mach=6.5,
                alpha_deg=3.0,
                T_inf_K=226.509,
                p_inf_Pa=1197.0,
            )

    def test_altitude_only_ussa_reaches_runner(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="n8-ussa-contract-", dir=self.runs_root
        ) as directory, self.assertRaisesRegex(ValueError, "run_dir already exists"):
            run_n8_taw_case(
                repo_root=self.root,
                case_spec_path="specs/cases/n8_taw_ma6p5_a3_h30km.yaml",
                run_dir=self._existing_run_dir(directory),
                mach=6.5,
                alpha_deg=3.0,
                h_m=30_000.0,
            )


class N8TawDispatchTest(unittest.TestCase):
    def test_dispatch_is_c1_and_blends_in_enthalpy_space(self) -> None:
        gas = _make_test_gas()
        epsilon = 0.05
        prediction, provider, valid, reason, weight = dispatch_taw_predictions(
            incidence_s=np.asarray([0.0, epsilon / 2.0, epsilon]),
            geometry_valid=np.asarray([True, True, True]),
            windward_taw_K=np.asarray([np.nan, 900.0, 900.0]),
            recovery_taw_K=np.asarray([800.0, 800.0, np.nan]),
            gas=gas,
            transition_epsilon=epsilon,
        )
        expected_midpoint = gas.T_from_h(
            0.5 * gas.h_from_T(800.0) + 0.5 * gas.h_from_T(900.0)
        )
        np.testing.assert_allclose(prediction, [800.0, expected_midpoint, 900.0])
        np.testing.assert_allclose(weight, [0.0, 0.5, 1.0])
        self.assertEqual(
            provider.tolist(),
            [
                "leeward_recovery",
                "near_tangent_blend",
                "windward_turbulent",
            ],
        )
        np.testing.assert_array_equal(valid, [True, True, True])
        self.assertEqual(reason.tolist(), ["", "", ""])

        near_endpoints, _, _, _, _ = dispatch_taw_predictions(
            incidence_s=np.asarray(
                [np.nextafter(0.0, 1.0), np.nextafter(epsilon, 0.0)]
            ),
            geometry_valid=np.asarray([True, True]),
            windward_taw_K=np.asarray([900.0, 900.0]),
            recovery_taw_K=np.asarray([800.0, 800.0]),
            gas=gas,
            transition_epsilon=epsilon,
        )
        np.testing.assert_allclose(near_endpoints, [800.0, 900.0], atol=1.0e-10)

    def test_dispatch_fails_closed_only_for_required_candidates(self) -> None:
        prediction, provider, valid, reason, weight = dispatch_taw_predictions(
            incidence_s=np.asarray([-0.1, 0.01, 0.06, np.nan]),
            geometry_valid=np.asarray([True, True, True, True]),
            windward_taw_K=np.asarray([np.nan, np.nan, 900.0, 900.0]),
            recovery_taw_K=np.asarray([800.0, np.nan, np.nan, 800.0]),
            gas=_make_test_gas(),
        )
        np.testing.assert_allclose(prediction[[0, 2]], [800.0, 900.0])
        self.assertTrue(np.isnan(prediction[1]))
        self.assertTrue(np.isnan(prediction[3]))
        np.testing.assert_array_equal(valid, [True, False, True, False])
        self.assertEqual(
            reason.tolist(), ["", "candidate_nonfinite", "", "invalid_incidence"]
        )
        self.assertEqual(
            provider.tolist(),
            [
                "leeward_recovery",
                "near_tangent_blend",
                "windward_turbulent",
                "typed_invalid",
            ],
        )
        self.assertEqual(weight[0], 0.0)
        self.assertEqual(weight[2], 1.0)
        self.assertTrue(np.isnan(weight[3]))



class N8StructuredConnectivityTest(unittest.TestCase):
    def test_only_triangles_touching_geometry_hole_are_not_triangulated(self) -> None:
        valid = np.ones((3, 4), dtype=np.bool_)
        valid[1, 1] = False
        triangles = _structured_cell_triangles(valid)
        self.assertEqual(triangles.shape, (6, 3))
        self.assertNotIn(5, triangles)
        for triangle in triangles:
            rows, columns = np.divmod(triangle, 4)
            self.assertLessEqual(int(np.max(rows) - np.min(rows)), 1)
            self.assertLessEqual(int(np.max(columns) - np.min(columns)), 1)

    def test_mapping_support_uses_the_same_valid_triangles(self) -> None:
        x_m = np.tile(np.arange(4, dtype=np.float64), (3, 1))
        span_m = np.tile(np.arange(3, dtype=np.float64)[:, None], (1, 4))
        valid = np.ones((3, 4), dtype=np.bool_)
        valid[1, 1] = False
        support = _structured_mapping_support_radius(
            x_m=x_m, span_m=span_m, geometry_valid=valid
        )
        self.assertTrue(np.isnan(support[1, 1]))
        self.assertEqual(support[0, 0], 0.0)
        connected = valid.copy()
        connected[0, 0] = False
        self.assertTrue(np.all(support[connected] > 0.0))
        np.testing.assert_allclose(
            support[connected], np.sqrt(2.0) / 2.0, rtol=0.0, atol=0.0
        )


class N8ComparisonContourTest(unittest.TestCase):
    def test_auto_color_limits_use_only_finite_supported_values(self) -> None:
        vmin, vmax = _comparison_auto_color_limits(
            values=np.asarray([-99.0, -3.5, 8.25, np.nan, 99.0]),
            comparison_valid=np.asarray([False, True, True, True, False]),
        )
        self.assertEqual(vmin, -3.5)
        self.assertEqual(vmax, 8.25)

    def test_auto_color_limits_pad_a_constant_field(self) -> None:
        vmin, vmax = _comparison_auto_color_limits(
            values=np.asarray([2.0, 2.0, 2.0]),
            comparison_valid=np.ones(3, dtype=np.bool_),
        )
        self.assertLess(vmin, 2.0)
        self.assertGreater(vmax, 2.0)

    def test_duplicate_supported_coordinates_are_aggregated(self) -> None:
        x, span, values, triangles, masked = _build_comparison_contour_mesh(
            x_m=np.asarray([0.0, 0.0, 1.0, 0.0]),
            span_m=np.asarray([0.0, 0.0, 0.0, 1.0]),
            values=np.asarray([1.0, 3.0, 2.0, 4.0]),
            comparison_valid=np.ones(4, dtype=np.bool_),
            mapping_support_limit_m=np.ones(4, dtype=np.float64),
        )
        self.assertEqual(x.size, 3)
        origin = (x == 0.0) & (span == 0.0)
        self.assertEqual(float(values[origin][0]), 2.0)
        self.assertEqual(triangles.shape, (1, 3))
        self.assertFalse(np.any(masked))

    def test_sparse_unsupported_samples_do_not_cut_holes_in_contour(self) -> None:
        x, _span, _values, triangles, masked = _build_comparison_contour_mesh(
            x_m=np.asarray([0.0, 1.0, 2.0, 3.0, 4.0] * 3),
            span_m=np.repeat([0.0, 1.0, 2.0], 5),
            values=np.arange(15, dtype=np.float64),
            comparison_valid=np.asarray(
                [True, True, False, True, True] * 3, dtype=np.bool_
            ),
            mapping_support_limit_m=np.ones(15, dtype=np.float64),
        )
        self.assertFalse(np.any(x == 2.0))
        self.assertFalse(np.any(masked))
        self.assertTrue(
            any(
                float(np.min(x[triangle])) < 2.0 < float(np.max(x[triangle]))
                for triangle in triangles
            )
        )

    def test_comparison_plot_writes_a_filled_contour_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comparison.png"
            _plot_comparison_surface(
                path=path,
                x_m=np.asarray([0.0, 1.0, 0.0, 1.0]),
                span_m=np.asarray([0.0, 0.0, 1.0, 1.0]),
                values=np.asarray([-1.0, 0.0, 1.0, 2.0]),
                comparison_valid=np.ones(4, dtype=np.bool_),
                mapping_support_limit_m=np.ones(4, dtype=np.float64),
                title="comparison",
                colorbar_label="error (%)",
                vmin=-2.0,
                vmax=2.0,
            )
            self.assertGreater(path.stat().st_size, 1_000)

    def test_auto_range_comparison_plot_writes_a_filled_contour_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comparison_auto_range.png"
            _plot_comparison_surface(
                path=path,
                x_m=np.asarray([0.0, 1.0, 0.0, 1.0]),
                span_m=np.asarray([0.0, 0.0, 1.0, 1.0]),
                values=np.asarray([-1.25, 0.0, 0.75, 2.5]),
                comparison_valid=np.ones(4, dtype=np.bool_),
                mapping_support_limit_m=np.ones(4, dtype=np.float64),
                title="comparison actual range",
                colorbar_label="error (%)",
                vmin=-1.25,
                vmax=2.5,
                extend="neither",
            )
            self.assertGreater(path.stat().st_size, 1_000)


class N8SourceRowPairingTest(unittest.TestCase):
    def test_many_to_one_preserves_every_source_row_and_stable_ties(self) -> None:
        pairing = pair_projected_physical_points(
            sheet="upper",
            source_canonical_index=np.asarray([8, 2, 5], dtype=np.int64),
            source_x_span_m=np.asarray([[0.9, 0.0], [0.1, 0.0], [0.5, 0.0]], dtype=np.float64),
            target_canonical_index=np.asarray([20, 10], dtype=np.int64),
            target_x_span_m=np.asarray([[1.0, 0.0], [0.0, 0.0]], dtype=np.float64),
            target_support_radius_m=np.asarray([0.6, 0.6], dtype=np.float64),
            chunk_size=2,
        )
        np.testing.assert_array_equal(pairing.source_canonical_index, [2, 5, 8])
        np.testing.assert_array_equal(pairing.target_canonical_index, [10, 10, 20])
        self.assertEqual(pairing.source_canonical_index.size, 3)
        self.assertEqual(pairing.target_pool_size, 2)
        np.testing.assert_array_equal(pairing.target_multiplicity, [2, 2, 1])
        np.testing.assert_array_equal(pairing.mapping_supported, [True, True, True])

    def test_comparison_uses_prediction_minus_observation_units(self) -> None:
        comparison, pairing = _build_comparison(
            sheet="lower",
            source_csv_sha256="a" * 64,
            source_canonical_index=np.asarray([0, 1], dtype=np.int64),
            source_row_index=np.asarray([7, 3], dtype=np.int64),
            source_surface_class=np.asarray([SURFACE_CLASS_WINDWARD, SURFACE_CLASS_LEEWARD], dtype=np.int8),
            source_wall_temperature_K=np.asarray([400.0, 500.0]),
            source_x_span_m=np.asarray([[0.0, 0.0], [1.0, 0.0]], dtype=np.float64),
            target_canonical_index=np.asarray([10, 11], dtype=np.int64),
            target_surface_class=np.asarray([SURFACE_CLASS_WINDWARD, SURFACE_CLASS_LEEWARD], dtype=np.int8),
            target_Taw_K=np.asarray([440.0, 450.0]),
            target_x_span_m=np.asarray([[0.0, 0.0], [1.0, 0.0]], dtype=np.float64),
            target_support_radius_m=np.asarray([0.25, 0.25], dtype=np.float64),
        )
        self.assertEqual(pairing.source_canonical_index.size, 2)
        np.testing.assert_allclose(comparison.signed_error_K, [40.0, -50.0])
        np.testing.assert_allclose(comparison.signed_relative_error_pct, [10.0, -10.0])
        np.testing.assert_allclose(comparison.absolute_error_K, [40.0, 50.0])

    def test_unsupported_mapping_preserves_row_and_masks_error(self) -> None:
        comparison, pairing = _build_comparison(
            sheet="upper",
            source_csv_sha256="b" * 64,
            source_canonical_index=np.asarray([3], dtype=np.int64),
            source_row_index=np.asarray([9], dtype=np.int64),
            source_surface_class=np.asarray([SURFACE_CLASS_NEAR_TANGENT], dtype=np.int8),
            source_wall_temperature_K=np.asarray([500.0]),
            source_x_span_m=np.asarray([[0.8, 0.0]], dtype=np.float64),
            target_canonical_index=np.asarray([10], dtype=np.int64),
            target_surface_class=np.asarray([SURFACE_CLASS_WINDWARD], dtype=np.int8),
            target_Taw_K=np.asarray([550.0]),
            target_x_span_m=np.asarray([[0.0, 0.0]], dtype=np.float64),
            target_support_radius_m=np.asarray([0.2], dtype=np.float64),
        )
        self.assertEqual(pairing.source_canonical_index.tolist(), [3])
        np.testing.assert_array_equal(comparison.comparison_valid, [False])
        self.assertEqual(comparison.comparison_failure_reason.tolist(), ["MAPPING_UNSUPPORTED"])
        self.assertTrue(np.isnan(comparison.Taw_prediction_K[0]))
        self.assertTrue(np.isnan(comparison.signed_relative_error_pct[0]))


class N8WallTemperaturePublicReaderTest(unittest.TestCase):
    def test_first_case_reader_is_source_order_and_read_only(self) -> None:
        root = Path(__file__).resolve().parents[1]
        values, raw_sha256 = read_fluent_wall_temperature_source(
            root / "fluent_export/adiabatic_wall_csv/1197pa_226.509k_30km_3alpha_6.5ma.csv"
        )
        self.assertEqual(values.shape, (21250,))
        self.assertEqual(len(raw_sha256), 64)
        self.assertFalse(values.flags.writeable)
        self.assertTrue(np.all(np.isfinite(values)))
        self.assertTrue(np.all(values > 0.0))


class N8GeometryDomainClosureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.case = load_n8_taw_case_spec(
            cls.root / "specs/cases/n8_taw_ma8_a10_h40km.yaml",
            repo_root=cls.root,
        )
        cls.sampling = load_n8_sampling_spec(
            cls.case.sampling_spec, repo_root=cls.root
        )
        cls.geometry = _load_geometry_inputs(cls.root, cls.case)
        cls.triangle_sheet = classify_triangle_geometric_sheets(
            cls.geometry.triangles
        )
        gas = _gas_model(cls.case)
        cls.legacy = _build_lf_surface_fields(
            case=cls.case,
            sampling=cls.sampling,
            geometry=cls.geometry,
            gas=gas,
        )
        cls.product = _build_domain_conforming_product(
            legacy_fields=cls.legacy,
            case=cls.case,
            sampling=cls.sampling,
            geometry=cls.geometry,
            gas=gas,
        )

    def test_formal_sheet_classifier_is_complete_and_requested_sheet_isolated(
        self,
    ) -> None:
        self.assertFalse(np.any(self.triangle_sheet < 0))
        legacy_triangle_sheet = classify_triangle_geometric_sheets(
            self.geometry.triangles, propagate_components=False
        )
        self.assertEqual(
            dict(zip(*np.unique(legacy_triangle_sheet, return_counts=True))),
            {
                -1: 76,
                0: 512,
                GEOMETRIC_SHEET_UPPER: 3136,
                GEOMETRIC_SHEET_LOWER: 2617,
            },
        )
        self.assertEqual(
            dict(zip(*np.unique(self.triangle_sheet, return_counts=True))),
            {
                0: 513,
                GEOMETRIC_SHEET_UPPER: 3150,
                GEOMETRIC_SHEET_LOWER: 2678,
            },
        )
        sampler = SurfaceSlopeSampler(mesh=self.geometry.mesh)
        unfiltered_upper, unfiltered_lower = (
            sampler.sample_upper_lower_with_triangle_id(
                x=2.092875772868064,
                span=0.695943225,
            )
        )
        self.assertEqual(int(unfiltered_upper[6]), 4633)
        self.assertEqual(int(unfiltered_lower[6]), 4633)
        upper, lower = sampler.sample_upper_lower_with_triangle_id(
            x=2.092875772868064,
            span=0.695943225,
            triangle_sheet=self.triangle_sheet,
        )
        self.assertIsNone(upper)
        self.assertEqual(int(lower[6]), 4633)

    def test_tip_and_legacy_exclusions_are_explicit(self) -> None:
        product = self.product
        self.assertTrue(np.all(product["y_over_b"] < 1.0))
        self.assertEqual(product["node_id"].size, 9663)
        self.assertEqual(product["triangle_id"].size, 18110)
        self.assertEqual(
            str(product["domain_topology_sha256"]),
            "1490f733d15e373ba017d503025b6bb0f4e558378e94e719e3f3a7b0c2b7acae",
        )
        reasons, counts = np.unique(
            product["excluded_geometry_failure_reason"], return_counts=True
        )
        self.assertEqual(
            dict(zip(reasons.tolist(), counts.tolist())),
            {
                "degenerate_planform_chord": 162,
                "geometric_sheet_mismatch": 1,
                "outside_stl_support": 170,
            },
        )
        direct = product["legacy_phase9_canonical_index"] >= 0
        legacy_index = product["legacy_phase9_canonical_index"][direct]
        self.assertEqual(
            np.count_nonzero(direct),
            np.count_nonzero(self.legacy["geometry_valid"]),
        )
        for key in (
            "normal_out",
            "sx",
            "sy",
            "incidence_s",
            "Taw_windward_candidate_K",
            "Taw_recovery_candidate_K",
            "Taw_prediction_K",
            "windward_blend_weight",
        ):
            np.testing.assert_array_equal(
                product[key][direct],
                self.legacy[key][legacy_index],
            )
        boundary = product["domain_role"] == "skin_boundary"
        self.assertGreater(np.count_nonzero(boundary), 0)
        self.assertTrue(np.all(product["source_stl_edge_id"][boundary] >= 0))

    def test_explicit_triangles_own_plot_and_mapping_support(self) -> None:
        product = self.product
        triangles = product["triangle_node_ids"]
        self.assertEqual(triangles.shape, (product["triangle_id"].size, 3))
        np.testing.assert_array_equal(
            np.unique(triangles), product["node_id"]
        )
        self.assertTrue(
            np.all(
                product["geometric_sheet"][triangles]
                == product["triangle_geometric_sheet"][:, None]
            )
        )
        points = np.stack(
            (
                np.column_stack(
                    (product["x_m"][triangles[:, 0]], product["span_m"][triangles[:, 0]])
                ),
                np.column_stack(
                    (product["x_m"][triangles[:, 1]], product["span_m"][triangles[:, 1]])
                ),
                np.column_stack(
                    (product["x_m"][triangles[:, 2]], product["span_m"][triangles[:, 2]])
                ),
            ),
            axis=1,
        )
        signed_twice_area = (
            (points[:, 1, 0] - points[:, 0, 0])
            * (points[:, 2, 1] - points[:, 0, 1])
            - (points[:, 1, 1] - points[:, 0, 1])
            * (points[:, 2, 0] - points[:, 0, 0])
        )
        self.assertTrue(np.all(np.abs(signed_twice_area) > 2.0e-16))
        expected_support = _explicit_mapping_support_radius(
            x_m=product["x_m"],
            span_m=product["span_m"],
            triangle_node_ids=triangles,
        )
        np.testing.assert_allclose(
            product["mapping_support_radius_m"],
            expected_support,
            rtol=0.0,
            atol=0.0,
        )
        self.assertTrue(np.all(product["geometry_valid"]))
        self.assertTrue(np.all(product["valid"]))
        self.assertTrue(np.all(np.isfinite(product["Taw_prediction_K"])))

if __name__ == "__main__":
    unittest.main()
