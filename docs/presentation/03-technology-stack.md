# 03 — Technology Stack

> **Related documents:** [02-architecture.md](02-architecture.md) | [09-ai-analysis.md](09-ai-analysis.md) | [14-engineering-decisions.md](14-engineering-decisions.md)

---

## Summary Table

| Technology | Category | Version | Role |
|---|---|---|---|
| Python | Language | 3.11+ | Primary language |
| FastAPI | Backend framework | 0.136.1 | HTTP server, routing, DI |
| Uvicorn | ASGI server | 0.46.0 | Production/dev server |
| Starlette | Middleware | 1.0.0 | Sessions, static files, middleware |
| Jinja2 | Templating | 3.1.6 | Server-rendered HTML |
| Pydantic | Validation | 2.13.3 | Schema validation, settings, LLM output parsing |
| SQLAlchemy | ORM | 2.0.49 | Database access layer |
| Alembic | Migrations | 1.18.4 | Database schema versioning |
| PostgreSQL | Database | 16 | Primary data store |
| psycopg2 | DB driver | binary | PostgreSQL adapter |
| OpenAI SDK | AI client | 2.33.0 | LLM calls (cover letter, normalization) |
| gpt-5-mini | LLM model | — | Cover letter generation + job normalization |
| OpenRouter | AI gateway | — | CV extraction (qwen2.5-7b routing) |
| qwen2.5-7b | LLM model | — | CV profile extraction (Step 1 + 2) |
| Ollama | Local LLM runtime | — | Local model serving (experimental) |
| httpx | HTTP client | 0.28.1 | Job search API calls (with async-compatible timeouts) |
| boto3 | S3 client | — | MinIO document storage |
| MinIO | Object storage | — | S3-compatible document store |
| PyMuPDF (fitz) | PDF processing | — | Embedded text extraction from PDFs |
| pymupdf4llm | Markdown extraction | — | PDF → markdown for LLM input |
| OpenCV | Image processing | headless | OCR fallback for scanned PDFs |
| Pillow | Image library | — | Image manipulation for OCR |
| bcrypt | Cryptography | 5.0.0 | Password hashing |
| python-multipart | Form handling | 0.0.27 | Multipart file upload support |
| python-dotenv | Config | 1.2.2 | `.env` file loading |
| pydantic-settings | Config | 2.14.0 | Typed settings from env vars |
| gender-guesser | NLP utility | — | Gender inference for salutation |
| Tailwind CSS | CSS framework | CDN | Utility-first styling with dark mode |
| HTMX | Frontend library | 1.9.12 | Server-driven dynamic interactions |
| Alpine.js | Frontend library | 3.14.1 | Lightweight reactive state |
| Docker Compose | Infrastructure | — | Local dev service orchestration |
| WeasyPrint | PDF export | — | Server-side HTML → PDF rendering |

---

## Frontend

### Jinja2 (Templating Engine)
- **What:** Python server-side template engine
- **Why:** Integrated with FastAPI's `TemplateResponse`; eliminates the need for a separate frontend build pipeline
- **Role:** Renders all HTML pages; templates extend `base.html` for consistent layout, navigation, and flash messages
- **Key file:** `templates/base.html`

### Tailwind CSS (via CDN)
- **What:** Utility-first CSS framework
- **Why:** Enables rapid, consistent UI development without writing custom CSS for common patterns
- **Role:** Styles every page including dark mode variants (`dark:` prefix classes)
- **Notable:** Used via `https://cdn.tailwindcss.com` — no build step, no PostCSS. This is acceptable for a prototype but would need a build pipeline in production to tree-shake unused classes.
- **Dark mode:** Class-based (`darkMode: 'class'`), toggled by JavaScript, persisted to `localStorage`

### HTMX (v1.9.12)
- **What:** HTML-over-the-wire library — extends HTML with declarative AJAX attributes
- **Why:** Enables dynamic interactions (polling, partial page updates) without writing JavaScript for each case
- **Role:** Powers the background task polling pattern (job analysis spinner, cover letter preparation page), and design-control live preview in the cover letter editor
- **Key attribute patterns:** `hx-get`, `hx-post`, `hx-swap="outerHTML"`, `hx-trigger="every 2s"`, `hx-include`

### Alpine.js (v3.14.1)
- **What:** Minimal declarative JS framework using HTML attributes
- **Why:** Provides reactive state (open/closed toggles) without the weight of Vue/React
- **Role:** Navigation hamburger toggle, collapsible tracker notes, minor state management
- **Key patterns:** `x-data`, `@click`, `x-show`

### Vanilla JavaScript (inline)
- **What:** Plain browser JavaScript embedded in `<script>` blocks in templates
- **Why:** No build system exists; inline JS avoids adding a module bundler
- **Role:** Cover letter editor content sync, unsaved-changes detection, PDF export orchestration, signature management
- **Notable:** The cover letter editor (`templates/cover_letter_editor.html`) contains ~400 lines of inline JS — the most complex frontend code in the project

---

## Backend

### FastAPI (0.136.1)
- **What:** Modern Python web framework built on Starlette + Pydantic
- **Why:** Async support, native dependency injection, automatic OpenAPI docs, first-class Pydantic integration
- **Role:** HTTP server, route registration, middleware, form validation, dependency injection
- **Key file:** `app/main.py`

### Starlette (SessionMiddleware)
- **What:** ASGI toolkit underlying FastAPI
- **Why:** Provides battle-tested session management
- **Role:** Cookie-based sessions store `user_id`, `created_at`, `last_seen`, `is_authenticated`; SessionMiddleware is configured with `SECRET_KEY`, `same_site`, `https_only` settings
- **Key file:** `app/main.py` (middleware setup), `app/dependencies/auth.py`

### Pydantic (2.13.3)
- **What:** Python data validation library using type annotations
- **Why:** FastAPI forms, LLM structured output parsing, environment settings
- **Role:** (1) `BaseSettings` for typed config (`app/core/config.py`); (2) form validation schemas (`app/schemas/`); (3) LLM output schema (`JobNormalizationSchema`, `CandidateProfile`)

### bcrypt (5.0.0)
- **What:** Adaptive password hashing library
- **Why:** Industry standard for secure password storage — cost factor adjusts over time
- **Role:** Hashes passwords on registration; verifies on login
- **Key file:** `app/core/security.py`

---

## Database

### PostgreSQL 16
- **What:** Relational database with advanced features (JSONB, arrays, full-text search)
- **Why:** JSONB columns allow flexible structured storage for evolving LLM outputs without schema changes; array columns for multi-value filters; ACID transactions
- **Role:** Primary data store for all application data

### SQLAlchemy (2.0.49)
- **What:** Python ORM and SQL toolkit
- **Why:** Type-safe database access; integrates with Alembic for migrations; supports async sessions
- **Role:** ORM models in `app/models/`; session factory in `app/db/session.py`; declarative base in `app/db/base.py`

### Alembic (1.18.4)
- **What:** Database migration tool for SQLAlchemy
- **Why:** Version-controlled schema evolution; supports `--autogenerate` from model changes
- **Role:** 15 migration files in `alembic/versions/` track the full schema history from initial tables to current state

---

## AI Components

### OpenAI SDK (2.33.0) + gpt-5-mini
- **What:** Official Python SDK for OpenAI API; `gpt-5-mini` is a reasoning-capable model
- **Why:** Structured output support (Responses API with `text.format`), high quality reasoning for complex tasks like cover letter generation
- **Role:**
  - Job normalization: single structured output call, `reasoning="medium"`, `max_output_tokens=16000`
  - Cover letter: 3-call pipeline, `reasoning="medium"` (Analysis), `reasoning="low"` (Writing, Verification)
- **Key files:** `app/services/job_normalization_service.py`, `app/services/cover_letter_service.py`, `prompts/`

### OpenRouter + qwen2.5-7b-instruct
- **What:** API gateway routing to open-source models; qwen2.5-7b is a compact multilingual LLM
- **Why:** Lower cost than GPT for the high-volume CV extraction step; experimental local option (Ollama) available
- **Role:** 2-step CV profile extraction pipeline: Step 1 text reconstruction, Step 2 structured parse
- **Key file:** `app/services/profile_extraction.py`

### Ollama (local)
- **What:** Local LLM serving runtime
- **Why:** Zero API cost; privacy (CV data never leaves the machine); used for experimentation
- **Role:** Serves `qwen2.5:7b` locally as an alternative to OpenRouter for CV extraction (currently OpenRouter is active for testing)
- **Docker service:** Defined in `compose.yaml`, port 11434

---

## Storage

### MinIO (S3-compatible)
- **What:** Self-hosted S3-compatible object storage
- **Why:** Full control over document data; same API as AWS S3 (boto3 client reusable for cloud migration); no third-party data sharing for sensitive CV files
- **Role:** Stores uploaded PDFs and generated documents; presigned URLs for browser downloads
- **Key files:** `app/services/document_storage.py`

### boto3
- **What:** AWS SDK for Python
- **Why:** boto3 works with any S3-compatible API, including MinIO — no separate MinIO SDK needed
- **Role:** `put_object`, `get_object`, `generate_presigned_url` calls against MinIO

---

## Infrastructure

### Docker Compose (`compose.yaml`)
- **What:** Multi-container Docker application definition
- **Why:** Reproducible local development environment with a single command (`docker compose up -d`)
- **Services:**
  - `db`: PostgreSQL 16 on port 5432
  - `minio`: MinIO on ports 9000 (API) and 9001 (admin console)
  - `ollama`: Ollama on port 11434

### No CI/CD
- **Confirmed:** No GitHub Actions, no Dockerfile for the application itself, no deployment pipeline
- **Current state:** Development only — run via `uvicorn app.main:app --reload` locally

### No Monitoring / Logging Infrastructure
- **Confirmed:** No structured logging, no Prometheus/Grafana, no Sentry
- **Current state:** Standard Python logging (inferred); no observability tooling
- See [15-future-improvements.md](15-future-improvements.md) for recommendations
