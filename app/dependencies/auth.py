"""Provide authentication dependencies for session-based browser routes."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.user import get_user_by_id
from app.db.session import get_db
from app.models.user import User


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Return the authenticated user stored in the current session.

    :param request: Incoming HTTP request.
    :param db: Active SQLAlchemy database session.
    :return: The authenticated user.
    :raises HTTPException: If the session is missing, invalid, expired, or the user no longer exists.
    """
    user_id = request.session.get("user_id")
    is_authenticated = request.session.get("is_authenticated", False)

    if not user_id or not is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    now_ts = int(time.time())
    created_at = request.session.get("created_at")
    last_seen = request.session.get("last_seen")

    if not created_at or not last_seen:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    if now_ts - int(last_seen) > settings.session_idle_timeout_seconds:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired.",
        )

    if now_ts - int(created_at) > settings.session_absolute_timeout_seconds:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired.",
        )

    user = get_user_by_id(db, user_id)

    if user is None:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    request.session["last_seen"] = now_ts
    return user