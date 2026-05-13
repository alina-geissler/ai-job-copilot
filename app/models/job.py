"""Define the ORM model for job postings stored in the application.

Map the ``jobs`` database table to a Python class and declare all columns
required to persist both externally sourced and manually entered job postings.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.application_tracker_entry import ApplicationTrackerEntry
    from app.models.search_run_job import SearchRunJob


class Job(Base):
    """Represent a job posting saved in the application.

    Store either a job fetched from an external provider or a manually entered
    posting. External jobs carry ``external_job_id`` and ``source`` for
    deduplication; manually entered jobs leave those fields empty.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("external_job_id", "source", name="uq_external_job_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    company_logo: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_remote: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    job_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tracker_entries: Mapped[list[ApplicationTrackerEntry]] = relationship(
        "ApplicationTrackerEntry", back_populates="job"
    )
    search_run_jobs: Mapped[list[SearchRunJob]] = relationship(
        "SearchRunJob", back_populates="job"
    )