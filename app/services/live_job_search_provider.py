"""Provide job-search results from the live external API.

Call the upstream job-search service with mapped query parameters and convert the returned payload
into the application's internal response models.
"""

from __future__ import annotations

import httpx

from app.schemas.job_search import JobSearchFilters
from app.services.job_search_provider import JobSearchProvider
from app.schemas.job_search_results import JobSearchResponse, JobSearchResult
from app.services.job_search_request_mapper import build_job_search_request_params
from app.services.job_search_response_mapper import map_payload_to_job_search_response


class LiveJobSearchProvider(JobSearchProvider):
    """Implement the shared job-search provider contract with live API calls."""

    def __init__(self, client: httpx.Client) -> None:
        """Initialize the live provider with a configured HTTP client."""
        self._client = client

    def search_jobs(self, filters: JobSearchFilters) -> JobSearchResponse:
        """Fetch and map live job-search results.

        Convert the validated ``JobSearchFilters`` object to upstream query parameters, send the external request,
        parse the JSON payload, and map it to the internal response schema.

        :param filters: Validated search criteria from the route layer.
        :return: Normalized results from the live API.
        """
        params = build_job_search_request_params(filters)
        response = self._client.get("/search", params=params)
        response.raise_for_status()
        payload = response.json()
        return map_payload_to_job_search_response(payload)
