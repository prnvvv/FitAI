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
`EMBEDDING_DIMENSION=1024`, `DB_POOL_SIZE=3`, `DB_MAX_OVERFLOW=2`, `GUARDRAILS_MODE=enforce`,
`FRONTEND_DIST_DIR`. `$PORT` is supplied by Render; the app binds `0.0.0.0:$PORT`.

Production start-up refuses unsafe configuration (SQLite, wildcard CORS, missing keys).

## Embedding model

Qwen3-Embedding-0.6B (1024-d) through the Hugging Face router (provider DeepInfra), OpenAI
format: `EMBEDDING_API_URL=https://router.huggingface.co/deepinfra/v1/openai/embeddings`,
`EMBEDDING_API_FORMAT=openai`, `EMBEDDING_REMOTE_MODEL=Qwen/Qwen3-Embedding-0.6B`,
`EMBEDDING_API_KEY` = a Hugging Face token. The request shape was derived from the
`huggingface_hub` DeepInfra client; a live call was **not verified** (the HF account returned
402: Inference Providers credit is required).

**Schema:** the pgvector column was `vector(384)` (migration 0005). Migration **0006**
resizes it to `vector(1024)` and rebuilds the HNSW index. It refuses to run (changing nothing)
if `vector_chunks` already holds rows, because vectors of different models are not comparable;
empty that derived table deliberately and re-ingest in that case. Apply 0006 with the rest of
the migrations before the first deploy.

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
