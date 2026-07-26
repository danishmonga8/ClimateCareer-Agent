"""Validated models for the local human-approval dashboard."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from app.models.candidate import StrictModel
from app.models.discovery import JobSource


class DashboardReviewStatus(StrEnum):
    """Internal review states; none represent an external submission."""

    AWAITING_REVIEW = "awaiting_review"
    APPROVED_FOR_MANUAL_NEXT_STEP = "approved_for_manual_next_step"
    REVISION_REQUESTED = "revision_requested"
    REJECTED = "rejected"


class DashboardReviewAction(StrEnum):
    """Append-only human review actions."""

    APPROVED = "approved"
    REVISION_REQUESTED = "revision_requested"
    REJECTED = "rejected"
    RESUBMITTED_FOR_REVIEW = "resubmitted_for_review"


class MaterialType(StrEnum):
    """Material types the dashboard can preview from linked artifacts."""

    TAILORED_RESUME = "tailored_resume"
    COVER_LETTER = "cover_letter"
    APPLICATION_ANSWERS = "application_answers"
    SUPPORTING_EVIDENCE = "supporting_evidence"


class MaterialMetadata(StrictModel):
    """Metadata only; material content remains in its existing artifact."""

    material_type: MaterialType
    version: str = Field(min_length=1)
    generated_at: datetime | None = None
    review_status: DashboardReviewStatus = DashboardReviewStatus.AWAITING_REVIEW

    @field_validator("generated_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Material timestamps must include a timezone.")
        return value


class ArtifactReferences(StrictModel):
    """Private paths to existing Phase 1-3 JSON artifacts."""

    discovery_snapshot: str = Field(min_length=1)
    scoring_result: str | None = None
    personalized_application: str | None = None
    profile_artifact_ref: str | None = None
    evidence_artifact_refs: list[str] = Field(default_factory=list)

    @field_validator("profile_artifact_ref", "evidence_artifact_refs", mode="before")
    @classmethod
    def require_opaque_reference(cls, value):
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item is not None and (
                "/" in item
                or "\\" in item
                or item in {".", ".."}
                or ".." in item
                or (len(item) > 1 and item[0].isalpha() and item[1] == ":")
            ):
                raise ValueError("Artifact references must be opaque logical identifiers.")
        return value

    @field_validator("discovery_snapshot", "scoring_result", "personalized_application")
    @classmethod
    def require_json_reference(cls, value: str | None) -> str | None:
        if value is not None and not value.lower().endswith(".json"):
            raise ValueError("Dashboard artifact references must point to JSON files.")
        return value


class DashboardReviewRecord(StrictModel):
    """Dashboard metadata for one stable discovered-job identity."""

    source: JobSource
    source_board: str = Field(min_length=1)
    source_job_id: str = Field(min_length=1)
    artifacts: ArtifactReferences
    status: DashboardReviewStatus = DashboardReviewStatus.AWAITING_REVIEW
    revision: int = Field(default=0, ge=0)
    materials: list[MaterialMetadata] = Field(default_factory=list)

    @property
    def job_key(self) -> str:
        """Return the stable Phase 3 job identity used by the dashboard."""
        return f"{self.source.value}:{self.source_board}:{self.source_job_id}"


class DashboardAuditEvent(StrictModel):
    """One immutable internal review event."""

    event_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    job_key: str = Field(min_length=1)
    previous_status: DashboardReviewStatus
    new_status: DashboardReviewStatus
    action: DashboardReviewAction
    reviewer_label: str = Field(min_length=1)
    reason_or_note: str | None = None
    material_version: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("Audit timestamps must include a timezone.")
        return value


class DashboardWorkspace(StrictModel):
    """Private local workspace referencing, but never copying, artifacts."""

    records: list[DashboardReviewRecord] = Field(default_factory=list)
    audit_events: list[DashboardAuditEvent] = Field(default_factory=list)
    schema_version: str = "1.0"

    @model_validator(mode="after")
    def validate_unique_records(self) -> "DashboardWorkspace":
        job_keys = [record.job_key for record in self.records]
        if len(job_keys) != len(set(job_keys)):
            raise ValueError("Dashboard workspace cannot contain duplicate job records.")
        return self
