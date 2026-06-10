# Additional Diagrams

## Title
AI Job Copilot — AI Pipeline Flows & Deployment Diagram

---

## 1. Cover Letter Generation — 3-Call LLM Pipeline

```mermaid
flowchart TD
    START([Cover Letter\nGeneration Request]) --> PREP

    subgraph PREP["Preparation"]
        P1[Resolve job text\nfrom DB]
        P2[Normalize job\nget_or_create_normalization]
        P3[Load user profile\nfrom profile_information]
        P4[Build profile_dict\nEXCLUDE phone, email,\naddress, name]
        P1 --> P2 --> P3 --> P4
    end

    PREP --> CALLA

    subgraph CALLA["Call A — Analysis (gpt-5-mini, reasoning=medium)"]
        A1["Input:\n• Normalized job (filtered)\n• Profile dict\n• Tone + industry + hierarchy\n• must_haves, no_gos\n• company context"]
        A2["Process:\nIdentify fit, gaps, evidence,\nkeywords, company angle,\nvalue proposition"]
        A3["Output: fit_plan\n• supported_ats_keywords\n• missing_requirements\n• evidence_points\n• must_include / must_avoid\n• salary_line, start_date_line"]
        A1 --> A2 --> A3
    end

    CALLA --> CALLB

    subgraph CALLB["Call B — Writing (gpt-5-mini, reasoning=low)"]
        B1["Input:\n• fit_plan from Call A\n• Tone style params\n• Industry lexicon rules\n• Hierarchy arg structure\n• Gender-safe salutation"]
        B2["Process:\nGenerate prose letter\n330-380 words\nhard max 2300 chars"]
        B3["Output:\n• subject_line\n• salutation\n• introduction\n• main_body_qualifications\n• main_body_fit\n• conclusion"]
        B1 --> B2 --> B3
    end

    CALLB --> LENCHECK{Length\n<2300 chars?}
    LENCHECK -->|Yes| CALLC
    LENCHECK -->|No| RETRY_B[Retry Call B\nwith compress instruction]
    RETRY_B --> CALLC

    subgraph CALLC["Call C — Verification (gpt-5-mini, reasoning=low)"]
        C1["Input:\n• Generated letter\n• must_avoid topics\n• no_gos from user"]
        C2["Process:\nScan for violations\nincl. paraphrases,\neuphemisms, allusions"]
        C3["Output:\n• violations list\n• evidence sentences"]
        C1 --> C2 --> C3
    end

    CALLC --> VIOLATIONS{Violations\nfound?}
    VIOLATIONS -->|No| INJECT
    VIOLATIONS -->|Yes| REMEDIAL[Remedial Call B\nwith avoid-list]
    REMEDIAL --> INJECT

    subgraph INJECT["Post-LLM Injection (never sent to model)"]
        I1[Add: first_name, last_name]
        I2[Add: email, phone]
        I3[Add: street, city]
        I4[Add: signature_image]
        I1 --> I2 --> I3 --> I4
    end

    INJECT --> SAVE[UPDATE cover_letters\nstatus=COMPLETED\ncontent=JSONB]
    SAVE --> SNAPSHOT[INSERT cover_letter_snapshots\nrevision_type=INITIAL]
    SNAPSHOT --> DONE([User redirected\nto editor])
```

---

## 2. Job Normalization Pipeline

```mermaid
flowchart LR
    A([Raw Job Text]) --> B{Already\nnormalized?}
    B -->|Yes| C[Load from\njob_normalizations]
    B -->|No| D[Build prompt\nfrom job_normalization.py v2]
    D --> E["OpenAI Responses API\nmodel: gpt-5-mini\nreasoning: medium\nstructured output: strict=False\nmax_tokens: 16,000"]
    E --> F[Validate → JobNormalizationSchema]
    F --> G[INSERT job_normalizations]
    G --> H[Append to\nevals/job_normalizations.jsonl]
    H --> C
    C --> I([Return\nJobNormalizationSchema])

    subgraph Schema["JobNormalizationSchema fields"]
        S1[title, company, location]
        S2[contact_person + gender]
        S3[industry_group, hierarchy_level]
        S4[role_summary]
        S5[responsibilities list]
        S6[required + nice_to_have competencies]
        S7[technical skills]
        S8[ats_keywords]
        S9[ad_language]
    end
```

---

## 3. CV Profile Extraction — 2-Step Pipeline

```mermaid
flowchart TD
    A([Raw CV Text\nfrom PDF]) --> S1

    subgraph STEP1["Step 1 — Text Reconstruction"]
        S1["OpenRouter: qwen2.5-7b-instruct\nprompt: profile_extraction_step1.py (step1_v1)\nTask: Rewrite as clean, structured\nplain text grouped by sections"]
        S1 --> S1O[Output: clean_text\n(plain text, all info preserved)]
    end

    S1O --> S2

    subgraph STEP2["Step 2 — Structured Extraction"]
        S2["OpenRouter: qwen2.5-7b-instruct\nprompt: profile_extraction.py (step2_v3)\nTask: Map clean_text → CandidateProfile\nusing beta.chat.completions.parse"]
        S2 --> S2O["Output: CandidateProfile\n• first_name, last_name\n• email, phone, street, city\n• target_role, seniority\n• work_experience (list)\n• education (list)\n• skills, languages\n• certifications, projects\n• publications, volunteering"]
    end

    S2O --> UPSERT[UPSERT profile_information\n(one row per user)]
    UPSERT --> LOG[Append to\nevals/profile_extractions.jsonl]
    LOG --> DONE([Profile available\nfor cover letter generation])
```

---

## 4. Deployment Architecture

```mermaid
graph TB
    subgraph Dev["Developer Machine (localhost)"]
        APP["FastAPI App\nuvicorn --reload\nPort 8000"]
        
        subgraph Docker["Docker Compose"]
            PG["PostgreSQL 16\nPort 5432\nVolume: postgres_data"]
            MINIO["MinIO S3\nPort 9000 (API)\nPort 9001 (Console)\nVolume: minio_data"]
            OLLAMA["Ollama (Local LLM)\nPort 11434\nVolume: ollama_data\nModel: qwen2.5:7b"]
        end
    end

    subgraph External["External APIs (Cloud)"]
        OPENAI["OpenAI API\ngpt-5-mini\nResponses API"]
        OPENROUTER["OpenRouter\nqwen2.5-7b-instruct\n(CV extraction)"]
        RAPID["RapidAPI / JSearch\n(live job search)"]
    end

    Browser["Browser"] --> APP
    APP --> PG
    APP --> MINIO
    APP --> OLLAMA
    APP --> OPENAI
    APP --> OPENROUTER
    APP --> RAPID
```

---

## 5. Session Authentication Flow

```mermaid
flowchart TD
    A([HTTP Request]) --> B{user_id in\nsession?}
    B -->|No| ERR1[Raise AuthenticationRequiredError\nreason=LOGIN_REQUIRED]
    B -->|Yes| C{idle_timeout\nexceeded?\nnow - last_seen > 30min}
    C -->|Yes| ERR2[Clear session\nRaise SESSION_EXPIRED]
    C -->|No| D{absolute_timeout\nexceeded?\nnow - created_at > 8h}
    D -->|Yes| ERR3[Clear session\nRaise SESSION_EXPIRED]
    D -->|No| E[SELECT users WHERE id=user_id]
    E --> F{User found\nand active?}
    F -->|No| ERR4[Clear session\nRaise USER_NOT_FOUND]
    F -->|Yes| G[Update session\nlast_seen = now]
    G --> H([Return User to route\nhandler])

    ERR1 --> REDIRECT["303 → /auth\nwith German flash message"]
    ERR2 --> REDIRECT
    ERR3 --> REDIRECT
    ERR4 --> REDIRECT
```
