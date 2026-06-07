"""Service functions for cover letter generation and lifecycle management.

Coordinate cover letter creation, the background generation task, and
supporting database writes. The real LLM generation uses a three-call pipeline:
Call A (Analysis) → Call B (Writing) → Call C (Verification, conditional).
"""

from __future__ import annotations

import json
import logging
from datetime import date

import httpx
from fastapi import BackgroundTasks
from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import (
    CoverLetterGenerationStatus,
    CoverLetterRevisionType,
    CoverLetterTemplate,
)
from app.crud.cover_letter import (
    create_cover_letter,
    get_cover_letter_by_id,
    set_cover_letter_content,
    update_cover_letter_content,
    update_cover_letter_status,
)
from app.crud.cover_letter_snapshot import create_snapshot, list_snapshots_for_cover_letter
from app.crud.job_normalization import get_normalization_by_job_id, get_normalization_by_manual_job_id
from app.crud.profile_information import get_profile_for_user
from app.db.session import SessionLocal
from app.models.cover_letter import CoverLetter
from app.models.job import Job
from app.models.job_normalization import JobNormalization
from app.models.manual_job_posting import ManualJobPosting
from app.models.profile_information import ProfileInformation
from app.schemas.cover_letter import CoverLetterContent
from app.schemas.job_normalization import JobNormalizationSchema
from app.services.job_normalization_service import get_or_create_normalization
from prompts.cover_letter_generation import (
    ANALYSIS_SETTINGS,
    ANALYSIS_SCHEMA,
    LENGTH_BUDGET,
    VERIFICATION_SETTINGS,
    VERIFICATION_SCHEMA,
    WRITING_SETTINGS,
    WRITING_SCHEMA,
    build_analysis_messages,
    build_verification_messages,
    build_writing_messages,
    filter_job_for_llm,
    resolve_contact_gender,
)

logger = logging.getLogger(__name__)


def _build_client() -> OpenAI:
    """Create a configured OpenAI client using the default OpenAI endpoint.

    :return: Configured OpenAI client instance.
    """
    return OpenAI(
        api_key=settings.openai_api_key,
        max_retries=3,
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0),
    )


def _build_draft_name(
    db: Session,
    *,
    job_id: int | None,
    manual_job_posting_id: int | None,
) -> str | None:
    """Build a human-readable draft title from the associated job record.

    Tries the normalization cache first (has canonical title + company name),
    then falls back to the raw Job or ManualJobPosting row. Returns ``None``
    if no title information is available.

    :param db: Active database session.
    :param job_id: FK to an API-sourced job, or ``None``.
    :param manual_job_posting_id: FK to a manual job posting, or ``None``.
    :return: Draft name, e.g. "Entwurf für Softwareentwickler (Acme GmbH)", or ``None``.
    """
    title: str | None = None
    company: str | None = None

    if job_id is not None:
        norm = get_normalization_by_job_id(db, job_id=job_id)
        if norm is not None:
            data = norm.normalized_data or {}
            title = data.get("canonical_job_title") or None
            company = data.get("company_name") or None
        if not title or not company:
            job = db.get(Job, job_id)
            if job is not None:
                title = title or job.title or None
                company = company or job.company or None
    elif manual_job_posting_id is not None:
        posting = db.get(ManualJobPosting, manual_job_posting_id)
        if posting is not None:
            title = posting.title or None
            company = posting.company or None
        norm = get_normalization_by_manual_job_id(db, manual_job_posting_id=manual_job_posting_id)
        if norm is not None:
            data = norm.normalized_data or {}
            title = data.get("canonical_job_title") or title
            company = data.get("company_name") or company

    if not title:
        return None
    if company:
        return f"Entwurf für {title} ({company})"
    return f"Entwurf für {title}"


def initiate_cover_letter_generation(
    db: Session,
    *,
    background_tasks: BackgroundTasks,
    user_id: int,
    template: CoverLetterTemplate,
    tone: str,
    industry_group: str,
    hierarchy_level: str,
    output_language: str,
    job_id: int | None = None,
    manual_job_posting_id: int | None = None,
    must_haves: str | None = None,
    no_gos: str | None = None,
    personal_motivation: str | None = None,
    why_company: str | None = None,
    added_value: str | None = None,
    earliest_start_date: str | None = None,
    salary_expectation: str | None = None,
    company_context: str | None = None,
) -> CoverLetter:
    """Create a PENDING cover letter record and enqueue the generation task.

    :param db: Active database session.
    :param background_tasks: FastAPI background task queue.
    :param user_id: Identifier of the owning user.
    :param template: Selected visual template.
    :param tone: Selected tone key (one of the ``CoverLetterToneKey`` values).
    :param industry_group: Mandatory industry group selected on setup form.
    :param hierarchy_level: Mandatory hierarchy level selected on setup form.
    :param output_language: Mandatory output language selected on setup form.
    :param job_id: FK to an API-sourced job, or ``None``.
    :param manual_job_posting_id: FK to a manual job posting, or ``None``.
    :param must_haves: Optional must-haves text.
    :param no_gos: Optional no-gos text.
    :param personal_motivation: Optional personal motivation text.
    :param why_company: Optional why-this-company text.
    :param added_value: Optional added-value text.
    :param earliest_start_date: Optional earliest start date.
    :param salary_expectation: Optional salary expectation.
    :param company_context: Optional company background (reserved for future use).
    :return: Newly created CoverLetter record with PENDING status.
    """
    cover_letter = create_cover_letter(
        db,
        user_id=user_id,
        template=template,
        tone=tone,
        industry_group=industry_group,
        hierarchy_level=hierarchy_level,
        output_language=output_language,
        job_id=job_id,
        manual_job_posting_id=manual_job_posting_id,
        must_haves=must_haves,
        no_gos=no_gos,
        personal_motivation=personal_motivation,
        why_company=why_company,
        added_value=added_value,
        earliest_start_date=earliest_start_date,
        salary_expectation=salary_expectation,
        company_context=company_context,
        document_name=_build_draft_name(
            db, job_id=job_id, manual_job_posting_id=manual_job_posting_id
        ),
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
    5. Generate cover letter content via the three-call LLM pipeline.
       The LLM does not receive private contact fields.
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

            content = _llm_generate(
                cover_letter=cover_letter,
                norm_schema=norm_schema,
                profile=profile,
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

            # Populate signature from profile if available.
            if profile is not None and profile.signature_image:
                cover_letter.layout_settings = {
                    **(cover_letter.layout_settings or {}),
                    "signature_image": profile.signature_image,
                }
                db.add(cover_letter)

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


def _llm_generate(
    *,
    cover_letter: CoverLetter,
    norm_schema: JobNormalizationSchema,
    profile: ProfileInformation | None,
) -> CoverLetterContent:
    """Run the three-call LLM pipeline and return structured cover letter content.

    The LLM never receives private candidate contact fields (phone, email, street,
    city). The caller populates those after this function returns.

    :param cover_letter: CoverLetter record carrying all user-selected options.
    :param norm_schema: Normalised job schema from the normalisation step.
    :param profile: User's profile information, or ``None`` if unavailable.
    :return: Populated CoverLetterContent with LLM-generated body fields.
    :raises ValueError: If mandatory generation fields are missing on the record.
    """
    for field in ("tone", "industry_group", "hierarchy_level", "output_language"):
        if not getattr(cover_letter, field):
            raise ValueError(
                f"Cover letter {cover_letter.id} is missing mandatory field '{field}'. "
                "This is a data integrity error — the setup form should have enforced it."
            )

    tone_key: str = cover_letter.tone
    industry_group: str = cover_letter.industry_group  # type: ignore[assignment]
    hierarchy_level: str = cover_letter.hierarchy_level  # type: ignore[assignment]
    output_language: str = cover_letter.output_language  # type: ignore[assignment]

    job_dict = filter_job_for_llm(norm_schema)
    contact_person_gender = resolve_contact_gender(
        job_dict, norm_schema.contact_person_gender
    )

    additional_details: dict = {
        k: v for k, v in {
            "must_haves":         cover_letter.must_haves,
            "no_gos":             cover_letter.no_gos,
            "personal_motivation": cover_letter.personal_motivation,
            "company_reason":     cover_letter.why_company,
            "added_value":        cover_letter.added_value,
            "earliest_start_date": cover_letter.earliest_start_date,
            "salary_expectation": cover_letter.salary_expectation,
        }.items() if v
    }

    company_context: str = cover_letter.company_context or ""
    profile_dict = _build_profile_dict(profile)

    client = _build_client()

    # ── Call A: Analysis ────────────────────────────────────────────────────
    analysis_messages = build_analysis_messages(
        job_dict, profile_dict, additional_details, company_context
    )
    fit_plan = _call_with_json_retry(
        client,
        call_name="Analysis",
        messages=analysis_messages,
        settings=ANALYSIS_SETTINGS,
        schema=ANALYSIS_SCHEMA,
    )

    # ── Call B: Writing (with length-check regeneration) ────────────────────
    letter = _call_writing(
        client=client,
        fit_plan=fit_plan,
        job_dict=job_dict,
        profile_dict=profile_dict,
        additional_details=additional_details,
        company_context=company_context,
        industry_group=industry_group,
        hierarchy_level=hierarchy_level,
        tone_key=tone_key,
        output_language=output_language,
        contact_person_gender=contact_person_gender,
    )

    # ── Call C: Verification (conditional) ──────────────────────────────────
    must_avoid: list[str] = fit_plan.get("must_avoid") or []
    if must_avoid:
        letter = _verify_and_maybe_regenerate(
            client=client,
            letter=letter,
            must_avoid=must_avoid,
            fit_plan=fit_plan,
            job_dict=job_dict,
            profile_dict=profile_dict,
            additional_details=additional_details,
            company_context=company_context,
            industry_group=industry_group,
            hierarchy_level=hierarchy_level,
            tone_key=tone_key,
            output_language=output_language,
            contact_person_gender=contact_person_gender,
        )

    company = norm_schema.company_name or "das Unternehmen"
    reference_number = norm_schema.reference_number

    return CoverLetterContent(
        company_name=norm_schema.company_name,
        contact_person=norm_schema.contact_person,
        company_street=norm_schema.company_street,
        company_city=norm_schema.company_city,
        date=date.today().strftime("%d.%m.%Y"),
        subject_line=letter.get("subject_line", ""),
        reference_number=reference_number,
        salutation=letter.get("salutation", ""),
        introduction=letter.get("introduction", ""),
        main_body_qualifications=letter.get("main_body_qualifications", ""),
        main_body_fit=letter.get("main_body_fit", ""),
        conclusion=letter.get("conclusion", ""),
        closing="Mit freundlichen Grüßen",
        attachments=["Lebenslauf"],
    )


def _call_writing(
    *,
    client: OpenAI,
    fit_plan: dict,
    job_dict: dict,
    profile_dict: dict,
    additional_details: dict,
    company_context: str,
    industry_group: str,
    hierarchy_level: str,
    tone_key: str,
    output_language: str,
    contact_person_gender: str,
) -> dict:
    """Execute Call B (Writing) with a single length-check regeneration pass.

    If the total character count of the four prose fields exceeds
    ``LENGTH_BUDGET["total_chars_hard_max"]``, appends a compression instruction
    and retries once.

    :return: Letter fields dict from the LLM.
    """
    messages = build_writing_messages(
        fit_plan, job_dict, profile_dict, additional_details, company_context,
        industry_group=industry_group,
        hierarchy_level=hierarchy_level,
        tone_key=tone_key,
        output_language=output_language,
        contact_person_gender=contact_person_gender,
    )
    letter = _call_with_json_retry(
        client, call_name="Writing", messages=messages,
        settings=WRITING_SETTINGS, schema=WRITING_SCHEMA,
    )

    prose_fields = ("introduction", "main_body_qualifications", "main_body_fit", "conclusion")
    total_chars = sum(len(letter.get(f, "")) for f in prose_fields)
    if total_chars > LENGTH_BUDGET["total_chars_hard_max"]:
        logger.info(
            "Writing Call B: letter too long (%d chars > %d). Regenerating with compression.",
            total_chars, LENGTH_BUDGET["total_chars_hard_max"],
        )
        compression_note = (
            "\n\nWICHTIG: Der vorherige Versuch war zu lang. "
            "Kürze jeden Abschnitt konsequent."
        )
        messages[-1]["content"] += compression_note
        letter = _call_with_json_retry(
            client, call_name="Writing (compressed)", messages=messages,
            settings=WRITING_SETTINGS, schema=WRITING_SCHEMA,
        )

    return letter


def _verify_and_maybe_regenerate(
    *,
    client: OpenAI,
    letter: dict,
    must_avoid: list[str],
    fit_plan: dict,
    job_dict: dict,
    profile_dict: dict,
    additional_details: dict,
    company_context: str,
    industry_group: str,
    hierarchy_level: str,
    tone_key: str,
    output_language: str,
    contact_person_gender: str,
) -> dict:
    """Run Call C (Verification) and regenerate Call B once if violations found.

    After one regeneration pass, returns the letter regardless of remaining
    violations — those are logged for human review rather than looped indefinitely.

    :return: Final letter fields dict (possibly regenerated).
    """
    verification_messages = build_verification_messages(letter, must_avoid)
    report = _call_with_json_retry(
        client, call_name="Verification", messages=verification_messages,
        settings=VERIFICATION_SETTINGS, schema=VERIFICATION_SCHEMA,
    )

    violations = [c for c in report.get("checks", []) if c.get("violated")]
    if not violations:
        return letter

    logger.warning(
        "Cover letter verification found %d violation(s): %s",
        len(violations),
        [v.get("no_go") for v in violations],
    )

    evidence_block = (
        "\n\nACHTUNG – vorheriger Versuch hat gegen folgende No-Go-Regeln verstoßen:\n"
        + json.dumps(violations, ensure_ascii=False)
        + "\nDiese Themen dürfen weder wörtlich noch sinngemäß erwähnt werden."
    )
    messages = build_writing_messages(
        fit_plan, job_dict, profile_dict, additional_details, company_context,
        industry_group=industry_group,
        hierarchy_level=hierarchy_level,
        tone_key=tone_key,
        output_language=output_language,
        contact_person_gender=contact_person_gender,
    )
    messages[-1]["content"] += evidence_block

    regenerated = _call_with_json_retry(
        client, call_name="Writing (violation fix)", messages=messages,
        settings=WRITING_SETTINGS, schema=WRITING_SCHEMA,
    )

    # Check once more; log remaining violations but do not loop.
    re_verification = build_verification_messages(regenerated, must_avoid)
    re_report = _call_with_json_retry(
        client, call_name="Verification (re-check)", messages=re_verification,
        settings=VERIFICATION_SETTINGS, schema=VERIFICATION_SCHEMA,
    )
    remaining = [c for c in re_report.get("checks", []) if c.get("violated")]
    if remaining:
        logger.error(
            "Cover letter still has %d violation(s) after regeneration — "
            "flagged for human review: %s",
            len(remaining),
            [v.get("no_go") for v in remaining],
        )

    return regenerated


def _call_with_json_retry(
    client: OpenAI,
    *,
    call_name: str,
    messages: list[dict],
    settings: dict,
    schema: dict,
) -> dict:
    """Execute one structured-output call and retry once on JSON parse failure.

    Uses the Responses API (``client.responses.create``) with ``text.format``
    for structured output.  The settings dicts use Responses-API parameters
    (``max_output_tokens``, ``reasoning_effort``, ``verbosity``).

    :param client: Configured OpenAI client.
    :param call_name: Label used in log messages.
    :param messages: Message list for the call.
    :param settings: Model and parameter kwargs (model, reasoning_effort, etc.).
    :param schema: JSON schema dict passed as ``text={"format": schema}``.
    :return: Parsed JSON dict from the LLM response.
    :raises ValueError: If the response cannot be parsed after one retry.
    """
    # Unwrap chat-completions response_format shape → Responses API text.format shape
    if "json_schema" in schema:
        text_format = {"type": "json_schema", **schema["json_schema"]}
    else:
        text_format = schema

    for attempt in range(2):
        response = client.responses.create(
            **settings,
            input=messages,
            text={"format": text_format},
        )
        raw = response.output_text
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            if attempt == 0:
                logger.warning(
                    "%s call returned unparseable JSON (attempt 1), retrying: %s",
                    call_name, exc,
                )
                continue
            raise ValueError(
                f"{call_name} call returned unparseable JSON after retry. "
                f"Raw response: {raw!r}"
            ) from exc
    # unreachable, but satisfies type checker
    raise ValueError(f"{call_name}: unexpected exit from retry loop")


def _build_profile_dict(profile: ProfileInformation | None) -> dict:
    """Build a compact, LLM-safe dict from the user's profile.

    Excludes all private contact fields (name, phone, email, street, city,
    location, signature_image). Only content useful for generating the letter
    body is included.

    :param profile: User's ProfileInformation record, or ``None``.
    :return: Dict suitable for passing to the prompt builder functions.
    """
    if profile is None:
        return {}
    return {
        k: v for k, v in {
            "target_role":           profile.target_role,
            "seniority_level":       profile.seniority_level,
            "leadership_experience": profile.leadership_experience,
            "salary_expectation":    profile.salary_expectation,
            "work_model":            profile.work_model,
            "availability":          profile.availability,
            "employment_types":      profile.employment_types,
            "work_experience":       profile.work_experience,
            "education":             profile.education,
            "certifications":        profile.certifications,
            "projects":              profile.projects,
            "courses":               profile.courses,
            "volunteering":          profile.volunteering,
            "hard_skills":           profile.hard_skills,
            "soft_skills":           profile.soft_skills,
            "languages":             profile.languages,
            "publications":          profile.publications,
            "honors_awards":         profile.honors_awards,
        }.items() if v
    }


def save_user_content_revision(
    db: Session,
    *,
    cover_letter_id: int,
    user_id: int,
    content_dict: dict,
) -> CoverLetter:
    """Persist a user-edited content revision as a USER_REVISION snapshot.

    Validates that the cover letter is COMPLETED and that the submitted dict
    is a valid ``CoverLetterContent``. Creates a new snapshot and updates
    the cover letter content column.

    :param db: Active database session.
    :param cover_letter_id: Identifier of the cover letter.
    :param user_id: Identifier of the authenticated user (ownership check).
    :param content_dict: Full ``CoverLetterContent`` dict with edited values.
    :return: Updated cover letter record.
    :raises ValueError: If the cover letter is not found or not COMPLETED.
    :raises pydantic.ValidationError: If content_dict is malformed.
    """
    cover_letter = get_cover_letter_by_id(
        db, cover_letter_id=cover_letter_id, user_id=user_id
    )
    if cover_letter is None:
        raise ValueError(f"Cover letter {cover_letter_id} not found.")
    if cover_letter.generation_status != CoverLetterGenerationStatus.COMPLETED:
        raise ValueError("Cover letter is not in COMPLETED status.")

    # Validate the incoming dict; raises ValidationError if malformed.
    CoverLetterContent(**content_dict)

    next_version = (
        len(list_snapshots_for_cover_letter(db, cover_letter_id=cover_letter_id)) + 1
    )

    set_cover_letter_content(db, cover_letter=cover_letter, content=content_dict)
    create_snapshot(
        db,
        cover_letter_id=cover_letter_id,
        content=content_dict,
        revision_type=CoverLetterRevisionType.USER_REVISION,
        version_number=next_version,
    )
    db.commit()
    return cover_letter


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
