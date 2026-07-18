"""Validated candidate-profile models for ClimateCareer-Agent."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class StrictModel(BaseModel):
    """Base model that rejects unexpected fields."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class VerificationStatus(StrEnum):
    """Verification status of candidate information."""

    VERIFIED = "verified"
    REQUIRES_CONFIRMATION = "requires_confirmation"


class SkillCategory(StrEnum):
    """Supported skill categories."""

    PROGRAMMING = "programming"
    MACHINE_LEARNING = "machine_learning"
    GENERATIVE_AI = "generative_ai"
    STATISTICAL_MODELLING = "statistical_modelling"
    GEOSPATIAL = "geospatial"
    DOMAIN_EXPERTISE = "domain_expertise"
    OTHER = "other"


class WorkMode(StrEnum):
    """Preferred working arrangements."""

    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    FLEXIBLE = "flexible"


class ContactInformation(StrictModel):
    """Candidate contact information extracted from a verified source."""

    emails: list[str] = Field(default_factory=list)
    phone: str | None = None
    location: str | None = None

    @field_validator("emails")
    @classmethod
    def validate_emails(cls, emails: list[str]) -> list[str]:
        """Perform a basic validation without changing the original address."""
        for email in emails:
            if "@" not in email or "." not in email.split("@")[-1]:
                raise ValueError(f"Invalid email address: {email}")
        return emails


class ProfessionalLink(StrictModel):
    """A verified professional or portfolio link."""

    label: str = Field(min_length=1)
    url: HttpUrl


class EducationRecord(StrictModel):
    """One verified education record."""

    degree: str = Field(min_length=1)
    field_of_study: str | None = None
    institution: str = Field(min_length=1)
    start_year: int | None = Field(default=None, ge=1950, le=2100)
    end_year: int | None = Field(default=None, ge=1950, le=2100)
    currently_enrolled: bool = False
    verification_status: VerificationStatus = VerificationStatus.VERIFIED


class ExperienceRecord(StrictModel):
    """One verified employment or research-experience record."""

    title: str = Field(min_length=1)
    organization: str = Field(min_length=1)
    start_date: str | None = None
    end_date: str | None = None
    currently_active: bool = False
    highlights: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.VERIFIED


class ProjectRecord(StrictModel):
    """One verified candidate project."""

    name: str = Field(min_length=1)
    description: str
    tools: list[str] = Field(default_factory=list)
    project_url: HttpUrl | None = None
    repository_url: HttpUrl | None = None
    verification_status: VerificationStatus = VerificationStatus.VERIFIED


class PublicationRecord(StrictModel):
    """A publication or conference presentation."""

    title: str
    venue: str | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)
    publication_type: str | None = None
    url: HttpUrl | None = None
    verification_status: VerificationStatus = VerificationStatus.VERIFIED


class CertificationOrAward(StrictModel):
    """A verified certification, rank, honour, or award."""

    name: str = Field(min_length=1)
    issuing_organization: str | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)
    category: str
    verification_status: VerificationStatus = VerificationStatus.VERIFIED


class SkillRecord(StrictModel):
    """A verified candidate skill."""

    name: str = Field(min_length=1)
    category: SkillCategory
    evidence: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.VERIFIED


class CareerPreferences(StrictModel):
    """Candidate-controlled job and mobility preferences."""

    target_job_titles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    work_modes: list[WorkMode] = Field(default_factory=list)
    open_to_relocation: bool | None = None
    notes: str | None = None


class SensitiveApplicationInformation(StrictModel):
    """Information that must be supplied or confirmed manually."""

    work_authorization: str | None = None
    visa_sponsorship_required: bool | None = None
    notice_period: str | None = None
    salary_expectation: str | None = None
    demographic_answers: dict[str, str] = Field(default_factory=dict)
    requires_explicit_confirmation: bool = True


class CandidateProfile(StrictModel):
    """Complete verified profile used throughout the application workflow."""

    full_name: str = Field(min_length=1)
    professional_headline: str | None = None
    professional_summary: str | None = None
    contact: ContactInformation
    links: list[ProfessionalLink] = Field(default_factory=list)
    education: list[EducationRecord] = Field(default_factory=list)
    experience: list[ExperienceRecord] = Field(default_factory=list)
    projects: list[ProjectRecord] = Field(default_factory=list)
    publications: list[PublicationRecord] = Field(default_factory=list)
    certifications_and_awards: list[CertificationOrAward] = Field(default_factory=list)
    skills: list[SkillRecord] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    preferences: CareerPreferences = Field(default_factory=CareerPreferences)
    sensitive_information: SensitiveApplicationInformation = Field(
        default_factory=SensitiveApplicationInformation
    )
    source_document: str = Field(min_length=1)