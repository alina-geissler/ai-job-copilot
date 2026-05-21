"""Provide authentication dependencies for session-based browser routes."""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.user import get_user_by_id
from app.db.session import get_db
from app.models.user import User


class AuthFailureReason(StrEnum):
    """Enumerate browser authentication failure reasons."""

    LOGIN_REQUIRED = "login_required"
    SESSION_EXPIRED = "session_expired"
    USER_NOT_FOUND = "user_not_found"


class AuthenticationRequiredError(Exception):
    """Raised when an authenticated browser user is required."""

    def __init__(self, reason: AuthFailureReason) -> None:
        """Initialize the exception with a failure reason.

        :param reason: Authentication failure reason.
        """
        self.reason = reason
        super().__init__(reason.value)


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)]
) -> User:
    """Return the authenticated user stored in the current session.

    :param request: Incoming HTTP request.
    :param db: Active SQLAlchemy database session.
    :return: The authenticated user.
    :raises AuthenticationRequiredError: If the session is missing, invalid,
        expired, or the user no longer exists.
    """
    user_id = request.session.get("user_id")
    is_authenticated = request.session.get("is_authenticated", False)

    if not user_id or not is_authenticated:
        raise AuthenticationRequiredError(AuthFailureReason.LOGIN_REQUIRED)

    now_ts = int(time.time())
    created_at = request.session.get("created_at")
    last_seen = request.session.get("last_seen")

    if not created_at or not last_seen:
        request.session.clear()
        raise AuthenticationRequiredError(AuthFailureReason.LOGIN_REQUIRED)

    if now_ts - int(last_seen) > settings.session_idle_timeout_seconds:
        request.session.clear()
        raise AuthenticationRequiredError(AuthFailureReason.SESSION_EXPIRED)

    if now_ts - int(created_at) > settings.session_absolute_timeout_seconds:
        request.session.clear()
        raise AuthenticationRequiredError(AuthFailureReason.SESSION_EXPIRED)

    user = get_user_by_id(db, user_id)

    if user is None:
        request.session.clear()
        raise AuthenticationRequiredError(AuthFailureReason.USER_NOT_FOUND)

    request.session["last_seen"] = now_ts
    return user