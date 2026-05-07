"""User Pydantic schemas for request validation and API response serialization.

Defines the data contracts between the API layer and its clients.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime


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


class UserResponse(UserBase):
    """Schema for user data returned by the API.

    Includes DB-generated fields (id, is_active, created_at).
    Intentionally excludes the password hash.
    """
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)