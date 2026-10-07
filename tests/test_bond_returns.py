import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd

from cma_curve.bond_returns import (project_sleeve, summarize_paths, historical_diagnostic,
                                    analytics_months, load_return_settings, checked_source, diagnostic_years, COMPONENTS,
                                    run_bond_returns)
from cma_curve.analysis import sha256


class BondReturnTests(unittest.TestCase):
    def endpoint(self):
        return pd.Series({'yield': .06, 'rate_duration': 2, 'spread_duration': 1.5, 'oas': .01})

    def curve(self, start=.04, end=.04, months=12):
        return pd.DataFrame({'key': 'BC_2YEAR', 'curve_type': 'par',
                             'horizon_years': np.arange(months + 1) / 12,
                             'rate_decimal': np.linspace(start, end, months + 1)})

    def project(self, **kwargs):
        return project_sleeve(kwargs.pop('curve', self.curve()), {'BC_2YEAR': 1},
                              self.endpoint(), kwargs.pop('spread', .01), 5, kwargs.pop('loss', 0))

    def test_flat_carry_spread_not_double_counted(self):
        path = self.project()
        np.testing.assert_allclose(path.monthly_return, .06 / 12)
        np.testing.assert_allclose(path.yield_basis_residual, .01)
        self.assertAlmostEqual(path.wealth_index.iloc[-1], (1 + .06 / 12) ** 12)

    def test_rising_rates_reduce_returns(self):
        path = self.project(curve=self.curve(.04, .05))
        self.assertAlmostEqual(path.rate_effect.sum(), -.02)
        self.assertGreater(path.ending_yield_proxy.iloc[-1], path.starting_yield_proxy.iloc[0])

    def test_falling_rates_raise_price(self):
        self.assertGreater(self.project(curve=self.curve(.04, .03)).rate_effect.sum(), 0)

    def test_spread_convergence_and_loss_once(self):
        path = self.project(spread=.02, loss=25)
        self.assertLess(path.spread_effect.sum(), 0)
        self.assertAlmostEqual(path.credit_loss_effect.sum(), -.0025)
        np.testing.assert_allclose(path.monthly_return,
                                   path[['carry_proxy', 'rate_effect', 'spread_effect', 'credit_loss_effect']].sum(axis=1))

    def test_compounding_and_horizon_limit(self):
        path = self.project()
        path['key'], path['rate_scenario'], path['return_case'] = 'test', 'base', 'gross'
        annual, cumulative = summarize_paths(path, [1])
        self.assertAlmostEqual(annual.annual_return.iloc[0], (1 + .005) ** 12 - 1)
        self.assertAlmostEqual(cumulative.annualized_return.iloc[0], annual.annual_return.iloc[0])
        self.assertAlmostEqual(sum(annual[c + '_compounded_contribution'].iloc[0] for c in COMPONENTS),
                               annual.annual_return.iloc[0])
        with self.assertRaisesRegex(ValueError, 'horizon'):
            summarize_paths(path, [2])

    def test_projection_missing_month_and_node_rejected(self):
        with self.assertRaisesRegex(ValueError, 'monthly grid'):
            self.project(curve=self.curve().drop(index=3))
        frame = self.curve()
        frame['key'] = 'other'
        with self.assertRaisesRegex(ValueError, 'missing rate node'):
            self.project(curve=frame)

    def test_nonfinite_projection_rejected(self):
        curve = self.curve()
        curve.loc[3, 'rate_decimal'] = np.nan
        with self.assertRaisesRegex(ValueError, 'Nonfinite'):
            self.project(curve=curve)

    def fixture_history(self):
        months = pd.period_range('2020-01', periods=30, freq='M')
        rows = []
        for month in months:
            for metric, value, units, normalized in [('yield', 6, 'percent', .06),
                                                     ('oas', 100, 'basis_points', .01),
                                                     ('rate_duration', 2, 'years', 2),
                                                     ('spread_duration', 1.5, 'years', 1.5)]:
                rows.append({'date': month.to_timestamp('M'), 'key': 'test', 'metric': metric,
                             'value': value, 'units': units, 'normalized_value': normalized,
                             'definition_verified': True})
        treasury = pd.DataFrame({'date': months.to_timestamp('M'), 'key': 'BC_2YEAR',
                                 'curve_type': 'par', 'verified': True, 'rate_decimal': .04})
        returns = pd.DataFrame({'date': months.to_timestamp('M'), 'key': 'test',
                                'monthly_total_return_decimal': .005})
        return pd.DataFrame(rows), treasury, returns

    def test_historical_beginning_period_and_gap(self):
        analytics, treasury, returns = self.fixture_history()
        analytics = analytics[analytics.date != pd.Timestamp('2020-06-30')]
        detail, metric = historical_diagnostic(analytics, treasury, returns, 'test', {'BC_2YEAR': 1})
        self.assertEqual(metric['months'], 27)
        self.assertNotIn('2020-07', detail.month.tolist())
        np.testing.assert_allclose(detail.residual, 0, atol=1e-12)

    def test_lagged_carry_not_end_period_yield(self):
        analytics, treasury, returns = self.fixture_history()
        analytics.loc[(analytics.date == pd.Timestamp('2020-02-29')) & (analytics.metric == 'yield'),
                      ['value', 'normalized_value']] = [12, .12]
        detail, _ = historical_diagnostic(analytics, treasury, returns, 'test', {'BC_2YEAR': 1})
        self.assertAlmostEqual(detail[detail.month == '2020-02'].carry_proxy.iloc[0], .005)
        self.assertAlmostEqual(detail[detail.month == '2020-03'].carry_proxy.iloc[0], .01)

    def test_units_and_verification_rejected(self):
        analytics, _, _ = self.fixture_history()
        analytics.loc[0, 'units'] = 'basis_points'
        with self.assertRaisesRegex(ValueError, 'units'):
            analytics_months(analytics, 'test')
        analytics.loc[0, 'definition_verified'] = False
        with self.assertRaisesRegex(ValueError, 'unverified'):
            analytics_months(analytics, 'test')

    def test_duplicate_month_rejected(self):
        analytics, _, _ = self.fixture_history()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            analytics_months(pd.concat([analytics, analytics.iloc[:1]]), 'test')

    def test_incomplete_calendar_year_not_compounded(self):
        analytics, treasury, returns = self.fixture_history()
        detail, _ = historical_diagnostic(analytics, treasury, returns, 'test', {'BC_2YEAR': 1})
        yearly = diagnostic_years(detail)
        self.assertTrue(yearly[yearly.year == 2020].observed_annual_return.isna().all())
        self.assertAlmostEqual(yearly[yearly.year == 2021].observed_annual_return.iloc[0], (1 + .005) ** 12 - 1)

    def test_stale_analytics_rejected(self):
        analytics, _, _ = self.fixture_history()
        analytics.loc[0, 'date'] = pd.Timestamp('2020-01-15')
        with self.assertRaisesRegex(ValueError, 'seven days'):
            analytics_months(analytics, 'test')

    def test_hash_guard(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            (path / 'observations.csv').write_text('changed')
            (path / 'manifest.json').write_text(json.dumps({'kind': 'test', 'output_sha256': {'observations.csv': 'bad'}}))
            with self.assertRaisesRegex(ValueError, 'checksum'):
                checked_source(path, 'test', ['observations.csv'])

    def test_invalid_weights_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'settings.json'
            path.write_text(json.dumps({'status': 'research_draft_not_approved', 'model': 'first_order_yield_proxy',
                                        'assets': {'short_term_bond': {'rate_node_weights': {'BC_2YEAR': .5}},
                                                   'us_aggregate': {'rate_node_weights': {'BC_5YEAR': 1}}}}))
            with self.assertRaisesRegex(ValueError, 'sum to one'):
                load_return_settings(path)

    def test_end_to_end_archive_and_changed_settings_guard(self):
        project = Path(__file__).resolve().parents[1]
        catalog = json.loads((project / 'bond_assets.json').read_text())
        config = json.loads((project / 'return_settings.json').read_text())
        config['report_horizons_years'] = [1]
        config['minimum_spread_months'] = 24
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings = root / 'return_settings.json'
            settings.write_text(json.dumps(config))
            anchor_settings, projection_settings = root / 'anchor.json', root / 'projection.json'
            anchor_settings.write_text('{}')
            projection_settings.write_text('{}')
            analytics, treasury, returns = self.fixture_history()
            treasury = pd.concat([treasury.assign(key=key) for key in ['BC_2YEAR', 'BC_5YEAR', 'BC_10YEAR']])
            treasury_folder = root / 'treasury'
            treasury_folder.mkdir()
            treasury.to_csv(treasury_folder / 'observations.csv', index=False)
            def archive(name, kind, frames, **metadata):
                folder = root / name
                folder.mkdir()
                for filename, frame in frames.items():
                    frame.to_csv(folder / filename, index=False)
                (folder / 'manifest.json').write_text(json.dumps({'kind': kind, **metadata,
                    'output_sha256': {filename: sha256(folder / filename) for filename in frames}}))
                return folder
            starting = treasury[treasury.date == treasury.date.max()]
            review = archive('review', 'anchor-review', {'starting_par_curve.csv': starting},
                             common_starting_curve_date='2022-06-30', treasury_bundle=str(treasury_folder),
                             treasury_observations_sha256=sha256(treasury_folder / 'observations.csv'))
            curves = pd.concat([self.curve().assign(key=key, scenario='base', candidate='hlw_median20')
                                for key in ['BC_2YEAR', 'BC_5YEAR', 'BC_10YEAR']])
            curve = archive('curve', 'curve-projection', {'projected_par_curves.csv': curves},
                            review_bundle=str(review), review_manifest_sha256=sha256(review / 'manifest.json'),
                            anchor_settings_sha256=sha256(anchor_settings), projection_settings_sha256=sha256(projection_settings),
                            anchor_settings={'primary_candidate': 'hlw_median20'})
            analytics = pd.concat([analytics.assign(key=key) for key in ['short_term_bond', 'us_aggregate']])
            returns = pd.concat([returns.assign(key=key) for key in ['short_term_bond', 'us_aggregate']])
            a = archive('analytics', 'asset-analytics-normalized', {'observations.csv': analytics}, asset_config=catalog)
            h = archive('history', 'asset-history', {'historical_total_returns.csv': returns}, asset_config=catalog)
            kwargs = dict(output=root, settings_path=settings, catalog_path=project / 'bond_assets.json',
                          anchor_settings=anchor_settings, projection_settings=projection_settings,
                          curve_bundle=curve, analytics_bundle=a, history_bundle=h, progress=None)
            result = run_bond_returns(**kwargs)
            manifest = json.loads((result / 'manifest.json').read_text())
            self.assertEqual(manifest['kind'], 'bond-returns')
            self.assertEqual(len(pd.read_csv(result / 'annual_return_paths.csv')), 8)
            self.assertEqual(manifest['output_sha256']['run_summary.md'], sha256(result / 'run_summary.md'))
            anchor_settings.write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError, 'settings changed'):
                run_bond_returns(**kwargs)
