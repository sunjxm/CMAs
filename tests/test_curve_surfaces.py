import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from cma_curve.curve_projection import convergence_decay, convergence_options, project_par_curve
from cma_curve.curve_surfaces import select_starting_curve, surface_arrays, render_surfaces, scenario_yield_range
from cma_curve.foreign_cash import project_foreign_cash


class HybridCurveTests(unittest.TestCase):
    def start(self):
        return pd.DataFrame({'key': ['short', 'long'], 'maturity_years': [2., 10.],
            'date': pd.to_datetime(['2023-06-30'] * 2), 'curve_type': ['par'] * 2,
            'verified': [True] * 2, 'rate_decimal': [.05, .03]})

    def anchors(self):
        return pd.DataFrame({'candidate': ['selected'] * 2, 'key': ['short', 'long'],
            'maturity_years': [2., 10.], 'curve_type': ['par'] * 2, 'anchor_decimal': [.03, .04]})

    def test_exact_terminal_and_post_terminal_all_half_lives(self):
        for half in (3, 5, 10):
            paths = project_par_curve(self.start(), self.anchors(), 'selected', [0, 25, 27.5, 30, 40], half, 25, 30)
            initial = paths[paths.horizon_years == 0].set_index('key').rate_decimal
            np.testing.assert_array_equal(initial.reindex(['short', 'long']), [.05, .03])
            for horizon in (30, 40):
                terminal = paths[paths.horizon_years == horizon]
                np.testing.assert_array_equal(terminal.rate_decimal, terminal.anchor_decimal)
            mid = paths[paths.horizon_years == 27.5].set_index('key').rate_decimal
            at25 = paths[paths.horizon_years == 25].set_index('key').rate_decimal
            np.testing.assert_allclose(mid.reindex(['short', 'long']), (at25.reindex(['short', 'long']) + [.03, .04]) / 2)

    def test_handoff_continuity_and_initial_half_life(self):
        for half in (3, 5, 10):
            decay = convergence_decay([0, half, 25 - 1e-7, 25, 25 + 1e-7, 30, 40], half, 25, 30)
            self.assertEqual(decay[0], 1)
            self.assertEqual(decay[1], .5)
            self.assertAlmostEqual(decay[2], decay[3], places=8)
            self.assertAlmostEqual(decay[4], decay[3], places=8)
            self.assertEqual(decay[5], 0); self.assertEqual(decay[6], 0)

    def test_no_overshoot_monotonic_gap_decay(self):
        for half in (3, 5, 10):
            decay = convergence_decay(np.arange(481) / 12, half, 25, 30)
            self.assertTrue((np.diff(decay) <= 0).all())
            self.assertTrue(((decay >= 0) & (decay <= 1)).all())

    def test_invalid_handoff_config_and_legacy_compatibility(self):
        for start, end in [(25, None), (None, 30), (30, 25), (0, 30), (25, np.inf)]:
            with self.assertRaises(ValueError):
                convergence_decay([0, 1], 5, start, end)
        with self.assertRaises(ValueError):
            convergence_options({'convergence_method': 'exponential_then_linear', 'linear_start_year': 25,
                                 'anchor_year': 30, 'horizon_years': 20})
        self.assertEqual(convergence_options({}), {})
        np.testing.assert_allclose(convergence_decay([0, 5, 30], 5), [1, .5, 1 / 64])

    def test_historical_exact_date_missing_node_unverified(self):
        data = self.start()
        self.assertEqual(len(select_starting_curve(data, '2023-06-30', ['short', 'long'])), 2)
        with self.assertRaises(ValueError):
            select_starting_curve(data, '2023-06-29', ['short', 'long'])
        with self.assertRaises(ValueError):
            select_starting_curve(data.iloc[:1], '2023-06-30', ['short', 'long'])
        with self.assertRaises(ValueError):
            select_starting_curve(data.assign(verified=False), '2023-06-30', ['short', 'long'])

    def test_display_interpolation_preserves_modeled_nodes(self):
        paths = project_par_curve(self.start(), self.anchors(), 'selected', [0, 25, 30], 10, 25, 30)
        x, y, z = surface_arrays(paths, 20)
        np.testing.assert_array_equal(y, [0, 25, 30])
        np.testing.assert_array_equal(z[0, [np.where(x == m)[0][0] for m in (2, 10)]], [5, 3])
        np.testing.assert_array_equal(z[-1, [np.where(x == m)[0][0] for m in (2, 10)]], [3, 4])
        with self.assertRaises(ValueError):
            surface_arrays(paths.iloc[1:])

    def test_shared_cash_convergence_stays_aligned_after_terminal(self):
        h = np.arange(481) / 12
        usd = pd.DataFrame({'scenario': 'base', 'horizon_years': h, 'half_life_years': 10,
                            'anchor_decimal': .03, 'rate_decimal': .03 + .01 * convergence_decay(h, 10, 25, 30)})
        assumptions = pd.DataFrame({'bucket': ['Other'], 'weight_decimal': [1.], 'current_cash_decimal': [.01],
                                    'inflation_anchor_decimal': [.02], 'real_cash_adjustment_bps': [0.]})
        paths, detail = project_foreign_cash(usd, assumptions, .02, linear_start_year=25, anchor_year=30)
        terminal = paths[paths.horizon_years >= 30]
        np.testing.assert_allclose(terminal.foreign_cash_decimal, terminal.usd_cash_decimal, rtol=0, atol=1e-15)
        np.testing.assert_allclose(terminal.hedge_carry_annual_decimal, np.zeros(len(terminal)), rtol=0, atol=1e-15)

    def test_interactive_mesh_and_scenario_updates(self):
        import matplotlib.pyplot  # Initialize pyplot before mocking its Figure.savefig wrapper.
        curves = pd.concat([project_par_curve(self.start(), self.anchors(), 'selected', [0, 25, 30], half, 25, 30)
                            .assign(starting_scenario='current') for half in (3, 5, 10)], ignore_index=True)
        other = curves.assign(starting_scenario='other', yield_percent=curves.yield_percent + 2)
        all_curves = pd.concat([curves, other], ignore_index=True)
        captured = []
        def capture(figure, *args, **kwargs):
            captured.append(figure.to_plotly_json())
        with tempfile.TemporaryDirectory() as folder, patch('matplotlib.figure.Figure.savefig'), \
                patch('plotly.graph_objects.Figure.write_html', new=capture):
            render_surfaces(all_curves, [{'id': 'current', 'date': '2023-06-30', 'label': 'Test'},
                                        {'id': 'other', 'date': '2020-07-31', 'label': 'Other test'}],
                            [3, 5, 10], Path(folder), 25, 30)
        figure = captured[0]
        self.assertEqual(len(figure['data']), 3)
        for trace in figure['data']:
            self.assertEqual(trace['cmin'], float(curves.yield_percent.min()))
            self.assertEqual(trace['cmax'], float(curves.yield_percent.max()))
            self.assertFalse(trace['cauto'])
            for axis in ('x', 'y'):
                self.assertTrue(trace['contours'][axis]['show'])
                self.assertEqual(trace['contours'][axis]['size'], 2)
        menus = figure['layout']['updatemenus']
        self.assertEqual(len(menus), 2)
        self.assertEqual(len(menus[0]['buttons'][0]['args'][0]['z']), 3)
        self.assertNotIn('contours', menus[0]['buttons'][0]['args'][0])
        self.assertEqual(menus[0]['buttons'][1]['args'][0]['cmin'], [float(other.yield_percent.min())] * 3)
        self.assertEqual(menus[0]['buttons'][1]['args'][0]['cmax'], [float(other.yield_percent.max())] * 3)
        self.assertEqual(menus[0]['buttons'][1]['args'][0]['cauto'], [False] * 3)
        self.assertEqual(menus[1]['buttons'][1]['args'][0],
                         {'contours.x.show': False, 'contours.y.show': False})
        expected_range = scenario_yield_range(curves.yield_percent)
        for scene in ('scene', 'scene2', 'scene3'):
            self.assertEqual(figure['layout'][scene]['zaxis']['range'], expected_range)
            self.assertEqual(menus[0]['buttons'][0]['args'][1][f'{scene}.zaxis.range'], expected_range)

    def test_tight_yield_limits_padding_flat_negative_and_invalid_values(self):
        limits = scenario_yield_range([3.1881, 5.64])
        np.testing.assert_allclose(limits, [3., 5.8])
        self.assertGreater(limits[0], 0)
        for values in ([4., 4.], [-.5, .25], [.09, 4.8]):
            low, high = scenario_yield_range(values)
            self.assertLess(low, min(values))
            self.assertGreater(high, max(values))
        for values in ([], [np.nan], [np.inf]):
            with self.assertRaises(ValueError):
                scenario_yield_range(values)


if __name__ == '__main__':
    unittest.main()
