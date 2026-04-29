"""Map internal job-search filters to external API request parameters.

 Translate the validated application search object into the flat string-based query format
 expected by the upstream job API.
 """

from __future__ import annotations

from app.schemas.job_search import JobSearchFilters


def build_job_search_request_params(filters: JobSearchFilters) -> dict[str, str]:
    """Build upstream request parameters from validated search filters.

     Read the ``JobSearchFilters`` object created in the route layer and derive the query parameters
     used by ``LiveJobSearchProvider`` for the external ``GET /search`` request.

     :param filters: Validated search criteria from the route layer.
     :return: Query parameters for the upstream job API.
     """
    request_params: dict[str, str] = {}

    if filters.location.lower() not in ("deutschland", "germany", "de"):
        request_params["query"] = f"{filters.query} in {filters.location}"
    else:
        request_params["query"] = filters.query

    request_params["page"] = "1"
    request_params["num_pages"] = "5"
    request_params["country"] = "de"
    request_params["date_posted"] = "all"

    # The API only supports filtering explicitly for remote jobs via work_from_home=true.
    # There is no dedicated "onsite only" flag, so if nothing is set, the API returns all jobs.
    if "remote" in filters.work_model and len(filters.work_model) == 1:
        request_params["work_from_home"] = "true"

    employment_type_mapping = {
        "full_time": "FULLTIME",
        "part_time": "PARTTIME",
        "internship": "INTERN",
    }

    mapped_employment_types = [
        employment_type_mapping[value]
        for value in filters.employment_type
        if value in employment_type_mapping
    ]

    if mapped_employment_types:
        request_params["employment_types"] = ",".join(mapped_employment_types)
    # TODO: Lösung überlegen für experience_level, company, industry (+ work_model, employment_type) !
    return request_params



