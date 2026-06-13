"""Integration tests for application tracker entry CRUD operations."""

from __future__ import annotations

from datetime import date, timezone

import pytest

from app.core.enums import ApplicationStatus
from app.crud.application_tracker_entry import (
    clear_tracker_entry_status_date,
    create_tracker_entry,
    create_tracker_entry_if_missing,
    delete_tracker_entry,
    get_tracker_entry_by_id_for_user,
    get_tracker_entry_by_job_id_for_user,
    list_tracker_entries_for_user,
    update_tracker_entry_notes,
    update_tracker_entry_status,
)
from app.crud.user import create_user
from app.models.job import Job
from app.schemas.user import UserCreate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db, email: str = "tracker@example.com"):
    user = create_user(db, UserCreate(email=email, password="Sicher!Passwort99"))
    db.flush()
    return user


def _make_job(db, external_id: str = "ext-001"):
    job = Job(title="Engineer", company="Acme", external_job_id=external_id, source="test")
    db.add(job)
    db.flush()
    return job


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateTrackerEntry:
    """Tests for ``create_tracker_entry`` and ``create_tracker_entry_if_missing``."""

    def test_default_status_is_saved(self, db):
        user = _make_user(db)
        job = _make_job(db)

        entry = create_tracker_entry(db, user_id=user.id, job_id=job.id)
        db.flush()

        assert entry.id is not None
        assert entry.status == ApplicationStatus.SAVED
        assert entry.user_id == user.id
        assert entry.job_id == job.id

    def test_if_missing_creates_entry(self, db):
        user = _make_user(db)
        job = _make_job(db)

        entry, created = create_tracker_entry_if_missing(db, user_id=user.id, job_id=job.id)
        db.flush()

        assert created is True
        assert entry.id is not None

    def test_if_missing_returns_existing_with_false(self, db):
        user = _make_user(db)
        job = _make_job(db)

        first, _ = create_tracker_entry_if_missing(db, user_id=user.id, job_id=job.id)
        db.flush()
        second, created = create_tracker_entry_if_missing(db, user_id=user.id, job_id=job.id)

        assert created is False
        assert first.id == second.id


class TestListAndGetTrackerEntries:
    """Tests for ``list_tracker_entries_for_user`` and lookup functions."""

    def test_empty_list_for_new_user(self, db):
        user = _make_user(db)
        assert list_tracker_entries_for_user(db, user_id=user.id) == []

    def test_list_returns_own_entries_only(self, db):
        user1 = _make_user(db, "u1@example.com")
        user2 = _make_user(db, "u2@example.com")
        job = _make_job(db)
        create_tracker_entry(db, user_id=user1.id, job_id=job.id)
        db.flush()

        assert list_tracker_entries_for_user(db, user_id=user2.id) == []

    def test_list_ordered_newest_first(self, db):
        user = _make_user(db)
        job1 = _make_job(db, "ext-1")
        job2 = _make_job(db, "ext-2")
        e1 = create_tracker_entry(db, user_id=user.id, job_id=job1.id)
        db.flush()
        e2 = create_tracker_entry(db, user_id=user.id, job_id=job2.id)
        db.flush()

        entries = list_tracker_entries_for_user(db, user_id=user.id)
        assert entries[0].id == e2.id

    def test_get_by_id_returns_entry(self, db):
        user = _make_user(db)
        job = _make_job(db)
        entry = create_tracker_entry(db, user_id=user.id, job_id=job.id)
        db.flush()

        found = get_tracker_entry_by_id_for_user(db, entry_id=entry.id, user_id=user.id)
        assert found is not None
        assert found.id == entry.id

    def test_get_by_id_wrong_user_returns_none(self, db):
        user1 = _make_user(db, "owner@example.com")
        user2 = _make_user(db, "other@example.com")
        job = _make_job(db)
        entry = create_tracker_entry(db, user_id=user1.id, job_id=job.id)
        db.flush()

        assert get_tracker_entry_by_id_for_user(db, entry_id=entry.id, user_id=user2.id) is None

    def test_get_by_job_id_returns_entry(self, db):
        user = _make_user(db)
        job = _make_job(db)
        entry = create_tracker_entry(db, user_id=user.id, job_id=job.id)
        db.flush()

        found = get_tracker_entry_by_job_id_for_user(db, user_id=user.id, job_id=job.id)
        assert found is not None
        assert found.id == entry.id


class TestUpdateTrackerEntryStatus:
    """Tests for ``update_tracker_entry_status``."""

    def test_applied_stores_applied_at(self, db):
        user = _make_user(db)
        job = _make_job(db)
        entry = create_tracker_entry(db, user_id=user.id, job_id=job.id)
        db.flush()

        update_tracker_entry_status(
            db,
            entry=entry,
            status=ApplicationStatus.APPLIED,
            status_date=date(2025, 5, 1),
        )
        assert entry.status == ApplicationStatus.APPLIED
        assert entry.applied_at is not None
        assert entry.applied_at.date() == date(2025, 5, 1)

    def test_saved_status_does_not_write_date(self, db):
        user = _make_user(db)
        job = _make_job(db)
        entry = create_tracker_entry(db, user_id=user.id, job_id=job.id)
        db.flush()
        entry.applied_at = None

        update_tracker_entry_status(
            db,
            entry=entry,
            status=ApplicationStatus.SAVED,
            status_date=date(2025, 5, 1),
        )
        # SAVED must not write applied_at
        assert entry.applied_at is None

    def test_null_date_clears_field(self, db):
        user = _make_user(db)
        job = _make_job(db)
        entry = create_tracker_entry(db, user_id=user.id, job_id=job.id)
        db.flush()

        update_tracker_entry_status(
            db, entry=entry, status=ApplicationStatus.INTERVIEW, status_date=date(2025, 5, 10)
        )
        update_tracker_entry_status(
            db, entry=entry, status=ApplicationStatus.INTERVIEW, status_date=None
        )

        assert entry.interview_at is None


class TestUpdateTrackerEntryNotes:
    """Tests for ``update_tracker_entry_notes``."""

    def test_sets_notes(self, db):
        user = _make_user(db)
        job = _make_job(db)
        entry = create_tracker_entry(db, user_id=user.id, job_id=job.id)
        db.flush()

        update_tracker_entry_notes(db, entry=entry, notes="Great company!")
        assert entry.notes == "Great company!"

    def test_clears_notes_with_none(self, db):
        user = _make_user(db)
        job = _make_job(db)
        entry = create_tracker_entry(db, user_id=user.id, job_id=job.id)
        db.flush()
        update_tracker_entry_notes(db, entry=entry, notes="Old note")
        update_tracker_entry_notes(db, entry=entry, notes=None)
        assert entry.notes is None


class TestClearTrackerEntryStatusDate:
    """Tests for ``clear_tracker_entry_status_date``."""

    def test_clears_applied_at(self, db):
        user = _make_user(db)
        job = _make_job(db)
        entry = create_tracker_entry(db, user_id=user.id, job_id=job.id)
        db.flush()
        update_tracker_entry_status(
            db, entry=entry, status=ApplicationStatus.APPLIED, status_date=date(2025, 5, 1)
        )
        assert entry.applied_at is not None

        clear_tracker_entry_status_date(db, entry=entry, status=ApplicationStatus.APPLIED)
        assert entry.applied_at is None

    def test_skips_saved_status(self, db):
        """SAVED has no dedicated date column — clear should be a no-op."""
        user = _make_user(db)
        job = _make_job(db)
        entry = create_tracker_entry(db, user_id=user.id, job_id=job.id)
        db.flush()

        original_created_at = entry.created_at
        clear_tracker_entry_status_date(db, entry=entry, status=ApplicationStatus.SAVED)
        assert entry.created_at == original_created_at


class TestDeleteTrackerEntry:
    """Tests for ``delete_tracker_entry``."""

    def test_deletes_entry(self, db):
        user = _make_user(db)
        job = _make_job(db)
        entry = create_tracker_entry(db, user_id=user.id, job_id=job.id)
        db.flush()
        entry_id = entry.id

        delete_tracker_entry(db, entry=entry)
        db.flush()

        assert (
            get_tracker_entry_by_id_for_user(db, entry_id=entry_id, user_id=user.id) is None
        )
