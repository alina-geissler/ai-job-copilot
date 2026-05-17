"""
Create the FastAPI application object and register route modules.

Expose the main ASGI app for the different endpoints.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.pages import router as pages_router
from app.api.routes.search_profiles import router as search_profiles_router
from app.api.routes.application_tracker import router as application_tracker_router

from app.core.config import settings

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age_seconds,
    same_site=settings.session_same_site,
    https_only=settings.session_https_only,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Redirect browser requests for unauthorized protected pages to the auth page.

    :param request: Incoming HTTP request.
    :param exc: Raised HTTP exception.
    :return: Redirect response for unauthorized browser requests, otherwise re-raise.
    """
    if exc.status_code == 401:
        redirect_url = request.url_for("render_auth_page").include_query_params(session_expired=1)
        return RedirectResponse(url=str(redirect_url), status_code=303)
    raise exc


app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(pages_router)
app.include_router(jobs_router)
app.include_router(dashboard_router)
app.include_router(search_profiles_router)
app.include_router(application_tracker_router)
