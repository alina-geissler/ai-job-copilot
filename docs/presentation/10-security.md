# 10 — Security Analysis

> **Related documents:** [07-api-analysis.md](07-api-analysis.md) | [11-engineering-practices.md](11-engineering-practices.md)

---

## Authentication

**Method:** Cookie-based sessions using Starlette `SessionMiddleware`.

**Implementation (`app/dependencies/auth.py`):**
- Session is an encrypted, signed cookie containing: `user_id`, `is_authenticated`, `created_at`, `last_seen`
- The `get_current_user()` FastAPI dependency validates every authenticated request
- Session data is signed using `SESSION_SECRET_KEY` (configured via environment variable, never hardcoded)

**Security properties:**
- Signed: tampering with the cookie invalidates the signature → rejected
- Server-controlled: session data lives in the signed cookie (not a server-side store); the server trusts the signed contents
- No JWT: sessions are stateful from the application's perspective (user_id is verified against the DB on every request)

---

## Session Management

| Property | Value | Configuration |
|---|---|---|
| Idle timeout | 30 minutes | `SESSION_IDLE_TIMEOUT_SECONDS=1800` |
| Absolute timeout | 8 hours | `SESSION_ABSOLUTE_TIMEOUT_SECONDS=28800` |
| Cookie `same_site` | Configurable | `SESSION_SAME_SITE` env var |
| Cookie `https_only` | Configurable | `SESSION_HTTPS_ONLY` env var |

**Timeout enforcement logic (`app/dependencies/auth.py`):**
1. `now - last_seen > idle_timeout` → session cleared, redirect to login with "Sitzung abgelaufen" flash
2. `now - created_at > absolute_timeout` → same action
3. After successful validation: `last_seen = now` (rolling idle window)

**Session destruction:** `POST /auth/logout` explicitly clears all session data.

---

## Password Security

**Library:** `bcrypt` (v5.0.0)
**File:** `app/core/security.py`

- Passwords are hashed with bcrypt on registration; the plaintext is never stored
- Verification uses `bcrypt.checkpw()` (constant-time comparison, prevents timing attacks)
- bcrypt's adaptive cost factor defends against brute force as hardware improves

---

## Secret Management

**Method:** Environment variables loaded from `.env` file (not committed to version control).
**Library:** `pydantic-settings` (`BaseSettings` class) in `app/core/config.py`.

Secrets managed via env vars:
- `DATABASE_URL` — includes DB credentials
- `SESSION_SECRET_KEY` — signs session cookies
- `OPENAI_API_KEY` — LLM access
- `JOB_API_KEY` — RapidAPI key
- `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY` — MinIO credentials
- `OPENROUTER_API_KEY` — CV extraction

`.gitignore` excludes `.env`; a `.env.example` should exist (best practice — status not confirmed in codebase).

---

## Privacy by Design: LLM Data Isolation

A deliberate architectural decision ensures that personal contact data is **never sent to the OpenAI API**:

- `_build_profile_dict()` in `cover_letter_service.py` explicitly excludes: `first_name`, `last_name`, `email`, `phone`, `street`, `city`, `location`, `signature_image`
- These fields are injected into the `content` JSONB **after** all LLM calls complete
- Risk mitigation: even if OpenAI stores request data, it will not contain the user's home address or phone number

---

## API Protection

**All protected routes** use `Depends(get_current_user)`. If the dependency raises `AuthenticationRequiredError`, the exception handler in `app/main.py` returns a 303 redirect to `/auth` — there is no 401 JSON response.

**No CSRF protection confirmed:** The application uses form POST submissions without explicit CSRF tokens. Starlette's `SessionMiddleware` signs the cookie but does not generate CSRF tokens by default. **This is a potential vulnerability** — see risks below.

**Rate limiting:** Soft limits for job search exist in `job_search_policy.py` (max 100 searches/day and 100 load-more actions/day). These are TODO items placeholder values — not production-hardened. There is no HTTP-level rate limiting (no middleware, no nginx rules).

---

## Input Validation

**Pydantic validation:** Form data is parsed into Pydantic models (`app/schemas/`) before reaching service code. Invalid types/missing required fields are rejected by FastAPI's form parsing.

**File upload validation (`document_service.py`):**
- MIME type check: only PDF accepted
- File size check: max 10 MB (`MAX_UPLOAD_SIZE_BYTES` env var)
- Unique storage key: `documents/{user_id}/{uuid}_{filename}` prevents path traversal

**SQL injection:** Not possible — SQLAlchemy ORM uses parameterised queries exclusively. Raw SQL is not used.

**XSS:** Jinja2 auto-escapes HTML by default. User-supplied content rendered in templates is escaped. The cover letter editor uses `contentEditable` but content is saved and re-rendered through the Jinja2 pipeline.

---

## Security Risks and Improvements

| Risk | Severity | Current State | Recommended Fix |
|---|---|---|---|
| **No CSRF protection** | High | No CSRF tokens on form submissions | Add Starlette `CSRFMiddleware` or generate CSRF tokens per form |
| **Soft rate limits only** | Medium | Job search limits are placeholder values (100/day); no HTTP-level throttling | Add `slowapi` middleware; enforce tighter per-user limits at HTTP level |
| **No HTTPS enforcement in dev** | Medium | `SESSION_HTTPS_ONLY` configurable but defaults unknown | Enforce `https_only=True` and `same_site=strict` in production config |
| **Session data in cookie** | Low | Signed cookie; no server-side session store | Acceptable for prototype; production could move to Redis-backed sessions for revocability |
| **No account lockout** | Medium | Unlimited login attempts | Add failed-attempt counter + temporary lockout after N failures |
| **OpenAI API key in env** | Low | Standard practice; not in code | Use a secrets manager (AWS Secrets Manager, HashiCorp Vault) in production |
| **CORS not configured** | Low | No CORS headers set; acceptable for server-rendered app | No external API consumers currently; add if REST API is introduced |
| **No security headers** | Low | No CSP, HSTS, X-Frame-Options headers set | Add `SecurityHeadersMiddleware` or configure via reverse proxy |
| **Audit log is a flat file** | Low | `evals/*.jsonl` has LLM outputs but no auth audit trail | Add structured auth event logging |
| **Document storage key predictable?** | Low | `documents/{user_id}/{uuid}_{name}` — UUID makes it non-guessable | Acceptable; presigned URLs add time-based expiry |

---

## Security Practices Implemented (Confirmed)

- bcrypt password hashing with adaptive cost factor
- Signed session cookies (Starlette SessionMiddleware)
- Session idle + absolute timeouts
- Environment-variable-based secret management
- Pydantic input validation at form boundaries
- SQLAlchemy parameterised queries (no SQL injection surface)
- Jinja2 auto-escaping (no XSS in templates)
- Private contact data excluded from LLM prompts (privacy-by-design)
- File type + size validation on upload
- UUID-based storage keys (no path traversal)
- Auth failure redirects (no information leakage via 401 responses)
