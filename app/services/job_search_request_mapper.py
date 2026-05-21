"""Map internal job-search filters to external API request parameters."""

from __future__ import annotations

from app.schemas.search_profile import SearchProfileBase


def build_job_search_request_params(
    filters: SearchProfileBase,
    *,
    start_page: int,
    pages_to_fetch: int,
    date_posted: str
) -> dict[str, str]:
    """Build upstream request parameters from validated search-profile data.

    :param filters: Validated search-profile data used as internal search filters.
    :param start_page: First upstream page to request.
    :param pages_to_fetch: Number of consecutive upstream pages to fetch.
    :param date_posted: Effective upstream ``date_posted`` value.
    :return: Dictionary of upstream request parameters for the external job-search API.
    """
    request_params: dict[str, str] = {}

    normalized_location = filters.location.strip().casefold()

    if normalized_location not in ("deutschland", "germany"):
        request_params["query"] = f"{filters.query} in {filters.location}"
    else:
        request_params["query"] = filters.query

    request_params["page"] = str(start_page)
    request_params["num_pages"] = str(pages_to_fetch)
    request_params["country"] = "de"
    request_params["date_posted"] = date_posted

    if filters.remote_only:
        request_params["work_from_home"] = "true"

    if filters.employment_types:
        request_params["employment_types"] = ",".join(filters.employment_types)

    if filters.experience_levels:
        request_params["job_requirements"] = ",".join(filters.experience_levels)

    if filters.radius_km is not None:
        request_params["radius"] = str(filters.radius_km)

    return request_params