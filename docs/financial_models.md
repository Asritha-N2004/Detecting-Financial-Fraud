# Financial formulas and scoring

All amounts must be in one explicit currency. Ratios use period-end assets and equity, not average balances. `operating_income` is used as an EBIT proxy and must be supplied consistently. Missing inputs, zero or negative ratio denominators yield unavailable results rather than infinity. Negative equity is separately flagged as distress.

| Metric | Formula |
|---|---|
| Current ratio | current assets / current liabilities |
| Quick ratio | (current assets − inventory) / current liabilities |
| Debt to equity | total debt / equity |
| Debt to assets | total debt / total assets |
| Gross margin | (revenue − cost of goods) / revenue |
| Operating margin | operating income / revenue |
| Net margin | net income / revenue |
| ROA / ROE | net income / period-end assets or equity |
| Interest coverage | operating income / interest expense |
| OCF coverage | operating cash flow / current liabilities |
| Cash ratio | cash / current liabilities |
| Working capital | current assets − current liabilities |
| Debt service coverage | operating cash flow / annual debt service |
| Revenue growth | latest revenue / prior revenue − 1 |

Original public-manufacturer Altman Z uses `1.2*WC/A + 1.4*RE/A + 3.3*EBIT/A + 0.6*MVE/L + Revenue/A`. It is withheld unless applicability is explicitly asserted. It is an historical distress indicator, not a calibrated default probability. The scikit-learn logistic regression function trains a research baseline, but no representative credit dataset or calibrated serving artifact is supplied. PD is intentionally absent.

Market simple return is `P[t]/P[t-1]−1`. Daily volatility is sample standard deviation (`ddof=1`); annual volatility multiplies it by `sqrt(252)`. Holding-period losses are `−(P[t]/P[t-h]−1)` using overlapping observed periods; no square-root-of-time VaR approximation is applied. Historical VaR is NumPy's linear-interpolated confidence quantile of losses. CVaR is the mean of observed losses greater than or equal to that threshold. VaR/CVaR may be negative when historical losses are negative. Small-tail limitations disclose when fewer than 20 observations enter CVaR. At least `max(31,h+2)` prices are needed. Constituent portfolios now apply the same calculations to their daily-rebalanced weighted return index.

Maximum drawdown is `max(1−P/running_peak(P))`, reported as positive loss fraction. Beta is sample covariance of date-aligned asset and benchmark returns divided by benchmark sample variance; correlation is Pearson correlation. Partial benchmarks or zero variance suppress the affected metric. HHI is `sum(weight²)`. When constituent histories are supplied, covariance, correlation, `w.T @ Σ @ w`, diversification and volatility contributions are calculated from a strictly aligned return matrix. Maturity ladders and signed funding gaps use supplied dated payments and operating flows. See [portfolio, maturity and stress methodology](portfolio_maturity_stress.md).

## Illustrative score rules

Each rule clamps a linear mapping to [0,100]. For an increasing-risk metric use `100*(value−low)/(high−low)`. For a decreasing-risk metric use `100*(good−value)/(good−bad)`. Dimension score is the mean of its available rule contributions only when all required scoring inputs are present. Missing required inputs suppress the dimension score.

| Dimension | Rules: low/high risk anchors |
|---|---|
| Financial | Debt/assets .2→.8; net margin .15→−.1; ROA .1→−.05 |
| Credit | Debt/equity .5→3; interest coverage 5→1; debt service coverage 2→.5 |
| Market | Annual volatility .1→.6; holding-period VaR .005→.08; drawdown .05→.5 |
| Liquidity | Current 2→.5; quick 1.5→.3; cash .5→.05; OCF coverage .5→−.1 |
| Operational | Supplied severity low=20, moderate=50, high=85; mean |

Market score thresholds are illustrative fixed anchors even when the holding period changes; scores across different horizon configurations should not be treated as comparable calibrated risks. Categories are low below 35, moderate below 65, otherwise high.

Default weights are credit .25, market .25, liquidity .20, financial .20, operational .10. Available contributions sum to an observed lower bound. Each missing weighted dimension contributes [0,100] to the overall interval. The point score is null until all positively weighted dimensions are complete. Weights are never silently redistributed. Closely related liquidity/leverage ratios cause correlated dimensions: this is an acknowledged double-counting limitation, not a portfolio independence claim.

Overlap sensitivity now measures primitive input reuse from included score components and explores explicit donor→recipient weight transfers. Optional comparable score history supplies descriptive dimension covariance/correlation only after 30 jointly complete observations. No structural reuse or correlation automatically discounts the canonical score. See [formulas, assumptions and research limits](risk_sensitivity.md).

## Hypothetical stress sensitivity

The six original scenarios plus baseline/adverse/severe presets now produce matched one-year cash/accounting bridges. Fixed debt does not reprice; floating exposure stops at its dated repayment. Costs distinguish fixed/variable shares, receipts can be delayed, and cash haircuts are restricted-cash transfers. Feasible balanced statements permit conditional credit/financial/liquidity score changes while market/operational contributions remain historical. Missing/reconciliation failures or any intraperiod funding gap withhold projected scores. No financing or balancing plug is invented. Full equations, source coverage, assumptions and limitations are documented in [the new methodology](portfolio_maturity_stress.md).
