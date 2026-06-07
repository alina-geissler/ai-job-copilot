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

from app.core.enums import CoverLetterGenerationStatus, CoverLetterTemplate, CoverLetterToneKey
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
from app.services.cover_letter_service import (
    initiate_cover_letter_generation,
    save_user_content_revision,
)

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

_TONE_KEY_LABELS: dict[str, str] = {
    CoverLetterToneKey.FORMELL:  "Formell",
    CoverLetterToneKey.LOCKER:   "Locker",
    CoverLetterToneKey.SACHLICH: "Sachlich",
    CoverLetterToneKey.WARM:     "Warm",
}

# Tooltip text shown on the "?" info icon for each tone option.
# Uses "Empfohlen für …" (not "Empfohlen basierend auf …").
_TONE_KEY_TOOLTIPS: dict[str, str] = {
    CoverLetterToneKey.FORMELL:  "Empfohlen für konservative Branchen / klassisches Geschäftsumfeld → sachlich, respektvoll, zurückhaltend-selbstbewusst",
    CoverLetterToneKey.LOCKER:   "Empfohlen für dynamische & moderne Branchen → aktiv, authentisch, nahbar",
    CoverLetterToneKey.SACHLICH: "Empfohlen für technisch/wissenschaftliche Branchen → präzise, faktenorientiert, ruhig-souverän",
    CoverLetterToneKey.WARM:     "Empfohlen für Sozial-/Gesundheits-/Bildungswesen → wertschätzend, empathisch, professionell-verbindlich",
}

_INDUSTRY_GROUP_LABELS: dict[str, str] = {
    "conservative_business":   "Konservatives Business",
    "dynamic_modern":          "Dynamisch & Modern",
    "technical_scientific":    "Technisch / Wissenschaftlich",
    "social_health_education": "Sozial / Gesundheit / Bildung",
}

# Guidelines shown in the info tooltip for each industry group.
_INDUSTRY_GROUP_TOOLTIPS: dict[str, str] = {
    "conservative_business":   "Banking, Versicherung, Recht, öffentlicher Dienst, traditionelle Konzerne",
    "dynamic_modern":          "Startups, Marketing, Medien, E-Commerce, Beratung, SaaS",
    "technical_scientific":    "Ingenieurwesen, IT, Software, Data, Forschung, Fertigung",
    "social_health_education": "Gesundheitswesen, Sozialarbeit, Bildung, NGO, Non-Profit",
}

_HIERARCHY_LEVEL_LABELS: dict[str, str] = {
    "entry_junior":       "Berufseinsteiger / Junior",
    "professional_senior": "Fachkraft / Senior",
    "executive_c_level":  "Führungskraft / C-Level",
}

# Guidelines shown in the info tooltip for each hierarchy level.
_HIERARCHY_LEVEL_TOOLTIPS: dict[str, str] = {
    "entry_junior":       "Trainee, Azubi, Junior, Quereinsteiger – bis ca. 2 Jahre Erfahrung",
    "professional_senior": "Mid-Level, Senior, Spezialist, Teamleitung – ca. 3–10 Jahre Erfahrung",
    "executive_c_level":  "Direktor, VP, C-Suite, Geschäftsführer, Abteilungsleitung",
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
    from prompts.cover_letter_generation import INDUSTRY_GROUP_TO_TONE, LANGUAGE_LABELS

    if tracker_entry_id is not None and job_id is None:
        entry = get_tracker_entry_by_id_for_user(
            db, entry_id=tracker_entry_id, user_id=current_user.id
        )
        if entry is not None:
            job_id = entry.job_id

    job_context = _resolve_job_context(db, job_id=job_id, manual_job_id=manual_job_id)
    prefill: dict[str, Any] = request.session.pop(_SETUP_PARAMS_SESSION_KEY, {})

    # Best-effort normalization lookup to pre-fill mandatory generation fields.
    norm_data: dict[str, Any] = {}
    if job_id is not None:
        norm_rec = get_normalization_by_job_id(db, job_id=job_id)
        if norm_rec is not None:
            norm_data = norm_rec.normalized_data or {}
    elif manual_job_id is not None:
        from app.crud.job_normalization import get_normalization_by_manual_job_id
        norm_rec = get_normalization_by_manual_job_id(db, manual_job_posting_id=manual_job_id)
        if norm_rec is not None:
            norm_data = norm_rec.normalized_data or {}

    recommended_industry_group = norm_data.get("industry_group") or "conservative_business"
    recommended_hierarchy_level = norm_data.get("hierarchy_level") or "professional_senior"
    recommended_tone = INDUSTRY_GROUP_TO_TONE[recommended_industry_group]
    posting_language = norm_data.get("posting_language") or "de"
    recommended_output_language = posting_language if posting_language in LANGUAGE_LABELS else "de"

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
            "tone_keys": list(CoverLetterToneKey),
            "tone_key_labels": _TONE_KEY_LABELS,
            "tone_key_tooltips": _TONE_KEY_TOOLTIPS,
            "industry_groups": list(_INDUSTRY_GROUP_LABELS.keys()),
            "industry_group_labels": _INDUSTRY_GROUP_LABELS,
            "industry_group_tooltips": _INDUSTRY_GROUP_TOOLTIPS,
            "hierarchy_levels": list(_HIERARCHY_LEVEL_LABELS.keys()),
            "hierarchy_level_labels": _HIERARCHY_LEVEL_LABELS,
            "hierarchy_level_tooltips": _HIERARCHY_LEVEL_TOOLTIPS,
            "language_labels": LANGUAGE_LABELS,
            "recommended_tone": recommended_tone,
            "recommended_industry_group": recommended_industry_group,
            "recommended_hierarchy_level": recommended_hierarchy_level,
            "recommended_output_language": recommended_output_language,
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
    industry_group: Annotated[str, Form()],
    hierarchy_level: Annotated[str, Form()],
    output_language: Annotated[str, Form()],
    job_id: Annotated[int | None, Form()] = None,
    manual_job_id: Annotated[int | None, Form()] = None,
    must_haves: Annotated[str, Form()] = "",
    no_gos: Annotated[str, Form()] = "",
    personal_motivation: Annotated[str, Form()] = "",
    why_company: Annotated[str, Form()] = "",
    added_value: Annotated[str, Form()] = "",
    earliest_start_date: Annotated[str, Form()] = "",
    salary_expectation: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Validate setup form, check profile, and start cover letter generation.

    If the user has no profile, stores the form parameters in the session
    and redirects to the profile page with an info banner.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param background_tasks: FastAPI background task queue.
    :param template: Selected template enum value string.
    :param tone: Selected tone key string (one of the ``CoverLetterToneKey`` values).
    :param industry_group: Selected industry group key.
    :param hierarchy_level: Selected hierarchy level key.
    :param output_language: Selected output language code (e.g. "de", "en").
    :param job_id: Optional API-sourced job identifier (hidden field).
    :param manual_job_id: Optional manual job posting identifier (hidden field).
    :param must_haves: Optional must-haves text.
    :param no_gos: Optional no-gos text.
    :param personal_motivation: Optional personal motivation text.
    :param why_company: Optional why-this-company text.
    :param added_value: Optional added-value text.
    :param earliest_start_date: Optional earliest start date.
    :param salary_expectation: Optional salary expectation.
    :return: Redirect to generating page or profile page.
    """
    from prompts.cover_letter_generation import INDUSTRY_RULES, HIERARCHY_RULES, LANGUAGE_LABELS

    try:
        tpl = CoverLetterTemplate(template)
    except ValueError:
        tpl = None

    tone_valid = tone in {k.value for k in CoverLetterToneKey}
    industry_group_valid = industry_group in INDUSTRY_RULES
    hierarchy_level_valid = hierarchy_level in HIERARCHY_RULES
    output_language_valid = output_language in LANGUAGE_LABELS

    if tpl is None or not tone_valid or not industry_group_valid or not hierarchy_level_valid or not output_language_valid:
        query_string = build_feedback_query(
            message="Bitte fülle alle Pflichtfelder aus.",
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
            "industry_group": industry_group,
            "hierarchy_level": hierarchy_level,
            "output_language": output_language,
            "job_id": job_id,
            "manual_job_id": manual_job_id,
            "must_haves": must_haves,
            "no_gos": no_gos,
            "personal_motivation": personal_motivation,
            "why_company": why_company,
            "added_value": added_value,
            "earliest_start_date": earliest_start_date,
            "salary_expectation": salary_expectation,
        }
        profile_url = str(request.url_for("render_profile_page"))
        return RedirectResponse(url=f"{profile_url}?needs_profile=1", status_code=303)

    # Map output_language code to human-readable label expected by the prompt.
    output_language_label = LANGUAGE_LABELS.get(output_language, "Deutsch")

    cover_letter = initiate_cover_letter_generation(
        db,
        background_tasks=background_tasks,
        user_id=current_user.id,
        template=tpl,
        tone=tone,
        industry_group=industry_group,
        hierarchy_level=hierarchy_level,
        output_language=output_language_label,
        job_id=job_id,
        manual_job_posting_id=manual_job_id,
        must_haves=must_haves.strip() or None,
        no_gos=no_gos.strip() or None,
        personal_motivation=personal_motivation.strip() or None,
        why_company=why_company.strip() or None,
        added_value=added_value.strip() or None,
        earliest_start_date=earliest_start_date.strip() or None,
        salary_expectation=salary_expectation.strip() or None,
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
    profile = get_profile_for_user(db, user_id=current_user.id)
    profile_signature_image = profile.signature_image if profile is not None else None

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
            "tone_label": _TONE_KEY_LABELS.get(cover_letter.tone, cover_letter.tone),
            "layout": layout,
            "default_document_name": default_document_name,
            "default_document_filename": default_document_filename,
            "template_labels": _TEMPLATE_LABELS,
            "pdf_url": request.url_for("export_cover_letter_pdf", cover_letter_id=cover_letter_id),
            "content_save_url": request.url_for("save_cover_letter_content_action", cover_letter_id=cover_letter_id),
            "sig_upload_url": request.url_for("upload_signature_action", cover_letter_id=cover_letter_id),
            "sig_remove_url": request.url_for("remove_signature_action", cover_letter_id=cover_letter_id),
            "sig_insert_url": request.url_for("insert_signature_from_profile_action", cover_letter_id=cover_letter_id),
            "signature_image": (cover_letter.layout_settings or {}).get("signature_image"),
            "has_signature": bool((cover_letter.layout_settings or {}).get("signature_image")),
            "profile_signature_image": profile_signature_image,
            "profile_update_url": request.url_for("update_profile_fields_action"),
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
    signature_image = (cover_letter.layout_settings or {}).get("signature_image")

    template_file = f"cover_letter_variants/cover_letter_{safe_template}.html"
    html = templates.get_template(template_file).render(
        **content.model_dump(),
        theme=safe_theme,
        font=safe_font,
        size=safe_size,
        spacing=safe_spacing,
        doc_classes=doc_classes,
        signature_image=signature_image,
    )
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Server-side PDF export
# ---------------------------------------------------------------------------

@router.get(
    "/cover-letter/{cover_letter_id}/pdf",
    name="export_cover_letter_pdf",
)
def export_cover_letter_pdf(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    cover_letter_id: int,
) -> Response:
    """Render the cover letter to PDF using WeasyPrint and return a download.

    Builds the same document context as the HTMX preview but renders a
    standalone HTML document (cover_letter_weasyprint.html) with WeasyPrint-
    specific CSS that uses @page for DIN 5008 margins.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param cover_letter_id: Identifier of the completed cover letter.
    :return: PDF file download response.
    """
    cover_letter = get_cover_letter_by_id(
        db, cover_letter_id=cover_letter_id, user_id=current_user.id
    )
    if cover_letter is None or cover_letter.content is None:
        editor_url = str(request.url_for("render_application_tracker_page"))
        return RedirectResponse(url=editor_url, status_code=303)

    content = CoverLetterContent(**cover_letter.content)
    layout = LayoutSettings(**(cover_letter.layout_settings or {}))
    safe_template = cover_letter.template.value
    signature_image = (cover_letter.layout_settings or {}).get("signature_image")

    doc_classes = _build_doc_classes(
        layout.theme_key, layout.font_key, layout.size_key, layout.spacing_key,
        layout.recipient_pos, layout.signature_space, layout.compact_attachments_pos,
    )

    html_str = templates.get_template("cover_letter_weasyprint.html").render(
        content=content,
        template_name=safe_template,
        doc_classes=doc_classes,
        signature_image=signature_image,
        base_url=str(request.base_url),
        theme=layout.theme_key,
        font=layout.font_key,
        size=layout.size_key,
        spacing=layout.spacing_key,
        **content.model_dump(),
    )

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page()
        pg.set_content(html_str, wait_until="networkidle")
        pdf_bytes = pg.pdf(format="A4", print_background=True)
        browser.close()

    filename = _sanitise_filename(cover_letter.document_filename or "Anschreiben") + ".pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Save user content revision
# ---------------------------------------------------------------------------

@router.post(
    "/cover-letter/{cover_letter_id}/content",
    name="save_cover_letter_content_action",
)
async def save_cover_letter_content_action(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    cover_letter_id: int,
) -> Response:
    """Persist user-edited cover letter text as a USER_REVISION snapshot.

    Collects editable field values from the form body, merges them over the
    existing content (preserving private candidate_* fields and any un-edited
    fields), validates the result, and creates a new snapshot.

    :param request: Incoming HTTP request with form data.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param cover_letter_id: Identifier of the cover letter.
    :return: JSON response with ok flag and new version number.
    """
    from fastapi.responses import JSONResponse
    from pydantic import ValidationError

    cover_letter = get_cover_letter_by_id(
        db, cover_letter_id=cover_letter_id, user_id=current_user.id
    )
    if cover_letter is None or cover_letter.content is None:
        return JSONResponse({"ok": False, "error": "Anschreiben nicht gefunden."}, status_code=404)

    form = await request.form()

    # Start from the stored content so private fields and untouched fields survive.
    merged = dict(cover_letter.content)

    # All scalar fields that may be submitted by the contenteditable hidden form.
    _EDITABLE_SCALAR_FIELDS = (
        "subject_line", "salutation", "introduction",
        "main_body_qualifications", "main_body_fit",
        "conclusion", "closing",
        "candidate_first_name", "candidate_last_name",
        "candidate_email", "candidate_phone",
        "candidate_street", "candidate_city", "candidate_location",
        "company_name", "contact_person", "company_street", "company_city",
    )
    for field in _EDITABLE_SCALAR_FIELDS:
        if field in form:
            merged[field] = str(form[field]).strip()

    # Backward-compat: collect ordered main_body_N fields for old letters.
    body_items: list[tuple[int, str]] = []
    for key, val in form.multi_items():
        if key.startswith("main_body_") and key[10:].isdigit():
            body_items.append((int(key[10:]), str(val).strip()))
    if body_items:
        body_items.sort(key=lambda x: x[0])
        merged["main_body"] = [text for _, text in body_items]

    try:
        cover_letter = save_user_content_revision(
            db, cover_letter_id=cover_letter_id, user_id=current_user.id, content_dict=merged
        )
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=422)
    except ValidationError as exc:
        return JSONResponse({"ok": False, "error": exc.json()}, status_code=422)

    from app.crud.cover_letter_snapshot import list_snapshots_for_cover_letter
    snapshots = list_snapshots_for_cover_letter(db, cover_letter_id=cover_letter_id)
    version = snapshots[-1].version_number if snapshots else 1

    # Compare candidate contact fields against the stored profile.
    _PROFILE_FIELD_MAP = {
        "candidate_first_name": "first_name",
        "candidate_last_name": "last_name",
        "candidate_email": "email",
        "candidate_phone": "phone",
        "candidate_street": "street",
        "candidate_city": "city",
        "candidate_location": "location",
    }
    profile = get_profile_for_user(db, user_id=current_user.id)
    profile_changes: dict = {}
    for content_field, profile_field in _PROFILE_FIELD_MAP.items():
        new_val = merged.get(content_field) or ""
        old_val = (getattr(profile, profile_field, None) or "") if profile else ""
        if new_val and new_val != old_val:
            profile_changes[content_field] = {
                "profile_value": old_val,
                "new_value": new_val,
                "profile_field": profile_field,
            }

    return JSONResponse({"ok": True, "version": version, "profile_changes": profile_changes})


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
# Signature image upload / remove
# ---------------------------------------------------------------------------

@router.post(
    "/cover-letter/{cover_letter_id}/signature-upload",
    name="upload_signature_action",
)
async def upload_signature_action(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    cover_letter_id: int,
) -> Response:
    """Accept an image file upload and store it as a base64 data URL in layout_settings.

    The image is validated (must be image/*, max 300 KB) and encoded as a
    data URL. Stored without a DB migration by using the existing JSONB
    layout_settings column.

    :param request: Incoming HTTP request with multipart form data.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param cover_letter_id: Identifier of the cover letter.
    :return: Redirect to the editor page.
    """
    import base64
    from fastapi import UploadFile

    cover_letter = get_cover_letter_by_id(
        db, cover_letter_id=cover_letter_id, user_id=current_user.id
    )
    editor_url = str(
        request.url_for("render_cover_letter_editor_page", cover_letter_id=cover_letter_id)
    )
    if cover_letter is None:
        query_string = build_feedback_query(message="Anschreiben nicht gefunden.", message_type="error")
        return RedirectResponse(url=f"{editor_url}?{query_string}", status_code=303)

    form = await request.form()
    file: UploadFile | None = form.get("file")  # type: ignore[assignment]
    if file is None or not hasattr(file, "read"):
        query_string = build_feedback_query(message="Keine Datei empfangen.", message_type="error")
        return RedirectResponse(url=f"{editor_url}?{query_string}", status_code=303)

    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        query_string = build_feedback_query(
            message="Ungültiger Dateityp. Bitte PNG, JPEG oder GIF hochladen.",
            message_type="error",
        )
        return RedirectResponse(url=f"{editor_url}?{query_string}", status_code=303)

    image_bytes = await file.read()
    if len(image_bytes) > 300 * 1024:
        query_string = build_feedback_query(
            message="Datei zu groß. Maximal 300 KB erlaubt.",
            message_type="error",
        )
        return RedirectResponse(url=f"{editor_url}?{query_string}", status_code=303)

    data_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode()}"
    cover_letter.layout_settings = {**(cover_letter.layout_settings or {}), "signature_image": data_url}
    db.add(cover_letter)
    db.commit()

    query_string = build_feedback_query(message="Unterschrift hochgeladen.", message_type="success")
    return RedirectResponse(url=f"{editor_url}?{query_string}", status_code=303)


@router.post(
    "/cover-letter/{cover_letter_id}/signature-remove",
    name="remove_signature_action",
)
def remove_signature_action(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    cover_letter_id: int,
) -> Response:
    """Remove the stored signature image from layout_settings.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param cover_letter_id: Identifier of the cover letter.
    :return: Redirect to the editor page.
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

    settings_dict = dict(cover_letter.layout_settings or {})
    settings_dict.pop("signature_image", None)
    cover_letter.layout_settings = settings_dict
    db.add(cover_letter)
    db.commit()

    query_string = build_feedback_query(message="Unterschrift entfernt.", message_type="success")
    return RedirectResponse(url=f"{editor_url}?{query_string}", status_code=303)


@router.post(
    "/cover-letter/{cover_letter_id}/signature-from-profile",
    name="insert_signature_from_profile_action",
)
def insert_signature_from_profile_action(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    cover_letter_id: int,
) -> Response:
    """Copy the profile signature into this cover letter's layout_settings.

    Reads ``profile_information.signature_image`` and writes it to
    ``cover_letter.layout_settings["signature_image"]``. The profile copy is
    not modified.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user.
    :param db: Active database session.
    :param cover_letter_id: Identifier of the cover letter.
    :return: Redirect to the editor page.
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

    profile = get_profile_for_user(db, user_id=current_user.id)
    if profile is None or not profile.signature_image:
        query_string = build_feedback_query(
            message="Keine Profilunterschrift vorhanden. Bitte zuerst eine Unterschrift hochladen.",
            message_type="error",
        )
        return RedirectResponse(url=f"{editor_url}?{query_string}", status_code=303)

    cover_letter.layout_settings = {
        **(cover_letter.layout_settings or {}),
        "signature_image": profile.signature_image,
    }
    db.add(cover_letter)
    db.commit()

    query_string = build_feedback_query(message="Unterschrift eingefügt.", message_type="success")
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
