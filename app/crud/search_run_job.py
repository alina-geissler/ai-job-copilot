"""CRUD operations for the SearchRunJob model.

Handles database interactions for creating and reading persisted
job entries that belong to a specific search run.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.search_run import SearchRun
from app.models.search_run_job import SearchRunJob


def create_search_run_job(
    db: Session,
    *,
    search_run_id: int,
    job_id: int,
    is_previously_seen: bool,
    page_number: int,
    result_position: int,
) -> SearchRunJob:
    """Create and flush one persisted job entry inside a search run.

    :param db: Active SQLAlchemy database session.
    :param search_run_id: Identifier of the owning search run.
    :param job_id: Identifier of the persisted job.
    :param is_previously_seen: Whether the job was already seen in an earlier run.
    :param page_number: Provider page number from which the job was loaded.
    :param result_position: Absolute result position inside the persisted search run.
    :return: Newly created persisted search-run-job ORM object.
    """
    search_run_job = SearchRunJob(
        search_run_id=search_run_id,
        job_id=job_id,
        is_previously_seen=is_previously_seen,
        page_number=page_number,
        result_position=result_position,
    )
    db.add(search_run_job)
    db.flush()
    return search_run_job


def list_search_run_jobs_for_run(
    db: Session,
    *,
    search_run_id: int,
) -> list[SearchRunJob]:
    """Return all persisted job entries of one search run.

    :param db: Active SQLAlchemy database session.
    :param search_run_id: Identifier of the search run.
    :return: List of persisted search-run-job ORM objects ordered by result position.
    """
    stmt = (
        select(SearchRunJob)
        .where(SearchRunJob.search_run_id == search_run_id)
        .options(selectinload(SearchRunJob.job))
        .order_by(SearchRunJob.result_position.asc(), SearchRunJob.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def get_previously_seen_job_ids_for_user(
    db: Session,
    *,
    user_id: int,
    job_ids: set[int] | list[int],
    exclude_search_run_id: int | None = None,
) -> set[int]:
    """Return the subset of given jobs that the user already saw before.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :param job_ids: Job identifiers to check for previous visibility.
    :param exclude_search_run_id: Optional search-run identifier to exclude from the lookup.
    :return: Set of job identifiers that were already seen by the user.
    """
    normalized_job_ids = set(job_ids)
    if not normalized_job_ids:
        return set()

    stmt = (
        select(SearchRunJob.job_id)
        .join(SearchRun, SearchRun.id == SearchRunJob.search_run_id)
        .where(
            SearchRun.user_id == user_id,
            SearchRunJob.job_id.in_(normalized_job_ids),
        )
        .distinct()
    )

    if exclude_search_run_id is not None:
        stmt = stmt.where(SearchRunJob.search_run_id != exclude_search_run_id)

    return set(db.execute(stmt).scalars().all())