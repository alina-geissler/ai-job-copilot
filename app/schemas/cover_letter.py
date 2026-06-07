"""Define Pydantic schemas for cover letter generation input and output.

Provide ``CoverLetterContent`` — the structured output produced by the
cover-letter generation service — and ``LayoutSettings`` for validated
design and positioning preferences stored in ``layout_settings`` JSONB.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CoverLetterContent(BaseModel):
    """Represent the structured content of one generated cover letter.

    Populated by the generation service and stored as a JSONB blob in the
    ``cover_letters.content`` column. Private contact fields (phone, email,
    street, city) are filled from the user's profile by the backend after
    generation and are never sent to the LLM.
    """

    # -- Recipient block ----------------------------------------------------------
    company_name: str | None = None
    contact_person: str | None = None
    company_street: str | None = None
    company_city: str | None = None

    # -- Sender contact (private — populated by backend, not LLM) ----------------
    candidate_first_name: str = ""
    candidate_last_name: str = ""
    candidate_street: str = ""
    candidate_city: str = ""
    candidate_location: str = ""
    candidate_phone: str = ""
    candidate_email: str = ""

    # -- Date / reference ---------------------------------------------------------
    date: str | None = None

    # -- Letter header ------------------------------------------------------------
    subject_line: str | None = None
    reference_number: str | None = None

    # -- Letter body --------------------------------------------------------------
    salutation: str = ""
    introduction: str = ""
    main_body_qualifications: str = ""
    main_body_fit: str = ""
    # Deprecated: present on letters generated before the Phase 2 pipeline.
    # Kept for backward compatibility so old records remain renderable.
    main_body: list[str] | None = None
    conclusion: str = ""
    closing: str = ""

    # -- Attachments --------------------------------------------------------------
    attachments: list[str] = Field(default_factory=lambda: ["Lebenslauf"])


class LayoutSettings(BaseModel):
    """Represent the design and positioning preferences for a cover letter.

    All values are stored as string preset keys so that CSS changes never
    require a data migration. Validated against allowed sets in the route
    before being persisted.
    """

    theme_key: str = "theme-blue"
    font_key: str = "font-arial"
    size_key: str = "size-medium"
    spacing_key: str = "spacing-normal"
    recipient_pos: str = "standard"           # standard | high
    signature_space: str = "standard"         # standard | compact
    compact_attachments_pos: str = "standard" # standard | higher | very-high (compact only)
