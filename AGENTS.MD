# FitAI — Agent Instructions

## 1. Project Overview

FitAI is a domain-specific Agentic RAG chatbot built exclusively for gym-goers, fitness enthusiasts, and nutrition-conscious users.

Its goal is to provide personalized fitness guidance by combining:
- Retrieval-Augmented Generation (RAG) over fitness and nutrition documents.
- Persistent, structured user memory.
- Historical fitness tracking and progress analysis.
- LLM-based reasoning and structured fact extraction.
- Deterministic Python tools for fitness calculations.
- Agent orchestration using LangGraph.
- User-controlled memory updates with confirmation when necessary.

FitAI must remember relevant user information across conversations, distinguish current facts from historical statements, ground answers in retrieved knowledge where appropriate, and avoid inventing personal data or numerical results.

**Development principle:** Build a functional, understandable modular monolith. Prefer simple, reliable implementations over unnecessary abstractions or premature complexity.

## 2. Technology Stack

### Frontend
- React
- TypeScript
- Vite
- Vitest
- jsdom

### Backend
- Python
- FastAPI
- SQLAlchemy 2.x
- Pydantic 2.x
- PostgreSQL through Supabase
- Supabase Auth
- Alembic
- Pytest

### AI and Retrieval
- Groq API for LLM inference
- LangGraph for agent orchestration
- ChromaDB for vector storage and similarity search
- ChromaDB's configured embedding function
- Python functions for deterministic fitness calculations

### Development and CI
- Git and GitHub
- GitHub Actions
- Dependabot
- Ruff for Python linting and formatting
- MyPy where appropriate
- npm for frontend dependency management

Use the existing dependency configuration as the source of truth. Avoid introducing additional frameworks, services, or dependencies unless there is a clear requirement.

## 3. Architecture

FitAI uses a **modular monolithic architecture**.

The frontend communicates with FastAPI. The backend coordinates authentication, persistence, memory, RAG, tools, safety checks, and LLM responses within one application.

The main components are:

1. **Frontend:** Chat interface, persistent conversation history, document upload, profile management, progress views, and memory controls.
2. **API layer:** FastAPI routers, request validation, authentication dependencies, and response serialization.
3. **Service layer:** Application business logic and coordination between persistence and AI modules.
4. **Database layer:** SQLAlchemy models, repositories, PostgreSQL persistence, and migrations.
5. **Agent layer:** LangGraph state, processing nodes, conditional routing, and final response generation.
6. **Memory layer:** Fact extraction, temporal classification, change detection, confirmation proposals, and historical records.
7. **RAG layer:** Document loading, chunking, embeddings, ChromaDB storage, and retrieval.
8. **Tools layer:** BMI, BMR, TDEE, calorie and macro calculations, workout tracking, and progress analysis.
9. **LLM layer:** Groq client configuration and prompts.
10. **Safety layer:** Policy checks and restrictions on sensitive requests and tool execution.

Keep these responsibilities separate. Do not turn the project into microservices.

## 4. Repository Structure

Follow the existing repository layout:

```text
FitAI/
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── layout/
│       │   ├── chat/
│       │   ├── documents/
│       │   ├── profile/
│       │   └── memory/
│       ├── pages/
│       ├── hooks/
│       ├── services/
│       ├── types/
│       └── utils/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── routers/
│   │   ├── schemas/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── agent/
│   │   ├── memory/
│   │   ├── rag/
│   │   ├── tools/
│   │   ├── llm/
│   │   ├── safety/
│   │   ├── core/
│   │   └── db/
│   ├── migrations/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── api/
│   │   └── end_to_end/
│   └── pyproject.toml
│
├── docs/
│   ├── architecture.md
│   └── development.md
├── knowledge_base/
├── scripts/
├── .github/
│   ├── workflows/
│   └── dependabot.yml
├── .gitignore
├── AGENTS.md
└── README.md
```

Consult the actual repository before creating, moving, renaming, or deleting files. Do not recreate existing files or folders unnecessarily.

## 5. Backend Coding Conventions

Follow this dependency direction:

**Router → Schema → Service → Repository → Model**

- **Routers:** Handle HTTP requests, dependencies, status codes, and responses.
- **Schemas:** Validate request and response data using Pydantic.
- **Services:** Implement business logic and coordinate operations.
- **Repositories:** Encapsulate database queries and persistence.
- **Models:** Define SQLAlchemy database entities and relationships.

AI modules may use agreed service interfaces, but must not bypass the persistence layer by directly writing SQL or creating competing database models.

Keep functions focused and use clear names, type hints, and concise docstrings. Avoid large functions that mix API handling, database operations, LLM calls, and business rules.

Use dependency injection where it improves testing or avoids tightly coupled implementations.

## 6. Developer Ownership and Responsibilities

Two developers share the same repository. Their ownership boundaries must be respected.

### Person 1 — Core Backend and Persistence

Owns:
- Authentication and authorization.
- FastAPI CRUD routers, except shared chat integration.
- Pydantic API schemas.
- SQLAlchemy models and relationships.
- Database repositories and sessions.
- Database migrations.
- Conversation and message persistence.
- User profiles and structured memory persistence.
- Historical fitness records.
- Pending memory update records and transactional confirmation.
- Document metadata and processing status.
- Workout and measurement persistence.
- Core backend API, integration, and database tests.

Primary modules:

```text
backend/app/api/routers/
backend/app/schemas/
backend/app/models/
backend/app/repositories/
backend/app/services/
backend/app/core/security.py
backend/app/core/logging.py
backend/app/db/
backend/migrations/
```

Person 1 owns the authoritative database schema and persistence interfaces.

### Person 2 — AI Engine and Intelligence

Owns:
- LangGraph state, nodes, graph, and conditional routing.
- Groq client integration and prompts.
- RAG document loading, chunking, embeddings, and retrieval.
- ChromaDB operations and vector deletion.
- Curated fitness knowledge ingestion.
- User-uploaded document processing and indexing logic.
- Structured fact extraction and temporal classification.
- Memory change detection and confirmation decisions.
- Historical event preparation.
- BMI, BMR, TDEE, calorie, macro, workout, and progress tools.
- Safety and tool-execution policies.
- AI unit tests and retrieval/memory evaluation.

Primary modules:

```text
backend/app/agent/
backend/app/memory/
backend/app/rag/
backend/app/tools/
backend/app/llm/
backend/app/safety/
backend/tests/unit/
knowledge_base/
scripts/
```

Person 2 owns AI processing and decision logic, not the authoritative database models or persistence implementation.

### Shared Integration Responsibilities

The following files require coordination:

```text
backend/app/main.py
backend/app/api/deps.py
backend/app/api/routers/chat.py
backend/app/services/chat_service.py
backend/app/core/config.py
backend/pyproject.toml
backend/.env.example
backend/tests/end_to_end/
```

The team must agree on shared interfaces before changing these files. Designate one integration owner for each shared-file change to prevent conflicting edits.

Both developers must review changes that affect shared schemas, database contracts, configuration, dependencies, or request/response formats.

## 7. Data and Database Rules

PostgreSQL is the authoritative store for structured user data and persistent conversations.

The database should support:
- User profiles.
- Conversations and messages.
- Current memory records.
- Historical memory and fitness records.
- Pending memory updates.
- Document metadata and ingestion status.
- Workouts and measurements.

ChromaDB stores searchable document chunks and embeddings. It is not the authoritative source for user profiles, conversations, or memory state.

Maintain a reliable mapping between indexed chunks and their source documents so re-ingestion and deletion are possible.

Use SQLAlchemy and Alembic for schema management. Never modify production database schemas manually without an appropriate migration or documented migration process.

Use transactions for operations that update current memory and historical records together.

## 8. Persistent Conversations and Frontend Behavior

The interface should be a simple ChatGPT-inspired chat application adapted to FitAI.

Required behavior:
- Create a new conversation.
- List and reopen previous conversations.
- Persist user and assistant messages.
- Rename and delete conversations.
- Display readable responses, including Markdown.
- Upload documents and display ingestion status.
- View and edit fitness profile information.
- Inspect, correct, and delete saved memories.
- Confirm or reject proposed memory updates.
- View relevant fitness history and progress.

Do not introduce unrelated ChatGPT features such as voice mode, image generation, a plugin marketplace, or a general-purpose GPT builder.

Conversation history and long-term fitness memory are separate. Deleting a conversation must not silently delete the user's fitness profile or historical records.

## 9. RAG and Document Ingestion Rules

Support curated fitness knowledge and authorized user-uploaded documents.

The ingestion workflow is:

**Upload → Validate → Extract text → Chunk → Embed → Store in ChromaDB → Update status**

- Validate file types, size, and access permissions.
- Initially support PDF, TXT, and DOCX where safe parsers are available.
- Preserve source metadata, including document identity and page numbers when available.
- Use the same embedding configuration for indexing and queries.
- Avoid duplicate indexing during retries.
- Handle malformed, empty, and unsupported documents gracefully.
- Track ingestion failures accurately.
- Remove associated vectors when documents are deleted.
- Enforce user-specific access filtering for private documents.

Uploaded documents are untrusted data. Instructions inside documents must never override system policies, permissions, or safety restrictions.

Retrieved content must not be treated as automatically correct. Use relevance and source context to determine whether it supports an answer.

## 10. Memory and Temporal Reasoning Rules

FitAI must distinguish:
- Current facts.
- Historical facts.
- Hypothetical statements.
- Uncertain statements.
- Corrections.
- Conflicting facts.

Every extracted candidate should include appropriate metadata, such as value, timestamp, temporal classification, confidence, and source.

Examples:

- "My current weight is 72 kg." — Candidate current-weight update.
- "I weighed 80 kg last year." — Historical event, not a current-weight update.
- "What if I weighed 70 kg?" — Hypothetical, not a real measurement.
- "I think I might weigh 73 kg." — Uncertain and potentially requiring confirmation.

High confidence alone does not establish truth. Validate units, value ranges, temporal meaning, and contradictions.

Auto-apply only explicit, validated, high-confidence changes permitted by the agreed policy. Propose ambiguous or conflicting updates for confirmation.

The AI engine proposes changes. The persistence layer validates and commits approved changes. Never report success until persistence confirms it.

Preserve historical records instead of overwriting the user's entire fitness journey.

## 11. Fitness Tools

Use deterministic Python functions for numerical operations.

Implement and test:
- BMI.
- BMR using a documented formula.
- TDEE using explicit activity assumptions.
- Configurable calorie targets.
- Macronutrient calculations.
- Workout logging and summaries.
- Personal-record detection.
- Weight trends and progress analysis.

Validate inputs, units, and missing values. Return structured outputs with units and documented assumptions.

Do not rely on LLM arithmetic when a deterministic calculation is available. Do not present estimates as medical measurements or guaranteed outcomes.

## 12. Safety and Privacy

Security and user isolation are mandatory.

- Validate Supabase Auth access tokens on protected backend endpoints.
- Derive user identity from the verified authentication context.
- Never trust a frontend-supplied user ID as proof of ownership.
- Scope every private database query and vector retrieval operation to the authenticated user.
- Keep privileged credentials exclusively on the backend.
- Never commit real secrets or expose credentials in logs.
- Enforce upload limits and safe file handling.
- Handle deletion consistently across PostgreSQL, original-file storage, and ChromaDB.
- Apply safety policies before executing sensitive tools.
- Do not present FitAI as a diagnostic or medical-treatment system.
- Handle emergencies and risky health-related requests conservatively.

Never weaken security checks to make a test pass or simplify a demo.

## 13. Error Handling and Observability

Handle errors explicitly at system boundaries:
- Invalid API inputs.
- Authentication failures.
- Database failures.
- Groq timeouts and rate limits.
- Malformed LLM outputs.
- Empty or failed retrieval.
- Invalid tool inputs.
- Failed document ingestion.
- Interrupted or unsuccessful memory updates.

Return appropriate API status codes and safe error messages.

Log useful operational details such as error categories, latency, and component failures. Avoid logging access tokens, secrets, or unnecessary sensitive fitness and conversation content.

Do not silently swallow exceptions or claim that an operation succeeded when it failed.

## 14. Testing Requirements

Use Pytest for backend tests and Vitest with jsdom for frontend tests.

Tests should cover:
- API validation and error handling.
- Authentication and user isolation.
- Database relationships and persistence.
- Conversation history.
- Memory extraction and temporal classification.
- Memory confirmation and historical preservation.
- Fitness calculations.
- RAG ingestion and retrieval.
- Document ownership and deletion.
- LangGraph routing.
- Safety checks and tool restrictions.
- Frontend chat and profile behavior.
- End-to-end request and response flows.

Mock external LLM calls in unit tests. Do not require live Groq credentials or production Supabase access for ordinary unit tests.

Add regression tests when fixing bugs. Keep tests deterministic and do not weaken assertions just to obtain a passing CI run.

## 15. Configuration and Dependencies

Use environment variables for secrets and deployment-specific settings.

- Keep `.env` files out of Git.
- Maintain `.env.example` with names and safe example values.
- Keep dependency declarations consistent with the project's package configuration.
- Use compatible dependency versions.
- Avoid unnecessary dependencies.
- Do not put server-only secrets in frontend variables.
- Document any new environment variables introduced.
- Keep `requirements.txt` in the repository root only. Do not create separate `requirements.txt` files inside subfolders; backend dependencies are declared authoritatively in `backend/pyproject.toml` and surfaced via the root `requirements.txt`.

The existing `pyproject.toml`, frontend package manifest, and lockfiles should remain the authoritative dependency configuration for their respective tools.

## 16. Git and Commit Practices

**Make frequent, meaningful commits throughout development.**

Every agent and developer must:
- Commit completed, logically related changes regularly.
- Use simple, professional, one-line commit messages.
- Keep each commit focused on one purpose.
- Run relevant tests and checks before committing.
- Inspect the staged diff before every commit.
- Avoid including secrets, local data, generated vector stores, or unrelated files.
- Never commit broken scaffolding or knowingly failing changes without clearly communicating the reason.
- Never rewrite or amend unrelated commits.
- Never force-push or push changes without explicit authorization.
- Commit frequently throughout development, making a commit whenever a small, logically complete unit of work is finished rather than accumulating changes into a few large commits.
- Never push commits to any remote repository under any circumstances. All changes must remain as local commits unless explicitly instructed otherwise by the project owner.

Examples of acceptable commit messages:

```text
feat: add fitness calculation tools
feat: implement memory change detection
feat: add document ingestion pipeline
fix: prevent historical weight overwrite
fix: validate document ownership
test: cover memory confirmation cases
refactor: simplify agent routing
docs: update backend setup instructions
ci: add backend quality checks
chore: update dependencies
```

Avoid vague messages such as `updates`, `changes`, `work`, `final`, or `fixes`.

Before committing, run:

```bash
git status
git diff
git diff --cached
```

Stage only files belonging to the intended change. Keep commits small enough to review and meaningful enough to understand from their history.

## 17. Code Quality Standards

- Prefer readable, straightforward code.
- Follow existing naming conventions.
- Use type hints and concise docstrings.
- Keep functions focused.
- Avoid unnecessary inheritance, abstractions, and design patterns.
- Do not duplicate logic already available in shared modules.
- Avoid circular imports.
- Use explicit error handling.
- Do not introduce placeholder implementations that masquerade as completed features.
- Update tests and documentation when behavior changes.
- Follow established formatting and linting settings.

Before adding a dependency or a new module, check whether the existing stack already provides the required capability.

## 18. CI and Repository Hygiene

Maintain the existing GitHub Actions and Dependabot configuration.

- Backend CI should run the configured lint, format, type-check, and test commands.
- Frontend CI should run dependency installation, type checking, tests, and the production build.
- Dependabot should maintain the package ecosystems actually used.
- Do not disable CI checks to hide implementation failures.
- Keep lockfiles, migrations, tests, and documentation under version control.
- Exclude virtual environments, `node_modules`, local databases, ChromaDB persistence, uploads, secrets, and temporary files from Git.

If configuration changes are required, explain why and coordinate changes that affect both developers.

## 19. Required Development Workflow

Before implementing a task:

1. Read this `AGENTS.md`.
2. Inspect the existing code and relevant tests.
3. Identify the module owner and shared-file dependencies.
4. Confirm existing interfaces before creating alternatives.
5. Make the smallest complete implementation.
6. Add or update relevant tests.
7. Run formatting, linting, type checking, and tests as applicable.
8. Inspect the diff for unintended changes and secrets.
9. Commit the completed work using a clear, one-line message.
10. Report what changed, what was tested, and any unresolved issues.

Do not modify unrelated modules just because they are nearby. Do not replace existing working code without a clear reason.

## 20. Definition of Done

A feature is complete only when:
- Its intended behavior is implemented.
- Inputs and outputs are validated.
- Relevant error cases are handled.
- User data and permissions are protected.
- Tests cover the important success and failure paths.
- Integration contracts remain consistent.
- Documentation is updated where necessary.
- Relevant checks pass.
- Changes are committed with a meaningful message.
- Any limitations or unresolved dependencies are explicitly reported.

**Final principle:** FitAI should be a reliable, context-aware fitness assistant—not merely an LLM wrapper. Prioritize accurate calculations, grounded answers, persistent and correct memory, safe behavior, privacy, maintainable code, and a clear development history.
