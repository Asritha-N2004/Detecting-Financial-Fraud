import numpy as np
from app.schemas.domain import Price, Metric


def market_metrics(prices: list[Price], confidence: float = .95, holding_days: int = 1) -> dict[str, Metric]:
    if len(prices) < max(31, holding_days + 2):
        return {'annualized_volatility': Metric(value=None, formula='std(daily_simple_returns, ddof=1) * sqrt(252)', limitation='At least 31 prices and holding_days + 2 observations required')}
    p = np.array([r.close for r in prices], dtype=float)
    r = p[1:] / p[:-1] - 1
    horizon = p[holding_days:] / p[:-holding_days] - 1
    losses = -horizon
    var = float(np.quantile(losses, confidence))
    tail = losses[losses >= var]
    refs = [f'prices:0:{len(prices)-1}']
    assumptions = ['Simple returns; 252 trading days/year; unweighted observations', f'{holding_days}-observation overlapping holding-period returns', 'Historical quantile is not a forecast; no normality assumption']
    def metric(value, formula, limitation=None):
        return Metric(value=float(value) if value is not None else None, formula=formula, evidence=refs, assumptions=assumptions, limitation=limitation)
    out = {
        'daily_volatility': metric(np.std(r, ddof=1), 'sample_std(daily_simple_returns)'),
        'annualized_volatility': metric(np.std(r, ddof=1)*np.sqrt(252), 'sample_std(daily_simple_returns) * sqrt(252)'),
        'historical_var': metric(var, f'quantile(-holding_period_returns, {confidence})'),
        'conditional_var': metric(tail.mean(), 'mean(losses >= historical_var)'),
        'maximum_drawdown': metric(np.max(1-p/np.maximum.accumulate(p)), 'max(1 - price / running_peak)'),
        'tail_observations': Metric(value=float(len(tail)), formula='count(losses >= VaR)', unit='observations', evidence=refs),
    }
    complete = all(x.benchmark is not None for x in prices)
    if complete:
        b = np.array([x.benchmark for x in prices], dtype=float)
        br = b[1:]/b[:-1]-1
        variance = np.var(br, ddof=1)
        out['beta'] = metric(np.cov(r, br, ddof=1)[0,1]/variance if variance > 0 else None, 'cov(asset_returns, benchmark_returns) / var(benchmark_returns)', None if variance > 0 else 'Zero benchmark variance')
        out['benchmark_correlation'] = metric(np.corrcoef(r, br)[0,1] if variance > 0 and np.std(r)>0 else None, 'pearson(asset_returns, benchmark_returns)', None if variance > 0 and np.std(r)>0 else 'Constant returns')
    else:
        out['beta'] = metric(None, 'cov(asset_returns, benchmark_returns) / var(benchmark_returns)', 'Complete date-aligned benchmark required')
    return out
