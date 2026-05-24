"""
Create the FastAPI application object and register route modules.

Expose the main ASGI app for the different endpoints.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.pages import router as pages_router
from app.api.routes.search_profiles import router as search_profiles_router
from app.api.routes.application_tracker import router as application_tracker_router

from app.core.config import settings
from app.dependencies.auth import AuthenticationRequiredError, AuthFailureReason
from app.dependencies.templates import build_feedback_query

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age_seconds,
    same_site=settings.session_same_site,
    https_only=settings.session_https_only
)


@app.exception_handler(AuthenticationRequiredError)
async def authentication_required_exception_handler(
    request: Request,
    exc: AuthenticationRequiredError
) -> RedirectResponse:
    """Redirect browser requests for authentication failures to the auth page.

    :param request: Incoming HTTP request.
    :param exc: Raised authentication failure.
    :return: Redirect response to the auth page with feedback message.
    """
    auth_url = str(request.url_for("render_auth_page"))

    if exc.reason == AuthFailureReason.SESSION_EXPIRED:
        message = "Deine Sitzung ist abgelaufen. Bitte logge dich erneut ein."
        message_type = "error"
    elif exc.reason == AuthFailureReason.USER_NOT_FOUND:
        message = "Dein Benutzerkonto wurde nicht gefunden. Bitte logge dich erneut ein."
        message_type = "error"
    else:
        message = "Bitte logge dich ein, um diese Seite aufzurufen."
        message_type = "error"

    query_string = build_feedback_query(
        message=message,
        message_type=message_type
    )
    return RedirectResponse(
        url=f"{auth_url}?{query_string}",
        status_code=303
    )


app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(pages_router)
app.include_router(jobs_router)
app.include_router(dashboard_router)
app.include_router(search_profiles_router)
app.include_router(application_tracker_router)
app.include_router(documents_router)
