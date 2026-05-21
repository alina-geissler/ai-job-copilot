"""Provide write services for search-profile use cases."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.crud.search_profile import (
    create_search_profile,
    delete_search_profile,
    update_search_profile
)
from app.models.search_profile import SearchProfile
from app.schemas.search_profile import SearchProfileCreate, SearchProfileUpdate


def create_search_profile_for_user(
    db: Session,
    *,
    user_id: int,
    search_profile_in: SearchProfileCreate
) -> SearchProfile:
    """Create and commit a new search profile for one user.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :param search_profile_in: Validated input data for profile creation.
    :return: Newly created persisted search-profile ORM object.
    """
    try:
        search_profile = create_search_profile(
            db,
            user_id=user_id,
            search_profile_in=search_profile_in
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return search_profile


def update_search_profile_for_user(
    db: Session,
    *,
    profile_id: int,
    user_id: int,
    search_profile_in: SearchProfileUpdate
) -> SearchProfile | None:
    """Update and commit an existing search profile for one user.

    :param db: Active SQLAlchemy database session.
    :param profile_id: Identifier of the search profile to update.
    :param user_id: Identifier of the owning user.
    :param search_profile_in: Validated input data for profile update.
    :return: Updated persisted search-profile ORM object, or ``None`` if not found.
    """
    try:
        search_profile = update_search_profile(
            db,
            profile_id=profile_id,
            user_id=user_id,
            search_profile_in=search_profile_in
        )
        if search_profile is None:
            db.rollback()
            return None

        db.commit()
    except Exception:
        db.rollback()
        raise

    return search_profile


def delete_search_profile_for_user(
    db: Session,
    *,
    profile_id: int,
    user_id: int
) -> bool:
    """Delete and commit one search profile for a user.

    :param db: Active SQLAlchemy database session.
    :param profile_id: Identifier of the search profile to delete.
    :param user_id: Identifier of the owning user.
    :return: True if the profile was deleted, otherwise False.
    """
    try:
        deleted = delete_search_profile(
            db,
            profile_id=profile_id,
            user_id=user_id
        )
        if not deleted:
            db.rollback()
            return False

        db.commit()
    except Exception:
        db.rollback()
        raise

    return True