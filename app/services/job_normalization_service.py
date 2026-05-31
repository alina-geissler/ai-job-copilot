"""Service functions for job advertisement normalisation.

Coordinate normalisation of raw job text into a structured
``JobNormalizationSchema`` and persist the result. Phase 1 uses a mock
implementation; phase 2 will replace ``_call_llm`` with an OpenAI
``beta.chat.completions.parse()`` call against ``JobNormalizationSchema``.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.crud.job_normalization import (
    create_job_normalization,
    get_normalization_by_job_id,
    get_normalization_by_manual_job_id,
)
from app.models.job import Job
from app.models.job_normalization import JobNormalization
from app.schemas.job_normalization import JobNormalizationSchema

logger = logging.getLogger(__name__)


def normalize_job(
    raw_text: str,
    existing_job: Job | None = None,
) -> JobNormalizationSchema:
    """Return a structured normalisation of the given job advertisement text.

    Phase 1: returns a hardcoded mock ``JobNormalizationSchema``.
    Phase 2: replace the body with an OpenAI structured-output call:
        ``client.beta.chat.completions.parse(response_format=JobNormalizationSchema, ...)``

    When ``existing_job`` is provided its structured fields (title, company,
    location, employment_type) are used to pre-populate identity/company
    fields so the LLM focuses on extracting what is missing.

    :param raw_text: Full text of the job advertisement.
    :param existing_job: Optional API-sourced Job record for pre-population.
    :return: Normalised job schema instance.
    """
    # -- Phase 2 hook: replace everything below with the real LLM call ----------
    company = existing_job.company if existing_job else "Musterunternehmen GmbH"
    title = existing_job.title if existing_job else "Software-Entwicklerin / Software-Entwickler"
    location = existing_job.location if existing_job else "Berlin, Deutschland"

    return JobNormalizationSchema(
        canonical_job_title=title,
        job_title_variants=[title],
        role_summary="Spannende Position in einem wachsenden Unternehmen mit modernen Technologien.",
        company_name=company,
        job_location=location,
        employment_type=existing_job.employment_type if existing_job else "Vollzeit",
        work_model="Hybrid",
        seniority_level="Berufserfahren",
        responsibilities=[
            "Entwicklung und Wartung von Backend-Services",
            "Code-Reviews und technische Dokumentation",
            "Zusammenarbeit mit interdisziplinären Teams",
        ],
        core_tasks=[
            "Implementierung neuer Features",
            "Bugfixing und Performance-Optimierung",
        ],
        must_have_competencies=[
            "Python",
            "SQL",
            "REST-APIs",
        ],
        nice_to_have_competencies=[
            "Docker",
            "Kubernetes",
            "Cloud-Erfahrung (AWS / GCP)",
        ],
        soft_skills=["Teamfähigkeit", "Eigenverantwortung", "Kommunikationsstärke"],
        ats_priority_keywords=["Python", "FastAPI", "PostgreSQL", "Agile", "REST"],
        action_verbs=["entwickeln", "implementieren", "optimieren", "koordinieren"],
        education_requirements=["Abgeschlossenes Studium der Informatik oder vergleichbare Qualifikation"],
        language_requirements=["Deutsch (fließend)", "Englisch (gut)"],
        benefits_perks=["Flexible Arbeitszeiten", "Home-Office-Option", "Weiterbildungsbudget"],
        posting_language="de",
        confidence_scores={"canonical_job_title": 0.95, "company_name": 0.99},
    )


def get_or_create_normalization(
    db: Session,
    *,
    job_id: int | None,
    manual_job_posting_id: int | None,
    raw_text: str,
    existing_job: Job | None = None,
) -> JobNormalization:
    """Return the existing normalisation record or create a new one.

    Checks the database for an existing record keyed by the given job or
    manual posting ID before calling the normalisation service. This avoids
    redundant LLM calls when multiple cover letters are generated for the
    same job.

    :param db: Active database session.
    :param job_id: FK to an API-sourced job, or ``None``.
    :param manual_job_posting_id: FK to a manual job posting, or ``None``.
    :param raw_text: Full text of the job advertisement.
    :param existing_job: Optional API-sourced Job record for pre-population.
    :return: Existing or newly created JobNormalization record.
    """
    if job_id is not None:
        existing = get_normalization_by_job_id(db, job_id=job_id)
        if existing is not None:
            return existing

    if manual_job_posting_id is not None:
        existing = get_normalization_by_manual_job_id(
            db, manual_job_posting_id=manual_job_posting_id
        )
        if existing is not None:
            return existing

    schema = normalize_job(raw_text, existing_job=existing_job)

    return create_job_normalization(
        db,
        normalized_data=schema.model_dump(),
        llm_model="mock",
        job_id=job_id,
        manual_job_posting_id=manual_job_posting_id,
    )
