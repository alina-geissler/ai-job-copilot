"""Integration tests for user CRUD operations."""

from __future__ import annotations

import pytest

from app.crud.user import create_user, get_user_by_email, get_user_by_id
from app.schemas.user import UserCreate


def _user_in(email: str = "crud@example.com") -> UserCreate:
    return UserCreate(email=email, password="Sicher!Passwort99")


class TestCreateUser:
    """Tests for ``create_user``."""

    def test_create_user_stores_hashed_password(self, db):
        """Creating a user stores a bcrypt hash, not the plaintext password."""
        user = create_user(db, _user_in())
        assert user.id is not None
        assert user.password_hash.startswith("$2b$")
        assert user.password_hash != "Sicher!Passwort99"

    def test_create_user_sets_defaults(self, db):
        """Newly created user is active with role 'user'."""
        user = create_user(db, _user_in())
        assert user.is_active is True
        assert user.role == "user"

    def test_create_user_duplicate_email_raises_value_error(self, db):
        """Creating two users with the same email raises ValueError."""
        create_user(db, _user_in())
        db.flush()

        with pytest.raises(ValueError, match="already registered"):
            create_user(db, _user_in())


class TestGetUserByEmail:
    """Tests for ``get_user_by_email``."""

    def test_returns_existing_user(self, db):
        user = create_user(db, _user_in())
        db.flush()

        found = get_user_by_email(db, "crud@example.com")
        assert found is not None
        assert found.id == user.id

    def test_returns_none_for_unknown_email(self, db):
        assert get_user_by_email(db, "nobody@example.com") is None

    def test_lookup_is_case_sensitive(self, db):
        """Email lookup is case-sensitive in PostgreSQL."""
        create_user(db, _user_in("Case@Example.com"))
        db.flush()

        assert get_user_by_email(db, "case@example.com") is None


class TestGetUserById:
    """Tests for ``get_user_by_id``."""

    def test_returns_existing_user(self, db):
        user = create_user(db, _user_in())
        db.flush()

        found = get_user_by_id(db, user.id)
        assert found is not None
        assert found.email == "crud@example.com"

    def test_returns_none_for_unknown_id(self, db):
        assert get_user_by_id(db, 999999) is None
