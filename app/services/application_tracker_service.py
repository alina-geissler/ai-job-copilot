"""Service functions for application tracker write use cases.

Coordinate tracker-specific business operations, own the transaction boundary,
and commit or roll back all tracker write use cases.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import ApplicationStatus
from app.crud.application_tracker_entry import (
    clear_tracker_entry_status_date,
    create_tracker_entry,
    create_tracker_entry_if_missing,
    get_tracker_entry_by_id_for_user,
    update_tracker_entry_notes,
    update_tracker_entry_status,
    delete_tracker_entry,
)
from app.crud.job import update_job_title_company
from app.crud.manual_job_posting import create_manual_job_posting
from app.models.application_tracker_entry import ApplicationTrackerEntry
from app.models.job import Job


def create_application_tracker_entry(
    db: Session,
    *,
    user_id: int,
    job_id: int,
    manual_job_posting_id: int | None = None,
) -> tuple[ApplicationTrackerEntry, bool]:
    """Save the given job to the application tracker.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param job_id: Identifier of the tracked job.
    :param manual_job_posting_id: Optional FK to a linked manual job posting.
    :return: Tuple of ``(tracker_entry, created)``.
    :raises IntegrityError: If the write violates database constraints.
    """
    try:
        tracker_entry, created = create_tracker_entry_if_missing(
            db,
            user_id=user_id,
            job_id=job_id,
            manual_job_posting_id=manual_job_posting_id,
        )
        db.commit()
        return tracker_entry, created
    except IntegrityError:
        db.rollback()
        raise


def create_manual_application_tracker_entry(
    db: Session,
    *,
    user_id: int,
    raw_text: str,
    title: str | None = None,
    company: str | None = None,
    job_url: str | None = None,
) -> ApplicationTrackerEntry:
    """Create a ManualJobPosting, a minimal Job record, and a tracker entry.

    Does not trigger normalisation — that is deferred until the user explicitly
    requests it in the tracker or generates a cover letter.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param raw_text: Full pasted job advertisement text.
    :param title: Optional user-supplied job title.
    :param company: Optional user-supplied company name.
    :param job_url: Optional URL to the original job advertisement.
    :return: Newly created ApplicationTrackerEntry.
    """
    posting = create_manual_job_posting(
        db,
        user_id=user_id,
        raw_text=raw_text,
        title=title or None,
        company=company or None,
        job_url=job_url or None,
    )

    display_title = title or "Manuell eingetragene Stelle"
    display_company = company or "Unbekanntes Unternehmen"

    job = Job(
        title=display_title,
        company=display_company,
        description=raw_text,
        source="manual",
        job_url=job_url or None,
    )
    db.add(job)
    db.flush()

    entry = create_tracker_entry(
        db,
        user_id=user_id,
        job_id=job.id,
        manual_job_posting_id=posting.id,
    )

    try:
        db.commit()
        return entry
    except IntegrityError:
        db.rollback()
        raise


def update_job_title_company_for_tracker_entry(
    db: Session,
    *,
    entry_id: int,
    user_id: int,
    title: str | None,
    company: str | None,
    job_url: str | None = None,
) -> ApplicationTrackerEntry | None:
    """Update the job title, company, and URL for a manually added tracker entry.

    Only allowed for jobs with ``source="manual"``.

    :param db: Active database session.
    :param entry_id: Identifier of the tracker entry.
    :param user_id: Identifier of the owning user.
    :param title: New job title, or ``None`` to leave unchanged.
    :param company: New company name, or ``None`` to leave unchanged.
    :param job_url: New job advertisement URL, or ``None`` to leave unchanged.
    :return: Updated tracker entry, or ``None`` when not found / not manual.
    """
    tracker_entry = get_tracker_entry_by_id_for_user(
        db, entry_id=entry_id, user_id=user_id
    )
    if tracker_entry is None or tracker_entry.job.source != "manual":
        return None

    try:
        update_job_title_company(db, job=tracker_entry.job, title=title, company=company, job_url=job_url)
        if tracker_entry.manual_job_posting_id is not None:
            from app.models.manual_job_posting import ManualJobPosting
            posting = db.get(ManualJobPosting, tracker_entry.manual_job_posting_id)
            if posting is not None:
                if title:
                    posting.title = title
                if company:
                    posting.company = company
                if job_url:
                    posting.job_url = job_url
                db.add(posting)
        db.commit()
        return tracker_entry
    except Exception:
        db.rollback()
        raise


def change_application_tracker_status(
    db: Session,
    *,
    entry_id: int,
    user_id: int,
    status: ApplicationStatus,
    status_date: date | None
) -> ApplicationTrackerEntry | None:
    """Change the status of one tracker entry owned by the given user.

    :param db: Active database session.
    :param entry_id: Identifier of the tracker entry to update.
    :param user_id: Identifier of the owning user.
    :param status: New tracker status.
    :param status_date: Optional date for the selected status.
    :return: Updated tracker entry or ``None`` when it does not exist.
    """
    tracker_entry = get_tracker_entry_by_id_for_user(
        db,
        entry_id=entry_id,
        user_id=user_id
    )
    if tracker_entry is None:
        return None

    try:
        update_tracker_entry_status(
            db,
            entry=tracker_entry,
            status=status,
            status_date=status_date
        )
        db.commit()
        return tracker_entry
    except Exception:
        db.rollback()
        raise


def change_application_tracker_notes(
    db: Session,
    *,
    entry_id: int,
    user_id: int,
    notes: str | None
) -> ApplicationTrackerEntry | None:
    """Change the notes of one tracker entry owned by the given user.

    :param db: Active database session.
    :param entry_id: Identifier of the tracker entry to update.
    :param user_id: Identifier of the owning user.
    :param notes: New notes text.
    :return: Updated tracker entry or ``None`` when it does not exist.
    """
    tracker_entry = get_tracker_entry_by_id_for_user(
        db,
        entry_id=entry_id,
        user_id=user_id
    )
    if tracker_entry is None:
        return None

    try:
        update_tracker_entry_notes(
            db,
            entry=tracker_entry,
            notes=notes
        )
        db.commit()
        return tracker_entry
    except Exception:
        db.rollback()
        raise


def clear_application_tracker_status_date(
    db: Session,
    *,
    entry_id: int,
    user_id: int,
    status: ApplicationStatus,
) -> ApplicationTrackerEntry | None:
    """Clear the date field for the given status on one tracker entry.

    Does not change the entry's current status value, only nulls the
    corresponding timestamp column.

    :param db: Active database session.
    :param entry_id: Identifier of the tracker entry to update.
    :param user_id: Identifier of the owning user.
    :param status: The status whose date field should be cleared.
    :return: Updated tracker entry or ``None`` when it does not exist.
    """
    tracker_entry = get_tracker_entry_by_id_for_user(
        db,
        entry_id=entry_id,
        user_id=user_id,
    )
    if tracker_entry is None:
        return None

    try:
        clear_tracker_entry_status_date(db, entry=tracker_entry, status=status)
        db.commit()
        return tracker_entry
    except Exception:
        db.rollback()
        raise


def remove_application_tracker_entry(
    db: Session,
    *,
    entry_id: int,
    user_id: int
) -> bool:
    """Delete one tracker entry owned by the given user.

    :param db: Active database session.
    :param entry_id: Identifier of the tracker entry to delete.
    :param user_id: Identifier of the owning user.
    :return: ``True`` when the entry was deleted, otherwise ``False``.
    """
    tracker_entry = get_tracker_entry_by_id_for_user(
        db,
        entry_id=entry_id,
        user_id=user_id
    )
    if tracker_entry is None:
        return False

    try:
        delete_tracker_entry(
            db,
            entry=tracker_entry
        )
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise