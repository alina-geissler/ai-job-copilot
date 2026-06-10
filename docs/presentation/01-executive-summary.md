# 01 — Executive Summary

> **Related documents:** [02-architecture.md](02-architecture.md) | [05-features.md](05-features.md) | [09-ai-analysis.md](09-ai-analysis.md)

---

## Project Name

**AI Job Copilot** (`ai-job-copilot`)

---

## Main Purpose

AI Job Copilot is a web-based, AI-powered job search and application management assistant designed for German-speaking job seekers. It centralises the entire job application lifecycle — from discovering relevant positions through to generating tailored cover letters — in a single, integrated platform.

---

## Problem Being Solved

Modern job searching is fragmented and time-consuming:

1. **Discovery is manual** — users must visit multiple platforms and re-enter the same search criteria repeatedly.
2. **Relevance assessment is slow** — reading full job descriptions to judge fit takes significant time.
3. **Application materials are generic** — writing individualised cover letters from scratch for each application is a major effort that most candidates shortcut, reducing their chances.
4. **Tracking is scattered** — applicants manage status updates across spreadsheets, browser bookmarks, and email threads.

AI Job Copilot addresses all four problems in one system.

---

## Target Users

- **Primary:** German-speaking job seekers (students, professionals, career changers)
- **Secondary:** Anyone who applies for multiple positions simultaneously and needs to track their pipeline

The UI is entirely in **German**. The cover letter generator supports both German and English output.

---

## Core Features

| Feature | Description |
|---|---|
| **Search Profile Management** | Reusable named filter sets (query, location, employment type, experience level) |
| **Job Search Execution** | Profile-based job search against RapidAPI/JSearch or fixture data, with daily limits and pagination |
| **Job Normalization (AI)** | Structured analysis of each job description using OpenAI into a consistent schema (requirements, keywords, industry, hierarchy) |
| **Application Tracker** | Kanban-like status progression: SAVED → APPLIED → INTERVIEW → OFFER / REJECTED / WITHDRAWN |
| **CV Upload & Profile Extraction (AI)** | Upload a PDF CV; AI extracts structured candidate profile (experience, skills, education, contact) |
| **Cover Letter Generation (AI)** | 3-call LLM pipeline generates a tailored, tone-appropriate, compliance-checked cover letter |
| **Cover Letter Editor** | In-browser rich editor: contentEditable fields, live A4 preview, template/font/theme selection, PDF export |
| **Document Management** | S3-compatible storage (MinIO), presigned download URLs, document rename/delete |
| **Dark Mode** | System-preference-aware dark/light theme toggle, persisted in localStorage |

---

## High-Level System Overview

AI Job Copilot is a **modular monolith** built on:

- **Backend:** FastAPI (Python) with server-rendered HTML via Jinja2 — no separate frontend SPA
- **Database:** PostgreSQL 16, managed through SQLAlchemy ORM and Alembic migrations (13 tables, 15 migration versions)
- **AI:** OpenAI API (`gpt-5-mini`) for job normalization and cover letter generation; OpenRouter (`qwen2.5-7b`) for CV text extraction
- **Storage:** MinIO (S3-compatible) for document files
- **Frontend:** Tailwind CSS (CDN), HTMX for dynamic interactions, Alpine.js for lightweight state, all JS inline in templates
- **Infrastructure:** Docker Compose (PostgreSQL, MinIO, Ollama for local LLM experiments)

The request lifecycle is: Browser → FastAPI route (thin) → Service layer (business logic + LLM calls) → CRUD layer (DB read/write) → Jinja2 template → HTML response.

Long-running AI operations (cover letter generation, CV extraction) are deferred to FastAPI `BackgroundTasks` and the frontend polls for completion via HTMX.

---

## Key Numbers

| Metric | Value |
|---|---|
| Python source files | ~60 |
| Jinja2 templates | ~33 |
| Database tables | 13 |
| Alembic migrations | 15 |
| Service modules | 19 |
| Route modules | 11 |
| LLM calls per cover letter | 3–5 (analysis + writing + verification + up to 2 retries) |
| Max document upload size | 10 MB |
| Session idle timeout | 30 minutes |
| Session absolute timeout | 8 hours |
