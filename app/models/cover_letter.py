"""Define the ORM model for generated cover letters.

Map the ``cover_letters`` table to a Python class. Each row tracks one cover
letter generation request — its source job, user-selected options, generation
lifecycle state, and the resulting structured content once complete.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import CoverLetterGenerationStatus, CoverLetterTemplate, CoverLetterTone
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.job import Job
    from app.models.manual_job_posting import ManualJobPosting
    from app.models.job_normalization import JobNormalization
    from app.models.cover_letter_snapshot import CoverLetterSnapshot


class CoverLetter(Base):
    """Represent one cover letter generation request and its result.

    Links to the source job (API-sourced or manual), the normalisation record
    used as input, the user's generation options, and the final generated
    content once the background task completes.
    """

    __tablename__ = "cover_letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    manual_job_posting_id: Mapped[int | None] = mapped_column(
        ForeignKey("manual_job_postings.id", ondelete="SET NULL"), nullable=True
    )
    job_normalization_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_normalizations.id", ondelete="SET NULL"), nullable=True
    )
    template: Mapped[CoverLetterTemplate] = mapped_column(
        Enum(CoverLetterTemplate, name="coverlettertemplate"), nullable=False
    )
    tone: Mapped[CoverLetterTone] = mapped_column(
        Enum(CoverLetterTone, name="coverlettertone"), nullable=False
    )
    must_haves: Mapped[str | None] = mapped_column(Text, nullable=True)
    personal_motivation: Mapped[str | None] = mapped_column(Text, nullable=True)
    why_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    generation_status: Mapped[CoverLetterGenerationStatus] = mapped_column(
        Enum(CoverLetterGenerationStatus, name="coverlettergenerationstatus"),
        nullable=False,
        default=CoverLetterGenerationStatus.PENDING,
    )
    generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_saved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    layout_settings: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    user: Mapped[User] = relationship("User", back_populates="cover_letters")
    job: Mapped[Job | None] = relationship("Job", back_populates="cover_letters")
    manual_job_posting: Mapped[ManualJobPosting | None] = relationship(
        "ManualJobPosting", back_populates="cover_letters"
    )
    job_normalization: Mapped[JobNormalization | None] = relationship(
        "JobNormalization", back_populates="cover_letters"
    )
    snapshots: Mapped[list[CoverLetterSnapshot]] = relationship(
        "CoverLetterSnapshot", back_populates="cover_letter", cascade="all, delete-orphan"
    )
