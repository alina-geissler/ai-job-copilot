"""Integration tests for the application tracker service."""

from __future__ import annotations

from datetime import date

import pytest

from app.core.enums import ApplicationStatus
from app.crud.application_tracker_entry import get_tracker_entry_by_id_for_user
from app.crud.user import create_user
from app.models.job import Job
from app.schemas.user import UserCreate
from app.services.application_tracker_service import (
    change_application_tracker_notes,
    change_application_tracker_status,
    clear_application_tracker_status_date,
    create_application_tracker_entry,
    remove_application_tracker_entry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db, email: str = "tracker_svc@example.com"):
    user = create_user(db, UserCreate(email=email, password="Sicher!Passwort99"))
    db.flush()
    return user


def _make_job(db, external_id: str = "svc-001"):
    job = Job(title="Engineer", company="Acme", external_job_id=external_id, source="test")
    db.add(job)
    db.flush()
    return job


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateApplicationTrackerEntry:
    """Tests for ``create_application_tracker_entry``."""

    def test_creates_entry_with_saved_status(self, db):
        user = _make_user(db)
        job = _make_job(db)

        entry, created = create_application_tracker_entry(db, user_id=user.id, job_id=job.id)

        assert created is True
        assert entry.status == ApplicationStatus.SAVED

    def test_idempotent_returns_false_on_second_call(self, db):
        user = _make_user(db)
        job = _make_job(db)

        create_application_tracker_entry(db, user_id=user.id, job_id=job.id)
        _, created = create_application_tracker_entry(db, user_id=user.id, job_id=job.id)

        assert created is False


class TestChangeApplicationTrackerStatus:
    """Tests for ``change_application_tracker_status``."""

    def test_changes_status(self, db):
        user = _make_user(db)
        job = _make_job(db)
        entry, _ = create_application_tracker_entry(db, user_id=user.id, job_id=job.id)

        updated = change_application_tracker_status(
            db,
            entry_id=entry.id,
            user_id=user.id,
            status=ApplicationStatus.APPLIED,
            status_date=date(2025, 5, 1),
        )

        assert updated is not None
        assert updated.status == ApplicationStatus.APPLIED
        assert updated.applied_at is not None

    def test_entry_not_found_returns_none(self, db):
        user = _make_user(db)

        result = change_application_tracker_status(
            db,
            entry_id=999999,
            user_id=user.id,
            status=ApplicationStatus.APPLIED,
            status_date=None,
        )

        assert result is None


class TestChangeApplicationTrackerNotes:
    """Tests for ``change_application_tracker_notes``."""

    def test_updates_notes(self, db):
        user = _make_user(db)
        job = _make_job(db)
        entry, _ = create_application_tracker_entry(db, user_id=user.id, job_id=job.id)

        updated = change_application_tracker_notes(
            db, entry_id=entry.id, user_id=user.id, notes="Very interesting role."
        )

        assert updated is not None
        assert updated.notes == "Very interesting role."

    def test_entry_not_found_returns_none(self, db):
        user = _make_user(db)

        result = change_application_tracker_notes(
            db, entry_id=999999, user_id=user.id, notes="X"
        )

        assert result is None


class TestClearApplicationTrackerStatusDate:
    """Tests for ``clear_application_tracker_status_date``."""

    def test_clears_applied_at(self, db):
        user = _make_user(db)
        job = _make_job(db)
        entry, _ = create_application_tracker_entry(db, user_id=user.id, job_id=job.id)
        change_application_tracker_status(
            db,
            entry_id=entry.id,
            user_id=user.id,
            status=ApplicationStatus.APPLIED,
            status_date=date(2025, 5, 1),
        )

        updated = clear_application_tracker_status_date(
            db, entry_id=entry.id, user_id=user.id, status=ApplicationStatus.APPLIED
        )

        assert updated is not None
        assert updated.applied_at is None


class TestRemoveApplicationTrackerEntry:
    """Tests for ``remove_application_tracker_entry``."""

    def test_removes_entry_returns_true(self, db):
        user = _make_user(db)
        job = _make_job(db)
        entry, _ = create_application_tracker_entry(db, user_id=user.id, job_id=job.id)
        entry_id = entry.id

        result = remove_application_tracker_entry(db, entry_id=entry_id, user_id=user.id)

        assert result is True
        assert get_tracker_entry_by_id_for_user(db, entry_id=entry_id, user_id=user.id) is None

    def test_not_found_returns_false(self, db):
        user = _make_user(db)
        assert remove_application_tracker_entry(db, entry_id=999999, user_id=user.id) is False
