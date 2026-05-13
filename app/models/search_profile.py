"""Define the ORM model for reusable job search profiles.

Map the ``search_profiles`` database table to a Python class and declare all
columns required to persist user-owned search criteria for profile-based job searches.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.search_run import SearchRun


class SearchProfile(Base):
    """Represent a reusable job search profile owned by a user.

    Store the search criteria that a user configures through the search form.
    The same database row is updated when the profile is edited so later search
    logic can decide whether a search run may be continued or a new one must start.
    """

    __tablename__ = "search_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "profile_name", name="uq_user_profile_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_name: Mapped[str] = mapped_column(String(255), nullable=False)
    query: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    work_model: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), nullable=False, default=list, server_default=text("'{}'")
    )
    employment_type: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), nullable=False, default=list, server_default=text("'{}'")
    )
    experience_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="search_profiles")
    search_runs: Mapped[list[SearchRun]] = relationship(
        "SearchRun", back_populates="search_profile"
    )

