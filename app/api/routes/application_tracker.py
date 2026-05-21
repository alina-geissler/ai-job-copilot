"""Define browser routes for the application tracker.

Render the tracker overview and detail pages and handle all browser-based
actions for creating, updating, and deleting tracker entries.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.enums import ApplicationStatus
from app.crud.application_tracker_entry import get_tracker_entry_by_id_for_user,list_tracker_entries_for_user
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.templates import build_feedback_query, get_base_template_context
from app.models.user import User
from app.services.application_tracker_service import (
    change_application_tracker_notes,
    change_application_tracker_status,
    create_application_tracker_entry,
    remove_application_tracker_entry
)
from app.utils.application_tracker_ui import (
    TRACKER_STATUS_CLASSES,
    TRACKER_STATUS_DATE_FIELDS,
    TRACKER_STATUS_LABELS,
    TRACKER_STATUS_ORDER
)

router = APIRouter(prefix="/tracker", tags=["application-tracker"])
templates = Jinja2Templates(directory="templates")


def _build_tracker_status_items(entry: Any) -> list[dict[str, Any]]:
    """Build template-ready status items for one tracker entry.

    :param entry: Tracker entry ORM object.
    :return: List of status metadata dictionaries for template rendering.
    """
    items: list[dict[str, Any]] = []

    for status in TRACKER_STATUS_ORDER:
        date_field_name = TRACKER_STATUS_DATE_FIELDS[status]

        if status == ApplicationStatus.SAVED:
            date_value = entry.created_at
            default_date = None
            shows_date = True
            opens_date_form = False
        else:
            date_value = getattr(entry, date_field_name) if date_field_name else None
            default_date = (
                date_value.date().isoformat()
                if date_value is not None
                else date.today().isoformat()
            )
            shows_date = date_value is not None
            opens_date_form = True

        items.append(
            {
                "value": status.value,
                "label": TRACKER_STATUS_LABELS[status],
                "css_class": TRACKER_STATUS_CLASSES[status],
                "is_current": entry.status == status,
                "date_value": date_value,
                "default_date": default_date,
                "shows_date": shows_date,
                "opens_date_form": opens_date_form
            }
        )

    return items


def _serialize_tracker_entry(entry: Any) -> dict[str, Any]:
    """Serialize one tracker entry into template-friendly data.

    :param entry: Tracker entry ORM object.
    :return: Dictionary with UI-ready tracker entry data.
    """
    return {
        "id": entry.id,
        "status": entry.status,
        "status_label": TRACKER_STATUS_LABELS[entry.status],
        "status_css_class": TRACKER_STATUS_CLASSES[entry.status],
        "status_items": _build_tracker_status_items(entry),
        "notes": entry.notes or "",
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "job": entry.job
    }


def _build_tracker_overview_context(
        request: Request,
        *,
        current_user: User,
        tracker_entries: list[Any]
) -> dict[str, Any]:
    """Build the template context for the tracker overview page.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param tracker_entries: Tracker entries visible to the user.
    :return: Template context for the tracker overview page.
    """
    return {
        **get_base_template_context(request),
        "current_user": current_user,
        "tracker_entries": [_serialize_tracker_entry(entry) for entry in tracker_entries]
    }


def _build_tracker_detail_context(
        request: Request,
        *,
        current_user: User,
        tracker_entry: Any
) -> dict[str, Any]:
    """Build the template context for one tracker detail page.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param tracker_entry: Tracker entry to display.
    :return: Template context for the tracker detail page.
    """
    return {
        **get_base_template_context(request),
        "current_user": current_user,
        "tracker_entry": _serialize_tracker_entry(tracker_entry)
    }


@router.get("", response_class=HTMLResponse, name="render_application_tracker_page")
def render_application_tracker_page(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)]
) -> HTMLResponse:
    """Render the application tracker overview page.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Rendered tracker overview page.
    """
    tracker_entries = list_tracker_entries_for_user(db, user_id=current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="tracker.html",
        context=_build_tracker_overview_context(
            request,
            current_user=current_user,
            tracker_entries=tracker_entries
        )
    )


@router.get("/{entry_id}", response_class=HTMLResponse, name="render_application_tracker_detail_page")
def render_application_tracker_detail_page(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        entry_id: int
) -> Response:
    """Render the detail page of one tracker entry.

    :param request: Incoming HTTP request.
    :param entry_id: Identifier of the tracker entry to display.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Rendered tracker detail page or redirect response.
    """
    tracker_entry = get_tracker_entry_by_id_for_user(
        db,
        entry_id=entry_id,
        user_id=current_user.id
    )

    if tracker_entry is None:
        tracker_url = str(request.url_for("render_application_tracker_page"))
        query_string = build_feedback_query(
            message="Tracker-Eintrag nicht gefunden.",
            message_type="error"
        )
        return RedirectResponse(
            url=f"{tracker_url}?{query_string}",
            status_code=303
        )

    return templates.TemplateResponse(
        request=request,
        name="tracker_detail.html",
        context=_build_tracker_detail_context(
            request,
            current_user=current_user,
            tracker_entry=tracker_entry
        )
    )


@router.post("/jobs/{job_id}", response_class=HTMLResponse, name="create_application_tracker_entry")
def create_application_tracker_entry_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        job_id: int
) -> RedirectResponse:
    """Create a tracker entry for one job if it is not already tracked.

    :param request: Incoming HTTP request.
    :param job_id: Identifier of the job to add to the tracker.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Redirect response to the tracker overview page.
    """
    _, created = create_application_tracker_entry(
        db,
        user_id=current_user.id,
        job_id=job_id
    )

    message = "Job wurde im Bewerbungstracker gespeichert."
    message_type = "success"
    if not created:
        message = "Dieser Job ist bereits im Bewerbungstracker gespeichert."
        message_type = "info"

    tracker_url = str(request.url_for("render_application_tracker_page"))
    query_string = build_feedback_query(
        message=message,
        message_type=message_type
    )
    return RedirectResponse(
        url=f"{tracker_url}?{query_string}",
        status_code=303
    )


@router.post("/{entry_id}/status", response_class=HTMLResponse, name="update_application_tracker_status")
def update_application_tracker_status_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        entry_id: int,
        status: Annotated[ApplicationStatus, Form()],
        status_date: Annotated[str | None, Form()] = None,
        redirect_to: Annotated[str, Form()] = "overview"
) -> RedirectResponse:
    """Update the current status of one tracker entry.

    :param request: Incoming HTTP request.
    :param entry_id: Identifier of the tracker entry to update.
    :param status: New tracker status.
    :param status_date: Optional date string for the selected status.
    :param redirect_to: Redirect target identifier, e.g. ``overview`` or ``detail``.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Redirect response to the overview or detail page.
    """
    normalized_status_date: date | None = None
    if status_date is not None:
        stripped_status_date = status_date.strip()
        if stripped_status_date:
            try:
                normalized_status_date = date.fromisoformat(stripped_status_date)
            except ValueError:
                query_string = build_feedback_query(
                    message="Ungültiges Datum für den Status.",
                    message_type="error"
                )

                if redirect_to == "detail":
                    detail_url = str(request.url_for("render_application_tracker_detail_page",
                                                     entry_id=entry_id)
                                     )
                    return RedirectResponse(
                        url=f"{detail_url}?{query_string}",
                        status_code=303
                    )

                tracker_url = str(request.url_for("render_application_tracker_page"))
                return RedirectResponse(
                    url=f"{tracker_url}?{query_string}",
                    status_code=303
                )

    tracker_entry = change_application_tracker_status(
        db,
        entry_id=entry_id,
        user_id=current_user.id,
        status=status,
        status_date=normalized_status_date
    )

    if tracker_entry is None:
        tracker_url = str(request.url_for("render_application_tracker_page"))
        query_string = build_feedback_query(
            message="Tracker-Eintrag nicht gefunden.",
            message_type="error"
        )
        return RedirectResponse(
            url=f"{tracker_url}?{query_string}",
            status_code=303
        )

    query_string = build_feedback_query(
        message="Status erfolgreich aktualisiert.",
        message_type="success"
    )

    if redirect_to == "detail":
        detail_url = str(request.url_for("render_application_tracker_detail_page",
                                         entry_id=entry_id)
                         )
        return RedirectResponse(
            url=f"{detail_url}?{query_string}",
            status_code=303
        )

    tracker_url = str(request.url_for("render_application_tracker_page"))
    return RedirectResponse(
        url=f"{tracker_url}?{query_string}",
        status_code=303
    )


@router.post("/{entry_id}/notes", response_class=HTMLResponse, name="update_application_tracker_notes")
def update_application_tracker_notes_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        entry_id: int,
        notes: Annotated[str | None, Form()] = None,
        redirect_to: Annotated[str, Form()] = "overview"
) -> RedirectResponse:
    """Update the notes of one tracker entry.

    :param request: Incoming HTTP request.
    :param entry_id: Identifier of the tracker entry to update.
    :param notes: New notes text.
    :param redirect_to: Redirect target identifier, e.g. ``overview`` or ``detail``.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Redirect response to the overview or detail page.
    """
    tracker_entry = change_application_tracker_notes(
        db,
        entry_id=entry_id,
        user_id=current_user.id,
        notes=notes
    )

    if tracker_entry is None:
        tracker_url = str(request.url_for("render_application_tracker_page"))
        query_string = build_feedback_query(
            message="Tracker-Eintrag nicht gefunden.",
            message_type="error"
        )
        return RedirectResponse(
            url=f"{tracker_url}?{query_string}",
            status_code=303
        )

    query_string = build_feedback_query(
        message="Notizen erfolgreich gespeichert.",
        message_type="success"
    )

    if redirect_to == "detail":
        detail_url = str(request.url_for("render_application_tracker_detail_page",
                                         entry_id=entry_id)
                         )
        return RedirectResponse(
            url=f"{detail_url}?{query_string}",
            status_code=303
        )

    tracker_url = str(request.url_for("render_application_tracker_page"))
    return RedirectResponse(
        url=f"{tracker_url}?{query_string}",
        status_code=303
    )


@router.post("/{entry_id}/delete", response_class=HTMLResponse, name="delete_application_tracker_entry")
def delete_application_tracker_entry_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        entry_id: int
) -> RedirectResponse:
    """Delete one tracker entry.

    :param request: Incoming HTTP request.
    :param entry_id: Identifier of the tracker entry to delete.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Redirect response to the tracker overview page.
    """
    was_deleted = remove_application_tracker_entry(
        db,
        entry_id=entry_id,
        user_id=current_user.id
    )

    message = "Tracker-Eintrag erfolgreich gelöscht."
    message_type = "success"
    if not was_deleted:
        message = "Tracker-Eintrag nicht gefunden."
        message_type = "error"

    tracker_url = str(request.url_for("render_application_tracker_page"))
    query_string = build_feedback_query(
        message=message,
        message_type=message_type
    )
    return RedirectResponse(
        url=f"{tracker_url}?{query_string}",
        status_code=303
    )
