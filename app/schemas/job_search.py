from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


NonEmptyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class JobSearchFilters(BaseModel):
    query: NonEmptyStr
    location: NonEmptyStr
    work_model: list[str] = Field(default_factory=list)
    employment_type: list[str] = Field(default_factory=list)
    experience_level: str | None = None
    company: str | None = None
    industry: list[str] = Field(default_factory=list)


class JobResult(BaseModel):
    title: str
    company: str
    location: str | None = None
    employment_type: str | None = None
    work_model: str | None = None
    url: str
    source: str | None = None


class JobSearchResponse(BaseModel):
    results: list[JobResult] = Field(default_factory=list)
    total: int = 0