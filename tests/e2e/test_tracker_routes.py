"""E2E tests for application tracker routes."""

from __future__ import annotations

from app.models.job import Job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_tracker_entry(authenticated_client, db) -> tuple[int, int]:
    """Create a job in the DB and a tracker entry via the route.

    :returns: Tuple of ``(entry_id, job_id)``.
    """
    job = Job(title="Engineer", company="Acme GmbH", external_job_id="e2e-001", source="test")
    db.add(job)
    db.flush()
    db.commit()

    response = authenticated_client.post(f"/tracker/jobs/{job.id}")
    assert response.status_code == 303, response.text[:200]

    # Retrieve the entry ID from the tracker list
    list_response = authenticated_client.get("/tracker")
    assert list_response.status_code == 200

    from app.crud.application_tracker_entry import list_tracker_entries_for_user
    from app.crud.user import get_user_by_email
    from tests.conftest import TEST_USER_EMAIL

    user = get_user_by_email(db, TEST_USER_EMAIL)
    entries = list_tracker_entries_for_user(db, user_id=user.id)
    entry = next((e for e in entries if e.job_id == job.id), None)
    assert entry is not None
    return entry.id, job.id


# ---------------------------------------------------------------------------
# GET /tracker
# ---------------------------------------------------------------------------

def test_render_tracker_page_ok(authenticated_client):
    """GET /tracker returns 200 for an authenticated user."""
    response = authenticated_client.get("/tracker")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /tracker/jobs/{job_id}
# ---------------------------------------------------------------------------

def test_create_tracker_entry_redirects(authenticated_client, db):
    """Creating a tracker entry redirects with 303."""
    job = Job(title="Dev", company="Test GmbH", external_job_id="e2e-002", source="test")
    db.add(job)
    db.flush()
    db.commit()

    response = authenticated_client.post(f"/tracker/jobs/{job.id}")
    assert response.status_code == 303


def test_create_tracker_entry_idempotent(authenticated_client, db):
    """Creating the same tracker entry twice redirects both times (no duplicate)."""
    job = Job(title="Dev", company="Test GmbH", external_job_id="e2e-003", source="test")
    db.add(job)
    db.flush()
    db.commit()

    r1 = authenticated_client.post(f"/tracker/jobs/{job.id}")
    r2 = authenticated_client.post(f"/tracker/jobs/{job.id}")
    assert r1.status_code == 303
    assert r2.status_code == 303


# ---------------------------------------------------------------------------
# POST /tracker/{entry_id}/status
# ---------------------------------------------------------------------------

def test_update_tracker_status_redirects(authenticated_client, db):
    """Updating a tracker status redirects with 303."""
    entry_id, _ = _seed_tracker_entry(authenticated_client, db)

    response = authenticated_client.post(
        f"/tracker/{entry_id}/status",
        data={
            "status": "applied",
            "status_date": "2025-06-01",
            "redirect_to": "overview",
        },
    )
    assert response.status_code == 303


# ---------------------------------------------------------------------------
# POST /tracker/{entry_id}/notes
# ---------------------------------------------------------------------------

def test_update_tracker_notes_redirects(authenticated_client, db):
    """Updating notes on a tracker entry redirects with 303."""
    entry_id, _ = _seed_tracker_entry(authenticated_client, db)

    response = authenticated_client.post(
        f"/tracker/{entry_id}/notes",
        data={"notes": "Interesting role", "redirect_to": "overview"},
    )
    assert response.status_code == 303


# ---------------------------------------------------------------------------
# POST /tracker/{entry_id}/status/clear-date
# ---------------------------------------------------------------------------

def test_clear_tracker_status_date_redirects(authenticated_client, db):
    """Clearing a status date redirects with 303."""
    entry_id, _ = _seed_tracker_entry(authenticated_client, db)

    # Set the status first
    authenticated_client.post(
        f"/tracker/{entry_id}/status",
        data={"status": "applied", "status_date": "2025-06-01", "redirect_to": "overview"},
    )

    response = authenticated_client.post(
        f"/tracker/{entry_id}/status/clear-date",
        data={"status": "applied", "redirect_to": "overview"},
    )
    assert response.status_code == 303


# ---------------------------------------------------------------------------
# GET /tracker/{entry_id}
# ---------------------------------------------------------------------------

def test_render_tracker_detail_page_ok(authenticated_client, db):
    """GET /tracker/{entry_id} returns 200 for an authenticated user."""
    entry_id, _ = _seed_tracker_entry(authenticated_client, db)
    response = authenticated_client.get(f"/tracker/{entry_id}")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /tracker/{entry_id}/delete
# ---------------------------------------------------------------------------

def test_delete_tracker_entry_redirects(authenticated_client, db):
    """Deleting a tracker entry redirects with 303."""
    entry_id, _ = _seed_tracker_entry(authenticated_client, db)
    response = authenticated_client.post(f"/tracker/{entry_id}/delete")
    assert response.status_code == 303


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def test_tracker_list_unauthenticated_redirects(client):
    """GET /tracker without session redirects to /auth."""
    response = client.get("/tracker")
    assert response.status_code == 303
    assert "/auth" in response.headers["location"]


def test_tracker_create_unauthenticated_redirects(client):
    """POST /tracker/jobs/1 without session redirects to /auth."""
    response = client.post("/tracker/jobs/1")
    assert response.status_code == 303
    assert "/auth" in response.headers["location"]
