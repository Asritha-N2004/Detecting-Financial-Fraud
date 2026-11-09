# Overlapping-risk and weight sensitivity

Sensitivity version 1 is a separate diagnostic over saved specialist scores. It does not change the canonical weights, risk score, category, assessment history or monitoring recommendations. It does not claim to remove double counting, calibrate default probabilities, or improve predictive accuracy.

## Score-driving input reuse

Each deterministic specialist now emits typed `score_components`: component ID, metric/source references, primitive input fields, bounded rule score, within-dimension weight and inclusion status. Complete dimensions use the actual equal component weights from their existing score rules. Failed/incomplete dimensions do not claim included components. The critic recomputes this metadata and the sensitivity report; tampered dependencies or diagnostics produce correctable objections.

Only score-driving inputs count. Displaying a ratio in another agent's metrics does not count as scoring it twice. Dependencies include debt/assets, debt/equity, profitability, cash coverage, price-history rules and distinct supplied operational indicators. This map records exact primitive-field reuse and can miss broader economic relationships between different fields.

For dimension d and input f, exposure `E[d,f]` is the sum of each included component's within-dimension weight divided equally among that component's distinct primitive inputs. Exposures sum to one per complete dimension. Pairwise input reuse is weighted Jaccard:

`J(a,b) = sum_f min(E[a,f], E[b,f]) / sum_f max(E[a,f], E[b,f])`.

This fraction is structural input reuse, **not** empirical correlation, loss dependence, a probability, or a justified redundancy discount. Per-component configured contributions are `dimension_weight * component_weight * rule_score`. Missing or legacy component metadata is marked unavailable rather than reconstructed from an LLM or inferred from prose.

## Explicit weight transfers

Default steps are 5 and 10 percentage points. Each scenario moves a stated amount from one donor dimension to one recipient, with all other weights fixed. Requested steps must be unique, ascending fractions in (0,.25], with at most three steps. Actual transfer is capped by donor weight and recipient capacity; both requested and actual transfer are recorded. No hidden normalization occurs.

For complete scores, `delta_score = actual_transfer * (recipient_score − donor_score)`, subject to the canonical aggregate's display precision. For unavailable dimensions, the usual fixed-weight missing-score bounds are recomputed; missing risk never becomes zero. A previously zero-weight unavailable dimension can make an exploratory point score unavailable if it receives weight.

The report contains every scenario's full weights, score/interval, category, delta and category-change flag. Its envelope is the min/max of the baseline and sampled intervals. Classification stability is null if any scenario lacks a complete point score. Otherwise it describes only that sampled grid, not all possible weight allocations. The envelope is not a statistical confidence interval or a calibrated loss range. No weight setting is recommended automatically.

## Optional empirical score history

Asset-return covariance is not dimension-risk correlation. A single assessment cannot estimate empirical cross-risk dependence. Optional `risk_score_history` supplies dated historical dimension score levels with its own provenance, entity name, `model_version: rules-2.0`, holding horizon and confidence setting. Entity/horizon/confidence, currency and synthetic/real origin must match the assessment. Dates are unique, ascending, historical and cannot extend beyond its dated source evidence. Scores are [0,100] or null, known dimension names only; at most 1000 rows are accepted.

At least 30 observations complete across all five dimensions are required. Incomplete rows are dropped explicitly and counted; there is no forward fill or pairwise deletion. From the complete score-level matrix X, compute sample covariance `S` with ddof=1 and Pearson correlations. Constant dimensions have null correlations, not zeros or independence claims. Report current-weight aggregate variation `w.T @ S @ w`, its square root in score points, per-dimension variance contributions `w[i] * (S @ w)[i]` and pair cross terms `2*w[i]*w[j]*S[i,j]`. Negative contributions are retained.

These are descriptions of supplied score history, not financial-loss covariance, causal effects or probabilities. Serial dependence, regime changes and unverified source quality limit interpretation. No p-values, effective-sample-size claim, significance threshold or automatic correlation discount is supplied. Source/model consistency still requires independent real-world validation. Synthetic history is explicitly labeled as demonstration data.

## API, UI and persistence

Normal orchestration computes sensitivity during aggregation, validates it in the critic, checkpoints it, and persists it in result JSON and the risk-score artifact. Workflow version 4 / sensitivity version 1 prevent incompatible queued jobs from silently mixing metadata; the canonical financial engine/rule version remains unchanged. No SQL migration is needed.

- `GET /api/v1/assessments/{id}/sensitivity`: authorized access to the saved report; 409 if not ready or absent on an older assessment.
- `POST /api/v1/assessments/{id}/sensitivity`: analyst/admin exploratory diagnostic using saved outputs, optional full five-dimension `weights` and `transfer_steps`. Validation failures return 422. Other organizations receive 404. The result includes the original `assessment_aggregate` and `exploratory: true`.

POST records the chosen weights/steps and a summary in the audit log. It does not rerun specialists, call a paid model, or overwrite the source assessment or saved sensitivity. Older outputs can support weight transfers while explicitly lacking structural metadata. A supplied historical profile is immutable assessment input, not a request to fetch other organizations' histories.

Risk Analysis includes a sensitivity explorer with explicitly validated percentage weights, sampled outcomes, shared-input dependencies, optional score-correlation matrix and source limitations. Saved and exploratory scores are labeled separately; reset restores the saved configuration. Switching assessments discards exploratory and stress state.

## Reproduction and tests

`python scripts/export_sensitivity_demo.py` creates `data/synthetic/sensitivity_history.json`, a complete importable assessment bundle with 60 explicitly assumed score-history rows. Its leverage/profitability dependencies are constructed deterministically; the constant operational series demonstrates null correlations. Those scores are a dependency illustration, not measured historical company assessments. Import the bundle through New Assessment to inspect empirical diagnostics. No real history is invented for the ordinary three demos.

`python scripts/export_frontend_fixtures.py` runs the actual offline Python engine to regenerate synthetic frontend response fixtures. Tests verify hand-computed transfers and boundaries, bounded missing dimensions, structural-versus-empirical distinction, component reconstruction, constant/negative correlations, covariance cross-term identities, complete-case thresholds, invalid/incompatible histories, tamper detection, persistence, authorization and immutable canonical results.

Representative real score panels, independent taxonomy review, empirical calibration of any redundancy mitigation, bootstrap/time-series uncertainty, and outcome validation remain research work. Passing these software tests is not evidence of improved financial forecasting.
