"""Validated models for publicly discovered job listings."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field, HttpUrl, field_validator

from app.models.candidate import StrictModel
from app.models.job import EmploymentType, JobDescription, WorkArrangement
from app.models.scoring import JobRelevanceScore


class JobSource(StrEnum):
    """Supported public job-discovery sources."""

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    COMPANY_SITE = "company_site"
    LINKEDIN_LINK = "linkedin_link"
    WEB_SEARCH = "web_search"
    MANUAL = "manual"


class DiscoveredJob(StrictModel):
    """One normalized job collected from a public source."""

    source: JobSource
    source_board: str = Field(min_length=1)
    source_job_id: str = Field(min_length=1)

    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    job_url: HttpUrl
    apply_url: HttpUrl | None = None

    location: str | None = None
    work_arrangement: WorkArrangement = WorkArrangement.UNSPECIFIED
    employment_type: EmploymentType = EmploymentType.UNKNOWN

    department: str | None = None
    team: str | None = None
    description: str = Field(min_length=1)
    salary_text: str | None = None

    date_posted: datetime | None = None
    date_updated: datetime | None = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator(
        "source_board",
        "source_job_id",
        "company",
        "title",
        "description",
    )
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        """Reject empty or whitespace-only required text."""

        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("Required text fields cannot be blank.")
        return cleaned_value

    @field_validator("date_posted", "date_updated", "discovered_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        """Keep timestamps unambiguous across job-board regions."""
        if value is not None and value.utcoffset() is None:
            raise ValueError("Discovery timestamps must include a timezone.")
        return value


class DiscoverySnapshot(StrictModel):
    """A private, validated snapshot of normalized public listings."""

    jobs: list[DiscoveredJob] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = "1.0"

    @field_validator("collected_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Require an unambiguous snapshot timestamp."""
        if value.utcoffset() is None:
            raise ValueError("Snapshot timestamps must include a timezone.")
        return value


class DiscoveryEvaluation(StrictModel):
    """A discovered listing and its parsed, explainable score outputs."""

    discovered_job: DiscoveredJob
    parsed_job: JobDescription
    relevance_score: JobRelevanceScore
