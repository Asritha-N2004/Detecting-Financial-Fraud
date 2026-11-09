# Observed verification — 2026-11-09

| Check | Result |
|---|---|
| `python -m alembic upgrade head` | Passed; SQLite schema created |
| `python -m alembic check` | Passed; no new upgrade operations detected |
| Backend pytest | 102 passed; two third-party deprecation warnings |
| TypeScript strict build | Passed |
| Vite production build | Passed; split chart/react/query chunks; largest chunk 406.82 kB |
| Frontend Vitest | 34 passed across 7 files, including 23 Axios/React Query integration cases |
| Playwright real-backend workflows | 2 passed: full lifecycle with immutable weight exploration, plus complete bundle import with synthetic historical correlations and constant-dimension disclosures |
| Specialized LLM contract | All five roles and real SDK over mocked HTTP passed; no live provider call |
| Durable recovery | Concurrent claims, all stage boundaries, API restart and hard process-exit recovery passed on SQLite |
| Portfolio/maturity/stress | Independent covariance/weighted-return references, singular/negative contributions, date/source validation, maturity boundaries, fixed/floating exposure, accounting identities, delayed receipts and intraperiod funding checks passed |
| Overlapping-risk sensitivity | Hand transfer/category calculations, dependency reconstruction, missing dimensions, history filtering/constants/cross-term covariance identities, tamper detection and immutable authorized API exploration passed |
| Browser CI | Separate SQLite/API/Chromium job defined; not run in GitHub Actions in this environment |
| API health | HTTP 200 with database connectivity |
| Vite dashboard | HTTP 200 |
| Desktop/mobile visual inspection | Inspected generated dashboard screenshots at 1280px and 390px; mobile table scrolls horizontally |
| Controlled ablation | 24 cases completed; all three fault-injected reflective cases resolved correctable issues in one cycle |
| Comparison chart | PNG and SVG generated and PNG visually inspected |
| Docker | Not verified: daemon unavailable and Compose plugin unavailable |
| PostgreSQL migration/run | Not executed |
| Live paid model / external market provider | Not executed; credentials and optional adapter validation remain |
| Remote deployment | Not performed |

The test API used disposable SQLite databases. Browser tests registered separate organization accounts using synthetic evidence only. Local preview used backend port 8017 and frontend port 5174 because default ports belonged to other services. Preview processes were stopped after verification; restart with README commands.

Third-party warnings concern AnyIO's pytest API and Starlette's current HTTPX test-client integration. No failing tests were ignored. Frontend installer initially reported blocked build scripts; installed esbuild functionality was subsequently verified by successful production builds. A pnpm allowlist now permits esbuild and Tailwind's native dependency.

Continuation implemented specialized LLM interpretation and durable job recovery. An initial JSX syntax error in the new UI test was corrected; the subsequent seven-test frontend suite and TypeScript build passed. New migration `0002` and model/schema parity were verified locally. Production PostgreSQL and live LLM-provider quality remain unverified.

A migration integration test upgrades a real `0001` database containing running, pending and completed assessments: only interrupted work is adopted, recovered and finalized; pending/completed rows are preserved. The upgraded schema passes Alembic parity checks. Compose YAML parses and includes the separate worker, but this is not a Docker execution test.

Latest continuation adds engine v2 portfolio covariance, maturity analysis and stress projections. The former scalar cash-haircut test was replaced with the new independently calculated cash bridge and a positive-closing-cash/intraperiod-deficit check. New UI tests cover covariance/risk contributions, incomplete profile disclosures, unfunded scores and explicit JSON-bundle import. Synthetic datasets, 24 evaluation cases and comparison figures were regenerated. Price alignment is strict; maturity cash coverage is bounded; hypothetical projected statements are stored only as stress artifacts.

Browser QA also found a stalled preview and an overly specific label locator: the preview was restarted with package-store/generated-file watch exclusions, and the test now uses the scenario combobox's accessible role/name. The final browser test passed the new matrix/maturity views and cash-gap warning. Chart animations are disabled for stable financial plots/captures and a zero-cash reference line is shown; shortfall badges use the danger style. No test failure was ignored.

Latest continuation adds overlapping-risk diagnostics and expanded frontend integration coverage. Initial integration assertion failures concerned callback argument boundaries, rounded display numbers and truncated IDs; callback delivery is now explicitly ID-only and assertions match the UI contract. The 23 integration tests pass after these corrections. Account-switch cache clearing and assessment-scoped stress state are covered. Browser testing scopes navigation locators to distinguish the header and sidebar links. New synthetic engine-backed response fixtures contain no production data or credentials. No software test result is presented as empirical financial accuracy.

Final sensitivity and historical-correlation layouts were visually inspected. The browser confirmed that exploratory POSTs leave the saved score unchanged, reset restores original weights, and 60 imported synthetic observations retain null operational correlations and source warnings. All 102 backend tests, 34 frontend tests and both browser workflows passed. TypeScript, production build, Alembic parity and the 24 controlled evaluation cases also passed. The new GitHub Actions browser job is defined but has not been run remotely.

Results are limited to this environment and suite. They do not establish production scalability, financial predictive accuracy, semantic truth of external documents, or live provider compatibility. Detailed limitations and next commands are in IMPLEMENTATION_STATUS.md.
