"""Persist provider search results into jobs, search runs, and run-job links."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud.job import get_or_create_job_from_search_result
from app.crud.search_run import create_search_run, update_search_run_after_fetch
from app.crud.search_run_job import (
    create_search_run_job,
    get_previously_seen_job_ids_for_user,
)
from app.models.search_profile import SearchProfile
from app.models.search_run import SearchRun
from app.schemas.job_search_results import JobSearchResponse
from app.services.job_search_policy import (
    evaluate_load_more_availability_after_load_more,
    evaluate_primary_search_load_more_availability,
)


@dataclass(slots=True)
class PersistedSearchResult:
    """Return persistence metadata for one provider call."""

    search_run: SearchRun
    total_jobs_in_response: int
    new_jobs_for_user_count: int
    previously_seen_jobs_count: int
    allow_further_load_more: bool
    message: str | None


def persist_primary_search_response(
    db: Session,
    *,
    user_id: int,
    search_profile: SearchProfile,
    run_date: date,
    date_posted: str,
    loaded_page: int,
    search_response: JobSearchResponse,
) -> PersistedSearchResult:
    """Persist the initial five-page provider response as a new search run.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :param search_profile: Search profile used for this run.
    :param run_date: Calendar date of the search run.
    :param date_posted: Provider filter used for published date.
    :param loaded_page: Last loaded provider page for the initial fetch.
    :param search_response: Normalized provider response.
    :return: Persistence metadata for the saved search run.
    """
    try:
        search_run = create_search_run(
            db,
            user_id=user_id,
            search_profile=search_profile,
            run_date=run_date,
            date_posted=date_posted,
            current_page=loaded_page,
            can_load_more=True,
        )

        persistence_batch = _persist_response_jobs_into_run(
            db,
            user_id=user_id,
            search_run=search_run,
            search_response=search_response,
            page_number=loaded_page,
            starting_result_position=1,
            exclude_search_run_id=search_run.id,
        )

        stop_evaluation = evaluate_primary_search_load_more_availability(
            total_jobs_returned=persistence_batch.total_jobs_in_response,
            new_jobs_for_user_count=persistence_batch.new_jobs_for_user_count,
        )

        update_search_run_after_fetch(
            db,
            search_run=search_run,
            current_page=loaded_page,
            total_jobs_loaded=persistence_batch.total_jobs_in_response,
            total_new_jobs_loaded=persistence_batch.new_jobs_for_user_count,
            increment_load_more_requests_used=0,
            can_load_more=stop_evaluation.allow_further_load_more,
        )

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(search_run)

    return PersistedSearchResult(
        search_run=search_run,
        total_jobs_in_response=persistence_batch.total_jobs_in_response,
        new_jobs_for_user_count=persistence_batch.new_jobs_for_user_count,
        previously_seen_jobs_count=persistence_batch.previously_seen_jobs_count,
        allow_further_load_more=stop_evaluation.allow_further_load_more,
        message=stop_evaluation.message,
    )


def persist_load_more_response(
    db: Session,
    *,
    user_id: int,
    search_run: SearchRun,
    loaded_page: int,
    search_response: JobSearchResponse,
) -> PersistedSearchResult:
    """Persist one additional provider page into an existing search run.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :param search_run: Existing persisted search run.
    :param loaded_page: Newly loaded provider page.
    :param search_response: Normalized provider response.
    :return: Persistence metadata for the updated search run.
    """
    try:
        persistence_batch = _persist_response_jobs_into_run(
            db,
            user_id=user_id,
            search_run=search_run,
            search_response=search_response,
            page_number=loaded_page,
            starting_result_position=search_run.total_jobs_loaded + 1,
            exclude_search_run_id=search_run.id,
        )

        stop_evaluation = evaluate_load_more_availability_after_load_more(
            total_jobs_returned=persistence_batch.total_jobs_in_response,
            new_jobs_for_user_count=persistence_batch.new_jobs_for_user_count,
        )

        update_search_run_after_fetch(
            db,
            search_run=search_run,
            current_page=loaded_page,
            total_jobs_loaded=search_run.total_jobs_loaded + persistence_batch.total_jobs_in_response,
            total_new_jobs_loaded=search_run.total_new_jobs_loaded + persistence_batch.new_jobs_for_user_count,
            increment_load_more_requests_used=1,
            can_load_more=stop_evaluation.allow_further_load_more,
        )

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(search_run)

    return PersistedSearchResult(
        search_run=search_run,
        total_jobs_in_response=persistence_batch.total_jobs_in_response,
        new_jobs_for_user_count=persistence_batch.new_jobs_for_user_count,
        previously_seen_jobs_count=persistence_batch.previously_seen_jobs_count,
        allow_further_load_more=stop_evaluation.allow_further_load_more,
        message=stop_evaluation.message,
    )


@dataclass(slots=True)
class _PersistenceBatch:
    """Store intermediate persistence data for one fetched response."""

    total_jobs_in_response: int
    new_jobs_for_user_count: int
    previously_seen_jobs_count: int


def _persist_response_jobs_into_run(
    db: Session,
    *,
    user_id: int,
    search_run: SearchRun,
    search_response: JobSearchResponse,
    page_number: int,
    starting_result_position: int,
    exclude_search_run_id: int | None,
) -> _PersistenceBatch:
    """Persist response jobs and link them to the given search run.

    Invalid or conflicting individual jobs are skipped with a nested
    transaction so the surrounding search run can still be persisted.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :param search_run: Persisted search run to extend.
    :param search_response: Normalized provider response.
    :param page_number: Provider page number of this response.
    :param starting_result_position: First result position for new run-job links.
    :param exclude_search_run_id: Search run id to exclude from previously-seen checks.
    :return: Aggregated persistence statistics for this response.
    """
    persisted_jobs = []
    seen_job_ids_in_run: set[int] = set()

    for result in search_response.results:
        try:
            with db.begin_nested():
                job, _created = get_or_create_job_from_search_result(db, job_in=result)
        except (ValueError, IntegrityError):
            continue

        if job.id in seen_job_ids_in_run:
            continue

        seen_job_ids_in_run.add(job.id)
        persisted_jobs.append(job)

    persisted_job_ids = [job.id for job in persisted_jobs]

    previously_seen_job_ids = get_previously_seen_job_ids_for_user(
        db,
        user_id=user_id,
        job_ids=persisted_job_ids,
        exclude_search_run_id=exclude_search_run_id,
    )

    linked_jobs_count = 0
    linked_previously_seen_count = 0

    for offset, job in enumerate(persisted_jobs):
        try:
            with db.begin_nested():
                create_search_run_job(
                    db,
                    search_run_id=search_run.id,
                    job_id=job.id,
                    is_previously_seen=job.id in previously_seen_job_ids,
                    page_number=page_number,
                    result_position=starting_result_position + linked_jobs_count,
                )
        except IntegrityError:
            continue

        linked_jobs_count += 1
        if job.id in previously_seen_job_ids:
            linked_previously_seen_count += 1

    db.flush()

    return _PersistenceBatch(
        total_jobs_in_response=linked_jobs_count,
        new_jobs_for_user_count=linked_jobs_count - linked_previously_seen_count,
        previously_seen_jobs_count=linked_previously_seen_count,
    )