import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import pandas as pd
from cma_curve.analysis import sha256
from cma_curve.workbook_inputs import SCHEMAS, read_breakdowns, review_breakdowns, run_workbook_inputs


class Sheet:
    def __init__(self, rows):
        self.rows = rows
        self.max_row = len(rows)

    def cell(self, row, col):
        value = self.rows[row - 1][col - 1]
        return SimpleNamespace(value=value, coordinate=f'{chr(64 + col)}{row}', column=col,
                               number_format='General', data_type='n')


class Book(dict):
    @property
    def sheetnames(self):
        return list(self)

    def close(self):
        pass


def fixture():
    rows = {
        'LBUSTRUU_Sector': [('Treasury', 70), ('Banking', 30)],
        'LBUSTRUU_Rating': [('NR', 70), ('BBB', 30)],
        'LG38TRUH_Currency': [('EUR', 99.85), ('Unclassified', .15), ('ITL', 0)],
        'LG38TRUH_Local_Yield_Duration': [('ITL', 5, 4.56), ('EUR', 6, '\u2014')],
    }
    return Book({name: Sheet([headers, *rows[name]]) for name, (_, _, headers) in SCHEMAS.items()})


class WorkbookInputTests(unittest.TestCase):
    def read(self, book=None):
        with patch('openpyxl.load_workbook', return_value=book or fixture()):
            return read_breakdowns('unused.xlsx')

    def test_units_missing_provenance_and_currency_join(self):
        data = self.read()
        eur = data[(data.category == 'EUR') & (data.metric == 'weight')].iloc[0]
        self.assertAlmostEqual(eur.normalized_value, .9985)
        self.assertEqual(eur.value_cell, 'B2')
        coverage, currencies = review_breakdowns(data)
        self.assertTrue(coverage.total_within_rounding_tolerance.all())
        self.assertTrue(coverage.full_portfolio_loss_decimal.isna().all())
        self.assertEqual(currencies.set_index('currency').loc['EUR', 'duration'], 6)
        self.assertEqual(currencies.loc[currencies.yield_available_on_positive_weight, 'weight_decimal'].sum(), 0)
        self.assertTrue(currencies.set_index('currency').loc['Unclassified', ['duration', 'local_yield']].isna().all())

    def test_duplicate_missing_headers_invalid_number_rejected(self):
        for mutate in (
            lambda b: b['LG38TRUH_Currency'].rows.__setitem__(2, ('EUR', .15)),
            lambda b: b['LG38TRUH_Currency'].rows.__setitem__(0, ('Currency', 'Weight')),
            lambda b: b['LG38TRUH_Currency'].rows.__setitem__(1, ('EUR', -2)),
            lambda b: b['LG38TRUH_Currency'].rows.__setitem__(1, ('EUR', '#VALUE!')),
        ):
            book = fixture(); mutate(book)
            with self.assertRaises(ValueError):
                self.read(book)

    def test_rounding_is_recorded_not_rescaled(self):
        book = fixture()
        book['LG38TRUH_Currency'].rows[1] = ('EUR', 99.84)
        coverage, currencies = review_breakdowns(self.read(book))
        self.assertAlmostEqual(currencies.weight_decimal.sum(), .9999)
        row = coverage[coverage.breakdown == 'currency'].iloc[0]
        self.assertAlmostEqual(row.weight_gap_decimal, .0001)
        self.assertTrue(row.total_within_rounding_tolerance)
        book['LG38TRUH_Currency'].rows[1] = ('EUR', 80)
        coverage, _ = review_breakdowns(self.read(book))
        self.assertFalse(coverage[coverage.breakdown == 'currency'].total_within_rounding_tolerance.iloc[0])

    def test_missing_formula_cache_is_not_zero(self):
        values = fixture(); raw = fixture()
        values['LG38TRUH_Local_Yield_Duration'].rows[2] = ('EUR', 6, None)
        original = raw['LG38TRUH_Local_Yield_Duration'].cell
        def cell(row, col):
            result = original(row, col)
            if (row, col) == (3, 3):
                result.data_type = 'f'; result.value = '=BDP("ticker","field")'
            return result
        raw['LG38TRUH_Local_Yield_Duration'].cell = cell
        with patch('openpyxl.load_workbook', side_effect=[values, raw]):
            data = read_breakdowns('unused.xlsx')
        self.assertTrue((data.status == 'formula_cache_missing').any())
        self.assertTrue(data.loc[data.status == 'formula_cache_missing', 'normalized_value'].isna().all())

    def test_source_preserved_unknown_date_and_output_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'input.xlsx'
            source.write_bytes(b'unit test placeholder; reader mocked')
            before = sha256(source)
            with patch('openpyxl.load_workbook', return_value=fixture()):
                folder = run_workbook_inputs(tmp, source, progress=None)
            info = json.loads((folder / 'manifest.json').read_text())
            self.assertIsNone(info['asof_date'])
            self.assertFalse(info['point_in_time_eligible'])
            self.assertFalse(info['weights_rescaled'])
            self.assertEqual(sha256(source), before)
            for name, digest in info['output_sha256'].items():
                self.assertEqual(sha256(folder / name), digest)
            cash = pd.read_csv(folder / 'currency_cash_review_template.csv')
            self.assertTrue(cash.foreign_cash_decimal.isna().all())
            self.assertNotIn('ITL', cash.currency.tolist())


if __name__ == '__main__':
    unittest.main()
