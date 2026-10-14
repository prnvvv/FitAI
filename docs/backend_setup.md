# FitAI Backend Setup

Environment and runbook for the backend. This documents what has been built and
the commands to run when execution is authorized. **Tests, lint, type checks,
migrations, and the app itself have not been run yet** — see the latest report.

## Prerequisites

- Python 3.10 or newer (project targets `>=3.10`; developed against 3.13.3).
- A Supabase project (Auth) and separately approved Supabase Storage for
  document files (optional while developing with `local` storage).
- Node.js only for the frontend; not needed for the backend.

## 1. Configuration

Copy the template and fill in values:

```bash
cp backend/.env.example backend/.env
```

Key variables (all owned by Person 1 unless marked Person 2):

| Variable                    | Default                | Notes                                                        |
| --------------------------- | ---------------------- | ------------------------------------------------------------ |
| `DATABASE_URL`              | local Postgres URL     | Use `postgresql+psycopg2://...` (Supabase pooled URL).       |
| `SUPABASE_URL`              | —                      | Project URL; drives the JWKS endpoint and expected issuer.   |
| `SUPABASE_JWT_SECRET`       | empty                  | Set only for legacy **HS256** signing. Leave empty for ES256/RS256. |
| `SUPABASE_JWT_ALGORITHMS`   | `ES256,RS256`          | Allow-list; `none` is always rejected.                       |
| `SUPABASE_JWT_AUDIENCE`     | `authenticated`        |                    |
| `DOCUMENT_STORAGE_BACKEND`  | `unconfigured`         | `unconfigured`/`local`/`supabase` (supabase not implemented).|
| `MAX_UPLOAD_SIZE_MB`        | `10`                   |                    |
| `CORS_ORIGINS`              | localhost Vite/React   | Comma-separated.                                             |
| `BACKEND_HOST` / `BACKEND_PORT` | `127.0.0.1` / `8000` | Single source of truth for the dev server address. The Vite proxy, `scripts/dev.ps1` and `scripts/run-all.sh` all read these from `backend/.env`. `HOST`/`PORT` are accepted as deprecated aliases. |
| `GROQ_API_KEY` / ChromaDB   | —                      | Person 2.                                                    |

`JWT_ALGORITHM`/`JWT_SECRET` (legacy names) are removed in favor of the
`SUPABASE_JWT_*` set above. Update any deployed environment accordingly.

## 2. Install

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## 3. Database migrations (run only when authorized)

```powershell
alembic revision --autogenerate -m "sync models"   # only for model changes
alembic upgrade head
```

The initial schema is `backend/migrations/versions/0001_initial_schema.py`.
It creates all tables with named constraints, JSONB columns, and the partial
unique index `uq_memories_user_key_active` (one active memory per user/key).
`migrations/env.py` uses `app.models.Base.metadata` and the configured
`DATABASE_URL`; `alembic.ini` holds no URL.

## 4. Run the app

The port lives in exactly one place: `BACKEND_HOST` / `BACKEND_PORT` in
`backend/.env`. Change it there; the dev scripts and the Vite proxy follow.

```powershell
# starts backend + frontend, checks the port first, stops both on Ctrl+C
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
```

On macOS/Linux (or Git Bash):

```bash
./scripts/run-all.sh
```

Backend only, using the configured address:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If startup fails because the port is unavailable, the script prints how to find
the owning process and how to change `BACKEND_PORT`; nothing is auto-moved.

- OpenAPI: `http://127.0.0.1:8000/openapi.json` (docs at `/docs`)
- Liveness: `GET /health`; readiness: `GET /health/ready` (both unauthenticated)

## 5. Tests (run only when authorized)

```powershell
pytest
```

The suite uses an in-memory SQLite database and overrides the auth dependency,
so no Supabase credentials are required for ordinary runs. `tests/unit` covers
config, token verification (symmetric mode), and memory-value validation;
`tests/api` covers authorization, ownership isolation, and every Person 1
endpoint; `tests/integration` covers model cascades and the memory
confirm/reject/stale/correct workflow.

## 6. Quality checks (run only when authorized)

```powershell
ruff check app tests
ruff format --check app tests
mypy app
```

## 7. Library index audit

Reconcile the `documents` table against the ChromaDB index (read-only by
default; exits non-zero when anything is not `OK`):

```powershell
python -m scripts.audit_library              # dry run, every user
python -m scripts.audit_library --user <id>  # one user
python -m scripts.audit_library --fix        # backup, re-index, drop orphans
```

Each document is classified `OK`, `OK_EMPTY` (Ready with no text on purpose),
`MISSING`, `STUCK`, `FAILED` or `DUPLICATE`; vectors without a database row are
reported as orphans, and a collection built with a different embedding model is
reported as `WRONG_EMBEDDING`. For every Ready document the script also runs one
real retrieval query built from the document's own first chunk and records
whether the document comes back.

`--fix` first copies the Chroma persist directory to a timestamped sibling,
then re-runs ingestion for missing/stuck/failed documents through
`DocumentService.retry` (same row, same stored file) and removes orphan vectors
only after that backup exists. It never deletes database rows or stored files,
never touches another user's data, and only reports duplicates.

Image text extraction is configured through `VISION_PROVIDER_ORDER`
(`groq,rapidocr` by default), `VISION_MODEL` (auto-detected when empty) and
`OCR_MAX_SIDE_PX`. `rapidocr-onnxruntime` needs no API key, no Tesseract binary
and no torch; Pillow does the EXIF/RGB/downscale preparation before any
provider runs.

## 8. Known decisions / open items

- **JWT signing type** for the live Supabase project is unknown; symmetric
  verification works once `SUPABASE_JWT_SECRET` is set, and asymmetric works
  via JWKS without it. Confirm which the project uses.
- **Document storage** target is unapproved; `local` is single-instance only
  and `supabase` is a placeholder until the owner approves a private bucket.
- **Memory-key taxonomy** is provisional until Person 2 confirms it (see
  `docs/api_contracts.md`).
- **Local OCR models** ship inside the `rapidocr-onnxruntime` wheel; a container
  image must include that wheel for image ingestion to work without Groq vision.
- `mypy app` currently crashes in this environment with an internal error
  ("unresolved placeholder type None") on the unmodified tree, so type checking
  is not a usable gate here until mypy or the dependency pins are updated.
- Supabase Auth did not exist at build time; provisioning is designed around
  the `sub` claim and must be validated against the live project.