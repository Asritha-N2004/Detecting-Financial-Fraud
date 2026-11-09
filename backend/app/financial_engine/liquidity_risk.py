"""Contractual maturity buckets and explicitly bounded cash-flow mismatch."""
from collections import defaultdict
from datetime import timedelta
from app.schemas.domain import AssessmentInput, Metric
from app.financial_engine.ratios import divide

BUCKETS=[('0_30_days',0,30),('31_90_days',31,90),('91_180_days',91,180),('181_365_days',181,365),('366_730_days',366,730),('over_730_days',731,None)]


def maturity_analysis(data: AssessmentInput) -> dict:
    schedule=data.debt_schedule
    if schedule is None:
        return {'status':'unavailable','metrics':{},'limitations':['No dated maturity schedule; the scalar debt_due_12m cannot establish cash-flow timing']}
    s=data.statements[-1] if data.statements else None
    cash=s.cash if s else None
    through=schedule.as_of+timedelta(days=365)
    operating_coverage=schedule.operating_flows_complete and schedule.operating_flows_through>=through
    refs=['debt_schedule']+([f'statements:{len(data.statements)-1}'] if s else [])
    total=sum(p.principal for p in schedule.payments)
    due=sum(p.principal for p in schedule.payments if (p.due_date-schedule.as_of).days<=365)
    interest=sum(p.interest for p in schedule.payments if (p.due_date-schedule.as_of).days<=365)
    assumptions=['Actual days from schedule as_of; 365-day year; no discounting',
        'Same-day cash flows netted; intraday liquidity and unsupplied liabilities are excluded',
        'Operating flows must exclude debt principal/interest to avoid double counting']
    def metric(value,formula,unit='ratio'):
        return Metric(value=value,formula=formula,unit=unit,evidence=refs,assumptions=assumptions)
    metrics={'scheduled_principal':metric(total,'sum(scheduled_principal)',data.provenance.currency),
        'principal_due_365d':metric(due,'sum(principal with residual_days <= 365)',data.provenance.currency),
        'interest_due_365d':metric(interest,'sum(interest with residual_days <= 365)',data.provenance.currency),
        'weighted_average_maturity_years':metric(sum(p.principal*(p.due_date-schedule.as_of).days/365 for p in schedule.payments)/total if total>0 else None,'sum(principal * residual_days / 365) / total_scheduled_principal'),
        'cash_to_365d_debt_service':divide(cash,due+interest,'cash / (365d_principal + 365d_interest)',refs),
        'scheduled_principal_365d_share':divide(due,total,'365d_principal / total_scheduled_principal',refs)}
    events=defaultdict(lambda:{'principal':0.,'interest':0.,'operating_inflow':0.,'operating_outflow':0.})
    for p in schedule.payments:
        events[p.due_date]['principal']+=p.principal;events[p.due_date]['interest']+=p.interest
    for flow in schedule.operating_flows:
        events[flow.date]['operating_inflow']+=flow.inflow;events[flow.date]['operating_outflow']+=flow.outflow
    running=cash;minimum=cash;first_gap=None;timeline=[]
    for date,event in sorted(events.items()):
        net=event['operating_inflow']-event['operating_outflow']-event['principal']-event['interest']
        running=running+net if running is not None and date<=through else None
        if running is not None:
            minimum=min(minimum,running)
            if running<0 and first_gap is None: first_gap=str(date)
        timeline.append({'date':str(date),'days':(date-schedule.as_of).days,**event,'net_flow':net,'cumulative_cash':running})
    buckets=[]
    for label,start,end in BUCKETS:
        rows=[e for e in timeline if e['days']>=start and (end is None or e['days']<=end)]
        buckets.append({'bucket':label,'start_day':start,'end_day':end,**{key:sum(e[key] for e in rows) for key in ['principal','interest','operating_inflow','operating_outflow','net_flow']}})
    gap=max(0,-minimum) if minimum is not None else None
    metrics['peak_scheduled_funding_gap']=metric(gap,'max(0, -min(opening_cash + cumulative_supplied_net_flows))',data.provenance.currency)
    limitations=['No assumption of automatic refinancing, unused credit lines, asset sales or future receipts',
        'Cumulative cash and funding gaps cover 365 days only; later bucket obligations are shown without inferred receipts']
    if not schedule.complete: limitations.append('Partial debt schedule; unscheduled debt is not treated as zero')
    if not operating_coverage: limitations.append('Operating flow coverage is incomplete over the next 365 days; partial gaps cannot establish funding adequacy')
    if cash is None: limitations.append('Opening cash unavailable; cumulative funding gaps withheld')
    if s and s.debt_due_12m is not None and abs(s.debt_due_12m-due)>max(.01,abs(s.debt_due_12m)*.01):
        limitations.append('Reported debt_due_12m disagrees with dated principal due within 365 days')
    return {'status':'completed' if schedule.complete and operating_coverage and cash is not None else 'partial','cash_flow_horizon_days':365,
        'as_of':str(schedule.as_of),'metrics':metrics,'buckets':buckets,'timeline':timeline,'first_shortfall_date':first_gap,
        'coverage':{'debt_schedule_complete':schedule.complete,'operating_flows_complete':bool(operating_coverage),'operating_flows_through':str(schedule.operating_flows_through) if schedule.operating_flows_through else None},
        'assumptions':assumptions,'limitations':limitations}
