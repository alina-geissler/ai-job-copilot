# Architecture Diagram

## Title
AI Job Copilot — High-Level Layered Architecture

## Explanation
The application follows a modular monolith pattern with four clearly separated layers. External systems (job API, OpenAI, MinIO) are accessed only through the service layer, keeping routes thin and CRUD modules stateless.

## Mermaid Diagram

```mermaid
graph TB
    subgraph Client["Browser (Client)"]
        UI["Jinja2 HTML + HTMX + Alpine.js"]
    end

    subgraph FastAPI["FastAPI Application (Modular Monolith)"]
        direction TB
        subgraph Routes["API Layer — app/api/routes/"]
            R1[auth.py]
            R2[jobs.py]
            R3[cover_letter.py]
            R4[application_tracker.py]
            R5[documents.py]
            R6[search_profiles.py]
            R7[dashboard.py / profile.py]
        end

        subgraph Services["Service Layer — app/services/"]
            S1[job_search_policy.py]
            S2[cover_letter_service.py]
            S3[job_normalization_service.py]
            S4[profile_extraction.py]
            S5[document_service.py]
            S6[auth_service.py]
        end

        subgraph CRUD["Data Access Layer — app/crud/"]
            C1[user.py]
            C2[jobs.py / search_run.py]
            C3[cover_letter.py]
            C4[documents.py]
            C5[profile_information.py]
        end

        subgraph Core["Core — app/core/ + app/dependencies/"]
            CO1[config.py — Settings]
            CO2[auth.py — Session Guard]
            CO3[providers.py — DI]
            CO4[enums.py]
        end
    end

    subgraph External["External Systems"]
        DB[(PostgreSQL 16)]
        MINIO[(MinIO / S3)]
        OPENAI[OpenAI API\ngpt-5-mini]
        RAPID[RapidAPI / JSearch]
        OPENROUTER[OpenRouter\nqwen2.5]
    end

    Client -->|HTTP POST/GET| Routes
    Routes -->|delegates| Services
    Routes -->|reads context from| Core
    Services -->|reads/writes via session| CRUD
    CRUD -->|SQLAlchemy ORM| DB
    Services -->|document upload/download| MINIO
    Services -->|LLM calls| OPENAI
    Services -->|CV extraction| OPENROUTER
    Services -->|job search| RAPID
```
