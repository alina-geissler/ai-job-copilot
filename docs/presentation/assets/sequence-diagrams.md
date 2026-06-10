# Sequence Diagrams

## Title
AI Job Copilot — User Journey Sequence Diagrams

---

## 1. User Registration & Login

```mermaid
sequenceDiagram
    actor User
    participant Browser
    participant FastAPI as FastAPI (auth.py)
    participant AuthSvc as auth_service.py
    participant CRUD as crud/user.py
    participant DB as PostgreSQL

    User->>Browser: Navigate to /auth
    Browser->>FastAPI: GET /auth
    FastAPI-->>Browser: Render auth.html (register/login form)

    Note over User,DB: Registration
    User->>Browser: Fill form, submit
    Browser->>FastAPI: POST /auth/register (email, password, name)
    FastAPI->>AuthSvc: register_user_account(UserCreate)
    AuthSvc->>CRUD: get_user_by_email(email)
    CRUD->>DB: SELECT users WHERE email=?
    DB-->>CRUD: None (not found)
    CRUD-->>AuthSvc: None
    AuthSvc->>AuthSvc: bcrypt.hash(password)
    AuthSvc->>CRUD: create_user(hashed_pw)
    CRUD->>DB: INSERT users
    DB-->>CRUD: User record
    AuthSvc->>FastAPI: User
    FastAPI->>FastAPI: session["user_id"] = user.id
    FastAPI-->>Browser: 303 Redirect → /dashboard

    Note over User,DB: Login
    User->>Browser: Submit login form
    Browser->>FastAPI: POST /auth/login (email, password)
    FastAPI->>CRUD: get_user_by_email(email)
    CRUD->>DB: SELECT users
    DB-->>CRUD: User record
    FastAPI->>FastAPI: bcrypt.verify(password, hash)
    FastAPI->>FastAPI: session["user_id"] = user.id\nsession["created_at"] = now
    FastAPI-->>Browser: 303 Redirect → /dashboard
```

---

## 2. Job Search Execution

```mermaid
sequenceDiagram
    actor User
    participant Browser
    participant FastAPI as FastAPI (jobs.py)
    participant Policy as job_search_policy.py
    participant Provider as JobSearchProvider
    participant Mapper as response_mapper.py
    participant Persist as job_search_persistence.py
    participant DB as PostgreSQL
    participant API as RapidAPI / JSearch

    User->>Browser: Select search profile, click "Suchen"
    Browser->>FastAPI: POST /jobs/search/{profile_id}
    FastAPI->>Policy: decide_primary_search(profile, user, today)
    Policy->>DB: SELECT search_runs WHERE run_date=today
    DB-->>Policy: existing_run or None

    alt SHOW_EXISTING_RUN
        Policy-->>FastAPI: action=SHOW_EXISTING_RUN, run=existing_run
        FastAPI-->>Browser: Render job_results.html (cached run)
    else BLOCKED_DAILY_LIMIT
        Policy-->>FastAPI: action=BLOCKED
        FastAPI-->>Browser: Flash error, redirect
    else START_NEW_RUN
        Policy-->>FastAPI: action=START_NEW_RUN
        FastAPI->>Provider: search(SearchRequest)
        Provider->>API: GET /search?query=...&page=1
        API-->>Provider: JSON job listings
        Provider-->>FastAPI: JobSearchResult
        FastAPI->>Mapper: map_to_orm(result, profile, run)
        Mapper-->>FastAPI: [Job ORM objects], [SearchRunJob objects]
        FastAPI->>Persist: persist(jobs, search_run, search_run_jobs)
        Persist->>DB: INSERT jobs (upsert), INSERT search_run, INSERT search_run_jobs
        DB-->>Persist: OK
        FastAPI-->>Browser: Render job_results.html with results
    end
```

---

## 3. Cover Letter Generation

```mermaid
sequenceDiagram
    actor User
    participant Browser
    participant FastAPI as FastAPI (cover_letter.py)
    participant CLSvc as cover_letter_service.py
    participant NormSvc as job_normalization_service.py
    participant OAI as OpenAI API
    participant DB as PostgreSQL

    User->>Browser: Fill setup form (tone, industry, etc.)
    Browser->>FastAPI: POST /cover-letter/generate
    FastAPI->>CLSvc: initiate_cover_letter_generation(form, user, job_id)
    CLSvc->>DB: INSERT cover_letters (status=PENDING)
    CLSvc->>FastAPI: Enqueue BackgroundTask(_run_generation_task)
    FastAPI-->>Browser: 303 Redirect → /cover-letter/{id}/generating
    Browser->>FastAPI: HTMX polls GET /cover-letter/{id}/status (every 2s)

    Note over CLSvc,OAI: Background Task
    CLSvc->>DB: SELECT jobs / manual_job_postings (get raw text)
    CLSvc->>NormSvc: get_or_create_normalization(job_id)
    NormSvc->>DB: SELECT job_normalizations WHERE job_id=?
    alt Not cached
        NormSvc->>OAI: Responses API (structured output, gpt-5-mini)
        OAI-->>NormSvc: JobNormalizationSchema JSON
        NormSvc->>DB: INSERT job_normalizations
    end
    NormSvc-->>CLSvc: JobNormalizationSchema

    CLSvc->>DB: SELECT profile_information (user profile, excl. contact)
    CLSvc->>OAI: Call A — Analysis (fit_plan, keywords, gaps)
    OAI-->>CLSvc: fit_plan JSON
    CLSvc->>OAI: Call B — Writing (cover letter prose)
    OAI-->>CLSvc: subject_line, salutation, intro, body, conclusion
    CLSvc->>CLSvc: length check (<2300 chars?)
    alt Too long
        CLSvc->>OAI: Retry Call B (compress instruction)
        OAI-->>CLSvc: shorter version
    end
    CLSvc->>OAI: Call C — Verification (no-go compliance)
    OAI-->>CLSvc: violations list
    alt Violations found
        CLSvc->>OAI: Remedial Call B (avoid violations)
        OAI-->>CLSvc: compliant version
    end
    CLSvc->>CLSvc: Inject contact fields from profile (name, email, phone, address)
    CLSvc->>DB: UPDATE cover_letters (content=JSONB, status=COMPLETED)
    CLSvc->>DB: INSERT cover_letter_snapshots (revision_type=INITIAL)

    FastAPI->>DB: Poll status
    DB-->>FastAPI: status=COMPLETED
    FastAPI-->>Browser: 303 Redirect → /cover-letter/{id}/editor
```

---

## 4. Application Status Update

```mermaid
sequenceDiagram
    actor User
    participant Browser
    participant FastAPI as FastAPI (application_tracker.py)
    participant TrackerSvc as application_tracker_service.py
    participant CRUD as crud/application_tracker_entry.py
    participant DB as PostgreSQL

    User->>Browser: Click status button (e.g., "Bewerbung eingereicht")
    Browser->>FastAPI: POST /tracker/{job_id}/status (status=APPLIED, applied_at=date)
    FastAPI->>TrackerSvc: update_status(user_id, job_id, status, date)
    TrackerSvc->>CRUD: get_entry(user_id, job_id)
    CRUD->>DB: SELECT application_tracker_entries
    DB-->>CRUD: existing entry or None
    alt Entry exists
        TrackerSvc->>CRUD: update_entry(status, applied_at)
        CRUD->>DB: UPDATE application_tracker_entries
    else New entry
        TrackerSvc->>CRUD: create_entry(user_id, job_id, status)
        CRUD->>DB: INSERT application_tracker_entries
    end
    DB-->>CRUD: OK
    FastAPI-->>Browser: Flash success + redirect
```

---

## 5. CV Upload & Profile Extraction

```mermaid
sequenceDiagram
    actor User
    participant Browser
    participant FastAPI as FastAPI (documents.py)
    participant DocSvc as document_service.py
    participant Storage as document_storage.py
    participant Extract as document_extraction.py
    participant Profile as profile_extraction.py
    participant OR as OpenRouter (qwen2.5)
    participant MINIO as MinIO S3
    participant DB as PostgreSQL

    User->>Browser: Upload PDF CV
    Browser->>FastAPI: POST /documents/upload (multipart/form-data)
    FastAPI->>DocSvc: upload_document(file, user_id)
    DocSvc->>DocSvc: validate MIME type + size (<10 MB)
    DocSvc->>Storage: put_object(bucket, key, bytes)
    Storage->>MINIO: PUT s3://bucket/documents/{user_id}/{uuid}.pdf
    MINIO-->>Storage: OK
    DocSvc->>DB: INSERT documents (status=PENDING)
    DocSvc->>FastAPI: Enqueue BackgroundTask

    Note over DocSvc,OR: Background Extraction
    DocSvc->>Extract: extract_text(storage_key)
    Extract->>MINIO: GET object
    MINIO-->>Extract: PDF bytes
    Extract->>Extract: Try embedded text (PyMuPDF)
    alt Embedded text sufficient
        Extract-->>DocSvc: text, method=EMBEDDED_TEXT
    else Fallback to markdown
        Extract->>Extract: pymupdf4llm.to_markdown()
        Extract-->>DocSvc: text, method=MARKDOWN
    else Fallback to OCR
        Extract->>Extract: OpenCV + Pillow OCR
        Extract-->>DocSvc: text, method=OCR
    end
    DocSvc->>Profile: extract_profile_from_cv_text(text)
    Profile->>OR: Step 1 — Reconstruct clean CV text (qwen2.5)
    OR-->>Profile: clean_text (plain text by section)
    Profile->>OR: Step 2 — Parse → CandidateProfile schema (qwen2.5)
    OR-->>Profile: CandidateProfile JSON
    Profile-->>DocSvc: CandidateProfile, step1_text, versions
    DocSvc->>DB: UPSERT profile_information
    DocSvc->>DB: UPDATE documents (status=COMPLETED, extraction_method)
    FastAPI-->>Browser: Flash success, redirect to /documents
```
