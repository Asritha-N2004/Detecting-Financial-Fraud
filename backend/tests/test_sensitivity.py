import asyncio
from copy import deepcopy
from datetime import date,timedelta
import numpy as np
import pytest
from pydantic import ValidationError
from app.schemas.domain import AgentOutput,ScoreComponent,DEFAULT_WEIGHTS,AssessmentInput,RiskScoreHistory,SensitivityConfig
from app.financial_engine.sensitivity import risk_sensitivity,empirical_overlap,structural_overlap
from app.providers.synthetic import synthetic
from app.agents.analysts import analyze,DIMENSIONS
from app.agents.critic import review
from app.orchestration.workflow import run_workflow


def outputs():
    return {d:AgentOutput(agent_id=d,dimension=d,status='completed',score=s,confidence='moderate',summary='test',
        score_components=[ScoreComponent(id=d+':one',metric_refs=[],input_fields=['shared' if d in ['credit','financial'] else d],
            evidence=['test'],score=s,within_dimension_weight=1,included=True)]) for d,s in zip(DEFAULT_WEIGHTS,[60,20,80,40,10])}


def history(count=40):
    data=synthetic()
    return RiskScoreHistory(entity_name=data.entity_name,model_version='rules-2.0',holding_days=1,confidence=.95,provenance=data.provenance,
        observations=[{'date':date(2024,1,1)+timedelta(days=i),'scores':{'credit':20+i,'market':10+i*.5,'liquidity':80-i,'financial':10+i*2,'operational':20}} for i in range(count)])


def test_explicit_transfer_hand_calculation_and_no_mutation():
    out=outputs();original=deepcopy(out);weights=DEFAULT_WEIGHTS.copy()
    report=risk_sensitivity(out,weights,SensitivityConfig(transfer_steps=[.05]))
    expected=sum(weights[d]*o.score for d,o in out.items())
    assert report['baseline']['score']==pytest.approx(expected)
    transfer=next(t for t in report['transfers'] if t['donor']=='credit' and t['recipient']=='liquidity')
    assert transfer['score_change']==pytest.approx(.05*(80-60))
    assert sum(transfer['weights'].values())==pytest.approx(1)
    assert transfer['weights']['credit']==pytest.approx(.20)
    assert out==original and weights==DEFAULT_WEIGHTS
    assert len(report['transfers'])==20


def test_structural_input_reuse_is_not_claimed_as_correlation():
    report=structural_overlap(outputs(),DEFAULT_WEIGHTS)
    pair=next(p for p in report['pairs'] if {p['first'],p['second']}=={'credit','financial'})
    assert pair['shared_input_fraction']==1 and pair['shared_inputs']==['shared']
    assert 'not empirical correlation' in report['methodology']
    assert sum(c['configured_contribution'] for c in report['components'])==pytest.approx(45)


def test_missing_dimensions_keep_weight_bounds_and_do_not_become_low_risk():
    out=outputs();out['operational'].score=None;out['operational'].status='failed'
    report=risk_sensitivity(out,DEFAULT_WEIGHTS)
    assert report['baseline']['score'] is None and report['classification_stable'] is None
    assert report['baseline']['score_interval'][1]-report['baseline']['score_interval'][0]==pytest.approx(10)
    transfer=next(t for t in report['transfers'] if t['donor']=='credit' and t['recipient']=='operational' and t['requested_transfer']==.05)
    assert transfer['aggregate']['score'] is None and transfer['aggregate']['coverage']==pytest.approx(.85)


def test_zero_weight_unavailable_dimension_and_capped_transfer_are_explicit():
    out=outputs();out['operational'].score=None;out['operational'].status='incomplete'
    weights={'credit':.02,'market':.48,'liquidity':.25,'financial':.25,'operational':0}
    report=risk_sensitivity(out,weights)
    assert report['baseline']['score'] is not None
    row=next(t for t in report['transfers'] if t['donor']=='credit' and t['recipient']=='operational')
    assert row['actual_transfer']==.02 and row['requested_transfer']==.05
    assert row['aggregate']['score'] is None and report['classification_stable'] is None


def test_category_boundary_and_sampled_envelope():
    out=outputs()
    for d,o in out.items():o.score=30 if d!='credit' else 50;o.score_components[0].score=o.score
    r=risk_sensitivity(out,DEFAULT_WEIGHTS,SensitivityConfig(transfer_steps=[.1]))
    assert r['baseline']['score']==35
    assert r['category_changes']>0 and r['classification_stable'] is False
    assert r['sampled_score_envelope']==pytest.approx([33,37])


def test_legacy_or_corrupt_component_metadata_is_not_invented():
    out=outputs();out['credit'].score_components=[]
    r=risk_sensitivity(out,DEFAULT_WEIGHTS)
    assert r['structural']['status']=='partial' and 'credit' in r['structural']['unavailable_dimensions']
    assert r['transfers'] and r['empirical']['status']=='unavailable'


def test_empirical_covariance_and_cross_terms_against_centered_scores():
    h=history();r=empirical_overlap(h,DEFAULT_WEIGHTS)
    matrix=np.array([[o.scores[d] for d in DEFAULT_WEIGHTS] for o in h.observations])
    centered=matrix-matrix.mean(axis=0);expected=centered.T@centered/(len(matrix)-1)
    assert np.allclose(r['covariance'],expected)
    assert r['correlation'][0][3]==pytest.approx(1)
    assert r['correlation'][0][2]==pytest.approx(-1)
    assert r['correlation'][4][4] is None and r['status']=='partial'
    w=np.array(list(DEFAULT_WEIGHTS.values()))
    assert r['aggregate_variance']==pytest.approx(w@expected@w)
    assert sum(r['variance_contributions'])==pytest.approx(r['aggregate_variance'])
    diagonal=sum(w[i]**2*expected[i,i] for i in range(5))
    assert diagonal+sum(p['aggregate_variance_cross_term'] for p in r['pairs'])==pytest.approx(r['aggregate_variance'])


def test_complete_case_history_threshold_and_missing_source():
    assert empirical_overlap(None,DEFAULT_WEIGHTS)['status']=='unavailable'
    h=history(29);assert empirical_overlap(h,DEFAULT_WEIGHTS)['status']=='unavailable'
    h=history(35)
    for row in h.observations[:6]:row.scores['market']=None
    report=empirical_overlap(h,DEFAULT_WEIGHTS)
    assert report['dropped_incomplete']==6 and report['complete_observations']==29 and report['status']=='unavailable'


@pytest.mark.parametrize('kind',['weights','steps','entity','horizon','future','duplicate','origin','bounds'])
def test_invalid_sensitivity_and_history_inputs(kind):
    raw=synthetic().model_dump(mode='json');raw['risk_score_history']=history().model_dump(mode='json')
    if kind=='weights':
        with pytest.raises(ValueError):risk_sensitivity(outputs(),{'credit':1});return
    if kind=='steps':
        with pytest.raises(ValueError):SensitivityConfig(transfer_steps=[.1,.05]);return
    h=raw['risk_score_history']
    if kind=='entity':h['entity_name']='Different entity'
    elif kind=='horizon':h['holding_days']=5
    elif kind=='future':h['observations'][-1]['date']='2099-01-01'
    elif kind=='duplicate':h['observations'][-1]['date']=h['observations'][-2]['date']
    elif kind=='origin':h['provenance']['synthetic']=False
    else:h['observations'][0]['scores']['credit']=101
    with pytest.raises(ValidationError):AssessmentInput.model_validate(raw)


def test_workflow_saves_report_and_critic_detects_diagnostic_tampering():
    data=synthetic();report=asyncio.run(run_workflow(data))
    assert report['sensitivity']['baseline']==report['aggregate']
    assert report['sensitivity']['structural']['components']
    out={d:AgentOutput.model_validate(o) for d,o in report['outputs'].items()}
    report['sensitivity']['sampled_score_envelope']=[0,0]
    assert any(i.rule=='sensitivity_mismatch' for i in review(data,out,report['aggregate'],report['sensitivity']))
