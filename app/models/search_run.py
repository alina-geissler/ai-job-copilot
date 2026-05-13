"""Define the ORM model for persisted job search runs.

Map the ``search_runs`` database table to a Python class and declare all
columns required to track one concrete execution of a search profile.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.search_profile import SearchProfile
    from app.models.user import User
    from app.models.search_run_job import SearchRunJob


class SearchRun(Base):
    """Represent one persisted execution of a user's search profile.

    Store the profile reference, the run date, the effective date-posted value,
    and the pagination counters required to continue or review the search later.
    """

    __tablename__ = "search_runs"
    __table_args__ = (
        UniqueConstraint("user_id", "search_profile_id", "run_date", name="uq_user_profile_run_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    search_profile_id: Mapped[int] = mapped_column(
        ForeignKey("search_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    date_posted: Mapped[str] = mapped_column(String(50), nullable=False)
    # saves the Date Posted value actually used for the run (API param)
    current_page: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    total_jobs_loaded: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_new_jobs_loaded: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    load_more_requests_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="search_runs")
    search_profile: Mapped[SearchProfile] = relationship(
        "SearchProfile", back_populates="search_runs"
    )
    search_run_jobs: Mapped[list[SearchRunJob]] = relationship(
        "SearchRunJob", back_populates="search_run"
    )