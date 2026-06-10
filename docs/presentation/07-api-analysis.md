# 07 — API Analysis

> **Related documents:** [06-user-flows.md](06-user-flows.md) | [10-security.md](10-security.md)

---

## API Architecture

AI Job Copilot does **not** expose a JSON REST API. All endpoints return:
- **HTML** (full-page `TemplateResponse`) for normal requests
- **HTML fragments** (partial `TemplateResponse`) for HTMX swap targets
- **HTTP 303 redirects** after successful state mutations (POST-redirect-GET pattern)

This is a deliberate architectural choice: server-rendered HTML with Jinja2, enhanced by HTMX for interactivity, with no frontend JavaScript framework and no separate API consumer.

**Request format:** All mutations use HTML form submissions (`application/x-www-form-urlencoded` or `multipart/form-data`).

**Authentication:** Cookie-based session. All protected endpoints inject `Depends(get_current_user)` which validates the session and returns the `User` ORM object.

---

## Endpoint Table

| Endpoint | Method | Purpose | Auth Required | Response |
|---|---|---|---|---|
| `/health` | GET | Health check | No | JSON `{"status": "ok"}` |
| `/` | GET | Landing page | No | HTML |
| `/privacy` | GET | Privacy policy | No | HTML |
| `/terms` | GET | Terms of service | No | HTML |
| `/auth` | GET | Login/register page | No | HTML |
| `/auth/register` | POST | Create new account | No | Redirect → /dashboard |
| `/auth/login` | POST | Authenticate user | No | Redirect → /dashboard |
| `/auth/logout` | POST | Destroy session | Yes | Redirect → /auth |
| `/dashboard` | GET | Home page with stats | Yes | HTML |
| `/jobs` | GET | Search profile list | Yes | HTML |
| `/jobs/search/{profile_id}` | POST | Execute job search | Yes | Redirect → run view |
| `/jobs/run/{run_id}` | GET | View search run results | Yes | HTML |
| `/jobs/run/{run_id}/load-more` | POST | Load next page of results | Yes | Redirect → run view |
| `/jobs/{job_id}/normalize` | POST | Trigger job normalization | Yes | Redirect |
| `/jobs/{job_id}/normalize/status` | GET | Poll normalization status (HTMX) | Yes | HTML fragment |
| `/jobs/history` | GET | List all past search runs | Yes | HTML |
| `/jobs/analyze` | GET | Single job analysis page | Yes | HTML |
| `/tracker` | GET | Application tracker list | Yes | HTML |
| `/tracker/{job_id}` | GET | Tracker entry detail | Yes | HTML |
| `/tracker/{job_id}/status` | POST | Update application status | Yes | Redirect |
| `/tracker/{job_id}/notes` | POST | Save notes | Yes | Redirect |
| `/search-profiles` | GET | List search profiles | Yes | HTML |
| `/search-profiles/create` | GET | New profile form | Yes | HTML |
| `/search-profiles/create` | POST | Save new profile | Yes | Redirect |
| `/search-profiles/{id}/edit` | GET | Edit profile form | Yes | HTML |
| `/search-profiles/{id}/edit` | POST | Save profile changes | Yes | Redirect |
| `/search-profiles/{id}/delete` | POST | Delete profile | Yes | Redirect |
| `/documents` | GET | Document list | Yes | HTML |
| `/documents/upload` | POST | Upload PDF document | Yes | Redirect |
| `/documents/{id}/rename` | POST | Rename document | Yes | Redirect |
| `/documents/{id}/delete` | POST | Delete document + MinIO object | Yes | Redirect |
| `/documents/{id}/download` | GET | Presigned download URL | Yes | Redirect (presigned URL) |
| `/profile` | GET | User profile page | Yes | HTML |
| `/profile/edit` | GET | Edit profile form | Yes | HTML |
| `/profile/edit` | POST | Save profile changes | Yes | Redirect |
| `/cover-letter/setup` | GET | Cover letter setup (job selection) | Yes | HTML |
| `/cover-letter/generate` | POST | Initiate generation | Yes | Redirect → generating |
| `/cover-letter/{id}/generating` | GET | Generation polling page | Yes | HTML |
| `/cover-letter/{id}/status` | GET | Poll generation status (HTMX) | Yes | HTML fragment |
| `/cover-letter/{id}/editor` | GET | Open cover letter editor | Yes | HTML |
| `/cover-letter/{id}/preview` | GET | Live A4 preview (HTMX target) | Yes | HTML fragment |
| `/cover-letter/{id}/content-save` | POST | Save edited content | Yes | JSON or Redirect |
| `/cover-letter/{id}/save` | POST | Mark as saved document | Yes | Redirect |
| `/cover-letter/{id}/copy` | POST | Duplicate cover letter | Yes | Redirect |
| `/cover-letter/{id}/delete` | POST | Delete cover letter | Yes | Redirect |
| `/cover-letter/{id}/export-pdf` | GET | Download PDF | Yes | PDF response |

---

## Key Endpoint Details

---

### `POST /auth/register`

**Purpose:** Create a new user account.

**Request:** Form data — `email`, `password`, `confirm_password`, `first_name`, `last_name`

**Processing:**
1. `auth_service.register_user_account(UserCreate)` called
2. Email uniqueness check via `crud/user.get_user_by_email()`
3. `bcrypt.hash(password)` for secure storage
4. `crud/user.create_user()` inserts record
5. Session populated: `user_id`, `is_authenticated=True`, `created_at`, `last_seen`

**Responses:**
- Success: 303 → `/dashboard`
- Email taken: flash error + 303 → `/auth`
- Passwords don't match: flash error + 303 → `/auth`

---

### `POST /jobs/search/{profile_id}`

**Purpose:** Execute a job search run for the given profile.

**Request:** No body (profile ID in URL path); user from session.

**Processing:**
1. `job_search_policy.decide_primary_search(profile, user, today)`
2. Decision determines next action (return, block, or search)
3. If `START_NEW_RUN`: provider called → response mapped → persisted → redirect
4. If `SHOW_EXISTING_RUN`: redirect to existing run's view

**Responses:**
- Success: 303 → `/jobs/run/{run_id}`
- Blocked: 303 → `/jobs` with flash error

---

### `POST /cover-letter/generate`

**Purpose:** Initiate cover letter generation (async).

**Request:** Form data — `job_id` or `manual_job_posting_id`, `tone`, `industry_group`, `hierarchy_level`, `output_language`, `must_haves`, `no_gos`, `personal_motivation`, `why_company`, `added_value`, `earliest_start_date`, `salary_expectation`, `company_context`

**Processing:**
1. `cover_letter_service.initiate_cover_letter_generation()` creates PENDING record
2. Background task enqueued (`_run_generation_task`)
3. Immediate redirect to polling page

**Response:** 303 → `/cover-letter/{id}/generating`

---

### `GET /cover-letter/{id}/status` (HTMX polling)

**Purpose:** Returns a small HTML fragment indicating generation status.

**Request:** HTMX GET, triggered every 2 seconds by the generating page.

**Processing:**
- SELECT `cover_letters` WHERE `id={id}` and `user_id={current_user.id}`
- Returns different HTML fragments for: PENDING, PROCESSING, COMPLETED, FAILED

**HTMX behaviour:**
- `PENDING/PROCESSING`: fragment contains next `hx-trigger="every 2s"` → polling continues
- `COMPLETED`: fragment contains a JavaScript redirect to editor
- `FAILED`: fragment shows error message with retry button

---

### `GET /cover-letter/{id}/preview` (HTMX live preview)

**Purpose:** Re-render the A4 cover letter preview when design controls change.

**Request:** HTMX GET; includes all editor form state via `hx-include="#editor-form"`.

**Processing:**
- Reads `template`, `theme`, `font`, `size`, `spacing` from query params
- Renders the appropriate variant template (`cover_letter_classic.html`, etc.) as a fragment
- **Does not** re-generate content — only re-styles the layout

**Response:** HTML fragment (cover letter body only, no page chrome)

---

## Route Module Summary

| Module | Prefix | Router Name |
|---|---|---|
| `app/api/routes/health.py` | (none) | `health_router` |
| `app/api/routes/pages.py` | (none) | `pages_router` |
| `app/api/routes/auth.py` | `/auth` | `auth_router` |
| `app/api/routes/dashboard.py` | `/dashboard` | `dashboard_router` |
| `app/api/routes/jobs.py` | `/jobs` | `jobs_router` |
| `app/api/routes/search_profiles.py` | `/search-profiles` | `search_profiles_router` |
| `app/api/routes/application_tracker.py` | `/tracker` | `application_tracker_router` |
| `app/api/routes/documents.py` | `/documents` | `documents_router` |
| `app/api/routes/profile.py` | `/profile` | `profile_router` |
| `app/api/routes/cover_letter.py` | `/cover-letter` | `cover_letter_router` |
