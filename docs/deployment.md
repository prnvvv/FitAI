# Deployment

FitAI ships as **one Docker web service** that serves the React app and the FastAPI backend from the
same origin. Persistence is entirely external, so the container filesystem is scratch space only:

```text
Browser ──► Render web service (Dockerfile.web: FastAPI + built frontend + in-process ingestion worker)
              ├─► Supabase  PostgreSQL (+ pgvector, ingestion jobs), Auth (JWKS), private Storage bucket
              ├─► Groq      chat, structured extraction, optional prompt-injection guard
              └─► Remote embeddings endpoint (and optional Hugging Face reranking)
```

> Nothing in this repository deploys or migrates anything by itself. Steps marked **[manual]** are
> yours to run. `render.yaml` sets `autoDeployTrigger: "off"`.

## 1. Prerequisites **[manual]**

| Item | Notes |
|---|---|
| Supabase project | Copy the project URL, the public **anon** key, the **service-role** key (server-side only) and the **pooled** connection string (append `?sslmode=require`). Keep a direct connection string for the one-off migration. |
| `vector` extension | Dashboard → Database → Extensions → enable **vector** (or let the migration create it). |
| Storage bucket | Create a **private** bucket named `fitai-documents` (or set `SUPABASE_STORAGE_BUCKET`). No policies are needed: the backend uses the service-role key and users never touch the bucket directly. |
| Groq API key | [console.groq.com](https://console.groq.com). |
| Embeddings key | See [Embeddings](#embeddings). |
| Backups | Take a database backup before migrating an existing project. |

## 2. Apply migrations **[manual, once, before the first deploy]**

The container **verifies the schema at start-up and refuses to boot against a database that is behind
the latest migration**; it never migrates by itself.

```bash
cd backend
DATABASE_URL="<direct connection string>" alembic upgrade head
```

Migrations are additive. `0006` resizes the pgvector column to `vector(1024)` and rebuilds the index; it
refuses to run (changing nothing) if `vector_chunks` already holds rows, because vectors from different
models are not comparable. Empty that derived table deliberately and re-ingest in that case.
Moving an existing ChromaDB store is covered in
[`chroma-to-pgvector-migration.md`](chroma-to-pgvector-migration.md).

## 3. Build the image

From the repository root:

```bash
docker build -f Dockerfile.web -t fitai-web:latest \
  --build-arg VITE_SUPABASE_URL=https://<project>.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=<public-anon-key> .
```

The two `VITE_*` values are **public** and compiled into the browser bundle. Never pass the service-role
key or any other secret as a build argument.

Run it locally (production safety checks apply because the image sets `ENVIRONMENT=production`):

```bash
docker run -d --name fitai-web -p 8000:8000 --env-file backend/.env fitai-web:latest
curl http://localhost:8000/health            # {"status":"ok"}
curl http://localhost:8000/health/ready      # also checks the database
docker logs -f fitai-web
docker stop fitai-web && docker rm fitai-web
```

## 4. Deploy on Render **[manual]**

1. Render → **New → Blueprint** → connect the repository (branch `main`). Render reads
   [`render.yaml`](../render.yaml).
2. Fill in every variable marked `sync: false`:

| Variable | Secret? | Value |
|---|:-:|---|
| `DATABASE_URL` | yes | Supabase pooled URL, `postgresql+psycopg2://…?sslmode=require` |
| `CORS_ORIGINS` | no | The service's own `https://` origin (explicit, never `*`) |
| `SUPABASE_URL` | no | Project URL (also feeds the CSP and token verification) |
| `SUPABASE_SERVICE_ROLE_KEY` | **yes** | Server-side only; Storage access |
| `GROQ_API_KEY`, `GROQ_EXTRACTION_API_KEY`, `PROMPT_GUARD_API_KEY` | **yes** | Groq keys (extraction and guard keys are optional) |
| `EMBEDDING_API_KEY` | **yes** | Embeddings provider token |
| `HF_TOKEN` | **yes** | Only if reranking is enabled |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | no (public) | Build-time values for the browser bundle |

3. Everything else is fixed in the Blueprint (`ENVIRONMENT=production`, `FITAI_SERVICE=core`,
   `SERVE_DOCUMENTS_ROUTES=true`, `INGESTION_MODE=jobs`, `DOCUMENT_STORAGE_BACKEND=supabase`,
   `VECTOR_STORE_BACKEND=pgvector`, `EMBEDDING_PROVIDER=remote`, `EMBEDDING_DIMENSION=1024`,
   `DB_POOL_SIZE=3`, `DB_MAX_OVERFLOW=2`, `GUARDRAILS_MODE=enforce`, `TRUST_PROXY_HEADERS=true`,
   `RATE_LIMIT_ENABLED=true`). Production start-up refuses unsafe configuration (SQLite, wildcard CORS,
   missing keys, debug on) and lists every problem.
4. Health check path: `/health` (liveness, no database). Trigger the first deploy manually.

**Smoke test:** `GET /health` → ok; `GET /health/ready` → 200; sign in; reload `/chat/<id>` (SPA fallback);
send a message and confirm history persists; upload a small PDF and wait for it to become *Ready*, then ask
a question it answers.

**Rollback:** Render → Deploys → previous deploy → Rollback. The release is backward compatible with the
schema; no migration downgrade is normally needed.

## Embeddings

Production uses `Qwen/Qwen3-Embedding-0.6B` (1024 dimensions) through the Hugging Face router
(`EMBEDDING_API_FORMAT=openai`, `EMBEDDING_API_URL=https://router.huggingface.co/deepinfra/v1/openai/embeddings`),
authenticated with a Hugging Face token in `EMBEDDING_API_KEY`. The dimension must match the database column.
An Inference Providers credit is required; request shape is unit-tested but a live call is not part of CI.

For local development the defaults are ChromaDB and a local `all-MiniLM-L6-v2` model (384 dimensions).

## Optional reranking

`HF_RERANKING_ENABLED=true` reorders retrieved candidates with Hugging Face sentence similarity
(`HF_RERANKING_MODEL`, default `sentence-transformers/all-MiniLM-L6-v2`). It never creates or stores
embeddings, and any failure falls back to vector order and pauses reranking for `HF_RERANKING_COOLDOWN_S`.
It is **off by default**; leave it off until a smoke test with a valid `HF_TOKEN` succeeds.

## Optional: Vercel frontend + Render backend

[`frontend/vercel.json`](../frontend/vercel.json) provides the SPA rewrite, caching and security headers.
Set `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` and `VITE_API_BASE_URL` (backend URL + `/api/v1`) in
Vercel, add the Vercel origin to the backend's `CORS_ORIGINS`, and, if the API is not on `*.onrender.com`,
add its origin to `connect-src` in `vercel.json`.

[`render.split.yaml`](../render.split.yaml) preserves a two-service layout (Core API and a separate
Documents service, built from `backend/Dockerfile.core` and `backend/Dockerfile.documents`). In that layout
set `VITE_DOCUMENTS_URL` to the Documents service; document calls fall back to `VITE_API_BASE_URL` when it
is unset. Services do not call each other; each verifies the user's Supabase token independently.

## Limits and operations

- **Single instance.** One Uvicorn worker. Rate-limit counters and the ingestion worker are per-process;
  do not scale horizontally without a shared limiter store.
- **No persistent disk.** Originals live in Supabase Storage, vectors and ingestion jobs in PostgreSQL.
- **Free tier.** Instances spin down after ~15 minutes idle and cold-start (tens of seconds), re-verifying
  the schema. An ingestion job only progresses while the instance is awake; it resumes at the next wake-up
  (lease `INGESTION_LEASE_SECONDS`, default 120).
- **Memory.** An idle process is roughly 110 MB RSS (measured); peaks during chat generation and PDF
  ingestion were **not measured**. If the first deploy shows sustained use above ~400 MB, move to a 1 GB plan
  rather than removing features.
- **Logging.** One `request_completed` line per request (path only, no query string, headers, bodies, tokens
  or document content).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Exits with `Invalid production configuration: …` | A required variable is missing or unsafe; the message lists each. |
| `database schema … behind` at start-up | Run `alembic upgrade head` once (section 2). |
| `/health/ready` returns 503 | Database unreachable: check `DATABASE_URL`, `?sslmode=require`, pooled vs direct. |
| Upload returns 503 "Document storage is not configured" | `DOCUMENT_STORAGE_BACKEND=supabase` needs `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and an existing private bucket. |
| Document stays *processing* | Look for `ingestion_batch_failed` in the logs; transient errors retry up to `INGESTION_MAX_ATTEMPTS`, then fail with a readable reason; use **Retry** in the UI. |
| `EMBEDDING_API_URL and EMBEDDING_API_KEY are required` | Remote embeddings are mandatory with pgvector. |
| Vector dimension error | The provider model's dimension must equal `EMBEDDING_DIMENSION` (1024 in production). |
| Browser CORS error | Add the exact frontend origin (https, no trailing slash) to `CORS_ORIGINS`. |
| Microphone disabled | Dictation uses the browser's Web Speech API: Chrome or Edge over HTTPS. See [`frontend/SPEECH_TO_TEXT.md`](../frontend/SPEECH_TO_TEXT.md). |
| Hits `429` during testing | Rate limits (`RATE_LIMIT_*`); raise them by environment variable if legitimate. |
| Container killed (OOM) | Reduce `INGESTION_PAGES_PER_BATCH` / `DB_POOL_SIZE`, or use a larger plan. |

See [`SECURITY_AUDIT.md`](SECURITY_AUDIT.md) for the required Supabase, Render and Vercel security settings.
