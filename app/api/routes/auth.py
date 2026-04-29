"""Define browser routes for authentication-related pages.

 Serve the authentication page template for the web UI.
 """

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
def render_auth_page(request: Request):
    """Render the authentication page template after an incoming HTTP request."""
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={}
    )
