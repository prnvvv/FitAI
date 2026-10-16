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
AGENT_ACTIVITY_EXTRACTION=true   # master switch for the extraction step
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

## Durable memory intelligence (`memory_insights`)

Preferences, recurring routines, habits, skills, ongoing projects, decisions and
other stable personal context are extracted as `memory_insight` candidates. The
LLM only *proposes* them; `app/extraction/reconciliation.py` decides what is
actually stored:

| candidate classification            | outcome |
|-------------------------------------|---------|
| new, explicit, durable              | `create` — one live record with a stable `insight:<hash>` key |
| same fact restated / paraphrase     | `retain` — only evidence + timestamp refresh, no second record |
| explicit correction ("no longer …")| `update` — previous fact moves to `memory_insight_history` as `superseded` |
| contradiction without a retraction  | `confirm` — stored flagged, never asserted as current |
| hedged ("I think …") / low confidence | `confirm` or skipped |
| hypothetical or planned             | `ignore` — never becomes a confirmed preference or a workout |
| historical ("used to …")            | stored with `status: historical`, never presented as current |

Deduplication uses token signatures plus a blended Jaccard/containment score, not
exact string equality, and an older statement never overwrites a newer one.

### Cross-chat retrieval

Preferences and confirmed insights are stored on the profile and surfaced into
the agent's context via `_ProfileReaderAdapter` (`interests`, `profile_notes`,
`known_facts`), bounded to the newest few confirmed facts. When continuity is
enabled they are also indexed into the derived ChromaDB continuity index under
`insight:<key>`, which `ContinuityStore.sync_memories` prunes on every turn, so a
deleted or superseded fact stops being recalled and can never override the
authoritative PostgreSQL rows. Questions about the
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
pagination over conversations/messages) and checkpointed: every processed message
records a durable activity event (`entity_type="message"`, `source="backfill"`),
so an interrupted run resumes without re-extracting (or re-paying for) messages it
already handled. Even without checkpoints it stays idempotent, because the same
dedup and reconciliation rules as live processing apply. Statements keep their
original message timestamps, so processing old messages later never overwrites a
newer fact. Each user's data is strictly isolated.

## Tests

- `tests/unit/extraction/test_extractor.py` — validation, provider/malformed
  failure handling, no phantom success.
- `tests/integration/extraction/test_persistence.py` — routing to the correct
  tables, dedup/idempotency, failed-write reporting, user isolation.
- `tests/integration/extraction/test_backfill.py` — backfill dedup, bounding,
  isolation, failure containment.
- `tests/unit/extraction/test_reconciliation.py` — create/retain/update/confirm/
  ignore rules, corrections vs history, hypothetical and low-confidence handling.
- `tests/unit/extraction/test_extraction_client_isolation.py` — independent keys
  and models, no fallback to the primary key, extraction safely disabled.
- `tests/integration/extraction/test_insight_persistence.py` — authoritative
  destination, dedup, corrections, deletions, isolation, injection rejection.
- `tests/api/test_chat_extraction.py` — end-to-end cycling example (durable
  workout + separate preference, cross-chat retrieval, retry idempotency).
- `tests/api/test_memory_intelligence.py` — fact extracted in one conversation is
  retrieved (and reaches the primary LLM) in another; hypothetical, historical,
  repetition, deletion, cross-user and routing behaviour.
- `tests/unit/agent/test_nodes.py` — personal-data questions answered from
  persisted data, not web search.
