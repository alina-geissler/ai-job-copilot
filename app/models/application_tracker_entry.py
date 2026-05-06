"""Define the ORM model for application tracker entries.

Map the ``application_tracker_entries`` database table to a Python class and
declare all columns required to track a user's job application lifecycle.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.user import User


class ApplicationStatus(enum.Enum):
    """Represent the possible stages of a job application lifecycle."""

    SAVED = "saved"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ApplicationTrackerEntry(Base):
    """Represent a single user's tracking record for a job posting.

    Link a user to a job and store the current application status, optional
    notes, and timestamps. The unique constraint on ``user_id`` and ``job_id``
    ensures a user can track the same job only once.
    """

    __tablename__ = "application_tracker_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_user_job"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), nullable=False, default=ApplicationStatus.SAVED
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="tracker_entries")
    job: Mapped[Job] = relationship("Job", back_populates="tracker_entries")
