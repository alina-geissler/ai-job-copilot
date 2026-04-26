from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.schemas.job_search import JobSearchFilters
from app.schemas.job_search_results import JobSearchResponse, JobSearchResult
from app.services.job_search_provider import JobSearchProvider


class FixtureJobSearchProvider(JobSearchProvider):
    def __init__(self, file_path: Path | None = None) -> None:
        self._file_path = file_path or (
            Path(__file__).resolve().parents[2] / "fixtures" / "job_search_response.json"
        )

    def _load_response_data(self) -> dict:
        with open(self._file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, dict):
            raise ValueError("Fixture JSON must contain a top-level object.")

        return data

    def _extract_raw_jobs(self, payload: dict) -> list[dict]:
        raw_jobs = payload.get("data", [])

        if raw_jobs is None:
            return []

        if not isinstance(raw_jobs, list):
            raise ValueError("Fixture JSON field 'data' must be a list.")

        return [item for item in raw_jobs if isinstance(item, dict)]

    def _map_job(self, raw_job: dict) -> JobSearchResult | None:
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
                provider_job_id=str(job_id),
                job_posted_at=posted_at or None,
                title=title.strip(),
                company=company.strip(),
                company_logo=raw_job.get("employer_logo") or None,
                location=location,
                employment_type=raw_job.get("job_employment_type") or None,
                is_remote=raw_job.get("job_is_remote"),
                job_description=raw_job.get("job_description") or None,
                source=raw_job.get("job_publisher") or None,
                apply_link=apply_link,
            )
        except ValidationError:
            return None

    def search_jobs(self, filters: JobSearchFilters) -> JobSearchResponse:
        payload = self._load_response_data()
        raw_jobs = self._extract_raw_jobs(payload)

        results: list[JobSearchResult] = []

        for raw_job in raw_jobs:
            mapped_job = self._map_job(raw_job)
            if mapped_job is not None:
                results.append(mapped_job)

        return JobSearchResponse(
            results=results,
            total=len(results),
        )