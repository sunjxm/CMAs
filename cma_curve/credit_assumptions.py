"""Composition-aware research diagnostics; incomplete exposure is never zero-filled."""
import json
from pathlib import Path
import re
import numpy as np
import pandas as pd

from .analysis import markdown_table, sha256
from .bond_returns import latest_source, checked_source
from .data import save_bundle

DEFAULT_SOURCE = 'https://maalot.co.il/Publications/FTS20250331162126.pdf'
# Table 4, page 9: issuer-weighted annual corporate default frequencies, 1981-2024.
CORPORATE_PD = {'AAA': 0, 'AA': .0002, 'A': .0005, 'BBB': .0014,
                'BB': .0056, 'B': .0293, 'CCC/C': .2612}


def rating_bucket(value):
    if pd.isna(value):
        return None
    text = str(value).strip().upper()
    match = re.fullmatch(r'(AAA|AA|A|BBB|BB|B|CCC|CC|C)[+-]?(?:\s+\*?[+-]?)?', text)
    if not match:
        return None
    bucket = match.group(1)
    return 'CCC/C' if bucket in {'CCC', 'CC', 'C'} else bucket


def loss_by_segment(segments):
    """Whole-portfolio weights times matched PD and LGD; require full inputs."""
    required = ['segment', 'weight_decimal', 'annual_pd_decimal', 'recovery_decimal']
    if not set(required).issubset(segments.columns):
        raise ValueError('Loss input columns are incomplete.')
    data = segments[required].copy()
    if data.empty or data.segment.duplicated().any():
        raise ValueError('Loss segments must be nonempty and unique.')
    values = data[required[1:]]
    if not np.isfinite(values).all().all() or not values.ge(0).all().all() or not values.le(1).all().all():
        raise ValueError('Weights, PD and recovery must be finite decimals between zero and one.')
    if not np.isclose(data.weight_decimal.sum(), 1, atol=1e-6, rtol=0):
        raise ValueError('Loss weights must cover the whole portfolio and sum to one.')
    data['annual_loss_contribution'] = data.weight_decimal * data.annual_pd_decimal * (1-data.recovery_decimal)
    return data, float(data.annual_loss_contribution.sum())


def spread_anchor_by_segment(segments, duration_power=0):
    """Explicit ratio sensitivity, not an assertion of JPM's unspecified formula."""
    columns = ['segment', 'weight_decimal', 'historical_spread_decimal', 'historical_duration', 'target_duration']
    if not set(columns).issubset(segments.columns):
        raise ValueError('Spread input columns are incomplete.')
    data = segments[columns].copy()
    if data.empty or data.segment.duplicated().any() or not np.isfinite(duration_power) or duration_power not in (0, 1):
        raise ValueError('Unique segments and duration-power sensitivity 0 or 1 are required.')
    if not np.isfinite(data[columns[1:]]).all().all() or (data.weight_decimal < 0).any():
        raise ValueError('Invalid spread segment values.')
    if not np.isclose(data.weight_decimal.sum(), 1, atol=1e-6, rtol=0) or (data[['historical_duration','target_duration']] <= 0).any().any():
        raise ValueError('Complete portfolio weights and positive durations are required.')
    data['duration_ratio'] = data.target_duration / data.historical_duration
    data['adjusted_spread_decimal'] = data.historical_spread_decimal * data.duration_ratio ** duration_power
    data['spread_contribution'] = data.weight_decimal * data.adjusted_spread_decimal
    return data, float(data.spread_contribution.sum())


def run_credit_review(output, constituent_bundle=None, progress=print,
                      loss_segments_path=None, spread_segments_path=None):
    prepared = {}
    for label, path in [('loss',loss_segments_path),('spread',spread_segments_path)]:
        if path:
            frame = pd.read_csv(path)
            required = {'asset_key','segment','weight_decimal','source','reference_date'}
            required.update({'annual_pd_decimal','recovery_decimal'} if label=='loss' else
                            {'historical_spread_decimal','historical_duration','target_duration'})
            if not required.issubset(frame.columns) or frame.empty or frame[list(required)].isna().any().any():
                raise ValueError('Supplied segment inputs need complete columns, source references and reference dates.')
            pd.to_datetime(frame.reference_date,errors='raise')
            for _,segments in frame.groupby('asset_key'):
                (loss_by_segment if label=='loss' else spread_anchor_by_segment)(segments)
            prepared[label]=frame
    source = Path(constituent_bundle) if constituent_bundle else latest_source(output, 'constituent-review')
    metadata = checked_source(source, 'constituent-review', ['members.csv', 'reference.csv'])
    members = pd.read_csv(source / 'members.csv')
    raw = pd.read_csv(source / 'reference.csv')
    if raw.duplicated(['ticker','field']).any():
        raise ValueError('Duplicate constituent field responses.')
    details = raw.pivot(index='ticker', columns='field', values='value')
    data = members.merge(details, left_on='security', right_index=True, how='left', validate='many_to_one')
    if data.duplicated(['key', 'security']).any() or not np.isfinite(data.weight_decimal).all() or (data.weight_decimal < 0).any():
        raise ValueError('Invalid constituent weights.')
    data['rating_bucket'] = data.RTG_SP.map(rating_bucket)
    data['resolved'] = data.ID_CUSIP.notna() & data.CRNCY.eq('USD')
    # The government category is kept separate; corporate PD is not applied to it.
    data['corporate_proxy_eligible'] = data.resolved & data.INDUSTRY_SECTOR.notna() & ~data.INDUSTRY_SECTOR.eq('Government')
    data['pd_proxy_decimal'] = data.rating_bucket.map(CORPORATE_PD).where(data.corporate_proxy_eligible)
    rows, rating_rows = [], []
    for key, sample in data.groupby('key', sort=False):
        total = sample.weight_decimal.sum()
        if not np.isclose(total, 1, atol=1e-5, rtol=0):
            raise ValueError(f'Incomplete weight list for {key}: {total}. No rescaling permitted.')
        covered = sample.pd_proxy_decimal.notna()
        eligible = sample.corporate_proxy_eligible
        for rating, group in sample.groupby('rating_bucket', dropna=False):
            rating_rows.append({'key': key, 'rating_bucket': rating, 'whole_portfolio_weight': group.weight_decimal.sum()})
        for recovery in [.2, .4, .6]:
            contribution = (sample.loc[covered,'weight_decimal'] * sample.loc[covered,'pd_proxy_decimal'] * (1-recovery)).sum()
            rows.append({'key': key, 'constituents': len(sample), 'total_weight': total,
                         'covered_corporate_weight': sample.loc[covered,'weight_decimal'].sum(),
                         'unresolved_corporate_weight': sample.loc[eligible & ~covered,'weight_decimal'].sum(),
                         'noncorporate_or_unresolved_weight': sample.loc[~eligible,'weight_decimal'].sum(),
                         'recovery_sensitivity_decimal': recovery, 'covered_loss_contribution_bps': contribution * 10000,
                         'full_portfolio_loss_bps': np.nan,
                         'status': 'partial_current_composition_proxy_not_approved_loss'})
    coverage = pd.DataFrame(rows)
    folder = save_bundle(data, coverage, output, {'kind':'credit-assumption-review',
        'status':'research_draft_not_approved', 'point_in_time_eligible':False,
        'source_bundle':str(source.resolve()), 'source_manifest_sha256':sha256(source / 'manifest.json'),
        'composition_retrieved_at_utc':metadata['retrieved_at_utc'], 'code_sha256':sha256(__file__),
        'default_study':{'source':DEFAULT_SOURCE, 'study_date':'2025-03-27', 'table':4, 'page':9,
                         'sample':'1981-2024', 'annual_pd_decimal':CORPORATE_PD,
                         'latest_study_claimed':False, 'issuer_weighted_applied_to_issue_rating_proxy':True},
        'recovery_rates_are':'20/40/60 percent illustrative sensitivities, not estimated recoveries'})
    pd.DataFrame(rating_rows).to_csv(folder / 'rating_weights.csv', index=False)
    pd.DataFrame(columns=['asset_key','segment','weight_decimal','annual_pd_decimal','recovery_decimal','source','reference_date']).to_csv(folder / 'loss_segments_template.csv', index=False)
    pd.DataFrame(columns=['asset_key','segment','weight_decimal','historical_spread_decimal','historical_duration','target_duration','source','reference_date']).to_csv(folder / 'spread_segments_template.csv', index=False)
    supplied = {}
    for label, path in [('loss',loss_segments_path),('spread',spread_segments_path)]:
        if not path:
            continue
        frame = prepared[label]
        records=[]
        for key,segments in frame.groupby('asset_key'):
            if label=='loss':
                _,estimate=loss_by_segment(segments)
                records.append({'asset_key':key,'annual_loss_decimal':estimate,
                                'annual_loss_bps':estimate*10000,'status':'supplied_inputs_not_approved'})
            else:
                for power in (0,1):
                    _,estimate=spread_anchor_by_segment(segments,power)
                    records.append({'asset_key':key,'duration_ratio_power':power,'spread_anchor_decimal':estimate,
                                    'spread_anchor_bps':estimate*10000,'status':'supplied_inputs_not_approved'})
        pd.DataFrame(records).to_csv(folder/('supplied_'+label+'_estimates.csv'),index=False)
        frame.to_csv(folder/('supplied_'+label+'_segments.csv'),index=False)
        supplied[label]={'path':str(Path(path).resolve()),'sha256':sha256(path)}
    report = ['# Composition-Aware Credit Review','',
              'Current October 7 composition, NOT September 30 historical weights. No existing return forecast was modified.','',
              markdown_table(coverage),'',
              'Loss contribution applies the published 1981-2024 corporate issuer default frequencies to covered issue-rating exposures. '
              'This rating/population mismatch, recovery assumptions, market-value versus par weighting and index exits need review. '
              'Government and other unresolved exposures are NOT assigned zero loss. Full portfolio losses remain unavailable. '
              'Government-related entities outside the Government industry category can still be misclassified by this coarse proxy. '
              'No unresolved exposure is rescaled away. No corporate default table is applied to EM sovereign debt.','',
              'US Aggregate and Global ex-USD membership returned 2,500 rows without usable weights; complete weighted exports are still needed. '
              'Segment spread histories are also needed before composition-aware spread anchors can be estimated. Templates are included.','',
              '$$',r'\ell=\sum_j w_j\,PD_j\,(1-RR_j)','$$','',
              f'[S&P corporate default study, Table 4]({DEFAULT_SOURCE})','']
    (folder / 'run_summary.md').write_text('\n'.join(report), encoding='utf-8')
    manifest = folder / 'manifest.json'
    info = json.loads(manifest.read_text())
    info['supplied_segment_inputs'] = supplied
    info['output_sha256'] = {p.name:sha256(p) for p in folder.iterdir() if p.name != 'manifest.json'}
    manifest.write_text(json.dumps(info, indent=2), encoding='utf-8')
    if progress:
        progress(f'Saved composition-aware credit review: {folder}')
        progress(markdown_table(coverage))
    return folder
