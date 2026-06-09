"""Define routes for the authenticated dashboard page."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.enums import ApplicationStatus, DocumentProcessingStatus, DocumentType
from app.crud.application_tracker_entry import list_tracker_entries_for_user
from app.crud.cover_letter import get_completed_drafts_for_user, get_saved_cover_letters_for_user
from app.crud.document import get_document_by_type_for_user
from app.crud.profile_information import get_profile_for_user
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.templates import get_base_template_context
from app.models.user import User

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="templates")

_ACTIVE_STATUSES = {ApplicationStatus.APPLIED, ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER}


def _calculate_profile_completion(profile, has_cv: bool, has_signature: bool) -> int:
    """Return profile completeness as a percentage (0–100, step 10).

    Ten sections are evaluated; each completed section contributes 10%.
    Certifications, projects, volunteering, publications, and honours/awards
    are excluded from the score.

    :param profile: ProfileInformation row or ``None``.
    :param has_cv: Whether the user has a successfully processed CV document.
    :param has_signature: Whether the user has uploaded a signature image.
    :return: Completion percentage as a multiple of 10.
    """
    if profile is None:
        sections = [has_cv, has_signature] + [False] * 8
        return sum(sections) * 10

    sections = [
        has_cv,
        has_signature,
        bool(profile.work_experience),
        bool(profile.education),
        bool(profile.hard_skills),
        bool(profile.soft_skills),
        bool(profile.languages),
        bool(
            profile.first_name or profile.last_name or profile.email
            or profile.phone or profile.street or profile.city or profile.location
        ),
        bool(profile.target_role or profile.seniority_level or profile.leadership_experience),
        bool(
            profile.salary_expectation or profile.work_model
            or profile.availability or profile.employment_types
        ),
    ]
    return sum(sections) * 10


@router.get("/dashboard", response_class=HTMLResponse, name="render_dashboard_page")
def render_dashboard_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    """Render the dashboard page for the authenticated user.

    :param request: Incoming HTTP request.
    :param current_user: Authenticated user resolved from the current session.
    :param db: Active database session.
    :return: Rendered dashboard page.
    """
    tracker_entries = list_tracker_entries_for_user(db, user_id=current_user.id)
    total_saved_jobs = len(tracker_entries)
    active_applications = sum(1 for e in tracker_entries if e.status in _ACTIVE_STATUSES)

    saved_cls = get_saved_cover_letters_for_user(db, user_id=current_user.id)
    draft_cls = get_completed_drafts_for_user(db, user_id=current_user.id)
    total_cover_letters = len(saved_cls) + len(draft_cls)

    cv_doc = get_document_by_type_for_user(db, user_id=current_user.id, document_type=DocumentType.CV)
    has_cv = cv_doc is not None and cv_doc.processing_status == DocumentProcessingStatus.COMPLETED

    profile = get_profile_for_user(db, user_id=current_user.id)
    has_signature = bool(profile and profile.signature_image)
    profile_completion = _calculate_profile_completion(profile, has_cv, has_signature)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            **get_base_template_context(request),
            "current_user": current_user,
            "total_saved_jobs": total_saved_jobs,
            "active_applications": active_applications,
            "total_cover_letters": total_cover_letters,
            "profile_completion": profile_completion,
            "job_searches_left": current_user.trial_job_searches_left,
        }
    )
