"""Sanitized append-only audit behavior for fictional local autofill sessions."""

from app.services.autofill_audit_service import (
    AutofillAuditAction,
    AutofillAuditEvent,
    append_event,
)


def test_equivalent_retry_event_is_idempotent_and_contains_identifiers_only() -> None:
    first = AutofillAuditEvent(
        session_id="session:fictional:1",
        job_key="manual:fictional:job-1",
        action=AutofillAuditAction.FIELD_POPULATED,
        field_identifier="email",
    )
    duplicate = AutofillAuditEvent(
        session_id="session:fictional:1",
        job_key="manual:fictional:job-1",
        action=AutofillAuditAction.FIELD_POPULATED,
        field_identifier="email",
    )

    events = append_event([], first)
    assert append_event(events, duplicate) == events
    payload = events[0].model_dump()
    assert set(payload) == {"session_id", "job_key", "action", "field_identifier", "timestamp"}
    assert "candidate@example.test" not in events[0].model_dump_json()
