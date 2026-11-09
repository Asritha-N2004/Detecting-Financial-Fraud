"""Validated hypothetical scenarios with matched one-year accounting projections."""
import math
from app.schemas.domain import AssessmentInput,Statement
from app.schemas.scenarios import ScenarioAssumptions
from app.financial_engine.ratios import ratios
from app.financial_engine.stress_projection import project_statement
from app.financial_engine.scoring import aggregate

SCENARIOS={
    'baseline':{},
    'market_decline':{'market_return':-.20},
    'interest_rate_increase':{'rate_increase':.03},
    'revenue_decline':{'revenue_change':-.20},
    'operating_cost_increase':{'cost_change':.15},
    'liquidity_contraction':{'cash_change':-.35},
    'combined_adverse':{'market_return':-.30,'rate_increase':.04,'revenue_change':-.25,'cost_change':.20,'cash_change':-.40},
    'adverse':{'market_return':-.15,'rate_increase':.02,'revenue_change':-.10,'cost_change':.05,'cash_change':-.15},
    'severe':{'market_return':-.40,'rate_increase':.06,'revenue_change':-.35,'cost_change':.25,'cash_change':-.50,'collection_delay_days':60},
}


def stress(data: AssessmentInput,name: str,overrides: dict | None = None) -> dict:
    from app.agents.analysts import analyze,DIMENSIONS
    if name not in SCENARIOS:raise ValueError('Unknown scenario')
    a=ScenarioAssumptions.model_validate({**SCENARIOS[name],**(overrides or {})})
    symbols={h.symbol for h in data.portfolio_holdings}
    if not set(a.asset_shocks).issubset(symbols) or any(not math.isfinite(v) or not -1<=v<=1 for v in a.asset_shocks.values()):
        raise ValueError('Asset shocks must reference known constituents and lie between -1 and 1')
    baseline_assumptions=ScenarioAssumptions(tax_rate=a.tax_rate,variable_cost_share=a.variable_cost_share,capex=a.capex,dividends=a.dividends)
    baseline=project_statement(data,baseline_assumptions)
    adverse=project_statement(data,a)
    outputs={d:analyze(d,data) for d in DIMENSIONS}
    historical=aggregate(outputs,data.config.weights)
    def score_projection(projection):
        if projection['status']!='completed':return None
        projected=Statement.model_validate(projection['statement'])
        # This internal hypothetical object is never ingested as historical data.
        hypothetical=data.model_copy(update={'statements':[*data.statements[:-1],projected],'debt_schedule':None})
        updated=dict(outputs)
        for dimension in ['credit','financial','liquidity']:updated[dimension]=analyze(dimension,hypothetical)
        return aggregate(updated,data.config.weights)
    baseline['aggregate']=score_projection(baseline);adverse['aggregate']=score_projection(adverse)
    point_delta=None;interval_delta=None
    if baseline['aggregate'] and adverse['aggregate']:
        b=baseline['aggregate'];s=adverse['aggregate']
        if b['score'] is not None and s['score'] is not None:point_delta=s['score']-b['score']
        interval_delta=[s['score_interval'][0]-b['score_interval'][1],s['score_interval'][1]-b['score_interval'][0]]
    portfolio_return=sum(h.weight*a.asset_shocks.get(h.symbol,a.market_return) for h in data.portfolio_holdings) if data.portfolio_holdings else None
    portfolio_impact={'return':portfolio_return,'pnl':portfolio_return*data.portfolio_value if portfolio_return is not None and data.portfolio_value is not None else None,
        'value_after_shock':data.portfolio_value*(1+portfolio_return) if portfolio_return is not None and data.portfolio_value is not None else None,
        'constituents':[{'symbol':h.symbol,'weight':h.weight,'shock':a.asset_shocks.get(h.symbol,a.market_return),'return_contribution':h.weight*a.asset_shocks.get(h.symbol,a.market_return)} for h in data.portfolio_holdings],
        'method':'One-time weighted constituent price shocks at supplied weights; no future covariance or volatility estimate'}
    s=data.statements[-1] if data.statements else None
    impact=dict(adverse.get('impact',{}))
    impact['asset_price']=data.prices[-1].close*(1+a.market_return) if data.prices else None
    limitations=['All scenario results are hypothetical, not forecasts',
        'Conditional overall scores update credit, financial and liquidity rules only; historical market/operational scores are held fixed',
        'Income tax effects, cash conversion, cost behavior and restricted cash classification are explicit scenario assumptions, not verified projections',
        'No automatic emergency borrowing or refinancing; funding gaps withhold projected scores',
        *baseline['limitations'],*adverse['limitations']]
    if data.portfolio_holdings:limitations.append('Spot market shocks change portfolio value; historical covariance and VaR are not reestimated from invented future observations')
    return {'engine_version':'2','scenario':name,'hypothetical':True,'currency':data.provenance.currency,
        'assumptions':a.model_dump(mode='json'),'inputs':s.model_dump(mode='json') if s else {},
        'baseline':{k:v.model_dump(mode='json') for k,v in ratios(s,f'statements:{len(data.statements)-1}').items()} if s else {},
        'impact':impact,'historical_aggregate':historical,'baseline_projection':baseline,'adverse_projection':adverse,
        'score_change':point_delta,'score_change_interval':interval_delta,'portfolio_impact':portfolio_impact,
        'method':'Matched one-year baseline/adverse cash-flow and accounting bridges; principal repaid on supplied dates, fixed/floating rate exposure, collection delays, restricted cash and no balancing plugs.',
        'limitations':list(dict.fromkeys(limitations))}
