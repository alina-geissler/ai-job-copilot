"""Define validated output schemas for mapped job-search results.

Describe the internal response objects produced after fixture or live provider payloads
are normalized for the application.
"""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class JobSearchResult(BaseModel):
    """Represent one normalized job entry returned by a provider."""
    external_job_id: str
    published_at: datetime | None = None
    title: str
    company: str
    company_logo: str | None = None
    location: str | None = None
    employment_type: str | None = None
    is_remote: bool | None = None
    description: str | None = None
    source: str | None = None
    job_url: str
    page: int | None = None


class JobSearchResponse(BaseModel):
    """Represent the normalized result set returned by a provider."""
    results: list[JobSearchResult] = Field(default_factory=list)
    total: int = 0