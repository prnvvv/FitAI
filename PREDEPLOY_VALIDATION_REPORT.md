# Pre-deployment validation (branch `feat/lightweight`)

Validation only; no optimization or redesign. Environment: Windows 11, Python 3.10,
Node 22. **The Docker daemon was not running, and the image is being built by the
owner, so no image was built here.** No Postgres/pgvector, Supabase, Groq or
embedding endpoint was available; nothing touched production (see "Isolation").

## 1. Docker (static validation only; image NOT built)

| Check | Result |
|---|---|
| Every `COPY` source is in the build context | Verified by `test_web_build_context.py` against the real `git ls-files` |
| Frontend build args declared and consumed | `ARG VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` -> `ENV` in the frontend stage only; no other `ARG` |
| Only public values reach the bundle | Built the frontend as Docker would (no `.env`, only the two args): URL and anon key present, 0 hits for `service_role`/`SERVICE_ROLE`/`gsk_`/`GROQ`; API base is same-origin `/api/v1` |
| Privileged credentials absent from layers | `Dockerfile.web` has no secret names outside comments; runtime image copies only `backend/app`, `migrations`, alembic/pyproject |
| Local `frontend/.env` excluded | Yes. It sets `VITE_API_BASE_URL`, which would have overridden same-origin if it ever entered the context |
| Image size / build warnings | **Not measured (no build)** |

**Finding, fixed:** only `Dockerfile.web.dockerignore` allowed `frontend/`. A builder that
does not honour Dockerfile-specific ignore files would fall back to the root
`.dockerignore`, which excluded `frontend/` and `requirements-web.txt`, so the build
would fail. The root file now also allows them (and excludes `node_modules`/`dist`).
Whether Render honours `Dockerfile.web.dockerignore` is unverified; both files now work.

## 2. Ingestion worker (single-service mode)

Lifecycle: `lifespan` -> `_startup_tasks` -> `start_worker()` (guarded by a module
singleton) -> one daemon thread (`ingestion-worker`) -> `claim_next` (lease +
`FOR UPDATE SKIP LOCKED`) -> `process_job` (5-page checkpointed batches). Shutdown:
`stop_worker()` sets the stop event and joins for 5 s.

Verified (real tests, `tests/unit/deploy/test_worker_lifecycle.py`, plus existing
`test_ingestion_jobs.py`): start is idempotent (one thread); stop joins; restart after
stop; a thread drains a queued job to `indexed`; a failing cycle does not kill the
loop; `stop()` does not hang on an in-flight job; the asyncio loop is not starved by
CPU- and wait-heavy ingestion; a job killed mid-run is reclaimed after lease expiry and
finishes with contiguous chunk ids.

Verified with a **real uvicorn process** (SQLite, local storage, in-memory vector
store, real pypdf + chunker; 200-page PDF, 400 chunks, simulated 0.4 s embedding latency per
batch, 4 concurrent API clients hammering an authenticated endpoint):

- Graceful stop (Windows `CTRL_BREAK`, the SIGTERM analogue) mid-job took **5.1 s**
  (the 5 s join timeout: the worker does not yield between batches). Job left
  `running`, checkpoint at page 95/200, lease set.
- Restarted against the same DB after the lease lapsed: job resumed (attempts 1 -> 2),
  finished `succeeded`, **400/400 unique chunks, contiguous, no duplicates**.
- API latency during slow ingestion: p50 38 ms, p99 113 ms, max 130 ms (565 requests;
  idle-ingestion baseline p50 42 ms, p99 62 ms). The only API errors (13) came after the
  stop signal, as the server shut down.

**Not verifiable here:** `SKIP LOCKED` under two real concurrent workers needs Postgres
(SQLite ignores it); the 16 skipped tests are the `TEST_PGVECTOR_URL` pgvector suite and a
live-guard eval. Behaviour on overlapping deployments is therefore argued from the code,
not observed: a second instance cannot claim a job until its lease (`INGESTION_LEASE_SECONDS`,
default 120 s) lapses, and each checkpoint renews it, so a *live* worker is never robbed. After
a deploy swap, an interrupted PDF may wait up to 120 s before the new instance resumes it.
Chunk ids are deterministic, so a late write by an old process cannot create duplicates.
Each interruption consumes one of `max_attempts` (3).

No code change was needed for the worker.

## 3. Single-service integration (what was actually executed)

Real uvicorn process with the built SPA and the real app: `/health` 200; `/health/ready`
200 with `database: ok`; `/` serves HTML; deep link `/chat/abc` falls back to the app shell
(200); unknown `/api/...` -> 404 (not the shell); missing/garbage token -> 401; valid token
-> 200; PDF upload -> storage -> job -> ingestion -> `indexed`; concurrent API traffic
during ingestion. Existing backend suites (auth, conversations, chat service, memory,
guardrails, transactions, SPA serving) exercise chat creation/persistence/memory with
fakes and ran green.

**Not exercised (blocked, need live services):** Supabase sign-in/session restoration in a
browser; real chat streaming through Groq; real retrieval over pgvector with remote
embeddings; Supabase Storage; Postgres transactions. Retrieval after ingestion was checked
only at the chunk-count level against a stand-in store.

## 4. Resource measurements (process RSS, measured by psutil)

Local process, not the container: Windows/Python 3.10 numbers, no cgroup, in-memory
vector stand-in, no real HTTP embedding client calls. Treat as a floor, not a Render figure.

| Phase | Peak RSS |
|---|---|
| Idle after start-up | 126 MB |
| API load, 4 clients (chat-like traffic without an LLM) | 129 MB |
| PDF ingestion (200 pages, 280 KB) | 137 MB |
| Ingestion + concurrent API load | 139 MB |
| Slow ingestion + API load (second run) | 136 MB |

Real chat generation (Groq streaming, guardrail calls) was **not measured**. Container
memory on Render, including the base image and OS, is **not measured**.

## 5. Fixes made

1. Root `.dockerignore` now supports `Dockerfile.web` (regression test added).
2. `PlanPage.requests.test.tsx` was date-fragile: it clicked calendar cell 10, which is
   *today* on 2026-11-05, so it failed on this date regardless of this branch. It now
   picks a non-today cell. (Pre-existing; unrelated to the lightweight work.)

## 6. Isolation

`backend/.env` holds real credentials and settings auto-loads it. The harness overrode every
outbound-capable setting (Supabase URL/keys, Groq, prompt guard, search/maps keys,
`DATABASE_URL`) with dummies, used a throwaway SQLite database and temp directories, and
made no calls to production. Scripts live outside the repo.

## 7. Remaining steps before Render deployment

1. Build the image yourself; record size and warnings; run it with test credentials.
2. Confirm Render uses `Dockerfile.web.dockerignore` (or rely on the updated root file).
3. Create the Supabase `fitai-documents` bucket; apply the Alembic migration manually.
4. Set the secret env vars and the two public `VITE_*` build values (do not set
   `VITE_API_BASE_URL`; same-origin is the default).
5. Against a **staging** Supabase project: sign in, reload `/chat/<id>`, send and stream a
   message, switch conversations, upload a PDF to `indexed`, ask a question it answers,
   confirm memory is stored and recalled.
6. Observe the Render memory graph for chat, ingestion and both together; if sustained use is
   above ~400 MB, move to a 1 GB plan rather than removing features.
7. Optional, with Postgres: run the pgvector suite (`TEST_PGVECTOR_URL`) and a two-worker
   claim test.
