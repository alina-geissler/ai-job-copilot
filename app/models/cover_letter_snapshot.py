"""Define the ORM model for cover letter content snapshots.

Each snapshot captures the full ``CoverLetterContent`` at a specific point in
time — initial generation, an AI revision, or a user-initiated overwrite. The
version_number is assigned per cover letter starting at 1.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import CoverLetterRevisionType
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.cover_letter import CoverLetter


class CoverLetterSnapshot(Base):
    """Represent one immutable snapshot of a cover letter's content.

    Created automatically on initial generation and before any LLM-driven
    or user-initiated overwrite. Enables content history and undo capability.
    """

    __tablename__ = "cover_letter_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    cover_letter_id: Mapped[int] = mapped_column(
        ForeignKey("cover_letters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    revision_type: Mapped[CoverLetterRevisionType] = mapped_column(
        Enum(CoverLetterRevisionType, name="coverletterrevisiontype"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cover_letter: Mapped[CoverLetter] = relationship(
        "CoverLetter", back_populates="snapshots"
    )
