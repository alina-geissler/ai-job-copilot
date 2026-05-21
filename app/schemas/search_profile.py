"""Define Pydantic schemas for persisted job-search profiles.

Describe the available search profile filter values and the validated data
structures used to create, update, display, and select search profiles.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator
)

from app.core.enums import EmploymentType, ExperienceLevel


NonEmptyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1)
]

OptionalProfileName = Annotated[
    str | None,
    StringConstraints(strip_whitespace=True, min_length=1)
]


class SearchProfileBase(BaseModel):
    """Represent shared validated search profile fields."""

    query: NonEmptyStr
    location: NonEmptyStr
    remote_only: bool = False
    employment_types: list[EmploymentType] = Field(default_factory=list)
    experience_levels: list[ExperienceLevel] = Field(default_factory=list)
    radius_km: int | None = Field(default=None, ge=1, le=500)

    @field_validator("radius_km", mode="before")
    @classmethod
    def normalize_radius_km(cls, value: str | int | None) -> str | int | None:
        """Convert blank radius values from HTML forms to ``None``.

        :param value: Raw incoming radius value.
        :return: ``None`` for blank values, otherwise the original value.
        """
        if value is None:
            return None

        if isinstance(value, str):
            value = value.strip()
            return value or None

        return value

    @model_validator(mode="after")
    def validate_radius_km_usage(self) -> SearchProfileBase:
        """Allow radius only for locations more specific than Germany.

        :return: Validated search profile instance.
        :raises ValueError: If ``radius_km`` is not used with a city.
        """
        if self.radius_km is None:
            return self

        if self.location.strip().casefold() in ("deutschland", "germany"):
            raise ValueError(
                "radius_km can only be set for cities"
            )

        return self


class SearchProfileCreate(SearchProfileBase):
    """Represent validated input for creating a search profile."""

    profile_name: OptionalProfileName = None


class SearchProfileUpdate(SearchProfileBase):
    """Represent validated input for updating a search profile."""

    profile_name: NonEmptyStr


class SearchProfileRead(SearchProfileBase):
    """Represent full stored search profile data for display purposes."""

    id: int
    user_id: int
    profile_name: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)