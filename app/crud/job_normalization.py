"""CRUD operations for the JobNormalization model.

Handle database interactions for creating and reading job normalisation
records keyed by either an API-sourced job ID or a manual job posting ID.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job_normalization import JobNormalization


def create_job_normalization(
    db: Session,
    *,
    normalized_data: dict[str, Any],
    llm_model: str,
    job_id: int | None = None,
    manual_job_posting_id: int | None = None,
) -> JobNormalization:
    """Create and flush a new job normalisation record.

    :param db: Active database session.
    :param normalized_data: Serialised ``JobNormalizationSchema`` dict.
    :param llm_model: Model identifier used for normalisation (e.g. ``"mock"``).
    :param job_id: FK to an API-sourced job, or ``None``.
    :param manual_job_posting_id: FK to a manual job posting, or ``None``.
    :return: Newly created JobNormalization record.
    """
    record = JobNormalization(
        job_id=job_id,
        manual_job_posting_id=manual_job_posting_id,
        normalized_data=normalized_data,
        llm_model=llm_model,
    )
    db.add(record)
    db.flush()
    return record


def get_normalization_by_job_id(
    db: Session,
    *,
    job_id: int,
) -> JobNormalization | None:
    """Return the most recent normalisation record for an API-sourced job.

    :param db: Active database session.
    :param job_id: Identifier of the source job.
    :return: Matching normalisation or ``None``.
    """
    stmt = (
        select(JobNormalization)
        .where(JobNormalization.job_id == job_id)
        .order_by(JobNormalization.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_normalizations_for_job_ids(
    db: Session,
    *,
    job_ids: list[int],
) -> dict[int, Any]:
    """Return the most recent normalisation data keyed by job ID.

    Issue a single query for all requested job IDs and keep only the newest
    record per job when duplicates exist.

    :param db: Active database session.
    :param job_ids: List of API-sourced job identifiers to look up.
    :return: Mapping of ``job_id`` → ``normalized_data`` dict.
    """
    if not job_ids:
        return {}

    stmt = (
        select(JobNormalization)
        .where(JobNormalization.job_id.in_(job_ids))
        .order_by(JobNormalization.job_id, JobNormalization.created_at.desc())
    )
    rows = db.execute(stmt).scalars().all()

    result: dict[int, Any] = {}
    for row in rows:
        if row.job_id not in result:
            result[row.job_id] = row.normalized_data
    return result


def get_normalization_by_manual_job_id(
    db: Session,
    *,
    manual_job_posting_id: int,
) -> JobNormalization | None:
    """Return the most recent normalisation record for a manual job posting.

    :param db: Active database session.
    :param manual_job_posting_id: Identifier of the source manual posting.
    :return: Matching normalisation or ``None``.
    """
    stmt = (
        select(JobNormalization)
        .where(JobNormalization.manual_job_posting_id == manual_job_posting_id)
        .order_by(JobNormalization.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()
