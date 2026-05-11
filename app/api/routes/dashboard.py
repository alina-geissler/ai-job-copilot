"""Define routes for the authenticated dashboard page."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="templates")

from app.dependencies.auth import get_current_user
from app.dependencies.templates import get_base_template_context
from app.models.user import User


@router.get("/dashboard", response_class=HTMLResponse, name="render_dashboard_page")
def render_dashboard_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> HTMLResponse:
    """Render the dashboard page for the authenticated user.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user resolved from the current session.
    :return: Rendered dashboard page.
    """
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user
        },
    )