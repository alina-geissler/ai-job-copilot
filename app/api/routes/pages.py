"""Define browser routes for static page templates.

Serve the landing page template for users entering the web interface.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse, name="render_index_page")
def render_index_page(request: Request):
    """Render the landing page template."""

    is_authenticated = bool(request.session.get("is_authenticated", False))

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"is_authenticated": is_authenticated}
    )
