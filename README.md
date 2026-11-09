# Prism — Reflective Financial Risk Intelligence

Implementation of **A Self-Reflective Multi-Agent Architecture for Financial Risk Analysis and Decision Explanation**.

Prism runs five financial specialists in parallel, with optional specialized LLM interpretations over deterministic Python evidence. It aggregates fixed-weight risk contributions, checks outputs with an independent critic, performs bounded targeted corrections, and produces evidence-linked explanations. A durable leased queue resumes checkpointed work after interruption. A React dashboard reads persisted API results. No paid API is required for the default workflow. Synthetic companies are explicitly labeled.

This is a working research application with production-oriented separation of concerns, not a production-certified financial model. See [implementation status](IMPLEMENTATION_STATUS.md) and [limitations](docs/limitations.md) before deployment.

## Quick start

Python 3.11+ and Node 22+ are required. Commands below start from the repository root. Use two terminals for the servers.

```powershell
python scripts/init_local.py
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
cd backend
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In the second terminal:

```powershell
cd frontend
corepack enable
pnpm install
pnpm dev
```

Open `http://127.0.0.1:5173`. Create a workspace with a password of at least 12 characters. On Overview, run any synthetic scenario; inspect analysis, agents, reflection, explanation, stress testing, and audit history. No company data or credentials are preloaded. The local secret initializer preserves existing `.env` files and never prints credentials.

If default ports are occupied, run the backend with `--port 8017` and set `$env:API_PROXY_TARGET='http://127.0.0.1:8017'` before starting Vite with `--port 5174`. API documentation is at `http://127.0.0.1:8017/docs` in that configuration.

## Verified commands

```powershell
cd backend
python -m alembic upgrade head
python -m pytest -q
python -m app.evaluation
cd ../frontend
pnpm build
pnpm test
# Requires the backend running and a Playwright Chromium installation:
pnpm exec playwright install chromium
pnpm test:e2e
```

For Windows sandbox restrictions affecting package-manager shims, equivalent local commands are `node node_modules/typescript/bin/tsc -b`, `node node_modules/vite/bin/vite.js build`, `node node_modules/vitest/vitest.mjs run`, and `node node_modules/@playwright/test/cli.js test`. Python's async event loop requires local socket permission even for in-process tests.

## Deployment

The requested Python/PostgreSQL stack runs using Docker Compose, rather than a static-only hosted dashboard:

```powershell
python scripts/init_local.py
docker compose up --build -d
```

Open `http://localhost:8080`. Compose starts PostgreSQL, runs migrations, waits for API health, and serves React through Nginx with a same-origin API proxy. Credentials are read from root `.env`. **Container execution has not been verified on this workstation because no Docker daemon is available.** No remote deployment has been made. See [deployment](docs/deployment.md).

## Implemented behavior

- Financial ratios, historical volatility/VaR/CVaR, drawdown and beta/correlation; constituent covariance, diversification and risk contributions; dated debt buckets and funding gaps; nine hypothetical stress presets with feasible accounting projections and conditional score changes.
- Credit distress indicators and applicability-gated Altman Z. A trainable research logistic baseline is available; default probabilities are withheld without a calibrated artifact.
- Five analysis specialists plus aggregation, critic, reflection, and explanation stages. Structured Pydantic outputs, retries, per-attempt timeouts, explicit failure states, and a three-cycle reflection limit.
- Specialized provider-backed analysis with configurable role prompts/models, strict output contracts, bounded read-only metric tools, reference validation, explicit unverified-prose labels and deterministic fallback.
- Database-backed jobs with renewable leases, stale-worker fencing, stage checkpoints, bounded retries, API restart recovery and an optional standalone worker.
- Overlap diagnostics with score-component input reuse, explicit weight-transfer scenarios and optional validated historical score correlations; saved scores remain unchanged.
- Missing dimensions keep their original weights and widen an overall score interval. No low-risk substitution or silent weight redistribution.
- Authenticated, organization-scoped API; scrypt password hashing; signed expiring JWTs; analyst/viewer authorization; validated uploads; audit history and execution artifacts.
- Eight dashboard routes with backend-driven data, CSV/XLSX/JSON staging, manual statement JSON entry, and one-click seeded demonstrations.
- Controlled four-configuration ablation with clean and fault-injected cases, measured metrics and saved results.

## Repository map

```text
backend/
  app/
    agents/          analysts and independent critic
    core/            environment configuration
    database/        SQLAlchemy engine and sessions
    financial_engine/ratios, market, credit, scoring, stress
    models/          tenant-scoped schema and result artifacts
    orchestration/   typed LangGraph workflow and reflection
    providers/       synthetic, optional market and narrative adapters
    schemas/         validated inputs, metrics, findings and issues
    security/        password hashing, JWT and role checks
    services/        ingestion and async persistence
    evaluation.py    controlled ablation runner
    main.py          FastAPI routes and request controls
  alembic/           frozen initial migration schema
  tests/             numerical, critic, failure, API, isolation, evaluation tests
frontend/
  src/components/    shared status, availability and error components
  src/pages/         dashboard, creation and analysis workspace pages
  tests/             Playwright lifecycle test
data/synthetic/      three complete generated evidence bundles
data/evaluation/     reproducible ablation results
docs/                design, formulas, API, deployment and limitations
scripts/             local secret initialization and dataset export
.github/workflows/   backend and frontend CI
```

## Documentation

[Architecture](docs/architecture.md) · [Agents](docs/agent_design.md) · [Financial models](docs/financial_models.md) · [Reflection](docs/reflection_framework.md) · [API](docs/api_documentation.md) · [Database](docs/database_schema.md) · [Evaluation](docs/evaluation_methodology.md) · [Deployment and environment](docs/deployment.md) · [Testing](docs/testing.md) · [Limitations](docs/limitations.md)

[LLM specialist configuration and contracts](docs/llm_specialists.md) · [Durable jobs and recovery guarantees](docs/durable_jobs.md)

[Portfolio, debt-maturity and stress methodology / input guide](docs/portfolio_maturity_stress.md)

[Overlapping-risk sensitivity / score-history input guide](docs/risk_sensitivity.md)

Observed test outcomes and verification limits: [verification results](docs/verification_results.md).
