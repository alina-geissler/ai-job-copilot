"""User Pydantic schemas for request validation and API response serialization.

Defines the data contracts between the API layer and its clients.
"""

from __future__ import annotations

import re

from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, ConfigDict, EmailStr, model_validator

def _load_password_blocklist() -> frozenset[str]:
    """Load common weak passwords from a flat text file.

    :return: Frozenset of lowercase blocked passwords.
    """
    blocklist_path = Path(__file__).parent.parent / "core" / "data" / "common_passwords.txt"
    with blocklist_path.open(encoding="utf-8") as f:
        return frozenset(line.strip().lower() for line in f if line.strip())

COMMON_WEAK_PASSWORDS = _load_password_blocklist()


class UserBase(BaseModel):
    """Shared base fields for all User schemas."""
    email: EmailStr


class UserCreate(UserBase):
    """Schema for user registration input.

    Extends ``UserBase`` with a plaintext password field.
    The password is hashed in the CRUD layer and never stored or
    returned as plaintext.
    """
    password: str

    @model_validator(mode="after")
    def validate_password_with_context(self) -> "UserCreate":
        """Validate password strength and context against the email address.

        :raises ValueError: If the password is too weak or context-related.
        :return: The validated model instance.
        """
        password = self.password
        email = self.email

        if password != password.strip():
            raise ValueError("whitespace")

        if len(password) < 10:
            raise ValueError("min_length")

        if len(password) > 128:
            raise ValueError("max_length")

        if password.lower() in COMMON_WEAK_PASSWORDS:
            raise ValueError("common_password")

        local_part = email.split("@")[0].lower()
        email_parts = [local_part] + [
            part for part in re.split(r"[._-]+", local_part) if len(part) >= 3
        ]

        for part in email_parts:
            if part in password.lower():
                raise ValueError("email_part_in_password")

        return self


class UserResponse(UserBase):
    """Schema for user data returned by the API.

    Includes DB-generated fields.
    Intentionally excludes the password hash.
    """
    id: int
    is_active: bool
    role: str
    trial_job_searches_left: int
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)