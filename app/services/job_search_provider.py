"""Define the shared protocol for job-search provider implementations."""

from __future__ import annotations

from typing import Protocol

from app.schemas.job_search_results import JobSearchResponse
from app.schemas.search_profile import SearchProfileBase


class JobSearchProvider(Protocol):
    """Define the common protocol for job-search provider implementations."""

    def search_jobs(
        self,
        filters: SearchProfileBase,
        *,
        start_page: int,
        pages_to_fetch: int,
        date_posted: str,
    ) -> JobSearchResponse:
        """Fetch normalized job-search results for one provider request.

        :param filters: Validated search-profile data.
        :param start_page: First upstream page to request.
        :param pages_to_fetch: Number of consecutive pages to fetch.
        :param date_posted: Effective upstream ``date_posted`` value.
        :return: Normalized provider results.
        """
        ...