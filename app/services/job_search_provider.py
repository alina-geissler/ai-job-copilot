from typing import Protocol

from app.schemas.job_search import JobSearchFilters
from app.schemas.job_search_results import JobSearchResponse


class JobSearchProvider(Protocol):
    def search_jobs(self, filters: JobSearchFilters) -> JobSearchResponse:
        ...
