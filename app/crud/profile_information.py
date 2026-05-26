"""CRUD operations for the profile_information table.

Provide read and upsert access to candidate profile records.
All functions accept a SQLAlchemy session and do not commit — the
service layer owns transaction boundaries.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.profile_information import ProfileInformation


def get_profile_for_user(db: Session, *, user_id: int) -> ProfileInformation | None:
    """Return the profile record for one user, or None if it does not exist.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :return: ProfileInformation instance or None.
    """
    return db.query(ProfileInformation).filter(ProfileInformation.user_id == user_id).first()


def upsert_profile(
    db: Session,
    *,
    user_id: int,
    data: dict,
) -> ProfileInformation:
    """Create or update the profile record for a user.

    Fetch the existing row if one exists; otherwise create a new one.
    Set every key in ``data`` as an attribute on the record, then flush
    so the caller can inspect the result before committing.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param data: Mapping of column names to new values.
    :return: Created or updated ProfileInformation instance.
    """
    profile = get_profile_for_user(db, user_id=user_id)
    if profile is None:
        profile = ProfileInformation(user_id=user_id)
        db.add(profile)

    for key, value in data.items():
        if hasattr(profile, key):
            setattr(profile, key, value)

    db.flush()
    return profile


def delete_profile(db: Session, *, profile: ProfileInformation) -> None:
    """Delete a profile record. Does not commit — caller owns the transaction.

    :param db: Active database session.
    :param profile: ProfileInformation instance to delete.
    """
    db.delete(profile)
    db.flush()
