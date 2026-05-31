"""CRUD operations for the CoverLetterSnapshot model.

Handle creation and retrieval of content snapshots that record the full
CoverLetterContent at key points in a cover letter's lifecycle.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import CoverLetterRevisionType
from app.models.cover_letter_snapshot import CoverLetterSnapshot


def create_snapshot(
    db: Session,
    *,
    cover_letter_id: int,
    content: dict[str, Any],
    revision_type: CoverLetterRevisionType,
    version_number: int,
) -> CoverLetterSnapshot:
    """Create and flush a new content snapshot for a cover letter.

    :param db: Active database session.
    :param cover_letter_id: Identifier of the owning cover letter.
    :param content: Serialised ``CoverLetterContent`` dict at this point in time.
    :param revision_type: Origin of the snapshot (INITIAL, AI_REVISION, USER_REVISION).
    :param version_number: Sequential version number within this cover letter.
    :return: Newly created snapshot record.
    """
    snapshot = CoverLetterSnapshot(
        cover_letter_id=cover_letter_id,
        content=content,
        revision_type=revision_type,
        version_number=version_number,
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def list_snapshots_for_cover_letter(
    db: Session,
    *,
    cover_letter_id: int,
) -> list[CoverLetterSnapshot]:
    """Return all snapshots for a cover letter ordered by version_number ascending.

    :param db: Active database session.
    :param cover_letter_id: Identifier of the cover letter.
    :return: List of snapshots, oldest first.
    """
    stmt = (
        select(CoverLetterSnapshot)
        .where(CoverLetterSnapshot.cover_letter_id == cover_letter_id)
        .order_by(CoverLetterSnapshot.version_number)
    )
    return list(db.execute(stmt).scalars().all())
