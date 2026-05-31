"""Define browser routes for the cover letter generator feature.

Handle the Single Job Analysis landing page, the generator setup page,
the generation spinner page, the cover letter editor, and the HTMX preview
endpoint used for live template and design switching.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.enums import CoverLetterGenerationStatus, CoverLetterTemplate, CoverLetterTone
from app.crud.application_tracker_entry import get_tracker_entry_by_id_for_user
from app.crud.cover_letter import (
    delete_cover_letter,
    get_cover_letter_by_id,
    save_cover_letter_document,
)
from app.crud.job_normalization import get_normalization_by_job_id
from app.crud.manual_job_posting import create_manual_job_posting, get_manual_job_posting_by_id
from app.crud.profile_information import get_profile_for_user
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.templates import build_feedback_query, get_base_template_context
from app.models.job import Job
from app.models.user import User
from app.schemas.cover_letter import CoverLetterContent, LayoutSettings
from app.schemas.job_normalization import JobNormalizationSchema
from app.services.cover_letter_service import initiate_cover_letter_generation

logger = logging.getLogger(__name__)
router = APIRouter(tags=["cover-letter"])
templates = Jinja2Templates(directory="templates")

_SETUP_PARAMS_SESSION_KEY = "cover_letter_setup_params"

# ---------------------------------------------------------------------------
# Allowed preset values (validated before persisting layout_settings)
# ---------------------------------------------------------------------------

_ALLOWED_THEMES = {"theme-blue", "theme-green", "theme-grey"}
_ALLOWED_FONTS = {"font-arial", "font-verdana", "font-georgia", "font-times-new-roman"}
_ALLOWED_SIZES = {"size-small", "size-medium", "size-large"}
_ALLOWED_SPACINGS = {"spacing-normal", "spacing-large"}
_ALLOWED_RECIPIENT_POS = {"standard", "high"}
_ALLOWED_SIGNATURE_SPACE = {"standard", "compact"}
_ALLOWED_COMPACT_ATTACHMENTS_POS = {"standard", "higher", "very-high"}

# ---------------------------------------------------------------------------
# Template and tone label helpers
# ---------------------------------------------------------------------------

_TEMPLATE_LABELS: dict[CoverLetterTemplate, str] = {
    CoverLetterTemplate.CLASSIC: "Klassisch",
    CoverLetterTemplate.MODERN: "Modern",
    CoverLetterTemplate.COMPACT: "Kompakt (besonders gut geeignet für ausführliche, längere Texte)",
}

_TONE_LABELS: dict[CoverLetterTone, str] = {
    CoverLetterTone.FORMAL: "Formell",
    CoverLetterTone.NEUTRAL: "Neutral",
    CoverLetterTone.CASUAL: "Locker",
}


# ---------------------------------------------------------------------------
# Single Job Analysis — landing / hub page
# ---------------------------------------------------------------------------

@router.get("/single-job-analysis", response_class=HTMLResponse, name="render_single_job_analysis_page")
def render_single_job_analysis_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> HTMLResponse:
    """Render the Single Job Analysis hub page.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :return: Rendered single job analysis page.
    """
    return templates.TemplateResponse(
        request=request,
        name="single_job_analysis.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user,
        },
    )


@router.post("/single-job-analysis", response_class=HTMLResponse, name="save_manual_job_action")
async def save_manual_job_action(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    raw_text: Annotated[str, Form()],
    title: Annotated[str, Form()] = "",
    company: Annotated[str, Form()] = "",
    save_to_tracker: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Save a manually entered job ad and redirect to the generator setup page.

    When the user checks "save to tracker" a minimal Job record (source="manual")
    and an ApplicationTrackerEntry are also created so the job appears in the
    tracker.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param raw_text: Full pasted job advertisement text.
    :param title: Optional user-supplied job title.
    :param company: Optional user-supplied company name.
    :param save_to_tracker: Non-empty string when the checkbox is checked.
    :return: Redirect to the generator setup page.
    """
    if not raw_text.strip():
        query_string = build_feedback_query(
            message="Bitte füge eine Stellenanzeige ein.",
            message_type="error",
        )
        url = str(request.url_for("render_single_job_analysis_page"))
        return RedirectResponse(url=f"{url}?{query_string}", status_code=303)

    posting = create_manual_job_posting(
        db,
        user_id=current_user.id,
        raw_text=raw_text.strip(),
        title=title.strip() or None,
        company=company.strip() or None,
    )

    if save_to_tracker.strip():
        _save_manual_job_to_tracker(
            db,
            user_id=current_user.id,
            title=title.strip() or "Manuell eingetragene Stelle",
            company=company.strip() or "Unbekanntes Unternehmen",
            description=raw_text.strip(),
        )

    db.commit()

    setup_url = str(request.url_for("render_cover_letter_setup_page"))
    return RedirectResponse(
        url=f"{setup_url}?manual_job_id={posting.id}",
        status_code=303,
    )


def _save_manual_job_to_tracker(
    db: Session,
    *,
    user_id: int,
    title: str,
    company: str,
    description: str,
) -> None:
    """Create a minimal Job record and a tracker entry for a manual job posting.

    Uses source='manual' so the job is distinguishable from API-sourced jobs.
    Silently skips if a tracker entry already exists for this job.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param title: Job title.
    :param company: Company name.
    :param description: Raw job advertisement text stored as description.
    """
    from app.models.application_tracker_entry import ApplicationTrackerEntry
    from sqlalchemy import select

    job = Job(
        title=title,
        company=company,
        description=description,
        source="manual",
    )
    db.add(job)
    db.flush()

    existing = db.execute(
        select(ApplicationTrackerEntry).where(
            ApplicationTrackerEntry.user_id == user_id,
            ApplicationTrackerEntry.job_id == job.id,
        )
    ).scalar_one_or_none()

    if existing is None:
        entry = ApplicationTrackerEntry(user_id=user_id, job_id=job.id)
        db.add(entry)


# ---------------------------------------------------------------------------
# Generator setup page
# ---------------------------------------------------------------------------

@router.get("/cover-letter/setup", response_class=HTMLResponse, name="render_cover_letter_setup_page")
def render_cover_letter_setup_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    job_id: int | None = None,
    manual_job_id: int | None = None,
    tracker_entry_id: int | None = None,
) -> Response:
    """Render the cover letter generator setup page.

    Resolves the job context (title, company) from whichever source parameter
    is present: tracker_entry_id → job_id; job_id; or manual_job_id. Pre-fills
    form fields from the session if the user was redirected here after creating
    a profile.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param job_id: Optional API-sourced job identifier.
    :param manual_job_id: Optional manual job posting identifier.
    :param tracker_entry_id: Optional tracker entry identifier.
    :return: Rendered setup page.
    """
    if tracker_entry_id is not None and job_id is None:
        entry = get_tracker_entry_by_id_for_user(
            db, entry_id=tracker_entry_id, user_id=current_user.id
        )
        if entry is not None:
            job_id = entry.job_id

    job_context = _resolve_job_context(db, job_id=job_id, manual_job_id=manual_job_id)
    prefill: dict[str, Any] = request.session.pop(_SETUP_PARAMS_SESSION_KEY, {})

    return templates.TemplateResponse(
        request=request,
        name="cover_letter_setup.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user,
            "job_id": job_id,
            "manual_job_id": manual_job_id,
            "tracker_entry_id": tracker_entry_id,
            "job_context": job_context,
            "templates": list(CoverLetterTemplate),
            "template_labels": _TEMPLATE_LABELS,
            "tones": list(CoverLetterTone),
            "tone_labels": _TONE_LABELS,
            "prefill": prefill,
        },
    )


@router.post("/cover-letter/setup", response_class=HTMLResponse, name="submit_cover_letter_setup_action")
async def submit_cover_letter_setup_action(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    background_tasks: BackgroundTasks,
    template: Annotated[str, Form()],
    tone: Annotated[str, Form()],
    job_id: Annotated[int | None, Form()] = None,
    manual_job_id: Annotated[int | None, Form()] = None,
    must_haves: Annotated[str, Form()] = "",
    personal_motivation: Annotated[str, Form()] = "",
    why_company: Annotated[str, Form()] = "",
    added_value: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Validate setup form, check profile, and start cover letter generation.

    If the user has no profile, stores the form parameters in the session
    and redirects to the profile page with an info banner.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param background_tasks: FastAPI background task queue.
    :param template: Selected template enum value string.
    :param tone: Selected tone enum value string.
    :param job_id: Optional API-sourced job identifier (hidden field).
    :param manual_job_id: Optional manual job posting identifier (hidden field).
    :param must_haves: Optional must-haves / no-gos text.
    :param personal_motivation: Optional personal motivation text.
    :param why_company: Optional why-this-company text.
    :param added_value: Optional added-value text.
    :return: Redirect to generating page or profile page.
    """
    try:
        tpl = CoverLetterTemplate(template)
        tn = CoverLetterTone(tone)
    except ValueError:
        query_string = build_feedback_query(
            message="Bitte wähle ein Template und einen Ton aus.",
            message_type="error",
        )
        setup_url = str(request.url_for("render_cover_letter_setup_page"))
        params = f"?{query_string}"
        if job_id:
            params += f"&job_id={job_id}"
        if manual_job_id:
            params += f"&manual_job_id={manual_job_id}"
        return RedirectResponse(url=f"{setup_url}{params}", status_code=303)

    profile = get_profile_for_user(db, user_id=current_user.id)
    if profile is None:
        request.session[_SETUP_PARAMS_SESSION_KEY] = {
            "template": template,
            "tone": tone,
            "job_id": job_id,
            "manual_job_id": manual_job_id,
            "must_haves": must_haves,
            "personal_motivation": personal_motivation,
            "why_company": why_company,
            "added_value": added_value,
        }
        profile_url = str(request.url_for("render_profile_page"))
        return RedirectResponse(url=f"{profile_url}?needs_profile=1", status_code=303)

    cover_letter = initiate_cover_letter_generation(
        db,
        background_tasks=background_tasks,
        user_id=current_user.id,
        template=tpl,
        tone=tn,
        job_id=job_id,
        manual_job_posting_id=manual_job_id,
        must_haves=must_haves.strip() or None,
        personal_motivation=personal_motivation.strip() or None,
        why_company=why_company.strip() or None,
        added_value=added_value.strip() or None,
    )

    generating_url = str(
        request.url_for("render_cover_letter_generating_page", cover_letter_id=cover_letter.id)
    )
    return RedirectResponse(url=generating_url, status_code=303)


# ---------------------------------------------------------------------------
# Generating (spinner) page
# ---------------------------------------------------------------------------

@router.get(
    "/cover-letter/{cover_letter_id}/generating",
    response_class=HTMLResponse,
    name="render_cover_letter_generating_page",
)
def render_cover_letter_generating_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    cover_letter_id: int,
) -> Response:
    """Render the cover letter generation spinner page.

    Redirects to the editor when generation completes, or shows an error
    card when it fails. Otherwise renders the spinner with a 10-second
    auto-reload.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param cover_letter_id: Identifier of the cover letter being generated.
    :return: Rendered spinner page or redirect to editor / error.
    """
    cover_letter = get_cover_letter_by_id(
        db, cover_letter_id=cover_letter_id, user_id=current_user.id
    )
    if cover_letter is None:
        tracker_url = str(request.url_for("render_application_tracker_page"))
        query_string = build_feedback_query(
            message="Anschreiben nicht gefunden.",
            message_type="error",
        )
        return RedirectResponse(url=f"{tracker_url}?{query_string}", status_code=303)

    if cover_letter.generation_status == CoverLetterGenerationStatus.COMPLETED:
        editor_url = str(
            request.url_for("render_cover_letter_editor_page", cover_letter_id=cover_letter_id)
        )
        return RedirectResponse(url=editor_url, status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="cover_letter_generating.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user,
            "cover_letter": cover_letter,
        },
    )


# ---------------------------------------------------------------------------
# Editor shell
# ---------------------------------------------------------------------------

@router.get(
    "/cover-letter/{cover_letter_id}/editor",
    response_class=HTMLResponse,
    name="render_cover_letter_editor_page",
)
def render_cover_letter_editor_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    cover_letter_id: int,
) -> Response:
    """Render the cover letter editor shell with A4 preview and design controls.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param cover_letter_id: Identifier of the completed cover letter.
    :return: Rendered editor page.
    """
    cover_letter = get_cover_letter_by_id(
        db, cover_letter_id=cover_letter_id, user_id=current_user.id
    )
    if cover_letter is None:
        tracker_url = str(request.url_for("render_application_tracker_page"))
        query_string = build_feedback_query(
            message="Anschreiben nicht gefunden.",
            message_type="error",
        )
        return RedirectResponse(url=f"{tracker_url}?{query_string}", status_code=303)

    if cover_letter.generation_status != CoverLetterGenerationStatus.COMPLETED:
        generating_url = str(
            request.url_for("render_cover_letter_generating_page", cover_letter_id=cover_letter_id)
        )
        return RedirectResponse(url=generating_url, status_code=303)

    content: CoverLetterContent | None = None
    if cover_letter.content:
        content = CoverLetterContent(**cover_letter.content)

    normalization: JobNormalizationSchema | None = None
    if cover_letter.job_normalization_id is not None:
        from app.models.job_normalization import JobNormalization
        norm_record = db.get(JobNormalization, cover_letter.job_normalization_id)
        if norm_record is not None:
            normalization = JobNormalizationSchema(**norm_record.normalized_data)

    layout = LayoutSettings(**(cover_letter.layout_settings or {}))
    job_title = _get_job_title(db, cover_letter)

    # Default document names derived from normalization data.
    company_name = (normalization.company_name if normalization else None) or "Unbekanntes Unternehmen"
    candidate_name = ""
    if content:
        parts = [content.candidate_first_name, content.candidate_last_name]
        candidate_name = " ".join(p for p in parts if p).strip() or "Bewerbung"

    default_document_name = cover_letter.document_name or f"Anschreiben {company_name}"
    raw_filename = f"Anschreiben_{candidate_name}_{company_name}"
    default_document_filename = cover_letter.document_filename or _sanitise_filename(raw_filename)

    return templates.TemplateResponse(
        request=request,
        name="cover_letter_editor.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user,
            "cover_letter": cover_letter,
            "content": content,
            "normalization": normalization,
            "job_title": job_title,
            "template_label": _TEMPLATE_LABELS.get(cover_letter.template, cover_letter.template),
            "tone_label": _TONE_LABELS.get(cover_letter.tone, cover_letter.tone),
            "layout": layout,
            "default_document_name": default_document_name,
            "default_document_filename": default_document_filename,
            "template_labels": _TEMPLATE_LABELS,
        },
    )


# ---------------------------------------------------------------------------
# HTMX preview endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/cover-letter/{cover_letter_id}/preview",
    response_class=HTMLResponse,
    name="render_cover_letter_preview",
)
def render_cover_letter_preview(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    cover_letter_id: int,
    template: str = "classic",
    theme_key: str = "theme-blue",
    font_key: str = "font-arial",
    size_key: str = "size-medium",
    spacing_key: str = "spacing-normal",
    recipient_pos: str = "standard",
    signature_space: str = "standard",
    compact_attachments_pos: str = "standard",
) -> HTMLResponse:
    """Return only the rendered cover letter partial for HTMX preview swaps.

    Called by the editor sidebar controls on change. Returns a bare HTML
    fragment (no page shell) that HTMX injects into the preview pane.
    Query parameter names match those of the save endpoint so both can share
    one editor form.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param cover_letter_id: Identifier of the cover letter.
    :param template: Template key (classic | modern | compact).
    :param theme_key: Theme class key.
    :param font_key: Font class key.
    :param size_key: Size class key.
    :param spacing_key: Spacing class key.
    :param recipient_pos: Recipient address position preset.
    :param signature_space: Closing-to-signature gap preset.
    :param compact_attachments_pos: Attachment position preset (compact only).
    :return: Rendered template partial HTML.
    """
    cover_letter = get_cover_letter_by_id(
        db, cover_letter_id=cover_letter_id, user_id=current_user.id
    )
    if cover_letter is None or cover_letter.content is None:
        return HTMLResponse("<p class='muted'>Kein Inhalt verfügbar.</p>")

    # Validate and clamp preset values to the allowed sets.
    safe_template = template if template in {t.value for t in CoverLetterTemplate} else "classic"
    safe_theme = theme_key if theme_key in _ALLOWED_THEMES else "theme-blue"
    safe_font = font_key if font_key in _ALLOWED_FONTS else "font-arial"
    safe_size = size_key if size_key in _ALLOWED_SIZES else "size-medium"
    safe_spacing = spacing_key if spacing_key in _ALLOWED_SPACINGS else "spacing-normal"
    safe_recipient_pos = recipient_pos if recipient_pos in _ALLOWED_RECIPIENT_POS else "standard"
    safe_signature_space = signature_space if signature_space in _ALLOWED_SIGNATURE_SPACE else "standard"
    safe_compact_attachments = (
        compact_attachments_pos if compact_attachments_pos in _ALLOWED_COMPACT_ATTACHMENTS_POS else "standard"
    )

    content = CoverLetterContent(**cover_letter.content)
    doc_classes = _build_doc_classes(
        safe_theme, safe_font, safe_size, safe_spacing,
        safe_recipient_pos, safe_signature_space, safe_compact_attachments,
    )

    template_file = f"cover_letter_variants/cover_letter_{safe_template}.html"
    html = templates.get_template(template_file).render(
        **content.model_dump(),
        theme=safe_theme,
        font=safe_font,
        size=safe_size,
        spacing=safe_spacing,
        doc_classes=doc_classes,
    )
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Save document
# ---------------------------------------------------------------------------

@router.post(
    "/cover-letter/{cover_letter_id}/save",
    response_class=HTMLResponse,
    name="save_cover_letter_document_action",
)
def save_cover_letter_document_action(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    cover_letter_id: int,
    document_name: Annotated[str, Form()] = "",
    document_filename: Annotated[str, Form()] = "",
    template: Annotated[str, Form()] = "",
    theme_key: Annotated[str, Form()] = "theme-blue",
    font_key: Annotated[str, Form()] = "font-arial",
    size_key: Annotated[str, Form()] = "size-medium",
    spacing_key: Annotated[str, Form()] = "spacing-normal",
    recipient_pos: Annotated[str, Form()] = "standard",
    signature_space: Annotated[str, Form()] = "standard",
    compact_attachments_pos: Annotated[str, Form()] = "standard",
) -> RedirectResponse:
    """Save the cover letter document with name, filename, and layout settings.

    Sets is_saved=True and persists all design and positioning preferences.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param cover_letter_id: Identifier of the cover letter to save.
    :param document_name: User-facing display name.
    :param document_filename: Export filename (no extension).
    :param template: Template key.
    :param theme_key: Theme preset key.
    :param font_key: Font preset key.
    :param size_key: Size preset key.
    :param spacing_key: Spacing preset key.
    :param recipient_pos: Recipient address position preset.
    :param signature_space: Closing gap preset.
    :param compact_attachments_pos: Attachments position preset (compact only).
    :return: Redirect to the editor page with feedback.
    """
    cover_letter = get_cover_letter_by_id(
        db, cover_letter_id=cover_letter_id, user_id=current_user.id
    )
    editor_url = str(
        request.url_for("render_cover_letter_editor_page", cover_letter_id=cover_letter_id)
    )

    if cover_letter is None:
        query_string = build_feedback_query(message="Anschreiben nicht gefunden.", message_type="error")
        return RedirectResponse(url=f"{editor_url}?{query_string}", status_code=303)

    # Validate preset keys.
    layout = LayoutSettings(
        theme_key=theme_key if theme_key in _ALLOWED_THEMES else "theme-blue",
        font_key=font_key if font_key in _ALLOWED_FONTS else "font-arial",
        size_key=size_key if size_key in _ALLOWED_SIZES else "size-medium",
        spacing_key=spacing_key if spacing_key in _ALLOWED_SPACINGS else "spacing-normal",
        recipient_pos=recipient_pos if recipient_pos in _ALLOWED_RECIPIENT_POS else "standard",
        signature_space=signature_space if signature_space in _ALLOWED_SIGNATURE_SPACE else "standard",
        compact_attachments_pos=(
            compact_attachments_pos if compact_attachments_pos in _ALLOWED_COMPACT_ATTACHMENTS_POS else "standard"
        ),
    )

    save_cover_letter_document(
        db,
        cover_letter=cover_letter,
        document_name=document_name.strip(),
        document_filename=document_filename.strip(),
        layout_settings=layout.model_dump(),
        template=template.strip() or None,
    )
    db.commit()

    query_string = build_feedback_query(message="Anschreiben gespeichert.", message_type="success")
    return RedirectResponse(url=f"{editor_url}?{query_string}", status_code=303)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.post(
    "/cover-letter/{cover_letter_id}/delete",
    response_class=HTMLResponse,
    name="delete_cover_letter_action",
)
def delete_cover_letter_action(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    cover_letter_id: int,
) -> RedirectResponse:
    """Delete a cover letter record.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param cover_letter_id: Identifier of the cover letter to delete.
    :return: Redirect to the application tracker page.
    """
    cover_letter = get_cover_letter_by_id(
        db, cover_letter_id=cover_letter_id, user_id=current_user.id
    )
    documents_url = str(request.url_for("render_documents_page"))

    if cover_letter is None:
        query_string = build_feedback_query(message="Anschreiben nicht gefunden.", message_type="error")
        return RedirectResponse(url=f"{documents_url}?{query_string}", status_code=303)

    delete_cover_letter(db, cover_letter=cover_letter)
    db.commit()

    query_string = build_feedback_query(message="Anschreiben gelöscht.", message_type="success")
    return RedirectResponse(url=f"{documents_url}?{query_string}", status_code=303)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _resolve_job_context(
    db: Session,
    *,
    job_id: int | None,
    manual_job_id: int | None,
) -> dict[str, str | None]:
    """Return a dict with job title and company for display in the setup page.

    :param db: Active database session.
    :param job_id: Optional API-sourced job identifier.
    :param manual_job_id: Optional manual job posting identifier.
    :return: Dict with keys ``title`` and ``company``.
    """
    if job_id is not None:
        job = db.get(Job, job_id)
        if job is not None:
            return {"title": job.title, "company": job.company}

    if manual_job_id is not None:
        from app.models.manual_job_posting import ManualJobPosting
        posting = db.get(ManualJobPosting, manual_job_id)
        if posting is not None:
            return {"title": posting.title, "company": posting.company}

    return {"title": None, "company": None}


def _get_job_title(db: Session, cover_letter: Any) -> str | None:
    """Return a human-readable job title for a cover letter, if available.

    :param db: Active database session.
    :param cover_letter: Cover letter ORM record.
    :return: Job title string or ``None``.
    """
    if cover_letter.job_id is not None:
        job = db.get(Job, cover_letter.job_id)
        if job is not None:
            return job.title

    if cover_letter.manual_job_posting_id is not None:
        from app.models.manual_job_posting import ManualJobPosting
        posting = db.get(ManualJobPosting, cover_letter.manual_job_posting_id)
        if posting is not None:
            return posting.title

    return None


def _sanitise_filename(name: str) -> str:
    """Convert a display name to a safe export filename (no extension).

    Replaces spaces with underscores and strips characters that are not
    alphanumeric, underscores, or hyphens.

    :param name: Raw display name string.
    :return: Sanitised filename string.
    """
    name = name.replace(" ", "_")
    name = re.sub(r"[^\w\-]", "", name, flags=re.UNICODE)
    return name[:200]


def _build_doc_classes(
    theme: str,
    font: str,
    size: str,
    spacing: str,
    recipient_pos: str,
    signature_space: str,
    compact_attachments_pos: str,
) -> str:
    """Build the extra CSS class string applied to the cover-letter article.

    The template's variant class (variant-classic etc.) is set by the template
    file itself. This function returns only the additional preset classes.

    :param theme: Theme preset key.
    :param font: Font preset key.
    :param size: Size preset key.
    :param spacing: Spacing preset key.
    :param recipient_pos: Recipient position preset.
    :param signature_space: Signature space preset.
    :param compact_attachments_pos: Compact attachments position preset.
    :return: Space-separated CSS class string.
    """
    classes = [theme, font, size, spacing]
    if recipient_pos == "high":
        classes.append("recipient-pos-high")
    if signature_space == "compact":
        classes.append("signature-space-compact")
    if compact_attachments_pos == "higher":
        classes.append("compact-attachments-higher")
    elif compact_attachments_pos == "very-high":
        classes.append("compact-attachments-very-high")
    return " ".join(classes)
