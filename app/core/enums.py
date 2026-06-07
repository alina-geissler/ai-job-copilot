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


class DocumentType(StrEnum):
    """Represent the type of a stored document.

    Used as a discriminator on the shared ``documents`` table so that uploaded
    CVs and generated documents such as cover letters share one table.
    """

    CV = "cv"
    COVER_LETTER = "cover_letter"


class DocumentProcessingStatus(StrEnum):
    """Represent the text-extraction lifecycle state of a document."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExtractionMethod(StrEnum):
    """Represent the method used to extract text from a PDF document."""

    EMBEDDED_TEXT = "embedded_text"
    OCR = "ocr"
    MARKDOWN = "markdown"


class CoverLetterTemplate(StrEnum):
    """Represent the visual template selected for a generated cover letter."""

    CLASSIC = "classic"
    MODERN = "modern"
    COMPACT = "compact"


class CoverLetterToneKey(StrEnum):
    """Represent the user-selected tone style for a generated cover letter.

    Maps 1:1 to the four ``TONE_STYLES`` keys in ``prompts.cover_letter_generation``.
    The pre-selection recommendation is derived from ``INDUSTRY_GROUP_TO_TONE``
    but the user may override it before submitting the setup form.
    """

    FORMELL  = "formell"
    LOCKER   = "locker"
    SACHLICH = "sachlich"
    WARM     = "warm"


class CoverLetterGenerationStatus(StrEnum):
    """Represent the lifecycle state of a cover letter generation task."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CoverLetterRevisionType(StrEnum):
    """Represent the origin of a cover letter content snapshot."""

    INITIAL = "INITIAL"
    AI_REVISION = "AI_REVISION"
    USER_REVISION = "USER_REVISION"