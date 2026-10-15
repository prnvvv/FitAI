# FitAI

FitAI is a domain-specific, agentic RAG chatbot for gym-goers, fitness enthusiasts,
and nutrition-conscious users. It pairs retrieval-augmented generation over curated
fitness and nutrition knowledge with persistent user memory, historical fitness
tracking, deterministic calculation tools, and a LangGraph agent — so answers are
grounded, personalized, and remember relevant context across conversations.

> **Not a medical system.** FitAI offers general fitness and nutrition guidance. It
> is not a diagnostic or medical-treatment tool and does not replace professional
> advice.

## Table of contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Repository structure](#repository-structure)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Testing and quality checks](#testing-and-quality-checks)
- [Architecture](#architecture)
- [API](#api)
- [Project documentation](#project-documentation)
- [Contributing and ownership](#contributing-and-ownership)
- [Status and limitations](#status-and-limitations)

## Features

- **Grounded chat:** answers grounded in retrieved knowledge, with sources surfaced
  in the UI.
- **Persistent, structured memory:** remembers relevant facts about the user,
  separates current facts from historical statements, and asks for confirmation on
  ambiguous or conflicting updates.
- **Cross-chat continuity:** pinned core context, semantic recall of saved memories,
  and past-chat summaries so earlier conversations inform later ones.
- **Safety guardrails:** a deterministic rule set plus an optional LLM intent
  classifier gates every turn before any model or tool call; refusals never reach
  the model.
- **Deterministic fitness tools:** BMI, BMR, TDEE, calorie and macro calculations,
  workout logging/summaries, personal-record detection, and progress analysis.
- **Document ingestion:** upload PDF/TXT/DOCX (and image text via OCR), chunk, embed,
  and index into ChromaDB with status tracking.
- **Fitness tracking UI:** profile, plan, progress, workouts, memory controls, and a
  ChatGPT-style chat history.

## Tech stack

| Layer          | Technologies                                                                                  |
| -------------- | --------------------------------------------------------------------------------------------- |
| Frontend       | React 19, TypeScript, Vite, Vitest, jsdom, react-router, react-markdown, Supabase JS           |
| Backend        | Python 3.10+, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, Uvicorn                              |
| Data & storage | PostgreSQL via Supabase, Supabase Auth, ChromaDB (vector store)                                |
| AI & retrieval | Groq (LLM inference), LangGraph (agent orchestration), ChromaDB embeddings                      |
| Tooling        | Ruff, MyPy, Pytest, oxlint, GitHub Actions, Dependabot                                          |

## Repository structure

```text
FitAI/
├── frontend/                 # React + TypeScript + Vite app
│   └── src/
│       ├── components/       # layout, chat, documents, profile, memory
│       ├── pages/            # Chat, Library, Memory, Plan, Profile, Progress, Login
│       ├── hooks/            # e.g. useConversations
│       ├── services/         # API client + Supabase
│       ├── context/          # auth context
│       ├── types/            # shared TypeScript types
│       └── utils/
│
├── backend/                  # FastAPI app (modular monolith)
│   ├── app/
│   │   ├── main.py
│   │   ├── api/              # deps + routers
│   │   ├── schemas/          # Pydantic request/response models
│   │   ├── models/           # SQLAlchemy entities
│   │   ├── repositories/     # database access
│   │   ├── services/         # business logic
│   │   ├── agent/            # LangGraph state, nodes, routing
│   │   ├── memory/           # fact extraction, temporal reasoning, confirmation
│   │   ├── rag/              # loading, chunking, embeddings, retrieval
│   │   ├── guardrails/       # deterministic rules + intent classifier
│   │   ├── tools/            # fitness calculators and helpers
│   │   ├── llm/              # Groq client + prompts
│   │   ├── safety/           # policy checks
│   │   ├── core/             # config, security, logging, errors
│   │   └── db/               # engine, session, base
│   ├── migrations/           # Alembic
│   └── tests/                # unit, integration, api, end_to_end
│
├── docs/                     # architecture, setup, API contracts, extraction
├── knowledge_base/           # curated fitness/nutrition source documents
├── scripts/                  # dev + audit + audit/smoke utilities
├── AGENTS.md                 # project conventions and ownership
└── README.md
```

## Getting started

### Prerequisites

- **Python 3.10+** (developed against 3.13).
- **Node.js and npm** for the frontend.
- A **Supabase** project for Auth (and optionally a private Storage bucket for
  documents).
- A **Groq API key** for LLM inference.

### Backend

```powershell
cd backend
python -m venv .venv
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

python -m pip install -e ".[dev]"

copy .env.example .env      # Windows; use `cp` on macOS/Linux, then fill in values
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- OpenAPI docs: `http://127.0.0.1:8000/docs`
- Liveness: `GET /health`; readiness: `GET /health/ready` (unauthenticated)

See [`docs/backend_setup.md`](docs/backend_setup.md) for the full environment
runbook.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env        # then fill in values
npm run dev
```

### Run both from the repository root

The root `package.json` wires the two apps together with `concurrently`:

```bash
npm install        # installs the root dev dependency
npm run dev        # starts backend (:8000) and frontend (Vite) together
```

Convenience wrappers are also available: `scripts/dev.ps1` (Windows) and
`scripts/run-all.sh` (macOS/Linux/Git Bash).

## Configuration

Environment variables are the single source of truth. Templates live in
[`backend/.env.example`](backend/.env.example) and
[`frontend/.env.example`](frontend/.env.example); never commit real `.env` files.

Common backend variables (full table in
[`docs/backend_setup.md`](docs/backend_setup.md)):

| Variable                   | Purpose                                                      |
| -------------------------- | ------------------------------------------------------------ |
| `DATABASE_URL`             | PostgreSQL URL (`postgresql+psycopg2://...`, Supabase pooled).|
| `SUPABASE_URL`             | Project URL; drives JWKS and expected issuer.                |
| `SUPABASE_JWT_ALGORITHMS`  | Token algorithm allow-list (`ES256,RS256` by default).       |
| `SUPABASE_JWT_SECRET`      | Only for legacy HS256 signing; leave empty otherwise.        |
| `GROQ_API_KEY`             | LLM inference.                                               |
| `BACKEND_HOST` / `BACKEND_PORT` | Dev server address consumed by the scripts and Vite proxy. |
| `CORS_ORIGINS`             | Comma-separated allowed origins.                             |
| `DOCUMENT_STORAGE_BACKEND` | `unconfigured` / `local` / `supabase`.                       |

Frontend variables: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, and
`VITE_API_BASE_URL` (defaults to `/api/v1`). Only the Supabase **anon** key
belongs in the frontend; server-only secrets must stay in the backend.

## Testing and quality checks

### Backend

```bash
cd backend
pytest                          # full suite
ruff check app tests            # lint
ruff format --check app tests   # formatting
mypy app                        # strict type checking
```

The backend suite runs against an in-memory SQLite database and overrides the
auth dependency, so **no live Supabase or Groq credentials are required** for
ordinary runs. A few tests opt into live calls through environment flags, for
example the guard classifier eval:

```bash
RUN_GUARD_EVAL=1 pytest tests/guardrails/test_guard_eval.py -q -s
```

### Frontend

```bash
cd frontend
npm run type-check   # tsc -b
npm run lint         # oxlint
npm test             # vitest (jsdom)
npm run build        # production build
```

From the repository root you can also run `npm run test:backend`,
`npm run test:frontend`, `npm run type-check:frontend`, and
`npm run build:frontend`.

## Architecture

FitAI is a **modular monolith**. The frontend talks to FastAPI, and the backend
coordinates authentication, persistence, memory, RAG, tools, safety, and LLM
responses in a single deployable application.

Dependency direction: **Router → Schema → Service → Repository → Model**.

Core components:

- **Frontend** — chat UI, persistent history, document upload, profile, progress,
  and memory controls.
- **API layer** — FastAPI routers, request validation, auth dependencies, response
  serialization.
- **Service layer** — business logic coordinating persistence and AI modules.
- **Database layer** — SQLAlchemy models, repositories, PostgreSQL, Alembic.
- **Agent layer** — LangGraph state, nodes, conditional routing, final response.
- **Memory layer** — fact extraction, temporal classification, change detection,
  confirmation proposals, historical records.
- **RAG layer** — document loading, chunking, embeddings, ChromaDB storage and
  retrieval.
- **Tools layer** — BMI, BMR, TDEE, calorie/macro calculators, workout and progress
  analysis.
- **LLM layer** — Groq client configuration and prompts.
- **Guardrails & safety layer** — policy checks and tool-execution restrictions.

PostgreSQL (via Supabase) is the authoritative store for structured user data and
conversations. ChromaDB stores searchable document chunks and embeddings; it is
not the authoritative source for user profiles, conversations, or memory state.

## API

All endpoints are served under `/api/v1`. Route groups include: `health`, `auth`,
`chat`, `conversations` (and messages), `profile`, `memory` (and pending
proposals), `documents`, `workouts`, `progress`, `plan`, `exercises`, `location`,
and `activity`.

Every protected endpoint verifies the Supabase access token and derives the user
identity from the verified context; private queries and vector retrieval are
scoped to the authenticated user. See
[`docs/api_contracts.md`](docs/api_contracts.md) and the live OpenAPI schema at
`/docs`.

## Project documentation

- [`docs/backend_setup.md`](docs/backend_setup.md) — backend environment and runbook.
- [`docs/api_contracts.md`](docs/api_contracts.md) — endpoint contracts.
- [`docs/extraction.md`](docs/extraction.md) — structured fact extraction.
- [`AGENTS.MD`](AGENTS.MD) — conventions, ownership, and workflow rules.

## Contributing and ownership

Two developers share this repository with clear boundaries:

- **Person 1 — core backend and persistence:** authentication, CRUD routers,
  Pydantic schemas, SQLAlchemy models, repositories, migrations, conversation and
  message persistence, profile/memory persistence, document metadata, and
  workout/measurement persistence.
- **Person 2 — AI engine and intelligence:** LangGraph agent, Groq prompts, RAG
  ingestion and retrieval, ChromaDB operations, memory extraction and temporal
  reasoning, continuity, fitness tools, and safety policies.

Some files are **shared** and require coordination before changes:
`backend/app/main.py`, `backend/app/api/deps.py`,
`backend/app/api/routers/chat.py`, `backend/app/services/chat_service.py`,
`backend/app/core/config.py`, `backend/pyproject.toml`, `backend/.env.example`,
and `backend/tests/end_to_end/`.

Workflow: read `AGENTS.MD`, inspect the existing code and tests, keep changes
small and focused, add or update tests, run formatting/lint/type checks/tests, and
commit focused one-line messages. Backend dependencies are authoritative in
`backend/pyproject.toml`; the root `requirements.txt` is a convenience mirror.

## Status and limitations

FitAI is **pre-alpha**. Notable open items:

- The document storage target (`supabase`) is a placeholder; `local` is
  single-instance only.
- The live Supabase JWT signing type (symmetric vs asymmetric) should be confirmed
  against the project.
- The memory-key taxonomy is provisional.
- `mypy app` currently crashes on the unmodified tree in some environments (see
  [`docs/backend_setup.md`](docs/backend_setup.md)).
- FitAI is not a diagnostic or medical-treatment system.

## License

License reference is pending (see `backend/pyproject.toml`). No open-source
license has been selected yet.
