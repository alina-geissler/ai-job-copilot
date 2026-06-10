# ER Diagram

## Title
AI Job Copilot — Entity Relationship Diagram (All 13 Tables)

## Explanation
All tables with their primary keys, foreign keys, key columns, and relationships. Source: `app/models/` and `alembic/versions/` (15 migration files).

## Mermaid ER Diagram

```mermaid
erDiagram
    users {
        int id PK
        string email UK
        string password_hash
        string role
        int trial_job_searches_left
        bool is_active
        timestamp created_at
        timestamp updated_at
    }

    search_profiles {
        int id PK
        int user_id FK
        string profile_name
        string query
        string location
        bool remote_only
        string[] employment_types
        string[] experience_levels
        int radius_km
        timestamp created_at
        timestamp updated_at
    }

    search_runs {
        int id PK
        int user_id FK
        int search_profile_id FK
        string query_snapshot
        string location_snapshot
        bool remote_only_snapshot
        string[] employment_types_snapshot
        string[] experience_levels_snapshot
        date run_date
        string date_posted
        int current_page
        int total_jobs_loaded
        int total_new_jobs_loaded
        bool can_load_more
        timestamp created_at
        timestamp updated_at
    }

    jobs {
        int id PK
        string external_job_id
        string source
        string title
        string company
        string company_logo
        string location
        bool is_remote
        string employment_type
        string job_url
        text description
        timestamp published_at
        timestamp imported_at
    }

    search_run_jobs {
        int id PK
        int search_run_id FK
        int job_id FK
        bool is_previously_seen
        int page_number
        int result_position
        timestamp created_at
    }

    job_normalizations {
        int id PK
        int job_id FK
        int manual_job_posting_id FK
        jsonb normalized_data
        string llm_model
        timestamp created_at
        timestamp updated_at
    }

    manual_job_postings {
        int id PK
        int user_id FK
        string title
        string company
        text raw_text
        timestamp created_at
    }

    application_tracker_entries {
        int id PK
        int user_id FK
        int job_id FK
        string status
        text notes
        timestamp applied_at
        timestamp interview_at
        timestamp offer_at
        timestamp rejected_at
        timestamp withdrawn_at
        timestamp created_at
    }

    documents {
        int id PK
        int user_id FK
        string document_type
        string document_name
        string original_filename
        string storage_key UK
        string mime_type
        int file_size_bytes
        string processing_status
        string extraction_method
        text extracted_text
        string extraction_error
        timestamp created_at
        timestamp updated_at
    }

    profile_information {
        int id PK
        int user_id FK UK
        string first_name
        string last_name
        string email
        string street
        string city
        string location
        string phone
        string target_role
        string seniority_level
        bool leadership_experience
        string salary_expectation
        string work_model
        string availability
        json employment_types
        json work_experience
        json education
        json certifications
        json projects
        json soft_skills
        json hard_skills
        json languages
        text signature_image
        text cv_reconstruction
        string extraction_error
        timestamp created_at
        timestamp updated_at
    }

    cover_letters {
        int id PK
        int user_id FK
        int job_id FK
        int manual_job_posting_id FK
        int job_normalization_id FK
        string template
        string tone
        text must_haves
        text no_gos
        text personal_motivation
        text why_company
        text added_value
        string earliest_start_date
        string salary_expectation
        string industry_group
        string hierarchy_level
        string output_language
        text company_context
        jsonb content
        string generation_status
        string generation_error
        string document_name
        string document_filename
        bool is_saved
        jsonb layout_settings
        timestamp created_at
        timestamp updated_at
    }

    cover_letter_snapshots {
        int id PK
        int cover_letter_id FK
        jsonb content
        string revision_type
        int version_number
        timestamp created_at
    }

    users ||--o{ search_profiles : "owns"
    users ||--o{ search_runs : "runs"
    users ||--o{ manual_job_postings : "pastes"
    users ||--o{ application_tracker_entries : "tracks"
    users ||--o{ documents : "uploads"
    users ||--|| profile_information : "has one"
    users ||--o{ cover_letters : "creates"

    search_profiles ||--o{ search_runs : "executed as"
    search_runs ||--o{ search_run_jobs : "contains"
    jobs ||--o{ search_run_jobs : "appears in"

    jobs ||--o| job_normalizations : "normalized to"
    manual_job_postings ||--o| job_normalizations : "normalized to"

    jobs ||--o| application_tracker_entries : "tracked in"
    jobs ||--o{ cover_letters : "basis for"
    manual_job_postings ||--o{ cover_letters : "basis for"
    job_normalizations ||--o{ cover_letters : "informs"

    cover_letters ||--o{ cover_letter_snapshots : "versioned as"
```
