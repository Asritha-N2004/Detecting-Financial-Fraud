"""Long-only, constant-weight daily-rebalanced historical portfolio analysis."""
import numpy as np
from app.schemas.domain import AssessmentInput, Metric, Price
from app.financial_engine.market_risk import market_metrics


def portfolio_risk(data: AssessmentInput) -> dict:
    holdings=data.portfolio_holdings
    assumptions=['Long-only fully invested weights; rebalanced each observation; no fees or FX conversion',
                 'Synchronized observed simple returns; sample covariance ddof=1; annual factor 252',
                 'No forward fill or pairwise deletion; identical constituent calendars required']
    report={'status':'unavailable','symbols':[h.symbol for h in holdings],'metrics':{},'assumptions':assumptions,'limitations':[]}
    if not holdings:
        report['limitations']=['Constituent histories are required; standalone prices are not a portfolio proxy']
        return report
    dates=[p.date for p in holdings[0].prices]
    minimum=max(31,data.config.holding_days+2)
    if any([p.date for p in h.prices]!=dates for h in holdings):
        report['limitations']=['Constituent price calendars do not match; align actual observations before analysis']
        return report
    if len(dates)<minimum:
        report['limitations']=[f'At least {minimum} aligned prices are required']
        return report
    prices=np.array([[p.close for p in h.prices] for h in holdings],dtype=float).T
    returns=prices[1:]/prices[:-1]-1
    weights=np.array([h.weight for h in holdings],dtype=float)
    covariance=np.atleast_2d(np.cov(returns,rowvar=False,ddof=1))
    variance=float(weights@covariance@weights)
    volatility=float(np.sqrt(max(0,variance)))
    individual=np.sqrt(np.maximum(0,np.diag(covariance)))
    denominator=np.outer(individual,individual)
    correlation=np.divide(covariance,denominator,out=np.zeros_like(covariance),where=denominator>0)
    contributions=weights*(covariance@weights)/volatility if volatility>1e-15 else None
    portfolio_returns=returns@weights
    path=np.r_[100,100*np.cumprod(1+portfolio_returns)]
    benchmark=[p.benchmark for p in data.prices] if [p.date for p in data.prices]==dates else []
    path_prices=[Price(date=d,close=float(v),benchmark=benchmark[i] if benchmark else None) for i,(d,v) in enumerate(zip(dates,path))]
    refs=[f'portfolio_holdings:{i}' for i in range(len(holdings))]
    metrics=market_metrics(path_prices,data.config.confidence,data.config.holding_days)
    for metric in metrics.values():
        metric.evidence=refs.copy();metric.assumptions+=assumptions
        if benchmark and metric.formula.startswith(('cov(','pearson(')): metric.evidence.append(f'prices:0:{len(data.prices)-1}')
    def metric(value,formula,unit='ratio'):
        return Metric(value=value,formula=formula,unit=unit,evidence=refs,assumptions=assumptions)
    metrics.update(portfolio_variance=metric(variance,'weights.T @ sample_covariance @ weights','daily return squared'),
        concentration_hhi=metric(float(weights@weights),'sum(constituent_weight ** 2)'),
        diversification_ratio=metric(float(weights@individual)/volatility if volatility>1e-15 else None,'weighted_sum(individual_daily_volatility) / portfolio_daily_volatility'),
        diversification_benefit=metric(float(weights@individual)-volatility,'weighted_sum(individual_daily_volatility) - portfolio_daily_volatility'))
    if data.portfolio_value is not None:
        metrics['portfolio_value_var']=metric(metrics['historical_var'].value*data.portfolio_value,'historical_var * supplied_portfolio_value',data.provenance.currency)
    report.update(status='completed',metrics=metrics,weights=weights.tolist(),observations=len(returns),start=str(dates[0]),end=str(dates[-1]),
        covariance=covariance.tolist(),annualized_covariance=(covariance*252).tolist(),
        correlation=[[float(correlation[i,j]) if denominator[i,j]>0 else None for j in range(len(holdings))] for i in range(len(holdings))],
        risk_contributions=[{'symbol':h.symbol,'weight':h.weight,'daily_volatility_contribution':float(contributions[i]) if contributions is not None else None,
            'annualized_volatility_contribution':float(contributions[i]*np.sqrt(252)) if contributions is not None else None,
            'variance_share':float(contributions[i]/volatility) if contributions is not None else None} for i,h in enumerate(holdings)])
    if np.linalg.matrix_rank(covariance)<len(holdings): report['limitations'].append('Covariance is singular; no inverse or portfolio optimization is attempted')
    if not benchmark: report['limitations'].append('No date-aligned benchmark supplied; beta unavailable')
    if volatility<=1e-15: report['limitations'].append('Zero portfolio volatility: marginal contributions and diversification ratio undefined')
    return report
