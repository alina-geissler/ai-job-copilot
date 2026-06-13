"""Unit tests for the job-search response mapper functions."""

from __future__ import annotations

import pytest

from app.services.job_search_response_mapper import (
    extract_raw_jobs,
    map_job,
    map_payload_to_job_search_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_raw_job(**overrides) -> dict:
    base = {
        "job_id": "abc123",
        "job_title": "Software Engineer",
        "employer_name": "Acme GmbH",
        "job_apply_link": "https://example.com/apply",
        "job_location": "Berlin",
        "job_posted_at_datetime_utc": "2025-06-01T10:00:00",
        "job_employment_type": "FULLTIME",
        "job_is_remote": False,
        "job_description": "A great role.",
        "job_publisher": "LinkedIn",
        "employer_logo": "https://example.com/logo.png",
        "page": 1,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# extract_raw_jobs
# ---------------------------------------------------------------------------

class TestExtractRawJobs:
    """Tests for ``extract_raw_jobs``."""

    def test_valid_payload_returns_list(self):
        payload = {"data": [_valid_raw_job()]}
        result = extract_raw_jobs(payload)
        assert len(result) == 1

    def test_empty_list_returns_empty(self):
        assert extract_raw_jobs({"data": []}) == []

    def test_missing_data_key_returns_empty(self):
        assert extract_raw_jobs({}) == []

    def test_null_data_value_returns_empty(self):
        assert extract_raw_jobs({"data": None}) == []

    def test_non_list_data_raises_value_error(self):
        with pytest.raises(ValueError):
            extract_raw_jobs({"data": {"job_id": "x"}})

    def test_filters_non_dict_items(self):
        payload = {"data": [_valid_raw_job(), "not-a-dict", 42, None]}
        result = extract_raw_jobs(payload)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# map_job
# ---------------------------------------------------------------------------

class TestMapJob:
    """Tests for ``map_job``."""

    def test_valid_record_maps_correctly(self):
        result = map_job(_valid_raw_job())
        assert result is not None
        assert result.external_job_id == "abc123"
        assert result.title == "Software Engineer"
        assert result.company == "Acme GmbH"
        assert result.job_url == "https://example.com/apply"

    def test_missing_job_id_returns_none(self):
        raw = _valid_raw_job()
        del raw["job_id"]
        assert map_job(raw) is None

    def test_falsy_job_id_returns_none(self):
        assert map_job(_valid_raw_job(job_id="")) is None

    def test_missing_title_returns_none(self):
        raw = _valid_raw_job()
        del raw["job_title"]
        assert map_job(raw) is None

    def test_missing_company_returns_none(self):
        raw = _valid_raw_job()
        del raw["employer_name"]
        assert map_job(raw) is None

    def test_missing_apply_link_returns_none(self):
        raw = _valid_raw_job()
        del raw["job_apply_link"]
        assert map_job(raw) is None

    def test_location_strips_bullet_separator(self):
        result = map_job(_valid_raw_job(job_location="Berlin • Remote"))
        assert result is not None
        assert result.location == "Berlin"

    def test_blank_location_becomes_none(self):
        result = map_job(_valid_raw_job(job_location="   "))
        assert result is not None
        assert result.location is None

    def test_null_optional_fields_are_none(self):
        raw = _valid_raw_job(
            job_posted_at_datetime_utc=None,
            employer_logo=None,
            job_location=None,
            job_employment_type=None,
            job_is_remote=None,
            job_description=None,
            job_publisher=None,
            page=None,
        )
        result = map_job(raw)
        assert result is not None
        assert result.published_at is None
        assert result.company_logo is None

    def test_title_is_stripped(self):
        result = map_job(_valid_raw_job(job_title="  Engineer  "))
        assert result is not None
        assert result.title == "Engineer"

    def test_company_is_stripped(self):
        result = map_job(_valid_raw_job(employer_name="  Acme  "))
        assert result is not None
        assert result.company == "Acme"


# ---------------------------------------------------------------------------
# map_payload_to_job_search_response
# ---------------------------------------------------------------------------

class TestMapPayload:
    """Tests for ``map_payload_to_job_search_response``."""

    def test_maps_all_valid_jobs(self):
        payload = {"data": [_valid_raw_job(), _valid_raw_job(job_id="xyz789")]}
        response = map_payload_to_job_search_response(payload)
        assert response.total == 2
        assert len(response.results) == 2

    def test_skips_invalid_records(self):
        invalid = _valid_raw_job(job_id=None)
        valid = _valid_raw_job()
        payload = {"data": [invalid, valid]}
        response = map_payload_to_job_search_response(payload)
        assert response.total == 1

    def test_empty_payload_returns_zero_total(self):
        response = map_payload_to_job_search_response({"data": []})
        assert response.total == 0
        assert response.results == []

    def test_missing_data_key_returns_zero_total(self):
        response = map_payload_to_job_search_response({})
        assert response.total == 0
