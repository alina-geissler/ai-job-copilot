"""Define validated input schemas for job-search requests.

Describe the normalized search criteria collected from form data or query parameters
before the application passes them to the provider layer.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


NonEmptyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class JobSearchFilters(BaseModel):
    """Represent validated job-search criteria.

    Store the canonical search object created in ``_build_search_filters()`` and passed to redirect helpers,
    request mappers, and job-search providers.
    """
    query: NonEmptyStr
    location: NonEmptyStr
    work_model: list[Literal["remote", "hybrid", "onsite"]] = Field(default_factory=list)
    employment_type: list[Literal["full_time", "part_time", "internship"]] = Field(default_factory=list)
    experience_level: str | None = None
    company: str | None = None
    industry: list[str] = Field(default_factory=list)
