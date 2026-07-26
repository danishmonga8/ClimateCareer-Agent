"""Offline tests for sanitized, read-only audit timeline aggregation."""

import ast
import inspect
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.models.audit_timeline import (
    AuditTimelineAction,
    AuditTimelineCategory,
    AuditTimelineFilters,
    AuditTimelinePageRequest,
    AuditTimelineSource,
    AuditTimelineStatus,
    CurrentCheckpointSummary,
)
from app.models.autofill import AutofillSession, AutofillSessionStatus
from app.models.dashboard_review import (
    ArtifactReferences,
    DashboardAuditEvent,
    DashboardReviewAction,
    DashboardReviewRecord,
    DashboardReviewStatus,
    DashboardWorkspace,
)
from app.models.discovery import JobSource
from app.services.audit_timeline_service import AuditTimelineService
from app.services.autofill_audit_service import AutofillAuditAction, AutofillAuditEvent
from app.services.autofill_repository import AutofillStorageError, StoredAutofillSession

JOB_KEY = "manual:fictional:job-1"
OTHER_JOB_KEY = "manual:fictional:job-2"
NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def _record(job_id: str = "job-1") -> DashboardReviewRecord:
    return DashboardReviewRecord(
        source=JobSource.MANUAL,
        source_board="fictional",
        source_job_id=job_id,
        artifacts=ArtifactReferences(discovery_snapshot="fictional.json"),
    )


def _workspace(*events: DashboardAuditEvent, include_other: bool = False) -> DashboardWorkspace:
    records = [_record()]
    if include_other:
        records.append(_record("job-2"))
    return DashboardWorkspace(records=records, audit_events=list(events))


def _review_event(
    *,
    event_id: str = "review-1",
    action: DashboardReviewAction = DashboardReviewAction.APPROVED,
    previous: DashboardReviewStatus = DashboardReviewStatus.AWAITING_REVIEW,
    current: DashboardReviewStatus = DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP,
    timestamp: datetime = NOW,
    job_key: str = JOB_KEY,
    note: str | None = "Private reviewer note",
    reviewer: str = "Fictional Reviewer",
) -> DashboardAuditEvent:
    return DashboardAuditEvent(
        event_id=event_id,
        job_key=job_key,
        previous_status=previous,
        new_status=current,
        action=action,
        reviewer_label=reviewer,
        reason_or_note=note,
        timestamp=timestamp,
    )


def _stored(
    *events: AutofillAuditEvent,
    job_key: str = JOB_KEY,
    status: AutofillSessionStatus = AutofillSessionStatus.AWAITING_START_CONFIRMATION,
) -> StoredAutofillSession:
    return StoredAutofillSession(
        session=AutofillSession(
            session_id="session-fictional-1",
            job_key=job_key,
            workspace_ref="workspace:fictional",
            profile_artifact_ref="artifact:profile:fictional",
            evidence_artifact_refs=("artifact:evidence:fictional",),
            expected_revision=1,
            material_version_ref="material:v1",
            status=status,
        ),
        events=tuple(events),
    )


def _autofill_event(
    *,
    action: AutofillAuditAction = AutofillAuditAction.SESSION_PREPARED,
    timestamp: datetime = NOW + timedelta(minutes=1),
    job_key: str = JOB_KEY,
    session_id: str = "session-fictional-1",
    field_identifier: str | None = None,
) -> AutofillAuditEvent:
    return AutofillAuditEvent(
        session_id=session_id,
        job_key=job_key,
        action=action,
        field_identifier=field_identifier,
        timestamp=timestamp,
    )


def test_aggregates_selected_job_with_redacted_note_and_reviewer_indicators() -> None:
    private_note = r"C:\private\review-note.txt candidate@example.test"
    private_reviewer = "candidate@example.test"
    page = AuditTimelineService().page(
        _workspace(_review_event(note=private_note, reviewer=private_reviewer)),
        JOB_KEY,
        autofill_session=_stored(
            _autofill_event(
                action=AutofillAuditAction.FIELD_PREPARED,
                field_identifier="candidate@example.test",
            )
        ),
    )

    assert [entry.source for entry in page.entries] == [
        AuditTimelineSource.AUTOFILL,
        AuditTimelineSource.DASHBOARD_REVIEW,
    ]
    review = page.entries[1]
    assert review.note_recorded and review.reviewer_recorded
    serialized = page.model_dump_json()
    for unsafe in (private_note, private_reviewer, "candidate@example.test", r"C:\private"):
        assert unsafe not in serialized
    assert page.checkpoint_summary is not None
    assert page.checkpoint_summary.label == "Current checkpoint summary"
    assert page.counts.total == 2


def test_selected_job_scoping_does_not_mix_valid_other_job_history() -> None:
    page = AuditTimelineService().page(
        _workspace(
            _review_event(event_id="current"),
            _review_event(event_id="other", job_key=OTHER_JOB_KEY),
            include_other=True,
        ),
        JOB_KEY,
    )

    assert len(page.entries) == 1
    assert page.entries[0].job_key == JOB_KEY
    assert not page.integrity_findings


def test_invalid_linkage_and_conflicting_transition_are_visible_but_non_blocking() -> None:
    conflicting = _review_event(
        action=DashboardReviewAction.APPROVED,
        current=DashboardReviewStatus.REJECTED,
    )
    invalid = _review_event(event_id="orphan", job_key="manual:fictional:missing")
    page = AuditTimelineService().page(_workspace(conflicting, invalid), JOB_KEY)

    codes = {finding.code for finding in page.integrity_findings}
    assert "AUDIT_DASHBOARD_TRANSITION_CONFLICT" in codes
    assert "AUDIT_DASHBOARD_EVENT_JOB_INVALID" in codes
    assert len(page.entries) == 1
    assert page.entries[0].action == AuditTimelineAction.APPROVED


def test_deterministic_newest_first_tie_breaking_and_cursor_continuation() -> None:
    first = _review_event(event_id="a", timestamp=NOW)
    second = _review_event(event_id="b", timestamp=NOW)
    third = _review_event(event_id="c", timestamp=NOW - timedelta(seconds=1))
    service = AuditTimelineService()
    initial = service.page(
        _workspace(first, second, third), JOB_KEY, request=AuditTimelinePageRequest(page_size=1)
    )
    repeated = service.page(
        _workspace(first, second, third), JOB_KEY, request=AuditTimelinePageRequest(page_size=1)
    )
    continuation = service.page(
        _workspace(first, second, third),
        JOB_KEY,
        request=AuditTimelinePageRequest(page_size=1, cursor=initial.next_cursor),
    )

    assert initial.entries == repeated.entries
    assert initial.next_cursor
    assert continuation.entries
    assert continuation.entries[0].source_key != initial.entries[0].source_key


def test_cursor_and_page_size_fail_safely() -> None:
    service = AuditTimelineService()
    page = service.page(
        _workspace(_review_event()),
        JOB_KEY,
        request=AuditTimelinePageRequest(cursor="not-a-valid-cursor"),
    )

    assert not page.entries
    assert {finding.code for finding in page.integrity_findings} == {"AUDIT_CURSOR_INVALID"}
    with pytest.raises(ValidationError):
        AuditTimelinePageRequest(page_size=101)
    with pytest.raises(ValidationError):
        AuditTimelineFilters(
            from_timestamp=NOW,
            to_timestamp=NOW - timedelta(seconds=1),
        )


def test_stale_cursor_and_individual_or_combined_structured_filters() -> None:
    review = _review_event(
        action=DashboardReviewAction.REJECTED, current=DashboardReviewStatus.REJECTED
    )
    autofill = _autofill_event(action=AutofillAuditAction.SESSION_PREPARED)
    service = AuditTimelineService()
    initial = service.page(
        _workspace(review),
        JOB_KEY,
        autofill_session=_stored(autofill),
        request=AuditTimelinePageRequest(page_size=1),
    )
    stale = service.page(
        _workspace(review),
        JOB_KEY,
        filters=AuditTimelineFilters(sources=frozenset({AuditTimelineSource.DASHBOARD_REVIEW})),
        request=AuditTimelinePageRequest(cursor=initial.next_cursor or "invalid"),
    )
    filtered = service.page(
        _workspace(review),
        JOB_KEY,
        filters=AuditTimelineFilters(
            sources=frozenset({AuditTimelineSource.DASHBOARD_REVIEW}),
            categories=frozenset({AuditTimelineCategory.REVIEW_DECISION}),
            actions=frozenset({AuditTimelineAction.REJECTED}),
            statuses=frozenset({AuditTimelineStatus.REJECTED}),
        ),
    )

    assert "AUDIT_CURSOR_STALE" in {finding.code for finding in stale.integrity_findings}
    assert [entry.action for entry in filtered.entries] == [AuditTimelineAction.REJECTED]


def test_duplicate_malformed_and_cross_job_autofill_records_are_sanitized() -> None:
    duplicate_one = _review_event(event_id="same")
    duplicate_two = _review_event(event_id="same", timestamp=NOW - timedelta(seconds=1))
    malformed = _review_event(event_id="bad").model_copy(update={"action": "unsupported"})
    mismatch = _stored(_autofill_event(job_key=OTHER_JOB_KEY))
    page = AuditTimelineService().page(
        _workspace(duplicate_one, duplicate_two, malformed), JOB_KEY, autofill_session=mismatch
    )

    codes = {finding.code for finding in page.integrity_findings}
    assert {
        "AUDIT_DUPLICATE_DASHBOARD_IDENTIFIER",
        "AUDIT_DUPLICATE_SOURCE_KEY",
        "AUDIT_DASHBOARD_EVENT_MALFORMED",
        "AUDIT_AUTOFILL_EVENT_LINKAGE_INVALID",
    }.issubset(codes)
    assert len(page.entries) == 1


def test_missing_timestamp_or_malformed_source_is_safely_visible() -> None:
    missing_timestamp = _review_event(event_id="missing-time").model_copy(
        update={"timestamp": None}
    )

    class MalformedRepository:
        def find_for_job(self, _job_key: str):
            return object()

    page = AuditTimelineService(autofill_session_repository=MalformedRepository()).page(
        _workspace(missing_timestamp), JOB_KEY
    )

    assert not page.entries
    assert {
        "AUDIT_DASHBOARD_EVENT_MALFORMED",
        "AUDIT_AUTOFILL_SOURCE_MALFORMED",
    }.issubset({finding.code for finding in page.integrity_findings})


def test_current_checkpoint_summary_is_explicitly_separate_from_historical_entries() -> None:
    summary = CurrentCheckpointSummary(
        status=AuditTimelineStatus.AWAITING_START_CONFIRMATION,
        reference_key="audit:0123456789abcdef0123456789abcdef",
        compatible=False,
    )
    page = AuditTimelineService().page(
        _workspace(_review_event()), JOB_KEY, checkpoint_summary=summary
    )

    assert page.checkpoint_summary == summary
    assert all(entry.action != "current_checkpoint_summary" for entry in page.entries)


def test_unavailable_autofill_source_and_inconsistent_checkpoint_are_non_blocking() -> None:
    class UnavailableRepository:
        def find_for_job(self, _job_key: str):
            raise AutofillStorageError("internal path must not be exposed")

    unavailable = AuditTimelineService(autofill_session_repository=UnavailableRepository()).page(
        _workspace(_review_event()), JOB_KEY
    )
    inconsistent = AuditTimelineService().page(
        _workspace(_review_event()),
        JOB_KEY,
        autofill_session=_stored(
            _autofill_event(action=AutofillAuditAction.FIELD_POPULATED, field_identifier="email"),
            status=AutofillSessionStatus.AWAITING_POPULATION_CONFIRMATION,
        ),
    )

    assert unavailable.entries
    assert "AUDIT_AUTOFILL_SOURCE_UNAVAILABLE" in {
        finding.code for finding in unavailable.integrity_findings
    }
    assert inconsistent.checkpoint_summary is not None
    assert not inconsistent.checkpoint_summary.compatible
    assert "AUDIT_CURRENT_CHECKPOINT_INCONSISTENT" in {
        finding.code for finding in inconsistent.integrity_findings
    }


def test_no_reachable_audit_timeline_module_imports_external_execution_capability() -> None:
    from app.dashboard import views
    from app.services import audit_timeline_service

    prohibited = {
        "httpx",
        "requests",
        "subprocess",
        "smtplib",
        "webbrowser",
        "selenium",
        "playwright",
    }
    for module in (audit_timeline_service, views):
        tree = ast.parse(inspect.getsource(module))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not imports.intersection(prohibited)
