"""CRUD operations for the CoverLetter model.

Handle database interactions for creating, reading, updating, and deleting
cover letter records that belong to one authenticated user.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import CoverLetterGenerationStatus, CoverLetterTemplate, CoverLetterTone
from app.models.cover_letter import CoverLetter


def create_cover_letter(
    db: Session,
    *,
    user_id: int,
    template: CoverLetterTemplate,
    tone: CoverLetterTone,
    job_id: int | None = None,
    manual_job_posting_id: int | None = None,
    must_haves: str | None = None,
    personal_motivation: str | None = None,
    why_company: str | None = None,
    added_value: str | None = None,
    document_name: str | None = None,
) -> CoverLetter:
    """Create and flush a new cover letter record with PENDING status.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param template: Selected visual template.
    :param tone: Selected tone.
    :param job_id: FK to an API-sourced job, or ``None``.
    :param manual_job_posting_id: FK to a manual job posting, or ``None``.
    :param must_haves: Optional must-haves / no-gos text.
    :param personal_motivation: Optional personal motivation text.
    :param why_company: Optional why-this-company text.
    :param added_value: Optional added-value text.
    :param document_name: Human-readable draft title, e.g. "Entwurf für …".
    :return: Newly created CoverLetter record.
    """
    cover_letter = CoverLetter(
        user_id=user_id,
        template=template,
        tone=tone,
        job_id=job_id,
        manual_job_posting_id=manual_job_posting_id,
        must_haves=must_haves or None,
        personal_motivation=personal_motivation or None,
        why_company=why_company or None,
        added_value=added_value or None,
        document_name=document_name or None,
        generation_status=CoverLetterGenerationStatus.PENDING,
    )
    db.add(cover_letter)
    db.flush()
    return cover_letter


def get_cover_letter_by_id(
    db: Session,
    *,
    cover_letter_id: int,
    user_id: int,
) -> CoverLetter | None:
    """Return one cover letter by identifier for the given user.

    :param db: Active database session.
    :param cover_letter_id: Identifier of the cover letter.
    :param user_id: Identifier of the owning user.
    :return: Matching cover letter or ``None``.
    """
    stmt = (
        select(CoverLetter)
        .where(CoverLetter.id == cover_letter_id, CoverLetter.user_id == user_id)
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def list_cover_letters_for_user(
    db: Session,
    *,
    user_id: int,
) -> list[CoverLetter]:
    """Return all cover letters for one user ordered by newest first.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :return: List of cover letters.
    """
    stmt = (
        select(CoverLetter)
        .where(CoverLetter.user_id == user_id)
        .order_by(CoverLetter.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_saved_cover_letters_for_user(
    db: Session,
    *,
    user_id: int,
    job_id: int | None = None,
) -> list[CoverLetter]:
    """Return saved cover letters (is_saved=True) for one user, newest first.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param job_id: Optional job identifier to filter by.
    :return: List of saved cover letters.
    """
    stmt = (
        select(CoverLetter)
        .where(CoverLetter.user_id == user_id, CoverLetter.is_saved.is_(True))
        .order_by(CoverLetter.created_at.desc())
    )
    if job_id is not None:
        stmt = stmt.where(CoverLetter.job_id == job_id)
    return list(db.execute(stmt).scalars().all())


def get_completed_drafts_for_user(
    db: Session,
    *,
    user_id: int,
    job_id: int | None = None,
) -> list[CoverLetter]:
    """Return completed but unsaved drafts for one user, newest first.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param job_id: Optional job identifier to filter by.
    :return: List of draft cover letters.
    """
    stmt = (
        select(CoverLetter)
        .where(
            CoverLetter.user_id == user_id,
            CoverLetter.is_saved.is_(False),
            CoverLetter.generation_status == CoverLetterGenerationStatus.COMPLETED,
        )
        .order_by(CoverLetter.created_at.desc())
    )
    if job_id is not None:
        stmt = stmt.where(CoverLetter.job_id == job_id)
    return list(db.execute(stmt).scalars().all())


def update_cover_letter_status(
    db: Session,
    *,
    cover_letter: CoverLetter,
    status: CoverLetterGenerationStatus,
    error: str | None = None,
) -> CoverLetter:
    """Update the generation status and optional error of a cover letter.

    :param db: Active database session.
    :param cover_letter: Existing cover letter record.
    :param status: New generation status.
    :param error: Error message if generation failed, otherwise ``None``.
    :return: Updated cover letter.
    """
    cover_letter.generation_status = status
    cover_letter.generation_error = error
    db.add(cover_letter)
    return cover_letter


def update_cover_letter_content(
    db: Session,
    *,
    cover_letter: CoverLetter,
    content: dict[str, Any],
    job_normalization_id: int | None = None,
) -> CoverLetter:
    """Persist generated content and link the normalisation record.

    :param db: Active database session.
    :param cover_letter: Existing cover letter record.
    :param content: Serialised ``CoverLetterContent`` dict.
    :param job_normalization_id: FK to the normalisation used as input.
    :return: Updated cover letter.
    """
    cover_letter.content = content
    cover_letter.generation_status = CoverLetterGenerationStatus.COMPLETED
    if job_normalization_id is not None:
        cover_letter.job_normalization_id = job_normalization_id
    db.add(cover_letter)
    return cover_letter


def save_cover_letter_document(
    db: Session,
    *,
    cover_letter: CoverLetter,
    document_name: str,
    document_filename: str,
    layout_settings: dict[str, Any],
    template: str | None = None,
) -> CoverLetter:
    """Mark a cover letter as saved and persist its document metadata.

    Sets ``is_saved=True`` and stores the display name, export filename,
    layout settings, and optionally an updated template choice.

    :param db: Active database session.
    :param cover_letter: Existing cover letter record.
    :param document_name: User-facing display name for the document.
    :param document_filename: Filename used for export (no extension).
    :param layout_settings: Dict of design preset keys.
    :param template: New template enum value string, or ``None`` to keep existing.
    :return: Updated cover letter.
    """
    from app.core.enums import CoverLetterTemplate

    cover_letter.is_saved = True
    cover_letter.document_name = document_name.strip() or None
    cover_letter.document_filename = document_filename.strip() or None
    cover_letter.layout_settings = layout_settings
    if template is not None:
        try:
            cover_letter.template = CoverLetterTemplate(template)
        except ValueError:
            pass
    db.add(cover_letter)
    return cover_letter


def set_cover_letter_content(
    db: Session,
    *,
    cover_letter: CoverLetter,
    content: dict[str, Any],
) -> CoverLetter:
    """Update only the content of a cover letter without changing its status.

    Used for user-initiated content revisions. Does not alter
    ``generation_status`` or ``job_normalization_id``.

    :param db: Active database session.
    :param cover_letter: Existing cover letter record.
    :param content: Serialised ``CoverLetterContent`` dict.
    :return: Updated cover letter.
    """
    cover_letter.content = content
    db.add(cover_letter)
    return cover_letter


def delete_cover_letter(db: Session, *, cover_letter: CoverLetter) -> None:
    """Delete a cover letter record from the database.

    :param db: Active database session.
    :param cover_letter: Existing cover letter to delete.
    """
    db.delete(cover_letter)
