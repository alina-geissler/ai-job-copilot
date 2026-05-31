"""Service functions for cover letter generation and lifecycle management.

Coordinate cover letter creation, the background generation task, and
supporting database writes. Phase 1 uses a mock generation function;
phase 2 will replace ``_mock_generate`` with a real OpenAI
``beta.chat.completions.parse()`` call.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.enums import (
    CoverLetterGenerationStatus,
    CoverLetterRevisionType,
    CoverLetterTemplate,
    CoverLetterTone,
)
from app.crud.cover_letter import (
    create_cover_letter,
    get_cover_letter_by_id,
    update_cover_letter_content,
    update_cover_letter_status,
)
from app.crud.cover_letter_snapshot import create_snapshot
from app.crud.profile_information import get_profile_for_user
from app.db.session import SessionLocal
from app.models.cover_letter import CoverLetter
from app.models.job_normalization import JobNormalization
from app.models.profile_information import ProfileInformation
from app.schemas.cover_letter import CoverLetterContent
from app.schemas.job_normalization import JobNormalizationSchema
from app.services.job_normalization_service import get_or_create_normalization

logger = logging.getLogger(__name__)


def initiate_cover_letter_generation(
    db: Session,
    *,
    background_tasks: BackgroundTasks,
    user_id: int,
    template: CoverLetterTemplate,
    tone: CoverLetterTone,
    job_id: int | None = None,
    manual_job_posting_id: int | None = None,
    must_haves: str | None = None,
    personal_motivation: str | None = None,
    why_company: str | None = None,
    added_value: str | None = None,
) -> CoverLetter:
    """Create a PENDING cover letter record and enqueue the generation task.

    :param db: Active database session.
    :param background_tasks: FastAPI background task queue.
    :param user_id: Identifier of the owning user.
    :param template: Selected visual template.
    :param tone: Selected tone.
    :param job_id: FK to an API-sourced job, or ``None``.
    :param manual_job_posting_id: FK to a manual job posting, or ``None``.
    :param must_haves: Optional must-haves / no-gos text.
    :param personal_motivation: Optional personal motivation text.
    :param why_company: Optional why-this-company text.
    :param added_value: Optional added-value text.
    :return: Newly created CoverLetter record with PENDING status.
    """
    cover_letter = create_cover_letter(
        db,
        user_id=user_id,
        template=template,
        tone=tone,
        job_id=job_id,
        manual_job_posting_id=manual_job_posting_id,
        must_haves=must_haves,
        personal_motivation=personal_motivation,
        why_company=why_company,
        added_value=added_value,
    )
    db.commit()

    background_tasks.add_task(_run_generation_task, cover_letter_id=cover_letter.id)
    return cover_letter


def _run_generation_task(*, cover_letter_id: int) -> None:
    """Background task: normalise the job ad and generate the cover letter.

    Opens its own database session (same pattern as document_service.py).
    Steps:
    1. Set generation_status = PROCESSING.
    2. Resolve job text from either the Job or ManualJobPosting record.
    3. Get or create the JobNormalization for this job.
    4. Load the user's ProfileInformation.
    5. Generate cover letter content (mock in phase 1); LLM does not receive
       private contact fields (phone, email, street, city).
    6. Populate private fields from profile after generation.
    7. Persist content, set status = COMPLETED, create INITIAL snapshot.
    On any exception: set status = FAILED and store the error message.

    :param cover_letter_id: Identifier of the CoverLetter record to process.
    """
    db = SessionLocal()
    try:
        cover_letter = db.get(CoverLetter, cover_letter_id)
        if cover_letter is None:
            logger.error("Generation task: cover letter %d not found.", cover_letter_id)
            return

        update_cover_letter_status(
            db, cover_letter=cover_letter, status=CoverLetterGenerationStatus.PROCESSING
        )
        db.commit()

        try:
            raw_text, existing_job = _resolve_job_text(db, cover_letter)

            normalization = get_or_create_normalization(
                db,
                job_id=cover_letter.job_id,
                manual_job_posting_id=cover_letter.manual_job_posting_id,
                raw_text=raw_text,
                existing_job=existing_job,
            )
            db.commit()

            profile = get_profile_for_user(db, user_id=cover_letter.user_id)

            norm_schema = JobNormalizationSchema(**normalization.normalized_data)

            # Phase 2 hook: replace _mock_generate with real LLM call.
            # The LLM must NOT receive private contact fields.
            content = _mock_generate(
                profile=profile, normalization=norm_schema, tone=cover_letter.tone
            )

            # Populate private contact fields from profile (never from LLM).
            if profile is not None:
                content.candidate_first_name = profile.first_name or ""
                content.candidate_last_name = profile.last_name or ""
                content.candidate_street = profile.street or ""
                content.candidate_city = profile.city or ""
                content.candidate_location = profile.location or ""
                content.candidate_phone = profile.phone or ""
                content.candidate_email = profile.email or ""

            content_dict = content.model_dump()

            update_cover_letter_content(
                db,
                cover_letter=cover_letter,
                content=content_dict,
                job_normalization_id=normalization.id,
            )

            # Create the initial snapshot immediately after generation.
            create_snapshot(
                db,
                cover_letter_id=cover_letter.id,
                content=content_dict,
                revision_type=CoverLetterRevisionType.INITIAL,
                version_number=1,
            )
            db.commit()

        except Exception as exc:
            logger.exception("Cover letter generation failed for record %d.", cover_letter_id)
            update_cover_letter_status(
                db,
                cover_letter=cover_letter,
                status=CoverLetterGenerationStatus.FAILED,
                error=str(exc),
            )
            db.commit()

    except Exception:
        db.rollback()
        logger.exception(
            "Generation task encountered an unhandled error for cover letter %d.", cover_letter_id
        )
    finally:
        db.close()


def _resolve_job_text(db: Session, cover_letter: CoverLetter) -> tuple[str, object | None]:
    """Return the raw job advertisement text and the Job record if available.

    :param db: Active database session.
    :param cover_letter: Cover letter record whose source job to resolve.
    :return: Tuple of (raw_text, Job | None).
    """
    from app.models.job import Job
    from app.models.manual_job_posting import ManualJobPosting

    if cover_letter.job_id is not None:
        job = db.get(Job, cover_letter.job_id)
        if job is None:
            raise ValueError(f"Job {cover_letter.job_id} not found.")
        return job.description or job.title, job

    if cover_letter.manual_job_posting_id is not None:
        posting = db.get(ManualJobPosting, cover_letter.manual_job_posting_id)
        if posting is None:
            raise ValueError(f"ManualJobPosting {cover_letter.manual_job_posting_id} not found.")
        return posting.raw_text, None

    raise ValueError("Cover letter has neither job_id nor manual_job_posting_id.")


def _mock_generate(
    profile: ProfileInformation | None,
    normalization: JobNormalizationSchema,
    tone: CoverLetterTone,
) -> CoverLetterContent:
    """Return a CoverLetterContent with German placeholder text.

    Private contact fields (candidate_first_name, candidate_last_name,
    candidate_street, candidate_city, candidate_location, candidate_phone,
    candidate_email) are intentionally left empty here. The caller populates
    them from the user's profile after this function returns.

    Phase 2: replace this function body with an OpenAI structured-output call:
        ``client.beta.chat.completions.parse(response_format=CoverLetterContent, ...)``
    The LLM prompt must NEVER include the candidate's private contact fields.

    :param profile: User's profile information, or ``None`` if unavailable.
    :param normalization: Normalised job advertisement schema.
    :param tone: Tone selected by the user.
    :return: Populated CoverLetterContent with placeholder text (no private fields).
    """
    company = normalization.company_name or "das Unternehmen"
    job_title = normalization.canonical_job_title or "die ausgeschriebene Stelle"
    contact = normalization.contact_person

    salutation = (
        f"Sehr geehrte/r {contact}," if contact else "Sehr geehrte Damen und Herren,"
    )
    if tone == CoverLetterTone.CASUAL:
        salutation = f"Hallo {contact}," if contact else "Hallo,"

    return CoverLetterContent(
        company_name=normalization.company_name,
        contact_person=normalization.contact_person,
        company_street=normalization.company_street,
        company_city=normalization.company_city,
        date=date.today().strftime("%d.%m.%Y"),
        subject_line=(
            f"Bewerbung als {job_title}"
            + (f" – Ref.-Nr. {normalization.reference_number}" if normalization.reference_number else "")
        ),
        reference_number=normalization.reference_number,
        salutation=salutation,
        introduction=(
            f"mit großem Interesse habe ich Ihre Stellenausschreibung als {job_title} bei {company} gelesen "
            f"und bewerbe mich hiermit auf diese Position."
        ),
        main_body=[
            "[Platzhalter: Hauptteil Absatz 1 – Berufserfahrung und Kernkompetenzen, "
            "die zur Stelle passen. Wird durch KI befüllt.]",
            "[Platzhalter: Hauptteil Absatz 2 – Motivation und konkreter Mehrwert für das Unternehmen. "
            "Wird durch KI befüllt.]",
        ],
        conclusion=(
            f"Ich freue mich auf die Möglichkeit, mich in einem persönlichen Gespräch bei {company} vorzustellen "
            f"und stehe ab sofort für Rückfragen zur Verfügung."
        ),
        closing="Mit freundlichen Grüßen",
        attachments=["Lebenslauf"],
    )
