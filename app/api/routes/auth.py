"""Define browser routes for authentication-related pages."""

from __future__ import annotations

import time

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.crud.user import get_user_by_email
from app.db.session import get_db
from app.dependencies.templates import get_base_template_context
from app.schemas.user import UserCreate
from app.services.auth_service import register_user_account

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="templates")


def _build_register_form_data(email: str = "") -> dict[str, str]:
    """Build normalized registration form data for template rendering.

    :param email: Submitted email value, if any.
    :return: Normalized form data for the registration form.
    """
    return {
        "register_email": email,
    }


def _build_login_form_data(email: str = "") -> dict[str, str]:
    """Build normalized login form data for template rendering.

    :param email: Submitted email value, if any.
    :return: Normalized form data for the login form.
    """
    return {
        "login_email": email,
    }


@router.get("", response_class=HTMLResponse, name="render_auth_page")
def render_auth_page(
    request: Request,
    registered: int = 0,
    session_expired: int = 0,
) -> HTMLResponse:
    """Render the authentication page.

    :param request: Incoming HTTP request.
    :param registered: Success flag shown after a completed registration redirect.
    :param session_expired: Success flag shown after a session expiration redirect.
    :return: Rendered authentication page.
    """
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={
            **get_base_template_context(request),
            "errors": {},
            "form_data": {
                **_build_login_form_data(),
                **_build_register_form_data(),
            },
            "registered": bool(registered),
            "session_expired": bool(session_expired),
        },
    )


@router.post("/register", response_class=HTMLResponse, response_model=None)
def register_user(
    request: Request,
    db: Session = Depends(get_db),
    email: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> Response:
    """Validate submitted registration data and create a new user.

    :param request: Incoming HTTP request.
    :param db: Active SQLAlchemy database session.
    :param email: Submitted email address from the registration form.
    :param password: Submitted plaintext password from the registration form.
    :return: Redirect to the auth page on success, or the form page with errors.
    """
    form_data = {
        **_build_login_form_data(),
        **_build_register_form_data(email=email),
    }
    errors: dict[str, str] = {}

    try:
        user_in = UserCreate(email=email, password=password)
    except ValidationError as exc:
        for error in exc.errors():
            field_name = str(error["loc"][0]) if error["loc"] else "__root__"

            if field_name == "email":
                errors["register_email"] = "Bitte gib eine gültige E-Mail-Adresse ein."

            elif field_name in ("password", "__root__"):
                msg = error["msg"]
                if "min_length" in msg:
                    errors["register_password"] = "Das Passwort muss mindestens 10 Zeichen lang sein."
                elif "max_length" in msg:
                    errors["register_password"] = "Das Passwort darf höchstens 128 Zeichen lang sein."
                elif "whitespace" in msg:
                    errors["register_password"] = "Das Passwort darf nicht mit Leerzeichen beginnen oder enden."
                elif "common_password" in msg:
                    errors["register_password"] = "Dieses Passwort ist zu häufig und daher nicht erlaubt."
                elif "email_part_in_password" in msg:
                    errors["register_password"] = "Das Passwort darf keine Teile deiner E-Mail-Adresse enthalten."
                else:
                    errors["register_password"] = "Das Passwort ist ungültig."

        return templates.TemplateResponse(
            request=request,
            name="auth.html",
            context={
                **get_base_template_context(request),
                "errors": errors,
                "form_data": form_data,
                "registered": False,
            },
            status_code=422,
        )

    try:
        register_user_account(db, user_in)
    except (ValueError, IntegrityError):
        errors["register_email"] = "Diese E-Mail-Adresse ist bereits registriert."

        return templates.TemplateResponse(
            request=request,
            name="auth.html",
            context={
                **get_base_template_context(request),
                "errors": errors,
                "form_data": form_data,
                "registered": False,
            },
            status_code=422,
        )

    redirect_url = request.url_for("render_auth_page").include_query_params(registered=1)
    return RedirectResponse(url=str(redirect_url), status_code=303)


@router.post("/login", response_class=HTMLResponse, response_model=None)
def login_user(
    request: Request,
    db: Session = Depends(get_db),
    email: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> Response:
    """Authenticate a user from the login form and start a session.

    :param request: Incoming HTTP request.
    :param db: Active SQLAlchemy database session.
    :param email: Submitted email address from the login form.
    :param password: Submitted plaintext password from the login form.
    :return: Redirect to the dashboard on success, or the auth page with errors.
    """
    form_data = {
        **_build_login_form_data(email=email),
        **_build_register_form_data(),
    }
    errors: dict[str, str] = {}

    user = get_user_by_email(db, email)

    if user is None or not verify_password(password, user.password_hash):
        errors["login_general"] = "Ungültige E-Mail-Adresse oder falsches Passwort."

        return templates.TemplateResponse(
            request=request,
            name="auth.html",
            context={
                **get_base_template_context(request),
                "errors": errors,
                "form_data": form_data,
                "registered": False,
            },
            status_code=422,
        )

    request.session.clear()
    now_ts = int(time.time())
    request.session["created_at"] = now_ts
    request.session["last_seen"] = now_ts
    request.session["user_id"] = user.id
    request.session["user_email"] = user.email
    request.session["is_authenticated"] = True

    redirect_url = request.url_for("render_dashboard_page")
    return RedirectResponse(url=str(redirect_url), status_code=303)


@router.post("/logout", response_model=None)
def logout_user(request: Request) -> RedirectResponse:
    """Clear the current session and redirect the user to the landing page.

    :param request: Incoming HTTP request.
    :return: Redirect response to the index page.
    """
    request.session.clear()

    redirect_url = request.url_for("render_index_page")
    return RedirectResponse(url=str(redirect_url), status_code=303)