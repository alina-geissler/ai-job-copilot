"""CRUD operations for the Job model.

Handles database interactions for creating, reading, and updating
persisted external job records from provider search results.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.schemas.job_search_results import JobSearchResult


def get_job_by_external_id_and_source(
    db: Session,
    *,
    external_job_id: str,
    source: str
) -> Job | None:
    """Return one persisted external job identified by provider ID and source.

    :param db: Active database session.
    :param external_job_id: Provider-specific job identifier.
    :param source: Source/provider name of the external job.
    :return: Matching persisted job or ``None``.
    """
    stmt = (
        select(Job)
        .where(
            Job.external_job_id == external_job_id,
            Job.source == source
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def create_job_from_search_result(
    db: Session,
    *,
    job_in: JobSearchResult
) -> Job:
    """Create and flush a new persisted job from one normalized search result.

    :param db: Active database session.
    :param job_in: Normalized provider result.
    :return: Newly created persisted job.
    """
    job = Job(
        external_job_id=job_in.external_job_id,
        source=job_in.source,
        title=job_in.title,
        company=job_in.company,
        company_logo=job_in.company_logo,
        location=job_in.location,
        is_remote=job_in.is_remote,
        employment_type=job_in.employment_type,
        job_url=job_in.job_url,
        description=job_in.description,
        published_at=job_in.published_at
    )
    db.add(job)
    db.flush()
    return job


def update_job_from_search_result(
    db: Session,
    *,
    job: Job,
    job_in: JobSearchResult
) -> Job:
    """Update selected mutable fields of an existing persisted external job.

    Keep the external identity stable and refresh user-visible provider fields
    when a later API response contains newer or more complete values.

    :param db: Active database session.
    :param job: Existing persisted job.
    :param job_in: Normalized provider result.
    :return: Updated persisted job.
    """
    job.title = job_in.title
    job.company = job_in.company
    job.company_logo = job_in.company_logo
    job.location = job_in.location
    job.is_remote = job_in.is_remote
    job.employment_type = job_in.employment_type
    job.job_url = job_in.job_url
    job.description = job_in.description
    job.published_at = job_in.published_at

    db.add(job)
    db.flush()
    return job


def get_or_create_job_from_search_result(
    db: Session,
    *,
    job_in: JobSearchResult
) -> tuple[Job, bool]:
    """Return a persisted job for one normalized provider result.

    External jobs are deduplicated via ``external_job_id`` plus ``source``.
    When a matching job already exists, its mutable fields are refreshed from
    the latest provider payload.

    :param db: Active database session.
    :param job_in: Normalized provider result.
    :return: Tuple of ``(job, created)``.
    :raises ValueError: If the provider result lacks deduplication fields.
    """
    if not job_in.external_job_id or not job_in.source:
        raise ValueError(
            "External search results must include external_job_id and source "
            "to be persisted safely."
        )

    existing_job = get_job_by_external_id_and_source(
        db,
        external_job_id=job_in.external_job_id,
        source=job_in.source
    )

    if existing_job is not None:
        updated_job = update_job_from_search_result(
            db,
            job=existing_job,
            job_in=job_in
        )
        return updated_job, False

    created_job = create_job_from_search_result(
        db,
        job_in=job_in
    )
    return created_job, True