# 05 — Functional Features

> **Related documents:** [06-user-flows.md](06-user-flows.md) | [07-api-analysis.md](07-api-analysis.md) | [09-ai-analysis.md](09-ai-analysis.md)

---

## Feature Matrix

| Feature | User Benefit | AI-Powered | Key Files |
|---|---|---|---|
| Search Profile Management | Save and reuse named filter sets | No | `routes/search_profiles.py`, `services/search_profile_service.py` |
| Job Search Execution | Find relevant jobs with one click | No | `routes/jobs.py`, `services/job_search_policy.py`, `services/live_job_search_provider.py` |
| Job Result Pagination | Load more results without re-running search | No | `routes/jobs.py` (load-more endpoint), `services/job_search_policy.py` |
| Job Search History | Review past search runs | No | `routes/jobs.py` (history view) |
| Job Normalization | Structured analysis of job descriptions | **Yes** | `services/job_normalization_service.py`, `prompts/job_normalization.py` |
| Manual Job Posting | Paste a job description for analysis | No | `routes/cover_letter.py`, `models/manual_job_posting.py` |
| Application Tracker | Track application lifecycle per job | No | `routes/application_tracker.py`, `services/application_tracker_service.py` |
| CV Upload | Upload PDF CV to the platform | No | `routes/documents.py`, `services/document_service.py` |
| Text Extraction | Extract text from uploaded PDF | Partial (model) | `services/document_extraction.py` |
| CV Profile Extraction | Parse CV into structured profile | **Yes** | `services/profile_extraction.py`, `prompts/profile_extraction.py` |
| Cover Letter Setup | Configure tone, industry, and constraints | No | `routes/cover_letter.py` (setup form) |
| Cover Letter Generation | AI-written tailored cover letter | **Yes** | `services/cover_letter_service.py`, `prompts/cover_letter_generation.py` |
| Cover Letter Editor | In-browser rich editing with live preview | No | `templates/cover_letter_editor.html` |
| Template Selection | Choose classic, modern, or compact layout | No | `cover_letter_service.py`, `templates/cover_letter_variants/` |
| Cover Letter PDF Export | Download formatted A4 PDF | No | WeasyPrint integration |
| Document Management | Rename, delete uploaded documents | No | `routes/documents.py` |
| Dark Mode | System-preference-aware theme toggle | No | `templates/base.html`, Tailwind CSS |
| Dashboard | Quick overview of recent activity | No | `routes/dashboard.py` |
| User Registration & Login | Account creation and session auth | No | `routes/auth.py`, `services/auth_service.py` |

---

## Feature Detail

---

### 1. Search Profile Management

**Purpose:** Let users define and save named search parameter sets so the same search can be re-run without re-entering filters.

**User Benefit:** One click to re-run a recurring search ("Software Engineer — Berlin — Remote").

**Technical Implementation:**
- Each profile stores: `query`, `location`, `remote_only`, `employment_types[]`, `experience_levels[]`, `radius_km`
- CRUD via `app/services/search_profile_service.py` and `app/crud/search_profile.py`
- Profile names are unique per user (enforced by DB unique constraint: migration `361bc55a5937`)
- A snapshot of the profile state is stored on each search run (`*_snapshot` columns in `search_runs`), so history reflects the filters used at run time even if the profile is later edited

**Components:** `routes/search_profiles.py`, `models/search_profile.py`, `templates/search_profile_form.html`

---

### 2. Job Search Execution

**Purpose:** Execute a search using a saved profile and display ranked results.

**User Benefit:** Discover relevant job postings without manually visiting job boards.

**Technical Implementation:**
- `job_search_policy.py` makes the primary decision: `START_NEW_RUN`, `SHOW_EXISTING_RUN`, or `BLOCKED_*`
- Daily limit enforced (100 searches/day — TODO: reduce to 5 for production)
- If a run already exists for today's date + profile, it is returned instead of making a new API call (cache by date)
- Profile changes since last run trigger a fresh search (detected by comparing `profile.updated_at` vs `search_run.created_at`)
- Live provider uses `httpx` to call RapidAPI/JSearch with the mapped parameters
- Results are upserted to the `jobs` table (external_job_id + source = unique key)

**Components:** `routes/jobs.py`, `services/job_search_policy.py`, `services/live_job_search_provider.py`, `services/job_search_response_mapper.py`, `services/job_search_persistence.py`

---

### 3. Job Normalization (AI)

**Purpose:** Convert a raw job description into a structured, machine-readable schema.

**User Benefit:** Enables accurate cover letter generation by providing the AI with structured job requirements, keywords, and classification.

**Technical Implementation:**
- Single OpenAI Responses API call with structured output (`text.format`)
- Model: `gpt-5-mini`, reasoning: `medium`, max_output_tokens: 16,000
- Output: `JobNormalizationSchema` (title, company, contact + gender, industry_group, hierarchy_level, role_summary, responsibilities, required/nice-to-have competencies, technical skills, ATS keywords, ad language)
- Cached: `get_or_create_normalization()` checks DB before calling LLM
- Audit trail: all outputs appended to `evals/job_normalizations.jsonl`
- Prompt versioned: v1 (basic extraction) and v2 (adds contact_person_gender detection)

**Components:** `services/job_normalization_service.py`, `prompts/job_normalization.py`, `crud/job_normalization.py`

**Data:** `job_normalizations` table (`normalized_data` JSONB column)

---

### 4. Application Tracker

**Purpose:** Track the state of each job application through a defined lifecycle.

**User Benefit:** Single place to see all active applications and their status, with date tracking for key milestones.

**Technical Implementation:**
- States: `SAVED → APPLIED → INTERVIEW → OFFER / REJECTED / WITHDRAWN`
- One entry per user per job (enforced by unique constraint)
- Each status has a dedicated date field (`applied_at`, `interview_at`, `offer_at`, `rejected_at`, `withdrawn_at`)
- Status updates are POST form submissions; HTMX could be used here in future for inline updates
- Notes field for free text

**Components:** `routes/application_tracker.py`, `services/application_tracker_service.py`, `models/application_tracker_entry.py`, `templates/tracker.html`

---

### 5. CV Upload & Profile Extraction (AI)

**Purpose:** Allow users to upload their CV so that contact details and experience can pre-populate cover letters.

**User Benefit:** Eliminates manual data entry; ensures cover letter content is always personalised to the actual candidate.

**Technical Implementation:**
- PDF upload validated: MIME type check, max 10 MB
- File stored in MinIO under `documents/{user_id}/{uuid}_{name}.pdf`
- Extraction method cascade: embedded text → markdown (pymupdf4llm) → OCR (OpenCV + Pillow)
- 2-step LLM pipeline (OpenRouter / qwen2.5):
  - Step 1: Raw text → clean, section-grouped plain text
  - Step 2: Clean text → `CandidateProfile` (Pydantic schema, all fields typed)
- Profile stored in `profile_information` table (one row per user, upserted)
- Signature image extracted and stored separately (base64 in DB)
- CV reconstruction text stored for debugging

- When deploying: Host Ollama/Qwen3 either on the same cloud server as the FastAPI app, on a separate (possibly GPU-accelerated) cloud server within the same private network, or as a dedicated AI service in its own container or VM with a hosting provider (e.g. Hetzner, OVHcloud, AWS or Azure).

  → This ensures that sensitive data from the CV is processed exclusively within the own infrastructure and is not transferred to external LLM providers or their APIs (LLM calls for further processing/generating documents are then made without the sensitive data)


**Components:** `services/document_service.py`, `services/document_extraction.py`, `services/profile_extraction.py`, `services/signature_processor.py`

---

### 6. Cover Letter Generation (AI)

**Purpose:** Generate a fully personalised, tone-appropriate, compliance-checked cover letter for a specific job.

**User Benefit:** Eliminates blank-page problem; produces a professional German business letter in seconds.

**Technical Implementation:**
The most complex feature — a **3-call LLM pipeline**:

| Call | Model | Reasoning | Max Tokens | Input | Output |
|---|---|---|---|---|---|
| A — Analysis | gpt-5-mini | medium | 5,000 | job schema + candidate profile | fit_plan (keywords, evidence, gaps, must_include/avoid) |
| B — Writing | gpt-5-mini | low | 4,000 | fit_plan + tone + industry config | 6-field letter (subject, salutation, intro, body×2, conclusion) |
| C — Verification | gpt-5-mini | low | 2,000 | letter + no_gos | violations list |

Additional passes:
- **Compression retry** (Call B): if letter >2300 chars, regenerate with compression instruction
- **Remedial Writing** (Call B again): if Call C finds violations, regenerate with avoid-list

Post-generation: contact fields (name, email, phone, address, signature) are injected from `profile_information` — these are **never** sent to the LLM.

**User controls:**
- Tone: `formell`, `locker`, `sachlich`, `warm` (each has detailed linguistic parameters in prompt)
- Industry group: `conservative_business`, `dynamic_modern`, `technical_scientific`, `social_health_education`
- Hierarchy level: `entry_junior`, `professional_senior`, `executive_c_level`
- `must_haves`: topics the letter must address
- `no_gos`: topics to explicitly avoid
- Output language: German / English

**Data:** `cover_letters` table; `cover_letter_snapshots` for version history

---

### 7. Cover Letter Editor

**Purpose:** Allow users to review and edit the generated letter before downloading.

**User Benefit:** Full control over the final text with immediate visual feedback in a realistic A4 layout.

**Technical Implementation:**
- Split-pane: sidebar (design controls) + preview pane (live A4 preview)
- `data-field` attributes mark editable fields as `contentEditable` in edit mode
- HTMX live preview: design control changes trigger `hx-get` which re-renders the preview pane server-side with the new layout settings
- Content sync: `_syncHiddenInputs()` copies contentEditable text to hidden form inputs before save
- Unsaved-changes detection: `_editorSetContentDirty()` tracks modifications; navigation guard modal confirms before leaving
- Version history: every save creates a new `cover_letter_snapshot` with revision_type
- PDF export: JavaScript appends current layout params to URL, flushes content to DB, triggers iframe download

**Components:** `templates/cover_letter_editor.html`, `templates/cover_letter_variants/`, `static/css/cover_letter/`

---

### 8. Dark Mode

**Purpose:** Provide a comfortable viewing experience in low-light environments.

**User Benefit:** Reduced eye strain; matches system preference automatically.

**Technical Implementation:**
- Script in `<head>` of `base.html` checks `localStorage.theme` and `window.matchMedia('prefers-color-scheme: dark')`
- Adds `dark` class to `<html>` element before first render (prevents flash-of-wrong-theme)
- `toggleTheme()` function stores preference and toggles the class
- Tailwind's `dark:` prefix applies dark-variant classes throughout all templates
