"""Evidence-bank models for verified candidate claims."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from app.models.candidate import StrictModel


class EvidenceStatus(StrEnum):
    """Verification status of one candidate claim."""

    VERIFIED = "verified"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    REJECTED = "rejected"


class EvidenceRecord(StrictModel):
    """One traceable candidate claim and its supporting evidence."""

    evidence_id: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    source_document: str = Field(min_length=1)
    source_section: str | None = None
    source_excerpt: str | None = Field(default=None, max_length=500)

    associated_project: str | None = None
    tools: list[str] = Field(default_factory=list)
    domain: str | None = None
    quantitative_evidence: list[str] = Field(default_factory=list)
    suitable_job_families: list[str] = Field(default_factory=list)

    confidence_score: float = Field(ge=0, le=1)
    status: EvidenceStatus
    allowed_in_resume: bool = False
    allowed_in_cover_letter: bool = False
    requires_confirmation: bool = True
    notes: str | None = None

    @model_validator(mode="after")
    def enforce_safe_usage(self) -> "EvidenceRecord":
        """Prevent unverified claims from being used in applications."""
        if self.status != EvidenceStatus.VERIFIED and (
            self.allowed_in_resume or self.allowed_in_cover_letter
        ):
            raise ValueError("Unverified evidence cannot be used in application documents.")

        if self.status == EvidenceStatus.VERIFIED and self.requires_confirmation:
            raise ValueError("Verified evidence cannot remain marked for confirmation.")

        return self


class EvidenceBank(StrictModel):
    """Collection of traceable evidence records for one candidate."""

    candidate_name: str = Field(min_length=1)
    source_document: str = Field(min_length=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    records: list[EvidenceRecord] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = "1.0"
