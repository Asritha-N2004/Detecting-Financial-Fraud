import asyncio
import math
import pytest
from pydantic import ValidationError
from app.providers.synthetic import synthetic
from app.schemas.domain import AssessmentInput, Statement, AnalysisConfig, Price
from app.financial_engine.ratios import ratios,divide
from app.financial_engine.market_risk import market_metrics
from app.financial_engine.credit_risk import altman_z,train_logistic_baseline
from app.financial_engine.scoring import aggregate
from app.financial_engine.stress_testing import stress,SCENARIOS
from app.agents.analysts import analyze,DIMENSIONS
from app.agents.critic import review
from app.orchestration.workflow import run_workflow,correction,route


def test_all_statement_formulas():
    s=synthetic().statements[-1]; m=ratios(s,'statements:2')
    expected={'current_ratio':4,'quick_ratio':3.2,'debt_to_equity':120/650,'debt_to_assets':.12,
        'gross_margin':.4,'operating_margin':120/1044,'net_margin':100/1044,'return_on_assets':.1,
        'return_on_equity':100/650,'interest_coverage':12,'operating_cash_flow_ratio':1.5,'cash_ratio':1.8,
        'working_capital':300,'debt_service_coverage':150/22}
    assert set(m)==set(expected)
    for key,value in expected.items():
        assert m[key].value==pytest.approx(value)
        assert m[key].formula and m[key].evidence


@pytest.mark.parametrize('a,b',[(None,1),(1,None),(1,0),(1,-1)])
def test_invalid_denominators(a,b):
    assert divide(a,b,'a/b',[]).value is None


def test_market_against_hand_returns():
    from datetime import date,timedelta
    import numpy as np
    prices=[Price(date=date(2024,1,1)+timedelta(days=i),close=100*(1.01**i) if i<30 else 100,benchmark=100+i) for i in range(31)]
    m=market_metrics(prices,.95,2)
    p=np.array([x.close for x in prices]); losses=-(p[2:]/p[:-2]-1)
    q=np.quantile(losses,.95)
    assert m['historical_var'].value==pytest.approx(q)
    assert m['conditional_var'].value==pytest.approx(losses[losses>=q].mean())
    assert m['maximum_drawdown'].value==pytest.approx(1-1/(1.01**29))
    assert m['annualized_volatility'].value==pytest.approx(np.std(p[1:]/p[:-1]-1,ddof=1)*math.sqrt(252))
    assert m['beta'].value is not None and m['benchmark_correlation'].value is not None
    assert market_metrics(prices[:10])['annualized_volatility'].value is None


def test_altman_and_pd_baseline():
    s=synthetic().statements[-1]
    assert altman_z(s,False,'s').value is None
    expected=1.2*300/1000+1.4*.1+3.3*.12+.6*780/350+1044/1000
    assert altman_z(s,True,'s').value==pytest.approx(expected)
    model=train_logistic_baseline([[0,0],[1,2],[2,3],[3,4],[4,5],[5,6]],[0,0,0,1,1,1])
    assert model.predict([[0,0]]).tolist()==[0]
    assert not hasattr(analyze('credit',synthetic()),'probability_of_default')


def test_missing_dimension_interval():
    data=synthetic(); data.operational=[]
    outputs={d:analyze(d,data) for d in DIMENSIONS}
    a=aggregate(outputs,data.config.weights)
    assert a['score'] is None and a['coverage']==pytest.approx(.9)
    assert a['score_interval'][1]-a['score_interval'][0]==pytest.approx(10)


@pytest.mark.parametrize('scenario',list(SCENARIOS))
def test_stress(scenario):
    data=synthetic(); r=stress(data,scenario)
    assert r['hypothetical'] and r['method'] and r['limitations']
    if scenario=='combined_adverse':
        assert r['impact']['revenue']==pytest.approx(1044*.75)
        extra_interest=40*.04*180/365
        delta_ebit=(1044*.75-(1044-120)*1.2*.85)-120
        assert r['impact']['cash']==pytest.approx(108+150+(delta_ebit-extra_interest)*.75-40)
        assert r['impact']['interest_expense']==pytest.approx(10+extra_interest)
        assert r['adverse_projection']['funding_gap']>0
        assert r['score_change'] is None # Positive closing cash cannot cover an earlier deficit.


def test_schema_rejects_inconsistent_inputs():
    raw=synthetic().model_dump(mode='json')
    raw['statements'][0]['currency']='INR'
    with pytest.raises(ValidationError): AssessmentInput.model_validate(raw)
    with pytest.raises(ValidationError): AnalysisConfig(weights={'credit':1})
    with pytest.raises(ValidationError): AnalysisConfig(max_reflections=4)
    with pytest.raises(ValidationError): Statement(period='2025-01-01',currency='USD',total_assets=10,total_liabilities=3,equity=2)
    raw=synthetic().model_dump(mode='json'); raw['prices'].reverse()
    with pytest.raises(ValidationError): AssessmentInput.model_validate(raw)
    with pytest.raises(ValidationError): Price(date='2025-01-01',close=float('nan'))


def test_critic_detects_and_reflection_repairs():
    data=synthetic(); outputs={d:analyze(d,data) for d in DIMENSIONS}
    outputs['market'].score=99
    outputs['liquidity'].metrics['current_ratio'].value=999
    outputs['credit'].findings[0].evidence=['fabricated']
    outputs['credit'].confidence='high'
    agg=aggregate(outputs,data.config.weights); issues=review(data,outputs,agg)
    assert {'score_mismatch','metric_mismatch:current_ratio','excess_confidence'} <= {i.rule for i in issues}
    assert any(i.rule.startswith('unsupported:') for i in issues)
    state={'data':data,'outputs':outputs,'aggregate':agg,'issues':issues,'executions':[],'iteration':0,'history':[]}
    fixed=asyncio.run(correction(state))
    assert fixed['history'][0]['corrections_completed']
    remaining=review(data,fixed['outputs'],aggregate(fixed['outputs'],data.config.weights))
    assert all(not i.correctable for i in remaining)
    state['iteration']=3
    assert route(state)=='explain'


def test_workflow_distinguishes_scenarios():
    results=[asyncio.run(run_workflow(synthetic(s))) for s in ['healthy','leveraged','volatile']]
    scores=[r['aggregate']['score'] for r in results]
    assert scores[0]<scores[1] and scores[0]<scores[2]
    for r in results:
        assert len(r['outputs'])==5 and r['explanation']['findings']
        assert len(r['reflections'])<=3
        assert r['usage']['tokens']==0
        assert r['issues'] # Unverified synthetic provenance cannot self-correct.


def test_agent_failure_is_incomplete(monkeypatch):
    import app.orchestration.workflow as wf
    original=wf.analyze
    def broken(d,data):
        if d=='market': raise RuntimeError('injected test failure')
        return original(d,data)
    monkeypatch.setattr(wf,'analyze',broken)
    result=asyncio.run(wf.run_workflow(synthetic()))
    assert result['aggregate']['score'] is None
    assert result['outputs']['market']['status']=='failed'
    assert len(result['reflections'])==3
