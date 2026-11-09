# API

Interactive OpenAPI documentation: `/docs`; machine-readable schema: `/openapi.json`. Prefix: `/api/v1`.

Register creates a new organization and admin; subsequent registration cannot join another organization. Protected routes require `Authorization: Bearer <token>`. JWT lifetime defaults to 60 minutes. Admin/analyst can create, start, upload, import and stress test; viewers can read within their organization. Cross-organization resources return 404. Organizations intentionally share assessments among authorized users.

| Method | Path | Behavior |
|---|---|---|
| POST | `/auth/register` | Email, password (12–128 chars), organization; returns JWT |
| POST | `/auth/login` | Email and password; returns JWT |
| POST | `/assessments` | Validated evidence bundle; 201 pending assessment |
| GET | `/assessments?offset=0&limit=20` | Tenant list, total and pagination (max 100) |
| GET | `/assessments/{id}` | Input, status, score, complete result |
| POST | `/assessments/{id}/run` | Atomic pending→running; 202, 409 for repeated start |
| GET | `/assessments/{id}/agents` | Execution attempts and structured specialist outputs |
| GET | `/assessments/{id}/job` | Durable status, attempts, heartbeat, saved next stage and sanitized error; no lease token |
| GET | `/assessments/{id}/reflections` | Ordered correction history |
| GET | `/assessments/{id}/explanations` | Explanation or 409 when not ready |
| GET | `/assessments/{id}/sensitivity` | Saved overlap/weight/history diagnostic or 409 if absent/not ready |
| POST | `/assessments/{id}/sensitivity` | Analyst/admin exploratory weights/steps; auditable, canonical score unchanged |
| POST | `/assessments/{id}/stress-tests` | Named scenario and optional bounded shocks |
| GET | `/assessments/{id}/audit` | Paginated events, default 100, max 500 |
| POST | `/data/financial-statements` | Multipart CSV/XLSX/JSON staging |
| POST | `/data/market-data` | Multipart CSV/XLSX/JSON staging |
| POST | `/import/market` | Optional Yahoo adapter; symbol, start, end, currency |
| POST | `/demo/{healthy,leveraged,volatile}` | Create and run labeled synthetic assessment |
| GET | `/health` | Database connectivity, API version, narrative mode |

Assessment JSON shape is demonstrated by `data/synthetic/healthy.json`. Statements require `period` and `currency`; remaining financial fields are nullable. Prices require `date`, positive `close`, optional positive aligned `benchmark`. Portfolio weights must be long-only and sum to 1. Operational indicators require name, severity (`low/moderate/high`) and evidence text. The combined evidence bundle carries explicit provider, source, currency and synthetic flag.

Staging endpoints return validated rows without storing unassociated uploads. The final assessment submission stores those rows with entity and provenance after cross-file validation. CSV/XLSX columns match JSON keys. A combined assessment JSON bundle is submitted directly to `/assessments`, not to a single-table upload endpoint.

Stress requests require a known scenario. Optional `market_return`, `revenue_change`, `cost_change`, `cash_change`, and `rate_increase` override scenario assumptions. Returns are fractions, not percentages.

Financial-engine v2 also accepts `variable_cost_share`, `tax_rate`, `capex`, `dividends`, `collection_delay_days`, `asset_shocks` (known constituent symbols to fractional shocks), and a 365-day horizon. `cash_change` is now a nonpositive availability haircut in [-1,0], not an unexplained cash windfall. Added presets are baseline/adverse/severe. Responses include historical risk, forward baseline/adverse projections, funding gaps, the cash bridge, accounting residual, conditional score deltas and separate portfolio spot P&L. Unknown symbols and invalid shocks return 422. Stress artifacts/audit remain tenant-scoped and persisted.

Assessment bundles can now carry `portfolio_holdings`, optional `portfolio_value`, and `debt_schedule` with dated payments, operating flows and explicit coverage dates. Exact input examples are in regenerated synthetic bundles and [the methodology/input guide](portfolio_maturity_stress.md). The New Assessment page imports complete JSON bundles; the existing single-table CSV/XLSX staging endpoints remain unchanged. Real symbols/weights and constituent histories are stored in portfolio records; no schema migration was required for these JSON payload extensions.

Errors have shape `{"error":{"code":"...","message":"...","details":[]}}`; `details` is present for request schema errors. Status codes include 401, 403, 404, 409, 413, 422, 429, 502 and 503. Request IDs are returned in `X-Request-ID`. Logs omit request bodies, credentials and authorization headers. No polling endpoint returns a fabricated result while analysis is pending.

Starting an assessment queues durable work in the status-transition transaction. A 202 response does not depend on a request-owned background task. LLM interpretation is configured server-side and returned separately as `llm_interpretation` in each specialist output. Structured model errors do not remove the deterministic metrics or silently change the overall score.

Sensitivity POST accepts an optional complete five-dimension `weights` map and `transfer_steps` (ascending fractions up to .25). It uses persisted specialist outputs, makes no LLM call, and records an audit event without changing assessment scores. Optional `risk_score_history` is supplied in the original assessment bundle with matching entity/provenance/model configuration; it is never inferred from asset returns. Full validation and interpretation are documented in [risk sensitivity](risk_sensitivity.md).
