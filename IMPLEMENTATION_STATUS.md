# Implementation status

Updated 2026-11-09. The repository started empty. A working local research application is implemented; the full production/research acceptance scope is **not yet complete**.

| Phase | Implemented | Verification / remaining scope |
|---|---|---|
| 1 Inspection/init | Empty repository inspected, modular project initialized | No pre-existing code changed |
| 2 Database | 18 SQLAlchemy tables; frozen initial migration plus `0002` durable jobs | Fresh/previous-schema SQLite upgrades, interrupted-job adoption and schema parity passed; PostgreSQL execution outstanding |
| 3 Quant engine | Existing financial/portfolio/maturity/stress calculations plus typed scoring dependencies, structural overlap, explicit weight-transfer sensitivity and optional comparable score-history covariance/correlation | Hand/reference calculations, bounds, complete-case thresholds, zero/negative correlation, classification changes, missing dimensions and immutable canonical scores verified; no automatic correlation discount |
| 4 Specialists | Five deterministic calculation specialists plus independent LLM interpretations, configurable role prompts/model overrides, strict schema and bounded read-only tools | All five roles and real SDK HTTP contract tested with offline mocks; live model/provider validation outstanding; numeric scores remain Python-only |
| 5 Orchestration | LangGraph, parallel specialists, dependent stages, retries/timeouts; durable leased queue, heartbeat, stale-worker fencing and versioned JSON stage resume | Concurrent claims, every stage boundary, reflection-state retention, API restart, shutdown and real child-process crash/recovery passed on SQLite; PostgreSQL load/failover outstanding |
| 6 Critic/reflection | Explicit source/numeric/contradiction/confidence rules; targeted corrections; max 3 cycles | Actual tamper repair and failure-limit tests passed; independent numerical model validation remains |
| 7 Explainability | Canonical explanations, LLM disclosure controls and score-component/input-dependency sensitivity persisted with critic validation | Dependency reconstruction, diagnostic tampering and historical-score limitations tested; no empirical predictive accuracy or redundancy calibration claim |
| 8 API/auth | JWT/scrypt, organizations, roles, assessment lifecycle, uploads, stress, audit, staged external adapter | Lifecycle/tenant/role tests passed; production identity and distributed controls remain |
| 9 Frontend | Existing pages plus interactive overlap/weight/history diagnostics, account-switch cache clearing and assessment-scoped exploratory/stress state | 34 frontend tests across 7 files, including 23 HTTP-boundary integration checks; TypeScript/build verified; representative usability/accessibility and broader browser coverage remain |
| 10 Data | Three seeded bundles with three years of statements, benchmark, three constituent histories, fixed/floating dated debt and covered operating flows | Regenerated and validated; demo/import/API persistence tested; live Yahoo adapter unverified |
| 11 Integration | Persisted API lifecycle/recovery, provider/numeric contracts, sensitivity authorization and expanded frontend/API integration | 102 backend tests, 34 frontend tests, 2 real-backend browser workflows passed; TypeScript, production build, schema parity and evaluation verified |
| 12 Evaluation | Four configurations × three scenarios × clean/faulted = 24 observed cases; static comparison figure | 100% injected correctable-issue recovery in one cycle per scenario; no financial accuracy claim |
| 13 Deployment/docs | Docker/Compose, backend/frontend CI and a new SQLite-backed Chromium browser CI job; sensitivity and integration methodology documented | Local checks verified; new GitHub Actions browser-job definition not run remotely; Docker/PostgreSQL/container deployment remains unverified |

## Working functionality

Create a workspace, run a synthetic assessment or submit validated uploaded/manual data, inspect numeric calculations and five specialist outputs, see critic concerns and genuine bounded corrections, generate evidence-linked explanations, run hypothetical shocks, and retrieve persistent history with tenant isolation. All nine logical roles execute; specialist and dependent-stage execution durations are recorded. Synthetic source verification remains a warning and is never automatically 'resolved'.

Continuation added opt-in specialized LLM agents with role-specific prompts and per-dimension model overrides. The only model tool reads a metric from its own evidence packet; unknown tools, arguments and references are rejected. Interpretations cannot alter quantitative scores, remain semantically unverified, and fail visibly while preserving deterministic results. Provider-contract tests run without paid access.

Assessment start now atomically enqueues a durable job. Workers renew expiring leases, enforce ownership tokens on checkpoints/finalization, preserve initial/reflection/explanation state and resume the saved next graph stage after interruption. Queue state is available through the tenant-scoped `/job` endpoint and dashboard. Checkpoints are application-managed JSON snapshots at LangGraph node boundaries; an in-flight stage may replay, including already-returned specialists within the parallel-specialist node. Exactly-once model calls/billing are not claimed. See [LLM specialist details](docs/llm_specialists.md) and [recovery guarantees](docs/durable_jobs.md).

Latest continuation implemented constituent sample covariance, correlation, portfolio historical risk and volatility contributions with strict calendars, currency and origin validation. Dated debt and covered operating-flow profiles now produce maturity buckets, weighted maturity and signed cash/funding gaps. The critic recomputes both matrix and maturity analytics. New source references reach explanations and LLM evidence packets; actual constituent symbols/weights and histories persist in portfolio records.

Stress scenarios now compare one-year baseline/adverse cash and accounting bridges, distinguish fixed/floating debt, allow receipt delays, model variable/fixed costs, capex/dividends and restricted-cash transfers, and report separate constituent spot P&L. Unreconciled inputs, incomplete coverage or any intraperiod funding gap withhold projected scores. Conditional score changes update financial/credit/liquidity ratios while holding historical market/operational contributions fixed. No borrowing, balancing plug or future covariance is invented. The synthetic healthy combined-adverse case deliberately demonstrates positive closing cash with an earlier funding deficit. See [methodology and input guide](docs/portfolio_maturity_stress.md).

Financial engine version 2 / workflow version 3 record this change. Existing assessment results remain unchanged; old queued runtime manifests cannot silently resume under the new engine. No table migration was needed for the additional validated JSON inputs and analytics. Evaluation bundles/results and comparison figures were regenerated; they still measure controlled software fault recovery, not predictive financial accuracy.

Latest continuation adds sensitivity version 1 / durable workflow version 4 while leaving canonical financial rules and scores unchanged. Score-driving components now identify their exact input/source dependencies. The overlap report distinguishes structural field reuse, explicitly sampled weight transfers and optional historical dimension-score dependence. Empirical calculations require 30 jointly complete, matching entity/model/horizon/confidence observations and disclose dropped rows, constant dimensions and synthetic provenance. No correlation is inferred from one assessment or substituted from asset-price covariance. No uncalibrated overlap discount is applied. Saved reports survive checkpoints and final persistence; exploratory API requests are authorized/audited and do not rerun models or overwrite assessment results. See [sensitivity methodology](docs/risk_sensitivity.md).

Frontend coverage now exercises real Axios serialization/auth interceptors, React Query cache/mutations/polling and rendered pages through a test HTTP adapter, using synthetic response fixtures generated by the Python engine. The 23 added integration cases cover authentication/account isolation, pagination, query errors, create/run ordering and failures, multipart staging, recovery polling, unavailable scores, reflection/explanation/audit views, sensitivity/history disclosures and stress/assessment switching. Query caches/selection are cleared between accounts, and stress/sensitivity state is keyed by assessment to avoid stale results. Recharts remains real in integration tests with only responsive measurement fixed; browser tests verify layout and server behavior. The 24-case controlled evaluation and comparison figures were regenerated.

## Verification commands

```powershell
cd backend
python -m alembic upgrade head
python -m pytest -q
python -m app.evaluation
cd ../frontend
node node_modules/typescript/bin/tsc -b
node node_modules/vite/bin/vite.js build
node node_modules/vitest/vitest.mjs run
$env:E2E_BASE_URL='http://127.0.0.1:5174'
node node_modules/@playwright/test/cli.js test
```

Local validation ports are API 8017 and Vite 5174 because other services already occupy 8000/5173. Use `API_PROXY_TARGET=http://127.0.0.1:8017` for the frontend. Secrets were generated in ignored root/backend `.env` files without output. Preview server processes should be restarted with README commands after this session.

## Remaining acceptance work

Vercel deployment preparation: target `resum-projects` is accessible in the signed-in browser. Added frontend Vite build/SPA configuration and upload exclusions; strict TypeScript and the production build pass. CLI authorization completed and the frontend deployment reached READY at https://reflective-risk-intelligence.vercel.app; its live sign-in page was verified in the browser. The FastAPI service, existing Neon database (isolated prism_risk_v1 schema), and durable worker image are now deployed. Live registration/sign-in, synthetic assessment completion, persisted analysis and stress execution pass. The team exhausted its Hobby Daemons quota, so the persistent worker is scaled to zero; bounded request execution and an authenticated saved-work resume action provide assessment processing. Unattended recovery still requires daemon capacity. See docs/vercel.md for the precise operational limits. See [Vercel deployment](docs/vercel.md).

1. Run the complete Docker Compose stack on a machine with a functioning Docker daemon and Compose plugin. Vercel HTTPS frontend/FastAPI, Neon migrations and a real browser synthetic assessment are verified; an always-running worker remains blocked by exhausted team Daemons quota, with request-bound execution active.
2. Validate the implemented durable queue on PostgreSQL under multi-process contention, lease expiry, database outages and production load. Consider per-specialist checkpoints, dead-letter/operator retry tooling and native LangGraph history/time travel. Current in-flight stages can replay and repeat provider billing.
3. Validate specialized LLM agents with authorized credentials, supported models and representative financial evidence; measure semantic claim support and prompt-injection resistance. Code, prompts, strict output/tool contracts and offline tests are implemented. Paid live calls have not been made. Configure explicit model pricing before reporting paid assessment costs.
4. Supply representative labeled credit data, calibrated PD artifacts and out-of-sample model evaluation before serving probabilities or feature attribution.
5. Portfolio/maturity/stress and overlapping-risk/weight/history sensitivity are implemented. Remaining work includes validating the dependency taxonomy and any redundancy mitigation against representative real score panels/outcomes, time-series uncertainty and regime stability, portfolio optimization or derivatives/FX, dynamic covariance/costs, multi-year refinancing/funding-facility models, and independent accounting/tax/cash-conversion validation. Current diagnostics are descriptive and do not alter the canonical model or forecast market/operational risk.
6. Frontend HTTP-boundary integration coverage is expanded and locally tested. Remaining work includes representative browser/accessibility/usability matrices, additional network-interruption/retry flows, and running the new browser CI job remotely. Semantic claim verification, independent production numeric verification, distributed rate controls, credential rotation, retention and security/load testing remain outstanding.
7. Repeat experiments on representative real evidence, establish external ground truth and confidence bounds before generalized accuracy claims. Current figures summarize controlled fault-recovery cases only.
8. Freeze and test exact Python transitive dependencies in a clean environment. The frontend has a generated pnpm lockfile; current preinstalled Python packages are not a fully reproduced production environment.

No pending tool approvals or unavailable credentials were treated as permission or invented success. Files are preserved for continuing these units.
