"""Pydantic schemas for candidate profile LLM extraction.

Define the structured data model that Ollama fills from raw CV text.
All fields default to empty strings or lists so missing sections in a CV
produce valid instances rather than validation errors.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DateRange(BaseModel):
    """Represent a time period with optional start and end."""

    start: str = ""
    end: str = ""


class WorkExperience(BaseModel):
    """Represent one position in the candidate's employment history."""

    company: str = ""
    position: str = ""
    period: DateRange = Field(default_factory=DateRange)
    responsibilities: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class Education(BaseModel):
    """Represent one educational qualification."""

    institution: str = ""
    degree: str = ""
    period: DateRange = Field(default_factory=DateRange)
    coursework: list[str] = Field(default_factory=list)
    grade: str = ""


class Certification(BaseModel):
    """Represent one licence or certification."""

    name: str = ""
    issuer: str = ""
    issue_date: str = ""
    skills: list[str] = Field(default_factory=list)


class Project(BaseModel):
    """Represent one personal or professional project."""

    name: str = ""
    period: str = ""
    description: str = ""
    outcome: str = ""
    technologies: list[str] = Field(default_factory=list)


class HardSkill(BaseModel):
    """Represent one technical skill with evidence of proficiency."""

    skill: str = ""
    proficiency: str = ""
    years_experience: str = ""
    evidence: str = ""


class Language(BaseModel):
    """Represent one spoken or written language."""

    language: str = ""
    level: str = ""


class Volunteering(BaseModel):
    """Represent one volunteering role."""

    role: str = ""
    organization: str = ""
    cause: str = ""
    period: DateRange = Field(default_factory=DateRange)
    description: str = ""
    skills: list[str] = Field(default_factory=list)


class Publication(BaseModel):
    """Represent one published work."""

    title: str = ""
    publisher: str = ""
    date: str = ""
    description: str = ""
    topics: list[str] = Field(default_factory=list)


class HonorAward(BaseModel):
    """Represent one honour or award."""

    title: str = ""
    issuer: str = ""
    date: str = ""
    description: str = ""


class Course(BaseModel):
    """Represent one completed course."""

    name: str = ""
    provider: str = ""
    period: DateRange = Field(default_factory=DateRange)
    skills: list[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    """Structured representation of all information extracted from a CV."""

    # Personal information — stored but not used for job matching
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    street: str = ""
    city: str = ""
    location: str = ""
    phone: str = ""

    # Professional identity
    target_role: str = ""
    seniority_level: str = ""
    leadership_experience: str = ""

    # Preferences
    salary_expectation: str = ""
    work_model: str = ""
    availability: str = ""
    employment_types: list[str] = Field(default_factory=list)

    # Experience and education
    work_experience: list[WorkExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    courses: list[Course] = Field(default_factory=list)
    volunteering: list[Volunteering] = Field(default_factory=list)

    # Skills
    soft_skills: list[str] = Field(default_factory=list)
    hard_skills: list[HardSkill] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)

    # Achievements
    publications: list[Publication] = Field(default_factory=list)
    honors_awards: list[HonorAward] = Field(default_factory=list)
