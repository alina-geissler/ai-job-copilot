"""Define shared enums for job-search-related filter values.

Provide centralized, reusable string enums for validated search filters
used across schemas, routes, templates, services, and mappers.
"""

from __future__ import annotations

from enum import StrEnum


class EmploymentType(StrEnum):
    """Define supported employment type filter values for job search profiles."""

    FULL_TIME = "FULLTIME"
    PART_TIME = "PARTTIME"
    CONTRACTOR = "CONTRACTOR"
    INTERNSHIP = "INTERN"


class ExperienceLevel(StrEnum):
    """Define supported experience level filter values for job search profiles."""

    UNDER_THREE_YEARS_EXPERIENCE = "under_3_years_experience"
    MORE_THAN_THREE_YEARS_EXPERIENCE = "more_than_3_years_experience"
    NO_EXPERIENCE = "no_experience"
    NO_DEGREE = "no_degree"