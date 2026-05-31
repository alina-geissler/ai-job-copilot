"""Define the ORM model for application users.

Map the ``users`` database table to a Python class and declare all columns
required for email-based authentication and account lifecycle management.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.application_tracker_entry import ApplicationTrackerEntry
    from app.models.document import Document
    from app.models.profile_information import ProfileInformation
    from app.models.search_profile import SearchProfile
    from app.models.search_run import SearchRun
    from app.models.manual_job_posting import ManualJobPosting
    from app.models.cover_letter import CoverLetter


class User(Base):
    """Represent a registered application user.

    Store credentials and account state for a user who authenticates
    via email and password. Every other model that belongs to a user
    references this table via a foreign key.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="user", server_default="user")
    trial_job_searches_left: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
    tracker_entries: Mapped[list[ApplicationTrackerEntry]] = relationship(
        "ApplicationTrackerEntry", back_populates="user"
    )
    search_profiles: Mapped[list[SearchProfile]] = relationship(
        "SearchProfile", back_populates="user"
    )
    search_runs: Mapped[list[SearchRun]] = relationship(
        "SearchRun", back_populates="user"
    )
    documents: Mapped[list[Document]] = relationship(
        "Document", back_populates="user"
    )
    profile_information: Mapped[ProfileInformation | None] = relationship(
        "ProfileInformation", back_populates="user", uselist=False
    )
    manual_job_postings: Mapped[list[ManualJobPosting]] = relationship(
        "ManualJobPosting", back_populates="user"
    )
    cover_letters: Mapped[list[CoverLetter]] = relationship(
        "CoverLetter", back_populates="user"
    )

