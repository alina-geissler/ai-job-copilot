"""Define shared enum types used across the application.

Provide centralized, reusable enums for validated filter values, allowed actions for search requests,
and canonical application states used across models, schemas, routes,
templates, services, CRUD functions, and mappers.
"""

from __future__ import annotations

import enum
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


class ApplicationStatus(enum.Enum):
    """Represent the possible stages of a job application lifecycle.

    Use stable English enum values in the database and translate them only
    in the UI layer.
    """

    SAVED = "saved"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class PrimarySearchAction(StrEnum):
    """Represent the next allowed action for a primary search request."""

    START_NEW_RUN = "start_new_run"
    SHOW_EXISTING_RUN = "show_existing_run"
    BLOCKED_DAILY_LIMIT = "blocked_daily_limit"
    BLOCKED_PROFILE_LIMIT = "blocked_profile_limit"