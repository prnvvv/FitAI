# Functionality Regression Report

Branch `feat/lightweight`. Nothing outside deployment plumbing and page-loading
was changed, so verification relies on the existing suites plus new tests.

## Test results

| Suite | Result |
|---|---|
| Backend `pytest` | 715 passed, 16 skipped, 0 failed |
| Backend `ruff check` | clean |
| Frontend `tsc -b` | clean |
| Frontend `oxlint` | 0 errors (pre-existing warnings only) |
| Frontend `vitest` | 316 passed, 0 failed |
| Frontend production build | succeeds |

Baseline before changes was 689 passed / 16 skipped backend, 316 frontend: no
test was removed or weakened. The only edit to an existing test file is the
blueprint path in `test_deploy_files.py` (`render.yaml` → `render.split.yaml`),
because that file guards the two-service blueprint, which was kept.

## Existing features covered by the existing automated suites (unchanged, still passing)

Authentication/JWT validation, chat and conversation persistence/ordering/pagination/
isolation, streaming, LangGraph agent and tools, memory extraction/persistence/
retrieval, RAG/pgvector (unit level), document ingestion jobs, Supabase Storage
adapter (mocked), workouts, exercises, progress/activity, plan, guardrails,
error envelope, frontend pages and routes (chat, library, memory, plan, progress).

## Regression tests added (26)

- `test_spa_serving.py`: shell fallback for client routes; immutable caching of
  hashed assets; `/health`, `/docs`, `/openapi.json` not shadowed; unknown `/api`
  paths return 404 not the shell; protected API still rejects anonymous calls;
  path traversal (plain, encoded) leaks nothing; POST to unknown path is not swallowed;
  Core stays API-only without a build.
- `test_single_service_worker.py`: worker starts only for jobs mode + document routes;
  start is idempotent; stop is safe twice; disabled outside jobs mode.
- `test_single_service_files.py`: blueprint is one service, env keys are real
  settings, no secrets in the file, production settings validate, Dockerfile is
  non-root/one worker/no auto-migration, requirements are the core ∪ documents
  union without ML libraries, dockerignore is an allow-list.
- Existing `test_service_entrypoints.py` import-isolation tests still pass, so
  Core and Documents still load no heavy libraries.

## Blocked / not verified

- **Docker image build**: daemon unavailable.
- **Live end-to-end** (login, chat with Groq, streaming against real model, memory
  extraction with the extraction key, PDF upload → Supabase Storage → embeddings →
  retrieval, real Postgres transactions): needs external credentials/services; not
  run. 16 existing Postgres/pgvector tests skip without a live database.
- **Browser-level check of lazy pages**: covered by type-check/build and unit tests
  only; no manual click-through was performed.
- **Cross-user isolation against a real database**: covered by existing mocked/
  in-memory tests only.
