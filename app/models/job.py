"""Validated job-description models for ClimateCareer-Agent."""

from datetime import date
from enum import StrEnum

from pydantic import Field, HttpUrl, model_validator

from app.models.candidate import StrictModel


class RequirementCategory(StrEnum):
    """Categories used to classify job requirements."""

    TECHNICAL_SKILL = "technical_skill"
    DOMAIN_SKILL = "domain_skill"
    EDUCATION = "education"
    EXPERIENCE = "experience"
    LANGUAGE = "language"
    LOCATION = "location"
    WORK_AUTHORIZATION = "work_authorization"
    LICENCE = "licence"
    TRAVEL = "travel"
    OTHER = "other"


class EmploymentType(StrEnum):
    """Common employment arrangements."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    UNKNOWN = "unknown"


class SeniorityLevel(StrEnum):
    """Normalized job seniority levels."""

    INTERNSHIP = "internship"
    ENTRY = "entry"
    ASSOCIATE = "associate"
    MID_LEVEL = "mid_level"
    SENIOR = "senior"
    LEAD = "lead"
    MANAGER = "manager"
    DIRECTOR = "director"
    UNKNOWN = "unknown"


class WorkArrangement(StrEnum):
    """Location arrangement stated in a job description."""

    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNSPECIFIED = "unspecified"


class JobRequirement(StrictModel):
    """One mandatory or preferred job requirement."""

    description: str = Field(min_length=1)
    category: RequirementCategory
    normalized_keywords: list[str] = Field(default_factory=list)
    minimum_years: float | None = Field(default=None, ge=0)
    evidence_text: str | None = None


class SalaryInformation(StrictModel):
    """Salary information explicitly published by the employer."""

    minimum: float | None = Field(default=None, ge=0)
    maximum: float | None = Field(default=None, ge=0)
    currency: str | None = None
    period: str | None = None
    raw_text: str | None = None

    @model_validator(mode="after")
    def validate_salary_range(self) -> "SalaryInformation":
        """Ensure that a stated salary range is logically valid."""
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("Minimum salary cannot exceed maximum salary.")
        return self


class JobDescription(StrictModel):
    """Structured information extracted from one job advertisement."""

    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    job_url: HttpUrl
    source: str = Field(min_length=1)

    location: str | None = None
    work_arrangement: WorkArrangement = WorkArrangement.UNSPECIFIED
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN

    date_posted: date | None = None
    application_deadline: date | None = None
    discovery_date: date

    responsibilities: list[str] = Field(default_factory=list)
    mandatory_requirements: list[JobRequirement] = Field(default_factory=list)
    preferred_requirements: list[JobRequirement] = Field(default_factory=list)

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    programming_languages: list[str] = Field(default_factory=list)
    ai_ml_tools: list[str] = Field(default_factory=list)
    cloud_tools: list[str] = Field(default_factory=list)
    domain_keywords: list[str] = Field(default_factory=list)

    required_education: str | None = None
    required_experience_years: float | None = Field(default=None, ge=0)
    work_authorization_text: str | None = None
    visa_information: str | None = None
    language_requirements: list[str] = Field(default_factory=list)
    travel_requirements: str | None = None
    required_documents: list[str] = Field(default_factory=list)

    salary: SalaryInformation | None = None
    raw_description: str = Field(min_length=1)
    extraction_confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_job_dates(self) -> "JobDescription":
        """Ensure that the deadline is not earlier than the posting date."""
        if (
            self.date_posted is not None
            and self.application_deadline is not None
            and self.application_deadline < self.date_posted
        ):
            raise ValueError("Application deadline cannot precede the posting date.")
        return self