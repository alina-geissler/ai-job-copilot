"""E2E tests for authentication routes."""

from __future__ import annotations

from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


# ---------------------------------------------------------------------------
# GET /auth
# ---------------------------------------------------------------------------

def test_render_auth_page_returns_200(client):
    """GET /auth renders the auth page without a session."""
    response = client.get("/auth")
    assert response.status_code == 200
    assert b"<html" in response.content.lower()


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------

def test_register_success_redirects_to_auth(client):
    """Successful registration redirects to /auth with a success message."""
    response = client.post(
        "/auth/register",
        data={"email": "newuser@example.com", "password": "Sicher!Passwort99"},
    )
    assert response.status_code == 303
    assert "/auth" in response.headers["location"]


def test_register_duplicate_email_returns_422(client, test_user):
    """Registering with an already-used email renders the form with status 422."""
    response = client.post(
        "/auth/register",
        data={"email": TEST_USER_EMAIL, "password": "Sicher!Passwort99"},
    )
    assert response.status_code == 422


def test_register_password_too_short_returns_422(client):
    """A password shorter than 10 characters returns 422 with the form."""
    response = client.post(
        "/auth/register",
        data={"email": "x@example.com", "password": "Short1!"},
    )
    assert response.status_code == 422


def test_register_common_password_returns_422(client):
    """A password on the common-password blocklist returns 422."""
    response = client.post(
        "/auth/register",
        data={"email": "x@example.com", "password": "password123"},
    )
    assert response.status_code == 422


def test_register_email_part_in_password_returns_422(client):
    """A password that contains the email local part returns 422."""
    response = client.post(
        "/auth/register",
        data={"email": "alice@example.com", "password": "alice_secure99!"},
    )
    assert response.status_code == 422


def test_register_invalid_email_returns_422(client):
    """An invalid email address returns 422."""
    response = client.post(
        "/auth/register",
        data={"email": "not-an-email", "password": "Sicher!Passwort99"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

def test_login_success_redirects_to_dashboard(client, test_user):
    """Correct credentials redirect to /dashboard."""
    response = client.post(
        "/auth/login",
        data={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
    )
    assert response.status_code == 303
    assert "/dashboard" in response.headers["location"]


def test_login_wrong_password_returns_422(client, test_user):
    """Wrong password returns 422 with the form."""
    response = client.post(
        "/auth/login",
        data={"email": TEST_USER_EMAIL, "password": "WrongPassword!"},
    )
    assert response.status_code == 422


def test_login_unknown_email_returns_422(client):
    """Login with an email that does not exist returns 422."""
    response = client.post(
        "/auth/login",
        data={"email": "nobody@example.com", "password": "Sicher!Passwort99"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

def test_logout_redirects_to_index(authenticated_client):
    """Logging out redirects to the index page."""
    response = authenticated_client.post("/auth/logout")
    assert response.status_code == 303
    location = response.headers["location"]
    assert "/" in location


# ---------------------------------------------------------------------------
# Auth guard: unauthenticated access to protected routes
# ---------------------------------------------------------------------------

def test_dashboard_unauthenticated_redirects_to_auth(client):
    """GET /dashboard without a session must redirect to /auth."""
    response = client.get("/dashboard")
    assert response.status_code == 303
    assert "/auth" in response.headers["location"]


def test_tracker_unauthenticated_redirects_to_auth(client):
    """GET /tracker without a session must redirect to /auth."""
    response = client.get("/tracker")
    assert response.status_code == 303
    assert "/auth" in response.headers["location"]


def test_search_profiles_unauthenticated_redirects_to_auth(client):
    """GET /search-profiles/new without a session must redirect to /auth."""
    response = client.get("/search-profiles/new")
    assert response.status_code == 303
    assert "/auth" in response.headers["location"]
