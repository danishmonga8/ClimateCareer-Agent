"""Sanitized, read-only projections of local audit sources.

These models deliberately describe *visibility*, not a new audit store.  They
contain stable internal identifiers and statuses only; source records remain
authoritative in their existing repositories.
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.models.candidate import StrictModel


class AuditTimelineSource(StrEnum):
    """Existing authoritative sources that may contribute timeline entries."""

    DASHBOARD_REVIEW = "dashboard_review"
    AUTOFILL = "autofill"


class AuditTimelineCategory(StrEnum):
    """Safe classifications for visible internal audit activity."""

    REVIEW_DECISION = "review_decision"
    AUTOFILL_SESSION = "autofill_session"
    AUTOFILL_FIELD = "autofill_field"


class AuditTimelineAction(StrEnum):
    """The fixed set of safe actions available from existing audit sources."""

    APPROVED = "approved"
    REVISION_REQUESTED = "revision_requested"
    REJECTED = "rejected"
    RESUBMITTED_FOR_REVIEW = "resubmitted_for_review"
    SESSION_PREPARED = "session_prepared"
    SESSION_CONFIRMED = "session_confirmed"
    FIELD_PREPARED = "field_prepared"
    FIELD_POPULATED = "field_populated"
    FIELD_SKIPPED = "field_skipped"
    SESSION_CANCELLED = "session_cancelled"
    SESSION_BLOCKED = "session_blocked"
    SESSION_COMPLETED = "session_completed"


class AuditTimelineStatus(StrEnum):
    """Internal status labels that never imply an external action."""

    AWAITING_REVIEW = "awaiting_review"
    APPROVED_FOR_MANUAL_NEXT_STEP = "approved_for_manual_next_step"
    REVISION_REQUESTED = "revision_requested"
    REJECTED = "rejected"
    AWAITING_START_CONFIRMATION = "awaiting_start_confirmation"
    AWAITING_POPULATION_CONFIRMATION = "awaiting_population_confirmation"
    PREPARED_FOR_MANUAL_FIELD_ENTRY = "prepared_for_manual_field_entry"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class AuditStatusTransition(StrictModel):
    """A sanitized status transition, when an audit source has one."""

    previous: AuditTimelineStatus | None = None
    current: AuditTimelineStatus | None = None


class AuditTimelineEntry(StrictModel):
    """One safe read-only entry projected from an existing audit source."""

    job_key: str = Field(min_length=1)
    source: AuditTimelineSource
    category: AuditTimelineCategory
    action: AuditTimelineAction
    transition: AuditStatusTransition | None = None
    timestamp: datetime
    source_key: str = Field(pattern=r"^audit:[a-f0-9]{32}$")
    note_recorded: bool = False
    reviewer_recorded: bool = False

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("Timeline timestamps must include a timezone.")
        return value


class AuditTimelineFilters(StrictModel):
    """Structured-only filtering; free-text source data is never searchable."""

    sources: frozenset[AuditTimelineSource] = frozenset()
    categories: frozenset[AuditTimelineCategory] = frozenset()
    actions: frozenset[AuditTimelineAction] = frozenset()
    statuses: frozenset[AuditTimelineStatus] = frozenset()
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None

    @field_validator("from_timestamp", "to_timestamp")
    @classmethod
    def require_timezones(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Timeline filters must include a timezone.")
        return value

    @model_validator(mode="after")
    def validate_time_range(self) -> "AuditTimelineFilters":
        if self.from_timestamp and self.to_timestamp and self.from_timestamp > self.to_timestamp:
            raise ValueError("Timeline time ranges must be chronological.")
        return self


class AuditTimelinePageRequest(StrictModel):
    """A bounded, opaque cursor request for a filtered timeline."""

    page_size: int = Field(default=25, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=512)


class AuditTimelineCounts(StrictModel):
    """Safe aggregate counts for the filtered result set."""

    total: int = Field(ge=0)
    dashboard_review: int = Field(ge=0)
    autofill: int = Field(ge=0)
    review_decisions: int = Field(ge=0)
    autofill_sessions: int = Field(ge=0)
    autofill_fields: int = Field(ge=0)


class AuditIntegritySeverity(StrEnum):
    """Read-only visibility severity; never a decision gate."""

    WARNING = "warning"


class AuditIntegrityFinding(StrictModel):
    """Sanitized source-integrity information with no payload or path data."""

    code: str = Field(pattern=r"^AUDIT_[A-Z0-9_]+$")
    severity: AuditIntegritySeverity = AuditIntegritySeverity.WARNING
    message: str = Field(min_length=1, max_length=240)
    recovery_guidance: str = Field(min_length=1, max_length=240)
    source: AuditTimelineSource | None = None


class CurrentCheckpointSummary(StrictModel):
    """Current local checkpoint metadata, explicitly not historical evidence."""

    label: Literal["Current checkpoint summary"] = "Current checkpoint summary"
    source: AuditTimelineSource = AuditTimelineSource.AUTOFILL
    status: AuditTimelineStatus
    reference_key: str = Field(pattern=r"^audit:[a-f0-9]{32}$")
    compatible: bool


class AuditTimelinePage(StrictModel):
    """A read-only, sanitized page of selected-job audit visibility."""

    job_key: str = Field(min_length=1)
    entries: tuple[AuditTimelineEntry, ...] = ()
    next_cursor: str | None = Field(default=None, max_length=512)
    counts: AuditTimelineCounts
    integrity_findings: tuple[AuditIntegrityFinding, ...] = ()
    checkpoint_summary: CurrentCheckpointSummary | None = None
