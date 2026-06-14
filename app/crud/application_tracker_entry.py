"""CRUD operations for the ApplicationTrackerEntry model.

Handle database interactions for creating, reading, updating, and deleting
application tracker entries that belong to one authenticated user.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager, joinedload

from app.core.enums import ApplicationStatus
from app.models.application_tracker_entry import ApplicationTrackerEntry
from app.models.job import Job

_STATUS_DATE_FIELD_BY_STATUS: dict[ApplicationStatus, str | None] = {
    ApplicationStatus.SAVED: None,  # saved/offen uses created_at, so there is no separate saved_at field
    ApplicationStatus.APPLIED: "applied_at",
    ApplicationStatus.INTERVIEW: "interview_at",
    ApplicationStatus.OFFER: "offer_at",
    ApplicationStatus.REJECTED: "rejected_at",
    ApplicationStatus.WITHDRAWN: "withdrawn_at"
}


def _combine_date_to_utc_datetime(value: date) -> datetime:
    """Convert a calendar date into a timezone-aware UTC datetime.

    Store date-only form input as midnight UTC so it can be persisted in the
    existing timezone-aware datetime columns.

    :param value: Submitted calendar date.
    :return: Timezone-aware datetime at midnight UTC.
    """
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def get_tracker_entry_by_job_id_for_user(
    db: Session,
    *,
    user_id: int,
    job_id: int
) -> ApplicationTrackerEntry | None:
    """Return one tracker entry for the given user and job.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param job_id: Identifier of the tracked job.
    :return: Matching tracker entry or ``None``.
    """
    stmt = (
        select(ApplicationTrackerEntry)
        .where(
            ApplicationTrackerEntry.user_id == user_id,
            ApplicationTrackerEntry.job_id == job_id
        )
        .options(joinedload(ApplicationTrackerEntry.job))
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_tracker_entry_by_id_for_user(
    db: Session,
    *,
    entry_id: int,
    user_id: int
) -> ApplicationTrackerEntry | None:
    """Return one tracker entry by identifier for the given user.

    :param db: Active database session.
    :param entry_id: Identifier of the tracker entry.
    :param user_id: Identifier of the owning user.
    :return: Matching tracker entry or ``None``.
    """
    stmt = (
        select(ApplicationTrackerEntry)
        .where(
            ApplicationTrackerEntry.id == entry_id,
            ApplicationTrackerEntry.user_id == user_id
        )
        .options(
            joinedload(ApplicationTrackerEntry.job),
            joinedload(ApplicationTrackerEntry.manual_job_posting),
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def list_tracker_entries_for_user(
    db: Session,
    *,
    user_id: int,
    sort: str = "newest",
    status_filter: str | None = None,
    jobs_with_cover_letters: set[int] | None = None,
) -> list[ApplicationTrackerEntry]:
    """Return tracker entries for one user with optional sort and filter.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param sort: Sort order — ``"newest"`` (default), ``"oldest"``, or ``"name_az"``.
    :param status_filter: Optional filter — individual status value, ``"active"``
        (APPLIED/INTERVIEW/OFFER), or ``"has_cover_letter"``.
    :param jobs_with_cover_letters: Set of job IDs with completed cover letters,
        required when ``status_filter="has_cover_letter"``.
    :return: List of tracker entries with their related jobs loaded.
    """
    active_statuses = [ApplicationStatus.APPLIED, ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER]

    if sort == "name_az":
        stmt = (
            select(ApplicationTrackerEntry)
            .join(ApplicationTrackerEntry.job)
            .where(ApplicationTrackerEntry.user_id == user_id)
            .options(contains_eager(ApplicationTrackerEntry.job))
        )
    else:
        stmt = (
            select(ApplicationTrackerEntry)
            .where(ApplicationTrackerEntry.user_id == user_id)
            .options(joinedload(ApplicationTrackerEntry.job))
        )

    if status_filter == "active":
        stmt = stmt.where(ApplicationTrackerEntry.status.in_(active_statuses))
    elif status_filter == "has_cover_letter":
        job_ids = list(jobs_with_cover_letters or set())
        stmt = stmt.where(ApplicationTrackerEntry.job_id.in_(job_ids))
    elif status_filter and status_filter in {s.value for s in ApplicationStatus}:
        stmt = stmt.where(ApplicationTrackerEntry.status == ApplicationStatus(status_filter))

    if sort == "oldest":
        stmt = stmt.order_by(ApplicationTrackerEntry.created_at.asc(), ApplicationTrackerEntry.id.asc())
    elif sort == "name_az":
        stmt = stmt.order_by(Job.title.asc(), ApplicationTrackerEntry.id.asc())
    else:
        stmt = stmt.order_by(ApplicationTrackerEntry.created_at.desc(), ApplicationTrackerEntry.id.desc())

    return list(db.execute(stmt).unique().scalars().all())


def get_tracker_entry_by_manual_job_posting_id(
    db: Session,
    *,
    user_id: int,
    manual_job_posting_id: int,
) -> ApplicationTrackerEntry | None:
    """Return one tracker entry linked to the given manual job posting.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param manual_job_posting_id: Identifier of the linked manual job posting.
    :return: Matching tracker entry or ``None``.
    """
    stmt = (
        select(ApplicationTrackerEntry)
        .where(
            ApplicationTrackerEntry.user_id == user_id,
            ApplicationTrackerEntry.manual_job_posting_id == manual_job_posting_id,
        )
        .options(joinedload(ApplicationTrackerEntry.job))
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def create_tracker_entry(
    db: Session,
    *,
    user_id: int,
    job_id: int,
    manual_job_posting_id: int | None = None,
) -> ApplicationTrackerEntry:
    """Create and flush a new tracker entry with saved status.

    Flush so the new tracker entry receives its primary key inside the current
    transaction.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param job_id: Identifier of the tracked job.
    :param manual_job_posting_id: Optional FK to the linked manual job posting.
    :return: Newly created tracker entry.
    """
    entry = ApplicationTrackerEntry(
        user_id=user_id,
        job_id=job_id,
        manual_job_posting_id=manual_job_posting_id,
        status=ApplicationStatus.SAVED,
    )
    db.add(entry)
    db.flush()
    return entry


def create_tracker_entry_if_missing(
    db: Session,
    *,
    user_id: int,
    job_id: int,
    manual_job_posting_id: int | None = None,
) -> tuple[ApplicationTrackerEntry, bool]:
    """Create a tracker entry when it does not exist yet.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param job_id: Identifier of the tracked job.
    :param manual_job_posting_id: Optional FK to the linked manual job posting.
    :return: Tuple of ``(tracker_entry, created)``.
    """
    existing_entry = get_tracker_entry_by_job_id_for_user(
        db,
        user_id=user_id,
        job_id=job_id
    )
    if existing_entry is not None:
        return existing_entry, False

    created_entry = create_tracker_entry(
        db,
        user_id=user_id,
        job_id=job_id,
        manual_job_posting_id=manual_job_posting_id,
    )
    return created_entry, True


def update_tracker_entry_notes(
    db: Session,
    *,
    entry: ApplicationTrackerEntry,
    notes: str | None
) -> ApplicationTrackerEntry:
    """Update the notes of one tracker entry.

    :param db: Active database session.
    :param entry: Existing tracker entry to update.
    :param notes: New notes text, possibly empty.
    :return: Updated tracker entry.
    """
    entry.notes = notes

    db.add(entry)
    return entry


def update_tracker_entry_status(
    db: Session,
    *,
    entry: ApplicationTrackerEntry,
    status: ApplicationStatus,
    status_date: date | None
) -> ApplicationTrackerEntry:
    """Update the current status and persist the status-specific date.

    Keep already stored dates for other statuses untouched. ``saved`` always
    uses ``created_at`` in the UI and therefore does not write a separate date.
    For every other status, persist the submitted date when provided and store
    ``None`` when the submitted value is empty.

    :param db: Active database session.
    :param entry: Existing tracker entry to update.
    :param status: New current application status.
    :param status_date: Optional submitted date for the chosen status.
    :return: Updated tracker entry.
    """
    entry.status = status

    if status != ApplicationStatus.SAVED:
        status_date_field = _STATUS_DATE_FIELD_BY_STATUS[status]
        if status_date is None:
            setattr(entry, status_date_field, None)
        else:
            setattr(entry, status_date_field, _combine_date_to_utc_datetime(status_date))

    db.add(entry)
    return entry


def clear_tracker_entry_status_date(
    db: Session,
    *,
    entry: ApplicationTrackerEntry,
    status: ApplicationStatus,
) -> ApplicationTrackerEntry:
    """Set the date field associated with *status* to null.

    Skips ``SAVED`` because its date is ``created_at``, which must not be
    cleared. All other statuses have a dedicated nullable timestamp column.

    :param db: Active database session.
    :param entry: Existing tracker entry to update.
    :param status: The status whose date field should be cleared.
    :return: Updated tracker entry.
    """
    field = _STATUS_DATE_FIELD_BY_STATUS.get(status)
    if field and field != "created_at":
        setattr(entry, field, None)
        db.add(entry)
    return entry


def delete_tracker_entry(
    db: Session,
    *,
    entry: ApplicationTrackerEntry
) -> None:
    """Delete one tracker entry.

    :param db: Active database session.
    :param entry: Existing tracker entry to delete.
    :return: ``None``.
    """
    db.delete(entry)