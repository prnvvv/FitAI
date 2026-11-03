# FitAI deployment guide (three Render services, 512 MB each)

> Nothing in this repository deploys or migrates anything by itself. Every step marked
> **[manual]** is yours to run. The blueprint (`render.yaml`) has `autoDeployTrigger: "off"`.
> This replaces the single-service flow in `docs/DEPLOYMENT_GUIDE.md` for the split
> deployment; the legacy single image (`backend/Dockerfile`) still works for local use.

## 1. Architecture

```
                         Browser (Vercel)
        ┌───────────────────┼──────────────────────┐
        │ VITE_API_BASE_URL │ VITE_DOCUMENTS_URL   │ VITE_STT_URL
        ▼                   ▼                      ▼
  fitai-core          fitai-documents          fitai-stt
  chat · auth ·       upload · extract ·       audio upload ·
  profile · memory    chunk · embed ·          validate ·
  LangGraph + Groq    ingestion worker         transcribe
        │                   │       │               │
        │                   │       └──► Storage    └──► STT provider (HTTP)
        │                   └──► Embedding provider (HTTP)
        └──► Groq · Embedding provider (HTTP, for queries)
        └─────────────┬──────────────┬─────────────────┘
                      ▼              ▼
              Supabase PostgreSQL (+ pgvector)   Supabase Storage (private bucket)
```

* **No service calls another.** Render Free has no private networking, so each service uses only
  Supabase and the public internet; the browser calls each service's public URL with the user's
  Supabase JWT, which every service verifies independently. No service-to-service secret is needed
  and none is exposed.
* Shared code: one repository, one `app/` package; three tiny entrypoints
  (`app.main`, `app.stt_main`, `app.documents_main`) that build the app with the same factory
  (`app/core/service_app.py`): CORS, error envelope, request-id/duration logging, `/health`.

## 2. Services

| | fitai-core | fitai-stt | fitai-documents |
|---|---|---|---|
| Entrypoint | `app.main:app` | `app.stt_main:app` | `app.documents_main:app` |
| Image | `Dockerfile.core` | `Dockerfile.stt` | `Dockerfile.documents` |
| Dependencies | `requirements-core.txt` | `requirements-stt.txt` | `requirements-documents.txt` |
| Routes | auth, chat, conversations, profile, memory, workouts, progress, activity, location, plan, exercises | `/api/v1/stt/*` | `/api/v1/documents/*` |
| Local models | none | none (`STT_PROVIDER=remote`) | none |
| Background work | none | none | durable ingestion worker (1 thread) |
| Workers | 1 | 1 | 1 |

## 3. Environment variables

`.env.example` documents every variable. Production start-up validation (in
`app/core/config.py`) aborts with an explicit list if a required one is missing:

| Variable | core | stt | documents | Notes |
|---|:-:|:-:|:-:|---|
| `ENVIRONMENT=production`, `FITAI_SERVICE`, `DEBUG=false` | ✔ | ✔ | ✔ | set by `render.yaml` |
| `DATABASE_URL` | ✔ | ✔ | ✔ | Supabase **pooler** URL, `?sslmode=require` |
| `CORS_ORIGINS` | ✔ | ✔ | ✔ | exact `https://` frontend origin(s), never `*` |
| `SUPABASE_URL` | ✔ | ✔ | ✔ | token (JWKS) verification + Storage base |
| `SUPABASE_ANON_KEY` | ✔ | | | |
| `SUPABASE_SERVICE_ROLE_KEY` | | | ✔ | **server-side only**; Storage access |
| `GROQ_API_KEY` (+ `GROQ_EXTRACTION_API_KEY`, `PROMPT_GUARD_API_KEY`) | ✔ | | | |
| `VECTOR_STORE_BACKEND=pgvector` | ✔ | | ✔ | |
| `EMBEDDING_PROVIDER=remote`, `EMBEDDING_API_URL`, `EMBEDDING_API_KEY`, `EMBEDDING_API_FORMAT` | ✔ | | ✔ | 384-dimension MiniLM-class model |
| `SERVE_DOCUMENTS_ROUTES=false`, `SERVE_STT_ROUTES=false` | ✔ | | | |
| `STT_PROVIDER=remote`, `STT_REMOTE_URL`, `STT_REMOTE_API_KEY`, `STT_REMOTE_MODEL` | | ✔ | | OpenAI-compatible `/audio/transcriptions` |
| `INGESTION_MODE=jobs`, `DOCUMENT_STORAGE_BACKEND=supabase`, `SUPABASE_STORAGE_BUCKET` | | | ✔ | |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 3 / 2 | 2 / 1 | 3 / 1 | per-instance; keep the sum well under the Supabase pool limit |

No endpoint is defaulted for embeddings or STT: pick a provider, confirm its URL/format in its
own documentation, and set it. (`EMBEDDING_API_FORMAT=hf` posts `{"inputs":[...]}` and expects
`[[...]]`; `openai` posts `{"input":[...],"model":...}` and expects `{"data":[{"embedding":[...]}]}`.)

## 4. Supabase setup **[manual]**

1. Use your existing project, or create one. Copy: project URL, anon key, **service-role key**,
   and the **pooled** connection string (Settings -> Database -> Connection pooling) plus the
   **direct** connection string (for the one-off migration and `pg_dump`).
2. Authentication: nothing new. Tokens are verified through the project's JWKS.
3. Backups: take one before anything else (see `DEPLOYMENT_DATABASE_MIGRATION.md` section 4.0).

## 5. pgvector setup **[manual]**

Dashboard -> Database -> Extensions -> enable **vector** (or let the migration run
`CREATE EXTENSION IF NOT EXISTS vector`). Then apply the schema once:

```bash
docker run --rm -e DATABASE_URL="$DIRECT_DATABASE_URL" -e ENVIRONMENT=development \
  --entrypoint alembic fitai-core:latest upgrade head
# or: cd backend && DATABASE_URL=... alembic upgrade head
```

It is additive (two new tables); the containers refuse to start against a database behind the
head, and never migrate themselves. Existing Chroma data: `DEPLOYMENT_DATABASE_MIGRATION.md`.

## 6. Storage bucket **[manual]**

Storage -> New bucket -> name `fitai-documents` (or set `SUPABASE_STORAGE_BUCKET`), **Private**
(not public). No policies are needed: the Documents service uses the service-role key, which
bypasses RLS, and users never access the bucket directly.

## 7. Local Docker testing

```bash
cd backend
docker build -f Dockerfile.core      -t fitai-core:latest .
docker build -f Dockerfile.stt       -t fitai-stt:latest .
docker build -f Dockerfile.documents -t fitai-documents:latest .

# Disposable database with pgvector (never your real one)
docker run -d --name fitai-pgvector-test -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=fitai_test -p 54329:5432 pgvector/pgvector:pg16

# Full automated smoke: migration via the image, 512 MB limits, restart recovery, memory
python scripts/deploy_smoke/run_smoke.py        # refuses databases not ending in _test
```

Run one service by hand (example: Core; add `-e` flags from section 3):

```bash
docker run --rm -p 8000:8000 --memory 512m --env-file .env.production-local fitai-core:latest
curl localhost:8000/health        # {"status":"ok"}
curl localhost:8000/health/ready  # database reported separately
```

## 8. GitHub -> Render **[manual]**

1. Render dashboard -> **New** -> **Blueprint** -> connect the GitHub repo (branch `main`).
2. Render reads `render.yaml` and proposes three services. For every `sync: false` variable it asks
   for a value: paste them from section 3. Leave the others as proposed.
3. Create the services. Because `autoDeployTrigger` is `"off"`, Render builds on first creation but
   will not redeploy on later pushes: use **Manual Deploy**, or change it to `commit` once you trust
   the pipeline.
4. Build context is `backend/`; Dockerfile paths are `./backend/Dockerfile.{core,stt,documents}`.

## 9. Health checks

All three services expose `GET /health` (constant-time liveness: no DB, no model, no LLM) and
`GET /health/ready` (one `SELECT 1`, reports `{"checks":{"database":"ok|unavailable"}}` separately and
returns 503 when the database is down). Render's `healthCheckPath` is `/health`; use `/health/ready`
for your own uptime monitor. Each request is logged as `request_completed` with `service`,
`request_id`, `endpoint`, `status`, `duration_ms` (the `/health` probe is not logged). Query strings,
headers, bodies, tokens and document contents are never logged.

## 10. Migration order for the first real deploy **[manual]**

1. Backups (section 4.0 of the migration doc).
2. Enable `vector`, create the bucket (sections 5-6).
3. `alembic upgrade head` (section 5).
4. Optional: `verify_embedding_parity.py`, then `migrate_chroma_to_pgvector.py` (dry-run, apply, verify).
5. Create the Render services (section 8), deploy Documents and STT, then Core.
6. Point the frontend at them (section 11) and redeploy it.

## 11. Frontend endpoint configuration

| Variable (Vercel build env) | Value | Effect |
|---|---|---|
| `VITE_API_BASE_URL` | `https://fitai-core.onrender.com/api/v1` | all Core calls (unchanged variable) |
| `VITE_DOCUMENTS_URL` | `https://fitai-documents.onrender.com/api/v1` | document list/upload/retry/rename/delete **(new, optional)** |
| `VITE_STT_URL` | `https://fitai-stt.onrender.com/api/v1/stt` | dictation (already existed) |

Paths and payloads are unchanged; only the origin differs. If `VITE_DOCUMENTS_URL` is unset or
empty, the document calls go to `VITE_API_BASE_URL`, so a single-process deployment is untouched.
Add the **frontend** origin to each service's `CORS_ORIGINS` (the backend services do not need each
other's origins). Never put the service-role key in any `VITE_*` variable.

## 12. Deploy and roll back

* Deploy order: Documents, STT, Core. Each deploy is independent.
* Roll back a service from Render -> Deploys -> previous deploy -> **Rollback**.
* Schema rollback (rarely needed): `alembic downgrade -1` removes only the two new tables.
* Roll back the vector backend: `VECTOR_STORE_BACKEND=chroma`, `EMBEDDING_PROVIDER=local` on the
  legacy image; Chroma was never modified by anything here.

## 13. Free-tier limitations (read this)

* **Instance hours**: a Render *workspace* gets a monthly free instance-hour allowance. One
  always-on service roughly uses it up; **three always-on free services will exceed it** and be
  suspended until the next month. Do not assume three free services run continuously. Options:
  run only Core on Free, or put the services you need on a paid plan.
* **Spin-down**: free services sleep after ~15 minutes idle and cold-start on the next request
  (tens of seconds), then each re-verifies the schema and (Documents) resumes ingestion.
* **No persistent disk**: nothing relies on the container filesystem (files live in Supabase Storage,
  vectors and jobs in PostgreSQL).
* **512 MB RAM**: measured headroom is in `DEPLOYMENT_VERIFICATION.md`.
* **Ingestion while asleep**: a job only progresses while its service is awake. An upload wakes the
  service; if it then idles and sleeps mid-job, the job resumes at the next wake-up (the lease
  expires after `INGESTION_LEASE_SECONDS`, default 120). Large documents on Free may need a keep-alive
  ping or a paid plan to finish promptly.
* Private networking between services is not available on Free and is not used.

## 14. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Container exits: `Invalid production configuration: ...` | A required variable is missing; the message lists each one. |
| `database schema ... behind` at start-up | Run section 5's `alembic upgrade head` once. |
| `/health/ready` 503 | Database unreachable: check `DATABASE_URL`, `?sslmode=require`, pooler vs direct. |
| Upload returns 503 "Document storage is not configured" | `DOCUMENT_STORAGE_BACKEND=supabase` needs `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, an existing private bucket. |
| Document stays `processing` | Check the Documents logs for `ingestion_batch_failed`; transient errors retry (up to `INGESTION_MAX_ATTEMPTS`) then fail with a readable reason; use **Retry** in the UI. |
| `EMBEDDING_API_URL and EMBEDDING_API_KEY are required` | Remote embeddings are mandatory with pgvector. |
| `embedding provider returned a vector that is not 384-dimensional` | The provider model differs; use a 384-d MiniLM-class model or run a full re-embed and migration. |
| STT returns 503 `Speech-to-text is not configured` | Set `STT_REMOTE_URL`, `STT_REMOTE_API_KEY`, `STT_REMOTE_MODEL`. |
| Browser CORS error | Add the exact frontend origin (https, no trailing slash) to that service's `CORS_ORIGINS`. |
| OOM-killed on Render | Check `INGESTION_PAGES_PER_BATCH`, `DB_POOL_SIZE`; see verification doc for baseline numbers. |
