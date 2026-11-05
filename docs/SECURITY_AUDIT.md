# FitAI Production Security Audit

Branch: `feat/security` · Audit date: 2026-11-05 · Scope: backend (FastAPI), frontend
(React 19 + Vite), Supabase (Auth/Postgres/Storage), Render, Vercel config.

> **About the "70-point checklist".** The request referred to a 70-point checklist "provided
> below", but the text received contained only the eleven categories (A–K). The 70 items
> below were therefore derived from those categories so every listed concern maps to at least
> one numbered, individually verifiable item. If you have the original numbered list, map it
> onto these rows.

Status legend: **PASS** (verified, evidence given) · **FIXED** (defect found and fixed here) ·
**FAIL** (defect not fixed here) · **N/A** · **NOT VERIFIED** (needs access I do not have,
usually the Supabase/Render/Vercel dashboards).

## 1. Executive summary

The application's core controls were already sound: every `/api/v1` route validates a Supabase
JWT server-side (signature, issuer, audience, expiry, algorithm allow-list), every query is
scoped to the authenticated user, SQL is parameterised, and no secret is in source or git
history. The audit found and fixed these gaps:

| # | Gap found | Severity | Fix |
|---|-----------|----------|-----|
| 1 | No rate limiting anywhere (chat/LLM, uploads, geocoding, auth brute force) | **High** | In-process sliding-window limiter + 401-lockout guard |
| 2 | SSRF bypass: `fetch_url` followed redirects without re-checking each hop (public page → `169.254.169.254`) | **High** | Manual redirect loop, every hop re-validated |
| 3 | No HSTS / CSP / Permissions-Policy on the Render-served app or API; `/docs` and `/openapi.json` public in production | Medium | `SecurityHeadersMiddleware`, SPA CSP, docs hidden in production |
| 4 | Upload content not verified until after the file was stored (disguised binaries persisted) | Medium | Signature check before storage + filename sanitisation |
| 5 | CORS allowed any method/header | Medium | Explicit method/header allow-lists |
| 6 | Source links from web-search results rendered into `href` unvalidated (`javascript:` URL) | Medium | `safeHttpUrl()` allow-lists http(s) |
| 7 | Vercel config lacked CSP/HSTS/Permissions-Policy | Medium | Added to `frontend/vercel.json` |
| 8 | `/health/guardrails` disclosed configuration publicly | Low | Minimal body in production |
| 9 | `npm audit`: high-severity transitive `undici` (dev-only via jsdom) | Low | Lockfile updated, 0 vulnerabilities |

**Not fixed (need decisions or dashboard access):** known advisories in pinned
`langgraph`/`langchain-core`/`langgraph-checkpoint` (major-version migration) and `filelock`
(fix needs Python ≥ 3.11); Supabase Auth settings (password policy, email confirmation, MFA,
auth rate limits) and Storage policies cannot be checked without dashboard access; the
Vercel frontend domain could not be identified from project config. See §7.

**Production verification caveat.** The live service at `fitai-web-femz.onrender.com` is
running the *pre-fix* build. The header/docs findings in §5 reflect that, and will show as
fixed only after this branch is deployed.

## 2. Critical / high findings

* **H1 – No rate limiting.** Any signed-in user (or anonymous token-guesser) could issue
  unlimited LLM chat calls, uploads and geocoding requests, spending provider quota. Fixed in
  `backend/app/core/http_security.py` (limits below). Limits are per client IP, in-process.
* **H2 – SSRF via redirect.** `app/tools/web/fetch.py` validated only the *first* URL, then
  `follow_redirects=True`. A hostile page the research agent fetched could redirect to cloud
  metadata or loopback. Fixed: redirects are followed manually and each `Location` is re-checked
  (scheme, host, private/loopback/link-local resolution). Residual risk: DNS rebinding between
  the check and the connection (see §7).
* No critical findings. No secrets were found in the tree, bundle or git history.

## 3. Checklist (70 items)

### A. Secrets and configuration

| # | Item | Status | Sev. | Evidence / fix | Manual action |
|---|------|--------|------|----------------|---------------|
| 1 | No secrets in source tree | PASS | – | Only `*.env.example` tracked (`git ls-files`); `.env`, `.env.*.local`, `*.db`, `uploads/` git-ignored | – |
| 2 | No secrets in git history | PASS | – | Regex scan of all 419 commits for Groq (`gsk_`), HF (`hf_`), `sb_secret_`, JWTs, DB URLs with passwords, private keys, AWS keys: 0 hits. Not a Gitleaks run (not installed) | Run Gitleaks in CI if desired |
| 3 | Service-role key never in frontend | PASS | – | Frontend reads only `VITE_SUPABASE_URL/ANON_KEY` (`src/services/supabase.ts`); `Dockerfile.web` passes only those two build args | – |
| 4 | Built bundle has no privileged secrets | FIXED | Med | New `frontend/scripts/scanBundle.mjs` (+ tests, CI step `npm run check:bundle`); scan of current `dist/` passed | – |
| 5 | Source maps not shipped | FIXED | Low | `build.sourcemap: false` made explicit; `dist/` contains 0 `.map` files; scanner fails on any | – |
| 6 | Prod/dev credentials separated | NOT VERIFIED | Med | Config is env-driven; separation depends on Render/Supabase projects | Confirm separate Supabase projects/keys for dev and prod |
| 7 | Debug off in production | PASS | – | `render.yaml` `DEBUG=false`; `Settings.production_problems()` refuses to start with `DEBUG=true` | – |
| 8 | Prod config validated at boot | PASS | – | `production_problems()` rejects SQLite, `*` CORS, non-https origins, missing Supabase URL; now also rejects `RATE_LIMIT_ENABLED=false` | – |
| 9 | `.env`/`.git`/backups not publicly served | PASS | – | Live probes of `/.env`, `/.git/config`, `/backend/.env`: return the SPA `index.html`, not file content; SPA handler has a `..`/symlink containment check (`core/spa.py`) | – |
| 10 | No secrets printed in logs | PASS | – | Grep of logging calls found no token/key/password logging; request log records path only (no query/headers/body) | – |

### B. Authentication

| # | Item | Status | Sev. | Evidence / fix | Manual action |
|---|------|--------|------|----------------|---------------|
| 11 | All protected routes require a bearer token | FIXED | – | New parametrised test `tests/security/test_authorization_sweep.py` enumerates every `/api/v1` route (54 method+path pairs) and asserts 401 anonymous; only `GET /plan/templates` (static data) is allow-listed | – |
| 12 | JWT signature verified (JWKS/HS256) | PASS | – | `core/security.py`; `test_security.py` | – |
| 13 | Algorithm allow-list; `none` rejected | PASS | – | Header `alg` must be in allow-list; new `test_alg_none_token_is_rejected` | – |
| 14 | Issuer enforced | PASS | – | `iss` required & compared; new `test_wrong_issuer…`, `test_missing_issuer…` | – |
| 15 | Audience enforced | PASS | – | default `authenticated`; new `test_wrong_audience_is_rejected` | – |
| 16 | Expiry required & enforced | PASS | – | `require: [exp, sub]`; `test_expired_token…`, new `test_missing_expiry…` | – |
| 17 | Subject must be a UUID | PASS | – | New `test_non_uuid_subject_is_rejected` | – |
| 18 | Identity never taken from request body | PASS | – | `get_current_auth_user` docstring + `test_client_cannot_set_ownership_fields_via_payload` | – |
| 19 | Signup / email verification behaviour | NOT VERIFIED | Med | Handled by Supabase Auth; not visible from code | Enable "Confirm email"; check redirect URLs |
| 20 | Password policy | NOT VERIFIED | Med | Supabase-managed | Set min length ≥ 10 and leaked-password protection (Auth → Policies) |
| 21 | Login/signup rate limiting | NOT VERIFIED | Med | Supabase-side limits not inspectable. FitAI-side: failed-auth (401) lockout added (#46) | Review Auth → Rate limits |
| 22 | MFA available for privileged accounts | N/A | – | No admin role/UI exists (see #31); Supabase offers TOTP MFA | Enable MFA for Supabase/Render/Vercel/GitHub owners |
| 23 | No default/test credentials | PASS | – | Grep of tree/history; examples are placeholders (`your-supabase-secret-key`) | – |

### C. Sessions and tokens

| # | Item | Status | Sev. | Evidence / fix | Manual action |
|---|------|--------|------|----------------|---------------|
| 24 | Token storage understood | PASS | Info | `supabase-js` with `persistSession: true` stores access+refresh tokens in **localStorage** (default). Any XSS could read them. Mitigated by: CSP `script-src 'self'` (no inline/eval), react-markdown without raw HTML, `safeHttpUrl()`, no `dangerouslySetInnerHTML` (grep). Cookie sessions deliberately **not** introduced (breaking redesign; would need `@supabase/ssr` + CSRF handling) | Consider cookie sessions in a future, planned migration |
| 25 | Auto-refresh & 401 sign-out | PASS | – | `autoRefreshToken: true`; `AuthContext.tsx` wires API 401 → sign-out | – |
| 26 | Access-token lifetime | NOT VERIFIED | Low | Supabase-configured (default 1 h) | Keep ≤ 1 h; enable refresh-token rotation |
| 27 | Logout / password-change invalidation | NOT VERIFIED | Low | Server-side session revocation is a Supabase feature; backend is stateless and trusts the JWT until `exp` | Use "sign out of all sessions" on password change |
| 28 | No tokens in URLs/logs | PASS | – | Bearer header only; request log omits query string | – |

### D. Authorization and access control

| # | Item | Status | Sev. | Evidence / fix | Manual action |
|---|------|--------|------|----------------|---------------|
| 29 | Conversations/messages ownership (IDOR) | PASS | – | `test_conversations.py`, new `test_messages_of_another_users_conversation_are_hidden` (404 for others) | – |
| 30 | Documents ownership | PASS | – | `test_document_ownership_is_enforced` | – |
| 31 | No admin/internal/debug routes | PASS | – | Route enumeration: only `/api/v1/*`, `/health*`, `/v1/models` stub, docs. Docs now off in prod | – |
| 32 | Workouts / sets (indirect) ownership | PASS | – | `tests/api/test_workouts.py`; repositories filter `user_id`; sets reachable only via the session | – |
| 33 | Planned sessions / exercises (indirect) | PASS | – | `tests/api/test_plan.py` (PATCH/complete/DELETE → 404 for other user) | – |
| 34 | Memory & pending updates ownership | PASS | – | `test_memory_ownership_is_enforced` | – |
| 35 | Measurements / progress ownership | PASS | – | `tests/api/test_progress.py` | – |
| 36 | Global vs custom exercise access | FIXED | – | New `test_custom_exercises_are_private_to_their_creator` (custom rows hidden from others; global visible) | – |
| 37 | Ownership fields not client-settable | PASS | – | New payload test; Pydantic schemas have no `user_id`/role fields | – |
| 38 | vector_chunks scoped to owner | PASS | – | `pg_vector_store._where_sql` always adds `collection` + owner scope via bind params; RLS policy requires `owner_id = auth.uid()` | – |
| 39 | RLS enabled on all tables | FIXED | – | Migration `ca4d2c439416` enables RLS on 18 tables (17 ORM + `vector_chunks`; the "19" in the brief is not what the code has). New `test_rls_migration.py` fails if any ORM table lacks RLS. **Static check only — not run against a live Postgres** | Verify with `select relname, relrowsecurity from pg_class …` in prod |
| 40 | RLS policy shape | PASS | – | Static tests: own-row `USING`+`WITH CHECK`; joins for messages/workout_sets/planned_exercises; anon limited to deny + global exercises | – |
| 41 | App enforces ownership despite `postgres` bypassing RLS | PASS | – | Explicit `user_id` filters in all repositories (130 references); sweep + IDOR tests | – |

### E. Input validation and injection

| # | Item | Status | Sev. | Evidence / fix | Manual action |
|---|------|--------|------|----------------|---------------|
| 42 | SQL injection | PASS | – | SQLAlchemy ORM; only dynamic SQL is `pg_vector_store` f-strings whose fragments are built from fixed templates with bind placeholders (`_Params.add`) | – |
| 43 | XSS in React/markdown/citations | FIXED | Med | No `dangerouslySetInnerHTML`; `react-markdown` v10 (no `rehype-raw`, URL sanitising). Source links now go through `safeHttpUrl()` (`utils/safeUrl.ts`, tested incl. `javascript:`/`data:`) | – |
| 44 | Pydantic validation on inputs | PASS | – | Length/range bounds on chat (4000), titles, plan/workout numbers; pagination `le=100` (`test_pagination_limit_is_capped`); plan sessions `le=500` | – |
| 45 | Upload type/content validation | FIXED | Med | Signature (magic bytes / NUL-free text) checked **before** storage; `tests/security/test_upload_validation.py` (exe-as-pdf, zip-as-pdf, binary-as-txt, wrong extension) | – |
| 46 | Upload size limit | PASS | – | Streaming 1 MiB-chunk cap (`MAX_UPLOAD_SIZE_MB`=10) → 413; tested | – |
| 47 | Uploaded files cannot execute | PASS | – | Stored under server-generated `user_id/uuid` keys in a private bucket, never served back; local backend has traversal containment (`test_storage_paths.py`) | – |
| 48 | Filename safety | FIXED | Low | `sanitize_filename()` strips directories/control chars, caps at 255 | – |
| 49 | Document download authz / traversal | N/A | – | No download endpoint exists (originals are not served); storage keys are not user-controlled | Re-audit if a download route is added |
| 50 | SSRF | FIXED | High | `fetch_url` redirect hops re-validated (tests incl. metadata IP, localhost, `file:`, redirect loops). Geocoding/places use fixed provider hosts | See DNS-rebinding note §7 |
| 51 | Open redirects | PASS | – | No `redirect`/`next`/`returnTo` handling in frontend; backend issues no redirects | Restrict Supabase redirect-URL allow-list |
| 52 | Unsafe eval/exec/pickle/yaml/shell | PASS | – | Grep of `app/`: none | – |

### F. Network and transport

| # | Item | Status | Sev. | Evidence / fix | Manual action |
|---|------|--------|------|----------------|---------------|
| 53 | HTTPS everywhere; HTTP→HTTPS | PASS | – | Live: `http://fitai-web-femz.onrender.com` → `301` to `https://…`; Vercel & Supabase are HTTPS-only | – |
| 54 | HSTS | FIXED | Med | Live app had none (pre-fix). Added in backend (production only) and `vercel.json` | Deploy |
| 55 | No mixed content | PASS | – | CSP `connect-src`/`img-src` https-only origins; no `http://` URLs in `src` | – |
| 56 | CORS: explicit https origins only | PASS | – | Prod validator rejects `*`/http; live: `Origin: https://evil.example` preflight → 400, no `Access-Control-Allow-Origin` | – |
| 57 | CORS methods/headers restricted | FIXED | Med | Was `*`; now explicit lists (tests incl. unexpected header → 400) | – |
| 58 | CSRF | N/A | – | Bearer tokens in `Authorization` (not cookies) are not auto-attached cross-site, so classic CSRF does not apply. Re-evaluate if cookie sessions are adopted | – |
| 59 | TLS configuration | NOT VERIFIED | Low | Terminated by Render/Cloudflare and Vercel; not run through an SSL scanner | Run SSL Labs on both domains |

### G. Security headers

| # | Item | Status | Sev. | Evidence / fix | Manual action |
|---|------|--------|------|----------------|---------------|
| 60 | Content-Security-Policy | FIXED | Med | API: `default-src 'none'; frame-ancestors 'none'`. SPA (Render): self + Supabase (https/wss) + Google Fonts, no inline/eval scripts. Vercel: same + `*.onrender.com` for API. Build verified to contain no inline script | If the API is on a non-Render host, add it to `connect-src` in `vercel.json` |
| 61 | Clickjacking (XFO / frame-ancestors) | PASS | – | Both present on live responses and in new middleware | – |
| 62 | `X-Content-Type-Options: nosniff` | PASS | – | Present live | – |
| 63 | Referrer-Policy | PASS | – | `strict-origin-when-cross-origin` live | – |
| 64 | Permissions-Policy | FIXED | Low | Added (`camera`, `payment`, `usb`… off; geolocation/microphone `self` since the app uses location + dictation) | – |

### H. Database and storage

| # | Item | Status | Sev. | Evidence / fix | Manual action |
|---|------|--------|------|----------------|---------------|
| 65 | Postgres not publicly exposed; roles/privileges | NOT VERIFIED | Med | Supabase-managed; backend uses pooled connection string | Restrict DB network access, use a least-privilege DB role if feasible, rotate DB password |
| 66 | Storage bucket private + cross-user access | NOT VERIFIED | Med | Code uses service-role key server-side only with `user_id/uuid` keys; bucket privacy/policies live in Supabase, and no download route exists. Not tested against the real bucket | Confirm `fitai-documents` is **private** and has no public/anon policies |

### I. API security, logging, monitoring and privacy

| # | Item | Status | Sev. | Evidence / fix | Manual action |
|---|------|--------|------|----------------|---------------|
| 67 | Rate limiting on auth, chat, uploads, LLM | FIXED | High | Per-IP/min: chat 20, uploads 10, location 30, writes 120, all API 240; auth-failure lockout (20×401/5 min → 429). Uses rightmost `X-Forwarded-For` (client cannot forge). Tests in `test_http_hardening.py`. **Limitation:** in-process, single worker (matches the image) | Use a shared store (Redis) if scaled beyond one worker |
| 68 | Errors don't leak internals | PASS | – | Shared handlers return a generic envelope; `test_unexpected_errors_do_not_leak_internals`; live malformed-token 401 reveals nothing | – |
| 69 | Debug/health/docs exposure | FIXED | Low–Med | `/docs`,`/redoc`,`/openapi.json` hidden in production (live: were public); `/health/guardrails` minimal in production | – |
| 70 | Dependencies, webhooks, privacy, IR | see §6 | – | npm audit prod: 0; dev: fixed → 0. pip-audit: 32 advisories in 5 packages (FAIL, §7). No webhooks exist (N/A). **No privacy policy / data-handling disclosure found in the repo (FAIL — Medium)**; app stores health data and sends chats to Groq | Publish a privacy policy; see §8 for IR/rotation |

> Row 70 bundles the dependency, webhook, privacy-policy and incident-response checks; each is
> reported separately in §6–§8. Third-party scripts: none (only Google Fonts CSS/fonts).
> Analytics: none found.

## 4. Rate-limit and header reference

| Rule | Match | Limit |
|------|-------|-------|
| chat | `POST /api/v1/chat` | `RATE_LIMIT_CHAT_PER_MINUTE` (20) |
| upload | `POST /api/v1/documents*` | `RATE_LIMIT_UPLOAD_PER_MINUTE` (10) |
| location | `/api/v1/location*` | `RATE_LIMIT_LOCATION_PER_MINUTE` (30) |
| writes | POST/PUT/PATCH/DELETE under `/api/v1` | `RATE_LIMIT_API_PER_MINUTE` (120) |
| api | everything under `/api/v1` | 2 × `RATE_LIMIT_API_PER_MINUTE` |
| auth failures | any 401 | `RATE_LIMIT_AUTH_FAILURES` (20) per 5 min per client |

`/health*`, the static app and CORS preflights are exempt. Exceeding a limit returns `429`
with `Retry-After` and the standard error envelope. Set `TRUST_PROXY_HEADERS=true` only behind
a proxy that appends the real peer (Render; set in `render.yaml`).

## 5. Production verification (non-destructive, 2026-11-05, pre-deploy build)

Target: `https://fitai-web-femz.onrender.com` (single Render service serving API + SPA).

| Check | Result |
|-------|--------|
| HTTP → HTTPS | `301` to `https://…` ✔ |
| `GET /health` | 200 `{"status":"ok"}` (intended public liveness) |
| `GET /api/v1/profile` (no token) | 401 JSON envelope ✔ |
| Malformed bearer token | 401 `Malformed access token.`, no internals ✔ |
| CORS preflight from `https://evil.example` | 400, no `Access-Control-Allow-Origin` ✔ |
| `/.env`, `/.git/config`, `/backend/.env`, `/assets/index.js.map` | return SPA `index.html` (no file content) ✔ |
| `/docs`, `/openapi.json` | **200 – publicly exposed** ✘ (fixed in this branch) |
| `/health/guardrails` | 200 with config flags ✘ (minimised in this branch) |
| HSTS / CSP / Permissions-Policy | **absent** ✘ (present after deploy) |
| `X-Frame-Options`, `nosniff`, `Referrer-Policy` | present ✔ |

**Vercel frontend:** the production Vercel domain could not be determined from project
configuration. `fitai.vercel.app` appears only as an *example* in `docs/DEPLOYMENT_GUIDE.md`; it
responds, but its headers/age suggest it is not this project, so it was **not** audited or
assumed to be ours. **NOT VERIFIED.**

No authenticated, destructive, load or credential-guessing tests were run.

## 6. Test and tool results

| Command | Result |
|---------|--------|
| `pytest` (backend, full, `DOCUMENT_STORAGE_BACKEND=local`) | **868 passed, 16 skipped, 0 failed** (baseline before this work: 758 passed, 16 skipped). One existing test used non-PDF bytes for a `.pdf`; its fixture was changed to a signed payload because uploads are now content-validated |
| `ruff check .` / `ruff format --check .` (backend) | pass |
| `npm test` (frontend, vitest) | 31 files, 330 tests passed |
| `npm run lint` (oxlint) | 0 errors (pre-existing warnings only) |
| `npm run type-check` / `npm run build` | pass |
| `npm run check:bundle` | pass (no secrets, no source maps) |
| `npm audit` | 0 vulnerabilities (was 1 high, dev-only `undici`) |
| `pip-audit` (resolved `requirements-web.txt`, py3.10) | **32 advisories** in `filelock`, `langchain-core`, `langgraph`, `langgraph-checkpoint`, `langgraph-sdk` — not fixed (§7) |
| Secret scan | custom regex over 419 commits + tree + bundle: 0 findings (Gitleaks unavailable) |
| Live RLS / Storage tests | **not run** (no database/dashboard access) |

New tests: `backend/tests/security/` (http hardening, authorization sweep, upload validation,
JWT claims, RLS migration), additions to `tests/unit/tools/test_web_fetch.py`, frontend
`safeUrl.test.ts` and `scripts/scanBundle.test.mjs`.

## 7. Remaining risks

1. **Vulnerable pinned AI libraries (High, unfixed).** `langgraph<0.3`, `langchain-core<0.4`
   (and `langgraph-checkpoint`/`-sdk`) have published fixes only in 1.x / ≥0.3.x lines. Upgrading
   is a breaking migration of the agent graph and needs its own PR + regression run. `filelock`
   fixes require Python ≥ 3.11 (image is 3.10). Exposure is mitigated by the app not exposing
   checkpoint/serialisation endpoints, but this is not proven. Advisory CI job added
   (`dependency-audit.yml`).
2. **Rate limiter is in-process.** Correct for the one-worker image; per-instance counters if
   scaled out. Shared IPs (NAT) share a bucket.
3. **Tokens in `localStorage`.** Any future XSS would expose sessions; CSP is the main defence.
4. **Supabase-side controls unverified** (password policy, email confirmation, MFA, Auth rate
   limits, token lifetime, bucket privacy, DB network exposure, RLS applied in prod).
5. **DNS rebinding** can still defeat the resolve-then-connect SSRF check in `fetch_url`; a
   fix means connecting to the validated IP (transport-level pinning).
6. **No privacy policy / data-processing disclosure** despite storing health/fitness data and
   sending chat content to Groq.
7. **`--forwarded-allow-ips "*"`** in the Dockerfile trusts forwarded headers from any peer; safe
   behind Render's proxy, not if the container is exposed directly.
8. **Vercel deployment** (if any) unidentified and unaudited.
9. **CSP** keeps `style-src 'unsafe-inline'` (React inline styles) and allows `https:` images.
10. **Uploaded PDFs/DOCX are parsed server-side** (pypdf, python-docx); parser bugs are a
    residual risk — keep `pypdf` current.

## 8. Required configuration, rotation, deployment and rollback

### Render (`fitai-web`)
* Deploy this branch (auto-deploy is off). `render.yaml` now sets `TRUST_PROXY_HEADERS=true`,
  `RATE_LIMIT_ENABLED=true`.
* Optional tuning: `RATE_LIMIT_*` variables (see `backend/.env.example`). `EXPOSE_API_DOCS=true`
  re-enables `/docs` temporarily if needed.
* `CORS_ORIGINS` must be the exact https origin(s). `SUPABASE_URL` must be set (also feeds the
  CSP `connect-src`).

### Supabase (manual)
* Auth: confirm email, password minimum ≥ 10 + leaked-password protection, enable MFA, review
  rate limits, restrict **Redirect URLs** to your real origins, refresh-token rotation.
* Storage: `fitai-documents` must be **private**; no anon/authenticated policies on
  `storage.objects` for it (the backend uses the service-role key).
* Database: confirm RLS flags (`select relname, relrowsecurity from pg_class where relnamespace
  = 'public'::regnamespace and relkind='r'`), restrict network access, use the pooled string.

### Vercel (if used)
* Redeploy for the new header set. If the API is not on `*.onrender.com`, add its origin to
  `connect-src` in `frontend/vercel.json`. Set only `VITE_SUPABASE_URL`,
  `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL` — never a service-role key.

### Secret rotation (no leak was found; do this on any suspicion and at least annually)
Rotate in this order, updating Render env vars, then redeploying: `SUPABASE_SERVICE_ROLE_KEY`
(Supabase → API keys) → DB password (`DATABASE_URL`) → `GROQ_API_KEY`, `GROQ_EXTRACTION_API_KEY`,
`PROMPT_GUARD_API_KEY` → `HF_TOKEN` → `EMBEDDING_API_KEY`. The anon key is public; rotate only
with the JWT secret. Revoke old keys at the provider after confirming `/health/ready` is OK.

### Incident response (summary)
1. Contain: rotate the affected credential; if user data is implicated, set Render env
   `RATE_LIMIT_API_PER_MINUTE` low or suspend the service. 2. Preserve logs (Render) and record
   request IDs. 3. Assess data exposed (RLS/ownership make cross-user exposure the key
   question). 4. Notify affected users/regulators as required. 5. Fix, add a regression test,
   and report via the GitHub Security Advisory flow in `SECURITY.md`.

### Deployment and rollback
* Backward compatible: no schema or migration change; new settings have safe defaults.
* Deploy → check `curl -sI https://<host>/` for HSTS/CSP, `GET /docs` → 404, a signed-in chat
  works (confirms CSP `connect-src` and CORS), uploads still work.
* If a legitimate flow is blocked: raise the relevant `RATE_LIMIT_*` value (env-only change);
  set `EXPOSE_API_DOCS=true` to restore docs. To roll back entirely, redeploy the previous
  Render deploy; `vercel.json` changes revert with the previous Vercel deployment.

## 9. Files changed

Backend: `app/core/http_security.py` (new), `app/core/service_app.py`, `app/core/spa.py`,
`app/core/config.py`, `app/main.py`, `app/services/document_service.py`,
`app/tools/web/fetch.py`, `.env.example`. Tests: `tests/security/*` (new), `tests/conftest.py`,
`tests/unit/rag/test_worker.py`, `tests/unit/tools/test_web_fetch.py`.
Frontend: `src/utils/safeUrl.ts` (+test), `src/components/chat/MessageBubble.tsx`,
`vite.config.ts`, `vercel.json`, `scripts/scanBundle.mjs` (+test), `vitest.config.ts`,
`package.json`, `package-lock.json`. Infra/CI: `render.yaml`,
`.github/workflows/frontend-ci.yml`, `.github/workflows/dependency-audit.yml`.
