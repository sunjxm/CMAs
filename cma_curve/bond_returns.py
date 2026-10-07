"""Auditable first-order return diagnostics for two USD investment-grade sleeves."""
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from .analysis import markdown_table, sha256
from .bond_inputs import load_assets

ASSETS = ('short_term_bond', 'us_aggregate')
METRICS = ('yield', 'rate_duration', 'spread_duration', 'oas')
COMPONENTS = ('carry_proxy', 'rate_effect', 'spread_effect', 'credit_loss_effect')


def load_return_settings(path):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    if config.get('status') != 'research_draft_not_approved' or config.get('model') != 'first_order_yield_proxy':
        raise ValueError('Return settings must specify the draft first-order model.')
    if set(config['assets']) != set(ASSETS):
        raise ValueError('This implementation supports only short-term bonds and US Aggregate.')
    for asset in config['assets'].values():
        weights = asset['rate_node_weights']
        if not weights or any(not np.isfinite(w) or w < 0 for w in weights.values()) or not np.isclose(sum(weights.values()), 1):
            raise ValueError('Rate-node weights must be finite, nonnegative and sum to one.')
    for key in ('spread_window_years', 'minimum_spread_months'):
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError(f'{key} must be a positive integer.')
    if not np.isfinite(config['spread_half_life_years']) or config['spread_half_life_years'] <= 0:
        raise ValueError('Spread half-life must be positive.')
    horizons = config['report_horizons_years']
    if not horizons or len(set(horizons)) != len(horizons) or any(type(h) is not int or h <= 0 for h in horizons):
        raise ValueError('Report horizons must be unique positive integers.')
    names = set()
    for case in config['cases']:
        if not case['name'] or case['name'] in names or case['spread_anchor'] not in {'current', 'historical_median'}:
            raise ValueError('Cases must have unique names and supported spread anchors.')
        names.add(case['name'])
        if not np.isfinite(case['annual_loss_bps']) or case['annual_loss_bps'] < 0:
            raise ValueError('Annual loss sensitivities must be finite and nonnegative.')
    if not names:
        raise ValueError('At least one return case is required.')
    return config


def latest_source(root, kind):
    candidates = []
    for path in Path(root).glob('*/manifest.json'):
        metadata = json.loads(path.read_text(encoding='utf-8'))
        if metadata.get('kind') == kind:
            candidates.append((pd.Timestamp(metadata.get('created_at_utc', metadata.get('retrieved_at_utc'))), path.parent))
    if not candidates:
        raise ValueError(f'Missing {kind} archive. Run the corresponding input task first.')
    return max(candidates, key=lambda item: item[0])[1]


def checked_source(folder, kind, filenames):
    folder = Path(folder)
    metadata = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if metadata.get('kind') != kind:
        raise ValueError(f'Expected {kind} archive.')
    for filename in filenames:
        if metadata.get('output_sha256', {}).get(filename) != sha256(folder / filename):
            raise ValueError(f'Source checksum mismatch: {filename}')
    return metadata


def analytics_months(data, asset):
    rows = data[(data.key == asset) & data.metric.isin(METRICS)].copy()
    if rows.empty or not rows.definition_verified.eq(True).all():
        raise ValueError(f'Missing or unverified analytics for {asset}.')
    expected_units = {'yield': 'percent', 'oas': 'basis_points', 'rate_duration': 'years', 'spread_duration': 'years'}
    if not rows.units.eq(rows.metric.map(expected_units)).all():
        raise ValueError('Analytics units do not match the return model.')
    factors = rows.metric.map({'yield': .01, 'oas': .0001, 'rate_duration': 1, 'spread_duration': 1})
    if not np.isfinite(rows.normalized_value).all() or not np.allclose(rows.value * factors, rows.normalized_value):
        raise ValueError('Invalid normalized analytics values.')
    rows['month'] = pd.to_datetime(rows.date).dt.to_period('M')
    if rows.duplicated(['month', 'metric']).any():
        raise ValueError('Duplicate monthly analytics.')
    age = (rows.month.dt.to_timestamp('M') - pd.to_datetime(rows.date)).dt.days
    if not age.between(0, 7).all():
        raise ValueError('Analytics must be observed within seven days of month-end.')
    wide = rows.pivot(index='month', columns='metric', values='normalized_value').reindex(columns=METRICS)
    for metric in ('rate_duration', 'spread_duration'):
        if (wide[metric].dropna() <= 0).any():
            raise ValueError('Durations must be positive.')
    return wide.sort_index()


def treasury_months(data, weights):
    rows = data[data.key.isin(weights)].copy()
    if not rows.curve_type.eq('par').all() or not rows.verified.eq(True).all():
        raise ValueError('Historical rate diagnostics require verified Treasury par nodes.')
    if rows.duplicated(['date', 'key']).any() or not np.isfinite(rows.rate_decimal).all():
        raise ValueError('Invalid Treasury observations.')
    # Select the last complete daily curve each month, not different dates per node.
    wide = rows.pivot(index='date', columns='key', values='rate_decimal').reindex(columns=weights).dropna()
    wide.index = pd.to_datetime(wide.index)
    wide = wide.groupby(wide.index.to_period('M')).tail(1)
    months = wide.index.to_period('M')
    age = (months.to_timestamp('M') - wide.index).days
    wide = wide[age <= 7]
    result = wide.mul(pd.Series(weights)).sum(axis=1)
    result.index = result.index.to_period('M')
    return result.rename('treasury_proxy')


def project_sleeve(curves, weights, endpoint, spread_anchor, spread_half_life, loss_bps):
    if curves.duplicated(['horizon_years', 'key']).any() or not curves.curve_type.eq('par').all():
        raise ValueError('Projection requires unique par nodes at each horizon.')
    wide = curves.pivot(index='horizon_years', columns='key', values='rate_decimal').reindex(columns=weights)
    h = wide.index.to_numpy(dtype=float)
    if len(h) < 2 or h[0] != 0 or not np.allclose(np.diff(h), 1 / 12, rtol=0, atol=1e-9):
        raise ValueError('Return projection requires a complete monthly grid starting at zero.')
    if not np.isfinite(wide.to_numpy()).all() or not np.isfinite([*endpoint.values, spread_anchor, spread_half_life, loss_bps]).all():
        raise ValueError('Nonfinite projection input or missing rate node.')
    if spread_half_life <= 0 or loss_bps < 0 or endpoint.rate_duration <= 0 or endpoint.spread_duration <= 0:
        raise ValueError('Invalid duration, spread half-life or loss assumption.')
    treasury = wide.mul(pd.Series(weights)).sum(axis=1).to_numpy()
    spread = spread_anchor + (endpoint.oas - spread_anchor) * np.exp2(-h / spread_half_life)
    basis = endpoint['yield'] - treasury[0] - endpoint.oas
    y = treasury + spread + basis
    result = pd.DataFrame({'horizon_years': h[1:], 'starting_yield_proxy': y[:-1],
                           'ending_yield_proxy': y[1:], 'starting_spread': spread[:-1],
                           'ending_spread': spread[1:], 'yield_basis_residual': basis,
                           'rate_duration': endpoint.rate_duration, 'spread_duration': endpoint.spread_duration,
                           'carry_proxy': y[:-1] / 12,
                           'rate_effect': -endpoint.rate_duration * np.diff(treasury),
                           'spread_effect': -endpoint.spread_duration * np.diff(spread),
                           'credit_loss_effect': -loss_bps / 10000 / 12})
    result['monthly_return'] = result[list(COMPONENTS)].sum(axis=1)
    if not np.isfinite(result.monthly_return).all() or (result.monthly_return <= -1).any():
        raise ValueError('Return path must be finite and greater than -100%.')
    result['wealth_index'] = (1 + result.monthly_return).cumprod()
    return result


def summarize_paths(paths, horizons):
    annual, cumulative = [], []
    group_cols = ['key', 'rate_scenario', 'return_case']
    for group, rows in paths.groupby(group_cols, sort=False):
        rows = rows.sort_values('horizon_years')
        labels = dict(zip(group_cols, group))
        for year in range(1, int(round(rows.horizon_years.max())) + 1):
            sample = rows[(rows.horizon_years > year - 1 + 1e-9) & (rows.horizon_years <= year + 1e-9)]
            if len(sample) != 12:
                raise ValueError('Annual compounding requires twelve monthly returns.')
            growth_before = np.r_[1, np.cumprod(1 + sample.monthly_return.to_numpy())[:-1]]
            annual.append({**labels, 'year': year, 'annual_return': np.prod(1 + sample.monthly_return) - 1,
                           **{c + '_sum': sample[c].sum() for c in COMPONENTS},
                           **{c + '_compounded_contribution': np.sum(growth_before * sample[c].to_numpy())
                              for c in COMPONENTS}})
        for horizon in horizons:
            sample = rows[rows.horizon_years <= horizon + 1e-9]
            if len(sample) != horizon * 12:
                raise ValueError('Report horizon exceeds the complete projection path.')
            cumulative.append({**labels, 'horizon_years': horizon,
                               'annualized_return': np.prod(1 + sample.monthly_return) ** (1 / horizon) - 1})
    return pd.DataFrame(annual), pd.DataFrame(cumulative)


def historical_diagnostic(analytics, treasury, returns, asset, weights):
    wide = analytics_months(analytics, asset).join(treasury_months(treasury, weights))
    actual = returns[returns.key == asset].copy()
    actual['month'] = pd.to_datetime(actual.date).dt.to_period('M')
    if actual.month.duplicated().any():
        raise ValueError('Duplicate historical index return months.')
    actual = actual.set_index('month').monthly_total_return_decimal.rename('observed_return')
    if not np.isfinite(actual.dropna()).all() or (actual.dropna() <= -1).any():
        raise ValueError('Invalid observed index returns.')
    wide = wide.join(actual)
    previous = wide.shift(1)
    adjacent = pd.Series(wide.index.asi8, index=wide.index).diff().eq(1)
    data = pd.DataFrame({'key': asset, 'month': wide.index.astype(str),
                         'carry_proxy': previous['yield'] / 12,
                         'rate_effect': -previous.rate_duration * (wide.treasury_proxy - previous.treasury_proxy),
                         'spread_effect': -previous.spread_duration * (wide.oas - previous.oas),
                         'observed_return': wide.observed_return}, index=wide.index)
    required = list(METRICS) + ['treasury_proxy']
    good = adjacent & wide[required].notna().all(axis=1) & previous[required].notna().all(axis=1)
    data = data[good].dropna()
    data['modeled_return'] = data[['carry_proxy', 'rate_effect', 'spread_effect']].sum(axis=1)
    data['residual'] = data.observed_return - data.modeled_return
    if len(data) < 24:
        raise ValueError(f'Insufficient comparable historical months for {asset}.')
    metrics = {'key': asset, 'months': len(data), 'first_month': data.month.iloc[0], 'last_month': data.month.iloc[-1],
               'monthly_bias_bps_observed_minus_model': data.residual.mean() * 10000,
               'monthly_rmse_bps': np.sqrt(np.mean(data.residual ** 2)) * 10000,
               'correlation': data.observed_return.corr(data.modeled_return)
               if np.ptp(data.observed_return.to_numpy()) > 0 and np.ptp(data.modeled_return.to_numpy()) > 0 else np.nan,
               'annualized_residual_std_percent': data.residual.std(ddof=1) * np.sqrt(12) * 100}
    return data.reset_index(drop=True), metrics


def diagnostic_years(detail):
    rows = []
    detail = detail.copy()
    detail['year'] = pd.PeriodIndex(detail.month, freq='M').year
    for (asset, year), sample in detail.groupby(['key', 'year'], sort=False):
        complete = len(sample) == 12
        rows.append({'key': asset, 'year': year, 'months': len(sample), 'complete_calendar_year': complete,
                     'observed_annual_return': np.prod(1 + sample.observed_return) - 1 if complete else np.nan,
                     'modeled_annual_return': np.prod(1 + sample.modeled_return) - 1 if complete else np.nan,
                     'monthly_rmse_bps': np.sqrt(np.mean(sample.residual ** 2)) * 10000})
    return pd.DataFrame(rows)


def run_bond_returns(output, settings_path, catalog_path, anchor_settings, projection_settings,
                     curve_bundle=None, analytics_bundle=None, history_bundle=None, progress=print):
    config = load_return_settings(settings_path)
    catalog = load_assets(catalog_path)
    curve = Path(curve_bundle) if curve_bundle else latest_source(output, 'curve-projection')
    analytics = Path(analytics_bundle) if analytics_bundle else latest_source(output, 'asset-analytics-normalized')
    history = Path(history_bundle) if history_bundle else latest_source(output, 'asset-history')
    cm = checked_source(curve, 'curve-projection', ['projected_par_curves.csv'])
    am = checked_source(analytics, 'asset-analytics-normalized', ['observations.csv'])
    hm = checked_source(history, 'asset-history', ['historical_total_returns.csv'])
    if cm['anchor_settings_sha256'] != sha256(anchor_settings) or cm['projection_settings_sha256'] != sha256(projection_settings):
        raise ValueError('Curve settings changed; rerun curve-projection before returns.')
    approved = {a['key']: a for a in catalog['assets']}
    for metadata in (am, hm):
        archived = {a['key']: a for a in metadata['asset_config']['assets']}
        for key in ASSETS:
            if not approved[key]['verified'] or approved[key]['ticker'] != archived[key]['ticker']:
                raise ValueError('Benchmark changed or is unapproved; rerun inputs.')
            if metadata is am:
                for metric in METRICS:
                    mapping = approved[key]['analytics'][metric]
                    old = archived[key]['analytics'][metric]
                    if not mapping['verified'] or any(mapping[k] != old[k] for k in ('field', 'units', 'verified')):
                        raise ValueError('Analytics mapping changed; rerun normalization.')
    review = Path(cm['review_bundle'])
    if sha256(review / 'manifest.json') != cm['review_manifest_sha256']:
        raise ValueError('Projection review manifest checksum mismatch.')
    rm = checked_source(review, 'anchor-review', ['starting_par_curve.csv'])
    asof = pd.Timestamp(rm['common_starting_curve_date'])
    month = asof.to_period('M')
    treasury_path = Path(rm['treasury_bundle']) / 'observations.csv'
    if sha256(treasury_path) != rm['treasury_observations_sha256']:
        raise ValueError('Historical Treasury checksum mismatch.')
    treasury = pd.read_csv(treasury_path, parse_dates=['date'])
    observations = pd.read_csv(analytics / 'observations.csv', parse_dates=['date'])
    returns = pd.read_csv(history / 'historical_total_returns.csv', parse_dates=['date'])
    curves = pd.read_csv(curve / 'projected_par_curves.csv')
    if not curves.candidate.eq(cm['anchor_settings']['primary_candidate']).all():
        raise ValueError('Curve candidate mismatch.')
    paths, diagnostics, metrics, inputs = [], [], [], []
    for asset in ASSETS:
        weights = config['assets'][asset]['rate_node_weights']
        wide = analytics_months(observations, asset)
        if month not in wide.index or wide.loc[month].isna().any():
            raise ValueError(f'Missing common forecast endpoint for {asset}.')
        endpoint = wide.loc[month]
        window_start = month - (config['spread_window_years'] * 12 - 1)
        sample = wide.loc[(wide.index >= window_start) & (wide.index <= month), 'oas'].dropna()
        if len(sample) < config['minimum_spread_months']:
            raise ValueError('Insufficient spread observations for median sensitivity.')
        median = sample.median()
        inputs.append({'key': asset, 'endpoint_month': str(month), **endpoint.to_dict(),
                       'median_spread_decimal': median, 'spread_months': len(sample),
                       'spread_first_month': str(sample.index.min()), 'spread_last_month': str(sample.index.max()),
                       'rate_node_weights': json.dumps(weights), 'annual_loss_base_bps': 0})
        for scenario, nodes in curves.groupby('scenario', sort=False):
            initial = nodes[nodes.horizon_years == 0].set_index('key').rate_decimal
            official = pd.read_csv(review / 'starting_par_curve.csv').set_index('key').rate_decimal
            if not set(weights).issubset(initial.index) or not np.allclose(initial.loc[list(weights)], official.loc[list(weights)]):
                raise ValueError('Projected starting curve differs from source review.')
            for case in config['cases']:
                anchor = endpoint.oas if case['spread_anchor'] == 'current' else median
                path = project_sleeve(nodes, weights, endpoint, anchor, config['spread_half_life_years'], case['annual_loss_bps'])
                path['key'], path['rate_scenario'], path['return_case'] = asset, scenario, case['name']
                path['date'] = pd.period_range(month + 1, periods=len(path), freq='M').to_timestamp('M')
                paths.append(path)
        diagnostic, metric = historical_diagnostic(observations[observations.date <= asof], treasury[treasury.date <= asof],
                                                   returns[returns.date <= asof], asset, weights)
        diagnostics.append(diagnostic)
        metrics.append(metric)
    paths = pd.concat(paths, ignore_index=True)
    annual, cumulative = summarize_paths(paths, config['report_horizons_years'])
    stamp = datetime.now(timezone.utc)
    folder = Path(output) / (stamp.strftime('%Y%m%dT%H%M%S') + '_bond-returns_' + uuid4().hex[:8])
    folder.mkdir(parents=True)
    outputs = {'monthly_return_paths.csv': paths, 'annual_return_paths.csv': annual,
               'annualized_returns.csv': cumulative, 'starting_inputs.csv': pd.DataFrame(inputs),
               'historical_diagnostics.csv': pd.concat(diagnostics, ignore_index=True),
               'historical_diagnostic_metrics.csv': pd.DataFrame(metrics)}
    outputs['historical_diagnostic_years.csv'] = diagnostic_years(outputs['historical_diagnostics.csv'])
    for name, frame in outputs.items():
        frame.to_csv(folder / name, index=False)
    selected = cumulative[(cumulative.rate_scenario == 'base') & (cumulative.return_case == 'gross_constant_spread')].copy()
    selected['annualized_return_percent'] = selected.annualized_return * 100
    report = ['# Investment-Grade Bond Return Research', '',
              'Status: draft scenario approximations, NOT approved expected-return CMAs.', '',
              f'Endpoint month: {month}. Anchor candidate: {cm["anchor_settings"]["primary_candidate"]}.', '',
              '## Gross Baseline', '',
              'Constant spreads, constant durations, yield-based carry proxy, no credit losses or fees. '
              'This is a deterministic gross scenario path, not an expected geometric return under uncertainty.', '',
              markdown_table(selected[['key', 'horizon_years', 'annualized_return_percent']]), '',
              '## Historical Diagnostics', '', markdown_table(pd.DataFrame(metrics)), '',
              'Diagnostics use realized next-month curve and OAS changes, beginning-month yield and durations. '
              'They test contemporaneous explanatory fit, not forecasting skill or a point-in-time backtest. '
              'Residuals are not fitted into forecast carry or credit losses. Missing or nonadjacent months are excluded.', '',
              '## Assumptions And Limitations', '',
              'Node weights are illustrative rate-exposure proxies, not measured key-rate durations or maturity mappings. '
              'US Aggregate uses 50% 5-year and 50% 10-year; short-term uses the 2-year node. '
              'Durations stay at their observed endpoint values. Yield-to-worst/12 approximates carry; '
              'a fixed initial yield-minus-Treasury-minus-OAS residual is retained. '
              'Separate roll-down, convexity, mortgage-option dynamics, fees and taxes are not modeled. '
              'OAS is included in the yield proxy once; spread-change price effects are separate. '
              '10/25bp annual loss cases are sensitivities, not estimated losses. '
              'The historical median spread case is separate from the baseline and from the neutral-rate median20 choice.', '',
              '## Formulas', '', '$$',
              r'q_a = Y_{a,0} - \sum_m w_{a,m}y_{m,0} - s_{a,0}', '$$', '', '$$',
              r'Y_{a,t}=\sum_m w_{a,m}y_{m,t}+s_{a,t}+q_a', '$$', '', '$$',
              r'R_{a,t+1}=\frac{Y_{a,t}}{12}-D^r_a\sum_m w_{a,m}(y_{m,t+1}-y_{m,t})'
              r'-D^s_a(s_{a,t+1}-s_{a,t})-\frac{\ell_a}{12}', '$$', '',
              'All rates and returns are decimals; durations are years. Columns ending _sum are arithmetic sums. '
              'Columns ending _compounded_contribution weight each monthly component by prior accumulated wealth '
              'within the year and sum exactly to the compounded annual return.', '',
              '## Reproduction', '', '```powershell', 'python main.py --task bond-returns', '```', '',
              f'Curve source: `{curve.resolve()}`', '', f'Analytics source: `{analytics.resolve()}`', '',
              f'Index history source: `{history.resolve()}`', '',
              '[Bloomberg index methodology](https://data.bloomberglp.com/professional/sites/10/'
              'Bloomberg-Index-Publications-Fixed-Income-Index-Methodology.pdf)', '']
    (folder / 'run_summary.md').write_text('\n'.join(report), encoding='utf-8')
    metadata = {'kind': 'bond-returns', 'created_at_utc': stamp.isoformat(), 'retrieved_at_utc': stamp.isoformat(),
                'status': 'research_draft_not_approved', 'point_in_time_eligible': False,
                'outputs_are': 'deterministic_scenario_returns_not_final_expected_return_assumptions',
                'observation_cutoff': str(asof.date()), 'settings': config, 'settings_sha256': sha256(settings_path),
                'asset_config_sha256': sha256(catalog_path), 'code_sha256': sha256(__file__),
                'sources': {str(p.resolve()): sha256(p / 'manifest.json') for p in (curve, analytics, history, review)},
                'treasury_observations_sha256': sha256(treasury_path),
                'output_sha256': {p.name: sha256(p) for p in folder.iterdir()}}
    (folder / 'manifest.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    if progress:
        progress(f'Saved investment-grade return research: {folder}')
        progress(markdown_table(selected[['key', 'horizon_years', 'annualized_return_percent']]))
    return folder
