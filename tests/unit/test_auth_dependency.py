"""Unit tests for the get_current_user authentication dependency."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from app.dependencies.auth import (
    AuthFailureReason,
    AuthenticationRequiredError,
    get_current_user,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(session: dict) -> MagicMock:
    """Build a mock Request whose ``.session`` attribute is a real dict."""
    request = MagicMock()
    request.session = session
    return request


def _valid_session(user_id: int = 1) -> dict:
    """Return a minimal valid session dict."""
    now = int(time.time())
    return {
        "user_id": user_id,
        "is_authenticated": True,
        "created_at": now,
        "last_seen": now,
    }


def _make_user(user_id: int = 1) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetCurrentUser:
    """Tests for ``get_current_user``."""

    def test_returns_user_when_session_valid(self):
        """A fully valid session returns the user from the DB."""
        user = _make_user()
        request = _make_request(_valid_session())
        db = MagicMock()

        with patch("app.dependencies.auth.get_user_by_id", return_value=user):
            result = get_current_user(request, db)

        assert result is user

    def test_raises_login_required_when_no_user_id(self):
        """Missing user_id in session raises LOGIN_REQUIRED."""
        session = _valid_session()
        del session["user_id"]
        request = _make_request(session)
        db = MagicMock()

        with pytest.raises(AuthenticationRequiredError) as exc_info:
            get_current_user(request, db)

        assert exc_info.value.reason == AuthFailureReason.LOGIN_REQUIRED

    def test_raises_login_required_when_not_authenticated(self):
        """is_authenticated=False raises LOGIN_REQUIRED."""
        session = _valid_session()
        session["is_authenticated"] = False
        request = _make_request(session)
        db = MagicMock()

        with pytest.raises(AuthenticationRequiredError) as exc_info:
            get_current_user(request, db)

        assert exc_info.value.reason == AuthFailureReason.LOGIN_REQUIRED

    def test_raises_login_required_when_session_timestamps_missing(self):
        """Missing created_at or last_seen raises LOGIN_REQUIRED and clears session."""
        session = _valid_session()
        del session["created_at"]
        request = _make_request(session)
        db = MagicMock()

        with pytest.raises(AuthenticationRequiredError) as exc_info:
            get_current_user(request, db)

        assert exc_info.value.reason == AuthFailureReason.LOGIN_REQUIRED

    def test_raises_session_expired_when_idle_timeout_exceeded(self):
        """A last_seen far in the past raises SESSION_EXPIRED."""
        session = _valid_session()
        session["last_seen"] = int(time.time()) - 99999  # well past idle limit
        request = _make_request(session)
        db = MagicMock()

        with pytest.raises(AuthenticationRequiredError) as exc_info:
            get_current_user(request, db)

        assert exc_info.value.reason == AuthFailureReason.SESSION_EXPIRED

    def test_raises_session_expired_when_absolute_timeout_exceeded(self):
        """A created_at far in the past raises SESSION_EXPIRED."""
        session = _valid_session()
        session["created_at"] = int(time.time()) - 999999  # well past absolute limit
        request = _make_request(session)
        db = MagicMock()

        with pytest.raises(AuthenticationRequiredError) as exc_info:
            get_current_user(request, db)

        assert exc_info.value.reason == AuthFailureReason.SESSION_EXPIRED

    def test_raises_user_not_found_when_db_returns_none(self):
        """USER_NOT_FOUND is raised and session is cleared when the DB has no user."""
        request = _make_request(_valid_session())
        db = MagicMock()

        with patch("app.dependencies.auth.get_user_by_id", return_value=None):
            with pytest.raises(AuthenticationRequiredError) as exc_info:
                get_current_user(request, db)

        assert exc_info.value.reason == AuthFailureReason.USER_NOT_FOUND
        # Session must have been cleared
        assert request.session == {}

    def test_updates_last_seen_on_valid_request(self):
        """last_seen in the session is refreshed after a valid authentication."""
        user = _make_user()
        now = int(time.time())
        session = _valid_session()
        old_last_seen = now - 60
        session["last_seen"] = old_last_seen
        request = _make_request(session)
        db = MagicMock()

        with patch("app.dependencies.auth.get_user_by_id", return_value=user):
            get_current_user(request, db)

        assert request.session["last_seen"] >= now
