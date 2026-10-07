"""USD hedge-carry approximation with explicit complete currency inputs."""
import json
import numpy as np
import pandas as pd
from .analysis import markdown_table, sha256
from .data import save_bundle

COLUMNS = ['date','currency','weight_decimal','local_return_decimal','usd_cash_decimal','foreign_cash_decimal']


def hedged_returns(inputs):
    if not set(COLUMNS).issubset(inputs.columns):
        raise ValueError('Global hedge input columns are incomplete.')
    data = inputs[COLUMNS].copy()
    data['date'] = pd.to_datetime(data.date)
    data['month'] = data.date.dt.to_period('M')
    if data.empty or data.currency.isna().any() or data.currency.eq('USD').any() or data.duplicated(['month','currency']).any():
        raise ValueError('Unique non-USD currency exposures per month are required.')
    if not np.isfinite(data[COLUMNS[2:]]).all().all() or (data.weight_decimal < 0).any() or (data.local_return_decimal <= -1).any():
        raise ValueError('Invalid weights, rates or monthly local returns.')
    if not data.groupby('month').weight_decimal.sum().map(lambda w: np.isclose(w, 1, atol=1e-6, rtol=0)).all():
        raise ValueError('Currency weights must sum to one each month; no omitted-currency rescaling.')
    if (data.groupby('month').usd_cash_decimal.nunique() != 1).any():
        raise ValueError('Use one common USD cash rate for each month.')
    months = np.sort(data.month.unique())
    if len(months) > 1 and not (np.diff(pd.PeriodIndex(months).asi8) == 1).all():
        raise ValueError('Missing months cannot be bridged in a hedge return path.')
    data['hedge_carry_decimal'] = (data.usd_cash_decimal - data.foreign_cash_decimal) / 12
    data['local_contribution'] = data.weight_decimal * data.local_return_decimal
    data['hedge_contribution'] = data.weight_decimal * data.hedge_carry_decimal
    result = data.groupby('month')[['local_contribution','hedge_contribution']].sum().reset_index()
    result['monthly_return'] = result.local_contribution + result.hedge_contribution
    if (result.monthly_return <= -1).any():
        raise ValueError('Hedged monthly return must exceed -100%.')
    result['wealth_index'] = (1 + result.monthly_return).cumprod()
    result['month'] = result.month.astype(str)
    return data, result


def run_global_hedge_review(output, inputs_path=None, progress=print):
    detail, results = (hedged_returns(pd.read_csv(inputs_path)) if inputs_path else
                       (pd.DataFrame(columns=COLUMNS), pd.DataFrame()))
    status = 'research_approximation' if inputs_path else 'missing_inputs_no_forecast'
    folder = save_bundle(detail, results, output, {'kind':'global-hedge-review','status':status,
        'point_in_time_eligible':False, 'code_sha256':sha256(__file__),
        'input_sha256':sha256(inputs_path) if inputs_path else None,
        'convention':'annual decimal beginning-period cash rates, monthly local returns, full monthly currency weights',
        'missing_inputs':[] if inputs_path else ['complete currency weights','foreign local bond return paths','USD and foreign cash rate paths'],
        'omissions':['cross-currency basis','actual forward quotes','hedge rebalancing slippage','residual FX exposure','fees']})
    pd.DataFrame(columns=COLUMNS).to_csv(folder / 'global_hedge_inputs_template.csv', index=False)
    report = ['# Global ex-USD Hedge Review','',f'Status: {status}.','',
              'No foreign-bond forecasts or currency weights are invented. A complete monthly input file is required. '
              'The short-rate differential is a first-order long-run proxy, not exact benchmark hedge P/L. '
              'Foreign duration remains foreign duration; currency hedging does not convert it to US Treasury exposure.','',
              '$$',r'R^{USD,h}_t\approx\sum_c w_{c,t}\left[R^{local}_{c,t}+(r^{USD}_t-r^c_t)/12\right]','$$','',
              'Cash rates are annual decimals known at the beginning of each return period; local returns are monthly decimals. '
              'Hedge carry can be positive or negative. Do not add an unhedged FX appreciation forecast on top of this approximation.','',
              markdown_table(results.tail()) if len(results) else 'No global return path generated: complete currency exposures and foreign return/cash paths are outstanding.','',
              '[JPM methodology, page 31](https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/portfolio-insights/ltcma/noindex/ltcma-methodology-handbook.pdf)','']
    (folder / 'run_summary.md').write_text('\n'.join(report),encoding='utf-8')
    manifest = folder / 'manifest.json'
    info = json.loads(manifest.read_text())
    info['output_sha256'] = {p.name:sha256(p) for p in folder.iterdir() if p.name != 'manifest.json'}
    manifest.write_text(json.dumps(info,indent=2),encoding='utf-8')
    if progress:
        progress(f'Saved global hedge review: {folder} ({status})')
    return folder
