# FitAI API Contracts

This document records the stable HTTP contracts exposed by the backend and the
shared service interfaces between Person 1 (core backend / persistence) and
Person 2 (AI engine). It is a coordination document, not generated OpenAPI
documentation (see `/docs` when running the server).

## 1. Conventions

- All versioned endpoints are prefixed with `/api/v1` (`API_V1_PREFIX`).
- List endpoints return a pagination envelope:

  ```json
  { "items": [], "total": 0, "limit": 20, "offset": 0 }
  ```

  `limit` defaults to 20 and is clamped to 1..100; `offset` starts at 0.
- Errors always use this body:

  ```json
  {
    "error": {
      "code": "RESOURCE_NOT_FOUND",
      "message": "Human-readable message.",
      "details": {}
    }
  }
  ```

- Status codes: `401` unauthenticated, `403` permission denied, `404` not
  found (also used to hide resources owned by another user), `409` conflict,
  `413` payload too large, `415` unsupported media type, `422` validation
  error, `503` unavailable dependency.
- Every authenticated endpoint derives the user identity exclusively from the
  verified bearer token. A frontend-supplied user id is never trusted.
- `error.code` values: `UNAUTHENTICATED`, `PERMISSION_DENIED`,
  `RESOURCE_NOT_FOUND`, `CONFLICT`, `VALIDATION_ERROR`, `PAYLOAD_TOO_LARGE`,
  `UNSUPPORTED_MEDIA_TYPE`, `SERVICE_UNAVAILABLE`, `INTERNAL_ERROR`.

## 2. Health (Person 1)

| Method | Path            | Purpose                                  |
| ------ | --------------- | ---------------------------------------- |
| GET    | `/health`       | Liveness probe (no dependency checks).   |
| GET    | `/health/ready` | Readiness; checks the database with `SELECT 1` and returns 503 on failure. |

## 3. Auth (Person 1)

| Method | Path         | Description                                        |
| ------ | ------------ | -------------------------------------------------- |
| GET    | `/auth/me`   | Returns the identity derived from the bearer token. |

Response: `{ "id": "<supabase sub>", "email": "...", "created_at": "..." }`.

The request provisions the local user row once (id = Supabase `sub`).

## 4. Conversations (Person 1)

| Method   | Path                                    | Description                              |
| -------- | --------------------------------------- | ---------------------------------------- |
| POST     | `/conversations`                        | Create (201). Body: `{ "title": "..." }`. |
| GET      | `/conversations`                        | List, newest first.                      |
| GET      | `/conversations/{id}`                   | Get one.                                 |
| PATCH    | `/conversations/{id}`                   | Rename. Body: `{ "title": "..." }`.      |
| DELETE   | `/conversations/{id}`                   | Delete conversation and its messages (204). |
| GET      | `/conversations/{id}/messages`          | Chronological messages.                  |

Deleting a conversation never affects the profile, memory, measurements, or
workouts.

## 5. Profile (Person 1)

| Method | Path            | Description                                        |
| ------ | --------------- | -------------------------------------------------- |
| GET    | `/profile`      | 404 until created.                                 |
| PUT    | `/profile`      | Create or fully replace (omitted fields cleared).  |
| PATCH  | `/profile`      | Partial update (only supplied fields change).      |

Writable fields: `date_of_birth`, `height_cm`, `weight_kg`, `goal`,
`activity_level` (`sedentary`/`light`/`moderate`/`active`/`very_active`),
`dietary_preferences`, `dietary_restrictions`, `supplements`, `preferences`.

`age` is a computed, read-only field derived from `date_of_birth`; it is never
stored. Profile `weight_kg` is the stated current weight; dated history lives in
measurements.

## 6. Memory (Person 1 owns persistence; Person 2 proposes changes)

| Method  | Path                              | Description                                          |
| ------- | --------------------------------- | ---------------------------------------------------- |
| GET     | `/memory`                         | Current active facts.                                |
| GET     | `/memory/history`                 | Immutable change history, newest first.              |
| GET     | `/memory/pending`                 | Proposals, filterable by `?status=pending`.          |
| POST    | `/memory/pending/{id}/confirm`    | Apply a proposal atomically; 409 if duplicate/stale. |
| POST    | `/memory/pending/{id}/reject`     | Reject; current memory untouched.                    |
| PATCH   | `/memory/{id}`                    | User correction (current + history in one transaction). |
| DELETE  | `/memory/{id}`                    | Soft delete preserving history (204).                |

Current facts live in `memories` (at most one **active** row per user/key).
Every applied change appends to `memory_history` in the same transaction.

### 6.1 Shared interface for Person 2 (proposals)

`MemoryService.create_proposal(user_id, key, proposed_value, *, confidence,
source, reason)` — validates and snapshots the current value; current memory is
not touched until confirmation. `Documented exact per-key value shapes are
**provisional** and must be confirmed with Person 2 before freezing (see
`app/services/memory_validation.py`).

`MemoryKey` taxonomy (provisional): `weight`, `height`, `goal`,
`dietary_preferences`, `dietary_restrictions`, `activity_level`,
`supplements`, `experience_level`, `workout_frequency`.

## 7. Documents (Person 1 owns metadata/status; Person 2 owns ingestion)

| Method | Path                     | Description                                                |
| ------ | ------------------------ | ---------------------------------------------------------- |
| POST   | `/documents`             | Upload (multipart `file`); 201 with status `pending`.      |
| GET    | `/documents`             | List metadata, newest first.                               |
| GET    | `/documents/{id}`        | Get metadata.                                              |
| POST   | `/documents/{id}/retry`  | Re-run ingestion on the same row and stored file.          |
| DELETE | `/documents/{id}`        | Delete metadata + stored file + vectors (204).             |

Upload validation: PDF/TXT/MD/DOCX/PNG/JPG/JPEG/WEBP by extension **and**
magic bytes; `MAX_UPLOAD_SIZE_MB` enforced while streaming; empty files
rejected. Identical bytes uploaded twice return the existing item with 200 and
`X-Duplicate: true`.

Status vocabulary: `pending` → `processing` → `indexed`, or `failed`.
`DocumentService.mark_status(user_id, document_id, status, error_message=...,
note=...)` is the shared transition entry point for Person 2. `DocumentOut`
carries `failure_reason` (never a traceback) and `note`, which is set when a
file was read but held no indexable text (for example a photo of a wall); such a
document is `indexed` with zero chunks, not a failure.

At startup, rows left `pending`/`processing` longer than 30 minutes become
`failed` with a retry hint (`reconcile_stuck_documents`). Retry re-runs
ingestion on the same row; it never creates a second row.

Images are read through the provider chain in `VISION_PROVIDER_ORDER`
(`groq` vision first, then local `rapidocr`). The Groq key is read from
application settings, so a `.env` file is honoured. An oversized file, an
unreadable file or an image with no text is reported with a short, human
reason; the full cause is logged server-side with `exc_info`.

Storage backend default is `unconfigured` (uploads fail with 503) until the
owner approves a target; `local` and `supabase` (not yet implemented) exist.
ChromaDB vector deletion is Person 2's responsibility and is not performed here.

## 8. Workouts and Progress (Person 1 owns persistence; Person 2 owns analysis)

| Method | Path                         | Description                                  |
| ------ | ---------------------------- | -------------------------------------------- |
| POST   | `/workouts`                  | Record session + sets (201).                 |
| GET    | `/workouts`                  | List sessions, newest first.                 |
| GET    | `/workouts/{id}`             | Get session with sets.                       |
| DELETE | `/workouts/{id}`             | Delete session + sets (204).                 |
| POST   | `/progress/measurements`     | Append-only measurement (never overwrites).  |
| GET    | `/progress/measurements`     | List, filter `?type=weight`.                 |
| GET    | `/progress/weight`           | Chronological weight series.                 |
| GET    | `/progress/records`          | Heaviest recorded load per exercise (descriptive). |

Set payloads validate `weight_unit` when `weight` is present. Measurement
units are validated per type (e.g. `kg`/`lb` for weight, `%` for body fat,
`cm`/`in` for circumferences).

Advanced trend analysis, PR *detection*, and fitness intelligence are owned by
Person 2 and consume these persisted records.

## 9. Person 2 owned endpoints (reserved)

`POST /api/v1/chat` and related chat routes are currently **not implemented**
(Person 2). `app/api/routers/chat.py` and `app/services/chat_service.py` are
placeholders; the router must be registered in the marked section of
`app/main.py` and may reuse `ConversationService.add_message(...)` for message
persistence.