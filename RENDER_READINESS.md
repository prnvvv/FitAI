# Render Readiness: single web service

Status: **configured and unit-tested; not yet deployed or image-built.**

## Architecture

One Docker web service (`fitai-web`, `render.yaml`): uvicorn (1 worker) serves
`/api/v1/*`, `/health`, `/docs` and the built React app (SPA fallback). The
checkpointed document-ingestion worker runs in the same process. Persistence is
external: Supabase Postgres (data, pgvector, ingestion jobs), Supabase Storage
(PDF originals), Supabase Auth; Groq for LLM; a remote HTTP embedding endpoint.
Nothing relies on Render's ephemeral disk.

## Build

```
docker build -f Dockerfile.web -t fitai-web:latest \
  --build-arg VITE_SUPABASE_URL=https://<project>.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=<public-anon-key> .
```

(Not run here: Docker daemon unavailable.) On Render, set the two `VITE_*`
variables; they are public values compiled into the browser bundle.

## Environment variables (names from `render.yaml` / `app/core/config.py`)

Secret (`sync: false`): `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`GROQ_API_KEY`, `GROQ_EXTRACTION_API_KEY`, `PROMPT_GUARD_API_KEY`, `EMBEDDING_API_URL`,
`EMBEDDING_API_KEY`, `CORS_ORIGINS` (the service's own `https://` URL),
`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.

Fixed in the blueprint: `ENVIRONMENT=production`, `FITAI_SERVICE=core`,
`SERVE_DOCUMENTS_ROUTES=true`, `INGESTION_MODE=jobs`, `DOCUMENT_STORAGE_BACKEND=supabase`,
`SUPABASE_STORAGE_BUCKET`, `VECTOR_STORE_BACKEND=pgvector`, `EMBEDDING_PROVIDER=remote`,
`EMBEDDING_DIMENSION=384`, `DB_POOL_SIZE=3`, `DB_MAX_OVERFLOW=2`, `GUARDRAILS_MODE=enforce`,
`FRONTEND_DIST_DIR`. `$PORT` is supplied by Render; the app binds `0.0.0.0:$PORT`.

Production start-up refuses unsafe configuration (SQLite, wildcard CORS, missing keys).

## Persistent storage

No Render disk. Create the private Supabase bucket `fitai-documents`. Apply the
Alembic migration manually before the first deploy
(`backend/DEPLOYMENT_DATABASE_MIGRATION.md`); the container verifies the schema
and refuses to start otherwise.

## Health check

`healthCheckPath: /health` (liveness, no DB). `/health/ready` also checks the database.

## Memory

| Measurement | Value | Status |
|---|---|---|
| Process after importing app and serving health + SPA | 107 MB RSS | measured |
| After importing pypdf + python-docx | 118 MB RSS | measured |
| Peak during chat generation | – | **not measured** |
| Peak during PDF ingestion (5-page batches) | – | **not measured** |
| Concurrent chat + ingestion | – | **not measured** |
| Docker image size | – | **not measured** (no daemon) |

**512 MB is plausible but unproven.** No local ML model is loaded (remote
embeddings), ingestion is single-job and batched, the pool is small, and idle
memory is ~110 MB. But the free tier also spins down after idle, and the peaks
above were not observed. If measurement on the first deploy shows sustained
usage above ~400 MB, move to the 1 GB tier (Starter-class paid plan with ≥1 GB)
rather than reducing features.

## Deploy and smoke test

1. Apply the migration; create the storage bucket; set env vars.
2. Create the Blueprint from `render.yaml`; trigger a manual deploy (auto-deploy is off).
3. `GET /health` → `{"status":"ok"}`; `GET /health/ready` → 200.
4. Open `/` and `/login`, sign in; reload `/chat/<id>` (SPA fallback must load).
5. Send a chat message; reload and confirm history; switch conversations.
6. Upload a small PDF; watch status reach ready; ask a question it answers.
7. Check Render memory graph during steps 5–6; record the peak.

Rollback: the two-service layout is preserved in `render.split.yaml`.
