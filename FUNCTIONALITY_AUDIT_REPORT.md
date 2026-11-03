# FitAI functionality audit report

Branch: `feat/deployment` · Scope: chat persistence bug fix plus a code-and-test audit of the
application. Evidence is limited to what was actually run (listed in section G). **No real-browser,
authenticated live-API, live-Groq or live-Storage verification was performed.**

## A. Executive summary

* The reported chat bug is fixed and covered by regression tests. Its root cause was a front-end
  data-flow defect; the backend history API was correct, with one latent ordering weakness that was
  also fixed.
* The backend (689 tests passed, 16 skipped) and frontend (316 tests passed) suites are green; lint,
  format, type-check and the production build succeed.
* Everything beyond chat (auth, RAG, memory, workouts, plan, guardrails, LangGraph) was audited by
  reading the code and running the existing automated tests. Those tests pass, but this audit did not
  exercise them against live providers or in a browser, so most rows below are WORKING *per tests* and
  NOT VERIFIED *live*.
* Verdict (section I): healthy by automated evidence; **not yet verified end to end**. Deployment
  should wait for the manual checks in section H.

## B. Chat bug investigation

**Data flow traced:** URL `/chat/:id` → `ChatPage` → `api.listMessages` → `GET
/conversations/{id}/messages` → `ConversationService.list_messages` (ownership check) →
`MessageRepository.list_for_conversation` (ordered, paginated) → `MessageOut` → React state → render.
The backend half was correct: scoped to the authenticated user, 404 for foreign or deleted
conversations, ordered by `created_at, id`, capped at 100 per page.

**Root cause (reproduced).** `frontend/src/pages/ChatPage.tsx` guarded its history effect with
`if (conversationId === lastConversationId.current) return` and used a per-run `cancelled` flag.
`main.tsx` renders under `<StrictMode>`, which in development mounts, unmounts and re-mounts every
component. Run 1 started the request and stored the id in the ref; the simulated unmount cancelled
run 1; run 2 saw "same id as last time" and returned early. Result: one request was made, its result
was discarded, and the page showed nothing. Reproduced against the old code with a StrictMode test:
`listMessages` called once, messages never visible (the new regression test fails on the old file and
passes on the new one). A production build has no double-effect, so this specifically broke
`npm run dev`.

**Contributing defects found while tracing (all fixed):**

| Defect | Effect |
|---|---|
| Messages were not tied to a conversation id, and the previous list stayed on screen during a switch | Stale messages shown while another conversation loaded |
| Late chat reply was appended to whatever conversation was on screen | Cross-conversation leakage when switching during a send |
| Load failure was shown as an empty chat with no retry | Failure indistinguishable from "no messages" |
| History fetched with `limit=100, offset=0` only | Conversations over 100 messages silently truncated |
| Live replies stored tool events under `metadata.activity`, but `MessageBubble` reads `metadata.tool_events` | "Searched the web…" lines vanished until the next reload |
| Assistant reply and user message could share a timestamp (DB default `now()`, coarse on SQLite), leaving order to a random UUID | Reply could sort before its question (reproduced in tests; unlikely on PostgreSQL, but not guaranteed) |
| Sidebar refresh after each send set `loading=true` and overlapping refreshes could land out of order | List flicker; an older response could overwrite a newer list |

**Fix.** `ChatPage` now keeps `{conversationId, items}` together and renders messages only when the id
matches the URL; the effect depends only on the id and each run owns its own cancel flag (so
StrictMode just fetches again); history loads all pages (bounded to 50); loading, error (with Retry)
and not-found ("conversation no longer exists") states are separate from the empty state; a reply is
applied only if the user is still viewing the conversation it belongs to; after a send the thread is
quietly reconciled with the stored messages so ids are the real ones. The database remains the source
of truth (nothing is persisted in `localStorage`). On the backend, `MessageRepository.create` assigns
`created_at` strictly increasing within a conversation. No schema change or migration.

## C. Chat regression test results

Automated, with the API mocked on the frontend and the real services plus an in-memory database on
the backend. **No real browser or live Supabase database was used.**

| # | Scenario | Result | Where |
|---|---|---|---|
| 1 | Create conversation, send several messages | PASSED | `test_chat_turns_are_persisted_in_order_and_reloadable` (backend); "creates a conversation…" (frontend) |
| 2-3 | Refresh restores the same conversation and messages | PASSED | "loads persisted history when opened directly", StrictMode variant |
| 4-6 | Open another, return: original messages restored, no leakage | PASSED | "restores the first conversation after visiting another", "never shows the previous conversation…" |
| 7-8 | Rapid switching; slow stale response cannot overwrite | PASSED | "survives rapid switching", "ignores a slow response for a conversation the user already left" |
| 9 | Second browser tab | NOT RUN (a tab is a fresh page load, i.e. scenario 2; no browser available) | n/a |
| 10 | Ownership and authentication isolation | PASSED | `test_another_user_cannot_read_or_write_a_conversation` |
| 11 | History API failure shows error and Retry | PASSED | "shows a recoverable error…", not-found variant |
| 12 | Streaming persistence | NOT APPLICABLE: the chat endpoint is a single request/response, not streamed. Persistence of the completed turn is covered by scenario 1, and a failed provider turn by `test_failed_chat_turn_does_not_corrupt_existing_history` (PASSED) |
| 13 | New conversation works after refresh | PASSED (create, then reload through the history endpoint) |
| 14 | Deleted conversation cannot be loaded | PASSED | `test_deleted_conversation_cannot_be_loaded…`, not-found UI test |
| + | Long conversation (130 messages) fully loaded | PASSED | "reads every page of a long conversation" |
| + | Pagination covers the whole conversation; stable ids | PASSED | `test_history_pages_cover_the_whole_conversation` |

## D. Functionality matrix

"Per tests" means the existing automated tests pass and the code was read; it does not mean the
feature was used live.

| Feature | Frontend | Backend | Database / persistence | Evidence | Overall |
|---|---|---|---|---|---|
| Sign-in / sign-up / sign-out | not browser-tested | JWKS verification tested (`test_security`, `test_auth`) | user row provisioned from token | unit/API tests | WORKING per tests; live NOT VERIFIED |
| Protected routes, session expiry (401 → sign out) | code read | `401` tested for all routers | n/a | tests; all non-public routes require `CurrentUser` (only `/v1/models` and `/plan/templates` are public by design) | WORKING per tests |
| Profile read/update, isolation | component tests | `test_profile` | yes | tests | WORKING per tests |
| Conversation create / list | `useConversations` tests | `test_conversations` | yes | tests | WORKING |
| **Chat history, refresh, switching** | **fixed** | correct | correct | section C | **WORKING (fixed), browser NOT VERIFIED** |
| Rename / delete | hook tests | API tests | cascade delete of messages | tests | WORKING per tests |
| Chat search | title filter only (client side); message-content search is not implemented | n/a | n/a | code | PARTIALLY WORKING (by design) |
| Streaming | none: single request with a 120 s timeout and a "Thinking…" indicator | n/a | n/a | code | NOT IMPLEMENTED |
| Citations / sources / tool events | rendering fixed for live replies | stored in `metadata` | yes | tests | WORKING per tests |
| LangGraph routing | n/a | graph read: safety → (extract/detect/apply) → retrieve → generate, blocked turns reach only `safe_response` | n/a | agent unit tests pass | WORKING per tests; live Groq NOT VERIFIED |
| Groq client, timeout, retry | n/a | client retries (a 429 followed by a retry was observed once, see H) | n/a | observed once | NOT VERIFIED |
| RAG: upload, extract, chunk, embed, retrieve, delete | upload UI tests | documents/lifecycle/vector tests | pgvector parity tests **skipped** (need `TEST_PGVECTOR_URL`) | tests | WORKING per tests; pgvector and Storage NOT VERIFIED |
| Memory extraction, confirmation, isolation | `MemoryPage` tests | memory/intelligence tests | yes | tests | WORKING per tests |
| Workouts, measurements, plan, progress | page tests | API tests incl. isolation | yes | tests | WORKING per tests |
| Guardrails / prompt guard | n/a | guardrail tests (classifier offline) | n/a | tests | WORKING per tests; live classifier NOT VERIFIED |
| Dictation (Web Speech) | mocked-API tests | none needed | none | tests | WORKING per tests; real microphone verified by the user |
| Migrations / startup against Supabase | n/a | backend started against the user's database ("Application startup complete", schema at head) | yes | run in this session | WORKING |
| Browser console / network audit | NOT RUN | n/a | n/a | no browser tool available | NOT VERIFIED |

## E. Issues discovered

| Severity | Issue | Status |
|---|---|---|
| High | History not loading on refresh in dev (StrictMode) | Fixed |
| Medium | Stale or late replies leaking into the wrong conversation | Fixed |
| Medium | Conversations over 100 messages truncated | Fixed |
| Medium | Load failure indistinguishable from empty; no retry | Fixed |
| Medium | Message ordering could tie (reply before question) | Fixed |
| Low | Live vs reloaded rendering differed for tool events | Fixed |
| Low | Sidebar flicker and out-of-order refresh | Fixed |
| Low | Pre-existing lint warnings (`set-state-in-effect`, `only-export-components`) | Not changed |
| Low | `mypy app` reports 39 errors in files I did not touch (not part of CI) | Not changed |
| Info | `docs/` is gitignored, so edits to `docs/*.md` are not tracked | Not changed |
| Info | Search covers conversation titles only | Documented |

No critical defects were found. No secrets were found in tracked files in the areas inspected; this
was not a full repository secret scan (the CI secret-scan workflow was not run).

## F. Changes made

Modified: `frontend/src/pages/ChatPage.tsx` (rewrite of the load/send state handling),
`frontend/src/pages/ChatPage.test.tsx` (rewritten, 15 tests), `frontend/src/hooks/useConversations.ts`
and its test (refresh race guard, no list blanking), `frontend/src/App.css` (loading/retry styles),
`backend/app/repositories/conversation_repository.py` (monotonic `created_at`).
Created: `backend/tests/api/test_chat_history_persistence.py` (7 tests), this report.
Removed: nothing.

Commits (author `prnvvv`, no co-author trailers, nothing pushed):
`0bbdd0c`, `eca5805`, `c88d13b`, `cbce7cb`, plus the commit containing this report.

## G. Test results

| Check | Command | Result |
|---|---|---|
| Frontend tests | `npx vitest run` | PASSED: 29 files, 316 tests |
| Frontend types | `npm run type-check` | PASSED |
| Frontend lint | `npm run lint` | PASSED with pre-existing warnings (two `set-state-in-effect` warnings remain in the files I changed, same kind as before) |
| Frontend build | `npm run build` | PASSED |
| Backend tests | `python -m pytest tests` | PASSED: 689 passed, 16 skipped |
| Backend lint/format | `ruff check app tests`, `ruff format --check app tests` | PASSED |
| Regression test fails on old code | old `ChatPage.tsx` against the new tests | CONFIRMED: 8 of the 15 new `ChatPage` tests fail on the pre-fix file, including the StrictMode refresh test |
| Backend startup | `uvicorn app.main:app` against the Supabase database | PASSED (earlier in this session) |
| Playwright / real browser | not installed | NOT RUN |
| GitHub Actions workflows | not run locally; their commands (`ruff`, `pytest`, `npm run lint/type-check/test/build`) were run directly | NOT RUN as workflows |
| Skipped | 16 backend tests (pgvector integration and parity, need a pgvector `TEST_PGVECTOR_URL`) | SKIPPED |

## H. Remaining issues requiring manual verification

1. Reload and switch conversations in `npm run dev` and a production build, in a real browser.
2. Authenticated end-to-end run against the running backend and Supabase (needs a real session).
3. Real Groq chat, memory extraction and prompt guard. During this audit one of my early test runs
   reached the live Groq API through the prompt guard with the key in `backend/.env` (it received a 429
   and a retry); I then disabled the guard in those tests. I did not audit whether other existing tests
   can do the same when a key is present.
4. pgvector, Supabase Storage uploads and `sb_secret_` key behaviour, as noted earlier.
5. Browser console and network error review, responsive layouts, modals, forms.

## I. Final verdict

The chat persistence bug is fixed and well covered by automated tests, and no regression showed up in
the full backend and frontend suites. FitAI is **functionally healthy by automated evidence**, but it
has not been verified end to end in a browser or against live providers, so it should not be treated as
deployment-ready until the checks in section H pass.
