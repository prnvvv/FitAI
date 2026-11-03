# Lightweight Optimization Report

Branch: `feat/lightweight`. Every number below was measured on this machine
(Windows, Python 3.10.10, Node 24) unless marked **estimate**.

## 1. Original architecture

- Backend: FastAPI (`app.main`), SQLAlchemy 2 + Alembic on Supabase Postgres,
  LangGraph + Groq agent, Supabase Auth (JWT/JWKS), Supabase Storage for uploads,
  pgvector for vectors, remote HTTP embeddings, a durable checkpointed ingestion
  job queue (`INGESTION_MODE=jobs`).
- Frontend: React 19 + Vite, one JS bundle, API base `/api/v1` (same-origin by default).
- Deployment: **two** Render services (`fitai-core`, `fitai-documents`) and a
  frontend hosted separately (Vercel config). Production already avoided
  chromadb/onnxruntime/torch via `requirements-core.txt` / `requirements-documents.txt`.

The backend had therefore already been made lean before this task. Heavy libraries
(pypdf, python-docx, chromadb) are imported lazily; this is enforced by
`tests/unit/deploy/test_service_entrypoints.py`.

## 2. Baseline (before any change)

| Check | Result |
|---|---|
| Backend tests | 689 passed, 16 skipped (live-Postgres/pgvector integration tests) |
| Frontend type-check | clean |
| Frontend lint (oxlint) | 0 errors, warnings only (pre-existing, `PlanPage.tsx`) |
| Frontend tests | 316 passed (29 files) |
| Frontend build | OK; single JS chunk **809.2 kB** (233.5 kB gzip), CSS 121.7 kB |
| `import app.main` RSS (dev venv) | 17 MB → 111 MB |

## 3. Issues identified

1. The requested target (one Render Web Service serving frontend + API) did not exist:
   Core did not serve the SPA, and in `INGESTION_MODE=jobs` only the Documents
   service started the ingestion worker, so folding documents into Core would have
   left uploads queued forever.
2. Every page shipped in one 809 kB bundle.
3. Two services meant two idle processes (two Python runtimes plus duplicated libraries).

## 4. Changes implemented

| Commit | Change | Why behavior is preserved |
|---|---|---|
| `d967aa2` | `app/core/spa.py`: optional SPA serving (`FRONTEND_DIST_DIR`); `app/services/ingestion_runtime.py`: worker start/stop shared by Core and Documents | Off unless `FRONTEND_DIST_DIR` is set and has an `index.html`. Registered last, so API/health/docs routes win; `/api/*` unknown paths still 404 as JSON; traversal-contained. Documents service uses the same code it had before, moved. |
| `d18cf4a` | `React.lazy` for Library, Memory, Plan, Profile, Progress pages | Same routes and components; a spinner shows only while a chunk loads. All 316 frontend tests pass unchanged. |
| `1be818f` | `Dockerfile.web` (3-stage: node build, pip venv, slim runtime), `requirements-web.txt` (union of core + documents), allow-list `Dockerfile.web.dockerignore` | Existing Dockerfiles untouched. No ML libraries. Non-root, one worker, binds `0.0.0.0:$PORT`. |
| `ae4f9b2` | `render.yaml` → one service; previous blueprint kept as `render.split.yaml` | Split topology still tested (`test_deploy_files.py` now reads `render.split.yaml`; assertions unchanged). |

No database schema, migration, retrieval, chunking, prompt, auth or guardrail code was modified.

## 5. Files modified / added

Backend: `app/main.py`, `app/documents_main.py`, `app/core/config.py` (+`frontend_dist_dir`),
new `app/core/spa.py`, `app/services/ingestion_runtime.py`, `requirements-web.txt`.
Tests: `tests/unit/deploy/test_spa_serving.py`, `test_single_service_worker.py`,
`test_single_service_files.py`; `test_deploy_files.py` (blueprint path only).
Frontend: `src/App.tsx`. Root: `Dockerfile.web`, `Dockerfile.web.dockerignore`,
`render.yaml`, `render.split.yaml`, three reports.

## 6. Before / after

| Metric | Before | After |
|---|---|---|
| Backend tests | 689 / 16 skipped | 715 passed / 16 skipped |
| Initial JS (entry + shared `api` chunk) | 809.2 kB (233.5 kB gz) | 478.3 + 234.4 = 712.7 kB (≈209.5 kB gz) |
| Entry chunk alone | 809.2 kB | 478.3 kB (147.5 kB gz) |
| Deferred page chunks | 0 | 5 (Plan 41.7, Progress 34.8, Profile 9.2, Library 7.5, Memory 5.2 kB) |
| Render services | 2 (+ separate frontend host) | 1 |
| `import app.main` + serve health/SPA (clean venv from `requirements-web.txt`) | n/a | 107 MB RSS |
| …after importing pypdf + python-docx | n/a | 118 MB RSS |
| Heavy modules loaded (chromadb, onnxruntime, numpy, torch, cv2) | none | none |
| Clean-venv site-packages for `requirements-web.txt` | n/a | 143 MB; `pip check` clean |

The gain in initial JS is modest (≈10% gzip); the large `api` chunk is the Supabase
client, which the app needs on first paint, so it was not split.

## 7. Functional equivalence

See `FUNCTIONALITY_REGRESSION_REPORT.md`.

## 8. Tests executed

- `python -m pytest -q` (backend): 715 passed, 16 skipped.
- `ruff check app tests`: clean.
- `npm run type-check`, `npm run lint` (0 errors), `npm test` (316 passed), `npm run build`.

## 9. Remaining limitations (not done, or not verifiable here)

- **Docker image not built.** The Docker daemon was not running on this machine, so
  image size and the multi-stage build are **unverified**. The Python half was
  verified by installing `requirements-web.txt` into a clean venv; the Node half by
  the identical `npm run build` run locally.
- **Memory during chat, PDF ingestion and concurrent load was not measured.** Those
  paths need live Groq, Supabase, and an embedding endpoint, which were not used
  (the local `.env` points at real services and was deliberately not exercised).
- Not investigated in depth: SQL query shapes / N+1 / missing indexes, LangGraph
  prompt duplication, Supabase Storage transfer patterns. No change was made where
  equivalence could not be established.
- Unused-dependency removal was not attempted; root `requirements.txt` still lists
  chromadb/onnxruntime/OCR for local development (production images do not install it).
  Removing them needs a repo-wide usage audit.
- `Dockerfile.web` has not been exercised against a real migrated database.

## 10. Render recommendations

See `RENDER_READINESS.md`. Short version: 512 MB is **not proven** sufficient.
Idle is ~110 MB, which leaves headroom, but the peak during PDF ingestion and
concurrent chat is unmeasured. Measure on the real deployment before relying on it.
