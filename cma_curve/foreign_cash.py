"""Configurable foreign cash basket and first-order USD hedge overlay."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from .analysis import markdown_table, sha256
from .bond_returns import checked_source, latest_source
from .curve_projection import convergence_decay, convergence_options
from .data import save_bundle

INPUT_COLUMNS = ['bucket', 'current_cash_decimal', 'current_cash_asof',
                 'inflation_anchor_decimal', 'real_cash_adjustment_bps', 'source', 'note']


def bucket_weights(currencies, majors):
    data = currencies[['currency', 'weight_decimal']].copy()
    if (not majors or len(set(majors)) != len(majors) or 'Other' in majors
            or data.currency.isna().any() or data.currency.duplicated().any()
            or not np.isfinite(data.weight_decimal).all() or (data.weight_decimal < 0).any()):
        raise ValueError('Unique currency labels and finite nonnegative weights are required.')
    if not set(majors).issubset(data.currency):
        raise ValueError('A major currency is missing from the workbook review.')
    residual = 1 - data.weight_decimal.sum()
    if abs(residual) > len(data) * .00005 + 1e-12:
        raise ValueError('Currency total exceeds the two-decimal weight rounding tolerance.')
    data['bucket'] = data.currency.where(data.currency.isin(majors), 'Other')
    weights = data.groupby('bucket').weight_decimal.sum().reindex([*majors, 'Other'], fill_value=0)
    weights.loc['Other'] += residual
    if (weights <= 0).any() or not np.isclose(weights.sum(), 1, atol=1e-12, rtol=0):
        raise ValueError('Each modeled bucket needs positive weight and the basket must sum to one.')
    result = weights.rename('weight_decimal').reset_index()
    result['rounding_residual_assigned_decimal'] = np.where(result.bucket == 'Other', residual, 0)
    return result, data


def validate_assumptions(inputs, weights, asof):
    if not set(INPUT_COLUMNS).issubset(inputs.columns):
        raise ValueError(f'Foreign cash inputs require columns: {INPUT_COLUMNS}.')
    data = inputs.copy()
    if data.bucket.isna().any() or data.bucket.duplicated().any() or set(data.bucket) != set(weights.bucket):
        raise ValueError('Supply exactly one row per modeled bucket, including Other.')
    numeric = ['current_cash_decimal', 'inflation_anchor_decimal', 'real_cash_adjustment_bps']
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors='raise')
    missing = data[numeric].isna().any(axis=1) | data.source.fillna('').str.strip().eq('')
    missing |= data.current_cash_asof.isna()
    if missing.any():
        return None, data.loc[missing, 'bucket'].tolist()
    if not np.isfinite(data[numeric]).all().all():
        raise ValueError('Cash assumptions must be finite. Rates are decimals, adjustments basis points.')
    dates = pd.to_datetime(data.current_cash_asof, errors='raise')
    if not dates.eq(pd.Timestamp(asof)).all():
        raise ValueError('Current cash inputs must match the curve/workbook observation date.')
    return data.merge(weights, on='bucket', validate='one_to_one'), []


def project_foreign_cash(usd_paths, assumptions, usd_inflation, shifts=(0,), basis_bps=0, cost_bps=0,
                         linear_start_year=None, anchor_year=None):
    """Use horizon-t cash for the following month; overlay is not standalone total return."""
    required = {'scenario', 'horizon_years', 'half_life_years', 'rate_decimal', 'anchor_decimal'}
    if not required.issubset(usd_paths.columns) or usd_paths.empty:
        raise ValueError('US cash paths are incomplete.')
    weights = assumptions.weight_decimal
    if (not np.isfinite(weights).all() or (weights < 0).any()
            or not np.isclose(weights.sum(), 1, atol=1e-12, rtol=0)):
        raise ValueError('Foreign basket weights must sum to one.')
    if (not shifts or len(set(shifts)) != len(shifts)
            or not np.isfinite([*shifts, usd_inflation, basis_bps, cost_bps]).all() or cost_bps < 0):
        raise ValueError('Unique finite anchor sensitivities and nonnegative implementation cost are required.')
    if not np.isfinite(assumptions[['current_cash_decimal', 'inflation_anchor_decimal', 'real_cash_adjustment_bps']]).all().all():
        raise ValueError('Complete finite cash and anchor assumptions are required.')
    paths, details = [], []
    for scenario, usd in usd_paths.groupby('scenario', sort=False):
        usd = usd.sort_values('horizon_years').reset_index(drop=True)
        h = usd.horizon_years.to_numpy()
        if (len(h) < 2 or h[0] != 0 or not np.allclose(np.diff(h), 1 / 12, atol=1e-10, rtol=0)
                or not np.isfinite(usd[list(required - {'scenario'})]).all().all()
                or usd.half_life_years.nunique() != 1 or usd.half_life_years.iloc[0] <= 0
                or usd.anchor_decimal.nunique() != 1):
            raise ValueError('US cash paths must have a complete monthly grid from zero and one anchor/half-life per scenario.')
        half_life, anchor = usd.half_life_years.iloc[0], usd.anchor_decimal.iloc[0]
        for shift in shifts:
            name = 'base' if shift == 0 else f'foreign_anchor_{shift:+g}bp'
            bucket_paths = []
            for row in assumptions.itertuples(index=False):
                foreign_anchor = anchor + row.inflation_anchor_decimal - usd_inflation + row.real_cash_adjustment_bps / 10000 + shift / 10000
                rates = foreign_anchor + (row.current_cash_decimal - foreign_anchor) * convergence_decay(
                    h, half_life, linear_start_year, anchor_year)
                bucket_paths.append(pd.DataFrame({'scenario': scenario, 'anchor_case': name,
                    'bucket': row.bucket, 'horizon_years': h, 'weight_decimal': row.weight_decimal,
                    'foreign_cash_decimal': rates, 'foreign_anchor_decimal': foreign_anchor,
                    'weighted_cash_decimal': row.weight_decimal * rates}))
            detail = pd.concat(bucket_paths, ignore_index=True)
            basket = detail.groupby('horizon_years').weighted_cash_decimal.sum().reindex(h).to_numpy()
            result = usd[['scenario', 'horizon_years', 'half_life_years']].copy()
            result['anchor_case'] = name
            result['usd_cash_decimal'] = usd.rate_decimal.to_numpy()
            result['foreign_cash_decimal'] = basket
            result['hedge_carry_annual_decimal'] = usd.rate_decimal.to_numpy() - basket + (basis_bps - cost_bps) / 10000
            result['hedge_carry_annual_bps'] = result.hedge_carry_annual_decimal * 10000
            result['next_month_hedge_overlay_decimal'] = result.hedge_carry_annual_decimal / 12
            paths.append(result); details.append(detail)
    return pd.concat(paths, ignore_index=True), pd.concat(details, ignore_index=True)


def run_foreign_cash(output, settings_path, assumptions_path=None, workbook_bundle=None, curve_bundle=None, progress=print):
    config = json.loads(Path(settings_path).read_text(encoding='utf-8'))
    if config.get('status') != 'research_draft_not_approved' or config.get('weight_policy') != 'major_raw_weights_other_residual':
        raise ValueError('Foreign cash settings must specify the draft model and explicit residual policy.')
    workbook = Path(workbook_bundle) if workbook_bundle else latest_source(output, 'workbook-input-review')
    curve = Path(curve_bundle) if curve_bundle else latest_source(output, 'curve-projection')
    wm = checked_source(workbook, 'workbook-input-review', ['currency_inputs.csv'])
    cm = checked_source(curve, 'curve-projection', ['projected_par_curves.csv'])
    review = Path(cm['review_bundle'])
    if sha256(review / 'manifest.json') != cm['review_manifest_sha256']:
        raise ValueError('Underlying anchor-review manifest changed.')
    rm = checked_source(review, 'anchor-review', ['candidate_anchors.csv', 'starting_par_curve.csv'])
    asof = rm['common_starting_curve_date']
    if wm.get('asof_date') != asof:
        raise ValueError('Workbook as-of date must be confirmed and match the starting curve.')
    weights, mapping = bucket_weights(pd.read_csv(workbook / 'currency_inputs.csv'), config['major_currencies'])
    anchors = pd.read_csv(review / 'candidate_anchors.csv')
    candidate = cm['anchor_settings']['primary_candidate']
    selected = anchors[(anchors.candidate == candidate) & (anchors.key == config['usd_cash_key'])]
    if len(selected) != 1 or not np.isfinite(selected.inflation_percent.iloc[0]):
        raise ValueError('US inflation anchor missing or ambiguous.')
    usd_inflation = selected.inflation_percent.iloc[0] / 100
    usd = pd.read_csv(curve / 'projected_par_curves.csv')
    usd = usd[(usd.key == config['usd_cash_key']) & (usd.candidate == candidate)].copy()
    if usd.empty or not np.allclose(usd.anchor_decimal, selected.anchor_decimal.iloc[0], rtol=0, atol=1e-12):
        raise ValueError('US cash projection does not match its selected anchor review.')
    input_path = Path(assumptions_path) if assumptions_path else Path(settings_path).resolve().parent / config['assumptions_file']
    template = pd.DataFrame({'bucket': weights.bucket, 'current_cash_decimal': np.nan,
        'current_cash_asof': asof, 'inflation_anchor_decimal': np.nan,
        'real_cash_adjustment_bps': 0.0, 'source': '',
        'note': 'Zero real-cash adjustment is provisional; specify cash convention and anchor rationale.'})
    if not input_path.exists():
        if assumptions_path:
            raise ValueError(f'Explicit foreign cash input file does not exist: {input_path}')
        input_path.parent.mkdir(parents=True, exist_ok=True)
        template.to_csv(input_path, index=False)
    inputs = pd.read_csv(input_path)
    assumptions, missing = validate_assumptions(inputs, weights, asof)
    paths, detail = (pd.DataFrame(), pd.DataFrame()) if missing else project_foreign_cash(
        usd, assumptions, usd_inflation, config['foreign_anchor_sensitivities_bps'],
        config['basis_adjustment_bps'], config['implementation_cost_bps'],
        **convergence_options(cm.get('projection_settings', {})))
    coverage = weights.copy()
    coverage['cash_inputs_complete'] = ~coverage.bucket.isin(missing)
    status = 'missing_inputs_no_projection' if missing else 'research_hedge_overlay_not_total_return'
    folder = save_bundle(detail, coverage, output, {'kind': 'foreign-cash-review', 'status': status,
        'asof_date': asof, 'candidate': candidate, 'usd_cash_key': config['usd_cash_key'],
        'usd_inflation_anchor_decimal': usd_inflation, 'settings': config,
        'settings_sha256': sha256(settings_path), 'code_sha256': sha256(__file__),
        'input_file': str(input_path.resolve()), 'input_sha256': sha256(input_path),
        'workbook_bundle': str(workbook.resolve()), 'workbook_manifest_sha256': sha256(workbook / 'manifest.json'),
        'curve_bundle': str(curve.resolve()), 'curve_manifest_sha256': sha256(curve / 'manifest.json'),
        'anchor_review_manifest_sha256': sha256(review / 'manifest.json'),
        'point_in_time_eligible': False, 'missing_buckets': missing,
        'weight_policy': 'Major weights unchanged; Other absorbs remaining exposures and displayed rounding residual.',
        'output_interpretation': 'Monthly additive hedge overlay only; do not compound it as standalone bond returns.'})
    inputs.to_csv(folder / 'input_assumptions.csv', index=False)
    mapping.to_csv(folder / 'currency_bucket_mapping.csv', index=False)
    template.to_csv(folder / 'foreign_cash_assumptions_template.csv', index=False)
    summaries = []
    if not missing:
        paths.to_csv(folder / 'cash_and_hedge_paths.csv', index=False)
        monthly = paths[paths.horizon_years < paths.horizon_years.max()].copy()
        # The horizon-zero rate funds the first month; never shift to an ending-period rate.
        monthly['return_month'] = monthly.horizon_years.mul(12).round().astype(int) + 1
        monthly['date'] = monthly.return_month.map(lambda n: (pd.Timestamp(asof) + pd.offsets.MonthEnd(n)).date().isoformat())
        monthly.to_csv(folder / 'monthly_hedge_overlay.csv', index=False)
        for (scenario, case), group in monthly.groupby(['scenario', 'anchor_case']):
            for years in (1, 5, 10, 20, 30, 40):
                selected_months = group[group.return_month <= years * 12]
                if len(selected_months) == years * 12:
                    summaries.append({'scenario': scenario, 'anchor_case': case, 'horizon_years': years,
                                      'average_annual_hedge_carry_bps': selected_months.hedge_carry_annual_bps.mean()})
    summary = pd.DataFrame(summaries)
    summary.to_csv(folder / 'horizon_average_hedge_carry.csv', index=False)
    report = ['# Foreign Cash Basket And USD Hedge Overlay', '', f'Status: {status}. Observation date: {asof}.', '',
        f'US cash proxy: {config["usd_cash_key"]}; candidate: {candidate}; US inflation anchor: {usd_inflation:.2%}.', '',
        '## Bucket Weights', '', markdown_table(coverage), '',
        'Other includes small currencies, Unclassified and the displayed rounding residual. This is an explicit '
        'modeling approximation, not a claim that the workbook supplied exact 100% weights. No major weight is rescaled.', '',
        '## Formulas', '', '$$', r'a_c=a_{USD}+(\pi_c-\pi_{USD})+\delta_c', '$$', '',
        '$$', r'r_c(t)=a_c+[r_c(0)-a_c]2^{-t/h}', '$$', '',
        '$$', r'H_t=r_{USD}(t)-\sum_c w_cr_c(t)+b-k,\qquad H_t^{monthly}=H_t/12', '$$', '',
        'Rates and inflation are annual decimals. Real-cash adjustments, basis and costs enter settings in basis points. '
        'Basis is a signed additive hedge-return adjustment; implementation cost is a nonnegative deduction. '
        'Half-lives are inherited from the US scenarios. Foreign anchor +/-50bp cases are illustrative sensitivities, not confidence intervals.', '',
        'Cash at horizon zero applies to the first return month. This is an additive return overlay, not a standalone '
        'bond return or CAGR. Do not add it to an already USD-hedged series. No foreign duration or bond-price path is generated.', '',
        f'Editable inputs: `{input_path.resolve()}`. Existing files are never overwritten. '
        'Current rates must match the observation date; source notes must document comparable cash proxies '
        'and the rationale for inflation/real-cash anchors, including the Other approximation.', '',
        f'Missing inputs in buckets: {missing}.' if missing else markdown_table(summary), '',
        'Zero basis, costs and real-cash adjustments are provisional assumptions, not estimated facts. '
        'US one-month Treasury cash is a cash-return proxy, not exact FX-forward funding. Cross-currency basis, '
        'funding conventions and hedge slippage are not replicated. Fixed weights are reviewed annually.', '',
        '[JPM methodology, currency hedging](https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/portfolio-insights/ltcma/noindex/ltcma-methodology-handbook.pdf)', '']
    (folder / 'run_summary.md').write_text('\n'.join(report), encoding='utf-8')
    manifest = folder / 'manifest.json'
    metadata = json.loads(manifest.read_text())
    metadata['output_sha256'] = {p.name: sha256(p) for p in folder.iterdir() if p.name != 'manifest.json'}
    manifest.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    if progress:
        progress(f'Saved foreign cash review: {folder} ({status})')
        progress(f'Editable foreign cash assumptions: {input_path.resolve()}')
    return folder
