"""Comparable historical-initialization surfaces for the current anchor model."""
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
from .analysis import markdown_table, sha256
from .bond_returns import checked_source, latest_source
from .curve_projection import convergence_options, project_par_curve

MESH_CONTOURS = {axis: {'show': True, 'start': 0, 'end': 30, 'size': 2,
                       'color': 'rgba(20,30,35,0.55)', 'width': 1,
                       'highlight': False, 'usecolormap': False} for axis in ('x', 'y')}


def scenario_yield_range(values):
    values = np.asarray(values, dtype=float)
    if not values.size or not np.isfinite(values).all():
        raise ValueError('Yield-axis limits need nonempty finite surface values.')
    low, high = float(values.min()), float(values.max())
    padding = max(.1, (high - low) * .05)
    return [float(np.floor((low - padding) * 10) / 10),
            float(np.ceil((high + padding) * 10) / 10)]


def select_starting_curve(history, date, keys):
    date = pd.Timestamp(date)
    rows = history[(history.date == date) & history.key.isin(keys)].copy()
    if set(rows.key) != set(keys) or rows.key.duplicated().any():
        raise ValueError(f'No complete common-date curve for {date.date()}; monthly archive dates must match exactly.')
    if not rows.verified.eq(True).all() or not rows.curve_type.eq('par').all() or not np.isfinite(rows.rate_decimal).all():
        raise ValueError('Historical starting curves must contain verified finite par yields.')
    return rows.sort_values('maturity_years').reset_index(drop=True)


def surface_arrays(paths, maturity_points=100):
    wide = paths.pivot(index='horizon_years', columns='maturity_years', values='yield_percent').sort_index()
    if wide.empty or wide.isna().any().any():
        raise ValueError('Every surface needs a complete horizon/maturity grid.')
    x = np.unique(np.concatenate([wide.columns.to_numpy(), np.linspace(wide.columns.min(), wide.columns.max(), maturity_points)]))
    # This interpolation is a rendering convenience, not a pricing/zero-curve bootstrap.
    z = np.array([np.interp(x, wide.columns, row) for row in wide.to_numpy()])
    return x, wide.index.to_numpy(), z


def historical_surface_grid(history, maturity_points=100):
    """Interpolate within same-date maturity brackets, never across dates or beyond endpoints."""
    data = history.copy()
    required = {'date', 'maturity_years', 'rate_decimal', 'curve_type', 'verified'}
    if data.empty or not required.issubset(data.columns):
        raise ValueError('Historical par observations are missing.')
    data['date'] = pd.to_datetime(data.date, errors='raise')
    if data.date.isna().any() or not data.curve_type.eq('par').all() or not data.verified.eq(True).all():
        raise ValueError('Historical observations need valid dates and verified par-curve definitions.')
    if (not np.isfinite(data.maturity_years).all() or (data.maturity_years <= 0).any()
            or np.isinf(data.rate_decimal).any() or data.duplicated(['date', 'maturity_years']).any()):
        raise ValueError('Historical maturities must be unique per date, positive and finite; yields cannot be infinite.')
    data['month'] = data.date.dt.to_period('M')
    latest = data.groupby('month').date.max()
    common_date = data.month.map(latest)
    excluded = data[data.date != common_date].copy()
    excluded['exclusion_reason'] = 'earlier_than_common_monthly_observation_date'
    selected = data[data.date == common_date].copy()
    maturities = np.sort(data.maturity_years.unique())
    grid = np.unique(np.concatenate([maturities, np.linspace(maturities.min(), maturities.max(), maturity_points)]))
    records = []
    for month in pd.period_range(data.month.min(), data.month.max(), freq='M'):
        rows = selected[(selected.month == month) & selected.rate_decimal.notna()].sort_values('maturity_years')
        date = latest.get(month, pd.NaT)
        observed_x, observed_y = rows.maturity_years.to_numpy(), rows.rate_decimal.to_numpy() * 100
        for maturity in grid:
            matched = np.flatnonzero(np.isclose(observed_x, maturity, rtol=0, atol=1e-10))
            value, left, right, status = np.nan, np.nan, np.nan, 'unavailable'
            if len(matched):
                index = matched[0]
                value, left, right, status = observed_y[index], observed_x[index], observed_x[index], 'observed'
            elif len(observed_x) >= 2 and observed_x[0] < maturity < observed_x[-1]:
                index = np.searchsorted(observed_x, maturity)
                left, right = observed_x[index - 1], observed_x[index]
                value = float(np.interp(maturity, observed_x, observed_y))
                status = 'interpolated_same_date_maturity'
            records.append({'month': str(month), 'date': date, 'calendar_year': month.year + (month.month - 1) / 12,
                            'maturity_years': maturity, 'yield_percent': value, 'status': status,
                            'left_maturity_years': left, 'right_maturity_years': right})
    return pd.DataFrame(records), excluded


def historical_surface_figure(grid):
    import plotly.graph_objects as go
    values = grid.pivot(index='calendar_year', columns='maturity_years', values='yield_percent').sort_index()
    statuses = grid.pivot(index='calendar_year', columns='maturity_years', values='status').reindex_like(values)
    date_labels = grid.assign(date_label=grid.date.map(lambda d: str(pd.Timestamp(d).date()) if pd.notna(d) else 'No observation'))
    dates = date_labels.pivot(index='calendar_year', columns='maturity_years', values='date_label').reindex_like(values)
    z = values.to_numpy()
    finite = z[np.isfinite(z)]
    z_range = scenario_yield_range(finite)
    low, high = float(finite.min()), float(finite.max())
    if low == high:
        low, high = z_range
    year_min, year_max = float(values.index.min()), float(values.index.max())
    year_ticks = [int(np.ceil(year_min)), *range(int(np.ceil(year_min / 5) * 5), int(year_max) + 1, 5), int(year_max)]
    fig = go.Figure(go.Surface(x=values.columns.to_numpy(), y=values.index.to_numpy(), z=z,
        customdata=np.stack([dates.to_numpy(), statuses.to_numpy()], axis=-1),
        connectgaps=False, colorscale='Viridis', cmin=low, cmax=high, cauto=False,
        contours={'x': dict(MESH_CONTOURS['x']), 'y': {**MESH_CONTOURS['y'],
            'start': np.floor(year_min), 'end': np.ceil(year_max), 'size': 2}},
        colorbar={'title': 'Yield (%)', 'len': .7},
        hovertemplate='Date: %{customdata[0]}<br>Maturity: %{x:.2f}y<br>Par yield: %{z:.2f}%<br>%{customdata[1]}<extra></extra>'))
    fig.update_layout(title=f'Historical Treasury Par Yield Curves | {grid.month.min()} to {grid.month.max()}',
        height=760, margin={'l': 25, 'r': 70, 't': 75, 'b': 70},
        scene={'xaxis': {'title': 'Maturity', 'tickvals': [1/12, 2, 5, 10, 20, 30],
                         'ticktext': ['1M', '2Y', '5Y', '10Y', '20Y', '30Y']},
               'yaxis': {'title': 'Historical year', 'tickvals': sorted(set(year_ticks)), 'tickformat': '.0f'},
               'zaxis': {'title': 'Par yield (%)', 'range': z_range, 'autorange': False},
               'aspectratio': {'x': 1.35, 'y': 1.65, 'z': .9}},
        annotations=[{'x': .5, 'y': -.06, 'xref': 'paper', 'yref': 'paper', 'showarrow': False,
            'text': 'Monthly observed curves; missing interior maturities interpolated on the same date.<br>'
                    'Hover distinguishes observations and interpolation. No endpoint extrapolation or time filling.'}])
    return fig


def render_surfaces(paths, scenarios, half_lives, folder, linear_start, anchor_year, historical_grid=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from matplotlib.cm import ScalarMappable
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go

    low = np.floor(paths.yield_percent.min() * 2) / 2
    high = np.ceil(paths.yield_percent.max() * 2) / 2
    if high <= low:
        high = low + .5
    norm = Normalize(low, high)
    maturities = [1 / 12, 2, 5, 10, 30]
    ticks = ['1M', '2Y', '5Y', '10Y', '30Y']
    # Quarterly display meshes reduce rendering cost; stored projections remain monthly.
    display = paths[np.isclose(paths.horizon_years * 4, (paths.horizon_years * 4).round())]
    def draw(rows, filename, height):
        fig = plt.figure(figsize=(18, height), facecolor='white')
        for i, row in enumerate(rows):
            for j, half in enumerate(half_lives):
                ax = fig.add_subplot(len(rows), len(half_lives), i * len(half_lives) + j + 1, projection='3d')
                data = display[(display.starting_scenario == row['id']) & (display.half_life_years == half)]
                x, y, z = surface_arrays(data)
                xx, yy = np.meshgrid(x, y)
                ax.plot_surface(xx, yy, z, cmap='viridis', norm=norm, rcount=len(y), ccount=len(x), linewidth=0, antialiased=True, alpha=.94)
                ax.plot(x, np.zeros(len(x)), z[0], color='#161616', linewidth=2.0)
                ax.plot(x, np.full(len(x), anchor_year), z[-1], color='#a82032', linewidth=2.0)
                at = np.where(np.isclose(y, linear_start))[0]
                if len(at):
                    ax.plot(x, np.full(len(x), linear_start), z[at[0]], color='#fafafa', linewidth=1.3, linestyle='--')
                ax.set(xlim=(0, 30), ylim=(0, 30), zlim=(low, high),
                       xlabel='Maturity', ylabel='Projection year', zlabel='Par yield (%)')
                ax.set_xticks(maturities, ['1M', '\n2Y', '5Y', '10Y', '30Y'])
                ax.set_yticks([0, 10, 20, 25, 30])
                ax.tick_params(labelsize=8, pad=0)
                ax.xaxis.label.set_size(9); ax.yaxis.label.set_size(9); ax.zaxis.label.set_size(9)
                ax.set_title(f'{row["date"]} | {row["label"]}\nHalf-life: {half:g} years', fontsize=11, pad=8)
                ax.view_init(elev=27, azim=-125)
                ax.set_box_aspect((1.3, 1.3, .75))
        fig.suptitle('Treasury Par Curve Convergence', fontsize=20, y=.985)
        fig.text(.5, .92 if len(rows) == 1 else .971,
                 'Exponential through year 25; linear landing at year 30. Shared current anchors and scales.', ha='center', fontsize=11)
        fig.text(.48, .018, 'Black: observed starting curve     Dashed white: year 25     Red: year-30 anchor', ha='center', fontsize=10)
        fig.subplots_adjust(left=.01, right=.92, top=.76 if len(rows) == 1 else .94, bottom=.07 if len(rows) == 1 else .035,
                            wspace=.02, hspace=.23)
        bar = fig.add_axes([.948, .2, .012, .57])
        fig.colorbar(ScalarMappable(norm=norm, cmap='viridis'), cax=bar, label='Par yield (%)')
        fig.savefig(folder / filename, dpi=180)
        plt.close(fig)
    draw(scenarios, 'yield_curve_surface_grid.png', 4.3 * len(scenarios) + 1.2)
    draw(scenarios[:1], 'current_curve_surfaces.png', 6.1)

    interactive = make_subplots(rows=1, cols=len(half_lives), specs=[[{'type': 'surface'} for _ in half_lives]],
        subplot_titles=[f'{half:g}-year half-life' for half in half_lives], horizontal_spacing=.04)
    meshes = {}
    for row in scenarios:
        meshes[row['id']] = [surface_arrays(display[(display.starting_scenario == row['id']) &
                              (display.half_life_years == half)], 60) for half in half_lives]
    z_ranges = {row['id']: scenario_yield_range(display.loc[
        display.starting_scenario == row['id'], 'yield_percent']) for row in scenarios}
    color_ranges = {}
    for row in scenarios:
        values = display.loc[display.starting_scenario == row['id'], 'yield_percent']
        limits = [float(values.min()), float(values.max())]
        color_ranges[row['id']] = limits if limits[0] < limits[1] else z_ranges[row['id']]
    initial_color = color_ranges[scenarios[0]['id']]
    for j, (x, y, z) in enumerate(meshes[scenarios[0]['id']], 1):
        interactive.add_trace(go.Surface(x=x, y=y, z=z, colorscale='Viridis',
            cmin=initial_color[0], cmax=initial_color[1], cauto=False,
            contours=MESH_CONTOURS,
            showscale=j == len(half_lives), colorbar={'title': 'Yield (%)', 'len': .65},
            hovertemplate='Maturity: %{x:.2f}y<br>Projection: %{y:.2f}y<br>Par yield: %{z:.2f}%<extra></extra>'), row=1, col=j)
    scenes = {}
    for j in range(1, len(half_lives) + 1):
        scenes['scene' if j == 1 else f'scene{j}'] = {
            'xaxis': {'title': 'Maturity', 'tickvals': maturities, 'ticktext': ticks, 'range': [0, 30]},
            'yaxis': {'title': 'Projection year', 'range': [0, 30]},
            'zaxis': {'title': 'Par yield (%)', 'range': z_ranges[scenarios[0]['id']], 'autorange': False},
            'aspectratio': {'x': 1.2, 'y': 1.2, 'z': .8}}
    buttons = []
    for row in scenarios:
        mesh = meshes[row['id']]
        layout_update = {'title': f'Treasury Par Curves: {row["date"]} - {row["label"]}'}
        for scene in scenes:
            layout_update[f'{scene}.zaxis.range'] = z_ranges[row['id']]
            layout_update[f'{scene}.zaxis.autorange'] = False
        buttons.append({'label': f'{row["date"]} - {row["label"]}', 'method': 'update',
                        'args': [{'x': [m[0] for m in mesh], 'y': [m[1] for m in mesh], 'z': [m[2] for m in mesh],
                                  'cmin': [color_ranges[row['id']][0]] * len(half_lives),
                                  'cmax': [color_ranges[row['id']][1]] * len(half_lives),
                                  'cauto': [False] * len(half_lives)},
                                 layout_update]})
    interactive.update_layout(**scenes, title=f'Treasury Par Curves: {scenarios[0]["date"]} - Current curve',
        height=730, margin={'l': 20, 'r': 65, 't': 145, 'b': 30},
        updatemenus=[{'buttons': buttons, 'x': 0, 'y': 1.17, 'xanchor': 'left', 'yanchor': 'top'},
                    {'type': 'buttons', 'direction': 'right', 'x': .62, 'y': 1.17,
                     'xanchor': 'left', 'yanchor': 'top', 'active': 0,
                     'buttons': [{'label': 'Mesh On', 'method': 'restyle',
                                  'args': [{'contours.x.show': True, 'contours.y.show': True}]},
                                 {'label': 'Mesh Off', 'method': 'restyle',
                                  'args': [{'contours.x.show': False, 'contours.y.show': False}]}]}],
        annotations=list(interactive.layout.annotations) + [dict(x=.5, y=-.03, xref='paper', yref='paper', showarrow=False,
            text='Observed historical starting curves; shared current-vintage anchors. Not historical forecasts.<br>'
                 'Z and color ranges fit the selected scenario and are shared across its half-life panels.')])
    if historical_grid is None:
        interactive.write_html(folder / 'interactive_curve_surfaces.html', include_plotlyjs=True, full_html=True)
    else:
        historical = historical_surface_figure(historical_grid)
        forecast_html = interactive.to_html(full_html=False, include_plotlyjs=True, div_id='projected-surfaces')
        history_html = historical.to_html(full_html=False, include_plotlyjs=False, div_id='historical-yields')
        html = ('<!DOCTYPE html><html><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>Treasury Yield Curve Surfaces</title></head><body style="margin:0">'
                f'{forecast_html}<hr style="border:0;border-top:1px solid #ddd">{history_html}</body></html>')
        (folder / 'interactive_curve_surfaces.html').write_text(html, encoding='utf-8')
        wide = historical_grid.pivot(index='calendar_year', columns='maturity_years', values='yield_percent').sort_index()
        xx, yy = np.meshgrid(wide.columns.to_numpy(), wide.index.to_numpy())
        finite = wide.to_numpy()[np.isfinite(wide.to_numpy())]
        fig = plt.figure(figsize=(13, 8))
        ax = fig.add_subplot(projection='3d')
        ax.plot_surface(xx, yy, wide.to_numpy(), cmap='viridis', rcount=len(wide), ccount=len(wide.columns), linewidth=0)
        ax.set(xlabel='Maturity (years)', ylabel='Historical year', zlabel='Par yield (%)', zlim=scenario_yield_range(finite))
        ax.set_xticks([1/12, 2, 5, 10, 20, 30], ['1M', '\n2Y', '5Y', '10Y', '20Y', '30Y'])
        ax.view_init(elev=27, azim=-125)
        ax.set_box_aspect((1.35, 1.65, .9))
        fig.suptitle(f'Historical Treasury Par Curves: {historical_grid.month.min()} to {historical_grid.month.max()}', y=.97, fontsize=15)
        fig.text(.5, .025, 'Same-date maturity interpolation only; missing endpoints remain gaps.', ha='center', fontsize=10)
        fig.savefig(folder / 'historical_yield_surface.png', dpi=160)
        plt.close(fig)


def run_curve_surfaces(output, surface_settings, curve_bundle=None, treasury_bundle=None, progress=print):
    config = json.loads(Path(surface_settings).read_text())
    if config.get('status') != 'research_draft_not_approved':
        raise ValueError('Surface settings must remain research draft.')
    source = Path(curve_bundle) if curve_bundle else latest_source(output, 'curve-projection')
    cm = checked_source(source, 'curve-projection', ['projected_par_curves.csv'])
    projection = cm['projection_settings']
    options = convergence_options(projection)
    if options != {'linear_start_year': 25, 'anchor_year': 30} or config['display_horizon_years'] != 30:
        raise ValueError('Surface comparison requires the requested 25-to-30 linear landing and 30-year display.')
    half_lives = projection['half_life_scenarios_years']
    if half_lives != [3, 5, 10]:
        raise ValueError('Run the updated curve projection with 3/5/10-year half-lives first.')
    review = Path(cm['review_bundle'])
    if sha256(review / 'manifest.json') != cm['review_manifest_sha256']:
        raise ValueError('Underlying review manifest checksum mismatch.')
    rm = checked_source(review, 'anchor-review', ['starting_par_curve.csv', 'candidate_anchors.csv'])
    history_source = Path(treasury_bundle) if treasury_bundle else Path(rm['treasury_bundle'])
    history_meta = json.loads((history_source / 'manifest.json').read_text())
    if history_meta.get('kind') != 'treasury_par_history':
        raise ValueError('Historical source must be an official Treasury par-history archive.')
    if treasury_bundle is None and sha256(history_source / 'observations.csv') != rm['treasury_observations_sha256']:
        raise ValueError('Treasury source checksum mismatch.')
    history = pd.read_csv(history_source / 'observations.csv', parse_dates=['date'])
    starting = pd.read_csv(review / 'starting_par_curve.csv', parse_dates=['date'])
    anchors = pd.read_csv(review / 'candidate_anchors.csv')
    keys = config['keys']
    if not keys or len(set(keys)) != len(keys):
        raise ValueError('Surface nodes must be nonempty and unique.')
    candidate = cm['anchor_settings']['primary_candidate']
    anchors = anchors[(anchors.candidate == candidate) & anchors.key.isin(keys)]
    current_date = str(starting.date.iloc[0].date())
    history = history[history.date <= pd.Timestamp(current_date)].copy()
    historical_grid, excluded_history = historical_surface_grid(history)
    scenarios = [{'id': 'current', 'date': current_date, 'label': 'Current curve'},
                 *[{'id': f'historical_{i+1}', **row} for i, row in enumerate(config['historical_scenarios'])]]
    if len({s['date'] for s in scenarios}) != len(scenarios):
        raise ValueError('Starting-scenario dates must be unique.')
    horizons = np.arange(30 * 12 + 1) / 12
    rows, inputs, diagnostics = [], [], []
    for i, scenario in enumerate(scenarios):
        selected = select_starting_curve(starting if i == 0 else history, scenario['date'], keys)
        inputs.append(selected.assign(starting_scenario=scenario['id'], starting_label=scenario['label']))
        rates = selected.set_index('key').rate_decimal
        diagnostics.append({**scenario, 'cash_percent': rates['BC_1MONTH'] * 100,
            'two_year_percent': rates['BC_2YEAR'] * 100, 'ten_year_percent': rates['BC_10YEAR'] * 100,
            'thirty_year_percent': rates['BC_30YEAR'] * 100, '10y_minus_2y_bps': (rates['BC_10YEAR'] - rates['BC_2YEAR']) * 10000})
        for half in half_lives:
            rows.append(project_par_curve(selected, anchors, candidate, horizons, half, **options).assign(
                starting_scenario=scenario['id'], starting_label=scenario['label'], starting_date=scenario['date']))
    paths = pd.concat(rows, ignore_index=True)
    stamp = datetime.now(timezone.utc)
    folder = Path(output) / (stamp.strftime('%Y%m%dT%H%M%S') + '_curve-surfaces_' + uuid4().hex[:8])
    folder.mkdir(parents=True)
    paths.to_csv(folder / 'scenario_par_curves.csv', index=False)
    pd.concat(inputs, ignore_index=True).to_csv(folder / 'starting_scenario_curves.csv', index=False)
    pd.DataFrame(diagnostics).to_csv(folder / 'starting_curve_diagnostics.csv', index=False)
    historical_grid.to_csv(folder / 'historical_surface_grid.csv', index=False)
    excluded_history.to_csv(folder / 'historical_excluded_quotes.csv', index=False)
    historical_coverage = historical_grid.groupby(['month', 'status']).size().unstack(fill_value=0).reset_index()
    historical_coverage.to_csv(folder / 'historical_surface_coverage.csv', index=False)
    render_surfaces(paths, scenarios, half_lives, folder, 25, 30, historical_grid)
    report = ['# Yield Curve Surface Comparison', '',
        f'{len(scenarios)} starting scenarios by 3 half-lives (3, 5, 10 years). Current curve first: {current_date}.', '',
        'X: maturity in years. Y: projection years 0-30. Z and color: par yield percent. All panels use identical scales. '
        'The five modeled nodes are 1 month, 2, 5, 10 and 30 years; linear maturity interpolation is display-only.', '',
        markdown_table(pd.DataFrame(diagnostics)), '',
        'Historical curves are exact common-date archived observations. No separate-node carry-forward or missing-node substitution '
        'is used. Historical starting curves converge to the SAME current-vintage median20 anchors. These are initialization '
        'stress scenarios, not point-in-time forecasts or a forecast-performance backtest.', '',
        'Exponential through year 25; straight-line interpolation of the remaining gap from year 25 to the exact year-30 anchor. '
        'Levels are continuous at year 25, but slopes generally change. Beyond year 30 the production curve remains at the anchor.', '',
        '![All scenarios](yield_curve_surface_grid.png)', '',
        '![Current curve](current_curve_surfaces.png)', '',
        '[Interactive three-column view](interactive_curve_surfaces.html): select a starting scenario and rotate/zoom the surfaces. '
        'Plotly is embedded; no internet connection is needed. Mesh lines follow maturity and projection-year '
        'directions at two-year intervals. Mesh On/Off controls retain the scenario selection. '
        'Interactive Z limits fit the selected starting scenario with a small margin and remain equal across '
        'its three half-life panels. Interactive colors span the selected scenario\'s actual yield extrema, shared '
        'across half-lives. Static grid axes and color scales remain fixed for cross-scenario comparison.', '',
        '## Historical Surface', '',
        f'The bottom HTML panel contains {historical_grid.month.nunique()} monthly historical curves from '
        f'{historical_grid.month.min()} through {historical_grid.month.max()}, using all available archived Treasury maturities. '
        'Missing interior nodes are interpolated linearly between same-date maturities. Observed nodes are retained exactly. '
        'No extrapolation, time interpolation or carry-forward is applied. Different-date quotes within a month are excluded '
        'rather than combined with its latest common observation date.', '',
        markdown_table(historical_grid.status.value_counts().rename_axis('status').reset_index(name='grid_points')), '',
        f'Excluded earlier-date quotes: {len(excluded_history)}. Source values remain in the original archive.', '',
        '![Historical surface](historical_yield_surface.png)', '']
    (folder / 'run_summary.md').write_text('\n'.join(report), encoding='utf-8')
    meta = {'kind': 'curve-surfaces', 'retrieved_at_utc': stamp.isoformat(), 'status': 'research_counterfactual_initialization',
        'point_in_time_eligible': False, 'candidate': candidate, 'settings': config, 'settings_sha256': sha256(surface_settings),
        'curve_bundle': str(source.resolve()), 'curve_manifest_sha256': sha256(source / 'manifest.json'),
        'treasury_bundle': str(history_source.resolve()), 'treasury_observations_sha256': sha256(history_source / 'observations.csv'),
        'code_sha256': sha256(__file__), 'projection_code_sha256': sha256(Path(__file__).with_name('curve_projection.py')),
        'scenarios': scenarios, 'interpolation': 'piecewise_linear_par_yields_display_only',
        'interactive_z_axis': 'scenario_shared_range_with_5pct_or_0.1pp_padding_rounded_outward_to_0.1pp',
        'interactive_color_scale': 'scenario_shared_actual_yield_extrema_with_padded_fallback_for_flat_surface',
        'historical_interpolation': 'same_date_linear_interior_maturities_only_no_endpoint_extrapolation_no_time_fill',
        'historical_months': int(historical_grid.month.nunique()),
        'output_sha256': {p.name: sha256(p) for p in folder.iterdir()}}
    (folder / 'manifest.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    if progress:
        progress(f'Saved {len(scenarios)} x 3 surface comparison: {folder}')
    return folder
