"""Template context dependencies and helpers for server-rendered pages."""

from __future__ import annotations

from fastapi import Request


def get_base_template_context(request: Request) -> dict[str, bool]:
    """Build the shared base template context for server-rendered pages.

    :param request: Incoming HTTP request.
    :return: Shared context values required by base templates.
    """
    return {
        "is_authenticated": bool(request.session.get("is_authenticated", False)),
    }