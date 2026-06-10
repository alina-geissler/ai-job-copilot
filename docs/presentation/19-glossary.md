# 19 — Glossary

Technical and domain terms used throughout this documentation package and in the AI Job Copilot codebase.

---

## Application Domain Terms

| Term | Definition |
|---|---|
| **Anschreiben** | German: Cover letter — the personalised letter accompanying a job application |
| **ATS** | Applicant Tracking System — software used by recruiters to filter CVs by keyword matching |
| **ATS Keywords** | Specific terms from a job description that ATS systems search for in candidate materials |
| **DIN 5008** | German standard for business letter formatting — defines margins, spacing, and layout conventions used in the cover letter CSS |
| **Lebenslauf / CV** | German: CV / Curriculum Vitae — the structured document of a candidate's experience and education |
| **Fit Plan** | Internal term — the structured analysis output from Cover Letter Generation Call A; maps candidate evidence to job requirements |
| **Hierarchy Level** | Classification of seniority in the job normalization schema: `entry_junior`, `professional_senior`, `executive_c_level` |
| **Industry Group** | Classification of company culture type: `conservative_business`, `dynamic_modern`, `technical_scientific`, `social_health_education` |
| **No-Gos** | Topics or claims the user explicitly does not want mentioned in their cover letter |
| **Must-Haves** | Topics the user explicitly wants addressed in their cover letter |
| **Search Profile** | A saved, named set of job search filter parameters (query, location, filters) |
| **Search Run** | One execution of a search profile — stores the jobs found and the parameters used at that point in time |
| **Tone** | Cover letter writing style: `formell` (formal), `locker` (casual), `sachlich` (factual), `warm` (warm/personal) |
| **Tracker** | Application tracker — the feature for managing the lifecycle of job applications |

---

## AI / LLM Terms

| Term | Definition |
|---|---|
| **Call A / B / C** | Project-internal names for the three sequential LLM calls in cover letter generation (Analysis / Writing / Verification) |
| **Context Window** | The maximum amount of text an LLM can process in one call — limits how much input can be provided |
| **Eval Log** | Evaluation log — JSONL file recording every LLM output for quality monitoring (`evals/`) |
| **Hallucination** | When an LLM generates plausible-sounding but factually incorrect content |
| **Inference** | Running a trained LLM to generate output (as opposed to training the model) |
| **LLM** | Large Language Model — a neural network trained on text that can generate coherent language (e.g., GPT-4, qwen2.5) |
| **OpenRouter** | API gateway that routes requests to various LLM providers; used here for qwen2.5 access |
| **Ollama** | Local LLM serving tool — runs open-source models on local hardware |
| **Pydantic** | Python library for data validation using type annotations; used to enforce LLM output schemas |
| **Prompt** | The input text sent to an LLM to guide its output |
| **Prompt Engineering** | The practice of designing effective LLM prompts to produce desired outputs |
| **Prompt Version** | Numbered iteration of a prompt; stored in a `VERSIONS` dict for safe iteration |
| **RAG** | Retrieval-Augmented Generation — technique of searching a knowledge base before generating LLM responses. **Not used in this project.** |
| **Reasoning Model** | An LLM with explicit chain-of-thought reasoning capabilities; `gpt-5-mini` is a reasoning model |
| **Reasoning Effort** | Parameter for reasoning models: `low`, `medium`, `high` — controls how much internal reasoning the model does |
| **Responses API** | OpenAI's newer API (alternative to Chat Completions) with native structured output support |
| **Structured Output** | LLM output that conforms to a predefined JSON schema — enforced via OpenAI's `text.format` or `beta.parse` |
| **System Prompt** | The part of an LLM prompt that establishes context, role, and constraints for the model |
| **Token** | The unit LLMs use to process text — roughly 0.75 words; API costs and context limits are measured in tokens |
| **Two-Step Extraction** | The CV profile extraction approach: Step 1 reconstructs clean text, Step 2 extracts structured data |

---

## Backend / Framework Terms

| Term | Definition |
|---|---|
| **Alembic** | Python database migration tool for SQLAlchemy — manages schema versioning |
| **ASGI** | Asynchronous Server Gateway Interface — the Python async web standard; FastAPI + Uvicorn use ASGI |
| **BackgroundTasks** | FastAPI mechanism for running functions after the HTTP response is sent — used for AI generation |
| **bcrypt** | Adaptive cryptographic hash function for password storage |
| **CRUD** | Create, Read, Update, Delete — the four basic database operations; `app/crud/` contains the data access layer |
| **DI / Dependency Injection** | Design pattern where a component receives its dependencies from outside rather than creating them — FastAPI's `Depends()` |
| **FastAPI** | Modern Python web framework with async support, native DI, and automatic OpenAPI documentation |
| **Jinja2** | Python server-side templating engine — renders HTML from templates + context data |
| **ORM** | Object-Relational Mapper — maps Python classes to database tables; SQLAlchemy is the ORM used |
| **Pydantic Settings** | Extension of Pydantic for typed configuration from environment variables (`BaseSettings`) |
| **SQLAlchemy** | Python SQL toolkit and ORM |
| **Starlette** | ASGI framework underlying FastAPI; provides `SessionMiddleware`, static files, etc. |
| **Uvicorn** | ASGI server that runs FastAPI applications |

---

## Frontend Terms

| Term | Definition |
|---|---|
| **Alpine.js** | Lightweight JavaScript framework for declarative component state in HTML — `x-data`, `@click` |
| **contentEditable** | HTML attribute that makes an element's text directly editable in the browser |
| **HTMX** | Library that extends HTML with declarative AJAX attributes — enables server-driven dynamic UI without JavaScript frameworks |
| **hx-get / hx-post** | HTMX attributes that trigger AJAX requests and swap the response into the DOM |
| **hx-swap="outerHTML"** | HTMX target swap strategy — replaces the entire element (including itself) with the server response |
| **hx-trigger="every 2s"** | HTMX trigger that fires the request every 2 seconds — used for background task polling |
| **Tailwind CSS** | Utility-first CSS framework — provides pre-defined classes applied directly in HTML markup |
| **WeasyPrint** | Python library for converting HTML+CSS to PDF — used for cover letter PDF export |

---

## Database / Storage Terms

| Term | Definition |
|---|---|
| **JSONB** | Binary JSON column type in PostgreSQL — indexed, queryable, used for LLM output storage |
| **MinIO** | S3-compatible self-hosted object storage — stores uploaded CV PDFs and generated documents |
| **Presigned URL** | A time-limited URL granting access to a private MinIO/S3 object — used for secure document downloads |
| **PostgreSQL** | Open-source relational database with advanced features (JSONB, arrays, ACID transactions) |
| **Upsert** | INSERT … ON CONFLICT DO UPDATE — inserts a record if it doesn't exist, updates it if it does |

---

## Security Terms

| Term | Definition |
|---|---|
| **CSRF** | Cross-Site Request Forgery — an attack where a malicious site tricks a user's browser into making authenticated requests to another site |
| **CSRF Token** | A secret value included in forms and validated server-side to prevent CSRF attacks |
| **Session Cookie** | An HTTP cookie storing an authenticated user's session identifier |
| **Signed Cookie** | A cookie whose contents are cryptographically signed — tampering invalidates the signature |
| **Same-Site** | Cookie attribute that controls when the browser sends the cookie with cross-site requests |
| **Idle Timeout** | Session expiry triggered by a period of inactivity (30 minutes in this application) |
| **Absolute Timeout** | Session expiry triggered by elapsed time since login regardless of activity (8 hours in this application) |
