"""Diagnostic input reuse, explicit weight transfers and optional score history.

These diagnostics never replace the configured canonical aggregate, estimate PD,
or claim that overlapping inputs prove statistical correlation.
"""
from itertools import combinations
import math
import numpy as np
from app.schemas.domain import AgentOutput,DEFAULT_WEIGHTS,RiskScoreHistory,SensitivityConfig
from app.financial_engine.scoring import aggregate

# Dependencies of score-driving metrics, not every metric an analyst displays.
RULE_INPUTS={
 'debt_to_assets':['total_debt','total_assets'],
 'net_margin':['net_income','revenue'], 'return_on_assets':['net_income','total_assets'],
 'debt_to_equity':['total_debt','equity'], 'nonpositive_equity':['equity'],
 'interest_coverage':['operating_income','interest_expense'],
 'debt_service_coverage':['operating_cash_flow','annual_debt_service'],
 'current_ratio':['current_assets','current_liabilities'],
 'quick_ratio':['current_assets','inventory','current_liabilities'],
 'cash_ratio':['cash','current_liabilities'],
 'operating_cash_flow_ratio':['operating_cash_flow','current_liabilities'],
 'annualized_volatility':['market_price_history'], 'historical_var':['market_price_history'],
 'maximum_drawdown':['market_price_history'],
}


def validate_weights(weights: dict[str,float]):
    if set(weights)!=set(DEFAULT_WEIGHTS) or any(not math.isfinite(v) or v<0 for v in weights.values()) or not math.isclose(sum(weights.values()),1,abs_tol=1e-8):
        raise ValueError('Sensitivity weights must contain all five dimensions and sum to one')


def structural_overlap(outputs: dict[str,AgentOutput],weights: dict[str,float]) -> dict:
    exposures={};details=[];unavailable=[]
    for dimension in DEFAULT_WEIGHTS:
        out=outputs.get(dimension)
        if out is None or out.status!='completed' or out.score is None:
            unavailable.append(dimension);continue
        components=[c for c in out.score_components if c.included]
        if not components or any(not c.input_fields for c in components) or not math.isclose(sum(c.within_dimension_weight for c in components),1,abs_tol=1e-8) or not math.isclose(sum(c.score*c.within_dimension_weight for c in components),out.score,abs_tol=1e-7):
            unavailable.append(dimension);continue
        fields={}
        for c in components:
            for field in sorted(set(c.input_fields)):
                fields[field]=fields.get(field,0)+c.within_dimension_weight/len(set(c.input_fields))
            details.append({'dimension':dimension,**c.model_dump(mode='json'),
                'configured_contribution':weights[dimension]*c.within_dimension_weight*c.score})
        if fields:exposures[dimension]=fields
    pairs=[]
    for first,second in combinations(DEFAULT_WEIGHTS,2):
        if first not in exposures or second not in exposures:continue
        a,b=exposures[first],exposures[second];keys=set(a)|set(b)
        numerator=sum(min(a.get(k,0),b.get(k,0)) for k in sorted(keys))
        denominator=sum(max(a.get(k,0),b.get(k,0)) for k in sorted(keys))
        pairs.append({'first':first,'second':second,'shared_inputs':sorted(set(a)&set(b)),
            'shared_input_fraction':numerator/denominator if denominator else None})
    return {'status':'completed' if not unavailable else 'partial','exposures':exposures,
        'pairs':sorted(pairs,key=lambda p:p['shared_input_fraction'] or 0,reverse=True),
        'components':details,'unavailable_dimensions':sorted(set(unavailable)),
        'methodology':'Each score component splits its within-dimension weight equally across its primitive inputs. Weighted Jaccard input reuse = sum(min exposures) / sum(max exposures). This is not empirical correlation or a calibrated redundancy discount.'}


def empirical_overlap(history: RiskScoreHistory | None,weights: dict[str,float]) -> dict:
    if history is None:
        return {'status':'unavailable','reason':'No comparable dimension-score history supplied; one assessment and asset-price covariance cannot establish cross-risk correlation','minimum_observations':30}
    dimensions=list(DEFAULT_WEIGHTS)
    complete=[r for r in history.observations if all(r.scores.get(d) is not None for d in dimensions)]
    report={'status':'unavailable','minimum_observations':30,'observations_supplied':len(history.observations),
        'complete_observations':len(complete),'dropped_incomplete':len(history.observations)-len(complete),
        'provenance':history.provenance.model_dump(mode='json'),'model_version':history.model_version,
        'limitations':['Correlations describe supplied historical score levels, not causal links or loss probabilities',
            'Serial dependence, source quality and regime changes limit interpretation; no significance or independence claim',
            'Complete-case filtering is explicit; no forward fill or pairwise deletion; weights are current exploratory weights']}
    if history.provenance.synthetic:report['limitations'].append('Synthetic history: demonstration correlations only, not measured company evidence')
    if len(complete)<30:
        report['reason']='At least 30 jointly complete historical observations are required';return report
    matrix=np.array([[r.scores[d] for d in dimensions] for r in complete],dtype=float)
    covariance=np.cov(matrix,rowvar=False,ddof=1)
    std=np.sqrt(np.maximum(0,np.diag(covariance)));denom=np.outer(std,std)
    corr=np.divide(covariance,denom,out=np.zeros_like(covariance),where=denom>0)
    w=np.array([weights[d] for d in dimensions]);variance=float(w@covariance@w)
    pairs=[{'first':dimensions[i],'second':dimensions[j],'correlation':float(corr[i,j]) if denom[i,j]>0 else None,
        'aggregate_variance_cross_term':float(2*w[i]*w[j]*covariance[i,j])} for i,j in combinations(range(len(dimensions)),2)]
    report.update(status='completed' if np.all(std>0) else 'partial',dimensions=dimensions,
        start=str(complete[0].date),end=str(complete[-1].date),covariance=covariance.tolist(),
        correlation=[[float(corr[i,j]) if denom[i,j]>0 else None for j in range(len(dimensions))] for i in range(len(dimensions))],
        pairs=pairs,aggregate_variance=max(0,variance),aggregate_score_standard_deviation=math.sqrt(max(0,variance)),
        variance_contributions=(w*(covariance@w)).tolist())
    if np.any(std==0):report['limitations'].append('Constant score dimensions have undefined correlations')
    return report


def risk_sensitivity(outputs: dict[str,AgentOutput],weights: dict[str,float],config: SensitivityConfig | None = None,history: RiskScoreHistory | None = None) -> dict:
    validate_weights(weights);config=config or SensitivityConfig()
    baseline=aggregate(outputs,weights);transfers=[]
    for requested in config.transfer_steps:
        for donor in DEFAULT_WEIGHTS:
            for recipient in DEFAULT_WEIGHTS:
                if donor==recipient:continue
                actual=min(requested,weights[donor],1-weights[recipient])
                if actual<=1e-12:continue
                changed=dict(weights);changed[donor]-=actual;changed[recipient]+=actual
                result=aggregate(outputs,changed)
                transfers.append({'donor':donor,'recipient':recipient,'requested_transfer':requested,'actual_transfer':actual,
                    'weights':changed,'aggregate':result,
                    'score_change':result['score']-baseline['score'] if result['score'] is not None and baseline['score'] is not None else None,
                    'category_changed':result['category']!=baseline['category'] if result['score'] is not None and baseline['score'] is not None else None})
    results=[baseline,*[t['aggregate'] for t in transfers]]
    all_complete=all(r['score'] is not None for r in results)
    return {'version':'1','baseline':baseline,'structural':structural_overlap(outputs,weights),
        'empirical':empirical_overlap(history,weights),'transfer_steps':config.transfer_steps,'transfers':transfers,
        'sampled_score_envelope':[min(r['score_interval'][0] for r in results),max(r['score_interval'][1] for r in results)],
        'classification_stable':all(r['category']==baseline['category'] for r in results) if all_complete else None,
        'category_changes':sum(t['category_changed'] is True for t in transfers),
        'limitations':['Diagnostic only: the configured assessment score and weights are unchanged',
            'Transfers explicitly move donor weight to one recipient; no hidden normalization or missing-dimension redistribution',
            'The envelope covers sampled weight transfers and missing-score bounds only; it is not a confidence interval or global robustness proof',
            'Shared inputs do not prove double counting; no automatic discount is applied without an externally validated calibration']}
