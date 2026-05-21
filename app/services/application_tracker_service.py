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
    create_tracker_entry_if_missing,
    get_tracker_entry_by_id_for_user,
    update_tracker_entry_notes,
    update_tracker_entry_status,
    delete_tracker_entry
)
from app.models.application_tracker_entry import ApplicationTrackerEntry


def create_application_tracker_entry(
    db: Session,
    *,
    user_id: int,
    job_id: int
) -> tuple[ApplicationTrackerEntry, bool]:
    """Save the given job to the application tracker.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param job_id: Identifier of the tracked job.
    :return: Tuple of ``(tracker_entry, created)``.
    :raises IntegrityError: If the write violates database constraints.
    """
    try:
        tracker_entry, created = create_tracker_entry_if_missing(
            db,
            user_id=user_id,
            job_id=job_id
        )
        db.commit()
        return tracker_entry, created
    except IntegrityError:
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