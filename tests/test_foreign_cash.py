import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
from cma_curve.analysis import sha256
from cma_curve.foreign_cash import bucket_weights, validate_assumptions, project_foreign_cash, run_foreign_cash


class ForeignCashTests(unittest.TestCase):
    def weights(self):
        return pd.DataFrame({'bucket': ['EUR', 'Other'], 'weight_decimal': [.6, .4]})

    def assumptions(self):
        return pd.DataFrame({'bucket': ['EUR', 'Other'], 'current_cash_decimal': [.02, .03],
            'current_cash_asof': ['2026-09-30'] * 2, 'inflation_anchor_decimal': [.02, .025],
            'real_cash_adjustment_bps': [0, -25], 'source': ['test source'] * 2, 'note': [''] * 2,
            'weight_decimal': [.6, .4]})

    def usd(self, years=2):
        horizon = np.arange(years * 12 + 1) / 12
        return pd.DataFrame({'scenario': 'base', 'horizon_years': horizon,
            'half_life_years': 5, 'anchor_decimal': .032,
            'rate_decimal': .032 + (.04 - .032) * np.exp2(-horizon / 5)})

    def test_aud_chf_separate_and_other_explicit_residual(self):
        currencies = pd.DataFrame({'currency': ['EUR', 'AUD', 'CHF', 'JPY', 'Unclassified'],
                                   'weight_decimal': [.6, .0282, .0098, .3604, .0015]})
        weights, mapping = bucket_weights(currencies, ['EUR', 'AUD', 'CHF'])
        by = weights.set_index('bucket')
        self.assertAlmostEqual(by.loc['Other', 'weight_decimal'], .362)
        self.assertAlmostEqual(by.loc['Other', 'rounding_residual_assigned_decimal'], .0001)
        self.assertAlmostEqual(by.loc['AUD', 'weight_decimal'], .0282)
        self.assertAlmostEqual(by.weight_decimal.sum(), 1)
        self.assertEqual(mapping.set_index('currency').loc['Unclassified', 'bucket'], 'Other')

    def test_bad_weight_totals_duplicates_and_missing_major_rejected(self):
        for currencies, majors in [
            (pd.DataFrame({'currency': ['EUR', 'Other'], 'weight_decimal': [.6, .2]}), ['EUR']),
            (pd.DataFrame({'currency': ['EUR', 'EUR'], 'weight_decimal': [.6, .4]}), ['EUR']),
            (pd.DataFrame({'currency': ['EUR', 'JPY'], 'weight_decimal': [.6, .4]}), ['AUD']),
        ]:
            with self.assertRaises(ValueError):
                bucket_weights(currencies, majors)

    def test_missing_inputs_no_zero_substitution(self):
        data = self.assumptions().drop(columns='weight_decimal')
        data.loc[0, 'current_cash_decimal'] = np.nan
        ready, missing = validate_assumptions(data, self.weights(), '2026-09-30')
        self.assertIsNone(ready); self.assertEqual(missing, ['EUR'])

    def test_wrong_date_missing_bucket_and_duplicate_rejected(self):
        data = self.assumptions().drop(columns='weight_decimal')
        data.loc[0, 'current_cash_asof'] = '2026-10-07'
        with self.assertRaisesRegex(ValueError, 'date'):
            validate_assumptions(data, self.weights(), '2026-09-30')
        with self.assertRaises(ValueError):
            validate_assumptions(data.iloc[:1], self.weights(), '2026-09-30')
        with self.assertRaises(ValueError):
            validate_assumptions(pd.concat([data, data.iloc[:1]]), self.weights(), '2026-09-30')

    def test_cash_anchors_sign_sensitivity_and_basis_cost(self):
        paths, detail = project_foreign_cash(self.usd(), self.assumptions(), .022, [-50, 0, 50], 10, 5)
        base = paths[paths.anchor_case == 'base']
        start = base.iloc[0]
        self.assertAlmostEqual(start.foreign_cash_decimal, .6 * .02 + .4 * .03)
        self.assertAlmostEqual(start.hedge_carry_annual_decimal, .04 - .024 + .0005)
        self.assertAlmostEqual(start.next_month_hedge_overlay_decimal, (.04 - .024 + .0005) / 12)
        anchors = detail[detail.anchor_case == 'base'].groupby('bucket').foreign_anchor_decimal.first()
        self.assertAlmostEqual(anchors['EUR'], .03)
        self.assertAlmostEqual(anchors['Other'], .0325)
        higher = paths[paths.anchor_case == 'foreign_anchor_+50bp']
        self.assertAlmostEqual(higher.iloc[0].hedge_carry_annual_decimal, start.hedge_carry_annual_decimal)
        self.assertLess(higher.iloc[-1].hedge_carry_annual_decimal, base.iloc[-1].hedge_carry_annual_decimal)

    def test_half_life_and_negative_cash_allowed(self):
        inputs = self.assumptions(); inputs.current_cash_decimal = -.005
        paths, _ = project_foreign_cash(self.usd(5), inputs, .022)
        target = .6 * .03 + .4 * .0325
        self.assertAlmostEqual(paths.foreign_cash_decimal.iloc[0], -.005)
        self.assertAlmostEqual(paths.foreign_cash_decimal.iloc[-1], (target - .005) / 2)

    def test_grid_and_cost_validation(self):
        for usd in (self.usd().iloc[1:], self.usd().drop(index=4), self.usd().assign(half_life_years=0)):
            with self.assertRaises(ValueError):
                project_foreign_cash(usd, self.assumptions(), .022)
        with self.assertRaises(ValueError):
            project_foreign_cash(self.usd(), self.assumptions(), .022, cost_bps=-1)

    def test_ready_pipeline_period_alignment_and_existing_inputs_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review, curve, workbook = [root / n for n in ['review', 'curve', 'workbook']]
            for folder in [review, curve, workbook]:
                folder.mkdir()
            pd.DataFrame({'candidate': ['hlw_median20'], 'key': ['BC_1MONTH'],
                          'inflation_percent': [2.2], 'anchor_decimal': [.032]}).to_csv(review / 'candidate_anchors.csv', index=False)
            pd.DataFrame({'date': ['2026-09-30']}).to_csv(review / 'starting_par_curve.csv', index=False)
            def manifest(folder, kind, **extra):
                payload = {'kind': kind, 'output_sha256': {p.name: sha256(p) for p in folder.glob('*.csv')}, **extra}
                (folder / 'manifest.json').write_text(json.dumps(payload))
            manifest(review, 'anchor-review', common_starting_curve_date='2026-09-30')
            self.usd().assign(key='BC_1MONTH', candidate='hlw_median20').to_csv(curve / 'projected_par_curves.csv', index=False)
            manifest(curve, 'curve-projection', review_bundle=str(review),
                review_manifest_sha256=sha256(review / 'manifest.json'), anchor_settings={'primary_candidate': 'hlw_median20'})
            pd.DataFrame({'currency': ['EUR', 'JPY'], 'weight_decimal': [.6, .4]}).to_csv(workbook / 'currency_inputs.csv', index=False)
            manifest(workbook, 'workbook-input-review', asof_date='2026-09-30')
            config = {'status': 'research_draft_not_approved', 'weight_policy': 'major_raw_weights_other_residual',
                'major_currencies': ['EUR'], 'usd_cash_key': 'BC_1MONTH', 'assumptions_file': 'inputs/cash.csv',
                'foreign_anchor_sensitivities_bps': [0], 'basis_adjustment_bps': 0, 'implementation_cost_bps': 0}
            settings = root / 'settings.json'; settings.write_text(json.dumps(config))
            missing = run_foreign_cash(root, settings, workbook_bundle=workbook, curve_bundle=curve, progress=None)
            self.assertFalse((missing / 'monthly_hedge_overlay.csv').exists())
            input_file = root / 'inputs/cash.csv'
            self.assumptions().drop(columns='weight_decimal').to_csv(input_file, index=False)
            before = sha256(input_file)
            ready = run_foreign_cash(root, settings, workbook_bundle=workbook, curve_bundle=curve, progress=None)
            self.assertEqual(before, sha256(input_file))
            monthly = pd.read_csv(ready / 'monthly_hedge_overlay.csv')
            self.assertEqual(len(monthly), 24)
            self.assertEqual(monthly.date.iloc[0], '2026-10-31')
            self.assertAlmostEqual(monthly.usd_cash_decimal.iloc[0], .04)
            self.assertAlmostEqual(monthly.horizon_years.iloc[0], 0)
            info = json.loads((ready / 'manifest.json').read_text())
            for name, digest in info['output_sha256'].items():
                self.assertEqual(sha256(ready / name), digest)


if __name__ == '__main__':
    unittest.main()
