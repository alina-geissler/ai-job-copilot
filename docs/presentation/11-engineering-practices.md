# 11 — Software Engineering Practices

> **Related documents:** [02-architecture.md](02-architecture.md) | [14-engineering-decisions.md](14-engineering-decisions.md)

---

## Design Patterns Identified

### 1. Strategy Pattern — Job Search Provider

**Where:** `app/services/job_search_provider.py`, `app/dependencies/providers.py`

The `JobSearchProvider` Protocol defines a single interface that both concrete providers implement:

```python
# app/services/job_search_provider.py
class JobSearchProvider(Protocol):
    def search(self, request: JobSearchRequest) -> JobSearchResult: ...
```

Two concrete strategies:
- `LiveJobSearchProvider` — RapidAPI/JSearch HTTP calls
- `FixtureJobSearchProvider` — hardcoded mock data

Selected at startup via `JOB_SEARCH_PROVIDER` env var; injected via `Depends(get_job_search_provider)`. Route handlers reference only the protocol — they never know which implementation they received.

**Benefit:** Enables development and testing without hitting the live API or consuming credits.

---

### 2. Repository Pattern — CRUD Layer

**Where:** `app/crud/` (13 modules)

Each CRUD module acts as a repository: a collection of focused, stateless data access functions for one domain entity. Functions:
- Accept a `db: Session` parameter (session passed in by the caller)
- Perform a single, focused DB operation
- Never commit transactions
- Return ORM objects or `None`

Example:
```python
# app/crud/user.py
def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()
```

This is a lightweight application of the Repository pattern: the service layer calls the CRUD functions without knowing the underlying SQL, and CRUD functions are independently reusable.

---

### 3. Dependency Injection — FastAPI `Depends()`

**Where:** `app/dependencies/`, all route files

FastAPI's `Depends()` system is used for:
- **Auth guard:** `Depends(get_current_user)` — validates session, returns `User` object
- **Provider selection:** `Depends(get_job_search_provider)` — returns correct strategy
- **Template context:** `Depends(build_feedback_query)` — assembles template context

This is proper DI: route handlers declare their dependencies via function parameters; FastAPI resolves them at request time. No global state, no singletons.

---

### 4. Template Method Pattern (Prompt Pipeline)

**Where:** `app/services/cover_letter_service.py`

The cover letter generation pipeline is structured as a fixed template with configurable steps:
- `_run_generation_task()` — invariant orchestration order (normalize → analyze → write → verify → inject → persist)
- Each sub-call (`_llm_generate`, `_call_writing`, `_call_with_json_retry`) is a separate private method
- Retry and verification logic is modular and can be adjusted without changing the outer flow

---

### 5. Provider / Factory Pattern — Storage and LLM Client

**Where:** `app/services/document_storage.py`, `app/services/job_normalization_service.py`

`DocumentStorage` abstracts MinIO operations — the service layer calls generic `put_object`, `get_object` methods; swapping to AWS S3 would require only changing the endpoint URL.

`_build_client()` in normalization and extraction services creates a configured `openai.OpenAI` client with custom timeouts and base URL — this is a factory pattern, enabling different backend endpoints (OpenAI, OpenRouter, local Ollama) with the same calling code.

---

### 6. Builder Pattern — Prompt Message Construction

**Where:** `prompts/cover_letter_generation.py`

Message list builders (`build_analysis_messages()`, `build_writing_messages()`, `build_verification_messages()`) assemble the `messages` array for each LLM call from discrete, typed components. This keeps prompt engineering code isolated from the service orchestration code.

---

## Separation of Concerns

| Concern | Layer | Files |
|---|---|---|
| HTTP routing | Route | `app/api/routes/` |
| Business logic | Service | `app/services/` |
| DB access | CRUD | `app/crud/` |
| Prompt engineering | Prompts | `prompts/` |
| LLM orchestration | Service | `cover_letter_service.py`, `job_normalization_service.py` |
| Configuration | Core | `app/core/config.py` |
| Auth validation | Dependency | `app/dependencies/auth.py` |
| Template rendering | Presentation | `templates/` |

No layer violates its boundary: routes do not query the DB directly; CRUD modules do not call external APIs; templates do not contain business logic.

---

## SOLID Principles Analysis

| Principle | Assessment | Evidence |
|---|---|---|
| **Single Responsibility** | Strong | Each service module has one clear purpose (e.g., `job_search_policy.py` only decides; `job_search_persistence.py` only persists) |
| **Open/Closed** | Partial | Provider strategy allows new search backends without changing existing code; LLM prompts are versioned (new version = new dict entry, not modification) |
| **Liskov Substitution** | Strong | `LiveJobSearchProvider` and `FixtureJobSearchProvider` are interchangeable via the `Protocol` interface |
| **Interface Segregation** | Partial | `JobSearchProvider` protocol has a single method (minimal interface); other services don't define formal interfaces |
| **Dependency Inversion** | Strong | Route handlers depend on the `JobSearchProvider` Protocol abstraction, not on concrete implementations; injected via DI |

---

## Reusability

| Mechanism | Example |
|---|---|
| CRUD functions | `crud/job.py` functions called by both normalization and cover letter services |
| Enums | `app/core/enums.py` centralises all application-wide enum types (20+ types, shared across models, services, templates) |
| Prompt builders | Message builder functions in `prompts/cover_letter_generation.py` reused across the 3 calls |
| Jinja2 macros | `templates/cover_letter_variants/_macros.html` defines shared rendering blocks |
| Document storage abstraction | `DocumentStorage` reused by document service and other upload scenarios |

---

## Maintainability

**Strengths:**
- **Consistent naming:** CRUD modules mirror model names (e.g., `models/cover_letter.py` → `crud/cover_letter.py`)
- **Automated test suite:** 162 tests across unit, integration, and e2e layers; savepoint isolation provides fast, reliable runs without manual database cleanup (see [12-testing.md](12-testing.md))
- **Prompt versioning:** Changing a prompt creates a new version key without breaking existing calls; old versions preserved for comparison
- **Eval logging:** `evals/*.jsonl` provide a persistent audit trail for debugging LLM output quality regressions
- **Schema migrations:** 15 Alembic migrations create an auditable, reversible schema history
- **Docstrings:** Sphinx-style docstrings required by `CLAUDE.md` working rules for all modified functions

**Weaknesses:**
- **Inline JS in templates:** The cover letter editor's ~400 lines of inline JavaScript is hard to test, refactor, or reuse
- **Hardcoded German strings:** No i18n layer; adding a second language requires editing every template

> **Resolved:** Structured logging was previously a gap. `python-json-logger` with `RequestLoggingMiddleware` and Langfuse LLM tracing have been implemented. See [03-technology-stack.md](03-technology-stack.md).

---

## Scalability (Architecture Level)

| Dimension | Current State | Scalability Path |
|---|---|---|
| Horizontal scaling | Single process (Uvicorn) | Add Gunicorn with multiple workers; stateless routes support this |
| Background tasks | In-process `BackgroundTasks` | Replace with Celery + Redis for distributed task processing |
| Database | Single PostgreSQL instance | Read replicas for search; connection pooling via PgBouncer |
| LLM throughput | Sequential calls per request | Parallelize independent calls; use OpenAI batch API for bulk normalization |
| File storage | MinIO (S3-compatible) | Drop-in replacement to AWS S3 (same boto3 API) |
