"""Provide job-search results from the live external API."""

from __future__ import annotations

import httpx

from app.schemas.job_search_results import JobSearchResponse
from app.schemas.search_profile import SearchProfileBase
from app.services.job_search_provider import JobSearchProvider
from app.services.job_search_request_mapper import build_job_search_request_params
from app.services.job_search_response_mapper import map_payload_to_job_search_response


class LiveJobSearchProvider(JobSearchProvider):
    """Implement the shared job-search provider contract with live API calls."""

    def __init__(self, client: httpx.Client) -> None:
        """Initialize the live provider with a configured HTTP client."""
        self._client = client

    def search_jobs(
        self,
        filters: SearchProfileBase,
        *,
        start_page: int,
        pages_to_fetch: int,
        date_posted: str
    ) -> JobSearchResponse:
        """Fetch and map live job-search results."""
        params = build_job_search_request_params(
            filters=filters,
            start_page=start_page,
            pages_to_fetch=pages_to_fetch,
            date_posted=date_posted
        )
        response = self._client.get("/search", params=params)
        response.raise_for_status()
        payload = response.json()
        return map_payload_to_job_search_response(payload)