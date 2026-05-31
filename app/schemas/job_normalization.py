"""Define Pydantic schemas for structured job normalisation output.

Provide the ``JobNormalizationSchema`` used as the target type for the
job-normalisation LLM call (phase 2) and as the in-memory representation
of normalisation data loaded from the JSONB database column.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class JobNormalizationSchema(BaseModel):
    """Represent the fully structured, normalised view of one job advertisement.

    All fields are optional and default to ``None`` or empty list so that
    partially extractable job postings always produce a valid instance.
    Field values are in the language of the original posting unless the
    LLM prompt instructs otherwise.
    """

    # -- Identity -----------------------------------------------------------------
    reference_number: str | None = None
    canonical_job_title: str | None = None
    job_title_variants: list[str] = Field(default_factory=list)
    role_summary: str | None = None

    # -- Company ------------------------------------------------------------------
    company_name: str | None = None
    contact_person: str | None = None
    company_street: str | None = None
    company_city: str | None = None
    company_email: str | None = None
    company_phone: str | None = None
    industry_domain: str | None = None

    # -- Role classification ------------------------------------------------------
    occupational_category: str | None = None
    department_function: str | None = None
    seniority_level: str | None = None
    employment_type: str | None = None
    work_model: str | None = None
    job_location: str | None = None
    work_hours_pattern: str | None = None
    salary_range: str | None = None

    # -- Tasks --------------------------------------------------------------------
    responsibilities: list[str] = Field(default_factory=list)
    core_tasks: list[str] = Field(default_factory=list)

    # -- Requirements -------------------------------------------------------------
    must_have_competencies: list[str] = Field(default_factory=list)
    nice_to_have_competencies: list[str] = Field(default_factory=list)
    tools_systems_equipment: list[str] = Field(default_factory=list)
    methods_processes_standards: list[str] = Field(default_factory=list)
    hard_requirements: list[str] = Field(default_factory=list)
    preferred_requirements: list[str] = Field(default_factory=list)
    years_of_experience_required: str | None = None
    type_of_experience_required: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    certifications_required: list[str] = Field(default_factory=list)
    licences_authorisations_required: list[str] = Field(default_factory=list)
    preferred_certifications: list[str] = Field(default_factory=list)
    language_requirements: list[str] = Field(default_factory=list)

    # -- Soft skills --------------------------------------------------------------
    soft_skills: list[str] = Field(default_factory=list)

    # -- Keywords -----------------------------------------------------------------
    domain_keywords: list[str] = Field(default_factory=list)
    ats_priority_keywords: list[str] = Field(default_factory=list)
    action_verbs: list[str] = Field(default_factory=list)

    # -- Context ------------------------------------------------------------------
    work_context_conditions: list[str] = Field(default_factory=list)
    regulatory_compliance_requirements: list[str] = Field(default_factory=list)
    business_goals: list[str] = Field(default_factory=list)
    success_signals: list[str] = Field(default_factory=list)

    # -- Benefits / admin ---------------------------------------------------------
    benefits_perks: list[str] = Field(default_factory=list)
    application_instructions: str | None = None
    posting_language: str | None = None
    raw_ats_phrases: list[str] = Field(default_factory=list)

    # -- Metadata -----------------------------------------------------------------
    confidence_scores: dict[str, float] = Field(default_factory=dict)
