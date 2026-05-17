"""CRUD operations for the SearchProfile model.

Handle database interactions for creating, reading, updating, and deleting
search profiles that belong to application users.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.search_profile import SearchProfile
from app.schemas.search_profile import SearchProfileCreate, SearchProfileRead, SearchProfileUpdate


def get_search_profiles_for_user(db: Session, user_id: int) -> list[SearchProfile]:
    """Retrieve all search profiles belonging to a specific user.

    Order the profiles by most recently updated first so the newest changes
    appear at the top of the overview page.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :return: List of matching ORM search-profile objects.
    """
    statement = (
        select(SearchProfile)
        .where(SearchProfile.user_id == user_id)
        .order_by(SearchProfile.updated_at.desc(), SearchProfile.id.desc())
    )
    return list(db.scalars(statement).all())


def get_search_profile_by_id(db: Session, profile_id: int, user_id: int) -> SearchProfile | None:
    """Retrieve a single search profile by id for a specific user.

    :param db: Active SQLAlchemy database session.
    :param profile_id: Identifier of the search profile.
    :param user_id: Identifier of the owning user.
    :return: Matching ORM search-profile object, or ``None`` if not found.
    """
    statement = select(SearchProfile).where(
        SearchProfile.id == profile_id,
        SearchProfile.user_id == user_id,
    )
    return db.scalar(statement)


def get_search_profile_by_id_for_user(
    db: Session,
    *,
    search_profile_id: int,
    user_id: int,
) -> SearchProfile | None:
    """Retrieve one search profile by id for a specific user.

    Provide a naming variant that matches the search-run/job-search service flow.

    :param db: Active SQLAlchemy database session.
    :param search_profile_id: Identifier of the search profile.
    :param user_id: Identifier of the owning user.
    :return: Matching ORM search-profile object, or ``None`` if not found.
    """
    return get_search_profile_by_id(db, profile_id=search_profile_id, user_id=user_id)


def get_next_default_search_profile_name(db: Session, user_id: int) -> str:
    """Build the smallest free default profile name for a user.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :return: Default profile name like ``Suchprofil 3``.
    """
    statement = select(SearchProfile.profile_name).where(SearchProfile.user_id == user_id)
    existing_names = set(db.scalars(statement).all())

    next_number = 1
    while f"Suchprofil {next_number}" in existing_names:
        next_number += 1

    return f"Suchprofil {next_number}"


def create_search_profile(
    db: Session,
    user_id: int,
    search_profile_in: SearchProfileCreate,
) -> SearchProfile:
    """Create and flush a new search profile for a user.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :param search_profile_in: Validated input data for profile creation.
    :raises ValueError: If the profile name already exists for the user.
    :return: Newly created ORM search-profile object.
    """
    profile_name = search_profile_in.profile_name or get_next_default_search_profile_name(
        db,
        user_id=user_id,
    )

    search_profile = SearchProfile(
        user_id=user_id,
        profile_name=profile_name,
        query=search_profile_in.query,
        location=search_profile_in.location,
        remote_only=search_profile_in.remote_only,
        employment_types=search_profile_in.employment_types,
        experience_levels=search_profile_in.experience_levels,
        radius_km=search_profile_in.radius_km,
    )
    db.add(search_profile)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("profile_name_already_exists") from exc

    return search_profile


def update_search_profile(
    db: Session,
    profile_id: int,
    user_id: int,
    search_profile_in: SearchProfileUpdate,
) -> SearchProfile | None:
    """Update an existing search profile belonging to a specific user.

    :param db: Active SQLAlchemy database session.
    :param profile_id: Identifier of the search profile to update.
    :param user_id: Identifier of the owning user.
    :param search_profile_in: Validated input data for profile update.
    :return: Updated ORM search-profile object, or ``None`` if no matching profile exists.
    """
    search_profile = get_search_profile_by_id(db, profile_id=profile_id, user_id=user_id)

    if search_profile is None:
        return None

    search_profile.profile_name = search_profile_in.profile_name
    search_profile.query = search_profile_in.query
    search_profile.location = search_profile_in.location
    search_profile.remote_only = search_profile_in.remote_only
    search_profile.employment_types = search_profile_in.employment_types
    search_profile.experience_levels = search_profile_in.experience_levels
    search_profile.radius_km = search_profile_in.radius_km

    db.add(search_profile)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("profile_name_already_exists") from exc

    return search_profile


def delete_search_profile(db: Session, profile_id: int, user_id: int) -> bool:
    """Delete a search profile belonging to a specific user.

    :param db: Active SQLAlchemy database session.
    :param profile_id: Identifier of the search profile to delete.
    :param user_id: Identifier of the owning user.
    :return: True if a profile was marked for deletion, otherwise False.
    """
    search_profile = get_search_profile_by_id(db, profile_id=profile_id, user_id=user_id)

    if search_profile is None:
        return False

    db.delete(search_profile)
    db.flush()
    return True


def get_search_profiles_for_user_read(db: Session, user_id: int) -> list[SearchProfileRead]:
    """Retrieve all search profiles for a user as validated read schemas.

    :param db: Active SQLAlchemy database session.
    :param user_id: Identifier of the owning user.
    :return: List of validated read schemas.
    """
    search_profiles = get_search_profiles_for_user(db, user_id=user_id)
    return [SearchProfileRead.model_validate(search_profile) for search_profile in search_profiles]


def get_search_profile_by_id_read(
    db: Session,
    profile_id: int,
    user_id: int,
) -> SearchProfileRead | None:
    """Retrieve one search profile for a user as a validated read schema.

    :param db: Active SQLAlchemy database session.
    :param profile_id: Identifier of the search profile.
    :param user_id: Identifier of the owning user.
    :return: Validated read schema, or ``None`` if not found.
    """
    search_profile = get_search_profile_by_id(db, profile_id=profile_id, user_id=user_id)

    if search_profile is None:
        return None

    return SearchProfileRead.model_validate(search_profile)