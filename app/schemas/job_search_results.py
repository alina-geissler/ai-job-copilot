from datetime import datetime
from pydantic import BaseModel, Field


class JobSearchResult(BaseModel):
    provider_job_id: str
    job_posted_at: datetime | None = None
    title: str
    company: str
    company_logo: str | None = None
    location: str | None = None
    employment_type: str | None = None
    is_remote: bool | None = None
    job_description: str | None = None
    source: str | None = None
    apply_link: str


class JobSearchResponse(BaseModel):
    results: list[JobSearchResult] = Field(default_factory=list)
    total: int = 0