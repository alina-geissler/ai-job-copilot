"""Integration tests for search-profile CRUD operations."""

from __future__ import annotations

import pytest

from app.crud.search_profile import (
    create_search_profile,
    delete_search_profile,
    get_next_default_search_profile_name,
    get_search_profile_by_id,
    get_search_profiles_for_user,
    update_search_profile,
)
from app.crud.user import create_user
from app.schemas.search_profile import SearchProfileCreate, SearchProfileUpdate
from app.schemas.user import UserCreate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db, email: str = "profile@example.com"):
    user = create_user(db, UserCreate(email=email, password="Sicher!Passwort99"))
    db.flush()
    return user


def _profile_in(name: str = "Mein Profil") -> SearchProfileCreate:
    return SearchProfileCreate(
        profile_name=name,
        query="Python",
        location="Berlin",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateSearchProfile:
    """Tests for ``create_search_profile``."""

    def test_create_with_explicit_name(self, db):
        user = _make_user(db)
        profile = create_search_profile(db, user_id=user.id, search_profile_in=_profile_in())
        db.flush()

        assert profile.id is not None
        assert profile.profile_name == "Mein Profil"
        assert profile.user_id == user.id

    def test_create_auto_names_suchprofil_1(self, db):
        user = _make_user(db)
        profile = create_search_profile(
            db,
            user_id=user.id,
            search_profile_in=SearchProfileCreate(query="Python", location="Berlin"),
        )
        db.flush()

        assert profile.profile_name == "Suchprofil 1"

    def test_create_auto_name_increments(self, db):
        user = _make_user(db)
        create_search_profile(
            db, user_id=user.id, search_profile_in=SearchProfileCreate(query="A", location="B")
        )
        db.flush()
        second = create_search_profile(
            db, user_id=user.id, search_profile_in=SearchProfileCreate(query="C", location="D")
        )
        db.flush()

        assert second.profile_name == "Suchprofil 2"


class TestGetSearchProfiles:
    """Tests for ``get_search_profiles_for_user`` and ``get_search_profile_by_id``."""

    def test_empty_list_for_new_user(self, db):
        user = _make_user(db)
        assert get_search_profiles_for_user(db, user.id) == []

    def test_returns_only_own_profiles(self, db):
        user1 = _make_user(db, "u1@example.com")
        user2 = _make_user(db, "u2@example.com")
        create_search_profile(db, user_id=user1.id, search_profile_in=_profile_in())
        db.flush()

        assert get_search_profiles_for_user(db, user2.id) == []

    def test_get_by_id_returns_profile(self, db):
        user = _make_user(db)
        profile = create_search_profile(db, user_id=user.id, search_profile_in=_profile_in())
        db.flush()

        found = get_search_profile_by_id(db, profile_id=profile.id, user_id=user.id)
        assert found is not None
        assert found.id == profile.id

    def test_get_by_id_wrong_user_returns_none(self, db):
        user1 = _make_user(db, "owner@example.com")
        user2 = _make_user(db, "other@example.com")
        profile = create_search_profile(db, user_id=user1.id, search_profile_in=_profile_in())
        db.flush()

        assert get_search_profile_by_id(db, profile_id=profile.id, user_id=user2.id) is None

    def test_get_next_default_name_is_suchprofil_1_for_empty_user(self, db):
        user = _make_user(db)
        assert get_next_default_search_profile_name(db, user.id) == "Suchprofil 1"

    def test_get_next_default_name_skips_existing(self, db):
        user = _make_user(db)
        create_search_profile(
            db,
            user_id=user.id,
            search_profile_in=SearchProfileCreate(query="X", location="Y"),
        )
        db.flush()
        assert get_next_default_search_profile_name(db, user.id) == "Suchprofil 2"


class TestUpdateSearchProfile:
    """Tests for ``update_search_profile``."""

    def test_update_profile(self, db):
        user = _make_user(db)
        profile = create_search_profile(db, user_id=user.id, search_profile_in=_profile_in())
        db.flush()

        updated = update_search_profile(
            db,
            profile_id=profile.id,
            user_id=user.id,
            search_profile_in=SearchProfileUpdate(
                profile_name="Updated Name",
                query="Rust",
                location="München",
            ),
        )
        assert updated is not None
        assert updated.profile_name == "Updated Name"
        assert updated.query == "Rust"

    def test_update_wrong_user_returns_none(self, db):
        user1 = _make_user(db, "owner@example.com")
        user2 = _make_user(db, "intruder@example.com")
        profile = create_search_profile(db, user_id=user1.id, search_profile_in=_profile_in())
        db.flush()

        result = update_search_profile(
            db,
            profile_id=profile.id,
            user_id=user2.id,
            search_profile_in=SearchProfileUpdate(profile_name="Hack", query="X", location="Y"),
        )
        assert result is None


class TestDeleteSearchProfile:
    """Tests for ``delete_search_profile``."""

    def test_delete_returns_true(self, db):
        user = _make_user(db)
        profile = create_search_profile(db, user_id=user.id, search_profile_in=_profile_in())
        db.flush()

        assert delete_search_profile(db, profile_id=profile.id, user_id=user.id) is True
        assert get_search_profile_by_id(db, profile_id=profile.id, user_id=user.id) is None

    def test_delete_wrong_user_returns_false(self, db):
        user1 = _make_user(db, "owner@example.com")
        user2 = _make_user(db, "intruder@example.com")
        profile = create_search_profile(db, user_id=user1.id, search_profile_in=_profile_in())
        db.flush()

        assert delete_search_profile(db, profile_id=profile.id, user_id=user2.id) is False
        # The profile must still exist for its real owner
        assert get_search_profile_by_id(db, profile_id=profile.id, user_id=user1.id) is not None

    def test_delete_nonexistent_returns_false(self, db):
        user = _make_user(db)
        assert delete_search_profile(db, profile_id=999999, user_id=user.id) is False
