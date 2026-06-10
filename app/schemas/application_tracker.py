"""Define Pydantic schemas for application tracker form submissions.

Describe the validated data structures used to update the status and notes
of an application tracker entry via HTML form submissions.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, field_validator

from app.core.enums import ApplicationStatus


class TrackerStatusUpdateForm(BaseModel):
    """Represent validated form input for updating a tracker entry status."""

    status: ApplicationStatus
    status_date: date | None = None
    redirect_to: Literal["overview", "detail"] = "overview"

    @field_validator("status_date", mode="before")
    @classmethod
    def parse_status_date(cls, value: object) -> None | date | object:
        """Parse and normalize the status date from form input.

        Accept a blank string or ``None`` as no date. Accept a non-blank
        ISO 8601 date string and parse it. Pass through an already-parsed
        ``date`` object unchanged.

        :param value: Raw incoming status date value from the form.
        :return: Parsed ``date`` or ``None``.
        :raises ValueError: If the string is non-blank but not a valid ISO date.
        """
        if value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            return date.fromisoformat(stripped)
        return value


class TrackerStatusClearDateForm(BaseModel):
    """Represent validated form input for clearing a status date field."""

    status: ApplicationStatus
    redirect_to: Literal["overview", "detail"] = "detail"


class TrackerNotesUpdateForm(BaseModel):
    """Represent validated form input for updating tracker entry notes."""

    notes: str | None = None
    redirect_to: Literal["overview", "detail"] = "overview"

    @field_validator("notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: object) -> str | None | object:
        """Strip whitespace and coerce blank notes to ``None``.

        :param value: Raw incoming notes value from the form.
        :return: Stripped non-empty string or ``None``.
        """
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value
