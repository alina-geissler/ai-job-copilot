# 12 — Testing and Quality Assurance

> **Related documents:** [15-future-improvements.md](15-future-improvements.md)

---

## Current State: No Formal Test Suite

**Confirmed:** There are no unit tests, integration tests, or end-to-end tests in the repository. No test runner configuration files (`pytest.ini`, `setup.cfg`, `pyproject.toml`) were found. No `tests/` directory exists.

This is acknowledged in `CLAUDE.md`: *"No test suite exists yet."*

---

## Substitute Quality Mechanisms

Despite the absence of automated tests, several mechanisms exist to support quality assurance:

---

### 1. Fixture Provider — Manual Integration Test Harness

**File:** `app/services/fixture_job_search_provider.py`
**Directory:** `fixtures/` (mock job data)

The `FixtureJobSearchProvider` returns hardcoded job data when `JOB_SEARCH_PROVIDER=fixture` is set. This serves as a manual integration harness:
- Allows the full job search → display → tracker → cover letter workflow to be exercised without hitting the live API
- Eliminates API cost and rate limit consumption during development
- The fixture data represents realistic job postings for UI and flow testing

---

### 2. Eval Logs — LLM Output Audit Trail

**Files:** `evals/job_normalizations.jsonl`, `evals/profile_extractions.jsonl`

Every LLM call appends a timestamped JSONL record with:
- The model used
- The prompt version
- The input job/profile identifier
- The full structured output

**Role:** These logs function as a lightweight regression detection mechanism — a developer can review recent LLM outputs to detect quality degradation, unexpected formats, or hallucinated content.

**Limitation:** These are append-only flat files. There is no automated analysis, no threshold alerting, and no diff-based regression detection.

---

### 3. Prompt Versioning — Safe Prompt Evolution

**Files:** `prompts/job_normalization.py`, `prompts/profile_extraction.py`, `prompts/cover_letter_generation.py`

Each prompt module maintains a `VERSIONS` dictionary. When a prompt is improved, a new version key is added (old versions preserved). The service code selects a specific version.

**Role:** This is a form of test-driven prompt engineering — old versions can be re-run against existing eval logs to compare outputs before committing to the new version.

---

### 4. Pydantic Schema Validation — Runtime Contract Enforcement

**Files:** `app/schemas/`, `app/services/` (everywhere `parse()` is called)

Pydantic models enforce type correctness and required fields at runtime:
- Form inputs are validated before reaching service code
- LLM outputs are validated via `beta.chat.completions.parse` and `text.format` structured output
- If the LLM returns an invalid schema, Pydantic raises a `ValidationError` rather than silently storing corrupt data

This is not a test, but it is a quality gate that catches structural errors at the boundary.

---

### 5. Alembic Migrations — Schema Correctness

**Directory:** `alembic/versions/`

The 15-file migration history ensures that schema changes are applied in a controlled, reversible sequence. Running `alembic upgrade head` on a fresh database produces a consistent, verified schema. This prevents "works on my machine" database inconsistencies.

---

## What Should Be Tested

The following areas have the highest risk and would benefit most from automated tests:

| Area | Suggested Test Type | Key Scenarios |
|---|---|---|
| `job_search_policy.py` | Unit tests | All 4 decision outcomes; daily limit boundary conditions; profile-changed detection |
| `cover_letter_service.py` | Integration tests (mocked OpenAI) | Generation pipeline states (PENDING → COMPLETED → FAILED); retry logic; verification compliance |
| `job_normalization_service.py` | Unit + mock LLM | Cache hit/miss; schema validation; eval log appending |
| `auth.py` dependency | Unit tests | Session expiry (idle/absolute); invalid user_id; missing session keys |
| `document_extraction.py` | Unit tests | Each extraction method (embedded, markdown, OCR); corrupt PDF handling |
| `profile_extraction.py` | Integration tests (mocked OpenRouter) | 2-step pipeline; schema validation; extraction_error handling |
| CRUD functions | Integration tests (test DB) | Upsert behaviour; unique constraint violations; cascade deletes |
| Route handlers | End-to-end (FastAPI TestClient) | Form submission → redirect → flash message; HTMX polling lifecycle |

---

## Recommended Testing Stack

```bash
# Core testing framework
pip install pytest pytest-asyncio httpx

# FastAPI test client (built into httpx)
# Use: from fastapi.testclient import TestClient

# LLM mocking
pip install pytest-mock

# Database: use a separate test PostgreSQL instance
# Configure TEST_DATABASE_URL in .env.test
```

**Key fixture patterns:**
```python
# Pytest fixture for database session
@pytest.fixture
def db():
    engine = create_engine(settings.test_database_url)
    with SessionLocal(bind=engine) as session:
        yield session
        session.rollback()

# Mock OpenAI client
@pytest.fixture
def mock_openai(mocker):
    return mocker.patch("app.services.cover_letter_service.openai.OpenAI")
```

---

## Linting and Formatting

**Confirmed:** No linting or formatting configuration files were found (`pyproject.toml`, `.flake8`, `.ruff.toml`, `.black`, `mypy.ini`).

**Recommended additions:**
- `ruff` for fast linting + formatting (replaces flake8 + black)
- `mypy` for static type checking (Pydantic models + SQLAlchemy provide rich type information)
- Pre-commit hooks to enforce these before commit

---

## Summary

| QA Mechanism | Present | Automated |
|---|---|---|
| Unit tests | No | — |
| Integration tests | No | — |
| End-to-end tests | No | — |
| Fixture provider (manual flow test) | Yes | No |
| Eval logs (LLM output audit) | Yes | No |
| Pydantic runtime validation | Yes | Yes (on every request) |
| Prompt versioning | Yes | No |
| Alembic migration history | Yes | Yes (CI would run `alembic upgrade head`) |
| Linting | No | — |
| Type checking | No | — |
