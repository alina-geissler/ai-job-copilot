"""Shared in-process state and background task runner for job normalisation.

Provide the in-memory error store and the background-task function used by
both the cover-letter flow and the direct-analyse endpoints so that they
share a single key-space and do not duplicate logic.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# In-memory normalisation error tracking (single-process dev server only).
# Key: "job_{id}" or "manual_{id}"; value: error message string.
# An absent key means the task is either pending, running, or completed.
NORM_ERRORS: dict[str, str] = {}


def norm_task_key(job_id: int | None, manual_job_id: int | None) -> str:
    """Return a stable string key for tracking per-job normalisation state.

    :param job_id: API-sourced job identifier, or ``None``.
    :param manual_job_id: Manual job posting identifier, or ``None``.
    :return: String key used in :data:`NORM_ERRORS`.
    """
    if job_id is not None:
        return f"job_{job_id}"
    return f"manual_{manual_job_id}"


def run_normalization_task(
    *, job_id: int | None, manual_job_id: int | None
) -> None:
    """Background task: normalise a job ad and persist the result.

    Opens its own database session, resolves the raw job text, calls the
    normalisation service, and commits the result. Errors are stored in
    :data:`NORM_ERRORS` so polling endpoints can surface them.

    :param job_id: API-sourced job identifier, or ``None``.
    :param manual_job_id: Manual job posting identifier, or ``None``.
    """
    from app.db.session import SessionLocal
    from app.models.job import Job
    from app.models.manual_job_posting import ManualJobPosting
    from app.services.job_normalization_service import get_or_create_normalization

    key = norm_task_key(job_id, manual_job_id)
    db = SessionLocal()
    try:
        existing_job = None
        if job_id is not None:
            job = db.get(Job, job_id)
            if job is None:
                NORM_ERRORS[key] = "Job nicht gefunden."
                return
            raw_text: str = job.description or job.title or ""
            existing_job = job
        elif manual_job_id is not None:
            posting = db.get(ManualJobPosting, manual_job_id)
            if posting is None:
                NORM_ERRORS[key] = "Stellenangebot nicht gefunden."
                return
            raw_text = posting.raw_text
        else:
            NORM_ERRORS[key] = "Kein Job angegeben."
            return

        if not raw_text:
            NORM_ERRORS[key] = "Kein Anzeigentext gefunden."
            return

        normalization = get_or_create_normalization(
            db,
            job_id=job_id,
            manual_job_posting_id=manual_job_id,
            raw_text=raw_text,
            existing_job=existing_job,
        )

        # For manually added jobs, back-fill Job.title/company from canonical
        # normalization values so the tracker list reflects the real position.
        if manual_job_id is not None and normalization is not None:
            norm_data = normalization.normalized_data or {}
            canonical_title = norm_data.get("canonical_job_title") or ""
            canonical_company = norm_data.get("company_name") or ""
            _TITLE_PLACEHOLDER = "Manuell eingetragene Stelle"
            _COMPANY_PLACEHOLDER = "Unbekanntes Unternehmen"
            from app.models.application_tracker_entry import ApplicationTrackerEntry
            from sqlalchemy import select
            stmt = (
                select(ApplicationTrackerEntry)
                .where(ApplicationTrackerEntry.manual_job_posting_id == manual_job_id)
                .limit(1)
            )
            linked_entry = db.execute(stmt).scalar_one_or_none()
            if linked_entry is not None and linked_entry.job_id is not None:
                job = db.get(Job, linked_entry.job_id)
                if job is not None and job.source == "manual":
                    if canonical_title and job.title in (None, "", _TITLE_PLACEHOLDER):
                        job.title = canonical_title
                    if canonical_company and job.company in (None, "", _COMPANY_PLACEHOLDER):
                        job.company = canonical_company

        db.commit()
        NORM_ERRORS.pop(key, None)
    except Exception as exc:
        logger.exception("Normalization task failed for key=%s: %s", key, exc)
        NORM_ERRORS[key] = str(exc)[:200]
    finally:
        db.close()
