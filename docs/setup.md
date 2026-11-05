# Development setup

A detailed local runbook. The [README](../README.md#getting-started) has the short version.

## Prerequisites

- Python 3.10+ and Node.js 22 with npm.
- A Supabase project (Auth is required for sign-in; Postgres and Storage are optional locally) and a Groq
  API key for chat.
- A PostgreSQL database reachable through `DATABASE_URL`. The backend refuses to start against a schema that
  is behind the latest migration.

## 1. Configure

```bash
cp backend/.env.example backend/.env        # PowerShell: Copy-Item backend\.env.example backend\.env
cp frontend/.env.example frontend/.env.local
```

[`backend/.env.example`](../backend/.env.example) documents every variable. The ones you need first:

| Variable | Notes |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://…` (Supabase pooled URL works). |
| `SUPABASE_URL` | Drives JWKS token verification and the expected issuer. |
| `SUPABASE_JWT_SECRET` | Only for legacy **HS256** projects; leave empty for ES256/RS256. |
| `GROQ_API_KEY`, `GROQ_MODEL` | Chat. See [`models.md`](models.md). |
| `DOCUMENT_STORAGE_BACKEND` | `local` for development; `supabase` in production. |
| `BACKEND_HOST` / `BACKEND_PORT` | Single source of truth for the dev server address; Vite and the dev scripts read them. |

Frontend: set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`; leave `VITE_API_BASE_URL` unset in
development (Vite proxies `/api/v1`). Only the public anon key belongs in the frontend.

## 2. Install and migrate

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
alembic upgrade head
```

`alembic.ini` holds no URL; migrations use `DATABASE_URL`. Create a new migration only for model changes:
`alembic revision --autogenerate -m "describe change"`. Review it for data loss before applying.

## 3. Run

```bash
npm install && npm run dev        # from the repository root: backend (:8000) + frontend (Vite)
```

Alternatives: `scripts/dev.ps1` (Windows) or `scripts/run-all.sh` (macOS/Linux/Git Bash); both check the port
first and stop both processes on Ctrl+C. Backend only:

```bash
cd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive API docs are at `http://127.0.0.1:8000/docs` in development. Probes: `GET /health` and
`GET /health/ready`.

## 4. Test and check

```bash
# backend/
python -m pytest -q          # in-memory SQLite, mocked LLM: no live credentials needed
ruff check . && ruff format --check .
mypy app

# frontend/
npm run lint && npm run type-check && npm test && npm run build
```

Some upload tests expect `DOCUMENT_STORAGE_BACKEND=local` (CI sets it); PostgreSQL/pgvector integration tests are
skipped unless a database is configured.

## 5. Utilities

| Script | Purpose |
|---|---|
| `python -m scripts.ingest_knowledge` | Ingest curated documents from [`knowledge_base/`](../knowledge_base/README.md) into the shared collection. |
| `python -m scripts.audit_library [--user <id>] [--fix]` | Reconcile the `documents` table against the vector index (read-only unless `--fix`, which backs up first and never deletes rows or stored files). |
| `python -m scripts.backfill_continuity` | Backfill cross-chat continuity data. |
| `python -m scripts.set_groq_key` | Update the Groq key variables in `backend/.env` safely (keeps a backup). |
| `python -m scripts.guard_smoke`, `continuity_smoke`, `verify_memory_intelligence` | Manual smoke checks that need live credentials. |

Image text extraction uses `VISION_PROVIDER_ORDER` (`groq,rapidocr` by default); `rapidocr-onnxruntime` needs
no API key and no extra binaries.

## Related documentation

[`api.md`](api.md) · [`models.md`](models.md) · [`extraction.md`](extraction.md) ·
[`deployment.md`](deployment.md) · [`SECURITY_AUDIT.md`](SECURITY_AUDIT.md)
