# Data Flow Diagram

## Title
AI Job Copilot — Request & Data Flow

## Explanation
Illustrates how data moves from browser to database and back, including AI calls, for the two most important workflows: job search and cover letter generation.

---

## Flow 1: Job Search Request

```mermaid
flowchart LR
    A([User clicks\n"Suchen"]) --> B[POST /jobs/search/profile_id]
    B --> C{job_search_policy:\ndecide_primary_search}
    C -->|BLOCKED| D[Render error flash\nand redirect]
    C -->|SHOW_EXISTING| E[Load cached run\nfrom DB]
    C -->|START_NEW_RUN| F{Provider\nselection}
    F -->|fixture| G[FixtureJobSearchProvider\nreturns hardcoded data]
    F -->|live| H[HTTP GET RapidAPI/JSearch\nhttpx client]
    G --> I[job_search_response_mapper:\nMap → ORM objects]
    H --> I
    I --> J[job_search_persistence:\nINSERT jobs, search_run, search_run_jobs]
    J --> K[(PostgreSQL)]
    E --> L[Render job_results.html]
    J --> L
```

---

## Flow 2: Cover Letter Generation

```mermaid
flowchart TD
    A([User submits\nsetup form]) --> B[POST /cover-letter/generate]
    B --> C[cover_letter_service:\ninitiate_cover_letter_generation]
    C --> D[INSERT cover_letter\nstatus=PENDING]
    D --> E[Enqueue BackgroundTask]
    B --> F[Redirect → cover_letter_generating.html\nHTMX polls status every 2s]

    subgraph Background Worker
        E --> G[Resolve job text\nfrom DB]
        G --> H[job_normalization_service:\nget_or_create_normalization]
        H --> I{Cached?}
        I -->|Yes| J[Load from DB]
        I -->|No| K[OpenAI Responses API\nstructured output\ngpt-5-mini]
        K --> L[INSERT job_normalizations]
        L --> J
        J --> M[Load profile_information\nfrom DB]
        M --> N["Call A — Analysis\nOpenAI: fit_plan\n(keywords, evidence, gaps)"]
        N --> O["Call B — Writing\nOpenAI: full letter prose\n(with length check)"]
        O --> P{>2300 chars?}
        P -->|Yes| Q[Compress & retry\nCall B once]
        Q --> R["Call C — Verification\nOpenAI: no-go compliance check"]
        P -->|No| R
        R --> S{Violations?}
        S -->|Yes| T[Remedial regen\nCall B once]
        T --> U[Inject private contact fields\nfrom profile NOT sent to LLM]
        S -->|No| U
        U --> V[UPDATE cover_letter\nstatus=COMPLETED\ncontent=JSONB]
        V --> W[INSERT cover_letter_snapshot\nrevision_type=INITIAL]
    end

    F -->|poll resolves| X[Redirect → cover_letter_editor.html]
```

---

## Flow 3: CV Upload & Profile Extraction

```mermaid
flowchart TD
    A([User uploads\nPDF CV]) --> B[POST /documents/upload]
    B --> C[document_service:\nvalidate + store to MinIO]
    C --> D[INSERT document\nstatus=PENDING]
    D --> E[Enqueue BackgroundTask]

    subgraph Extraction Pipeline
        E --> F[document_extraction:\nextract text from PDF]
        F --> G{Method}
        G -->|embedded text| H[PyMuPDF embedded text]
        G -->|markdown| I[pymupdf4llm markdown]
        G -->|OCR| J[OpenCV + Pillow OCR]
        H --> K[Step 1: OpenRouter qwen2.5\nReconstruct clean CV text]
        I --> K
        J --> K
        K --> L[Step 2: OpenRouter qwen2.5\nStructured parse → CandidateProfile]
        L --> M[UPSERT profile_information]
        M --> N[UPDATE document\nstatus=COMPLETED]
    end
```
