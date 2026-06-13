"""Unit tests for UserCreate Pydantic validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate


def _make(email: str = "user@example.com", password: str = "Sicher!Passwort99") -> UserCreate:
    return UserCreate(email=email, password=password)


def test_valid_user_create():
    """A well-formed email and strong password must create successfully."""
    user = _make()
    assert user.email == "user@example.com"
    assert user.password == "Sicher!Passwort99"


def test_password_too_short_raises():
    """A password shorter than 10 characters must be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        _make(password="Short1!")
    errors = exc_info.value.errors()
    assert any("min_length" in e["msg"] for e in errors)


def test_password_too_long_raises():
    """A password longer than 128 characters must be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        _make(password="A" * 129)
    errors = exc_info.value.errors()
    assert any("max_length" in e["msg"] for e in errors)


def test_password_leading_whitespace_raises():
    """A password with leading whitespace must be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        _make(password=" Sicher!Passwort99")
    errors = exc_info.value.errors()
    assert any("whitespace" in e["msg"] for e in errors)


def test_password_trailing_whitespace_raises():
    """A password with trailing whitespace must be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        _make(password="Sicher!Passwort99 ")
    errors = exc_info.value.errors()
    assert any("whitespace" in e["msg"] for e in errors)


def test_common_password_blocked():
    """A password on the common-password blocklist must be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        _make(password="password123")
    errors = exc_info.value.errors()
    assert any("common_password" in e["msg"] for e in errors)


def test_email_local_part_in_password_raises():
    """A password that contains the email local part must be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(email="alice@example.com", password="alice_secure99!")
    errors = exc_info.value.errors()
    assert any("email_part_in_password" in e["msg"] for e in errors)


def test_email_sub_segment_in_password_raises():
    """A password containing a meaningful sub-segment of the email must be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(email="alice.jones@example.com", password="jones1234secur!")
    errors = exc_info.value.errors()
    assert any("email_part_in_password" in e["msg"] for e in errors)


def test_invalid_email_raises():
    """A string that is not a valid email address must be rejected."""
    with pytest.raises(ValidationError):
        _make(email="not-an-email")
