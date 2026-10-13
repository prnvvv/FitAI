# FitAI Unit Tests

Tests are organized to mirror the `app/` module layout (one test file per
production module).

## Person 1 (backend / persistence)

- `test_config.py` — settings parsing and derived properties.
- `test_security.py` — Supabase token verification (symmetric mode).
- `test_memory_validation.py` — structured memory value validation.

These run against an in-memory SQLite database via `tests/conftest.py` and
require no live credentials.

## Person 2 (AI engine)

- `agent/`, `llm/`, `memory/`, `rag/`, `safety/`, `tools/` — unit tests for the
  agent graph, LLM client, memory extraction/confirmation, RAG pipeline, safety
  guardrails, and fitness calculations.

External services (Groq, ChromaDB, databases) are mocked so unit tests do not
require live credentials.

Run the suite from the `backend/` directory with:

```bash
python -m pytest tests/unit -v
```