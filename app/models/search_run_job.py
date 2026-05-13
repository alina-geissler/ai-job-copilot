"""Define the ORM model for jobs belonging to a persisted search run.

Map the ``search_run_jobs`` database table to a Python class and declare all
columns required to link saved jobs to one specific search run.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.search_run import SearchRun


class SearchRunJob(Base):
    """Represent one job entry inside a specific persisted search run.

    Link a saved job to a search run and store run-specific metadata such as
    whether the job was seen before, on which loaded page it appeared, and
    which overall position it had in that run.
    """

    __tablename__ = "search_run_jobs"
    __table_args__ = (
        UniqueConstraint("search_run_id", "job_id", name="uq_search_run_job"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    search_run_id: Mapped[int] = mapped_column(
        ForeignKey("search_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_previously_seen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    result_position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    search_run: Mapped[SearchRun] = relationship("SearchRun", back_populates="search_run_jobs")
    job: Mapped[Job] = relationship("Job", back_populates="search_run_jobs")
