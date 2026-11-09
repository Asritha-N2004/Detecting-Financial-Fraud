"""A disclosed one-year accounting and liquidity bridge, not a financial forecast."""
from collections import defaultdict
from datetime import timedelta
import math
from app.schemas.domain import AssessmentInput, Statement
from app.schemas.scenarios import ScenarioAssumptions
from app.financial_engine.ratios import ratios


def project_statement(data: AssessmentInput, a: ScenarioAssumptions) -> dict:
    report={'status':'unavailable','statement':None,'metrics':{},'timeline':[],'funding_gap':None,'first_shortfall_date':None,'balance_residual':None,'limitations':[]}
    s=data.statements[-1] if data.statements else None;schedule=data.debt_schedule
    required=['cash','current_assets','inventory','current_liabilities','total_assets','total_liabilities','total_debt','equity','revenue','cost_of_goods','operating_income','net_income','interest_expense','operating_cash_flow']
    if s is None or any(getattr(s,key) is None for key in required):
        report['limitations']=['Complete financial inputs are required for an accounting projection'];return report
    if schedule is None or not schedule.complete:
        report['limitations']=['A complete dated debt schedule is required; unsupplied maturities are not assumed zero'];return report
    horizon=a.horizon_days;scale=horizon/s.reporting_days
    tol=max(1,abs(s.total_assets))*1e-8
    if abs(s.total_assets-s.total_liabilities-s.equity)>tol:
        report['limitations']=['Opening accounting equation must reconcile exactly for a projected score'];return report
    if s.current_assets-s.cash-s.inventory < -tol:
        report['limitations']=['Opening current asset components do not reconcile'];return report
    principal_total=sum(p.principal for p in schedule.payments)
    current_principal=sum(p.principal for p in schedule.payments if (p.due_date-s.period).days<=365)
    if not math.isclose(principal_total,s.total_debt,rel_tol=1e-6,abs_tol=.01) or current_principal>s.current_liabilities+tol or s.total_debt>s.total_liabilities+tol:
        report['limitations']=['Maturity principal does not reconcile to debt or current/noncurrent liability classification'];return report
    if s.debt_due_12m is not None and not math.isclose(current_principal,s.debt_due_12m,rel_tol=1e-6,abs_tol=.01):
        report['limitations']=['Reported debt_due_12m conflicts with the dated schedule'];return report
    if a.rate_increase and any(p.principal>0 and p.rate_type=='unknown' for p in schedule.payments):
        report['limitations']=['Rate-shock exposure is unknown for part of the debt; specify fixed/floating principal'];return report
    costs=(s.revenue-s.operating_income)*scale
    if costs<0 or s.cost_of_goods*scale>costs+tol:
        report['limitations']=['Operating expense classification cannot be reconciled to revenue, EBIT and COGS'];return report
    revenue=s.revenue*scale*(1+a.revenue_change)
    stressed_costs=costs*(1+a.cost_change)*(1+a.variable_cost_share*a.revenue_change)
    ebit=revenue-stressed_costs;delta_ebit=ebit-s.operating_income*scale
    due=[p for p in schedule.payments if (p.due_date-s.period).days<=horizon]
    principal=sum(p.principal for p in due);scheduled_interest=sum(p.interest for p in due)
    events=defaultdict(lambda:{'operating_net_flow':0.,'principal':0.,'interest':0.,'capex':0.,'dividends':0.})
    incremental_interest=0.
    for p in schedule.payments:
        days=(p.due_date-s.period).days
        extra=p.principal*a.rate_increase*min(days,horizon)/365 if p.rate_type=='floating' else 0.
        incremental_interest+=extra
        events[min(days,horizon)]['interest']+=extra
        if days<=horizon:
            events[days]['principal']+=p.principal;events[days]['interest']+=p.interest
    annual_interest=s.interest_expense*scale
    expected_gross_ocf=(s.operating_cash_flow+s.interest_expense)*scale
    if schedule.operating_flows_complete:
        if schedule.operating_flows_through<s.period+timedelta(days=horizon):
            report['limitations']=['Operating-flow completeness does not cover the projection horizon'];return report
        in_period=[f for f in schedule.operating_flows if (f.date-s.period).days<=horizon]
        observed=sum(f.inflow-f.outflow for f in in_period)
        if not math.isclose(observed,expected_gross_ocf,rel_tol=1e-6,abs_tol=.01):
            report['limitations']=['Complete operating flows must reconcile to reported OCF plus cash interest over the projection year'];return report
        for f in in_period:
            day=(f.date-s.period).days
            events[day]['operating_net_flow']-=f.outflow
            if day+a.collection_delay_days<=horizon: events[day+a.collection_delay_days]['operating_net_flow']+=f.inflow
    else:
        if a.collection_delay_days:
            report['limitations']=['Collection-delay scenarios require a complete dated operating-flow profile'];return report
        for day in range(1,horizon+1):events[day]['operating_net_flow']+=expected_gross_ocf/horizon
        report['limitations'].append('Operating cash receipts/outlays distributed uniformly because no complete profile was supplied')
    tax_adjustment=a.tax_rate*(scheduled_interest+incremental_interest-annual_interest)
    uniform_delta=(delta_ebit*(1-a.tax_rate)+tax_adjustment)/horizon
    for day in range(1,horizon+1):events[day]['operating_net_flow']+=uniform_delta
    events[horizon]['capex']=a.capex;events[horizon]['dividends']=a.dividends
    restricted_cash=-s.cash*a.cash_change
    running=s.cash-restricted_cash;minimum=running;first_gap=None;timeline=[]
    for day,event in sorted(events.items()):
        net=event['operating_net_flow']-event['principal']-event['interest']-event['capex']-event['dividends']
        running+=net;minimum=min(minimum,running)
        if running < -tol and first_gap is None:first_gap=str(s.period+timedelta(days=day))
        timeline.append({'day':day,'date':str(s.period+timedelta(days=day)),**event,'net_flow':net,'cash':running})
    ocf=sum(e['operating_net_flow']-e['interest'] for e in timeline)
    net_income=s.net_income*scale+(delta_ebit+annual_interest-scheduled_interest-incremental_interest)*(1-a.tax_rate)
    report.update(impact={'revenue':revenue,'operating_income':ebit,'interest_expense':scheduled_interest+incremental_interest,
        'operating_cash_flow':ocf,'net_income':net_income,'cash':running,'cash_ratio':None,'restricted_cash_transfer':restricted_cash,
        'principal_repaid':principal,'incremental_interest':incremental_interest},
        bridge={'opening_cash':s.cash,'operating_cash_flow':ocf,'principal_repaid':principal,'capex':a.capex,'dividends':a.dividends,'restricted_cash_transfer':restricted_cash,'closing_cash':running},
        funding_gap=max(0,-minimum),first_shortfall_date=first_gap,timeline=timeline,
        assumptions=['Reported OCF assumed after cash interest and tax; scheduled operating flows exclude debt service',
            'Variable costs scale with revenue; remaining costs fixed; both receive the cost shock',
            'Tax shields/charges on incremental EBIT and interest realized within the year at supplied tax_rate',
            'Floating principal reprices immediately until its dated repayment; Actual/365 interest, no compounding',
            'Cash haircut transfers opening cash into noncurrent restricted cash; it is not an equity loss',
            'NI minus OCF changes other noncash current assets; inventory and nondebt liabilities held fixed',
            'Capex capitalized; dividends reduce equity; no automatic borrowing, refinancing or asset sales',
            'Interest on principal after the horizon is paid at horizon; same-day flows netted; no intraday model'])
    if first_gap:
        report['status']='funding_shortfall';report['limitations'].append('An unfunded intraperiod cash deficit prevents a realizable projected score');return report
    other_current=s.current_assets-s.cash-s.inventory+net_income-ocf
    next_current=sum(p.principal for p in schedule.payments if horizon<(p.due_date-s.period).days<=horizon+365)
    updates={'period':s.period+timedelta(days=horizon),'reporting_days':horizon,
        'cash':max(0,running),'current_assets':s.inventory+other_current+max(0,running),
        'total_assets':s.total_assets+net_income-principal-a.dividends,
        'total_liabilities':s.total_liabilities-principal,'total_debt':s.total_debt-principal,
        'current_liabilities':s.current_liabilities-current_principal+next_current,
        'equity':s.equity+net_income-a.dividends,'revenue':revenue,'cost_of_goods':s.cost_of_goods*scale*(stressed_costs/costs if costs else 1),
        'operating_income':ebit,'net_income':net_income,'interest_expense':scheduled_interest+incremental_interest,
        'operating_cash_flow':ocf,'annual_debt_service':principal+scheduled_interest+incremental_interest,'debt_due_12m':next_current,
        'retained_earnings':s.retained_earnings+net_income-a.dividends if s.retained_earnings is not None else None,
        'market_equity':s.market_equity*(1+a.market_return) if s.market_equity is not None else None}
    if other_current < -tol or updates['current_liabilities']>updates['total_liabilities']+tol:
        report['limitations'].append('Implied noncash current assets or debt classification is infeasible; no balancing plug inserted');return report
    residual=updates['total_assets']-updates['total_liabilities']-updates['equity']
    report['balance_residual']=residual
    if abs(residual)>tol:
        report['limitations'].append('Projected accounting equation does not reconcile');return report
    try:projected=Statement.model_validate({**s.model_dump(),**updates})
    except ValueError:
        report['limitations'].append('Projected statement fails financial input validation');return report
    report.update(status='completed',statement=projected.model_dump(mode='json'),metrics={k:m.model_dump(mode='json') for k,m in ratios(projected,'scenario:projected_statement').items()})
    report['impact']['cash_ratio']=projected.cash/projected.current_liabilities if projected.current_liabilities>0 else None
    return report
