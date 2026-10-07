import unittest
import pandas as pd
from cma_curve.tips_inputs import SERIES, prepare_proxies


class TipsProxyTests(unittest.TestCase):
    def history(self):
        return pd.DataFrame([{'date': date, 'ticker': ticker, 'field': field, 'value': value}
                             for date in ['2026-07-31', '2026-09-30']
                             for (_, ticker, field, _), value in zip(SERIES, [-0.5, 3.5, 4.8])])

    def test_units_negative_real_yield_and_missing_month(self):
        data, coverage = prepare_proxies(self.history(), '2026-09-30')
        self.assertEqual(len(data), 6)
        self.assertEqual(coverage.observations.tolist(), [2, 2, 2])
        self.assertEqual(data[data.key == 'real_yield_proxy'].normalized_value.iloc[0], -0.005)
        self.assertEqual(data[data.key == 'real_duration_proxy'].normalized_value.iloc[0], 3.5)
        self.assertFalse(data.index_real_analytic_verified.any())

    def test_stale_rejected(self):
        with self.assertRaisesRegex(ValueError, 'stale'):
            prepare_proxies(self.history(), '2026-10-31')

    def test_duplicates_rejected(self):
        frame = self.history()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            prepare_proxies(pd.concat([frame, frame.iloc[:1]]), '2026-09-30')

    def test_missing_duration_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Missing'):
            prepare_proxies(self.history().query("field != 'INDEX_OAD_TSY'"), '2026-09-30')
