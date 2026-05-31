"""Define the ORM model for structured job normalisation records.

Map the ``job_normalizations`` table to a Python class. Each row stores the
full structured output produced by the job-normalisation step (LLM or mock)
for one API-sourced job or one manual job posting.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.manual_job_posting import ManualJobPosting
    from app.models.cover_letter import CoverLetter


class JobNormalization(Base):
    """Represent the normalised, structured view of one job advertisement.

    Produced by the job-normalisation service (mock in phase 1, OpenAI in
    phase 2) and stored as a JSONB blob. References either an API-sourced
    ``Job`` row or a ``ManualJobPosting`` row — never both.
    """

    __tablename__ = "job_normalizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    manual_job_posting_id: Mapped[int | None] = mapped_column(
        ForeignKey("manual_job_postings.id", ondelete="CASCADE"), nullable=True
    )
    normalized_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    llm_model: Mapped[str] = mapped_column(String(100), nullable=False, default="mock")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    job: Mapped[Job | None] = relationship("Job", back_populates="normalizations")
    manual_job_posting: Mapped[ManualJobPosting | None] = relationship(
        "ManualJobPosting", back_populates="normalizations"
    )
    cover_letters: Mapped[list[CoverLetter]] = relationship(
        "CoverLetter", back_populates="job_normalization"
    )
