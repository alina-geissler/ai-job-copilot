# 15 — Future Improvements

> **Related documents:** [16-v2-roadmap.md](16-v2-roadmap.md) | [12-testing.md](12-testing.md) | [13-performance.md](13-performance.md) | [10-security.md](10-security.md)

---

Improvements are ranked by **impact** (High / Medium / Low) and **effort** (Low / Medium / High).

---

## Technical Improvements

| Improvement | Impact | Effort | Description |
|---|---|---|---|
| Add test suite (unit + integration) | High | Medium | pytest with mocked LLM clients; TestClient for route handlers |
| Add CSRF protection | High | Low | Add `itsdangerous`-based CSRF tokens or Starlette CSRF middleware to all POST forms |
| Celery + Redis task queue | High | Medium | Replace `BackgroundTasks` with durable task queue; enables restart-safe generation, progress reporting, retry logic |
| HTTP-level rate limiting | High | Low | Add `slowapi` middleware; enforce per-user limits on search and generation endpoints |
| Structured logging | Medium | Low | Replace print/implicit logging with `structlog` or `python-json-logger`; enables log aggregation |
| MyPy type checking | Medium | Low | The codebase is already heavily typed; adding `mypy --strict` would catch errors at development time |
| Ruff linting + pre-commit hooks | Medium | Low | Consistent code style; catch bugs before commit |
| Replace inline JS with Alpine.js or module scripts | Medium | High | The 400-line cover letter editor JS is hard to maintain; refactor into modules or Alpine.js components |
| Add account lockout after failed logins | Medium | Low | Track failed attempts in `users` table; lock for 15 minutes after 10 failures |
| Migrate Tailwind from CDN to build pipeline | Low | Medium | Tree-shake unused classes; remove CDN dependency; add PostCSS for production build |
| Move large text columns to MinIO | Low | Medium | Store `extracted_text` and `cv_reconstruction` in object storage; reference by key in DB |

---

## AI Improvements

| Improvement | Impact | Effort | Description |
|---|---|---|---|
| Streaming LLM responses for cover letter | High | Medium | Use OpenAI streaming API to show words appearing in real-time; reduces perceived wait time |
| Async parallel LLM calls | High | Medium | Run job normalization and fit analysis in parallel where possible; reduce total generation time |
| Automatic eval regression detection | High | Medium | Compare new LLM output structure against previous versions in eval logs; alert on schema drift |
| User feedback loop on letter quality | High | Medium | Allow users to rate generated letters (thumbs up/down); aggregate feedback for prompt tuning |
| Multi-turn cover letter refinement | Medium | High | Let users chat with the AI to refine the letter iteratively instead of fixed regeneration |
| Local LLM for cover letter (privacy) | Medium | High | Route cover letter generation through Ollama to avoid sending job data to OpenAI |
| Prompt A/B testing framework | Medium | Medium | Systematically compare prompt versions using eval logs and user rating data |
| Interview preparation AI | Medium | Medium | Use job normalization schema to generate likely interview questions + suggested answers |
| Keyword match score | Low | Low | Compare candidate profile skills against job's `ats_keywords` and display a match percentage |

---

## Architecture Improvements

| Improvement | Impact | Effort | Description |
|---|---|---|---|
| Celery + Redis task queue | High | Medium | Replaces `BackgroundTasks`; enables durable tasks, retries, progress reporting |
| Docker containerise the FastAPI app | High | Low | Add `Dockerfile` for the app itself; enables consistent deployment and CI |
| CI/CD pipeline (GitHub Actions) | High | Low | Run migrations, tests, and linting on each PR; enforce code quality gates |
| Production configuration hardening | High | Low | Enforce `HTTPS_ONLY`, `SAME_SITE=strict`, `DEBUG=false`; separate prod `.env` management |
| Database connection pooling (PgBouncer) | Medium | Medium | Prevent connection exhaustion under concurrent load |
| Reverse proxy (Nginx) | Medium | Low | Handle HTTPS termination, static file serving, compression |
| Read replica for analytics queries | Low | High | Separate dashboard/stats queries from write path |

---

## UX Improvements

| Improvement | Impact | Effort | Description |
|---|---|---|---|
| Fix stuck PENDING cover letters UI | High | Low | Show "retry" button for cover letters that have been PENDING > N minutes |
| Real-time generation progress bar | High | Medium | Show which call is in progress (Analysing → Writing → Verifying) instead of generic spinner |
| Cover letter version history UI | Medium | Low | The `cover_letter_snapshots` table already exists; build a UI to browse and restore previous versions |
| Search result relevance sorting | Medium | Medium | Sort job results by keyword match against profile's target_role and hard_skills |
| In-line tracker status updates | Medium | Low | Use HTMX to update tracker status without page reload |
| Keyboard shortcuts in editor | Low | Low | Save (Ctrl+S), toggle edit mode, cycle through templates |
| Mobile-responsive cover letter editor | Low | High | The A4 preview pane is not usable on mobile screens; requires significant layout redesign |
| Onboarding wizard | Medium | Medium | Guide new users through: create profile → upload CV → create search profile → first search |

---

## Scalability Improvements

| Improvement | Impact | Effort | Description |
|---|---|---|---|
| Gunicorn multi-worker deployment | High | Low | Add `gunicorn -w 4 -k uvicorn.workers.UvicornWorker`; routes are already stateless |
| OpenAI batch API for bulk normalization | Medium | Medium | Normalize many jobs in a single batch request (up to 50% cost reduction) |
| CDN for static assets | Low | Low | Serve CSS/JS/images from CDN; reduce app server bandwidth |
| Background task deduplication | Medium | Low | Prevent multiple simultaneous normalizations for the same job (task-key pattern exists in `job_normalization_task.py` but could be strengthened) |
