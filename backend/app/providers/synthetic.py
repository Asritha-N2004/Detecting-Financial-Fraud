"""Reproducible demo data, never presented as real market observations."""
from datetime import date, timedelta
import numpy as np
from app.schemas.domain import AssessmentInput


def synthetic(scenario: str = 'healthy') -> AssessmentInput:
    if scenario not in {'healthy','leveraged','volatile'}:
        raise ValueError('Unknown synthetic scenario')
    debt,cl,cash,ca,equity,income,interest,ocf = {
        'healthy':(120,100,180,400,650,120,10,150),
        'leveraged':(680,420,25,260,180,35,42,20),
        'volatile':(350,240,65,310,420,-25,25,5),
    }[scenario]
    liabilities = 1000-equity
    statements = []
    for year in [2023,2024,2025]:
        growth = (year-2023)*(.08 if scenario=='healthy' else -.12 if scenario=='volatile' else .01)
        rev = 900*(1+growth)
        statements.append(dict(period=f'{year}-12-31',currency='USD',current_assets=ca,inventory=ca*.2,cash=cash,current_liabilities=cl,total_assets=1000,total_liabilities=liabilities,total_debt=debt,equity=equity,revenue=rev,cost_of_goods=rev*.6,operating_income=income if year==2025 else income+10,net_income=income-interest-10,interest_expense=interest,operating_cash_flow=ocf,retained_earnings=100,market_equity=equity*1.2,debt_due_12m=cl*.4,annual_debt_service=interest+debt*.1))
    rng = np.random.default_rng({'healthy':17,'leveraged':23,'volatile':31}[scenario])
    sigma = {'healthy':.008,'leveraged':.016,'volatile':.037}[scenario]
    returns = rng.normal(.0003 if scenario!='volatile' else -.001,sigma,504)
    benchmark_returns = rng.normal(.0003,.009,504)
    prices = np.r_[100,100*np.cumprod(1+returns)]
    benchmark = np.r_[100,100*np.cumprod(1+benchmark_returns)]
    dates=[]; cursor=date(2024,1,1)
    while len(dates)<len(prices):
        if cursor.weekday()<5: dates.append(cursor.isoformat())
        cursor+=timedelta(days=1)
    provenance={'provider':'synthetic-seeded','source':f'demo:{scenario}; seed fixed; no real company','synthetic':True,'currency':'USD','quality':'unverified'}
    constituent_returns=[returns,benchmark_returns,.4*returns+.6*rng.normal(.0002,sigma*.8,504)]
    holdings=[{'symbol':symbol,'weight':weight,'provenance':provenance,
        'prices':[{'date':d,'close':float(p)} for d,p in zip(dates,np.r_[100,100*np.cumprod(1+r)])]}
        for symbol,weight,r in zip(['SYNTH_A','SYNTH_B','SYNTH_C'],[.5,.3,.2],constituent_returns)]
    as_of=date(2025,12,31)
    near=cl*.4
    payments=[{'id':'near-maturity','due_date':(as_of+timedelta(days=180)).isoformat(),'principal':near,'interest':interest*.5,'rate_type':'floating'},
        {'id':'annual-coupon','due_date':(as_of+timedelta(days=365)).isoformat(),'principal':0,'interest':interest*.5,'rate_type':'fixed'},
        {'id':'long-maturity','due_date':(as_of+timedelta(days=900)).isoformat(),'principal':debt-near,'interest':interest,'rate_type':'fixed'}]
    flows=[{'id':f'quarter-{i}','date':(as_of+timedelta(days=day)).isoformat(),'inflow':(ocf+interest)/4,'outflow':0} for i,day in enumerate([90,180,270,365],1)]
    return AssessmentInput.model_validate({'entity_name':{'healthy':'Aster Manufacturing','leveraged':'Meridian Industrial','volatile':'Vela Technologies'}[scenario],
        'provenance':provenance,
        'statements':statements,'prices':[{'date':d,'close':float(p),'benchmark':float(b)} for d,p,b in zip(dates,prices,benchmark)],
        'operational':[{'name':'Control review','severity':'low' if scenario=='healthy' else 'high' if scenario=='leveraged' else 'moderate','evidence':'Synthetic scenario assumption: documented control review indicator'}],
        'portfolio_weights':[.5,.3,.2],'portfolio_holdings':holdings,'portfolio_value':1000000,
        'debt_schedule':{'as_of':str(as_of),'provenance':provenance,'complete':True,'payments':payments,'operating_flows':flows,'operating_flows_complete':True,'operating_flows_through':str(as_of+timedelta(days=365))},
        'public_manufacturer':scenario!='volatile'})
