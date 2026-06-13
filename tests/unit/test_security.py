"""Unit tests for password hashing and verification helpers."""

from __future__ import annotations

from app.core.security import hash_password, verify_password


def test_hash_returns_bcrypt_prefix():
    """Hashed password must start with the bcrypt identifier."""
    result = hash_password("SuperSecret99!")
    assert result.startswith("$2b$")


def test_verify_correct_password_returns_true():
    """Verifying the same password against its hash returns True."""
    password = "SuperSecret99!"
    hashed = hash_password(password)
    assert verify_password(password, hashed) is True


def test_verify_wrong_password_returns_false():
    """Verifying a wrong password against a hash returns False."""
    hashed = hash_password("SuperSecret99!")
    assert verify_password("WrongPassword!", hashed) is False


def test_hashes_are_unique_due_to_salt():
    """Two hashes of the same password must differ because of per-hash salts."""
    password = "SuperSecret99!"
    hash1 = hash_password(password)
    hash2 = hash_password(password)
    assert hash1 != hash2
