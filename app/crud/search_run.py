"""CRUD operations for the SearchRun model.

Handles database interactions for creating, reading, and updating
persisted search runs and their search-history metadata.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.search_profile import SearchProfile
from app.models.search_run import SearchRun
from app.models.search_run_job import SearchRunJob


def create_search_run(
    db: Session,
    *,
    user_id: int,
    search_profile: SearchProfile,
    run_date: date,
    date_posted: str,
    current_page: int,
    can_load_more: bool = True
) -> SearchRun:
    """Create and flush a new persisted search run with profile snapshots.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :param search_profile: Search profile used to start the run.
    :param run_date: Calendar date of the search run.
    :param date_posted: Effective provider ``date_posted`` filter.
    :param current_page: Last loaded provider page after the current fetch.
    :param can_load_more: Whether further load-more actions are initially allowed.
    :return: Newly created persisted search-run ORM object.
    """
    search_run = SearchRun(
        user_id=user_id,
        search_profile_id=search_profile.id,
        search_profile_name_snapshot=search_profile.profile_name,
        query_snapshot=search_profile.query,
        location_snapshot=search_profile.location,
        remote_only_snapshot=search_profile.remote_only,
        employment_types_snapshot=list(search_profile.employment_types or []),
        experience_levels_snapshot=list(search_profile.experience_levels or []),
        radius_km_snapshot=search_profile.radius_km,
        run_date=run_date,
        date_posted=date_posted,
        current_page=current_page,
        total_jobs_loaded=0,
        total_new_jobs_loaded=0,
        load_more_requests_used=0,
        can_load_more=can_load_more
    )
    db.add(search_run)
    db.flush()
    return search_run


def update_search_run_after_fetch(
    db: Session,
    *,
    search_run: SearchRun,
    current_page: int,
    total_jobs_loaded: int,
    total_new_jobs_loaded: int,
    increment_load_more_requests_used: int,
    can_load_more: bool
) -> SearchRun:
    """Update counters and continuation state after one provider fetch.

    :param db: Active SQLAlchemy database session.
    :param search_run: Existing persisted search run to update.
    :param current_page: Last loaded provider page after the current fetch.
    :param total_jobs_loaded: Total number of jobs linked to this run.
    :param total_new_jobs_loaded: Total number of newly seen jobs linked to this run.
    :param increment_load_more_requests_used: Number of additional load-more actions to add.
    :param can_load_more: Whether further load-more actions remain allowed.
    :return: Updated persisted search-run ORM object.
    """
    search_run.current_page = current_page
    search_run.total_jobs_loaded = total_jobs_loaded
    search_run.total_new_jobs_loaded = total_new_jobs_loaded
    search_run.load_more_requests_used += increment_load_more_requests_used
    search_run.can_load_more = can_load_more
    db.add(search_run)
    db.flush()
    return search_run


def get_search_run_by_id_for_user(
    db: Session,
    *,
    search_run_id: int,
    user_id: int
) -> SearchRun | None:
    """Return one persisted search run belonging to the given user.

    :param db: Active SQLAlchemy database session.
    :param search_run_id: Identifier of the search run.
    :param user_id: Identifier of the owning user.
    :return: Matching persisted search-run ORM object, or ``None`` if not found.
    """
    stmt = (
        select(SearchRun)
        .where(SearchRun.id == search_run_id, SearchRun.user_id == user_id)
        .options(
            selectinload(SearchRun.search_profile),
            selectinload(SearchRun.search_run_jobs).selectinload(SearchRunJob.job)
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def get_latest_search_run_for_profile(
    db: Session,
    *,
    user_id: int,
    search_profile_id: int
) -> SearchRun | None:
    """Return the most recent search run of one user's search profile.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :param search_profile_id: Identifier of the search profile.
    :return: Most recent persisted search-run ORM object, or ``None`` if none exists.
    """
    stmt = (
        select(SearchRun)
        .where(
            SearchRun.user_id == user_id,
            SearchRun.search_profile_id == search_profile_id
        )
        .order_by(SearchRun.run_date.desc(), SearchRun.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_today_search_run_for_profile(
    db: Session,
    *,
    user_id: int,
    search_profile_id: int,
    today: date
) -> SearchRun | None:
    """Return today's search run for one user's search profile, if it exists.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :param search_profile_id: Identifier of the search profile.
    :param today: Calendar date used for the lookup.
    :return: Matching persisted search-run ORM object for today, or ``None`` if not found.
    """
    stmt = (
        select(SearchRun)
        .where(
            SearchRun.user_id == user_id,
            SearchRun.search_profile_id == search_profile_id,
            SearchRun.run_date == today
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def has_primary_search_for_profile_today(
    db: Session,
    *,
    user_id: int,
    search_profile_id: int,
    today: date
) -> bool:
    """Return whether the user already started this search profile today.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :param search_profile_id: Identifier of the search profile.
    :param today: Calendar date used for the lookup.
    :return: ``True`` if a primary search run exists for today, otherwise ``False``.
    """
    stmt = (
        select(func.count(SearchRun.id))
        .where(
            SearchRun.user_id == user_id,
            SearchRun.search_profile_id == search_profile_id,
            SearchRun.run_date == today
        )
    )
    return db.execute(stmt).scalar_one() > 0


def count_primary_searches_for_user_today(
    db: Session,
    *,
    user_id: int,
    today: date
) -> int:
    """Count how many primary searches the user started today.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :param today: Calendar date used for the count.
    :return: Number of primary search runs started today.
    """
    stmt = (
        select(func.count(SearchRun.id))
        .where(
            SearchRun.user_id == user_id,
            SearchRun.run_date == today
        )
    )
    return db.execute(stmt).scalar_one()


def count_load_more_actions_for_user_today(
    db: Session,
    *,
    user_id: int,
    today: date
) -> int:
    """Count how many load-more actions the user has used today.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :param today: Calendar date used for the count.
    :return: Total number of load-more actions used today.
    """
    stmt = (
        select(func.coalesce(func.sum(SearchRun.load_more_requests_used), 0))
        .where(
            SearchRun.user_id == user_id,
            SearchRun.run_date == today
        )
    )
    return db.execute(stmt).scalar_one()


def list_search_runs_for_user(
    db: Session,
    *,
    user_id: int,
    search_profile_id: int | None = None,
    run_date: date | None = None,
    limit: int | None = None
) -> list[SearchRun]:
    """Return persisted search runs for the user's history page.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :param search_profile_id: Optional identifier used to filter by search profile.
    :param run_date: Optional calendar date used to filter the result list.
    :param limit: Optional maximum number of search runs to return.
    :return: List of persisted search-run ORM objects.
    """
    stmt = (
        select(SearchRun)
        .where(SearchRun.user_id == user_id)
        .options(selectinload(SearchRun.search_profile))
        .order_by(SearchRun.run_date.desc(), SearchRun.id.desc())
    )

    if search_profile_id is not None:
        stmt = stmt.where(SearchRun.search_profile_id == search_profile_id)

    if run_date is not None:
        stmt = stmt.where(SearchRun.run_date == run_date)

    if limit is not None:
        stmt = stmt.limit(limit)

    return list(db.execute(stmt).scalars().all())