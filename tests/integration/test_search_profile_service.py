"""Integration tests for the search-profile service."""

from __future__ import annotations

import pytest

from app.crud.search_profile import get_search_profile_by_id
from app.crud.user import create_user
from app.schemas.search_profile import SearchProfileCreate, SearchProfileUpdate
from app.schemas.user import UserCreate
from app.services.search_profile_service import (
    create_search_profile_for_user,
    delete_search_profile_for_user,
    update_search_profile_for_user,
)


def _make_user(db, email: str = "sp_service@example.com"):
    user = create_user(db, UserCreate(email=email, password="Sicher!Passwort99"))
    db.flush()
    return user


def _profile_in(name: str = "My Profile") -> SearchProfileCreate:
    return SearchProfileCreate(profile_name=name, query="Python", location="Berlin")


class TestCreateSearchProfileForUser:
    """Tests for ``create_search_profile_for_user``."""

    def test_creates_profile(self, db):
        user = _make_user(db)
        profile = create_search_profile_for_user(
            db, user_id=user.id, search_profile_in=_profile_in()
        )
        assert profile.id is not None
        assert profile.profile_name == "My Profile"

    def test_committed_after_creation(self, db):
        user = _make_user(db)
        profile = create_search_profile_for_user(
            db, user_id=user.id, search_profile_in=_profile_in()
        )
        found = get_search_profile_by_id(db, profile_id=profile.id, user_id=user.id)
        assert found is not None


class TestUpdateSearchProfileForUser:
    """Tests for ``update_search_profile_for_user``."""

    def test_updates_profile(self, db):
        user = _make_user(db)
        profile = create_search_profile_for_user(db, user_id=user.id, search_profile_in=_profile_in())

        updated = update_search_profile_for_user(
            db,
            profile_id=profile.id,
            user_id=user.id,
            search_profile_in=SearchProfileUpdate(
                profile_name="Updated", query="Go", location="Hamburg"
            ),
        )
        assert updated is not None
        assert updated.query == "Go"

    def test_not_found_returns_none(self, db):
        user = _make_user(db)
        result = update_search_profile_for_user(
            db,
            profile_id=999999,
            user_id=user.id,
            search_profile_in=SearchProfileUpdate(profile_name="X", query="Y", location="Z"),
        )
        assert result is None


class TestDeleteSearchProfileForUser:
    """Tests for ``delete_search_profile_for_user``."""

    def test_returns_true_on_success(self, db):
        user = _make_user(db)
        profile = create_search_profile_for_user(db, user_id=user.id, search_profile_in=_profile_in())

        assert delete_search_profile_for_user(db, profile_id=profile.id, user_id=user.id) is True
        assert get_search_profile_by_id(db, profile_id=profile.id, user_id=user.id) is None

    def test_not_found_returns_false(self, db):
        user = _make_user(db)
        assert delete_search_profile_for_user(db, profile_id=999999, user_id=user.id) is False
