# Deployment verification report

> **Update:** the IBM Granite speech-to-text service (`fitai-stt`) described below has since been
> removed. Dictation is now browser-native (Web Speech API); see `frontend/SPEECH_TO_TEXT.md`. The
> measurements and tables in this report are historical and were not re-run for the two-service layout.

Everything below was executed on 2026-11-03 on a Windows 11 workstation (Python 3.10.10,
Docker Desktop 29.8.1 running **Linux containers**, the same OS family as Render). Numbers are copied
from real runs; nothing is estimated. Where something could not be verified it says so.

Commands are repo-relative. `TEST_PGVECTOR_URL` points at a disposable
`pgvector/pgvector:pg16` container (`localhost:54329/fitai_test`).

## 1. Tests

| Check | Command | Result |
|---|---|---|
| Baseline (before any change, `main`) | `pytest` | 613 passed, 1 skipped |
| Backend suite (this branch, CI configuration) | `cd backend && python -m pytest` | **716 passed, 16 skipped, 0 failed** |
| Same incl. the opt-in Postgres/pgvector tests | `TEST_PGVECTOR_URL=... pytest tests/unit/deploy` | **118 passed, 0 skipped** |
| Ruff lint (CI-pinned 0.7.4) | `uvx --from "ruff>=0.7.0,<0.8" ruff check app tests scripts` | all checks passed |
| Ruff format (CI-pinned 0.7.4) | `... ruff format --check app tests scripts` | 254 files already formatted |
| mypy (config in `pyproject.toml`; **not** a CI step) | `python -m mypy app` | 39 errors vs **38 on `main`**; the +1 is `service_name`'s `AliasChoices` ("Required dynamic aliases disallowed"), the same pattern the settings already use 8 times |
| Frontend lint | `npm run lint` | exit 0 (3 pre-existing `PlanPage.tsx` warnings) |
| Frontend type-check | `npm run type-check` | pass |
| Frontend unit tests | `npm test` | 269 passed |
| Frontend build | `npm run build` | built |

The 16 skips are 15 opt-in Postgres tests (9 pgvector + 6 Chroma parity) and the 1 skip that already
existed on `main`.

New test modules (`backend/tests/unit/deploy/`): service entrypoints and import isolation
(fresh subprocesses), per-service production config, remote embeddings + pgvector filter translation,
Supabase Storage + remote STT (HTTP mocked), durable ingestion jobs, deploy-file guards
(`render.yaml`, Dockerfiles, requirements, `.dockerignore`), pgvector integration, Chroma-to-pgvector parity.

## 2. The five claims you asked to be proven

### 2.1 Core starts without importing STT/document dependencies - **proven**

* `tests/unit/deploy/test_service_entrypoints.py` imports `app.main` in a fresh interpreter and asserts none of
  `torch torchaudio transformers chromadb onnxruntime av scipy soundfile pypdf docx rapidocr_onnxruntime cv2 accelerate`
  is in `sys.modules`; `app.stt*`, `app.rag.page_source`, `app.api.routers.documents` and `app.services.ingestion_jobs`
  are absent in the production configuration. This holds even for the single-process development default
  (Chroma is now imported lazily). Before: `chromadb`, `onnxruntime` and `numpy` loaded at start-up.
* STT imports only `numpy` of that list; Documents imports none; neither imports the chat agent.
* In a clean virtualenv with **only** `requirements-core.txt` (no torch, chromadb, pypdf, numpy...), `app.main`
  imports and `/health` answers 200.

### 2.2 All three services install and start independently - **proven**

| | clean venv, `uv pip install -r requirements-X.txt` | `uv pip check` | app import + `/health` in that venv | Docker build | container starts |
|---|---|---|---|---|---|
| core | 62 packages | compatible | 200 | ok (466 MB image) | healthy |
| stt | 38 packages | compatible | 200 | ok (460 MB image) | healthy |
| documents | 40 packages | compatible | 200 | ok (394 MB image) | healthy |

(Image size is disk, not RAM; the legacy image is 3.4 GB.) `pip check` also runs inside each Docker build.

### 2.3 Chroma-to-pgvector preserves dimension and retrieval - **proven for the local embedding model**

`tests/unit/deploy/test_chroma_pgvector_parity.py` (real ONNX all-MiniLM-L6-v2, real Postgres 16 + pgvector,
real Alembic chain): the migration script copies all collections, `--verify` reports equal counts, a second
`--apply` is a no-op, stored dimension is 384, and for four queries the ranked ids are identical and
distances agree to 1e-4; owner scoping and `where` filters match. `test_pgvector_integration.py` additionally
checks upsert idempotency, owner isolation, document-scoped deletes, JSONB filters, chunk ordering, and
migration upgrade -> downgrade -> upgrade with the pre-existing `documents` table intact.

**Not proven:** that your chosen *remote* embedding provider returns vectors equivalent to the local model.
No provider is chosen and no credential exists here. Run `scripts/verify_embedding_parity.py` first
(see `DEPLOYMENT_DATABASE_MIGRATION.md` 4.2).

### 2.4 PDF processing recovers after a restart - **proven (container level)**

`scripts/deploy_smoke/run_smoke.py` (512 MB container, fake providers, real Postgres):

1. Upload a 600-page, 1.2 MB PDF -> `201 pending`; the job checkpoints every 5 pages.
2. `docker kill` (SIGKILL) at ~page 30 of 600: job row `running`, `next_unit=30`, 60 chunks already durable.
3. `docker start` the same image (fresh process): after the 15 s lease expires the job is reclaimed,
   resumes from the checkpoint, and the document becomes `indexed` (`attempts=2`).
4. Result: **1200 chunks, chunk indices 0..1199 contiguous and unique, nothing lost or duplicated**;
   one job row; a repeat upload of the same bytes returns `200` with no new job.

Unit tests (`test_ingestion_jobs.py`) cover the same with finer control: transient failures keep the checkpoint,
a `BaseException` mid-run (kill simulation) is recovered after lease expiry, attempts are bounded then the
document fails with a readable reason, sliced ingestion equals whole-document ingestion chunk-for-chunk,
duplicate/orphan handling, delete-during-ingestion cleans vectors, temp files are always removed.

### 2.5 Peak memory within 512 MB - **measured, comfortable margin**

Containers ran with `--memory 512m --memory-swap 512m` (hard cgroup limit; none was OOM-killed). RSS is PID 1's
`VmRSS`/`VmHWM` from `/proc`; "cgroup peak" is the container's own `memory.peak` (includes page cache).

| Service | Start-up RSS | Peak RSS | cgroup peak | Workload |
|---|---|---|---|---|
| core | 120.5 MB | **157.3 MB** | 129.0 MB | 8 authenticated chat turns through LangGraph + guardrails + pgvector retrieval + continuity indexing (15 LLM calls, 39 embedding calls) |
| stt | 109.1 MB | **151.6 MB** | 135.0 MB | 3 uploads of ~9.7 MB audio (10 MB limit) + one 413 rejection |
| documents | 95.7 MB | **114.4 MB** | 99.0 MB | ingest a 600-page PDF (1200 chunks, 160 embedding batches), killed and resumed |

Peak is 22-31 % of the limit. **Caveats:** the providers were local fakes (real Groq/embedding responses are
similar JSON but I did not measure them); the PDF was text-only and 1.2 MB, not an image-heavy 10 MB scan
(pypdf's per-document cache grows with the pages touched, so a very large PDF will use more; uploads are capped
at `MAX_UPLOAD_SIZE_MB=10` and 2000 chunks, but I have no measurement near that ceiling); measurements are Linux
container RSS, not Render's own accounting.

## 3. Other verified behaviour

* Migration applied **through the Core image** (`alembic upgrade head`): head `0005_ingestion_jobs_pgvector`.
* Core in production configuration answers `404` for `/documents` and `/stt`; peer services register only their
  own routes. Every protected route returns `401` without a token (tested for all three apps).
* `/health` is 200 and constant-time; `/health/ready` returns 503 with `checks.database = unavailable` when the
  database is down while `/health` stays 200.
* Production start-up validation is per service (`test_service_config.py`): STT must be remote, Documents needs
  `jobs` + pgvector + durable storage, pgvector requires remote embeddings, wildcard CORS is rejected everywhere.
* `render.yaml`: parsed and checked statically (every env key is a real `Settings` field, secrets are `sync: false`,
  Docker, one worker, `/health`, `autoDeployTrigger: off`, production validation passes with the declared values).
* No secrets in the diff; `.dockerignore` is an allow-list; images contain no `.env`, database, Chroma data or uploads.

## 4. Not verified / missing credentials

| Item | Why | What to do |
|---|---|---|
| Real Supabase project (JWKS auth, pooler DB, Storage REST) | no credentials | follow `DEPLOYMENT_GUIDE.md` sections 4-6; Storage request shapes are unit-tested against the documented REST paths, never against the live API |
| Embedding provider (URL, format, 384-d parity) | none selected | pick one, set `EMBEDDING_API_*`, run `verify_embedding_parity.py` |
| STT provider | none selected | set `STT_REMOTE_*`; contract is the OpenAI-compatible `/audio/transcriptions` shape |
| Groq | no key | set `GROQ_API_KEY`; the agent path was only exercised against a fake |
| `render.yaml` against Render's own validator | not run (no Render access) | create the Blueprint and read Render's diagnostics |
| Render memory accounting / cold-start timings | no Render account | observe on first deploy |
| Image-heavy or near-10 MB PDFs, real long audio | not measured | try a representative file after deploy and watch Render's memory graph |
| Frontend end-to-end against split origins | not run | after deploy, upload a document and dictate once |

## 5. Known limitations

* Render Free: three always-on services exceed the monthly instance-hour allowance; services spin down and cold-start;
  ingestion only progresses while its service is awake (it resumes on the next wake). See guide section 13.
* The legacy `inline` ingestion path is kept for local development and is not restart-safe; production validation
  forces `INGESTION_MODE=jobs` for the Documents service.
* A deleted document's vectors are removed on delete; the Chroma directory is never touched by anything here.
* `/api/v1/stt/status` now requires a bearer token (the web client already sent one).

## 6. Remaining deployment steps (yours)

See `DEPLOYMENT_GUIDE.md`, "Migration order for the first real deploy" (backups, enable `vector`, create the private bucket,
`alembic upgrade head`, optional parity check and Chroma copy, create the Blueprint, set secrets, set the three `VITE_*`
URLs, deploy Documents/STT then Core).
