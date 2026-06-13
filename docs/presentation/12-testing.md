# 12 — Testing and Quality Assurance

> **Related documents:** [15-future-improvements.md](15-future-improvements.md)

---

## Automated Test Suite

A formal test suite covering 162 tests runs against the application using pytest. Tests are organised in three layers:

| Layer | Count | Purpose |
|---|---|---|
| Unit tests (`tests/unit/`) | 73 | Pure-function logic; no DB or network required |
| Integration tests (`tests/integration/`) | 46 | CRUD and service-layer tests against a real test database |
| End-to-end tests (`tests/e2e/`) | 43 | HTTP route behaviour via FastAPI TestClient |
| **Total** | **162** | |

**Location:** `tests/` at the project root. Shared fixtures live in `tests/conftest.py`.

**To run:**
```bash
pytest           # full suite
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/
```

---

### Unit Tests (`tests/unit/`)

Pure-function tests with no database or network dependency:

| File | What it covers |
|---|---|
| `test_security.py` | `hash_password` / `verify_password` — bcrypt prefix, correct/wrong password, hash uniqueness |
| `test_user_schema.py` | `UserCreate` validation — min/max length, whitespace, common-password blocklist, email-part detection |
| `test_job_search_policy.py` | All decision functions in `job_search_policy.py` — 29 tests covering all daily-limit boundary conditions and date-posted ranges |
| `test_job_search_response_mapper.py` | `extract_raw_jobs` and `map_job` — valid/invalid payloads, null fields, location separator stripping |
| `test_auth_dependency.py` | `get_current_user` — valid session, idle/absolute timeout, missing session keys, user-not-found |

---

### Integration Tests (`tests/integration/`)

Tests that hit a real PostgreSQL test database (`ai_job_copilot_test`) with savepoint-based rollback isolation:

| File | What it covers |
|---|---|
| `test_crud_user.py` | Create, read, duplicate detection; password hash stored (not plaintext) |
| `test_crud_search_profile.py` | Create (explicit + auto-named "Suchprofil N"), ownership isolation, update, delete |
| `test_crud_tracker.py` | Default status SAVED, idempotent creation, status updates, `applied_at` date tracking, notes, clear date, delete |
| `test_auth_service.py` | Registration commits user; duplicate email raises and rolls back |
| `test_search_profile_service.py` | Service-layer create, update, not-found → None, delete returns True/False |
| `test_tracker_service.py` | Full CRUD via service layer; idempotent create; status, notes, and date updates |

**Test isolation:** Each test runs inside a savepoint transaction (`join_transaction_mode="create_savepoint"`). Service-layer `db.commit()` calls commit to the savepoint; the outer transaction is rolled back at teardown. No `TRUNCATE` needed; no residual data between tests.

---

### End-to-End Tests (`tests/e2e/`)

HTTP-level tests using FastAPI's `TestClient` with `follow_redirects=False`:

| File | What it covers |
|---|---|
| `test_health.py` | `GET /health` returns 200 |
| `test_auth_routes.py` | Register, login, logout, session cookie, wrong password, common password, email-part validation, unauthenticated redirect |
| `test_search_profile_routes.py` | Create success → 303, blank query → 422, radius with Deutschland → 422, duplicate name → 422, auth guard |
| `test_tracker_routes.py` | Create entry, idempotent create, status/notes/date updates, delete, tracker detail page, auth guard |

---

## Test Infrastructure

**Test database:** `ai_job_copilot_test` on the same PostgreSQL server. Created once; schema built via `Base.metadata.create_all()` at the start of each test session and dropped at the end.

**Fixtures (`tests/conftest.py`):**

| Fixture | Scope | Purpose |
|---|---|---|
| `test_engine` | session | Creates / drops all tables once per test session |
| `db` | function | Savepoint-isolated `Session`; rolls back at teardown |
| `client` | function | `TestClient(app)` with `get_db` overridden to `db` |
| `test_user` | function | Seeded `User` in the test DB |
| `authenticated_client` | function | `client` after a real `POST /auth/login` |

**Environment:** `os.environ` is set at the top of `conftest.py` before any `app.*` import, so `pydantic_settings` picks up test values (test DB URL, placeholder API keys, `JOB_SEARCH_PROVIDER=fixture`) when `Settings()` is initialised at module import time.

**Savepoint pattern:**
```python
@pytest.fixture
def db(test_engine):
    with test_engine.connect() as conn:
        conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        conn.rollback()   # undoes all commits made via SAVEPOINTs
```

---

## Additional Quality Mechanisms

Beyond the automated test suite, several mechanisms provide additional quality assurance:

### Fixture Provider — Manual Integration Test Harness

**File:** `app/services/fixture_job_search_provider.py`

The `FixtureJobSearchProvider` returns hardcoded job data when `JOB_SEARCH_PROVIDER=fixture` is set. This allows the full job search → display → tracker → cover letter workflow to be exercised without hitting the live API or consuming credits. The automated e2e tests also use this provider.

### Eval Logs — LLM Output Audit Trail

**Files:** `evals/job_normalizations.jsonl`, `evals/profile_extractions.jsonl`

Every LLM call appends a timestamped JSONL record with the model, prompt version, input identifier, and full structured output. These logs function as a lightweight regression detection mechanism — a developer can review recent LLM outputs to detect quality degradation, unexpected formats, or hallucinated content.

### Prompt Versioning — Safe Prompt Evolution

**Files:** `prompts/job_normalization.py`, `prompts/profile_extraction.py`, `prompts/cover_letter_generation.py`

Each prompt module maintains a `VERSIONS` dictionary. Old versions are preserved so they can be re-run against existing eval logs before committing to a new version.

### Pydantic Schema Validation — Runtime Contract Enforcement

Pydantic models enforce type correctness and required fields at runtime: form inputs are validated before reaching service code; LLM outputs are validated via `beta.chat.completions.parse` and `text.format` structured output APIs. Validation errors are raised at the boundary rather than allowing corrupt data through.

### Alembic Migrations — Schema Correctness

15 migration files ensure that `alembic upgrade head` produces a consistent, verified schema on any database — preventing "works on my machine" inconsistencies.

---

## Not Yet Covered

The following areas are not covered by the current test suite:

| Area | Gap |
|---|---|
| `cover_letter_service.py` | Requires a mocked OpenAI client; LLM pipeline tests not yet implemented |
| `job_normalization_service.py` | Same — requires mock LLM responses |
| `profile_extraction.py` | Same — requires mock OpenRouter responses |
| Flash message content | Flash messages are cleared on render; current e2e tests assert status codes only, not message text |
| HTMX polling lifecycle | Background task polling requires timing-aware test patterns not yet implemented |

---

## Linting and Formatting

**Confirmed:** No linting or formatting configuration files are present (`pyproject.toml` contains only pytest configuration; no `.flake8`, `.ruff.toml`, `.black`, or `mypy.ini`).

**Recommended additions:**
- `ruff` for fast linting + formatting (replaces flake8 + black)
- `mypy` for static type checking (Pydantic models + SQLAlchemy provide rich type information)
- Pre-commit hooks to enforce these before commit

---

## Summary

| QA Mechanism | Present | Automated |
|---|---|---|
| Unit tests | Yes | Yes |
| Integration tests | Yes | Yes |
| End-to-end tests | Yes | Yes |
| Fixture provider (manual flow test) | Yes | No |
| Eval logs (LLM output audit) | Yes | No |
| Pydantic runtime validation | Yes | Yes (on every request) |
| Prompt versioning | Yes | No |
| Alembic migration history | Yes | Yes (CI would run `alembic upgrade head`) |
| Linting | No | — |
| Type checking | No | — |
