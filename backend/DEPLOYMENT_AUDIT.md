# FitAI deployment audit (512 MB / service)

Audit of the repository as it stood at `main` (`d56475c`) before the split-service
work on `feat/deployment`. Everything here was read from the code or measured; the
"measured" numbers are reproduced in [DEPLOYMENT_VERIFICATION.md](DEPLOYMENT_VERIFICATION.md).

## 1. Existing architecture

| Concern | State at `main` |
|---|---|
| Entrypoint | One FastAPI app, `app.main:app`, registering **all** routers (auth, chat, conversations, profile, memory, documents, workouts, progress, activity, location, plan, exercises, stt). |
| Database | SQLAlchemy 2 (sync), `psycopg2`. PostgreSQL in production; SQLite only for tests and local dev (`backend/data.db`). Alembic migrations 0001-0004. Start-up refuses to boot if the DB is behind the migration head. |
| Auth | Supabase JWT (ES256/RS256 via JWKS, optional HS256 secret), verified in-process; user row provisioned from claims. |
| LLM | Groq (`groq` SDK) through LangGraph agent + guardrails. No local LLM. |
| Vectors | **ChromaDB `PersistentClient` on local disk** (`chroma_data/`), three collections: `fitness_knowledge`, `user_documents` (owner-scoped), `user_continuity` (owner-scoped). Cosine space. |
| Embeddings | **Chroma's bundled ONNX all-MiniLM-L6-v2, run in-process** (384-d), model downloaded to a local cache on first use. |
| Documents | `DocumentService` stores the original file (local disk backend, or "unconfigured"), a `documents` row holds status, ingestion runs in a FastAPI `BackgroundTask` receiving the **whole file as bytes**. A start-up sweep marks rows stuck >30 min as `failed`. |
| STT | IBM Granite Speech 5.0 TurboCTC, loaded **locally via torch + transformers** (~900 MB weights), eager background warm-up at start-up. |
| Container | One legacy image (`backend/Dockerfile`, build context = repo root) bundling torch, transformers, chromadb, ONNX, OCR libs (3.4 GB), expecting a persistent disk at `/var/data`. |

## 2. Dependency analysis (what is actually imported)

Determined with `grep` over `app/` plus a clean-virtualenv install of each new
requirements file (`uv pip install -r ... && uv pip check`).

| Package | Used by | Evidence | Core | STT | Docs |
|---|---|---|---|---|---|
| fastapi, uvicorn, pydantic(-settings), structlog, httpx | all | everywhere | yes | yes | yes |
| sqlalchemy, alembic, psycopg2-binary | all (auth provisions a user row; start-up schema check) | `app.api.deps`, `app.db.*` | yes | yes | yes |
| pyjwt[crypto] | token verification (ES256/RS256 needs `cryptography`) | `app.core.security` | yes | yes | yes |
| langgraph, langchain-core, groq | agent / chat | `app.agent`, `app.llm` | yes | no | no |
| ddgs | web-search tool, imported at start-up | `app.tools.web*` | yes | no | no |
| python-multipart | `UploadFile` routes | `app.stt`, `app.api.routers.documents` | no | yes | yes |
| numpy | audio helpers (module-level) | `app.stt.audio_utils`, `speech_service` | no | yes | no |
| pypdf, python-docx | document extraction | `app.rag.loader`, `page_source` | no | no | yes |
| chromadb, onnxruntime, posthog | local vectors + embeddings (dev only now) | `app.rag.vector_store`, `embeddings` | **no** | no | **no** |
| torch, torchaudio, transformers, accelerate, scipy, soundfile, av | local Granite STT (dev only) | `app.stt.speech_service`, `audio_utils` | no | no | no |
| **supabase** (PyPI client) | **never imported** | `grep -rn "supabase import"` -> nothing | no | no | no |
| **pillow, rapidocr-onnxruntime** | **never imported** (image OCR was removed; only a leftover config constant remains) | `grep -rn "rapidocr\|PIL"` | no | no | no |
| python-dotenv | pydantic-settings `.env` reading | `Settings.model_config` | yes | yes | yes |

Consequence: the legacy requirements shipped ~2.5 GB of libraries (torch/CUDA-free CPU
wheels, transformers, ONNX, OCR) to every deployment, two of which (`supabase`,
`pillow`/`rapidocr`) nothing used.

## 3. Router-to-service mapping

| Router (`/api/v1/...`) | Service | Notes |
|---|---|---|
| `auth`, `chat`, `conversations`, `profile`, `memory`, `workouts`, `progress`, `activity`, `location`, `plan`, `exercises`, compat probe | **Core** | Unchanged paths and schemas. |
| `documents` (`POST/GET/PATCH/DELETE`, `/{id}/retry`) | **Documents** | Same paths; the frontend must call the Documents service origin (see guide, section 11). |
| `stt` (`/transcribe`, `/status`) | **STT** | `/status` now requires a token (the web app already sends one). |
| `/health`, `/health/ready` | all three | `/health` is a constant-time liveness probe; `/health/ready` runs `SELECT 1` and reports the database separately. `/health/guardrails` stays Core-only. |

`SERVE_DOCUMENTS_ROUTES` / `SERVE_STT_ROUTES` (default `true`) keep a single-process
local run and the existing test-suite working; the production Core image sets both to
`false`, and Core then does not even import those modules.

## 4. Start-up import analysis (measured)

`python -c "import app.main"` with every heavy module name checked in `sys.modules`:

| | before | after (production Core: documents + STT off) |
|---|---|---|
| chromadb | **loaded** | not loaded |
| onnxruntime | **loaded** | not loaded |
| numpy | **loaded** (via chromadb) | not loaded |
| torch / transformers / av / scipy / soundfile / pypdf / docx | not loaded (already lazy) | not loaded |
| groq, langgraph, langchain_core, ddgs | loaded | loaded (needed) |

`app.stt_main` loads only `numpy` of the watched modules; `app.documents_main` loads none
(`pypdf`/`docx` are imported when a document is parsed). These are asserted by
`tests/unit/deploy/test_service_entrypoints.py` in fresh subprocesses.

## 5. Potential memory bottlenecks

1. **Local ONNX embedder in Core** (chromadb + onnxruntime + model): removed for production by `EMBEDDING_PROVIDER=remote`.
2. **Local Granite STT** (>= 900 MB weights, torch): cannot fit; production STT requires `STT_PROVIDER=remote` and enforces it at start-up.
3. **Whole-document ingestion**: `load_file` extracted every page into memory and the upload bytes were also held by the request closure. Replaced for the Documents service by page-slice extraction (5 pages / batch), a temp file instead of an in-memory copy, and 50-row embed/insert batches.
4. **Audio decode**: decoding a long compressed clip to float32 PCM can reach hundreds of MB (a 10 MB Opus clip is ~40 min). The remote path does not decode; it validates size and magic bytes and forwards the bytes.
5. **Unbounded `File.read()`** in STT: replaced by `read(limit + 1)`.
6. **DB pool**: defaults of 5 + 5 overflow; production values are 2-3 + 1-2 per service.
7. Process-level caches reviewed: guardrails decision cache is capped at 1000 entries; `_WEB_KITS` is per-user and cleared per turn (feature flag off by default); the vector-store handle is a singleton.

## 6. Persistent-storage dependencies (and Render Free reality)

| Data | Where it lived | New home |
|---|---|---|
| Uploaded originals | `UPLOAD_DIR` on local disk | **Supabase Storage** (private bucket) |
| Vectors | `chroma_data/` on local disk | **pgvector** table `vector_chunks` in Supabase PostgreSQL |
| Ingestion state | process memory + `documents.status` | **`document_ingestion_jobs`** table (checkpointed) |
| Granite model cache | `HF_HOME` on disk | not needed (remote STT) |
| Relational data | PostgreSQL | unchanged |

Render Free has **no persistent disk**, so any of the "local disk" rows would be lost on every
restart/spin-down. Nothing production-critical now depends on the container filesystem; only
a transient temp file during ingestion, which is always deleted.

## 7. External API dependencies

| Provider | Used by | Configured by | Verified here? |
|---|---|---|---|
| Groq | Core | `GROQ_API_KEY` | no credential; chat path exercised against a local fake |
| Supabase Auth (JWKS) | all | `SUPABASE_URL` | no credential; HS256 path exercised |
| Supabase PostgreSQL | all | `DATABASE_URL` | **pgvector/Postgres 16 container**, not the real project |
| Supabase Storage REST | Documents | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET` | request shapes unit-tested; **never hit the real API** |
| Embedding provider (384-d MiniLM) | Core, Documents | `EMBEDDING_API_URL/KEY/FORMAT` | **no provider chosen or tested** (see risk R1) |
| STT provider (`/audio/transcriptions`) | STT | `STT_REMOTE_URL/KEY/MODEL` | **no provider chosen or tested** |
| ddgs / Nominatim / Overpass / Open-Meteo | Core tools | feature flags / defaults | untouched |

## 8. Risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | A remote embedder may not produce vectors equivalent to the local ONNX model, silently degrading retrieval of already-indexed data. | Dimension is enforced on every write (`EMBEDDING_DIMENSION`, 384); `scripts/verify_embedding_parity.py` compares local vs remote cosine similarity before cut-over; the migration copies existing vectors verbatim (no re-embedding) and the parity test proves retrieval equivalence for the local model. **If the provider's model differs, re-embed instead of migrating.** |
| R2 | Render Free spins services down after idle; in-flight ingestion stops. | Jobs are durable with leases + checkpoints; the next start resumes. Verified with a SIGKILL test (see verification). First request after spin-down is slow (cold start). |
| R3 | Three always-on free services exceed the monthly instance-hour allowance. | Documented; do not claim continuous free operation. Use a paid plan or deploy only what is needed. |
| R4 | No private networking between free services. | No service calls another. Each talks to Supabase; the browser calls each public URL. Auth is the user's Supabase JWT, verified independently in each service. |
| R5 | A migration run by three containers at boot could race. | Containers never migrate; the schema is applied once, manually, and each container verifies the head at start-up. |
| R6 | Service-role key exposure. | Only the Documents service has it; never in `VITE_*`; request/response bodies of Supabase and providers are never logged. |
| R7 | Pre-existing: the legacy `ingest_user_document_bytes` stamps the temp-file name into chunk `source` metadata. | Not changed (out of scope, covered by tests). The new job path stores the real filename. |
| R8 | The legacy `inline` ingestion path is not restart-safe. | Kept for local dev/tests; production validation requires `INGESTION_MODE=jobs` for the Documents service. |
