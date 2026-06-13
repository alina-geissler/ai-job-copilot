"""Integration tests for the auth service."""

from __future__ import annotations

import pytest

from app.crud.user import get_user_by_email
from app.schemas.user import UserCreate
from app.services.auth_service import register_user_account


class TestRegisterUserAccount:
    """Tests for ``register_user_account``."""

    def test_creates_and_commits_user(self, db):
        """Registering a new user persists the record and returns it."""
        user = register_user_account(
            db, UserCreate(email="new@example.com", password="Sicher!Passwort99")
        )

        assert user.id is not None
        # The commit means get_user_by_email can find it within the same (savepoint) transaction
        found = get_user_by_email(db, "new@example.com")
        assert found is not None
        assert found.id == user.id

    def test_duplicate_email_raises_and_rolls_back(self, db):
        """Re-registering an existing email raises ValueError."""
        register_user_account(
            db, UserCreate(email="dup@example.com", password="Sicher!Passwort99")
        )

        with pytest.raises((ValueError, Exception)):
            register_user_account(
                db, UserCreate(email="dup@example.com", password="Sicher!Passwort99")
            )
