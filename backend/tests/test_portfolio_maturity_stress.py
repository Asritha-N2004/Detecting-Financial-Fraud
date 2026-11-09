from datetime import date,timedelta
from copy import deepcopy
import asyncio
import numpy as np
import pytest
from pydantic import ValidationError
from app.schemas.domain import AssessmentInput,DebtSchedule
from app.providers.synthetic import synthetic
from app.financial_engine.portfolio_risk import portfolio_risk
from app.financial_engine.liquidity_risk import maturity_analysis
from app.financial_engine.stress_testing import stress
from app.agents.analysts import analyze,DIMENSIONS
from app.agents.critic import review
from app.financial_engine.scoring import aggregate
from app.orchestration.workflow import run_workflow


def test_covariance_against_independent_centered_matrix_and_weighted_returns():
    data=synthetic();report=portfolio_risk(data)
    p=np.array([[r.close for r in h.prices] for h in data.portfolio_holdings]).T
    r=p[1:]/p[:-1]-1;w=np.array([h.weight for h in data.portfolio_holdings])
    centered=r-r.mean(axis=0);expected=centered.T@centered/(len(r)-1)
    assert np.allclose(report['covariance'],expected,rtol=1e-12)
    assert np.allclose(report['annualized_covariance'],expected*252)
    vol=np.std(r@w,ddof=1)
    assert report['metrics']['daily_volatility'].value==pytest.approx(vol)
    assert report['metrics']['portfolio_variance'].value==pytest.approx(vol**2)
    assert sum(c['daily_volatility_contribution'] for c in report['risk_contributions'])==pytest.approx(vol)
    assert sum(c['variance_share'] for c in report['risk_contributions'])==pytest.approx(1)
    assert report['metrics']['portfolio_value_var'].value==pytest.approx(report['metrics']['historical_var'].value*data.portfolio_value)


def test_singular_and_constant_constituents_are_finite_and_explicit():
    raw=synthetic().model_dump(mode='json')
    for holding in raw['portfolio_holdings']:
        for price in holding['prices']:price['close']=100
    report=portfolio_risk(AssessmentInput.model_validate(raw))
    assert report['status']=='completed' and report['metrics']['portfolio_variance'].value==0
    assert report['metrics']['diversification_ratio'].value is None
    assert all(v is None for row in report['correlation'] for v in row)
    assert all(c['variance_share'] is None for c in report['risk_contributions'])


def test_negative_covariance_can_produce_a_negative_risk_contribution():
    raw=synthetic().model_dump(mode='json');raw['portfolio_holdings']=raw['portfolio_holdings'][:2];raw['portfolio_weights']=[.8,.2]
    for i,h in enumerate(raw['portfolio_holdings']):
        h['weight']=[.8,.2][i]
        returns=np.array([.01,-.01,.02,-.02]*126)*(1 if i==0 else -.5)
        values=np.r_[100,100*np.cumprod(1+returns)]
        for row,value in zip(h['prices'],values):row['close']=float(value)
    r=portfolio_risk(AssessmentInput.model_validate(raw))
    assert r['risk_contributions'][1]['annualized_volatility_contribution']<0
    assert sum(c['variance_share'] for c in r['risk_contributions'])==pytest.approx(1)


def test_alignment_and_insufficient_history_never_fall_back_to_single_asset():
    raw=synthetic().model_dump(mode='json');raw['portfolio_holdings'][0]['prices'].pop()
    data=AssessmentInput.model_validate(raw)
    out=analyze('market',data)
    assert out.status=='incomplete' and out.score is None
    assert 'calendars' in out.analytics['portfolio']['limitations'][0]
    raw=synthetic().model_dump(mode='json')
    for h in raw['portfolio_holdings']:h['prices']=h['prices'][:10]
    assert portfolio_risk(AssessmentInput.model_validate(raw))['status']=='unavailable'
    data=synthetic();data.portfolio_holdings=[];data.assessment_type='portfolio'
    assert analyze('market',data).score is None


@pytest.mark.parametrize('mutation',['currency','origin','duplicate','weight','legacy','future','unsorted'])
def test_portfolio_input_validation(mutation):
    raw=synthetic().model_dump(mode='json');h=raw['portfolio_holdings'][0]
    if mutation=='currency':h['provenance']['currency']='EUR'
    elif mutation=='origin':h['provenance']['synthetic']=False
    elif mutation=='duplicate':raw['portfolio_holdings'][1]['symbol']=h['symbol']
    elif mutation=='weight':h['weight']=.8
    elif mutation=='legacy':raw['portfolio_weights']=[.1,.1,.8]
    elif mutation=='future':h['prices'][-1]['date']='2099-01-01'
    else:h['prices'].reverse()
    with pytest.raises(ValidationError):AssessmentInput.model_validate(raw)


def test_maturity_bucket_boundaries_and_signed_cumulative_gaps():
    raw=synthetic().model_dump(mode='json');s=raw['statements'][-1];s['total_debt']=120;s['debt_due_12m']=70
    as_of=date.fromisoformat(s['period'])
    raw['debt_schedule'].update(payments=[{'id':str(day),'due_date':str(as_of+timedelta(days=day)),'principal':10,'interest':1,'rate_type':'fixed'} for day in [0,30,31,90,91,180,181,365,366,730,731,900]],complete=True,operating_flows=[],operating_flows_complete=False)
    data=AssessmentInput.model_validate(raw);r=maturity_analysis(data)
    assert [b['principal'] for b in r['buckets']]==[20,20,20,20,20,20]
    assert r['metrics']['principal_due_365d'].value==80
    assert r['status']=='partial'
    assert any('disagrees' in text for text in r['limitations'])
    assert r['timeline'][-1]['cumulative_cash'] is None # Cash coverage is not extrapolated beyond one year.
    assert r['metrics']['peak_scheduled_funding_gap'].value==0
    assert r['metrics']['weighted_average_maturity_years'].value==pytest.approx(sum([0,30,31,90,91,180,181,365,366,730,731,900])/12/365)


def test_maturity_gap_and_partial_data_are_not_zero_risk():
    data=synthetic('leveraged');r=maturity_analysis(data)
    assert r['first_shortfall_date'] is not None
    assert r['metrics']['peak_scheduled_funding_gap'].value>0
    data.debt_schedule.operating_flows_complete=False
    assert maturity_analysis(data)['status']=='partial'
    data.statements[-1].cash=None
    assert maturity_analysis(data)['metrics']['peak_scheduled_funding_gap'].value is None
    data.debt_schedule=None
    assert maturity_analysis(data)['status']=='unavailable'


@pytest.mark.parametrize('mutation',['sum','as_of','currency','past','duplicate'])
def test_debt_schedule_validation(mutation):
    raw=synthetic().model_dump(mode='json');schedule=raw['debt_schedule']
    if mutation=='sum':schedule['payments'][0]['principal']+=1
    elif mutation=='as_of':schedule['as_of']='2025-12-30'
    elif mutation=='currency':schedule['provenance']['currency']='EUR'
    elif mutation=='past':schedule['payments'][0]['due_date']='2020-01-01'
    else:schedule['payments'][1]['id']=schedule['payments'][0]['id']
    with pytest.raises(ValidationError):AssessmentInput.model_validate(raw)


def test_complete_operating_profile_requires_explicit_horizon():
    raw=synthetic().model_dump(mode='json');raw['debt_schedule']['operating_flows_through']=None
    with pytest.raises(ValidationError):AssessmentInput.model_validate(raw)


def test_balanced_baseline_bridge_and_zero_shock_score_delta():
    r=stress(synthetic(),'baseline');p=r['adverse_projection'];s=p['statement']
    assert p['status']=='completed' and p['funding_gap']==0
    assert s['cash']==pytest.approx(180+150-40)
    assert s['equity']==pytest.approx(650+100)
    assert s['total_liabilities']==pytest.approx(350-40)
    assert s['total_assets']==pytest.approx(s['equity']+s['total_liabilities'])
    assert s['current_assets']==pytest.approx(400+100-40)
    assert r['score_change']==pytest.approx(0)
    assert p['balance_residual']==pytest.approx(0)


def test_fixed_floating_exposure_and_amortization_are_not_all_debt_repricing():
    data=synthetic();r=stress(data,'interest_rate_increase');p=r['adverse_projection']
    assert r['impact']['incremental_interest']==pytest.approx(40*.03*180/365)
    for payment in data.debt_schedule.payments:payment.rate_type='fixed'
    assert stress(data,'interest_rate_increase')['impact']['incremental_interest']==0
    data.debt_schedule.payments[0].rate_type='unknown'
    result=stress(data,'interest_rate_increase')
    assert result['adverse_projection']['status']=='unavailable' and result['score_change'] is None


def test_intraperiod_gap_with_positive_closing_cash_withholds_score():
    result=stress(synthetic(),'combined_adverse');p=result['adverse_projection']
    assert result['impact']['cash']>0 and p['funding_gap']>0
    assert p['status']=='funding_shortfall' and p['first_shortfall_date']
    assert p['statement'] is None and p['aggregate'] is None and result['score_change'] is None


def test_cash_haircut_is_reclassification_capex_and_dividends_reconcile():
    result=stress(synthetic(),'liquidity_contraction',{'cash_change':-.2,'capex':10,'dividends':5})
    p=result['adverse_projection'];s=p['statement'];bridge=p['bridge']
    assert p['status']=='completed'
    assert s['cash']==pytest.approx(180+150-40-36-10-5)
    assert s['equity']==pytest.approx(650+100-5)
    assert s['total_assets']==pytest.approx(s['total_liabilities']+s['equity'])
    assert s['total_assets']-s['current_assets']==pytest.approx(600+36+10)
    assert bridge['restricted_cash_transfer']==36


def test_collection_delay_affects_cash_and_receivables_without_invented_funding():
    data=synthetic();r=stress(data,'baseline',{'collection_delay_days':30})
    p=r['adverse_projection']
    assert p['status']=='completed' and p['statement']['operating_cash_flow']==pytest.approx(110)
    assert p['statement']['net_income']==pytest.approx(100)
    assert p['statement']['cash']==pytest.approx(250)
    data.debt_schedule.operating_flows_complete=False
    assert stress(data,'baseline',{'collection_delay_days':30})['adverse_projection']['status']=='unavailable'


def test_invalid_projection_and_unknown_shocks_are_not_silently_scored():
    data=synthetic();data.debt_schedule.complete=False
    assert stress(data,'adverse')['adverse_projection']['aggregate'] is None
    data=synthetic();data.statements[-1].equity+=1
    assert stress(data,'baseline')['adverse_projection']['status']=='unavailable'
    with pytest.raises(ValueError):stress(synthetic(),'adverse',{'asset_shocks':{'unknown':-.2}})
    with pytest.raises(ValueError):stress(synthetic(),'adverse',{'asset_shocks':{'SYNTH_A':-2}})
    with pytest.raises(ValueError):stress(synthetic(),'adverse',{'cash_change':.5})


def test_constituent_shocks_do_not_reestimate_historical_covariance():
    r=stress(synthetic(),'market_decline',{'asset_shocks':{'SYNTH_A':-.5,'SYNTH_B':.1,'SYNTH_C':0}})
    assert r['portfolio_impact']['return']==pytest.approx(-.22)
    assert r['portfolio_impact']['pnl']==pytest.approx(-220000)
    assert r['portfolio_impact']['value_after_shock']==pytest.approx(780000)
    assert r['adverse_projection']['aggregate']['contributions']['market']==r['historical_aggregate']['contributions']['market']


def test_critic_recomputes_matrices_and_workflow_persists_new_analytics():
    data=synthetic();outputs={d:analyze(d,data) for d in DIMENSIONS}
    outputs['market'].analytics['portfolio']['covariance'][0][0]=999
    assert any(i.rule=='analytics_mismatch' for i in review(data,outputs,aggregate(outputs,data.config.weights)))
    result=asyncio.run(run_workflow(data))
    assert result['outputs']['market']['analytics']['portfolio']['status']=='completed'
    assert result['outputs']['liquidity']['analytics']['maturity']['buckets']
    assert not any(i['correctable'] for i in result['issues'])
