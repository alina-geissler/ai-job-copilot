"""Provide authentication-related write services."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.crud.user import create_user
from app.models.user import User
from app.schemas.user import UserCreate


def register_user_account(db: Session, user_in: UserCreate) -> User:
    """Create and commit a new user account.

    The service acts as the upper transaction boundary for the registration
    use case and keeps commit/rollback logic out of routes and CRUD helpers.

    :param db: Active SQLAlchemy database session.
    :param user_in: Validated user registration data.
    :raises ValueError: If the email address is already registered.
    :raises IntegrityError: If the insert violates a database constraint.
    :return: Newly created persisted user ORM object.
    """
    try:
        user = create_user(db, user_in)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return user