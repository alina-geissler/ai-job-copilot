"""Security helpers for password hashing and verification."""

from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt.

    :param password: Plaintext password provided by the user.
    :return: Bcrypt hash as a UTF-8 string for database storage.
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes, salt)
    return hashed_password.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash.

    :param password: Plaintext password provided by the user.
    :param password_hash: Stored bcrypt password hash from the database.
    :return: True if the password matches the hash, otherwise False.
    """
    password_bytes = password.encode("utf-8")
    hash_bytes = password_hash.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hash_bytes)