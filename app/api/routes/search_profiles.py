"""Define browser routes for creating, editing, and deleting search profiles."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud.search_profile import (
    get_next_default_search_profile_name,
    get_search_profile_by_id,
)
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.templates import get_base_template_context
from app.models.user import User
from app.schemas.search_profile import SearchProfileCreate, SearchProfileUpdate
from app.services.search_profile_service import (
    create_search_profile_for_user,
    delete_search_profile_for_user,
    update_search_profile_for_user,
)

router = APIRouter(prefix="/search-profiles", tags=["search_profiles"])
templates = Jinja2Templates(directory="templates")


def _build_form_data(
    profile_name: str = "",
    query: str = "",
    location: str = "Deutschland",
    remote_only: bool = False,
    employment_types: list[str] | None = None,
    experience_levels: list[str] | None = None,
    radius_km: str | None = None,
) -> dict[str, object]:
    """Build normalized form data for the search-profile form.

    :param profile_name: Submitted profile name.
    :param query: Submitted job query.
    :param location: Submitted location value.
    :param remote_only: Submitted remote-only flag.
    :param employment_types: Submitted employment types.
    :param experience_levels: Submitted experience levels.
    :param radius_km: Submitted search radius.
    :return: Normalized template form data.
    """
    return {
        "profile_name": profile_name,
        "query": query,
        "location": location,
        "remote_only": remote_only,
        "employment_types": employment_types or [],
        "experience_levels": experience_levels or [],
        "radius_km": "" if radius_km is None else radius_km,
    }


def _map_search_profile_validation_errors(exc: ValidationError) -> dict[str, str]:
    """Map Pydantic validation errors to user-friendly German form errors.

    :param exc: Raised Pydantic validation error.
    :return: Template-ready error messages keyed by form field name.
    """
    errors: dict[str, str] = {}

    for error in exc.errors():
        loc = error.get("loc", ())
        field_name = str(loc[0]) if loc else "__root__"
        error_type = error.get("type", "")
        msg = error.get("msg", "")

        if field_name == "profile_name":
            if error_type == "missing":
                errors["profile_name"] = "Bitte gib einen Profilnamen ein."
            else:
                errors["profile_name"] = "Bitte gib einen gültigen Profilnamen ein."

        elif field_name == "query":
            if error_type == "missing":
                errors["query"] = "Bitte gib einen Suchbegriff ein."
            else:
                errors["query"] = "Bitte gib einen gültigen Suchbegriff ein."

        elif field_name == "location":
            if error_type == "missing":
                errors["location"] = "Bitte gib einen Standort ein."
            else:
                errors["location"] = "Bitte gib einen gültigen Standort ein."

        elif field_name == "radius_km":
            if error_type == "int_parsing":
                errors["radius_km"] = "Bitte gib beim Radius eine ganze Zahl ein."
            elif error_type in ("greater_than_equal", "less_than_equal"):
                errors["radius_km"] = "Der Radius muss zwischen 1 und 500 km liegen."
            else:
                errors["radius_km"] = "Bitte gib einen gültigen Radius ein."

        elif field_name in ("__root__",):
            if "radius_km can only be set for cities" in msg:
                errors["radius_km"] = (
                    "Ein Radius ist nur erlaubt, wenn du einen konkreten Ort statt Deutschland angibst."
                )

    return errors


def _render_form(
    request: Request,
    *,
    current_user: User,
    form_data: dict[str, object],
    errors: dict[str, str],
    search_profile=None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the shared search-profile form template.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param form_data: Normalized template form data.
    :param errors: Template-ready error messages.
    :param search_profile: Existing ORM search profile for edit mode, if any.
    :param status_code: HTTP status code for the response.
    :return: Rendered HTML form response.
    """
    return templates.TemplateResponse(
        request=request,
        name="search_profile_form.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user,
            "form_data": form_data,
            "errors": errors,
            "search_profile": search_profile,
        },
        status_code=status_code,
    )


@router.get("/new", response_class=HTMLResponse, name="render_search_profile_create_page")
def render_search_profile_create_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    """Render the empty form for creating a search profile.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active SQLAlchemy database session.
    :return: Rendered HTML create form.
    """
    default_profile_name = get_next_default_search_profile_name(db, user_id=current_user.id)

    return _render_form(
        request,
        current_user=current_user,
        form_data=_build_form_data(profile_name=default_profile_name),
        errors={},
    )


@router.post("", response_class=HTMLResponse, name="create_search_profile")
def create_search_profile_action(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    profile_name: Annotated[str | None, Form()] = None,
    query: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "Deutschland",
    remote_only: Annotated[bool, Form()] = False,
    employment_types: Annotated[list[str] | None, Form()] = None,
    experience_levels: Annotated[list[str] | None, Form()] = None,
    radius_km: Annotated[str | None, Form()] = None,
) -> Response:
    """Validate and create a new search profile.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active SQLAlchemy database session.
    :param profile_name: Submitted profile name.
    :param query: Submitted job query.
    :param location: Submitted location value.
    :param remote_only: Submitted remote-only flag.
    :param employment_types: Submitted employment types.
    :param experience_levels: Submitted experience levels.
    :param radius_km: Submitted search radius.
    :return: Redirect response on success, or rendered form with errors.
    """
    form_data = _build_form_data(
        profile_name=profile_name or "",
        query=query,
        location=location,
        remote_only=remote_only,
        employment_types=employment_types,
        experience_levels=experience_levels,
        radius_km=radius_km,
    )

    try:
        search_profile_in = SearchProfileCreate(
            profile_name=profile_name.strip() if profile_name else None,
            query=query,
            location=location,
            remote_only=remote_only,
            employment_types=employment_types or [],
            experience_levels=experience_levels or [],
            radius_km=radius_km,
        )

    except ValidationError as exc:
        errors = _map_search_profile_validation_errors(exc)
        return _render_form(
            request,
            current_user=current_user,
            form_data=form_data,
            errors=errors,
            status_code=422,
        )

    try:
        create_search_profile_for_user(
            db,
            user_id=current_user.id,
            search_profile_in=search_profile_in,
        )
    except (ValueError, IntegrityError):
        errors = {
            "profile_name": "Du hast bereits ein Suchprofil mit diesem Namen."
        }
        return _render_form(
            request,
            current_user=current_user,
            form_data=form_data,
            errors=errors,
            status_code=422,
        )

    return RedirectResponse(
        url=str(request.url_for("render_job_search_page")),
        status_code=303,
    )


@router.get("/{search_profile_id}/edit", response_class=HTMLResponse, name="render_search_profile_edit_page")
def render_search_profile_edit_page(
    request: Request,
    search_profile_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Render the prefilled form for editing one search profile.

    :param request: Incoming HTTP request.
    :param search_profile_id: Identifier of the search profile.
    :param current_user: Authenticated user.
    :param db: Active SQLAlchemy database session.
    :return: Rendered HTML edit form or redirect response.
    """
    search_profile = get_search_profile_by_id(
        db,
        profile_id=search_profile_id,
        user_id=current_user.id,
    )
    if search_profile is None:
        return RedirectResponse(
            url=str(request.url_for("render_job_search_page")),
            status_code=303,
        )

    return _render_form(
        request,
        current_user=current_user,
        form_data=_build_form_data(
            profile_name=search_profile.profile_name,
            query=search_profile.query,
            location=search_profile.location,
            remote_only=search_profile.remote_only,
            employment_types=list(search_profile.employment_types or []),
            experience_levels=list(search_profile.experience_levels or []),
            radius_km=search_profile.radius_km,
        ),
        errors={},
        search_profile=search_profile,
    )


@router.post("/{search_profile_id}", response_class=HTMLResponse, name="update_search_profile")
def update_search_profile_action(
    request: Request,
    search_profile_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    profile_name: Annotated[str | None, Form()] = None,
    query: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "Deutschland",
    remote_only: Annotated[bool, Form()] = False,
    employment_types: Annotated[list[str] | None, Form()] = None,
    experience_levels: Annotated[list[str] | None, Form()] = None,
    radius_km: Annotated[str | None, Form()] = None,
) -> Response:
    """Validate and update an existing search profile.

    :param request: Incoming HTTP request.
    :param search_profile_id: Identifier of the search profile to update.
    :param current_user: Authenticated user.
    :param db: Active SQLAlchemy database session.
    :param profile_name: Submitted profile name.
    :param query: Submitted job query.
    :param location: Submitted location value.
    :param remote_only: Submitted remote-only flag.
    :param employment_types: Submitted employment types.
    :param experience_levels: Submitted experience levels.
    :param radius_km: Submitted search radius.
    :return: Redirect response on success, or rendered form with errors.
    """
    existing_profile = get_search_profile_by_id(
        db,
        profile_id=search_profile_id,
        user_id=current_user.id,
    )
    if existing_profile is None:
        return RedirectResponse(
            url=str(request.url_for("render_job_search_page")),
            status_code=303,
        )

    form_data = _build_form_data(
        profile_name=profile_name or "",
        query=query,
        location=location,
        remote_only=remote_only,
        employment_types=employment_types,
        experience_levels=experience_levels,
        radius_km=radius_km,
    )

    try:
        search_profile_in = SearchProfileUpdate(
            profile_name=profile_name.strip() if profile_name else None,
            query=query,
            location=location,
            remote_only=remote_only,
            employment_types=employment_types or [],
            experience_levels=experience_levels or [],
            radius_km=radius_km,
        )
    except ValidationError as exc:
        errors = _map_search_profile_validation_errors(exc)
        return _render_form(
            request,
            current_user=current_user,
            form_data=form_data,
            errors=errors,
            search_profile=existing_profile,
            status_code=422,
        )

    try:
        updated_profile = update_search_profile_for_user(
            db,
            profile_id=search_profile_id,
            user_id=current_user.id,
            search_profile_in=search_profile_in,
        )
    except (ValueError, IntegrityError):
        errors = {"profile_name": "Du hast bereits ein Suchprofil mit diesem Namen."}
        return _render_form(
            request,
            current_user=current_user,
            form_data=form_data,
            errors=errors,
            search_profile=existing_profile,
            status_code=422,
        )

    if updated_profile is None:
        return RedirectResponse(
            url=str(request.url_for("render_job_search_page")),
            status_code=303,
        )

    return RedirectResponse(
        url=str(request.url_for("render_job_search_page")),
        status_code=303,
    )


@router.post("/{search_profile_id}/delete", response_class=HTMLResponse, name="delete_search_profile")
def delete_search_profile_action(
    request: Request,
    search_profile_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RedirectResponse:
    """Delete one search profile owned by the current user.

    :param request: Incoming HTTP request.
    :param search_profile_id: Identifier of the search profile to delete.
    :param current_user: Authenticated user.
    :param db: Active SQLAlchemy database session.
    :return: Redirect response to the search page.
    """
    was_deleted = delete_search_profile_for_user(
        db,
        profile_id=search_profile_id,
        user_id=current_user.id,
    )

    message = "Suchprofil erfolgreich gelöscht."
    if not was_deleted:
        message = "Suchprofil nicht gefunden."

    search_page_url = str(request.url_for("render_job_search_page"))
    return RedirectResponse(
        url=f"{search_page_url}?message={message}",
        status_code=303,
    )