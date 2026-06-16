"""Define browser routes for the candidate profile feature.

Render the read-only profile overview and the edit profile page, and handle
saving all profile fields in a single bulk form submission.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.enums import DocumentProcessingStatus, DocumentType
from app.crud.document import get_document_by_type_for_user
from app.crud.profile_information import get_profile_for_user, upsert_profile
from app.models.profile_information import ProfileInformation
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.templates import build_feedback_query, get_base_template_context
from app.models.user import User
from app.services.document_service import retry_profile_extraction

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profil", tags=["profile"])
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Form parsing helpers
# ---------------------------------------------------------------------------

def _split_lines(text: str) -> list[str]:
    """Split a newline-separated string into a list of non-blank lines.

    :param text: Raw textarea value.
    :return: List of stripped, non-empty strings.
    """
    return [line.strip() for line in text.splitlines() if line.strip()]


def _parse_indexed_list(
    form,
    prefix: str,
    *,
    anchor: str,
    string_fields: tuple[str, ...] = (),
    list_fields: tuple[str, ...] = (),
    has_period: bool = False,
) -> list[dict]:
    """Reconstruct a list of dicts from flat indexed form fields.

    Iterates from index 0, stopping when the anchor field for that index is
    absent from the form. Relies on the client JS to keep indices contiguous
    after add/delete operations.

    :param form: Raw Starlette FormData.
    :param prefix: Field name prefix, e.g. ``work_experience``.
    :param anchor: Subfield name used to detect whether an index exists.
    :param string_fields: Subfield names stored as plain strings.
    :param list_fields: Subfield names stored as newline-separated text → list.
    :param has_period: When True, read ``{prefix}_{i}_period_start`` and
        ``{prefix}_{i}_period_end`` and nest them under a ``"period"`` key.
    :return: List of entry dicts.
    """
    entries = []
    i = 0
    while f"{prefix}_{i}_{anchor}" in form:
        entry: dict = {}
        for field in string_fields:
            entry[field] = form.get(f"{prefix}_{i}_{field}", "").strip()
        for field in list_fields:
            raw = form.get(f"{prefix}_{i}_{field}", "")
            entry[field] = _split_lines(raw)
        if has_period:
            entry["period"] = {
                "start": form.get(f"{prefix}_{i}_period_start", "").strip(),
                "end": form.get(f"{prefix}_{i}_period_end", "").strip(),
            }
        entries.append(entry)
        i += 1
    return entries


def _parse_profile_form(form) -> dict:
    """Parse all profile edit form fields from raw Starlette FormData.

    :param form: Raw FormData from ``await request.form()``.
    :return: Dict suitable for passing to ``upsert_profile``.
    """
    return {
        # Simple string fields
        "first_name": form.get("first_name", "").strip(),
        "last_name": form.get("last_name", "").strip(),
        "email": form.get("email", "").strip(),
        "phone": form.get("phone", "").strip(),
        "street": form.get("street", "").strip(),
        "city": form.get("city", "").strip(),
        "location": form.get("location", "").strip(),
        "target_role": form.get("target_role", "").strip(),
        "seniority_level": form.get("seniority_level", "").strip(),
        "leadership_experience": form.get("leadership_experience", "").strip(),
        "salary_expectation": form.get("salary_expectation", "").strip(),
        "work_model": form.get("work_model", "").strip(),
        "availability": form.get("availability", "").strip(),
        # Simple list fields (newline-separated textarea)
        "employment_types": _split_lines(form.get("employment_types", "")),
        "soft_skills": _split_lines(form.get("soft_skills", "")),
        # Complex list fields (card-based, flat indexed form fields)
        "work_experience": _parse_indexed_list(
            form, "work_experience",
            anchor="company",
            string_fields=("company", "position"),
            list_fields=("responsibilities", "achievements", "skills"),
            has_period=True,
        ),
        "education": _parse_indexed_list(
            form, "education",
            anchor="institution",
            string_fields=("institution", "degree", "grade"),
            list_fields=("coursework",),
            has_period=True,
        ),
        "certifications": _parse_indexed_list(
            form, "certifications",
            anchor="name",
            string_fields=("name", "issuer", "issue_date"),
            list_fields=("skills",),
        ),
        "projects": _parse_indexed_list(
            form, "projects",
            anchor="name",
            string_fields=("name", "period", "description", "outcome"),
            list_fields=("technologies",),
        ),
        "hard_skills": _parse_indexed_list(
            form, "hard_skills",
            anchor="skill",
            string_fields=("skill", "proficiency", "years_experience", "evidence"),
        ),
        "languages": _parse_indexed_list(
            form, "languages",
            anchor="language",
            string_fields=("language", "level"),
        ),
        "volunteering": _parse_indexed_list(
            form, "volunteering",
            anchor="role",
            string_fields=("role", "organization", "cause", "description"),
            list_fields=("skills",),
            has_period=True,
        ),
        "publications": _parse_indexed_list(
            form, "publications",
            anchor="title",
            string_fields=("title", "publisher", "date", "description"),
            list_fields=("topics",),
        ),
        "honors_awards": _parse_indexed_list(
            form, "honors_awards",
            anchor="title",
            string_fields=("title", "issuer", "date", "description"),
        ),
        "courses": _parse_indexed_list(
            form, "courses",
            anchor="name",
            string_fields=("name", "provider"),
            list_fields=("skills",),
            has_period=True,
        ),
        "extraction_error": None,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _profile_has_content(profile: ProfileInformation | None) -> bool:
    """Return True when the profile row has been meaningfully populated.

    An empty profile row (all fields None, no extraction error) created by
    the edit form clearing all fields is treated as having no content so the
    UI shows the correct empty state rather than a blank content block.

    :param profile: ProfileInformation ORM instance or None.
    :return: True if the profile has extractable data or an extraction error.
    """
    if profile is None:
        return False
    return bool(
        profile.extraction_error is not None
        or profile.first_name or profile.last_name or profile.target_role
        or profile.work_experience or profile.education
        or profile.hard_skills or profile.soft_skills
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse, name="render_profile_page")
def render_profile_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    """Render the read-only candidate profile overview page.

    Clears the post-upload redirect session flag so the auto-redirect only
    fires once per upload cycle.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Rendered profile overview page.
    """
    request.session.pop("redirect_to_profile", None)
    profile = get_profile_for_user(db, user_id=current_user.id)
    profile_has_content = _profile_has_content(profile)

    show_ai_warning = False
    extraction_in_progress = request.session.get("profile_extraction_in_progress", False)
    if extraction_in_progress:
        if profile is not None:
            request.session.pop("profile_extraction_in_progress", None)
            extraction_in_progress = False
            if not profile.extraction_error:
                show_ai_warning = True
    else:
        request.session.pop("profile_extraction_in_progress", None)

    has_completed_cv = False
    if not profile_has_content and not extraction_in_progress:
        cv_doc = get_document_by_type_for_user(
            db, user_id=current_user.id, document_type=DocumentType.CV
        )
        has_completed_cv = (
            cv_doc is not None
            and cv_doc.processing_status == DocumentProcessingStatus.COMPLETED
        )

    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user,
            "profile": profile,
            "profile_has_content": profile_has_content,
            "extraction_in_progress": extraction_in_progress,
            "show_ai_warning": show_ai_warning,
            "has_completed_cv": has_completed_cv,
            "has_signature": bool(profile and profile.signature_image),
        },
    )


@router.get("/bearbeiten", response_class=HTMLResponse, name="render_profile_edit_page")
def render_profile_edit_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    """Render the profile edit page with all fields pre-filled from the database.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Rendered profile edit page.
    """
    profile = get_profile_for_user(db, user_id=current_user.id)

    return templates.TemplateResponse(
        request=request,
        name="profile_edit.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user,
            "profile": profile,
        },
    )


@router.post("/bearbeiten", name="save_profile_route")
async def save_profile_route(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RedirectResponse:
    """Save all profile fields from the edit form in a single bulk update.

    Reads raw form data to handle flat indexed fields for card-based list
    sections (work experience, education, etc.). Simple string fields and
    newline-separated list fields are also parsed from the form body.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Redirect to the profile overview page.
    """
    profil_url = str(request.url_for("render_profile_page"))

    form = await request.form()
    data = _parse_profile_form(form)

    upsert_profile(db, user_id=current_user.id, data=data)
    db.commit()

    query_string = build_feedback_query(message="Profil gespeichert.", message_type="success")
    return RedirectResponse(url=f"{profil_url}?{query_string}", status_code=303)


@router.post("/fields", name="update_profile_fields_action")
async def update_profile_fields_action(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse:
    """Update a subset of profile contact fields from a JSON body.

    Accepts a JSON object mapping field names to new string values. Only the
    explicitly allowed contact fields are written; all other keys are ignored.

    :param request: Incoming HTTP request (JSON body ``{field_name: value}``).
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: JSON ``{"ok": true}`` on success.
    """
    _ALLOWED_FIELDS = frozenset(
        {"first_name", "last_name", "email", "phone", "street", "city", "location"}
    )
    body: dict = await request.json()
    updates = {k: str(v).strip() for k, v in body.items() if k in _ALLOWED_FIELDS}
    if updates:
        profile = get_profile_for_user(db, user_id=current_user.id)
        if profile is None:
            upsert_profile(db, user_id=current_user.id, data=updates)
        else:
            for field, value in updates.items():
                setattr(profile, field, value or None)
            db.add(profile)
        db.commit()
    return JSONResponse({"ok": True})


@router.post("/signatur", name="upload_profile_signature_action")
async def upload_profile_signature_action(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RedirectResponse:
    """Accept a signature image, process it into a transparent PNG, and store it on the profile.

    Validates MIME type (image/png or image/jpeg only) and size (≤ 300 KB).
    Runs SignatureProcessor to remove the background, crop to the ink bounding
    box, and produce a transparent PNG. Stores the result as a base64 data URL
    in ``profile_information.signature_image`` so it persists across all cover
    letters.

    :param request: Incoming HTTP request with multipart form data.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :return: Redirect to the documents page with a feedback message.
    """
    import base64

    from app.services.signature_processor import SignatureProcessor

    documents_url = str(request.url_for("render_documents_page"))

    form = await request.form()

    # Optional return URL supplied by the caller (e.g. the cover letter editor).
    next_url = str(form.get("next") or "").strip()

    file: UploadFile | None = form.get("file")  # type: ignore[assignment]
    if file is None or not hasattr(file, "read"):
        query_string = build_feedback_query(message="Keine Datei empfangen.", message_type="error")
        target = next_url or documents_url
        return RedirectResponse(url=f"{target}?{query_string}", status_code=303)

    content_type = file.content_type or ""
    if content_type not in ("image/png", "image/jpeg"):
        query_string = build_feedback_query(
            message="Ungültiger Dateityp. Bitte PNG oder JPEG hochladen.",
            message_type="error",
        )
        target = next_url or documents_url
        return RedirectResponse(url=f"{target}?{query_string}", status_code=303)

    image_bytes = await file.read()
    if len(image_bytes) > 300 * 1024:
        query_string = build_feedback_query(
            message="Datei zu groß. Maximal 300 KB erlaubt.",
            message_type="error",
        )
        target = next_url or documents_url
        return RedirectResponse(url=f"{target}?{query_string}", status_code=303)

    try:
        png_bytes = SignatureProcessor.process(image_bytes, content_type)
    except ValueError as exc:
        query_string = build_feedback_query(message=str(exc), message_type="error")
        target = next_url or documents_url
        return RedirectResponse(url=f"{target}?{query_string}", status_code=303)

    data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode()

    profile = get_profile_for_user(db, user_id=current_user.id)
    if profile is None:
        upsert_profile(db, user_id=current_user.id, data={"signature_image": data_url})
    else:
        profile.signature_image = data_url
        db.add(profile)
    db.commit()

    query_string = build_feedback_query(
        message="Signatur erfolgreich hochgeladen.", message_type="success"
    )
    target = next_url or documents_url
    return RedirectResponse(url=f"{target}?{query_string}", status_code=303)


@router.post("/extrahieren", name="retry_profile_extraction_route")
def retry_profile_extraction_route(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> RedirectResponse:
    """Delete the existing profile and re-enqueue LLM extraction from the CV text.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param background_tasks: FastAPI background task queue.
    :return: Redirect to the profile overview page with a feedback message.
    """
    profil_url = str(request.url_for("render_profile_page"))
    enqueued = retry_profile_extraction(
        db, background_tasks=background_tasks, user_id=current_user.id
    )
    if enqueued:
        request.session["profile_extraction_in_progress"] = True
        query_string = build_feedback_query(
            message="Profilerstellung wird erneut gestartet…", message_type="success"
        )
    else:
        query_string = build_feedback_query(
            message="Kein abgeschlossener Lebenslauf gefunden. Bitte lade zuerst einen Lebenslauf hoch.",
            message_type="error",
        )
    return RedirectResponse(url=f"{profil_url}?{query_string}", status_code=303)
