"""Provide job-search results from a local fixture payload.

Load a stored JSON response from disk and map it to the same internal response
models used by the live provider so the rest of the application can work
against one provider contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.schemas.job_search_results import JobSearchResponse
from app.schemas.search_profile import SearchProfileBase
from app.services.job_search_provider import JobSearchProvider
from app.services.job_search_response_mapper import map_payload_to_job_search_response


class FixtureJobSearchProvider(JobSearchProvider):
    """Implement the shared job-search provider contract with fixture data.

    Serve pre-recorded search results from a local JSON file for development and
    testing without calling the live external API.
    """

    def __init__(self, file_path: Path | None = None) -> None:
        """Initialize the provider with a fixture file path.

        If no path is provided, use the default job-search fixture file.
        """
        self._file_path = file_path or (
            Path(__file__).resolve().parents[2] / "fixtures" / "job_search_response.json"
        )

    def _load_response_data(self) -> dict[str, Any]:
        """Load the fixture payload from disk.

        :return: Parsed top-level fixture payload.
        :raises ValueError: If the fixture does not contain the expected JSON
            object structure.
        """
        with self._file_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, dict):
            raise ValueError("Fixture JSON must contain a top-level object.")

        return data

    def search_jobs(
        self,
        filters: SearchProfileBase,
        *,
        start_page: int,
        pages_to_fetch: int,
        date_posted: str,
    ) -> JobSearchResponse:
        """Return normalized results from the fixture payload.

        Accept the validated ``SearchProfileBase`` object and the paging/date
        parameters required by the shared provider contract. The fixture provider
        does not apply these values dynamically; it only returns the stored
        captured payload mapped into the internal response schema.

        :param filters: Validated search-profile data accepted by the provider
            contract.
        :param start_page: First upstream page requested by the caller.
        :param pages_to_fetch: Number of pages requested by the caller.
        :param date_posted: Effective upstream ``date_posted`` value.
        :return: Normalized search results built from fixture data.
        """
        _ = filters
        _ = start_page
        _ = pages_to_fetch
        _ = date_posted

        payload = self._load_response_data()
        return map_payload_to_job_search_response(payload)