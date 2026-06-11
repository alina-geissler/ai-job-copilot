"""Map provider payloads to the application's internal result models.

Extract raw job dictionaries, normalize provider-specific fields, skip invalid records,
and build validated response objects for the results page.
"""

from __future__ import annotations

from pydantic import ValidationError

from app.schemas.job_search_results import JobSearchResult, JobSearchResponse


def extract_raw_jobs(payload: dict) -> list[dict]:
    """Extract raw job items from the response payload.

    Read the top-level ``data`` field, ensure that it is a list, and return only dictionary entries
    for downstream mapping.

    :param payload: Parsed top-level provider payload.
    :return: Raw job records extracted from the payload or empty list if the field is missing or empty
    :raises ValueError: If the ``data`` field is not a list.
    """
    raw_jobs = payload.get("data", [])

    if raw_jobs is None:
        return []

    if not isinstance(raw_jobs, list):
        raise ValueError("Fixture JSON field 'data' must be a list.")

    return [item for item in raw_jobs if isinstance(item, dict)]


def map_job(raw_job: dict) -> JobSearchResult | None:
    """Map one raw job record to the internal JobSearchResult schema.

    Read provider-specific field names, validate required values, normalize optional values, and build a
     ``JobSearchResult`` instance.

    :param raw_job: Raw job dictionary from the provider payload.
    :return: The mapped job result, or ``None`` if the record cannot be used.
    """
    job_id = raw_job.get("job_id")
    title = raw_job.get("job_title")
    company = raw_job.get("employer_name")
    posted_at = raw_job.get("job_posted_at_datetime_utc")
    apply_link = raw_job.get("job_apply_link")

    if not job_id or not title or not company or not apply_link:
        return None

    raw_location = raw_job.get("job_location")
    location = (
        raw_location.split("•")[0].strip()
        if isinstance(raw_location, str) and raw_location.strip()
        else None
    )

    try:
        return JobSearchResult(
            external_job_id=str(job_id),
            published_at=posted_at or None,
            title=title.strip(),
            company=company.strip(),
            company_logo=raw_job.get("employer_logo") or None,
            location=location,
            employment_type=raw_job.get("job_employment_type") or None,
            is_remote=raw_job.get("job_is_remote"),
            description=raw_job.get("job_description") or None,
            source=raw_job.get("job_publisher") or None,
            job_url=apply_link,
            page=raw_job.get("page") or None
        )

    except ValidationError as exc:
        # print("MAP_JOB_VALIDATION_ERROR:", exc)
        # print("RAW_JOB_KEYS:", raw_job.keys())
        return None


def map_payload_to_job_search_response(payload: dict[str, object]) -> JobSearchResponse:
    """Map a full provider payload to the internal response schema.

    Extract raw records, map each usable record to ``JobSearchResult``, and return the final ``JobSearchResponse``
    consumed by the results route and template.

    :param payload: Parsed top-level provider payload.
    :return: Normalized response containing valid mapped jobs.
    """
    raw_jobs = extract_raw_jobs(payload)
    results: list[JobSearchResult] = []

    for raw_job in raw_jobs:
        mapped_job = map_job(raw_job)
        if mapped_job is not None:
            results.append(mapped_job)

    # print("RAW_JOBS_COUNT:", len(raw_jobs))
    # print("MAPPED_RESULTS_COUNT:", len(results))

    return JobSearchResponse(
        results=results,
        total=len(results)
    )
