# 18 — Viva / Defense Preparation

> 20 likely professor questions with strong technical answers. Questions cover architecture, AI, security, scalability, and engineering practice.

---

## General Architecture Questions

---

### Q1. Why did you choose a monolithic architecture instead of microservices?

**Answer:**
The application is a single-developer university project where the cost of operational complexity outweighs the benefits of service isolation. Microservices introduce: inter-service network calls that need tracing, service discovery infrastructure, serialisation contracts between services, and independent deployment pipelines. None of these problems exist in a monolith of this scale.

More importantly, the modular monolith achieves the same *logical* separation of concerns — routes, services, CRUD, prompts are all distinct modules — without the network boundary. If scaling demands it, individual services (e.g., a dedicated cover letter generator) can be extracted later because the service boundaries are already cleanly defined.

The one genuine downside of the monolith is that background tasks (AI generation) compete with web request handling in the same process. This is a known trade-off and the solution (Celery) is identified.

---

### Q2. Why server-rendered HTML instead of a React/Vue SPA with a REST API?

**Answer:**
For a solo developer building a data-heavy CRUD application, a server-rendered approach eliminates an entire layer of complexity: no JSON API contract to maintain, no frontend build pipeline, no state management library, no API versioning.

Jinja2 + HTMX provides 80% of SPA-level interactivity (HTMX handles polling, partial swaps, inline updates) without JavaScript tooling. The remaining 20% (cover letter editor inline editing) was solved with vanilla JavaScript inline in the template — more complex than ideal, but contained.

The trade-off is that adding a mobile app or third-party integrations requires introducing a JSON API in the future.

---

### Q3. How does the request lifecycle work from browser to database?

**Answer:**
1. Browser sends HTTP form POST (e.g., `POST /jobs/search/42`)
2. Starlette `SessionMiddleware` validates the signed session cookie
3. FastAPI's `Depends(get_current_user)` dependency runs: checks session timestamps (idle 30min, absolute 8h), fetches the `User` from PostgreSQL, updates `last_seen`
4. Route handler (`jobs.py`) receives the validated `Request` + `User` object
5. Route calls `job_search_policy.decide_primary_search()` — this is pure decision logic, no DB access of its own
6. Based on the decision, the route calls `LiveJobSearchProvider.search()` → HTTP call to RapidAPI via `httpx`
7. Response mapper transforms API JSON → ORM `Job` objects
8. Persistence service INSERT/upserts to PostgreSQL and commits the transaction
9. Route calls `TemplateResponse("job_results.html", context)` — Jinja2 renders the HTML
10. Browser receives a complete HTML page

---

### Q4. How does dependency injection work in this project?

**Answer:**
FastAPI's `Depends()` system is used for three cross-cutting concerns:

1. **Auth guard:** `Depends(get_current_user)` — every protected route declares this parameter; FastAPI resolves it before the route handler runs. If authentication fails, `AuthenticationRequiredError` is raised and caught by the main exception handler.

2. **Provider selection:** `Depends(get_job_search_provider)` — the factory function in `app/dependencies/providers.py` reads `settings.JOB_SEARCH_PROVIDER` and returns either `LiveJobSearchProvider` or `FixtureJobSearchProvider`. The route never imports either concrete class.

3. **Template context:** `Depends(build_feedback_query)` — assembles template context (flash messages, current user data) for every template response.

This is inversion of control: the route handler declares *what it needs*, not *how to get it*. FastAPI resolves the dependency graph at startup and at request time.

---

## Database Questions

---

### Q5. Why did you use JSONB columns for LLM outputs instead of normalised relational columns?

**Answer:**
LLM output schemas evolve frequently during development. The `JobNormalizationSchema` changed structure 3 times across 15 migrations. If each field were a separate column, every schema change would require an Alembic migration, a model change, a CRUD function change, and a schema change — four files for one prompt improvement.

With JSONB, the schema is defined in Python (Pydantic) and the database just stores whatever the LLM returns. Alembic migrations are reserved for structural database changes, not prompt-driven schema evolution.

PostgreSQL's JSONB is still indexed, queryable (via `->>` operators), and supports GIN indexes if field-level queries become necessary.

The downside: JSONB cannot enforce NOT NULL or foreign key constraints on individual fields. This is acceptable because the Pydantic validation layer catches structural errors before storage.

---

### Q6. Explain the unique constraints in your schema and why they matter.

**Answer:**
Several unique constraints enforce business rules at the database level (not just application level):

- `jobs (external_job_id, source)`: prevents duplicate job imports when the same job appears across multiple search runs or days
- `search_runs (user_id, search_profile_id, run_date)`: enforces the "one run per profile per day" rule at the DB level, not just in `job_search_policy.py`
- `search_run_jobs (search_run_id, job_id)`: prevents the same job appearing twice in one run's results
- `application_tracker_entries (user_id, job_id)`: one tracker entry per user per job — prevents duplicate tracking records
- `profile_information (user_id)`: the UNIQUE constraint on the FK makes this a true one-to-one relationship
- `search_profiles (user_id, profile_name)`: profile names must be unique per user

These constraints are the last line of defence against race conditions and application bugs creating corrupt data.

---

### Q7. How do you manage database schema evolution?

**Answer:**
Alembic with `--autogenerate`. The workflow is:
1. Update the SQLAlchemy ORM model (`app/models/`)
2. Run `alembic revision --autogenerate -m "description"`
3. Review the generated migration (sometimes autogenerate misses things like server defaults or custom constraints)
4. Run `alembic upgrade head` to apply

The 15 migration files in `alembic/versions/` represent the complete schema history from the initial three tables to the current 13-table schema. Any team member can start from a blank database and reach the current state with a single command.

Important constraint: we never run migrations without explicit approval — the `CLAUDE.md` working rules prohibit autogenerated migration application without review.

---

## AI Questions

---

### Q8. Why do you use three separate LLM calls for cover letter generation instead of one big prompt?

**Answer:**
Asking a single LLM call to simultaneously: (1) analyse candidate-job fit, (2) write the letter body, and (3) check compliance with user-specified no-gos produces lower-quality output. The model is trying to do too much at once, which leads to weaker analysis and more generic writing.

Decomposition mirrors expert human workflow: a senior HR expert would first research the job and understand the fit, then write the letter, then review it for compliance. Separate calls for each phase allow each call to use its full context window and reasoning capacity on a single, focused task.

The practical benefits:
- The `fit_plan` from Call A is explicit and inspectable — it can be used for future features like interview prep
- Call C (verification) is an independent compliance audit; it doesn't constrain Call B's writing quality
- Each call can use different reasoning levels: `medium` for analysis (more critical), `low` for writing (faster)

Trade-off: 3–5x the API cost and 15–60 seconds of latency. Accepted for quality.

---

### Q9. How do you prevent the LLM from hallucinating false information about the candidate?

**Answer:**
Multiple layers:

1. **Truth constraint in prompts:** "Never invent. Extract only from provided data. If evidence is absent, use the `missing_requirements` field with an appropriate strategy."

2. **Evidence-based `fit_plan`:** Call A produces `evidence_points` — direct quotes or references from the profile that support each claim in the letter. Call B is instructed to write from this evidence, not from inference.

3. **`missing_requirements` strategies:** When the candidate lacks a required skill, the prompt provides structured strategies (`transferable`, `theory`, `goal`, `willingness_to_learn`) that are honest acknowledgements of the gap, not invented claims.

4. **Contact data injection:** The most factually sensitive data (name, email, phone, address) is never given to the LLM. It is injected from the database post-generation. The LLM cannot hallucinate a wrong phone number because it never sees it.

5. **Verification call:** Call C checks for no-go topics, but it does not verify factual accuracy. Factual verification is an open area for improvement.

---

### Q10. Why do you use two different LLM providers (OpenAI and OpenRouter)?

**Answer:**
Different tasks have different requirements:

- **Cover letter generation and job normalization** require the highest output quality (the user sees this directly) and structured output with reliable schema enforcement. OpenAI's `gpt-5-mini` via the Responses API is the best fit — it's a reasoning model with first-class structured output support.

- **CV profile extraction** is a simpler text transformation task (restructure → extract). `qwen2.5-7b` on OpenRouter is sufficient and significantly cheaper. OpenRouter also provides privacy benefits — it routes to an open-source model and has different data retention policies than OpenAI.

- **Ollama** is included in Docker Compose for local experimentation — zero API cost, full privacy, no internet required. It's the long-term target for CV extraction if local quality improves.

---

### Q11. How does your prompt versioning system work?

**Answer:**
Each prompt module (`prompts/job_normalization.py`, `prompts/profile_extraction.py`, `prompts/cover_letter_generation.py`) maintains a `VERSIONS` dictionary where keys are version strings (e.g., `"v1"`, `"v2"`, `"step2_v3"`) and values are the prompt text or configuration.

When a prompt is improved, a new key is added. The old version remains in the dictionary — it's not deleted. The service code selects a specific version key.

Benefits:
- Safe to test: the old version still works while the new one is evaluated
- Eval logs record which prompt version produced each output, enabling before/after comparison
- Code review shows exactly what changed between versions (diff shows dict key additions)

The limitation is that this is manual — there's no automated A/B testing framework that compares outputs statistically.

---

### Q12. How does the LLM output caching work for job normalization?

**Answer:**
`get_or_create_normalization(job_id, db)` in `job_normalization_service.py` first queries the `job_normalizations` table:

```python
existing = db.query(JobNormalization).filter(JobNormalization.job_id == job_id).first()
if existing:
    return JobNormalizationSchema(**existing.normalized_data)
```

If a record exists, the database result is deserialized into the Pydantic schema and returned without any LLM call. If not, the LLM call is made and the result is stored.

This caching is permanent (no TTL) — job descriptions don't change after posting, so cached normalizations stay valid. For a user who generates multiple cover letters for the same job, only the first cover letter incurs the normalization cost.

---

## Security Questions

---

### Q13. How do you protect against session hijacking?

**Answer:**
Sessions are stored in signed cookies using Starlette's `SessionMiddleware` with `SECRET_KEY`. The cookie is cryptographically signed — tampering with the session data invalidates the signature and the request is rejected.

Additional protections:
- Idle timeout (30 min): a stolen session cookie becomes invalid after 30 minutes of inactivity
- Absolute timeout (8 h): a session cookie stolen at login becomes invalid after 8 hours regardless of activity
- `SESSION_HTTPS_ONLY=true` in production: the cookie is only transmitted over HTTPS (prevents network interception)
- `SESSION_SAME_SITE=strict`: prevents CSRF via the cookie mechanism

One gap: there is no server-side session revocation. If a user logs out, the session is cleared client-side, but a captured cookie copy (if it hasn't expired) would still be valid. A Redis-backed session store would solve this.

---

### Q14. What is the biggest security vulnerability in the current implementation?

**Answer:**
The most significant unaddressed vulnerability is **the absence of CSRF protection** on form submissions.

All state-mutating actions (login, register, status updates, cover letter generation, document deletion) use HTML form POST submissions without CSRF tokens. An attacker who can trick an authenticated user into visiting a malicious page could craft a form that POSTs to the application on their behalf.

The session cookie's `SameSite` attribute mitigates this in modern browsers (the cookie won't be sent with cross-site requests if `same_site=strict` is configured), but this should not be the only protection.

The fix is straightforward: generate a CSRF token per session, embed it as a hidden input in every form, and validate it on every POST.

---

### Q15. How do you handle sensitive user data (CV content, personal details)?

**Answer:**
Multiple layers of data protection:

1. **LLM isolation:** Personal contact data (name, email, phone, address, signature image) is never included in OpenAI API calls. Only professional history and skills are sent. Contact fields are injected post-generation from the database.

2. **Secure storage:** CV PDFs are stored in MinIO (self-hosted) — not sent to a third-party file host. Presigned URLs for downloads are time-limited.

3. **At-rest encryption:** Not explicitly implemented (relies on PostgreSQL and MinIO default storage). Production would add PostgreSQL encryption at rest and MinIO volume encryption.

4. **Minimal disclosure to third-party LLMs:** The qwen2.5 model via OpenRouter is used for CV extraction — it's an open-source model with different data retention than OpenAI.

5. **GDPR considerations:** A privacy policy page exists. Data deletion (account deletion cascade) is built into the schema via `CASCADE DELETE` constraints.

---

## Performance and Scalability Questions

---

### Q16. Cover letter generation takes 15–60 seconds. How do you handle this UX problem?

**Answer:**
The key decision is: **never block the HTTP response on LLM latency**.

The route handler (`POST /cover-letter/generate`) immediately creates a `cover_letters` record with `generation_status=PENDING` and enqueues a `BackgroundTask`. It returns a 303 redirect to a polling page in under 100ms.

The polling page uses HTMX with `hx-trigger="every 2s"` to poll a status endpoint. The status endpoint returns a small HTML fragment — either a spinner (still running) or a JavaScript redirect (completed). The user sees real-time feedback without blocking.

When generation completes, the HTMX poll detects `COMPLETED` and the browser redirects to the editor automatically.

The remaining UX issue: the user sees a generic "generating..." spinner without knowing which of the 3 calls is in progress. A future improvement would stream progress events (SSE) to show "Analysing... Writing... Verifying..."

---

### Q17. How would you scale this application to handle 1,000 concurrent users?

**Answer:**
Current bottlenecks and their solutions:

1. **Web worker limit:** Currently one Uvicorn process. Add Gunicorn with `uvicorn.workers.UvicornWorker`; routes are fully stateless so multiple workers work without sticky sessions.

2. **Background tasks:** `BackgroundTasks` run in the web process — under load, AI calls would starve web requests. **Solution:** Celery + Redis. Workers in separate processes handle AI tasks; web process only queues tasks.

3. **Database connections:** PostgreSQL has a default connection limit. **Solution:** PgBouncer connection pooler in front of PostgreSQL; each web worker gets pooled connections.

4. **LLM throughput:** OpenAI rate limits apply per account. **Solution:** Exponential backoff retry logic; request queue with backpressure; consider OpenAI batch API for normalization.

5. **Object storage:** MinIO is single-node in development. **Solution:** AWS S3 is a drop-in replacement (same boto3 API); distributes storage globally.

---

## Testing and Quality Questions

---

### Q18. You have no test suite. How did you maintain quality during development?

**Answer:**
Honestly, the absence of tests is the largest engineering debt in the project. Quality was maintained through several compensating mechanisms:

1. **Fixture provider:** `FixtureJobSearchProvider` allows the complete user flow to be tested manually without API costs — useful for regression testing after changes

2. **Eval logs:** `evals/job_normalizations.jsonl` and `evals/profile_extractions.jsonl` capture every LLM output. After changing a prompt, reviewing recent outputs against the previous version provides a manual quality signal.

3. **Pydantic validation:** Runtime schema enforcement catches structural errors in LLM outputs immediately — a malformed response raises a `ValidationError` rather than storing corrupt data silently

4. **Alembic migrations:** Schema correctness is verified by running `alembic upgrade head` on a fresh database — this is a form of integration test for the database layer

5. **Manual testing:** Each feature was tested manually by running through the full user flow after each change

The first priority for V2 is adding pytest unit tests for `job_search_policy.py` (pure logic, easy to test) and mocked integration tests for the LLM service calls.

---

### Q19. How would you test the AI components?

**Answer:**
AI testing requires a different approach than traditional unit testing:

1. **Unit test the orchestration logic with mocked LLM clients:** The cover letter service's retry logic, compliance checking, and contact injection can all be tested by mocking the OpenAI client to return predefined structured outputs. Pytest + `pytest-mock` for this.

2. **Schema contract tests:** Validate that the LLM output for a sample job description matches the expected Pydantic schema fields. Use `pytest.approx` for partial field matching.

3. **Prompt regression tests using eval logs:** When a prompt is updated, run the new version against the sample inputs from `evals/job_normalizations.jsonl` and compare key fields (ats_keywords count, industry_group classification, required_competencies count) against expected ranges.

4. **End-to-end flow tests with fixture data:** Use `FixtureJobSearchProvider` + a mocked OpenAI client to run the full generation pipeline from search → normalize → cover letter in a test environment.

5. **Human evaluation:** For cover letter quality, automated tests are insufficient. A small human evaluation panel comparing outputs from different prompt versions is the most reliable quality signal.

---

### Q20. What is the most important thing you learned from building this project?

**Answer:**
The most important lesson was: **decompose AI tasks into focused sub-calls rather than trying to do everything in one prompt**.

Initially, the cover letter generation was a single large prompt asking the LLM to analyse fit, write the letter, and check compliance simultaneously. The output was mediocre — generic phrases, weak evidence, and compliance violations slipping through.

Splitting into three calls (Analysis → Writing → Verification) significantly improved quality. Each call could focus on a single, well-defined task. The fit_plan from Call A became the explicit foundation for Call B's writing, so the letter was evidence-based rather than generic.

This led to a broader principle: **treat multi-step LLM tasks like software architecture — decompose, encapsulate, compose**. A complex AI task is not one big prompt; it's a pipeline of focused, testable steps with well-defined inputs and outputs.

The second lesson: **don't underestimate the complexity of server-rendered rich editors**. The cover letter editor — with its contentEditable fields, HTMX live preview, content sync, and navigation guards — became the most technically complex component despite being "just frontend." A JavaScript framework like Vue or React would have been the right tool for that specific component.
