"""QuantLib rolling Treasury holding returns, not credit-index replicas."""
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4
import numpy as np
import pandas as pd
from .analysis import sha256, markdown_table
from .bond_returns import latest_source, checked_source


def qdate(timestamp):
    import QuantLib as ql
    date = pd.Timestamp(timestamp)
    return ql.Date(date.day, date.month, date.year)


def schedule(start, maturity):
    import QuantLib as ql
    return ql.Schedule(start, maturity, ql.Period(6,ql.Months), ql.NullCalendar(),
                       ql.Unadjusted, ql.Unadjusted, ql.DateGeneration.Backward, False)


def discount_curve(nodes, reference):
    """Bootstrap synthetic par quotes using explicit research conventions."""
    import QuantLib as ql
    nodes = nodes.sort_values('maturity_years')
    if nodes.maturity_years.duplicated().any() or not np.isfinite(nodes[['maturity_years','rate_decimal']]).all().all():
        raise ValueError('Curve maturities must be unique and finite.')
    if (nodes.maturity_years <= 0).any() or not nodes.curve_type.eq('par').all():
        raise ValueError('Positive par-curve maturities are required; no par-as-zero substitution.')
    months = nodes.maturity_years.to_numpy() * 12
    if not np.allclose(months, np.round(months), atol=1e-8):
        raise ValueError('Synthetic instruments require whole-month maturities.')
    helpers = []
    daycount = ql.Actual365Fixed()
    for row in nodes.itertuples(index=False):
        months = int(round(row.maturity_years * 12))
        quote = ql.QuoteHandle(ql.SimpleQuote(row.rate_decimal))
        if months < 12:
            helper = ql.DepositRateHelper(quote,ql.Period(months,ql.Months),0,
                                         ql.NullCalendar(),ql.Unadjusted,False,daycount)
        else:
            maturity = reference + ql.Period(months,ql.Months)
            helper = ql.FixedRateBondHelper(ql.QuoteHandle(ql.SimpleQuote(100)),0,100,
                                            schedule(reference,maturity),[row.rate_decimal],daycount,ql.Unadjusted)
        helpers.append(helper)
    curve = ql.PiecewiseLogLinearDiscount(reference,helpers,daycount)
    discounts = [curve.discount(helper.pillarDate()) for helper in helpers]
    if not np.isfinite(discounts).all() or min(discounts) <= 0:
        raise ValueError('Bootstrap produced invalid discount factors.')
    return curve


def holding_period(start_nodes, end_nodes, start_date, tenor_years):
    """Buy a synthetic par bond, collect coupons, sell the aged bond after one year."""
    import QuantLib as ql
    if type(tenor_years) is not int or tenor_years <= 1:
        raise ValueError('Holding-period tenor must be an integer greater than one year.')
    original = ql.Settings.instance().evaluationDate
    start = qdate(start_date)
    end = start + ql.Period(1,ql.Years)
    try:
        ql.Settings.instance().evaluationDate = start
        curve0 = discount_curve(start_nodes,start)
        tenor = start_nodes[start_nodes.maturity_years == tenor_years]
        if len(tenor) != 1:
            raise ValueError('Synthetic bond coupon requires an observed par tenor.')
        coupon = float(tenor.rate_decimal.iloc[0])
        bond = ql.FixedRateBond(0,100,schedule(start,start+ql.Period(tenor_years,ql.Years)),
                                [coupon],ql.Actual365Fixed(),ql.Unadjusted)
        bond.setPricingEngine(ql.DiscountingBondEngine(ql.YieldTermStructureHandle(curve0)))
        initial_price = bond.dirtyPrice()
        if not np.isclose(initial_price,100,atol=1e-6):
            raise ValueError('Bootstrap does not reprice the synthetic starting par bond.')
        # Coupon on the sale date is received as cash, not included a second time in sale value.
        coupons = sum(flow.amount() for flow in bond.cashflows() if start < flow.date() <= end)
        ql.Settings.instance().evaluationDate = end
        frozen = discount_curve(start_nodes,end)
        bond.setPricingEngine(ql.DiscountingBondEngine(ql.YieldTermStructureHandle(frozen)))
        frozen_price = bond.dirtyPrice()
        ending = discount_curve(end_nodes,end)
        bond.setPricingEngine(ql.DiscountingBondEngine(ql.YieldTermStructureHandle(ending)))
        final_price = bond.dirtyPrice()
        income = coupons / initial_price
        aging = (frozen_price-initial_price)/initial_price
        normalization = (final_price-frozen_price)/initial_price
        result = {'initial_dirty_price':initial_price,'coupon_cash':coupons,'frozen_curve_sale_dirty_price':frozen_price,
                  'sale_dirty_price':final_price,'coupon_return':income,
                  'frozen_curve_aging_return':aging,'normalization_return':normalization,
                  'holding_return':income+aging+normalization}
        if not np.isfinite(list(result.values())).all() or result['holding_return'] <= -1:
            raise ValueError('Invalid holding return.')
        return result
    finally:
        ql.Settings.instance().evaluationDate = original


def run_holding_returns(output, curve_bundle=None, progress=print):
    try:
        import QuantLib as ql
    except ImportError as exc:
        raise RuntimeError('Install the pricing extra in my_env: pip install -e ".[pricing]"') from exc
    source = Path(curve_bundle) if curve_bundle else latest_source(output,'curve-projection')
    metadata = checked_source(source,'curve-projection',['projected_par_curves.csv'])
    review = Path(metadata['review_bundle'])
    if sha256(review/'manifest.json') != metadata['review_manifest_sha256']:
        raise ValueError('Curve review checksum mismatch.')
    review_meta = json.loads((review/'manifest.json').read_text())
    start = pd.Timestamp(review_meta['common_starting_curve_date'])
    curves = pd.read_csv(source/'projected_par_curves.csv')
    rows = []
    for scenario,nodes in curves.groupby('scenario',sort=False):
        terminal = int(round(nodes.horizon_years.max()))
        for year in range(terminal):
            first = nodes[np.isclose(nodes.horizon_years,year)]
            last = nodes[np.isclose(nodes.horizon_years,year+1)]
            date = start + pd.DateOffset(years=year)
            for tenor in (2,5,10):
                rows.append({'rate_scenario':scenario,'year':year+1,'tenor_years':tenor,
                             **holding_period(first,last,date,tenor)})
    data = pd.DataFrame(rows)
    cumulative=[]
    for (scenario,tenor),sample in data.groupby(['rate_scenario','tenor_years']):
        for h in (1,5,10,20,30,40):
            selected=sample[sample.year<=h]
            if len(selected)==h:
                cumulative.append({'rate_scenario':scenario,'tenor_years':tenor,'horizon_years':h,
                                    'annualized_return':np.prod(1+selected.holding_return)**(1/h)-1})
    summary=pd.DataFrame(cumulative)
    stamp=datetime.now(timezone.utc)
    folder=Path(output)/(stamp.strftime('%Y%m%dT%H%M%S')+'_holding-returns_'+uuid4().hex[:8])
    folder.mkdir()
    data.to_csv(folder/'annual_holding_returns.csv',index=False)
    summary.to_csv(folder/'annualized_returns.csv',index=False)
    report=['# Treasury Holding-Period Return Comparison','',
            'Research comparison only: these are rolling synthetic 2/5/10-year Treasury bonds, NOT LGC3TRUU or LBUSTRUU replicas. '
            'Each year buys a new par bond and sells it after one year; semiannual coupon cash is not reinvested within that year.','',
            'QuantLib bootstraps discount factors from synthetic par instruments. Short nodes below one year use simple-rate deposits; '
            'long nodes use semiannual fixed-rate par bonds, Actual/365 Fixed, zero settlement lag and unadjusted dates. '
            'These are explicit modeling conventions, not exact Treasury market quoting conventions. No curve extrapolation is enabled.','',
            'Attribution: coupon cash plus frozen-curve aging price change plus changing-curve normalization price change. '
            'The aging term can include coupon-date/accrual effects; it is not pure roll-down for every schedule. '
            'Roll-down is already embedded in repricing; yield/12 carry and a separate duration shock must NOT be added to the total.','',
            '$$',r'R=(C+P_1-P_0)/P_0','$$','',
            markdown_table(summary[(summary.rate_scenario=='base') & summary.horizon_years.isin([1,10,30,40])]),'',
            'This does not yet replace the credit-index model. Measured sector/key-rate exposures, credit spread pricing and mortgage modeling '
            'are needed for an index-level upgrade. No standalone-bond duration is silently mapped to maturity.','',
            '[QuantLib](https://www.quantlib.org/)', '']
    (folder/'run_summary.md').write_text('\n'.join(report),encoding='utf-8')
    manifest={'kind':'holding-returns','retrieved_at_utc':stamp.isoformat(),'status':'research_comparison_not_index_forecasts',
              'point_in_time_eligible':False,'QuantLib_version':ql.__version__,'code_sha256':sha256(__file__),
              'curve_bundle':str(source.resolve()),'curve_manifest_sha256':sha256(source/'manifest.json'),
              'output_sha256':{p.name:sha256(p) for p in folder.iterdir()}}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    if progress:
        progress(f'Saved Treasury holding-return comparison: {folder}')
    return folder
