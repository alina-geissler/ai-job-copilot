"""Define browser routes for the application tracker.

Render the tracker overview and detail pages and handle all browser-based
actions for creating, updating, and deleting tracker entries.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.enums import ApplicationStatus
from app.crud.application_tracker_entry import (
    get_tracker_entry_by_id_for_user,
    list_tracker_entries_for_user,
)
from app.crud.cover_letter import get_completed_drafts_for_user, get_saved_cover_letters_for_user
from app.crud.job_normalization import (
    get_normalization_by_job_id,
    get_normalization_by_manual_job_id,
    get_normalizations_for_job_ids,
)
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.templates import build_feedback_query, get_base_template_context
from app.models.job import Job
from app.models.user import User
from app.schemas.application_tracker import TrackerNotesUpdateForm, TrackerStatusClearDateForm, TrackerStatusUpdateForm
from app.services.application_tracker_service import (
    change_application_tracker_notes,
    change_application_tracker_status,
    clear_application_tracker_status_date,
    create_application_tracker_entry,
    create_manual_application_tracker_entry,
    remove_application_tracker_entry,
    update_job_title_company_for_tracker_entry,
)
from app.services.job_normalization_task import NORM_ERRORS, norm_task_key, run_normalization_task
from app.utils.application_tracker_ui import (
    TRACKER_STATUS_CLASSES,
    TRACKER_STATUS_DATE_FIELDS,
    TRACKER_STATUS_LABELS,
    TRACKER_STATUS_ORDER
)

router = APIRouter(prefix="/tracker", tags=["application-tracker"])
templates = Jinja2Templates(directory="templates")


def _resolve_redirect_url(
        request: Request,
        *,
        redirect_to: str,
        entry_id: int | None,
        query_string: str,
) -> str:
    """Return the redirect URL for the given target and query string.

    :param request: Incoming HTTP request.
    :param redirect_to: Redirect target identifier, e.g. ``overview`` or ``detail``.
    :param entry_id: Identifier of the tracker entry; required when redirecting to detail.
    :param query_string: Pre-built feedback query string to append.
    :return: Absolute redirect URL with query string.
    """
    if redirect_to == "detail" and entry_id is not None:
        detail_url = str(request.url_for("render_application_tracker_detail_page", entry_id=entry_id))
        return f"{detail_url}?{query_string}"
    tracker_url = str(request.url_for("render_application_tracker_page"))
    return f"{tracker_url}?{query_string}"


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
            default_date = entry.created_at.date().isoformat()
            shows_date = True
            opens_date_form = True
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
        "job_id": entry.job_id,
        "manual_job_posting_id": entry.manual_job_posting_id,
        "manual_job_posting": entry.manual_job_posting if hasattr(entry, "manual_job_posting") else None,
        "status": entry.status,
        "status_label": TRACKER_STATUS_LABELS[entry.status],
        "status_css_class": TRACKER_STATUS_CLASSES[entry.status],
        "status_items": _build_tracker_status_items(entry),
        "notes": entry.notes or "",
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "job": entry.job,
    }


def _build_tracker_overview_context(
        request: Request,
        *,
        current_user: User,
        tracker_entries: list[Any],
        jobs_with_cover_letters: set[int],
        jobs_with_normalizations: set[int],
) -> dict[str, Any]:
    """Build the template context for the tracker overview page.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param tracker_entries: Tracker entries visible to the user.
    :param jobs_with_cover_letters: Set of job IDs that have at least one cover letter.
    :param jobs_with_normalizations: Set of job IDs that have a normalisation record.
    :return: Template context for the tracker overview page.
    """
    return {
        **get_base_template_context(request),
        "current_user": current_user,
        "tracker_entries": [_serialize_tracker_entry(entry) for entry in tracker_entries],
        "jobs_with_cover_letters": jobs_with_cover_letters,
        "jobs_with_normalizations": jobs_with_normalizations,
    }


def _build_tracker_detail_context(
        request: Request,
        *,
        current_user: User,
        tracker_entry: Any,
        normalization: Any = None,
        cover_letters: list[Any] | None = None,
        norm_expanded: bool = False,
        auto_analyse: bool = False,
) -> dict[str, Any]:
    """Build the template context for one tracker detail page.

    When normalization data is available and the Job record lacks location,
    employment_type, or remote information (as is the case for manually added
    jobs), resolved fallback values are passed to the template.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param tracker_entry: Tracker entry to display.
    :param normalization: Optional JobNormalization ORM object for the entry's job.
    :param cover_letters: Cover letters associated with the entry's job.
    :param norm_expanded: When ``True`` the normalisation section opens and scrolls into view.
    :param auto_analyse: When ``True`` the analyse spinner is shown immediately (task
        was started by a non-HTMX POST from the overview page).
    :return: Template context for the tracker detail page.
    """
    norm_data = normalization.normalized_data if normalization is not None else None
    effective_norm_expanded = norm_expanded or (auto_analyse and norm_data is not None)

    # Resolve location, employment type, and work model from normalization when
    # the job record's own fields are blank (typical for manually added jobs).
    norm_location: str | None = None
    norm_employment_type: str | None = None
    norm_work_model: str | None = None
    norm_job_url: str | None = None
    if norm_data:
        norm_location = norm_data.get("job_location") or None
        norm_employment_type = norm_data.get("employment_type") or None
        norm_work_model = norm_data.get("work_model") or None
    if norm_data and tracker_entry.manual_job_posting and tracker_entry.manual_job_posting.job_url:
        norm_job_url = tracker_entry.manual_job_posting.job_url

    return {
        **get_base_template_context(request),
        "current_user": current_user,
        "tracker_entry": _serialize_tracker_entry(tracker_entry),
        "normalization": norm_data,
        "cover_letters": cover_letters or [],
        "norm_expanded": effective_norm_expanded,
        "auto_analyse": auto_analyse and norm_data is None,
        "norm_location": norm_location,
        "norm_employment_type": norm_employment_type,
        "norm_work_model": norm_work_model,
        "norm_job_url": norm_job_url,
    }


_VALID_SORT_VALUES = {"newest", "oldest", "name_az"}
_VALID_STATUS_FILTERS = {s.value for s in ApplicationStatus} | {"active", "has_cover_letter"}


@router.get("", response_class=HTMLResponse, name="render_application_tracker_page")
def render_application_tracker_page(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        sort: Annotated[str, Query()] = "newest",
        filter: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    """Render the application tracker overview page.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param sort: Sort order — ``"newest"`` (default), ``"oldest"``, ``"name_az"``.
    :param filter: Optional status filter or special value ``"active"`` /
        ``"has_cover_letter"``.
    :return: Rendered tracker overview page.
    """
    safe_sort = sort if sort in _VALID_SORT_VALUES else "newest"
    safe_filter = filter if filter in _VALID_STATUS_FILTERS else None

    all_cls = (
        get_saved_cover_letters_for_user(db, user_id=current_user.id)
        + get_completed_drafts_for_user(db, user_id=current_user.id)
    )
    jobs_with_cover_letters = {cl.job_id for cl in all_cls if cl.job_id is not None}

    tracker_entries = list_tracker_entries_for_user(
        db,
        user_id=current_user.id,
        sort=safe_sort,
        status_filter=safe_filter,
        jobs_with_cover_letters=jobs_with_cover_letters if safe_filter == "has_cover_letter" else None,
    )

    job_ids = [e.job_id for e in tracker_entries if e.job_id is not None]
    jobs_with_normalizations = set(get_normalizations_for_job_ids(db, job_ids=job_ids).keys())

    return templates.TemplateResponse(
        request=request,
        name="tracker.html",
        context={
            **_build_tracker_overview_context(
                request,
                current_user=current_user,
                tracker_entries=tracker_entries,
                jobs_with_cover_letters=jobs_with_cover_letters,
                jobs_with_normalizations=jobs_with_normalizations,
            ),
            "current_sort": safe_sort,
            "current_filter": safe_filter,
        },
    )


@router.get("/add-manual", response_class=HTMLResponse, name="render_add_manual_tracker_page")
def render_add_manual_tracker_page(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
) -> HTMLResponse:
    """Render the form for adding a job advertisement manually to the tracker.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :return: Rendered add-manual form page.
    """
    return templates.TemplateResponse(
        request=request,
        name="tracker_add_manual.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user,
        },
    )


@router.post("/add-manual", response_class=HTMLResponse, name="add_manual_tracker_entry_action")
async def add_manual_tracker_entry_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        raw_text: Annotated[str, Form()],
        title: Annotated[str, Form()] = "",
        company: Annotated[str, Form()] = "",
        job_url: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Create a manual job posting and tracker entry from the add-manual form.

    Normalisation is NOT triggered automatically; the user may trigger it later
    via the "Analysieren" button in the tracker.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param raw_text: Full pasted job advertisement text.
    :param title: Optional user-supplied job title.
    :param company: Optional user-supplied company name.
    :param job_url: Optional URL to the original job advertisement.
    :return: Redirect to the new tracker entry's detail page.
    """
    if not raw_text.strip():
        query_string = build_feedback_query(
            message="Bitte füge eine Stellenanzeige ein.",
            message_type="error",
        )
        add_url = str(request.url_for("render_add_manual_tracker_page"))
        return RedirectResponse(url=f"{add_url}?{query_string}", status_code=303)

    try:
        entry = create_manual_application_tracker_entry(
            db,
            user_id=current_user.id,
            raw_text=raw_text.strip(),
            title=title.strip() or None,
            company=company.strip() or None,
            job_url=job_url.strip() or None,
        )
    except Exception:
        query_string = build_feedback_query(
            message="Fehler beim Speichern. Bitte versuche es erneut.",
            message_type="error",
        )
        tracker_url = str(request.url_for("render_application_tracker_page"))
        return RedirectResponse(url=f"{tracker_url}?{query_string}", status_code=303)

    query_string = build_feedback_query(
        message="Stellenanzeige erfolgreich zum Tracker hinzugefügt.",
        message_type="success",
    )
    detail_url = str(request.url_for("render_application_tracker_detail_page", entry_id=entry.id))
    return RedirectResponse(url=f"{detail_url}?{query_string}", status_code=303)


@router.get("/{entry_id}", response_class=HTMLResponse, name="render_application_tracker_detail_page")
def render_application_tracker_detail_page(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        entry_id: int,
        norm_expanded: Annotated[bool, Query()] = False,
        auto_analyse: Annotated[bool, Query()] = False,
) -> Response:
    """Render the detail page of one tracker entry.

    :param request: Incoming HTTP request.
    :param entry_id: Identifier of the tracker entry to display.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param norm_expanded: When ``True`` expand the normalisation section on load.
    :param auto_analyse: When ``True`` the task was started from the overview;
        show spinner immediately and poll for completion.
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

    normalization = None
    cover_letters: list[Any] = []
    if tracker_entry.job_id is not None:
        if tracker_entry.manual_job_posting_id is not None:
            normalization = get_normalization_by_manual_job_id(
                db, manual_job_posting_id=tracker_entry.manual_job_posting_id
            )
        if normalization is None:
            normalization = get_normalization_by_job_id(db, job_id=tracker_entry.job_id)
        cover_letters = (
            get_saved_cover_letters_for_user(db, user_id=current_user.id, job_id=tracker_entry.job_id)
            + get_completed_drafts_for_user(db, user_id=current_user.id, job_id=tracker_entry.job_id)
        )

    return templates.TemplateResponse(
        request=request,
        name="tracker_detail.html",
        context=_build_tracker_detail_context(
            request,
            current_user=current_user,
            tracker_entry=tracker_entry,
            normalization=normalization,
            cover_letters=cover_letters,
            norm_expanded=norm_expanded,
            auto_analyse=auto_analyse,
        )
    )


@router.post("/{entry_id}/edit-job", response_class=HTMLResponse, name="edit_tracker_job_action")
def edit_tracker_job_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        entry_id: int,
        title: Annotated[str, Form()] = "",
        company: Annotated[str, Form()] = "",
        job_url: Annotated[str, Form()] = "",
        redirect_to: Annotated[str, Form()] = "detail",
) -> RedirectResponse:
    """Update the title, company, and URL of a manually added tracker job.

    Only permitted for jobs with ``source="manual"``. Silently ignores empty
    values (leaves the existing value unchanged).

    :param request: Incoming HTTP request.
    :param entry_id: Identifier of the tracker entry to update.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param title: New job title, or empty string to leave unchanged.
    :param company: New company name, or empty string to leave unchanged.
    :param job_url: New job advertisement URL, or empty string to leave unchanged.
    :param redirect_to: Redirect target — ``"detail"`` or ``"overview"``.
    :return: Redirect response.
    """
    updated = update_job_title_company_for_tracker_entry(
        db,
        entry_id=entry_id,
        user_id=current_user.id,
        title=title.strip() or None,
        company=company.strip() or None,
        job_url=job_url.strip() or None,
    )

    if updated is None:
        query_string = build_feedback_query(
            message="Eintrag nicht gefunden oder Bearbeitung nicht erlaubt.",
            message_type="error",
        )
    else:
        query_string = build_feedback_query(
            message="Stelle und Unternehmen aktualisiert.",
            message_type="success",
        )

    return RedirectResponse(
        url=_resolve_redirect_url(request, redirect_to=redirect_to, entry_id=entry_id, query_string=query_string),
        status_code=303,
    )


@router.post("/jobs/{job_id}", response_class=HTMLResponse, name="create_application_tracker_entry_action")
def create_application_tracker_entry_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        job_id: int,
        redirect_to_url: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Create a tracker entry for one job if it is not already tracked.

    If ``redirect_to_url`` is a relative path supplied by the originating page
    (e.g. the search-results page), redirect back there so the user stays in
    context rather than landing on the tracker overview.

    :param request: Incoming HTTP request.
    :param job_id: Identifier of the job to add to the tracker.
    :param redirect_to_url: Optional relative URL to redirect to after creation.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Redirect response.
    """
    _, created = create_application_tracker_entry(
        db,
        user_id=current_user.id,
        job_id=job_id
    )

    message_type = "success"
    if created:
        job = db.get(Job, job_id)
        job_title = job.title if job else "Job"
        message = f"{job_title} erfolgreich zum Bewerbungs-Tracker zugefügt."
    else:
        message = "Dieser Job ist bereits im Bewerbungstracker gespeichert."
        message_type = "info"

    query_string = build_feedback_query(message=message, message_type=message_type)

    if redirect_to_url and redirect_to_url.startswith("/"):
        separator = "&" if "?" in redirect_to_url else "?"
        return RedirectResponse(url=f"{redirect_to_url}{separator}{query_string}", status_code=303)

    tracker_url = str(request.url_for("render_application_tracker_page"))
    return RedirectResponse(url=f"{tracker_url}?{query_string}", status_code=303)


@router.post("/{entry_id}/status", response_class=HTMLResponse, name="update_application_tracker_status_action")
def update_application_tracker_status_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        entry_id: int,
        form_data: Annotated[TrackerStatusUpdateForm, Form()]
) -> RedirectResponse:
    """Update the current status of one tracker entry.

    :param request: Incoming HTTP request.
    :param entry_id: Identifier of the tracker entry to update.
    :param form_data: Validated status update form data.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Redirect response to the overview or detail page.
    """
    tracker_entry = change_application_tracker_status(
        db,
        entry_id=entry_id,
        user_id=current_user.id,
        status=form_data.status,
        status_date=form_data.status_date
    )

    if tracker_entry is None:
        query_string = build_feedback_query(
            message="Tracker-Eintrag nicht gefunden.",
            message_type="error"
        )
        return RedirectResponse(
            url=_resolve_redirect_url(request, redirect_to="overview", entry_id=None, query_string=query_string),
            status_code=303
        )

    query_string = build_feedback_query(
        message="Status erfolgreich aktualisiert.",
        message_type="success"
    )
    return RedirectResponse(
        url=_resolve_redirect_url(
            request, redirect_to=form_data.redirect_to, entry_id=entry_id, query_string=query_string
        ),
        status_code=303
    )


@router.post("/{entry_id}/notes", response_class=HTMLResponse, name="update_application_tracker_notes_action")
def update_application_tracker_notes_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        entry_id: int,
        form_data: Annotated[TrackerNotesUpdateForm, Form()]
) -> RedirectResponse:
    """Update the notes of one tracker entry.

    :param request: Incoming HTTP request.
    :param entry_id: Identifier of the tracker entry to update.
    :param form_data: Validated notes update form data.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Redirect response to the overview or detail page.
    """
    tracker_entry = change_application_tracker_notes(
        db,
        entry_id=entry_id,
        user_id=current_user.id,
        notes=form_data.notes
    )

    if tracker_entry is None:
        query_string = build_feedback_query(
            message="Tracker-Eintrag nicht gefunden.",
            message_type="error"
        )
        return RedirectResponse(
            url=_resolve_redirect_url(request, redirect_to="overview", entry_id=None, query_string=query_string),
            status_code=303
        )

    query_string = build_feedback_query(
        message="Notizen erfolgreich gespeichert.",
        message_type="success"
    )
    return RedirectResponse(
        url=_resolve_redirect_url(
            request, redirect_to=form_data.redirect_to, entry_id=entry_id, query_string=query_string
        ),
        status_code=303
    )


@router.post("/{entry_id}/delete", response_class=HTMLResponse, name="delete_application_tracker_entry_action")
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


@router.post("/{entry_id}/status/clear-date", response_class=HTMLResponse, name="clear_application_tracker_status_date_action")
def clear_application_tracker_status_date_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        entry_id: int,
        form_data: Annotated[TrackerStatusClearDateForm, Form()]
) -> RedirectResponse:
    """Clear the date field for a given status on one tracker entry.

    Does not change the entry's current status, only removes the associated
    timestamp so the status segment no longer shows a date.

    :param request: Incoming HTTP request.
    :param entry_id: Identifier of the tracker entry to update.
    :param form_data: Validated clear-date form data.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Redirect response to the detail page.
    """
    tracker_entry = clear_application_tracker_status_date(
        db,
        entry_id=entry_id,
        user_id=current_user.id,
        status=form_data.status,
    )

    if tracker_entry is None:
        query_string = build_feedback_query(
            message="Tracker-Eintrag nicht gefunden.",
            message_type="error"
        )
        return RedirectResponse(
            url=_resolve_redirect_url(request, redirect_to="overview", entry_id=None, query_string=query_string),
            status_code=303
        )

    query_string = build_feedback_query(
        message="Datum erfolgreich gelöscht.",
        message_type="success"
    )
    return RedirectResponse(
        url=_resolve_redirect_url(
            request, redirect_to=form_data.redirect_to, entry_id=entry_id, query_string=query_string
        ),
        status_code=303
    )


@router.post("/{entry_id}/analyse", response_class=HTMLResponse, name="analyse_tracker_job_action")
def analyse_tracker_job_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        background_tasks: BackgroundTasks,
        entry_id: int,
) -> Response:
    """Trigger job normalisation for one tracker entry.

    If normalisation already exists, redirects immediately to the detail page
    with the normalisation section expanded. Otherwise enqueues a background
    normalisation task and returns a spinner partial with HTMX polling.

    :param request: Incoming HTTP request.
    :param entry_id: Identifier of the tracker entry to analyse.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param background_tasks: FastAPI background task queue.
    :return: Spinner partial or redirect response.
    """
    tracker_entry = get_tracker_entry_by_id_for_user(
        db, entry_id=entry_id, user_id=current_user.id
    )
    if tracker_entry is None:
        query_string = build_feedback_query(
            message="Tracker-Eintrag nicht gefunden.",
            message_type="error"
        )
        err_tracker_url = str(request.url_for("render_application_tracker_page"))
        response = HTMLResponse(content="")
        response.headers["HX-Redirect"] = f"{err_tracker_url}?{query_string}"
        return response

    is_htmx = request.headers.get("HX-Request") == "true"
    detail_url = str(request.url_for("render_application_tracker_detail_page", entry_id=entry_id))

    job_id = tracker_entry.job_id
    manual_job_id = tracker_entry.manual_job_posting_id

    # Prefer normalization via manual job posting for manually added jobs.
    existing_norm = None
    if manual_job_id is not None:
        existing_norm = get_normalization_by_manual_job_id(db, manual_job_posting_id=manual_job_id)
    if existing_norm is None and job_id is not None:
        existing_norm = get_normalization_by_job_id(db, job_id=job_id)

    if existing_norm is not None:
        if is_htmx:
            response = HTMLResponse(content="")
            response.headers["HX-Redirect"] = f"{detail_url}?norm_expanded=1"
            return response
        return RedirectResponse(url=f"{detail_url}?norm_expanded=1", status_code=303)

    task_job_id = None if manual_job_id is not None else job_id
    task_manual_id = manual_job_id
    NORM_ERRORS.pop(norm_task_key(task_job_id, task_manual_id), None)
    background_tasks.add_task(run_normalization_task, job_id=task_job_id, manual_job_id=task_manual_id)

    if not is_htmx:
        return RedirectResponse(url=f"{detail_url}?auto_analyse=1", status_code=303)

    status_url = str(request.url_for("tracker_analyse_status", entry_id=entry_id))
    return templates.TemplateResponse(
        request=request,
        name="_tracker_analyse_spinner.html",
        context={"entry_id": entry_id, "status_url": status_url},
    )


@router.get("/{entry_id}/analyse/status", response_class=HTMLResponse, name="tracker_analyse_status")
def tracker_analyse_status_route(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
        entry_id: int,
) -> Response:
    """HTMX polling endpoint: check normalisation progress for a tracker entry.

    Returns the spinner partial while the background task is still running.
    Sets ``HX-Redirect`` to the tracker detail page with ``norm_expanded=1``
    when normalisation completes. Returns an error snippet on failure.

    :param request: Incoming HTTP request.
    :param entry_id: Identifier of the tracker entry being analysed.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Spinner partial, error HTML, or redirect response.
    """
    tracker_entry = get_tracker_entry_by_id_for_user(
        db, entry_id=entry_id, user_id=current_user.id
    )
    if tracker_entry is None:
        return HTMLResponse(content='<p class="text-sm text-red-600">Tracker-Eintrag nicht gefunden.</p>')

    job_id = tracker_entry.job_id
    manual_job_id = tracker_entry.manual_job_posting_id
    task_job_id = None if manual_job_id is not None else job_id
    key = norm_task_key(task_job_id, manual_job_id)

    if key in NORM_ERRORS:
        error_msg = NORM_ERRORS.pop(key)
        return HTMLResponse(content=f'<p class="text-sm text-red-600">Fehler bei der Analyse: {error_msg}</p>')

    existing_norm = None
    if manual_job_id is not None:
        existing_norm = get_normalization_by_manual_job_id(db, manual_job_posting_id=manual_job_id)
    if existing_norm is None and job_id is not None:
        existing_norm = get_normalization_by_job_id(db, job_id=job_id)

    if existing_norm is not None:
        detail_url = str(request.url_for("render_application_tracker_detail_page", entry_id=entry_id))
        response = HTMLResponse(content="")
        response.headers["HX-Redirect"] = f"{detail_url}?norm_expanded=1"
        return response

    status_url = str(request.url_for("tracker_analyse_status", entry_id=entry_id))
    return templates.TemplateResponse(
        request=request,
        name="_tracker_analyse_spinner.html",
        context={"entry_id": entry_id, "status_url": status_url},
    )
