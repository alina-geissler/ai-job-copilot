"""CRUD operations for the ManualJobPosting model.

Handle database interactions for creating and reading manually entered
job posting records that belong to one authenticated user.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.manual_job_posting import ManualJobPosting


def create_manual_job_posting(
    db: Session,
    *,
    user_id: int,
    raw_text: str,
    title: str | None = None,
    company: str | None = None,
    job_url: str | None = None,
) -> ManualJobPosting:
    """Create and flush a new manual job posting record.

    :param db: Active database session.
    :param user_id: Identifier of the owning user.
    :param raw_text: Full pasted job advertisement text.
    :param title: Optional user-supplied job title.
    :param company: Optional user-supplied company name.
    :param job_url: Optional URL to the original job advertisement.
    :return: Newly created ManualJobPosting record.
    """
    posting = ManualJobPosting(
        user_id=user_id,
        raw_text=raw_text,
        title=title or None,
        company=company or None,
        job_url=job_url or None,
    )
    db.add(posting)
    db.flush()
    return posting


def get_manual_job_posting_by_id(
    db: Session,
    *,
    posting_id: int,
    user_id: int,
) -> ManualJobPosting | None:
    """Return one manual job posting by identifier for the given user.

    :param db: Active database session.
    :param posting_id: Identifier of the posting.
    :param user_id: Identifier of the owning user.
    :return: Matching posting or ``None``.
    """
    stmt = (
        select(ManualJobPosting)
        .where(ManualJobPosting.id == posting_id, ManualJobPosting.user_id == user_id)
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()
