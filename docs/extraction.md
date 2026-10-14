# Structured activity & memory extraction

FitAI extracts durable, structured facts from the chat and persists them to the
authoritative PostgreSQL store, then retrieves them in later conversations so
answers stay grounded in the user's own data (not web noise or invented history).

## Configuration

The dedicated extraction LLM is separate from the primary assistant and has its
own key/model. Configure it with environment variables (see `backend/.env.example`):

```
GROQ_EXTRACTION_API_KEY=...      # optional; when unset extraction is disabled and chat is unaffected
GROQ_EXTRACTION_MODEL=openai/gpt-oss-20b
```

- When `GROQ_EXTRACTION_API_KEY` is empty, `settings.extraction_enabled` is
  `False`: the extractor is not built, extraction never runs, and the normal
  chat response is produced with no false "recorded" claims.
- The primary assistant keeps using `GROQ_API_KEY` / `GROQ_MODEL`. The
  extractor never answers the user; it only classifies candidates.

## Pipeline

```
user message
  -> ChatService._extract_and_persist            (backend only)
       -> RecordExtractor.extract()              (dedicated Groq model, JSON, Pydantic-validated)
       -> ExtractionPersister.persist()          (routes to the correct service + dedups + commits)
  -> durable records saved
  -> a truthful confirmation is appended ONLY after the DB confirms the write
```

Candidate → destination:

| candidate         | service                       | table                        |
|-------------------|-------------------------------|------------------------------|
| completed_workout | `WorkoutService`              | `workout_sessions`           |
| planned_workout   | `PlanService`                 | `planned_sessions`           |
| progress_record   | `WorkoutService.create_measurement` | `measurements`         |
| user_preference   | `ProfileService`              | `user_profiles.preferences.interests` |
| profile_fact      | `ProfileService`              | `user_profiles.preferences.profile_notes` |
| fitness_goal      | existing LangGraph memory confirmation workflow (not persisted twice here) |

Guarantees:
- **No false success.** A record is only reported `saved` after the owning
  service commits; a failed write is reported as `failed`, never as success.
- **Idempotency.** Re-processing the same message yields `duplicate`, not a
  second row (completed workouts dedup on same-day activity + duration;
  measurements on same-day type/value; preferences on exact text).
- **Total containment.** An extractor/provider/DB failure never breaks the chat
  response and never fabricates facts.

## Cross-chat retrieval

Preferences are stored on the profile and surfaced into the agent's context via
`_ProfileReaderAdapter` (`interests`, `profile_notes`). Questions about the
user's own data ("What do I like to do every day?") are answered from that
persisted context — live web search is intentionally suppressed for them
(`wants_personal_data_answer`) so the grounded preference isn't drowned out by
web results. Workout/progress questions use the real `WorkoutService` records via
`_FitnessReaderAdapter`.

## Backfilling historical conversations

Existing chat history can be re-processed on demand (never automatically on
chat or startup):

```
cd backend
./.venv/Scripts/python.exe -m app.extraction.backfill --max 400          # all users
./.venv/Scripts/python.exe -m app.extraction.backfill --user <uuid>      # one user
```

The backfill is bounded (a maximum number of messages per user per run, with
pagination over conversations/messages) and idempotent (the same dedup rules as
live processing), so it is safe to run repeatedly and to resume in batches. Each
user's data is strictly isolated.

## Tests

- `tests/unit/extraction/test_extractor.py` — validation, provider/malformed
  failure handling, no phantom success.
- `tests/integration/extraction/test_persistence.py` — routing to the correct
  tables, dedup/idempotency, failed-write reporting, user isolation.
- `tests/integration/extraction/test_backfill.py` — backfill dedup, bounding,
  isolation, failure containment.
- `tests/api/test_chat_extraction.py` — end-to-end cycling example (durable
  workout + separate preference, cross-chat retrieval, retry idempotency).
- `tests/unit/agent/test_nodes.py` — personal-data questions answered from
  persisted data, not web search.
