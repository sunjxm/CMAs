import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from cma_curve.credit_assumptions import rating_bucket, loss_by_segment, spread_anchor_by_segment, run_credit_review
from cma_curve.global_hedge import hedged_returns, run_global_hedge_review
from cma_curve.analysis import sha256


class CreditExtensionTests(unittest.TestCase):
    def test_rating_buckets_and_unrated_not_zero(self):
        self.assertEqual(rating_bucket('BBB-'),'BBB')
        self.assertEqual(rating_bucket('CCC+'),'CCC/C')
        self.assertEqual(rating_bucket('AA- *-'),'AA')
        for value in (None,'NR','D','Aa2','AA (sf)'):
            self.assertIsNone(rating_bucket(value))

    def segments(self):
        return pd.DataFrame({'segment':['A','B'],'weight_decimal':[.8,.2],
                             'annual_pd_decimal':[.001,.03],'recovery_decimal':[.4,.4]})

    def test_loss_formula_and_whole_portfolio_coverage(self):
        detail,total=loss_by_segment(self.segments())
        self.assertAlmostEqual(total,(.8*.001+.2*.03)*.6)
        with self.assertRaisesRegex(ValueError,'whole portfolio'):
            loss_by_segment(self.segments().iloc[:1])

    def test_missing_and_bad_recovery_rejected(self):
        for value in (np.nan,1.1,-.1):
            data=self.segments()
            data.loc[0,'recovery_decimal']=value
            with self.assertRaises(ValueError):
                loss_by_segment(data)

    def test_composition_spread_and_duration_sensitivity(self):
        data=pd.DataFrame({'segment':['A','BBB'],'weight_decimal':[.7,.3],
                            'historical_spread_decimal':[.01,.02],'historical_duration':[4,4],'target_duration':[8,4]})
        _,base=spread_anchor_by_segment(data)
        _,adjusted=spread_anchor_by_segment(data,1)
        self.assertAlmostEqual(base,.013)
        self.assertAlmostEqual(adjusted,.02)
        with self.assertRaises(ValueError):
            spread_anchor_by_segment(data.iloc[:1])

    def test_review_preserves_unknown_exposure(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'source'; source.mkdir()
            pd.DataFrame({'key':['high_yield']*2,'security':['one','two'],'weight_decimal':[.9,.1]}).to_csv(source/'members.csv',index=False)
            rows=[{'ticker':sec,'field':field,'value':value} for sec,rating in [('one','B'),('two','NR')]
                  for field,value in [('ID_CUSIP',sec),('CRNCY','USD'),('INDUSTRY_SECTOR','Financial'),('RTG_SP',rating)]]
            pd.DataFrame(rows).to_csv(source/'reference.csv',index=False)
            (source/'manifest.json').write_text(json.dumps({'kind':'constituent-review','retrieved_at_utc':'2026-10-07T00:00:00Z',
                'output_sha256':{n:sha256(source/n) for n in ['members.csv','reference.csv']}}))
            folder=run_credit_review(root,source,progress=None)
            coverage=pd.read_csv(folder/'coverage.csv')
            self.assertTrue(coverage.full_portfolio_loss_bps.isna().all())
            np.testing.assert_allclose(coverage.unresolved_corporate_weight,.1)
            supplied=self.segments().assign(asset_key='high_yield',source='unit test fixture',reference_date='2026-09-30')
            supplied.to_csv(root/'loss.csv',index=False)
            folder=run_credit_review(root,source,progress=None,loss_segments_path=root/'loss.csv')
            estimates=pd.read_csv(folder/'supplied_loss_estimates.csv')
            self.assertAlmostEqual(estimates.annual_loss_decimal.iloc[0],(.8*.001+.2*.03)*.6)


class HedgeExtensionTests(unittest.TestCase):
    def inputs(self):
        return pd.DataFrame({'date':['2026-10-31']*2,'currency':['EUR','JPY'],'weight_decimal':[.6,.4],
                             'local_return_decimal':[.01,.02],'usd_cash_decimal':[.04,.04],
                             'foreign_cash_decimal':[.02,.05]})

    def test_hedge_sign_weighting_and_units(self):
        detail,result=hedged_returns(self.inputs())
        self.assertGreater(detail.hedge_carry_decimal.iloc[0],0)
        self.assertLess(detail.hedge_carry_decimal.iloc[1],0)
        self.assertAlmostEqual(result.monthly_return.iloc[0],.6*(.01+.02/12)+.4*(.02-.01/12))

    def test_missing_currency_weights_rejected(self):
        with self.assertRaisesRegex(ValueError,'sum to one'):
            hedged_returns(self.inputs().iloc[:1])

    def test_bad_rate_and_duplicate_rejected(self):
        data=self.inputs(); data.loc[0,'usd_cash_decimal']=np.nan
        with self.assertRaises(ValueError):
            hedged_returns(data)
        with self.assertRaisesRegex(ValueError,'Unique'):
            hedged_returns(pd.concat([self.inputs(),self.inputs()]))

    def test_gap_and_inconsistent_usd_cash_rejected(self):
        data=self.inputs(); data.loc[1,'usd_cash_decimal']=.05
        with self.assertRaisesRegex(ValueError,'common USD'):
            hedged_returns(data)
        with self.assertRaisesRegex(ValueError,'Missing months'):
            hedged_returns(pd.concat([self.inputs(),self.inputs().assign(date='2026-12-31')]))

    def test_no_inputs_no_forecast(self):
        with tempfile.TemporaryDirectory() as root:
            path=run_global_hedge_review(root,progress=None)
            metadata=json.loads((path/'manifest.json').read_text())
            self.assertEqual(metadata['status'],'missing_inputs_no_forecast')
            self.assertFalse(metadata['point_in_time_eligible'])


@unittest.skipUnless(importlib.util.find_spec('QuantLib'),'Install the pricing extra for holding-return tests.')
class HoldingExtensionTests(unittest.TestCase):
    def nodes(self, slope=0):
        maturities=np.array([1/12,.25,.5,1,2,3,5,7,10,20,30])
        return pd.DataFrame({'maturity_years':maturities,'rate_decimal':.04+slope*maturities,'curve_type':'par'})

    def test_flat_curve_coupon_and_attribution(self):
        from cma_curve.holding_returns import holding_period
        result=holding_period(self.nodes(),self.nodes(),'2026-09-30',5)
        self.assertAlmostEqual(result['initial_dirty_price'],100,places=6)
        self.assertAlmostEqual(result['holding_return'],.04,places=5)
        self.assertAlmostEqual(result['normalization_return'],0)
        self.assertAlmostEqual(result['holding_return'],sum(result[k] for k in
            ['coupon_return','frozen_curve_aging_return','normalization_return']))

    def test_upward_curve_aging_and_rate_shock(self):
        from cma_curve.holding_returns import holding_period
        start=self.nodes(.001)
        result=holding_period(start,start,'2026-09-30',5)
        self.assertGreater(result['frozen_curve_aging_return'],0)
        shock=holding_period(start,start.assign(rate_decimal=start.rate_decimal+.01),'2026-09-30',5)
        self.assertLess(shock['normalization_return'],0)

    def test_settings_restored_and_par_as_zero_rejected(self):
        import QuantLib as ql
        from cma_curve.holding_returns import holding_period
        original=ql.Settings.instance().evaluationDate
        with self.assertRaisesRegex(ValueError,'par-curve'):
            holding_period(self.nodes().assign(curve_type='zero'),self.nodes(),'2026-09-30',5)
        self.assertEqual(original,ql.Settings.instance().evaluationDate)
