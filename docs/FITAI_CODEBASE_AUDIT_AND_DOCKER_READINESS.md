# FitAI — Codebase Audit and Docker Readiness

Date: 2026-11-02 · Branch: `feat/in-app-dialogs` · Scope: read-only audit (no fixes applied except Phase 1 dialogs).

Evidence legend: **Verified** = I executed it or read the code path end to end. **Needs Verification** = inferred, not executed (e.g. anything requiring live Supabase/Groq/GPU). No secrets are reproduced here.

---

## 1. Executive summary

- **Health:** Modular monolith with a coherent layered backend (routers → services → repositories → models), a solid test suite (backend 581 passed / 1 skipped; frontend 265 passed) and real security thinking (JWKS-verified JWTs, per-user scoping, upload limits, SSRF guard in web fetch, prompt guard). Maturity is "late pre-alpha": features exist end to end, but operational concerns (database setup, persistent paths, deployment) are not yet reliable.
- **Major risks:** (1) the database/migration story was broken for local runs and is only partly fixed; (2) data-path configuration depends on the working directory (Chroma, uploads); (3) SQLite does not enforce foreign keys, so deletes leave orphans; (4) no rate limiting on the LLM-backed endpoints; (5) no container or deployment artefacts, and a very heavy ML dependency set (torch, transformers).
- **Docker readiness: NOT READY.** Nothing is fundamentally incompatible, but there are 5 blockers (Section 7), all small-to-medium and fixable before any Dockerfile is written.

---

## 2. Existing architecture

| Layer | Implementation |
|---|---|
| Frontend | React + TypeScript + Vite, React Router, Supabase JS for sign-in, `services/api.ts` (fetch, base `/api/v1`), Vite dev proxy to backend. Vitest + jsdom. |
| Backend | FastAPI (`app/main.py`), 14 routers under `/api/v1` plus unprefixed `/health*` and `compat`. SQLAlchemy 2 + Alembic, Pydantic settings. |
| Auth | Supabase JWT verified in `core/security.py` (JWKS ES256/RS256, legacy HS256 only if secret set); `CurrentUser` dependency; user row provisioned on first request. |
| Persistence | Relational DB (PostgreSQL/Supabase intended; SQLite supported) + ChromaDB embedded (`chromadb_persist_dir`) + file storage (`local` or `supabase` backend). |
| AI | Groq LLM client, LangGraph agent (`app/agent`, optional multi-agent behind `AGENT_MULTI_AGENT`), prompt guard + guardrails, memory extraction/confirmation, conversation continuity summaries (Chroma + DB). |
| RAG | Loader → chunker → embeddings → `VectorStore` (curated + per-user collections) → retriever filtered by owner. Ingestion runs in FastAPI `BackgroundTasks` (`rag/worker.py`). |
| STT | Local IBM Granite model (`app/stt`), warmed in a daemon thread at startup. |

Data flow (chat): frontend → `POST /chat` (sync handler, threadpool) → `ChatService` → guard → agent graph (tools, retrieval, memory) → persist messages → response.

---

## 3. Feature completeness matrix

| Feature | Status | Evidence / Files | Issues | Required action |
|---|---|---|---|---|
| Auth / user provisioning | Complete | `core/security.py`, `services/auth_service.py`; user created on first request (verified via smoke run) | Live Supabase flow not exercised | Verify against real project |
| Chat + agent | Complete | `routers/chat.py`, `services/chat_service.py`, `agent/` | Synchronous, non-streaming; no rate limit | See F-06 |
| Conversations (list/rename/delete) | Partial | `routers/conversations.py` | Orphaned messages on SQLite (F-02, resolved for new deletes; see section 11) | None for new data |
| Documents / RAG ingest | Complete | `routers/documents.py`, `rag/*`, `services/document_service.py` | Background ingest is in-process only; stuck docs reconciled at startup (works) | Acceptable for single instance |
| Document delete | Complete | Router deletes vectors, file, row (stale docstring in service says vectors are not removed) | Misleading docstring | Fix comment |
| Library page | Complete | `LibraryPage.tsx` | — | — |
| Memory + pending updates | Complete | `routers/memory.py`, `memory/*` | — | — |
| Profile | Complete | `routers/profile.py` | — | — |
| Workouts | Complete | `routers/workouts.py`, `WorkoutsPage.tsx` | — | — |
| Plan (sessions, templates) | Complete | `routers/plan.py` | Lint purity warnings only | — |
| Progress / measurements | Complete | `routers/progress.py` | — | — |
| Activity events | Needs Verification | `routers/activity.py` exists; I found no frontend call to `/activity` | May be backend-only by design | Confirm with docs |
| Exercises library / location | Needs Verification | `routers/exercises.py`, `location.py`; frontend usage only partly traced | — | Confirm |
| Speech-to-text | Needs Verification | `app/stt`, `services/stt.ts`; tests mock the model | Never run against the real model/GPU here | Verify on target hardware |
| Web search / nearby gyms | Needs Verification | `tools/web*`, `tools/nearby_gyms.py` | Needs live network | Verify |
| In-app dialogs/toasts | Complete (Phase 1) | `components/ui/ConfirmDialog.tsx`, `Toast.tsx` | — | — |

---

## 4. Technical audit findings

| ID | Severity | Area | Finding | Evidence | Recommended fix |
|---|---|---|---|---|---|
| F-01 | **High** | Config / DB | Previously `DATABASE_URL=sqlite:///` (in-memory) in local `.env` caused "no such table". Root cause fixed in code (startup schema check; portable migrations; SQLite path anchoring) and locally (`data.db` migrated). **Production Postgres/Supabase state is Needs Verification**: the live DB's `alembic_version` is unknown. | commits `f1e64d0`…`631826d`; `alembic current` on `data.db` = `0004` | Run `alembic upgrade head` on the real DB after a backup; if tables pre-exist without Alembic history, plan a reviewed baseline (do not blind-stamp). |
| F-02 | **High** (resolved, see section 11) | Data integrity | SQLite never enables `PRAGMA foreign_keys`. Models use `passive_deletes=True`, so deleting a conversation leaves its messages. | Reproduced: 1 orphan message after delete on SQLite. `db/session.py` has no pragma. | Enable FK pragma via an engine `connect` listener for SQLite. |
| F-03 | **High** (resolved in code; data consolidation open, see section 11) | Config | Relative `CHROMADB_PERSIST_DIR=./chroma_data` and `UPLOAD_DIR=./uploads` depend on CWD. Three Chroma directories exist on disk (`/chroma_data`, `backend/chroma_data`, `backend/data/chroma`), so starting from different folders yields different vector stores — the same class of bug as the DB issue. | `core/config.py:81,111`; directory listing | Anchor to a data root (as done for SQLite) and/or require absolute paths; consolidate. |
| F-04 | Medium | Migrations | `alembic check` reports drift between models and the migrated SQLite schema (Enum vs VARCHAR, `user_profiles.user_id` unique constraint vs unique index). Much is SQLite/non-native-enum noise; the `user_profiles` uniqueness difference may be real. **Needs Verification on Postgres.** | `alembic check` output | Run `alembic check` against Postgres; add a CI job that migrates a scratch DB and checks drift. |
| F-05 | Medium | Migrations | Migrations were edited in place (JSONB→portable JSON variant, `now()`→`CURRENT_TIMESTAMP`, dialect branch in `0cf16f5439a2`). Postgres SQL output was compared offline only; no live Postgres run. | Offline `--sql` render | Run the chain on a disposable Postgres in CI. |
| F-06 | **High** | Security / cost | No rate limiting on `/chat`, `/documents` upload, `/stt/transcribe`. Each chat call triggers paid LLM work. (Only web-tool calls have a limit.) | grep: only `web_user_rate_limit_per_minute` | Add per-user rate limits/quotas. |
| F-07 | Medium | Reliability | Startup `_reconcile_stuck_documents` and STT warmup swallow/log failures; STT warmup success is not visible in `/health/ready`. `/health/ready` checks only the DB (not Chroma, storage, Groq). | `main.py` | Extend readiness; expose STT/Chroma state. |
| F-08 | Medium | Reliability | Ingestion uses in-process `BackgroundTasks`; a process restart mid-ingest leaves docs `processing` until reconciliation marks them failed. Multiple uvicorn workers would each run their own startup sweep and share one Chroma dir. | `rag/worker.py`, `main.py` | Document single-worker constraint, or add a proper job queue later (not needed now). |
| F-09 | Medium | Security | `allow_credentials=True` with an origins list — safe while the list is explicit; defaults are localhost only, so production **will** need `CORS_ORIGINS` set. | `main.py`, `config.py:28` | Make origins required in production; startup warning. |
| F-10 | Medium | Security | Default `DATABASE_URL` embeds `postgres:postgres@localhost`; `DEBUG=true`/`reload` are dev defaults. | `config.py:64`, root `package.json` | Fail fast in `ENVIRONMENT=production` on default credentials. |
| F-11 | Low | Hygiene | Stray files at repo root and in backend: `test_upload.py/.sh`, `test_full_flow.py`, `test_workout.*`, `test_config.py`, `backend/check_tables.py` (the last two are untracked local debugging scripts) and a `unit testing/` folder. Some are git-ignored. | `ls` | Remove/relocate after review (not touched here). |
| F-12 | Low | Config | `.env.example` is missing `EXTRACTION_API_KEY` and `EXTRACTION_MODEL` (the only 2 of 76 settings absent). | script comparison | Add placeholders. |
| F-13 | Low | Docs | `DocumentService.delete` docstring says vectors are not removed; the router does remove them first. | `document_service.py:279` | Correct docstring. |
| F-14 | Low | Frontend | Pre-existing oxlint warnings (setState-in-effect, impure `Date` in render, fast-refresh exports). Not errors. | `npm run lint` | Triage later. |
| F-15 | Low | Docs | Root `package.json` dev script uses `uvicorn --reload` on `127.0.0.1`; README documents `alembic upgrade head` but not the SQLite option now supported. | `package.json` | Update docs. |

### Previously observed errors — are they resolved?
- `no such table: users/documents`, `Engine(sqlite:///)`: **Resolved in code and locally; Verified** (full backend suite, startup against `data.db`, endpoints 200). Startup now fails loudly rather than continuing against an empty DB. Production DB state remains F-01.

---

## 5. Security and data-integrity findings

**Security (by severity)**
1. **High — F-06** unthrottled LLM/STT/upload endpoints (cost and abuse).
2. **Medium — F-09/F-10** production CORS/defaults must be forced explicit.
3. **Medium — prompt injection / RAG boundaries:** retrieval is owner-filtered (`retriever.py` scopes user collection by `owner_id`; blank user gets curated only) and a prompt guard exists. Residual risk from uploaded documents containing instructions is inherent; **Needs Verification** via adversarial tests (none found).
4. **Good (Verified by reading):** JWT algorithm allow-list, optional audience check, no secrets committed (`.env` ignored, no `.env`/db/uploads tracked), sensitive keys redacted in logging config, upload size limit enforced while streaming, SSRF host check in web fetch, secret-scan workflow present.
5. **Needs Verification:** upload filename/path handling in `document_storage.py` (keys appear server-generated; not fully traced), `SUPABASE_SERVICE_ROLE_KEY` is configured but I found no use in app code.

**Data integrity:** F-02 (orphans on SQLite), F-03 (split vector stores), F-04/F-05 (migration drift/verification), document deletion ordering is deliberate and sound (vectors → file → row). Continuity summary vectors are removed on conversation delete (router).

---

## 6. Testing gaps

Current: backend 13 API + 9 unit + 7 integration + 3 guardrail test files; `tests/end_to_end/` is **empty**; coverage gate `fail_under = 0`; frontend 27 files / 265 tests; CI runs ruff, pytest, oxlint, tsc, vitest, build; no mypy or Playwright/e2e in CI.

Prioritised additions:
1. **P0** Migration test on **PostgreSQL** (service container) + `alembic check` drift gate.
2. **P0** FK-enforcement test (conversation/user delete cascades) once F-02 is fixed.
3. **P1** Startup test: `create_app()` lifespan with a real temp-file DB (the TestClient fixtures never run startup — that is how this class of bug escaped).
4. **P1** Rate-limit tests once implemented; upload hostile-filename/oversize/zip-bomb tests.
5. **P1** Cross-user isolation tests for every router (documents, memory, workouts, conversations, Chroma retrieval).
6. **P2** Prompt-injection regression set against RAG content; STT contract test with a tiny fixture model.
7. **P2** Frontend: delete flows for Documents/Memory/Workouts/Profile pages (Phase 1 covered conversations, memory and library via updated tests only); one Playwright smoke test of login → chat.
8. **P2** Raise coverage gate above 0 after a baseline measurement.

---

## 7. Docker readiness checklist

| Item | State |
|---|---|
| Frontend builds reproducibly (`npm ci && npm run build`, lockfile present, CI builds it) | **Ready** |
| Backend deps pinned via `pyproject.toml` (mirror `requirements.txt`) | **Ready**, but see torch note |
| Config via environment (pydantic-settings) | **Ready** |
| Liveness/readiness endpoints | **Ready** (readiness DB-only — improve) |
| Migrations runnable headless (`alembic upgrade head`) | **Ready** after this work; Postgres run **Needs Verification** |
| DB URL / startup validation | **Ready** (fails fast) |
| Persistent paths independent of CWD (Chroma, uploads) | Ready in code (F-03 resolved); existing directories not consolidated |
| FK integrity if SQLite is used | Resolved for SQLite (F-02); pre-existing orphans reported only |
| Postgres production path proven | **Needs Verification — blocker (F-01/F-05)** |
| Production CORS / default-credential guard | **Not ready — blocker (F-09/F-10)** |
| Rate limiting | **Not ready — high priority, not a build blocker** |
| Non-root user, resource limits, graceful shutdown | **Not ready** (no container yet; Chroma/SQLite need clean shutdown — uvicorn SIGTERM is adequate) |
| STT/Granite in container (torch 2.9.1, transformers ≥5.16, ~900 MB weights, GPU optional) | **Needs Verification — blocker for image design** (CPU-only image vs GPU; weights must be baked or on a volume) |
| `STT_EAGER_LOAD`, HF cache location | **Needs Verification** |
| Localhost references | Defaults only (`config.py` host/CORS/DB). Frontend uses relative `/api/v1` → needs a reverse proxy in prod (Vite proxy is dev-only). |
| Secrets in images | None tracked; must be injected at runtime (`.env` ignored). Frontend `VITE_*` values are baked at build time — only the anon key/URL, which is intended to be public. |

**Blockers:** F-01 Postgres verification, F-03 CWD-dependent data paths, production config guard (F-09/F-10), STT/torch packaging decision, and a decision on how the SPA reaches the API (reverse proxy).

Python 3.10 floor and Node version are only implied by CI; pin both explicitly before building images. `psycopg2-binary` is acceptable for slim images; `av`, `soundfile` need system libs (ffmpeg/libsndfile) — **Needs Verification**.

---

## 8. Recommended Docker architecture

Keep it minimal — three services, two if the DB stays on Supabase:

1. **`web`** (nginx): serves the built SPA and reverse-proxies `/api/v1` and `/health` to `api`. Removes the dev-proxy dependency and CORS surface (same origin).
2. **`api`** (FastAPI, uvicorn, **single worker**, non-root): embedded ChromaDB, local uploads and HF model cache on **named volumes** (`chroma`, `uploads`, `hf-cache`). One-shot migration step (`alembic upgrade head`) before start (entrypoint or init job), then readiness gating.
3. **`db`** (PostgreSQL) **only if not using Supabase Postgres**. The product already authenticates against Supabase, so the simplest production shape is `web` + `api` with `DATABASE_URL` pointing at Supabase; Compose adds `db` for local dev parity.

No separate Chroma server (embedded + volume is sufficient for one instance) and no worker service (in-process background tasks are adequate until multi-instance). Networking: one internal network; only `web` publishes a port. Health checks: `api` → `/health/ready`; `web` depends on `api` healthy. Restart policy `unless-stopped`; JSON logs to stdout (structlog already). Dev vs prod via Compose override files; secrets via env-file/secret store, never the image.

Startup sequence: `db` healthy → migrate → `api` ready (schema check passes) → `web`.

---

## 9. Prioritised implementation roadmap

**P0 — correctness / integrity / security blockers**
- F-02 enable SQLite FK pragma. F-03 anchor/consolidate data paths. F-01/F-05 prove migrations on Postgres (disposable DB), plan the real-DB upgrade with backup. F-10/F-09 production config guard.
- Accept when: new tests for cascades and path anchoring pass; Postgres CI job green; production startup refuses default creds/localhost CORS.
- Files: `db/session.py`, `core/config.py`, `.github/workflows/backend-ci.yml`, migrations.

**P1 — functionality and reliability**
- F-06 rate limiting; F-07 richer readiness; confirm unverified features (activity, exercises, STT, web tools); F-08 document single-worker constraint.
- Accept when: limits tested; `/health/ready` reports DB, Chroma, storage.

**P2 — testing / maintainability / config**
- Section 6 plan; F-04 drift gate; F-11 cleanup; F-12 `.env.example`; F-13/F-15 docs; coverage baseline.

**P3 — Docker preparation and containerisation**
- Decide STT packaging (CPU vs GPU, weights strategy); pin Python/Node; write Dockerfiles, Compose (dev/prod), nginx config, entrypoint migration step.
- Accept when: `docker compose up` yields healthy services, data survives `down/up`, migrations idempotent.

**P4 — production hardening**
- Non-root, resource limits, image scanning, backups for Postgres/Chroma/uploads, log shipping, CI image build.

---

## 10. Final recommendation

1. **What prevents reliable deployment today?** Unproven Postgres migration path, CWD-dependent data directories, no production config guard, undecided STT/torch packaging, and no reverse-proxy/serving story for the SPA.
2. **Fix before Dockerising:** the P0 list above plus the STT packaging decision.
3. **Safely deferred:** rate-limit polish beyond a basic limiter, job queue, Playwright e2e, lint-warning cleanup, coverage thresholds, image hardening details.
4. **Order:** P0 → P1 (rate limits, readiness) → P2 (CI Postgres/drift tests) → P3 → P4.
5. **First task after approval:** enable SQLite FK enforcement and anchor Chroma/upload paths to a single data root (F-02 + F-03), with tests — small, high-value, and it removes the last CWD-dependent behaviour.

## 11. Remediation log: P0 data integrity and storage (F-02, F-03)

### F-02: SQLite foreign keys — resolved for new data
- **Root cause (confirmed):** `app/db/session.py` built the SQLite engine without `PRAGMA foreign_keys=ON`. The relationships use `passive_deletes=True` and the schema declares `ON DELETE CASCADE`, so SQLite skipped the cascade and left messages behind.
- **Fix:** `enable_sqlite_foreign_keys(engine)` registers an engine `connect` hook, so the pragma is set on every pooled connection. `build_engine` applies it to SQLite; the `db_session` test fixture applies it too. Alembic builds its own engine and is intentionally left without it (SQLite batch table rebuilds must run with enforcement off). No model or migration changed; no cascade semantics were altered.
- **Existing data:** `find_foreign_key_violations(engine)` (`PRAGMA foreign_key_check`, read-only) runs at startup and logs `foreign_key_violations_found`. `backend/scripts/check_orphans.py` prints counts per table. Nothing is deleted automatically. The local `backend/data.db` currently has **2 orphan rows in `messages`** (parent conversation missing); they were left untouched. Back up the file before any manual cleanup.
- **Tests:** `tests/unit/test_sqlite_foreign_keys.py` (pragma on every/new/recycled connection, invalid reference rejected, conversation delete removes only its own messages, legacy orphans reported and preserved, no-op on non-SQLite).
- **Limits:** this does not show PostgreSQL behaviour (PostgreSQL enforces FKs natively; unverified here, see F-01).

### F-03: working-directory-dependent paths — resolved in code; consolidation open
- **Root cause (confirmed):** `upload_dir` and `chromadb_persist_dir` were relative strings; `VectorStore` fell back to a different default (`./data/chroma`); `.env` itself was read from the current directory.
- **Fix:** `core/config.py` adds `BACKEND_DIR` and `resolve_storage_path()`. Relative `UPLOAD_DIR` / `CHROMADB_PERSIST_DIR` values are resolved against `backend/`; absolute values (e.g. a volume mount) are used unchanged. `.env` is read from `backend/.env` regardless of directory. `VectorStore` now falls back to the configured directory instead of `./data/chroma`. Defaults are unchanged for the usual launch from `backend/`, so the store in use does not move.
- **Existing Chroma directories (read-only inspection):**
  - `backend/chroma_data`: the active store. `user_documents` 237 chunks, `user_continuity` 28, `fitness_knowledge` 0.
  - `backend/data/chroma`: `user_documents` 2 chunks. It was the old `VectorStore()` default, no longer used by the application.
  - `<repo>/chroma_data`: collections exist but hold 0 chunks (created when launched from the repo root).
  - No migration was performed. The two minor directories were not merged, moved or deleted. Whether the 2 chunks in `backend/data/chroma` matter must be decided by the owner (they may correspond to test documents). Re-ingesting is the safe path if needed.
- **Tests:** `tests/unit/test_storage_paths.py` (anchoring, absolute and env overrides, document storage root, and a subprocess probe from `backend/`, the repo root and a temp directory returning identical paths without creating directories).
- **Limits:** the data root is still two separate settings rather than a single `DATA_DIR`; `.env.example` keeps the same relative defaults.
