"""CRUD operations for the User model.

Handles database interactions for user creation and lookup.
Password hashing is delegated to the security module.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate


def get_user_by_email(db: Session, email: str) -> User | None:
    """Retrieve a user by their email address.

    :param db: Active SQLAlchemy database session.
    :param email: Email address to look up.
    :return: The matching User ORM object, or None if not found.
    """
    return db.scalar(select(User).where(User.email == email))


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """Retrieve a user by their primary key.

    :param db: Active SQLAlchemy database session.
    :param user_id: Primary key of the user to retrieve.
    :return: The matching User ORM object, or None if not found.
    """
    return db.get(User, user_id)


def create_user(db: Session, data: UserCreate) -> User:
    """Create and flush a new user record.

    Checks for duplicate email before inserting. The plaintext password
    from ``data`` is hashed before storage and never persisted as plaintext.

    :param db: Active SQLAlchemy database session.
    :param data: Validated registration input from the API layer.
    :raises ValueError: If the email address is already registered.
    :return: The newly created User ORM object.
    """
    if get_user_by_email(db, data.email):
        raise ValueError("Email already registered")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password)
    )
    db.add(user)
    db.flush()
    return user