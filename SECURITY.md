# Security Policy

FitAI is a domain-specific agentic RAG assistant for gym-goers, fitness
enthusiasts, and nutrition-conscious users. It stores personal fitness data
(profile, workouts, measurements, progress, chat history, and long-term memory)
and it calls an external LLM provider. Both facts raise the bar for security
review, so this document describes what is in scope, what maintainers expect
from contributors, and how to report a problem privately.

## Supported versions

FitAI is pre-alpha software maintained on a rolling basis on the default branch
(`main`). Fixes land on `main` first and are then picked up by the feature
branches; there is no long-term-support or release-tagging schedule yet.

| Version | Supported |
| ------- | --------- |
| `main` (latest commit) | Yes |
| Any older commit or unmerged branch | No |

Older commits are not patched retroactively. If you are running a fork or an
older snapshot, update to the current `main` and re-test before reporting
against that older code.

## Reporting a vulnerability

**Do not open a public issue, discussion, or pull request for a security
problem.**

Use **GitHub Security Advisories** ("Report a vulnerability" on the
repository's Security tab) to submit a report privately:
<https://github.com/prnvvv/FitAI/security/advisories/new>

Private advisory reporting keeps the conversation between the reporter and the
maintainers; only they can see it until a fix exists. If you cannot use that
channel, contact the maintainers through a private channel on GitHub rather than
a public tracker.

A useful report includes:

- **Affected component** — endpoint or route, module path, or frontend area.
- **Reproduction steps** — the smallest sequence of requests or UI actions that
  demonstrates the issue. Say which environment (local, preview, production)
  it was reproduced in.
- **Impact** — what an attacker gains: another user's data, an unapproved
  memory write, credential disclosure, availability loss, and so on.
- **Evidence** — request/response pairs, logs, or screenshots with access
  tokens, API keys, personal data, and passwords redacted.
- **Your assessment** — severity and any suggested mitigation.

Please keep the report private and allow maintainers a reasonable opportunity to
investigate and ship a fix before disclosing publicly. Do not access, modify,
or exfiltrate data beyond what is needed to demonstrate the problem, do not
degrade the service for other users, and do not run automated scanners against
the deployed environment.

Maintainers do not commit to a specific response or fix window in this document.
Reports are triaged in the order they arrive, with confirmed issues prioritized
over reports that cannot be reproduced.

## Scope

The following are in scope. They reflect what FitAI actually runs today.

### Backend API and authorization
- `backend/app/api/routers/` — every FastAPI route, request validation, and
  status-code handling.
- `backend/app/api/deps.py` and `backend/app/core/security.py` — Supabase access
  token verification, user identity derivation, and the authorization
  dependencies that protect private routes.
- Missing or bypassable authorization, IDOR, privilege escalation between users,
  and authentication failures that are silently treated as anonymous.

### Frontend
- `frontend/src/` — React 19 + TypeScript views, hooks, services, and state.
- Storing or leaking tokens or private responses in browser storage, missing
  route protection, and unsafe rendering of untrusted content (`dangerouslySet`
  style usage, unsanitized HTML, unsafe Markdown rendering of model output).

### Authentication and sessions
- Supabase Auth token verification: algorithm confusion, audience/issuer
  checks, JWKS handling, expired or revoked tokens, and any path where identity
  is taken from a client-supplied value instead of the verified token.

### Database and user isolation
- PostgreSQL via SQLAlchemy and Alembic: raw SQL string interpolation, missing
  `user_id` scoping on reads, writes, or deletes, cross-tenant conversation or
  document access, and migration safety.
- ChromaDB vector retrieval must be filtered by owner so one user cannot
  retrieve another user's chunks.

### External model integration
- `backend/app/llm/` and `backend/app/guardrails/` — Groq client
  configuration, key handling, model allow-lists, timeouts, and rate-limit
  behavior.
- `PROMPT_GUARD_API_KEY`, `GROQ_API_KEY`, and `GROQ_EXTRACTION_API_KEY` must
  stay backend-only. Leaking them to the browser, logs, error responses, or
  prompts is in scope.

### Memory intelligence
- `backend/app/memory/` — fact extraction, temporal classification, change
  detection, and the confirmation flow for current versus historical facts.
- Unauthorized modification of another user's memory, silent overwriting of a
  current fact with a historical or hypothetical statement, and any path that
  reports a write as persisted when persistence failed.

### RAG, ingestion, and retrieval
- `backend/app/rag/` and document routers — upload validation (type, size,
  extension), text extraction from PDF/TXT/DOCX/images, chunking, embedding,
  indexing, and deletion.
- Stored XSS through Markdown rendering, path traversal in filenames or storage
  paths, unbounded resource use from a malicious document, and duplicate or
  orphaned vectors after a deletion.

### Agent tools, safety, and untrusted model output
- `backend/app/tools/`, `backend/app/agent/`, and `backend/app/safety/` —
  BMI/BMR/TDEE, calorie and macro calculations, workout logging, progress
  analysis, web fetch/search tools, and the guardrail decision path.
- Missing input validation on tool arguments, calculations presented as
  measurements, unsafe web fetches (SSRF against internal addresses), or tool
  execution that runs before the safety gate.

### User data at rest
- Workouts, measurements, profile fields, generated plans, chat history, and
  the long-term memory store — deletion behavior, isolation, and accidental
  inclusion in exports, logs, or telemetry.

### Supply chain and infrastructure
- `backend/pyproject.toml`, root `requirements.txt`, `frontend/package.json` and
  its lockfile, `.github/workflows/`, `.github/dependabot.yml`, any Dockerfiles
  or deployment configuration, and committed files that could contain secrets.

### Out of scope
- Vulnerabilities in third-party services that FitAI does not configure
  (Supabase, Groq, ChromaDB, GitHub), unless FitAI's use of them is the cause.
- Reports generated only by automated scanners with no demonstrated impact, and
  findings against unmerged branches or the reporter's own deployment.
- Denial of service against a developer's local machine.
- Missing hardening headers or rate limits with no practical impact.

## Security expectations

These are the rules contributors and reviewers are expected to uphold.

### Secrets and credentials
- Secrets live only in the backend environment. Never in the frontend, never in
  git, never in logs, tests, or fixtures.
- `backend/.env.example` and `frontend/.env.example` document variable names
  with safe placeholder values only. `.env` files are ignored by `.gitignore`.
- Prefer `*_API_KEY` variables with narrow scopes and separate keys for separate
  jobs (chat, extraction, guard). A key that is ever printed, committed, pasted
  into a transcript, or sent to an untrusted service must be treated as
  compromised: revoke it, issue a new one, and update the deployment
  environment.
- Rotate credentials when a maintainer, a log sink, a CI job, or a third party
  may have seen them. Rotation means revoking the old key at the provider, not
  just changing the value in a config file.

### Authentication and authorization
- Validate Supabase access tokens on every protected route and derive the user
  identity from the verified token, never from a client-supplied user ID.
- Scope every database query, vector retrieval, and file access to the
  authenticated user. Ownership checks belong in the service or repository
  layer, not only in the router.
- Do not weaken or bypass security checks to make a test or demo pass.

### Input validation and structured output
- Validate and bound every external input at the schema boundary: sizes,
  ranges, units, allowed values, and enum membership.
- Treat LLM output as untrusted. Parse it into explicit schemas, reject
  malformed or unexpected shapes, and never pass model-produced strings to a
  query, a file path, a shell, or an eval.
- Keep numerical fitness results in deterministic Python tools rather than
  model arithmetic.

### Untrusted content and prompt injection
- User messages, uploaded documents, and retrieved chunks are data, never
  instructions. Instructions inside a document must not change system policy,
  permissions, or safety rules.
- FitAI runs a deterministic rule set plus an optional LLM intent classifier
  before model or tool calls. New call paths must pass through the same gate.
- Retrieved content supports an answer; it does not by itself make an answer
  correct. Relevance and source context decide whether it is used.
- Restrict model capabilities: bounded tool budgets, timeouts on every
  extraction or fetch call, and allow-lists of models and web providers.

### Data isolation and storage
- Parameterize all database access through SQLAlchemy; no string-built SQL with
  user input.
- Validate uploads for type, size, and count, generate server-side storage
  names, and keep originals outside the web root.
- Keep ChromaDB deletion consistent with PostgreSQL and file storage so a
  deleted document leaves no readable chunks behind.

### Logging and error handling
- Log error categories, latency, and component failures. Do not log access
  tokens, API keys, full prompt bodies, or unnecessary fitness and conversation
  content.
- Return safe, generic error messages to clients; keep details in server-side
  logs.
- Never swallow exceptions or report success for an operation that failed,
  including memory writes.
- Configuration defaults must be safe: telemetry off, debug and verbose model
  output off, and no permissive CORS wildcard in production settings.

### Dependencies and CI
- Add no dependency without checking whether the existing stack already covers
  the need, and keep `pyproject.toml`, the lockfile, and `requirements.txt`
  consistent.
- CI workflows run with `permissions: contents: read`, pin third-party actions
  to commit SHAs, cache only by lockfile or manifest, and inject no production
  secrets into pull-request runs.
- Report vulnerabilities in dependencies upstream where appropriate, and use
  Dependabot updates to keep the Python, Node.js, and Actions sets current.

## AI-specific risks

FitAI's agent reads user messages, documents, and its own memory, then calls an
LLM that can call tools and write to the database. That combination creates
risks that do not exist in a conventional CRUD application. None of them can be
eliminated completely; they are managed with layers.

**Direct prompt injection.** A user message instructs the model to ignore its
system policy, reveal its instructions, or act outside the fitness domain.
Defense in depth: a deterministic refusal rule set runs first, an optional
classifier model scores the message, refusals short-circuit before any model or
tool call, and tool permissions are fixed in code rather than requested by the
model. Residual risk: a sufficiently obfuscated injection may pass these gates,
so post-generation safety checks and user-visible confirmation remain necessary.

**Indirect prompt injection.** Instructions are hidden in an uploaded document
or in a retrieved chunk instead of the chat. The same gate runs on retrieved
content, chunks carry source and owner metadata, and retrieval is filtered per
user, but content that is retrieved *because* it matched is still attacker
text. Treat every chunk as data.

**Unauthorized memory modification.** An injected turn tries to make the
extraction step rewrite the user's memory: change a current fact, insert a
false historical record, or attribute a statement to the user. Defense in
depth: temporal classification separates current, historical, hypothetical, and
uncertain statements; units and ranges are validated; ambiguity and conflicts
produce a confirmation proposal rather than an automatic write; and persistence
validates and commits only what was approved. A write is never reported as
saved unless the database confirmed it.

**Cross-user memory and data leakage.** Retrieval or memory reads that miss the
owner filter would expose one user's workouts, measurements, or stored facts.
Defense in depth: identity derived from the verified token, `user_id` scoping in
every query and vector filter, and API tests covering isolation.

**Unsafe tool arguments.** Model-produced tool calls may carry out-of-range
numbers, wrong units, or unexpected shapes. Tools validate inputs, units, and
missing values, return structured output with units and documented assumptions,
and are budget-limited per turn.

**Fabricated persistence confirmations.** The model may claim a workout was
logged or a memory was updated when nothing was written. Only the persistence
layer may report success, and failures surface as errors instead of confident
prose.

**Unsafe fitness or nutrition advice.** The assistant gives general guidance and
is not a diagnostic or medical system. It must not present estimates as
measurements, must not promise outcomes, and must route injury, medication, and
emergency questions to professional care.

**Disclosure of prompts or credentials.** System prompts, guard configuration,
and API keys must never appear in responses or logs. Keys stay server-side, and
configuration probes receive a generic non-revealing answer.

## Incident response

When a vulnerability is confirmed, maintainers follow this path.

1. **Triage.** Confirm the report, identify the affected component and version,
   and classify severity by impact: cross-user data access, unauthorized writes,
   credential exposure, or availability.
2. **Reproduce.** Build a minimal offline reproduction — a failing test is
   preferred, because it doubles as the regression test. Do not use production
   data or production credentials.
3. **Contain.** If credentials were exposed, revoke and rotate them at the
   provider first (Groq, Supabase, and any other involved service) before the
   code fix. Removing a value from the working tree is not containment: if it
   ever entered git history, logs, a transcript, or a third-party service, treat
   it as compromised. Rotate, then audit usage.
4. **Assess impact.** Determine which users and data are affected and whether
   notification is warranted. Cross-user exposure requires an explicit decision
   about telling affected users.
5. **Patch.** Fix the root cause with the smallest correct change, keep the fix
   scoped to the vulnerability, and never weaken an existing security check to
   make the fix land.
6. **Test.** Add a regression test that fails without the fix, run the full
   backend and frontend suites, and confirm formatting and lint are clean.
7. **Clean history.** If a secret was committed, purge it from history in a
   coordinated rewrite agreed by the maintainers, and assume the key is
   compromised regardless of the rewrite.
8. **Disclose.** Once a fix is available, publish a GitHub Security Advisory
   describing the affected versions, impact, and remediation, and credit the
   reporter if they wish. If the reporter disclosed early, acknowledge the
   report and publish the advisory as soon as the fix ships.

## Reporting a problem with this policy

If this policy is unclear or incomplete, open a normal pull request against the
documentation with the improvement. Do not use the vulnerability channel for
documentation questions.