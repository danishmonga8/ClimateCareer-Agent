"""Sanitized append-only local audit events for mock-only autofill sessions."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field

from app.models.candidate import StrictModel


class AutofillAuditAction(StrEnum):
    SESSION_PREPARED = "session_prepared"
    SESSION_CONFIRMED = "session_confirmed"
    FIELD_PREPARED = "field_prepared"
    FIELD_POPULATED = "field_populated"
    FIELD_SKIPPED = "field_skipped"
    SESSION_CANCELLED = "session_cancelled"
    SESSION_BLOCKED = "session_blocked"
    SESSION_COMPLETED = "session_completed"


class AutofillAuditEvent(StrictModel):
    session_id: str = Field(min_length=1)
    job_key: str = Field(min_length=1)
    action: AutofillAuditAction
    field_identifier: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


def append_event(
    events: list[AutofillAuditEvent], event: AutofillAuditEvent
) -> list[AutofillAuditEvent]:
    """Append a unique sanitized event without retaining any field value."""
    if any(
        existing.session_id == event.session_id
        and existing.action == event.action
        and existing.field_identifier == event.field_identifier
        for existing in events
    ):
        return events
    return [*events, event]
