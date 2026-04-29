"""Provide job-search results from a local fixture payload.

Load a stored JSON response from disk and map it to the same internal response models used by the live provider
so the rest of the application can work against one provider contract.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas.job_search import JobSearchFilters
from app.schemas.job_search_results import JobSearchResponse
from app.services.job_search_provider import JobSearchProvider

from app.services.job_search_response_mapper import map_payload_to_job_search_response


class FixtureJobSearchProvider(JobSearchProvider):
    """Implement the shared job-search provider contract with fixture data.

    Serve pre-recorded search results from a local JSON file for development and testing without calling
    the live external API.
    """

    def __init__(self, file_path: Path | None = None) -> None:
        """Initialize the provider with a fixture file path.

        If no path is provided, the default job search fixture file is used.
        """
        self._file_path = file_path or (
            Path(__file__).resolve().parents[2] / "fixtures" / "job_search_response.json"
        )

    def _load_response_data(self) -> dict:
        """Load the fixture payload from disk.

        :return: Parsed top-level fixture payload.
        :raises ValueError: If the fixture does not contain the expected JSON object structure.
        """
        with open(self._file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, dict):
            raise ValueError("Fixture JSON must contain a top-level object.")

        return data

    def search_jobs(self, filters: JobSearchFilters) -> JobSearchResponse:
        """Return normalized results from the fixture payload.

        Accept the validated ``JobSearchFilters`` object to satisfy the shared provider contract, then load and map
        the stored fixture response. The filters are not applied inside this provider because the fixture already
        represents a captured search result.

        :param filters: Validated search criteria accepted by the provider contract.
        :return: Normalized search results built from fixture data.
        """
        payload = self._load_response_data()
        response = map_payload_to_job_search_response(payload)
        return response

