"""ORM model for structured candidate profile information.

Store the fields extracted from a CV by the LLM extraction pipeline.
One row per user; complex list fields are stored as JSON.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class ProfileInformation(Base):
    """Store structured candidate profile data extracted from an uploaded CV.

    Each user has at most one profile row. Simple fields use VARCHAR/Text
    columns; complex or repeated fields (work experience, education, etc.)
    are stored as JSON so the schema can evolve without new migrations.
    """

    __tablename__ = "profile_information"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Personal information
    name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(512))
    phone: Mapped[str | None] = mapped_column(String(100))

    # Professional identity
    target_role: Mapped[str | None] = mapped_column(String(255))
    seniority_level: Mapped[str | None] = mapped_column(String(100))
    leadership_experience: Mapped[str | None] = mapped_column(Text)

    # Preferences
    salary_expectation: Mapped[str | None] = mapped_column(String(255))
    work_model: Mapped[str | None] = mapped_column(String(100))
    availability: Mapped[str | None] = mapped_column(String(255))
    employment_types: Mapped[list | None] = mapped_column(JSON)

    # Experience and education (list of structured dicts)
    work_experience: Mapped[list | None] = mapped_column(JSON)
    education: Mapped[list | None] = mapped_column(JSON)
    certifications: Mapped[list | None] = mapped_column(JSON)
    projects: Mapped[list | None] = mapped_column(JSON)
    courses: Mapped[list | None] = mapped_column(JSON)
    volunteering: Mapped[list | None] = mapped_column(JSON)

    # Skills
    soft_skills: Mapped[list | None] = mapped_column(JSON)
    hard_skills: Mapped[list | None] = mapped_column(JSON)
    languages: Mapped[list | None] = mapped_column(JSON)

    # Achievements
    publications: Mapped[list | None] = mapped_column(JSON)
    honors_awards: Mapped[list | None] = mapped_column(JSON)

    # Extraction metadata
    extraction_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="profile_information")
