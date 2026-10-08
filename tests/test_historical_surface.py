from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from cma_curve.curve_projection import project_par_curve
from cma_curve.curve_surfaces import historical_surface_grid, historical_surface_figure, render_surfaces


class HistoricalSurfaceTests(unittest.TestCase):
    def history(self):
        return pd.DataFrame({'date': pd.to_datetime(['2020-01-31'] * 3 + ['2020-03-31'] * 2),
            'maturity_years': [1., 2., 5., 1., 5.], 'rate_decimal': [.01, .02, .05, .02, .06],
            'curve_type': ['par'] * 5, 'verified': [True] * 5})

    def test_observations_and_same_date_missing_maturity_interpolation(self):
        grid, excluded = historical_surface_grid(self.history(), 5)
        self.assertTrue(excluded.empty)
        observed = grid[grid.status == 'observed']
        self.assertEqual(len(observed), 5)
        target = grid[(grid.month == '2020-03') & (grid.maturity_years == 2)].iloc[0]
        self.assertAlmostEqual(target.yield_percent, 3.)
        self.assertEqual(target.status, 'interpolated_same_date_maturity')
        self.assertEqual(target.left_maturity_years, 1)
        self.assertEqual(target.right_maturity_years, 5)
        initial = observed[observed.month == '2020-01'].sort_values('maturity_years')
        np.testing.assert_array_equal(initial.yield_percent, [1, 2, 5])

    def test_no_time_fill_and_missing_month_included(self):
        grid, _ = historical_surface_grid(self.history(), 5)
        missing = grid[grid.month == '2020-02']
        self.assertGreater(len(missing), 0)
        self.assertTrue(missing.date.isna().all())
        self.assertTrue(missing.yield_percent.isna().all())
        self.assertTrue(missing.status.eq('unavailable').all())

    def test_no_endpoint_extrapolation(self):
        history = self.history()
        history = history[~((history.date == '2020-03-31') & (history.maturity_years == 5))]
        grid, _ = historical_surface_grid(history, 5)
        end = grid[(grid.month == '2020-03') & (grid.maturity_years > 1)]
        self.assertTrue(end.yield_percent.isna().all())

    def test_earlier_monthly_quote_excluded_not_combined(self):
        early = self.history().iloc[:1].assign(date=pd.Timestamp('2020-01-15'), maturity_years=30., rate_decimal=.1)
        grid, excluded = historical_surface_grid(pd.concat([self.history(), early], ignore_index=True), 5)
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded.date.iloc[0], pd.Timestamp('2020-01-15'))
        last = grid[(grid.month == '2020-01') & (grid.maturity_years == 30)]
        self.assertTrue(last.yield_percent.isna().all())
        self.assertEqual(last.date.iloc[0], pd.Timestamp('2020-01-31'))

    def test_invalid_source_definitions_duplicates_and_nonfinite_rejected(self):
        for data in (self.history().assign(verified=False), self.history().assign(curve_type='zero'),
                     pd.concat([self.history(), self.history().iloc[:1]]),
                     self.history().assign(maturity_years=-1), self.history().assign(rate_decimal=np.inf)):
            with self.assertRaises(ValueError):
                historical_surface_grid(data)

    def test_historical_figure_hover_dates_and_gaps(self):
        grid, _ = historical_surface_grid(self.history(), 5)
        fig = historical_surface_figure(grid)
        trace = fig.data[0]
        self.assertFalse(trace.connectgaps)
        self.assertIn('customdata[0]', trace.hovertemplate)
        self.assertIn('customdata[1]', trace.hovertemplate)
        self.assertIn('Historical year', fig.layout.scene.yaxis.title.text)
        self.assertEqual(trace.customdata[0, 0, 0], '2020-01-31')
        self.assertTrue(np.isnan(np.asarray(trace.z)[1]).all())

    def test_combined_html_has_history_below_forecasts_and_one_plotly_bundle(self):
        import matplotlib.pyplot
        start = self.history().iloc[:3].rename(columns={'maturity_years': 'maturity_years'}).copy()
        start['key'] = ['one', 'two', 'five']
        anchors = pd.DataFrame({'candidate': ['selected'] * 3, 'key': ['one', 'two', 'five'],
            'maturity_years': [1., 2., 5.], 'curve_type': ['par'] * 3, 'anchor_decimal': [.03, .035, .04]})
        curves = pd.concat([project_par_curve(start, anchors, 'selected', [0, 25, 30], half, 25, 30)
                            .assign(starting_scenario='current') for half in (3, 5, 10)], ignore_index=True)
        grid, _ = historical_surface_grid(self.history(), 5)
        with tempfile.TemporaryDirectory() as folder, patch('matplotlib.figure.Figure.savefig'):
            render_surfaces(curves, [{'id': 'current', 'date': '2020-01-31', 'label': 'Test'}],
                            [3, 5, 10], Path(folder), 25, 30, historical_grid=grid)
            html = (Path(folder) / 'interactive_curve_surfaces.html').read_text(encoding='utf-8')
        self.assertLess(html.index('id="projected-surfaces"'), html.index('id="historical-yields"'))
        self.assertEqual(html.count('plotly.js v'), 1)
        self.assertIn('Historical Treasury Par Yield Curves', html)
        self.assertIn('Mesh On', html)


if __name__ == '__main__':
    unittest.main()
