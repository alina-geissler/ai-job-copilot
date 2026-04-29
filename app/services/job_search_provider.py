"""Declare the shared contract for job-search providers.

Define the interface that all provider backends implement so the route layer can request job data
without knowing whether it comes from a fixture file or the live external API.
"""

from __future__ import annotations

from typing import Protocol

from app.schemas.job_search import JobSearchFilters
from app.schemas.job_search_results import JobSearchResponse


class JobSearchProvider(Protocol):
    """Define the common protocol for job-search provider implementations."""
    def search_jobs(self, filters: JobSearchFilters) -> JobSearchResponse:
        ...
