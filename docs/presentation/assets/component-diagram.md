# Component Diagram

## Title
AI Job Copilot — Component Interaction Map

## Explanation
Shows which components call which, and which external services each component depends on. The service layer is the integration hub — it is the only layer that touches external APIs.

## Mermaid Diagram

```mermaid
graph LR
    subgraph Browser
        HTM["HTMX Polling\n(job analysis, cover letter prep)"]
        ALP["Alpine.js\n(toggle UI state)"]
    end

    subgraph Routes
        RJ[jobs.py]
        RCL[cover_letter.py]
        RD[documents.py]
        RA[auth.py]
        RT[application_tracker.py]
    end

    subgraph Services
        SP[job_search_policy.py]
        SL[live_job_search_provider.py]
        SF[fixture_job_search_provider.py]
        SRM[job_search_response_mapper.py]
        SPS[job_search_persistence.py]
        SN[job_normalization_service.py]
        SCL[cover_letter_service.py]
        SPR[profile_extraction.py]
        SD[document_service.py]
        SS[document_storage.py]
        SE[document_extraction.py]
        SA[auth_service.py]
    end

    subgraph CRUD
        CJ[crud/job.py]
        CCL[crud/cover_letter.py]
        CD[crud/document.py]
        CP[crud/profile_information.py]
        CU[crud/user.py]
        CSR[crud/search_run.py]
    end

    subgraph DB
        PG[(PostgreSQL)]
    end

    subgraph External
        OAI[OpenAI API]
        OR[OpenRouter]
        RA_EXT[RapidAPI / JSearch]
        MINIO[(MinIO S3)]
    end

    Browser -->|form POST| Routes

    RJ --> SP
    SP -->|decision| SL
    SP -->|decision| SF
    SL --> RA_EXT
    SL --> SRM
    SRM --> SPS
    SPS --> CJ
    SPS --> CSR

    RCL --> SCL
    SCL --> SN
    SN --> OAI
    SCL --> OAI
    SCL --> CCL

    RD --> SD
    SD --> SE
    SD --> SS
    SS --> MINIO
    SD --> SPR
    SPR --> OR
    SD --> CP

    RA --> SA
    SA --> CU

    CRUD --> PG
```
