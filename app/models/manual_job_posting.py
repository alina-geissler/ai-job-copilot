"""Define the ORM model for manually entered job postings.

Map the ``manual_job_postings`` table to a Python class. Stores raw job
advertisement text pasted by the user on the Single Job Analysis page.
These entries are kept separate from API-sourced jobs in the ``jobs`` table
because they lack the structured fields returned by the search API.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.job_normalization import JobNormalization
    from app.models.cover_letter import CoverLetter


class ManualJobPosting(Base):
    """Represent a job advertisement entered manually by the user.

    Store the raw pasted text together with optional user-supplied metadata
    such as a job title and company name. A separate normalisation record
    (``JobNormalization``) extracts structured data from the raw text.
    """

    __tablename__ = "manual_job_postings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="manual_job_postings")
    normalizations: Mapped[list[JobNormalization]] = relationship(
        "JobNormalization", back_populates="manual_job_posting", cascade="all, delete-orphan"
    )
    cover_letters: Mapped[list[CoverLetter]] = relationship(
        "CoverLetter", back_populates="manual_job_posting", cascade="all, delete-orphan"
    )
