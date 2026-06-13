# Hire Hero - AI Application Assistant

![Startseite](screenshots/index_page.png)

An AI-powered job search and application management assistant for German-speaking job seekers. Search for relevant positions, analyze them, track your applications, and generate personalised, professional cover letters — all in one place.

Built with **FastAPI**, **PostgreSQL**, **OpenAI**, and **HTMX**.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
  - [1. Clone the repository](#1-clone-the-repository)
  - [2. Configure environment variables](#2-configure-environment-variables)
  - [3. Start infrastructure services](#3-start-infrastructure-services)
  - [4. Install dependencies](#4-install-dependencies)
  - [5. Run database migrations](#5-run-database-migrations)
  - [6. Start the development server](#6-start-the-development-server)
- [Environment Variables](#environment-variables)
- [Running Tests](#running-tests)
- [Job Search Providers](#job-search-providers)
- [Project Structure](#project-structure)
- [AI Components](#ai-components)
- [Document Storage](#document-storage)
- [Database Migrations](#database-migrations)
- [Documentation](#documentation)

---

## Features

- **Profile-based job search** — Save named filter sets and re-run them with one click. Results are cached per profile per day; a "load more" mechanism fetches additional pages without re-executing the search.
- **AI job analysis** — Each job description is normalised by an LLM into a structured schema: required skills, ATS keywords, industry group, hierarchy level, and contact details.
- **Application tracker** — Follow every application through a defined lifecycle: Saved → Applied → Interview → Offer / Rejected / Withdrawn, with per-stage date tracking.
- **CV upload and profile extraction** — Upload a PDF CV; a two-step LLM pipeline extracts your full candidate profile (contact details, work history, skills, education) and uses it to pre-populate every cover letter. In production, Ollama (Qwen2.5-7b) can be self-hosted on the same server as the application, on a separate GPU-accelerated instance within a private network, or as a dedicated container or VM at any cloud provider (e.g. Hetzner, OVHcloud, AWS, Azure) — ensuring that sensitive CV data is processed exclusively within your own infrastructure and never transmitted to an external API. Document generation calls made after extraction (cover letters, job analysis) do not include this personal data.
- **AI cover letter generation** — A three-call LLM pipeline produces a tailored, tone-appropriate, compliance-checked cover letter. Choose between four tones (formal, factual, warm, casual), three templates (classic, modern, compact), and German or English output. Private contact data is injected post-generation and never sent to the LLM.
- **In-browser editor** — Review and edit the generated letter in an A4 live-preview editor. Change the template, font, colour scheme, or spacing in real time, insert your signature, then download a PDF.
- **Document management** — All uploaded and generated files are stored in S3-compatible object storage (MinIO) with presigned download URLs.
- **Dark mode** — System-preference-aware theme, persisted to `localStorage`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Templating | Jinja2 |
| Frontend | Tailwind CSS (CDN), HTMX, Alpine.js |
| Database | PostgreSQL 16, SQLAlchemy 2.0, Alembic |
| AI — generation | OpenAI API (`gpt-5-mini`) |
| AI — CV extraction | OpenRouter / Ollama (`qwen2.5-7b`) |
| Object storage | MinIO (S3-compatible) |
| Infrastructure | Docker Compose |
| Auth | Starlette `SessionMiddleware` (signed cookie) |
| PDF export | WeasyPrint |
| Testing | pytest, pytest-mock |

---

## Architecture

The application is a **modular monolith** with a strict four-layer structure:

```
Browser (Jinja2 + HTMX)
    ↓ HTTP form submissions
API Layer  (app/api/routes/)       — thin route handlers; delegate to services
    ↓
Service Layer  (app/services/)     — business logic, LLM calls, external APIs
    ↓
CRUD Layer  (app/crud/)            — stateless DB read/write functions
    ↓
PostgreSQL                         — primary data store
```

Long-running AI operations (cover letter generation, CV extraction) are deferred to FastAPI `BackgroundTasks`. The browser polls a status endpoint via HTMX every two seconds until the task completes.

---

## Prerequisites

- **Python** 3.11 or newer
- **Docker** and **Docker Compose** (for PostgreSQL, MinIO, and optionally Ollama)
- **OpenAI API key** — required for job normalisation and cover letter generation
- **RapidAPI / JSearch key** — required only when `JOB_SEARCH_PROVIDER=live`; the default fixture mode works without it
- **OpenRouter API key** — optional; used for CV extraction (falls back to local Ollama if omitted)

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/alina-geissler/ai-job-copilot.git
cd ai-job-copilot
```

### 2. Configure environment variables

Copy the example file and fill in the required values:

```bash
cp .env.example .env
```

The minimum required values to run the app in development mode (fixture job search, no live API):

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ai_job_copilot
SESSION_SECRET_KEY=change-me-to-a-long-random-string
OPENAI_API_KEY=sk-...
STORAGE_ENDPOINT_URL=http://localhost:9000
```

See [Environment Variables](#environment-variables) for the full reference.

### 3. Start infrastructure services

```bash
docker compose up -d
```

This starts:
- **PostgreSQL 16** on port `5432`
- **MinIO** on ports `9000` (API) and `9001` (admin console — http://localhost:9001)
- **Ollama** on port `11434` (optional local LLM for CV extraction)

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

> A virtual environment is strongly recommended: `python -m venv .venv && source .venv/bin/activate` (Linux/macOS) or `.venv\Scripts\activate` (Windows).

### 5. Run database migrations

```bash
alembic upgrade head
```

### 6. Start the development server

```bash
uvicorn app.main:app --reload
```

The application is now available at **http://localhost:8000**.

---

## Environment Variables

All variables are loaded from `.env` via `pydantic-settings`. Variables marked **required** have no default and must be set.

### Application

| Variable | Required | Default | Description |
|---|---|---|---|
| `DEBUG` | No | `True` | Enable debug mode |

### Database

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | **Yes** | — | SQLAlchemy connection string, e.g. `postgresql+psycopg://postgres:postgres@localhost:5432/ai_job_copilot` |

### Session / Auth

| Variable | Required | Default | Description |
|---|---|---|---|
| `SESSION_SECRET_KEY` | **Yes** | — | Secret used to sign session cookies — use a long, random string |
| `SESSION_COOKIE_NAME` | No | `ai_job_copilot_session` | Cookie name |
| `SESSION_MAX_AGE_SECONDS` | No | `28800` (8 h) | Cookie max-age |
| `SESSION_SAME_SITE` | No | `lax` | Cookie `SameSite` policy (`lax`, `strict`, `none`) |
| `SESSION_HTTPS_ONLY` | No | `False` | Set to `True` in production (HTTPS-only cookie) |
| `SESSION_IDLE_TIMEOUT_SECONDS` | No | `1800` (30 min) | Idle session expiry |
| `SESSION_ABSOLUTE_TIMEOUT_SECONDS` | No | `28800` (8 h) | Absolute session expiry since login |

### AI — OpenAI

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | **Yes** | — | OpenAI API key — used for job normalisation and cover letter generation |
| `OPENAI_MODEL` | No | `gpt-5-mini` | Model used for all OpenAI calls |

### AI — CV Extraction (OpenRouter / Ollama)

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | No | — | OpenRouter API key for `qwen2.5-7b-instruct`; if omitted, Ollama is used instead |
| `OPENROUTER_API_URL` | No | `https://openrouter.ai/api/v1` | OpenRouter endpoint |
| `LLM_API_URL` | No | `http://localhost:11434/v1` | Local Ollama endpoint (fallback for CV extraction) |
| `LLM_MODEL` | No | `qwen2.5:7b` | Local model name served by Ollama |

### Job Search

| Variable | Required | Default | Description |
|---|---|---|---|
| `JOB_SEARCH_PROVIDER` | No | `fixture` | `fixture` — use local mock data; `live` — call the RapidAPI/JSearch endpoint |
| `JOB_API_BASE_URL` | If `live` | — | JSearch API base URL, e.g. `https://jsearch.p.rapidapi.com` |
| `JOB_API_KEY` | If `live` | — | RapidAPI authentication key |
| `JOB_API_HOST` | If `live` | — | RapidAPI host header value, e.g. `jsearch.p.rapidapi.com` |
| `JOB_API_TIMEOUT_CONNECT` | No | `5.0` | TCP connection timeout (seconds) |
| `JOB_API_TIMEOUT_READ` | No | `30.0` | Response read timeout (seconds) |
| `JOB_API_TIMEOUT_WRITE` | No | `10.0` | Request write timeout (seconds) |
| `JOB_API_TIMEOUT_POOL` | No | `5.0` | Connection pool timeout (seconds) |

### Document Storage (MinIO / S3)

| Variable | Required | Default | Description |
|---|---|---|---|
| `STORAGE_ENDPOINT_URL` | No | — | MinIO or S3 endpoint, e.g. `http://localhost:9000` |
| `STORAGE_ACCESS_KEY` | No | `minioadmin` | Storage access key |
| `STORAGE_SECRET_KEY` | No | `minioadmin` | Storage secret key |
| `STORAGE_BUCKET_NAME` | No | `ai-job-copilot-documents` | Bucket for all uploaded and generated files |
| `STORAGE_REGION` | No | `us-east-1` | Storage region |
| `MAX_UPLOAD_SIZE_BYTES` | No | `10485760` (10 MB) | Maximum file upload size |

---

## Running Tests

The test suite contains 162 tests across three layers: unit (73), integration (46), and end-to-end (43).

### Prerequisites

The integration and e2e tests require a separate PostgreSQL database. Create it once:

```bash
# Using psql directly (Docker)
docker exec -it ai-job-copilot-db-1 psql -U postgres -c "CREATE DATABASE ai_job_copilot_test;"
```

### Run the tests

```bash
# Full suite
pytest

# Individual layers
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# With verbose output
pytest -v --tb=short
```

The test database is left clean after each run — every test rolls back its transaction at teardown.

---

## Job Search Providers

The job search backend is selected by `JOB_SEARCH_PROVIDER`:

| Value | Description | API Key Needed |
|---|---|---|
| `fixture` | Returns pre-recorded results from `fixtures/job_search_response.json`. All filter values are accepted but ignored. | No |
| `live` | Calls the [JSearch API on RapidAPI](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch). Filters are mapped to API parameters. | Yes (`JOB_API_KEY`) |

Use `fixture` during development to avoid API costs and rate limits.

---

## Project Structure

```
ai-job-copilot/
├── app/
│   ├── main.py                   # App factory: middleware, routers, error handlers
│   ├── api/routes/               # HTTP route handlers (11 modules)
│   ├── services/                 # Business logic and external integrations (19 modules)
│   ├── crud/                     # DB read/write functions — never commit (13 modules)
│   ├── models/                   # SQLAlchemy ORM models (13 tables)
│   ├── schemas/                  # Pydantic request/response models
│   ├── dependencies/             # FastAPI DI: auth guard, provider factory, template context
│   ├── db/                       # Engine and session factory
│   ├── core/                     # Settings, enums, password hashing
│   └── utils/                    # UI helper utilities
├── templates/                    # Jinja2 HTML templates (~33 files)
├── static/                       # CSS and images
├── prompts/                      # Versioned LLM prompt definitions
├── evals/                        # LLM output audit logs (JSONL)
├── alembic/versions/             # Database migration history (15 files)
├── tests/
│   ├── conftest.py               # Shared fixtures (engine, db session, client, auth)
│   ├── unit/                     # Pure-function tests — no DB (73 tests)
│   ├── integration/              # CRUD and service tests against test DB (46 tests)
│   └── e2e/                      # Route tests via FastAPI TestClient (43 tests)
├── fixtures/                     # Pre-recorded API response for fixture provider
├── docs/presentation/            # Full technical documentation package
├── compose.yaml                  # Docker Compose: PostgreSQL, MinIO, Ollama
├── pyproject.toml                # pytest configuration
├── requirements.txt
└── .env                          # Local environment variables (not committed)
```

---

## AI Components

The application integrates AI in three independent pipelines:

### Job Normalisation
A single OpenAI Responses API call (`gpt-5-mini`, `reasoning=medium`) converts a raw job description into a structured schema: title, company, contact person and gender, industry group, hierarchy level, responsibilities, required and preferred competencies, technical skills, and ATS keywords. Results are cached in the database — each job is normalised at most once.

### Cover Letter Generation
A three-call pipeline produces a tailored cover letter:
1. **Analysis** — evaluates candidate–job fit; produces a `fit_plan` with keywords, evidence points, gap strategies, and must-include / must-avoid rules
2. **Writing** — generates the letter body (330–380 words, hard limit 2,300 characters) using tone, industry, and hierarchy parameters; one automatic compression retry if the limit is exceeded
3. **Verification** — audits the letter for user-specified no-go topics including paraphrases and euphemisms; one remedial rewrite if violations are found

Contact details (name, email, phone, address, signature) are injected from the user's profile **after** all LLM calls and are never included in any API request.

### CV Profile Extraction
A two-step pipeline using `qwen2.5-7b-instruct` (via OpenRouter or local Ollama):
1. **Reconstruction** — rewrites raw PDF text as clean, structured plain text grouped by section
2. **Extraction** — maps the clean text to a typed `CandidateProfile` schema covering contact details, work history, education, skills, languages, and more

#### Self-hosting the CV extraction model

CV profile extraction runs through Ollama (Qwen2.5-7b) rather than a proprietary cloud API. For production, Ollama can be deployed on the same server as the FastAPI application, on a separate GPU-accelerated instance within the same private network, or as a dedicated container or VM with any cloud provider (e.g. Hetzner, OVHcloud, AWS, Azure). This keeps PII within your own infrastructure. Subsequent LLM calls for cover letter generation and job analysis are made to the OpenAI API, but those calls never include the personal data extracted from the CV; contact fields are injected locally after generation completes.

---

## Document Storage

Uploaded CVs and generated files are stored in MinIO (S3-compatible). The Docker Compose service starts MinIO automatically. The admin console is available at http://localhost:9001 with the default credentials `minioadmin` / `minioadmin`.

To use AWS S3 instead, set `STORAGE_ENDPOINT_URL` to your S3 endpoint and update the access credentials — the application uses the `boto3` S3 API, which is identical for both.

---

## Database Migrations

Migrations are managed with Alembic.

```bash
# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Create a new migration after changing a model
alembic revision --autogenerate -m "describe the change"

# Show current migration state
alembic current
```

> **Note:** Never apply or create migrations in a shared environment without reviewing the generated file first. The `--autogenerate` output should always be inspected before running.

---

## Documentation

A complete technical documentation package is available under `docs/presentation/`. It was created for the presentation of this capstone project and covers architecture, AI pipelines, security, engineering decisions, and more.

| File | Contents |
|---|---|
| `01-executive-summary.md` | Project overview, features, key metrics |
| `02-architecture.md` | Layered architecture, request lifecycle, diagrams |
| `03-technology-stack.md` | Every technology with rationale |
| `04-project-structure.md` | Annotated repository tree |
| `05-features.md` | All features with implementation details |
| `06-user-flows.md` | User journeys with sequence diagrams |
| `07-api-analysis.md` | All ~40 endpoints with request/response details |
| `08-database-analysis.md` | All 13 tables, ER diagram, migration history |
| `09-ai-analysis.md` | Deep dive into all three AI pipelines |
| `10-security.md` | Auth, session management, risks, mitigations |
| `11-engineering-practices.md` | Design patterns, SOLID analysis, maintainability |
| `12-testing.md` | Test suite structure, infrastructure, and coverage |
| `13-performance.md` | Request latency profile, scalability analysis, concurrency limits |
| `14-engineering-decisions.md` | Key trade-offs with rationale |
| `15-future-improvements.md` | Prioritised improvements ranked by impact and effort |
| `16-v2-roadmap.md` | V2 product evolution: quick wins, medium-term features, long-term vision |
| `17-presentation-plan.md` | Slide-by-slide content plan for the capstone presentation |
| `18-defense-preparation.md` | 20 likely viva questions with technical answers |
| `19-glossary.md` | Definitions of technical and domain terms used in the codebase |
| `20-job-search-analysis.md` | Complete job search subsystem analysis |
| `assets/` | Standalone Mermaid diagrams (architecture, ER, sequence) |
