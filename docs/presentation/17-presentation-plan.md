# 17 — Presentation Plan

> This is a content planning document for approximately 10 slides. It does not contain final slide text — it contains the raw content, key points, and visualisation suggestions needed to build the slides manually.
>
> Reference the detailed documentation in this package for full technical depth.

---

## Slide 1 — Project Overview

**Goal:** Orient the audience to what this project is and why it matters in ~60 seconds.

**Key Talking Points:**
- Project name: AI Job Copilot
- A German-language web application for AI-assisted job searching and application management
- Combines classical software engineering (FastAPI, PostgreSQL, Jinja2) with modern AI (OpenAI gpt-5-mini, structured output, multi-call orchestration)
- University capstone project: solo-built, full-stack, production-grade architecture

**Important Findings to Highlight:**
- The application handles the entire job application lifecycle from search to cover letter to tracking
- 3 distinct AI pipelines, each serving a different purpose
- 13 database tables, 15 migrations, ~60 Python source files

**Suggested Visualisations:**
- Screenshot of the dashboard or cover letter editor
- Logo / project name as hero element

**Recommended Diagrams:** None — use product screenshot

**Speaker Notes:**
- Keep this brief — one minute maximum
- "I built an AI-powered job search and cover letter assistant that helps German-speaking job seekers with the full application process — from discovering relevant jobs to generating tailored cover letters in seconds"
- Mention the stack briefly: Python FastAPI + OpenAI + PostgreSQL

---

## Slide 2 — Problem and Motivation

**Goal:** Establish why this application is useful and what real problem it solves.

**Key Talking Points:**
- Job searching is fragmented: users visit multiple platforms, re-enter the same criteria repeatedly
- Reading full job descriptions to judge fit is time-consuming
- Writing individualised cover letters for each job is a major effort most candidates skip
- Tracking 20+ open applications across spreadsheets, email, and bookmarks is chaotic

**Important Findings to Highlight:**
- The application solves all four problems in one integrated system
- The cover letter is often the most effort-intensive part of the application — and the one AI can help with most

**Suggested Visualisations:**
- 4-quadrant problem diagram: Search / Assess / Write / Track
- "Before vs. After" contrast for time spent per application

**Recommended Diagrams:** None — use simple text layout or icons

**Speaker Notes:**
- "Most candidates write generic cover letters because personalised ones take too long — we fix that with AI"
- "The fragmentation problem is real: I've seen students managing 30+ applications in a spreadsheet"

---

## Slide 3 — Solution Overview

**Goal:** Show the complete feature set and how it maps to the problems.

**Key Talking Points:**
- Search profiles: define filters once, search repeatedly
- AI job normalization: structured requirements + ATS keywords from raw job text
- Application tracker: SAVED → APPLIED → INTERVIEW → OFFER/REJECTED/WITHDRAWN
- CV upload + AI extraction: profile pre-populates all cover letters
- 3-call AI pipeline: Analysis → Writing → Verification = personalised, compliant letter in seconds

**Feature Matrix:** (reference `05-features.md` matrix)

**Suggested Visualisations:**
- Feature table (5 rows, icons + one-line description)
- Screenshot of the application tracker or search results

**Recommended Diagrams:** Feature-to-problem mapping table

**Speaker Notes:**
- Walk through the user journey in 30 seconds: "First I upload my CV, the AI extracts my profile. Then I search for jobs with my saved filters. I click Analyse on an interesting job — the AI breaks it down into requirements and keywords. I click Generate Letter — three AI calls later I have a personalised cover letter ready to edit and download."

---

## Slide 4 — System Architecture

**Goal:** Show how the system is structured at the technical level.

**Key Talking Points:**
- Modular monolith — single FastAPI process, four clean layers
- Routes (thin) → Services (business logic + LLM) → CRUD (DB access) → Database
- No SPA: server-rendered HTML with Jinja2, enhanced by HTMX and Alpine.js
- External: OpenAI API (cover letter + normalization), OpenRouter/qwen2.5 (CV extraction), MinIO (storage)

**Important Findings to Highlight:**
- Provider strategy pattern: `FixtureJobSearchProvider` for dev, `LiveJobSearchProvider` for production — injected via FastAPI DI
- Background tasks for all AI operations: user gets immediate response, AI runs asynchronously
- Session-based auth with idle (30 min) and absolute (8 h) timeout

**Suggested Visualisations:**
- Architecture diagram (from `assets/architecture-diagram.md`)

**Recommended Diagrams:** Architecture diagram (layered box diagram with external services)

**Speaker Notes:**
- "I chose a modular monolith over microservices because the operational complexity of microservices is not justified for a single-developer project"
- "The provider strategy pattern means I can develop and demo without spending money on the live API — just set JOB_SEARCH_PROVIDER=fixture"

---

## Slide 5 — Technology Stack

**Goal:** Overview every major technology choice and its rationale.

**Key Talking Points:**
- Python + FastAPI: async, native DI, Pydantic integration
- Jinja2 + HTMX: server-rendered HTML with selective dynamic behaviour (no SPA)
- PostgreSQL 16 with JSONB: relational + flexible structured storage
- OpenAI gpt-5-mini via Responses API: structured output for consistent LLM results
- MinIO: S3-compatible local object storage for documents
- Docker Compose: one command to start all infrastructure services

**Technology Summary Table:** (reference `03-technology-stack.md` summary table)

**Suggested Visualisations:**
- Technology icon grid (Python, FastAPI, PostgreSQL, OpenAI, MinIO, Docker, HTMX, Tailwind)

**Recommended Diagrams:** Summary table from `03-technology-stack.md`

**Speaker Notes:**
- "The most interesting choice is HTMX — it gives us 80% of React-level interactivity without a JavaScript build pipeline"
- "JSONB columns for LLM outputs let me evolve the schema without database migrations every time a prompt changes"

---

## Slide 6 — Core User Flow

**Goal:** Walk through the most important end-to-end user journey.

**Key Talking Points:**
- The complete cover letter generation flow is the heart of the application
- User uploads CV → AI extracts profile → user searches for job → AI normalizes job → user generates cover letter → 3 LLM calls → editor opens with ready letter

**Flow Steps:**
1. Upload CV → PDF stored in MinIO → 2-step AI extraction → profile_information UPSERT
2. Search with saved profile → job_search_policy decides → RapidAPI → results stored in DB
3. Setup form: tone, industry, no-gos → POST /cover-letter/generate → PENDING record
4. Background: normalize job (cached) → Call A Analysis → Call B Writing → Call C Verification
5. Contact fields injected post-LLM → COMPLETED → editor opens

**Suggested Visualisations:**
- Sequence diagram (simplified) from `assets/sequence-diagrams.md` — Cover Letter Generation flow

**Recommended Diagrams:** Simplified cover letter generation sequence diagram

**Speaker Notes:**
- "The user never waits at the browser — after clicking Generate, they immediately see a polling page. The AI works in the background. When it's done, the editor opens automatically."
- "Contact data is never sent to OpenAI — it's injected after all LLM calls. This is a deliberate privacy decision."

---

## Slide 7 — Database and Data Management

**Goal:** Show the data model and how the system persists and evolves data.

**Key Talking Points:**
- 13 tables covering: users, search, jobs, application tracking, documents, profile, cover letters
- JSONB columns for LLM outputs (no migration needed when AI schema evolves)
- 15 Alembic migrations — the full schema history is version-controlled
- Cover letter snapshots: every revision is stored — INITIAL, AI_REVISION, USER_REVISION

**Important Findings:**
- Job normalization results are cached in `job_normalizations` — the same job is never normalized twice
- `profile_information` is a single-row-per-user profile (ONE-to-ONE) with ~30 fields covering the full CV
- `search_run_jobs` join table tracks whether a job was "previously seen" (deduplication across runs)

**Suggested Visualisations:**
- Simplified ER diagram (key tables + relationships only)
- Table count: "13 tables, 15 migrations" as a statistic

**Recommended Diagrams:** Simplified ER diagram from `assets/er-diagram.md`

**Speaker Notes:**
- "The key insight is using JSONB for LLM outputs — the schema of a job normalization result evolved 3 times during development. With JSONB, I didn't need a migration for each change."

---

## Slide 8 — AI Architecture and Intelligent Components

**Goal:** Deep-dive the AI implementation — the most technically differentiated aspect of the project.

**Key Talking Points:**
- Three distinct AI pipelines: Job Normalization, Cover Letter Generation, CV Extraction
- All use structured output / Pydantic schema enforcement — no free-text LLM responses
- Cover letter: 3-call pipeline (Analysis → Writing → Verification) with compliance check and optional retry
- Privacy: contact data never sent to OpenAI — injected post-generation
- Prompt versioning for safe iteration

**Technical Detail:**
- Normalization: OpenAI Responses API, `reasoning=medium`, `max_output_tokens=16000`
- Cover letter Writing: gpt-5-mini, `reasoning=low`, 330–380 word target with hard 2300 char limit
- CV extraction: qwen2.5-7b via OpenRouter, 2-step (reconstruct → structured parse)
- Eval logs: every LLM output appended to JSONL for quality monitoring

**Suggested Visualisations:**
- Cover letter 3-call pipeline flowchart from `assets/additional-diagrams.md`
- Side-by-side: "Call A input" vs "Call A output" example

**Recommended Diagrams:** 3-call pipeline diagram

**Speaker Notes:**
- "The most important design decision in the AI system is decomposing the cover letter into three separate calls. A single large prompt produces lower quality — separating analysis, writing, and verification lets each call focus on one task."
- "The verification call is essentially an AI auditing another AI's output — it checks if the no-go topics the user specified are being violated."

---

## Slide 9 — Engineering Decisions and Lessons Learned

**Goal:** Reflect on key technical decisions and what was learned.

**Key Talking Points:**
- Server-rendered HTML (Jinja2 + HTMX) vs. React SPA: right choice for solo developer, wrong choice for cover letter editor complexity
- Modular monolith: appropriate for this scale; Celery would be needed for production reliability
- Three-call LLM pipeline: higher quality but 3–5x cost and 15–60 second latency
- JSONB for LLM output: enabled rapid schema iteration without migrations
- Privacy-first design: excluding contact data from LLM is the right approach

**Challenges:**
- Cover letter editor is the most complex component — 1250 lines in a single template
- Background task reliability: FastAPI `BackgroundTasks` are lost on server restart
- No test suite: made rapid iteration easy but created regression risk

**Suggested Visualisations:**
- Decision trade-off table (3 columns: Decision / Advantage / Disadvantage)

**Recommended Diagrams:** Table from `14-engineering-decisions.md`

**Speaker Notes:**
- "If I did this again, I would introduce Celery from day one — the background task problem is the biggest production risk."
- "The HTMX approach worked well for 90% of the UI, but the cover letter editor really needs a proper JavaScript framework."

---

## Slide 10 — Future Improvements and V2 Roadmap

**Goal:** Show the path forward and demonstrate awareness of the system's limitations.

**Key Talking Points:**
- Quick wins (low effort, high impact): version history browser, job match score, analytics dashboard, email notifications
- Medium-term: multi-turn chat refinement, interview prep assistant, automated job alerts
- Long-term vision: multi-agent AI orchestration, salary benchmarking, enterprise mode

**Immediate technical improvements:**
- Add test suite (pytest + mocked LLM clients)
- CSRF protection for all POST forms
- Celery + Redis for durable background tasks
- Docker containerise the app itself (CI/CD)

**Suggested Visualisations:**
- 3-tier roadmap: Quick Wins / Medium-Term / Long-Term
- Prioritisation matrix (effort vs. impact)

**Recommended Diagrams:** Prioritisation matrix or 3-column roadmap from `16-v2-roadmap.md`

**Speaker Notes:**
- "The most impactful V2 feature would be the interview preparation assistant — the job normalization schema already contains everything needed to generate targeted interview questions."
- "The biggest architectural improvement is replacing FastAPI BackgroundTasks with Celery — this is the foundation for reliable, scalable AI operations."
