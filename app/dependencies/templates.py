"""Template context dependencies and helpers for server-rendered pages."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from fastapi import Request


def build_feedback_query(
    *,
    message: str,
    message_type: str
) -> str:
    """Build a URL-encoded query string for one feedback message.

    :param message: Human-readable feedback text.
    :param message_type: Feedback category, e.g. ``success`` or ``error``.
    :return: URL-encoded query string without leading question mark.
    """
    return urlencode(
        {
            "message": message,
            "message_type": message_type
        }
    )


def get_base_template_context(request: Request) -> dict[str, Any]:
    """Build the shared base template context for all pages.

    :param request: Incoming HTTP request.
    :return: Shared context values required by base template.
    """
    message = request.query_params.get("message")
    message_type = request.query_params.get("message_type")

    feedback: dict[str, str] | None = None
    if message and message_type in {"success", "error", "info", "warning"}:
        feedback = {
            "message": message,
            "type": message_type
        }

    return {
        "is_authenticated": bool(request.session.get("is_authenticated", False)),
        "feedback": feedback
    }