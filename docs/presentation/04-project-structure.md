# 04 — Project Structure

> **Related documents:** [02-architecture.md](02-architecture.md) | [03-technology-stack.md](03-technology-stack.md)

---

## Repository Tree

```
ai-job-copilot/
│
├── app/                               # FastAPI application package
│   ├── main.py                        # App factory: middleware, router registration, error handlers
│   │
│   ├── api/
│   │   └── routes/                    # HTTP route handlers (thin; delegate to services)
│   │       ├── __init__.py
│   │       ├── auth.py                # Registration, login, logout
│   │       ├── jobs.py                # Job search execution, run display, load-more, history
│   │       ├── cover_letter.py        # Cover letter setup, generate, editor, save, delete, preview
│   │       ├── application_tracker.py # Application status updates and list view
│   │       ├── dashboard.py           # Home page with stats
│   │       ├── documents.py           # CV upload, rename, delete, extraction trigger
│   │       ├── search_profiles.py     # CRUD for search filter sets
│   │       ├── profile.py             # User profile page
│   │       ├── pages.py               # Static pages (privacy, terms, about)
│   │       └── health.py              # GET /health endpoint
│   │
│   ├── services/                      # Business logic and external integrations
│   │   ├── auth_service.py            # User registration
│   │   ├── job_search_provider.py     # Protocol (interface) definition
│   │   ├── live_job_search_provider.py    # RapidAPI/JSearch HTTP client
│   │   ├── fixture_job_search_provider.py # Mock data for dev/testing
│   │   ├── job_search_policy.py       # Rate limiting + run caching decisions
│   │   ├── job_search_request_mapper.py   # UI filters → API request params
│   │   ├── job_search_response_mapper.py  # API JSON → ORM Job objects
│   │   ├── job_search_persistence.py      # Persist search results to DB
│   │   ├── job_normalization_service.py   # OpenAI structured output: job → schema
│   │   ├── job_normalization_task.py      # Background task runner with deduplication
│   │   ├── cover_letter_service.py        # 3-call OpenAI pipeline + persistence
│   │   ├── document_service.py            # Upload, storage, extraction lifecycle
│   │   ├── document_storage.py            # MinIO S3 abstraction
│   │   ├── document_extraction.py         # PDF → text (embedded / markdown / OCR)
│   │   ├── profile_extraction.py          # 2-step LLM: CV text → CandidateProfile
│   │   ├── signature_processor.py         # Signature image processing
│   │   ├── search_profile_service.py      # Search filter CRUD
│   │   └── application_tracker_service.py # Application status transitions
│   │
│   ├── crud/                          # DB read/write (stateless; never commit)
│   │   ├── user.py
│   │   ├── search_profile.py
│   │   ├── search_run.py
│   │   ├── search_run_job.py
│   │   ├── job.py
│   │   ├── job_normalization.py
│   │   ├── manual_job_posting.py
│   │   ├── application_tracker_entry.py
│   │   ├── cover_letter.py
│   │   ├── cover_letter_snapshot.py
│   │   ├── document.py
│   │   └── profile_information.py
│   │
│   ├── models/                        # SQLAlchemy ORM models
│   │   ├── user.py
│   │   ├── search_profile.py
│   │   ├── search_run.py
│   │   ├── search_run_job.py
│   │   ├── job.py
│   │   ├── job_normalization.py
│   │   ├── manual_job_posting.py
│   │   ├── application_tracker_entry.py
│   │   ├── cover_letter.py
│   │   ├── cover_letter_snapshot.py
│   │   ├── document.py
│   │   └── profile_information.py
│   │
│   ├── schemas/                       # Pydantic request/response models
│   │   ├── user.py                    # UserCreate, UserLogin
│   │   ├── search_profile.py          # SearchProfileBase, filter schemas
│   │   ├── job_search_results.py      # Provider response schema
│   │   ├── job_normalization.py       # JobNormalizationSchema (LLM output)
│   │   ├── application_tracker.py     # Status + date schemas
│   │   ├── cover_letter.py            # CoverLetterContent, LayoutSettings
│   │   ├── document.py                # Document upload schema
│   │   └── profile.py                 # CandidateProfile (extracted from CV)
│   │
│   ├── dependencies/                  # FastAPI DI providers
│   │   ├── auth.py                    # get_current_user() — session guard
│   │   ├── providers.py               # JobSearchProvider factory
│   │   └── templates.py               # Template context builders (flash, feedback)
│   │
│   ├── db/                            # Database infrastructure
│   │   ├── session.py                 # Engine + SessionLocal factory
│   │   └── base.py                    # Declarative base (all models import from here)
│   │
│   ├── core/                          # Application-wide configuration
│   │   ├── config.py                  # Settings class (pydantic-settings, env vars)
│   │   ├── enums.py                   # All shared enums (20+ types)
│   │   └── security.py                # bcrypt hash/verify
│   │
│   └── utils/                         # UI helper utilities
│       ├── application_tracker_ui.py  # Status labels, CSS class maps
│       └── document_ui.py             # Document type/status display helpers
│
├── templates/                         # Jinja2 HTML templates
│   ├── base.html                      # Master layout (nav, footer, dark mode, flash)
│   ├── index.html                     # Landing page
│   ├── auth.html                      # Login / registration
│   ├── dashboard.html                 # Home with stats and quick actions
│   ├── profile.html / profile_edit.html
│   ├── job_search.html                # Search profile list
│   ├── job_results.html               # Search run results
│   ├── search_profile_form.html       # Create/edit filter form
│   ├── search_run_history.html        # Past runs list
│   ├── single_job_analysis.html       # Manual job paste/analysis
│   ├── tracker.html / tracker_detail.html
│   ├── documents.html
│   ├── cover_letter_setup.html        # Initial cover letter setup
│   ├── cover_letter_generating.html   # Polling page
│   ├── cover_letter_preparing.html    # Job prep polling page
│   ├── cover_letter_editor.html       # Rich editor (~1250 lines)
│   ├── cover_letter_weasyprint.html   # PDF export template
│   ├── cover_letter_variants/         # Template design variants
│   │   ├── cover_letter_classic.html
│   │   ├── cover_letter_modern.html
│   │   ├── cover_letter_compact.html
│   │   ├── _content.html              # Shared content structure
│   │   └── _macros.html               # Jinja2 macros for repeated blocks
│   └── _*.html                        # HTMX partial templates (spinners, fragments)
│
├── static/                            # Static assets
│   ├── css/
│   │   ├── dev-ui.css                 # Custom components, status badges, button styles
│   │   └── cover_letter/              # Document styling system
│   │       ├── base.css               # DIN 5008 A4 geometry, CSS custom properties
│   │       ├── classic.css / modern.css / compact.css
│   │       ├── print.css              # Browser print rules
│   │       └── weasyprint.css         # WeasyPrint PDF overrides
│   └── hero.png
│
├── prompts/                           # LLM prompt definitions (versioned)
│   ├── cover_letter_generation.py     # 908 lines: schemas, message builders, tone/industry configs
│   ├── job_normalization.py           # Versioned job extraction prompts (v1, v2)
│   ├── profile_extraction.py          # CV structured extraction prompts (step2_v1/v2/v3)
│   └── profile_extraction_step1.py    # Step 1 text reconstruction prompt
│
├── evals/                             # LLM output audit logs
│   ├── job_normalizations.jsonl       # Appended after every normalization call
│   └── profile_extractions.jsonl      # Appended after every profile extraction
│
├── alembic/                           # Database migration management
│   ├── versions/                      # 15 migration files (chronological schema history)
│   ├── env.py                         # Migration environment config
│   └── script.py.mako                 # Migration file template
│
├── fixtures/                          # Mock data for FixtureJobSearchProvider
│
├── docs/                              
│   └── presentation/                  # ← This documentation package
│
├── compose.yaml                       # Docker Compose (PostgreSQL, MinIO, Ollama)
├── alembic.ini                        # Alembic configuration
├── requirements.txt                   # Python dependencies (56 packages)
├── README.md                          # Project summary / user manual
└── .env                               # Runtime secrets (not committed)
```

---

## Directory Purpose Summary

| Directory | Core Responsibility |
|---|---|
| `app/api/routes/` | **API layer** — HTTP entry points, form parsing, template rendering |
| `app/services/` | **Business logic + AI** — all LLM calls, external API calls, transaction ownership |
| `app/crud/` | **Database access** — thin, composable read/write functions |
| `app/models/` | **Domain model** — SQLAlchemy ORM table definitions |
| `app/schemas/` | **Validation contracts** — Pydantic models for input and LLM output |
| `app/dependencies/` | **Cross-cutting concerns** — auth, provider selection, template context |
| `app/core/` | **Configuration and utilities** — settings, enums, security |
| `app/db/` | **DB infrastructure** — engine, session factory, declarative base |
| `templates/` | **UI layer** — Jinja2 HTML pages and HTMX fragments |
| `static/` | **Assets** — CSS and images |
| `prompts/` | **AI prompt engineering** — versioned LLM prompt configurations |
| `evals/` | **AI quality audit** — JSONL logs of all LLM outputs |
| `alembic/versions/` | **Schema history** — 15 migrations from initial to current schema |

---

## Key File Highlights

### Core Business Logic
- `app/services/cover_letter_service.py` — the largest service (709 lines); orchestrates the full cover letter lifecycle
- `app/services/job_search_policy.py` — decision engine for rate limiting and run caching (247 lines)
- `app/services/job_normalization_service.py` — caching layer + LLM call for structured job data

### AI Logic
- `prompts/cover_letter_generation.py` — 908-line prompt configuration: schemas, tone parameters, industry lexicons, message builders
- `app/services/profile_extraction.py` — 2-step CV extraction pipeline
- `app/services/job_normalization_service.py` — single-call structured output

### API Layer
- `app/api/routes/cover_letter.py` — most complex route file; handles setup, generation, polling, editing, deletion
- `app/api/routes/jobs.py` — search execution, pagination, history

### UI Layer
- `templates/cover_letter_editor.html` — ~1250 lines; the most sophisticated template with contentEditable editing, HTMX live preview, JS content sync, navigation guards
- `templates/base.html` — master layout with dark mode detection, session-aware navigation, flash message rendering

### Database Layer
- `app/db/session.py` — engine and `SessionLocal` factory
- `alembic/versions/` — 15 files; the authoritative history of every schema change
