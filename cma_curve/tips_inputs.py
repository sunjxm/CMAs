"""Explicit, provisional benchmark proxies for the 1-10 year TIPS sleeve."""
import json
import numpy as np
import pandas as pd

from .analysis import sha256, markdown_table
from .data import completed_month_end, monthly_sample, save_bundle

SERIES = (
    ('real_yield_proxy', 'USGGT05Y Index', 'PX_LAST', 'percent'),
    ('real_duration_proxy', 'LTI1TRUU Index', 'INDEX_OAD_TSY', 'years'),
    ('average_maturity', 'LTI1TRUU Index', 'WEIGHTED_AVERAGE_MATURITY_YEARS', 'years'),
)


def prepare_proxies(history, end):
    """Keep observed monthly inputs separate; never equate duration and maturity."""
    end = completed_month_end(end)
    frames, coverage = [], []
    for key, ticker, field, units in SERIES:
        rows = history[(history.ticker == ticker) & (history.field == field)].copy()
        rows['date'] = pd.to_datetime(rows.date)
        rows['value'] = pd.to_numeric(rows.value, errors='coerce')
        rows = rows[(rows.date <= end) & rows.value.notna()]
        if not np.isfinite(rows.value).all():
            raise ValueError(f'Nonfinite {key} observations.')
        if rows.duplicated('date').any():
            raise ValueError(f'Duplicate {key} dates.')
        if units == 'years' and not (rows.value > 0).all():
            raise ValueError(f'{key} must be positive.')
        rows['key'] = key
        rows = monthly_sample(rows, end)
        rows['units'] = units
        rows['normalized_value'] = rows.value * (0.01 if units == 'percent' else 1)
        rows['is_proxy'] = key != 'average_maturity'
        rows['index_real_analytic_verified'] = False
        frames.append(rows)
        coverage.append({'key': key, 'observations': len(rows),
                         'first_date': str(rows.date.min().date()) if len(rows) else None,
                         'last_date': str(rows.date.max().date()) if len(rows) else None})
        if rows.empty or (end - rows.date.max()).days > 7:
            raise ValueError(f'Missing or stale endpoint for {key}; no filling permitted.')
    return pd.concat(frames, ignore_index=True), pd.DataFrame(coverage)


def run_tips_inputs(output, start, end, client, progress=print):
    end = completed_month_end(end)
    if pd.Timestamp(start) > end:
        raise ValueError('No complete months in TIPS input window.')
    frames = []
    for key, ticker, field, units in SERIES:
        if progress:
            progress(f'Fetching TIPS input: {key} ({ticker}, {field})')
        frames.append(client.history([ticker], [field], start, end, frequency='monthly'))
    raw = pd.concat(frames, ignore_index=True)
    raw = raw[pd.to_datetime(raw.date) >= pd.Timestamp(start)]
    data, coverage = prepare_proxies(raw, end)
    folder = save_bundle(data, coverage, output, {
        'kind': 'tips-proxy-inputs', 'start': str(start), 'effective_end': str(end.date()),
        'frequency': 'monthly', 'status': 'provisional_approximation_not_verified_index_analytics',
        'real_yield_proxy_tenor_years': 5, 'source': 'Bloomberg',
        'code_sha256': sha256(__file__), 'point_in_time_eligible': False,
        'real_duration_proxy': 'INDEX_OAD_TSY; real-yield sensitivity not independently verified',
        'inflation_in_yield_proxy': False,
        'limitations': ['Generic 5-year TIPS yield is not index real YTW, par or zero curve.',
                        'Fixed 5-year tenor is not duration; maturity is a separate diagnostic.',
                        'OAD is a duration proxy, not verified index real duration.',
                        'No inflation assumption is subtracted from generic index YTW.',
                        'No missing observations are filled or extrapolated.',
                        'CPI inflation is a separate return input, not automatically PCE.'],
    })
    endpoint = data.sort_values('date').groupby('key', sort=False).tail(1)
    report = ['# TIPS Proxy Input Review', '',
              'Provisional approximations authorized by the user. These inputs do not constitute a return forecast.', '',
              '## Endpoint Observations', '',
              markdown_table(endpoint[['key', 'date', 'ticker', 'field', 'value', 'units', 'is_proxy']]), '',
              '## Coverage', '', markdown_table(coverage), '',
              '## Methodology', '',
              r'Use the observed 5-year TIPS benchmark yield as $y^{R,\mathrm{proxy}}_t$. '
              'Do not subtract assumed inflation from the unverified generic index YTW.', '',
              r'A future first-order nominal return approximation is '
              r'$R^{N}_t \approx y^{R,\mathrm{proxy}}_t\Delta t + \pi^{\mathrm{CPI}}_t\Delta t '
              r'- D^{R,\mathrm{proxy}}_t\Delta y^{R,\mathrm{proxy}}_t$. '
              'This equation is a specification only, not an implemented forecast. '
              'It excludes roll-down, convexity, index turnover, inflation-indexation lag and deflation-floor effects.', '',
              'The fixed 5-year yield proxy approximates a diversified 1-10 year sleeve. '
              'Average maturity is diagnostic, not a replacement for duration. '
              'INDEX_OAD_TSY is an unverified proxy for real-yield sensitivity. '
              'Benchmark verification and exact real-analytics verification remain separate.', '',
              '[Bloomberg methodology](https://data.bloomberglp.com/professional/sites/10/'
              'Bloomberg-Index-Publications-Fixed-Income-Index-Methodology.pdf), '
              '[Federal Reserve real yield curve](https://www.federalreserve.gov/data/tips-yield-curve-and-inflation-compensation.htm)', '']
    (folder / 'run_summary.md').write_text('\n'.join(report), encoding='utf-8')
    manifest = folder / 'manifest.json'
    metadata = json.loads(manifest.read_text())
    metadata['output_sha256'] = {p.name: sha256(p) for p in folder.iterdir() if p.name != 'manifest.json'}
    manifest.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    if progress:
        progress(f'Saved TIPS proxy inputs: {folder}')
        progress(markdown_table(endpoint[['key', 'date', 'value', 'units']]))
    return folder
