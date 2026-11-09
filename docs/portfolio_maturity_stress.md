# Portfolio covariance, maturity analysis and stress projections

Financial engine version 2 adds these calculations. Assessment rule metadata is `rules-2.0`; durable workflow version 3 prevents incompatible older checkpoints from silently mixing new calculations into saved state. Historical assessment inputs/results are preserved. These models are deterministic research calculations, not calibrated predictions or regulatory compliance tests.

## Constituent portfolios

`portfolio_holdings` is an array of up to 20 positive-weight constituents. Each has `symbol`, `weight`, its own `provenance`, and historical `prices` (`date`, positive `close`, optional `benchmark`). Weights sum to one; legacy `portfolio_weights`, if also present, must match the constituent ordering and weights. At most 50,000 total constituent prices are accepted. Currency and synthetic/real origin must match the assessment; source mixing or implicit FX conversion is rejected. Symbols and dates must be unique and dates ascending/historical.

Each constituent must have exactly the same observed calendar. The engine does not forward-fill prices, discard observations silently, use pairwise covariance, or substitute a single asset's prices. Fewer than `max(31,holding_days+2)` aligned prices produces unavailable analytics and an incomplete market dimension.

For the T×K simple-return matrix R and weights w:

- Sample covariance `Σ = (R − mean(R)).T @ (R − mean(R)) / (T−1)`, consistent with [`numpy.cov(..., rowvar=False, ddof=1)`](https://numpy.org/doc/stable/reference/generated/numpy.cov.html).
- Daily variance `w.T @ Σ @ w`; annual covariance `252Σ`; annual volatility `sqrt(252 * w.T @ Σ @ w)`.
- Volatility contribution of asset i: `w[i] * (Σw)[i] / σp`; contributions sum to portfolio volatility. Variance shares divide these contributions by σp. Negative contributions are retained when historical covariance implies a hedge.
- Diversification ratio `sum(w[i] * σ[i]) / σp`; diversification benefit is the difference between weighted standalone volatility and portfolio volatility.
- Correlation is covariance divided by constituent volatilities. Zero-volatility correlations, contributions for zero portfolio volatility, and the diversification ratio's zero denominator are unavailable rather than NaN.

Historical portfolio returns are `R @ w`, representing constant weights rebalanced each observation without fees. A cumulative index feeds the existing historical VaR/CVaR, drawdown and volatility calculations. An assessment `prices` benchmark is used only when dates align exactly; a supplied `portfolio_value` converts fractional VaR into currency. Constituents are not assumed to be components of the company's accounting balance sheet without an explicit linkage model.

Singular covariance is allowed and disclosed; no inverse or optimization is attempted. Sampling noise, adjusted-close quality, market calendars, FX and turnover costs still require source review. No expected investment return is inferred.

## Dated debt and operating flows

`debt_schedule` contains `as_of`, `provenance`, `complete`, `payments`, `operating_flows`, `operating_flows_complete`, and optional `operating_flows_through`. Its as-of must match the latest statement. Payments contain a unique `id`, `due_date`, nonnegative `principal` and `interest`, and `rate_type` (`fixed`, `floating`, `unknown`). Dates are ascending and cannot precede as-of; future contractual payments are allowed. A complete principal schedule must reconcile to total debt. A partial schedule cannot exceed total debt.

Operating rows contain a unique `id`, `date`, nonnegative `inflow` and `outflow`. They exclude principal and interest so debt service is not counted twice. Claiming complete operating data requires an explicit coverage-through date. Provenance currency/origin must match the assessment.

The engine groups supplied obligations into inclusive day buckets 0–30, 31–90, 91–180, 181–365, 366–730, and >730. It reports 365-day principal/interest, cash/debt-service coverage, principal-weighted residual maturity, dated net flows, first cash shortfall, and peak funding gap. Cumulative cash equals opening cash plus supplied operating flows minus debt service. Same-day flows are netted; no intraday ordering is modeled. Cash gaps cover 365 days only; subsequent cash balances are withheld. Later principal buckets remain visible without inventing future operating receipts.

Incomplete debt, operating coverage, or opening cash is explicit. A gap is conditional on supplied flows; an incomplete profile cannot establish funding adequacy. Reported `debt_due_12m` is reconciled against 365-day principal and disagreements disclosed. Maturity monitoring is supplementary: it does not silently add correlated score terms or reweight the existing liquidity rules.

This approach is informed by contractual time-band analysis described in [BIS liquidity monitoring metrics, SRP50.6–50.13](https://www.bis.org/committees/bcbs/basel-framework/standard/srp/50/inforce/2019-12-15/published/2019-12-15). The application's corporate model and chosen buckets are not a Basel bank-reporting implementation.

## Matched one-year stress projection

Presets include the original six shocks plus `baseline`, `adverse`, and `severe`. Requests may override market return, floating rate increase, revenue/cost changes, a nonpositive cash-availability haircut, variable cost share, tax rate, capex, dividends, collection delay, and constituent spot shocks. Only a 365-day projection is supported. `reporting_days` (default 365) scales the source income/cash-flow period to that horizon. Tax rate 25% and variable cost share 60% are illustrative configurable assumptions.

Let `t=365/reporting_days`, costs `(revenue−EBIT)*t`, revenue shock r, cost shock c and variable share v. Projected revenue is `revenue*t*(1+r)`; projected costs are `costs*(1+c)*(1+v*r)`. The cost-of-goods share of total operating costs is held constant. The remainder is fixed-cost exposure. Negative or unreconcilable cost classification prevents projection.

Floating-rate incremental interest is `sum(floating_principal * rate_shock * min(days_to_repayment,365)/365)`. Fixed debt does not reprice. Unknown exposure blocks rate-shock projection. Scheduled interest is paid on its supplied dates; incremental interest on debt extending beyond the year is paid at the horizon. No compounding, hedging or new borrowing is inferred.

Reported OCF is assumed after cash interest and tax. A complete dated operating profile must cover the year and reconcile to `(OCF + interest_expense)*t`. It supplies baseline cash timing. Otherwise, pre-debt-service OCF is explicitly spread uniformly; collection-delay scenarios require a complete profile and are withheld without it. Incremental operating earnings and tax effects are spread uniformly; delaying receipts moves them to later dates and excludes receipts beyond the horizon from current-year cash. Loss tax shields are assumed realizable within the year; this may be inappropriate for a real company.

With ΔEBIT, source interest I0, scheduled interest Is, incremental interest ΔI and tax rate τ:

`projected_NI = source_NI*t + (ΔEBIT + I0*t − Is − ΔI)*(1−τ)`.

Cash OCF applies the same earnings/interest changes to source OCF and additionally reflects receipts delayed outside the year. Principal, capex and dividends are separate dated cash outflows. The cash haircut transfers opening cash into noncurrent restricted cash: it reduces availability, not equity. Capex is capitalized; dividends reduce equity. There is no automatic refinancing, emergency funding or balancing plug.

The accounting bridge holds inventory and nondebt liabilities fixed, allocates `NI−OCF` to other noncash current assets, and reclassifies debt due in the following 365 days into current liabilities:

```text
closing_cash = opening_cash + projected_OCF − principal − capex − dividends − restricted_cash
closing_assets = opening_assets + projected_NI − principal − dividends
closing_liabilities = opening_liabilities − principal
closing_equity = opening_equity + projected_NI − dividends
```

Noncurrent assets absorb capex and restricted cash. The `NI−OCF` allocation is a scenario assumption; it does not establish the true source of noncash adjustments such as depreciation. Infeasible negative components, unreconciled opening balances, missing inputs or incomplete debt schedules prevent a projected score. Any intraperiod funding deficit withholds the adverse statement/score even when closing cash is positive.

Conditional score comparisons use feasible balanced forward baseline and adverse statements over the same year. Only credit, financial and liquidity metrics are rescored; historical market/operational contributions are held fixed. Missing dimensions keep their weight and interval. Point deltas are null when scores are unavailable. Spot portfolio P&L is reported separately using `sum(weight * constituent_shock)`; it is not charged to company earnings or used to manufacture a future covariance estimate.

The synthetic healthy company has a feasible adverse projection. Its combined-adverse scenario ends with approximately 7.80 cash units yet has an earlier funding gap, demonstrating why a year-end cash-only check is insufficient. The leveraged and volatile cases expose funding stress without invented financing.

## Usage and verification

Regenerate complete examples with `python scripts/export_demo.py`. The three JSON bundles now contain three constituent histories, fixed/floating dated debt and a covered operating-flow profile. Upload one using **New assessment → Import a complete evidence bundle**, or POST it to `/api/v1/assessments`. Portfolio matrices and maturity analytics appear in Risk Analysis; Stress Testing shows matched scores, the cash bridge, a timing chart and funding limitations.

Tests independently construct centered covariance and weighted returns; check singular/zero variance and negative contributions; validate dates, weights, currency and origin; test all maturity boundaries; verify fixed/floating exposure and accounting identities; distinguish intraperiod versus terminal cash; exercise receipt delays and partial coverage; check artifact persistence, tenant isolation, critic recomputation and the browser workflow. Real financial calibration and independent production model validation remain outstanding.
