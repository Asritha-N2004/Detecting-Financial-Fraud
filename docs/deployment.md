# Installation, configuration and deployment

Use Python 3.11+ (verified on 3.12.10) and Node 22+. Follow README for local setup. SQLite database path is relative to the backend working directory. Migrations must run before API startup; the application does not silently create schema on requests. `scripts/init_local.py` generates excluded local `.env` files; keep secrets out of Git and backups intended for sharing.

| Variable | Default / purpose |
|---|---|
| `DATABASE_URL` | `sqlite:///./risk.db`; PostgreSQL uses `postgresql+psycopg://...` |
| `JWT_SECRET` | No usable default; at least 32 characters required |
| `TOKEN_MINUTES` | 60; signed JWT lifetime |
| `CORS_ORIGINS` | Comma-separated explicit local frontend origins |
| `MODEL_PROVIDER` | `deterministic` or `openai-compatible` |
| `SPECIALIST_PROVIDER` | `deterministic` or `openai-compatible`; independent of narrative mode |
| `SPECIALIST_MODEL` | Default specialist model; falls back to `OPENAI_MODEL` |
| `SPECIALIST_MODELS` | JSON map of dimension-specific model overrides |
| `AGENT_PROMPTS_DIR` | Optional administrator-owned directory containing all five role Markdown files |
| `LLM_MAX_TOOL_ROUNDS` | 3; bounded 1–5 read-only metric tool rounds |
| `LLM_MAX_COMPLETION_TOKENS` | 2000 per specialist model response |
| `OPENAI_API_KEY` | Required only for optional compatible narrative provider |
| `OPENAI_MODEL` | Configurable structured-narrative model ID |
| `OPENAI_BASE_URL` | Optional compatible provider endpoint |
| `AGENT_TIMEOUT_SECONDS` | 30 per specialist attempt |
| `AGENT_RETRIES` | 1 retry after the initial attempt |
| `UPLOAD_LIMIT_BYTES` | 2,000,000 compressed input bytes |
| `POSTGRES_PASSWORD` | Required for Compose; generated locally |
| `VITE_API_BASE_URL` | Build-time frontend API base; defaults `/api/v1` |
| `API_PROXY_TARGET` | Vite development proxy only; defaults `http://127.0.0.1:8000` |
| `E2E_BASE_URL` | Playwright target; defaults `http://127.0.0.1:5173` |
| `WORKER_ENABLED` | true; start an embedded poller in each API process; false for separate workers |
| `WORKER_POLL_SECONDS` | .5; polling interval when idle |
| `JOB_LEASE_SECONDS` | 60; renewable lease duration (10–3600) |
| `JOB_MAX_ATTEMPTS` | 3; stored on enqueue, bounded 1–10 |
| `JOB_RETRY_SECONDS` | 2; delay after a recoverable job failure |

The optional market adapter is installed with `pip install -r requirements-market.txt`. External provider availability, currency metadata, licensing and quality must be assessed before production use. A provider failure returns 502 and users can upload local evidence instead. No external market data were fetched during validation.

Docker Compose includes PostgreSQL persistence, an unprivileged Python user, migrations, health checks, a separate durable worker and Nginx same-origin routing. It binds the UI to localhost:8080. The API has `WORKER_ENABLED=false`; the worker starts after backend health confirms migration completion. Use a URL-safe database password or URL-encode it for SQLAlchemy credentials. Root `.env` is used by Compose; backend `.env` is used for direct Python startup. Empty optional environment values are ignored so model defaults remain valid. The generated secrets are independent.

Before internet exposure, configure TLS and trusted reverse-proxy behavior, disable public organization registration if inappropriate, add a distributed rate limiter, move secrets into a managed secret store, configure backups/retention and database least-privilege roles, test PostgreSQL migrations and restore procedures, pin and audit exact production dependencies, and perform a security review. These are deployment requirements for this application, not completed claims.

Durable job ownership and stage resume replace the original in-process job model. Graceful shutdown requeues owned work with its checkpoint; hard termination is recovered after lease expiry. API startup does not fail another worker's jobs. Completed stages are preserved, but an in-flight stage may replay and repeat provider billing. See [durable jobs](durable_jobs.md). Run migrations once before starting/scaling workers; validate PostgreSQL contention, load, lease sizing and failover before production scaling. Compatible worker configuration is enforced by a runtime manifest and prompt hashes. Do not mix pre-queue application versions with the new workers.

Sites hosting executes Workers, and cannot run this Python service or raw PostgreSQL stack. A frontend-only publication would not meet the requested functional deployment. No such static-only publication is made. Docker daemon was unavailable in this environment; Compose configuration can be validated separately but successful container deployment is outstanding.

## Live Vercel configuration

The repository-root services deployment now hosts the frontend and FastAPI on one HTTPS origin with Neon PostgreSQL in an isolated schema. Registration, sign-in and assessment execution were verified live. A worker container image is deployed, but exhausted team Daemons quota prevents a running instance; bounded request execution and saved-work resume are active instead. See [current Vercel deployment](vercel.md) for configuration, verification and the unattended-recovery limitation.
