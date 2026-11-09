# Live Vercel deployment

Application: https://reflective-risk-intelligence.vercel.app
Team/project: `resum-projects/reflective-risk-intelligence`.

The repository-root `vercel.json` deploys a Vite frontend and a Python FastAPI service behind the same HTTPS origin. `/api/*` routes to the API; other routes enter the frontend. Deploy the repository root, not only `frontend`. Source upload exclusions prevent local environment files, databases, package stores and tests from being published.

The existing Neon database remains connected through Vercel environment variables. The app uses a dedicated `prism_risk_v1` schema because the database already contained unversioned tables; those existing tables were preserved. Generic PostgreSQL URLs select psycopg 3. `DATABASE_URL_UNPOOLED` is preferred when present so advisory locks and schema search paths use direct PostgreSQL sessions. Deployment migrations are serialized using an advisory lock and run at service startup. JWT signing material was generated directly into Vercel's secret store without displaying or writing it locally.

## Job execution and current quota limitation

The Python durable worker image is built and deployed as a Vercel Daemon. Its instance count is currently zero: the team exhausted its monthly Hobby Daemons provisioned-memory quota (420 GB-hours), which prevents an always-running worker from starting. No plan upgrade was purchased.

`REQUEST_WORKER_ENABLED=true` provides bounded request execution using the same durable database queue, leases, fencing, checkpoints, critic and reflection pipeline. Creating/running an assessment performs up to 20 seconds of work before returning. A cancellation releases the lease and preserves saved stages; hard termination requires lease expiry. The authenticated, organization-scoped `POST /api/v1/assessments/{id}/work` endpoint resumes eligible saved work. The frontend offers **Resume saved work** for unfinished jobs. It never reclaims an unexpired active lease or repeats a succeeded job. There is no unattended recovery while daemon capacity is unavailable. Current deployed providers are deterministic; paid LLM calls were not configured.

When daemon capacity becomes available, set its instance count to one, set `REQUEST_WORKER_ENABLED=false`, and redeploy. The standalone worker uses graceful SIGTERM cancellation to release owned work. API replicas retain `WORKER_ENABLED=false`.

## Configuration and redeployment

Production environment variable names: `DATABASE_URL`, optional `DATABASE_URL_UNPOOLED`, `DATABASE_SCHEMA=prism_risk_v1`, `JWT_SECRET`, `DEPLOY_MIGRATIONS=true`, `WORKER_ENABLED=false`, `WORKER_POLL_SECONDS=5`, `REQUEST_WORKER_ENABLED=true`. Keep values in Vercel. The frontend uses its default same-origin `/api/v1`; no public database/provider secrets or external API base are needed.

Run `vercel deploy --prod --yes --scope resum-projects` from the repository root. Local `.vercel` linking metadata and environment files are ignored. Do not download production secrets for routine deployment.

## Verification

Live API/PostgreSQL health, registration, sign-in, synthetic assessment completion, succeeded job persistence, agents/reflections/explanations/audit/sensitivity reads, and stress execution passed. The healthy synthetic assessment returned heuristic score 4.3937. These are functional checks, not predictive accuracy claims. `scripts/verify_live.py <url>` repeats the API workflow using a new synthetic-only verification workspace; credentials and tokens stay in memory. Verification accounts remain isolated in their own organizations.

Local verification: 104 backend cases passed in the full run; the remaining new case had its expectation corrected to accept the documented `completed_with_warnings` outcome and passed on rerun (105 distinct passing cases). Frontend TypeScript and the original 34 frontend cases passed; the expanded integration file then passed all 24 cases, including the new saved-work resume case (35 distinct passing cases). The live browser also created a workspace and displayed the completed synthetic assessment, score 4.4/100 and succeeded job. Evidence screenshot: live-deployment.png. PostgreSQL contention/outage/load testing and a worker restart exercise remain outstanding because daemon capacity is unavailable.

Platform references: [Services](https://vercel.com/docs/services), [Daemons](https://vercel.com/docs/daemons), [Python runtime](https://vercel.com/docs/functions/runtimes/python).

Production deployment: `dpl_FoepbCQD942gax63yh2F2BQNwhEp` (READY).
