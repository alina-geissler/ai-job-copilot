"""Provide dependency factories for configuration and job-search services.

Create reusable objects for FastAPI dependency injection, including application settings,
the HTTP client for the live job API, and the active job-search provider implementation.
"""

from __future__ import annotations

import httpx
from functools import lru_cache

from app.core.config import Settings
from app.services.fixture_job_search_provider import FixtureJobSearchProvider
from app.services.live_job_search_provider import LiveJobSearchProvider
from app.services.job_search_provider import JobSearchProvider


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()


def get_job_search_api_client() -> httpx.Client:
    """Build the HTTP client for the live job-search API.

    Read connection settings from the cached ``Settings`` object and create the ``httpx.Client`` instance
    used by ``LiveJobSearchProvider`` to call the upstream ``/search`` endpoint.

    :return: A configured HTTP client for the live job API.
    """
    settings = get_settings()
    return httpx.Client(
        base_url=settings.job_api_base_url,
        timeout=httpx.Timeout(
            connect=settings.job_api_timeout_connect,
            read=settings.job_api_timeout_read,
            write=settings.job_api_timeout_write,
            pool=settings.job_api_timeout_pool
        ),
        headers={
            "x-rapidapi-key": settings.job_api_key,
            "x-rapidapi-host": settings.job_api_host,
            "Content-Type": "application/json"
        }
    )


def get_job_search_provider() -> JobSearchProvider:
    """Return the configured job-search provider.

      Instantiate the provider selected in application settings and return it behind the shared ``JobSearchProvider``
      contract so route handlers do not depend on a specific backend.

      :return: The active job-search provider implementation.
      :raises ValueError: If the configured provider name is unsupported.
      """
    settings = get_settings()
    if settings.job_search_provider == "fixture":
        return FixtureJobSearchProvider()
    elif settings.job_search_provider == "live":
        client = get_job_search_api_client()
        return LiveJobSearchProvider(client=client)
    raise ValueError(
        f"Unsupported job search provider: {settings.job_search_provider}"
    )
