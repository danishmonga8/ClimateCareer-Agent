"""Read-only aggregation of existing local audit sources.

The service is intentionally a projection layer.  It never writes, repairs,
migrates, or otherwise changes dashboard, autofill, or workflow history.
"""

import base64
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from app.models.audit_timeline import (
    AuditIntegrityFinding,
    AuditStatusTransition,
    AuditTimelineAction,
    AuditTimelineCategory,
    AuditTimelineCounts,
    AuditTimelineEntry,
    AuditTimelineFilters,
    AuditTimelinePage,
    AuditTimelinePageRequest,
    AuditTimelineSource,
    AuditTimelineStatus,
    CurrentCheckpointSummary,
)
from app.models.autofill import AutofillSession, AutofillSessionStatus
from app.models.dashboard_review import (
    DashboardAuditEvent,
    DashboardReviewAction,
    DashboardReviewStatus,
    DashboardWorkspace,
)
from app.services.autofill_audit_service import AutofillAuditAction, AutofillAuditEvent
from app.services.autofill_repository import (
    AutofillSessionRepository,
    StoredAutofillSession,
)

_DASHBOARD_STATUS = {
    DashboardReviewStatus.AWAITING_REVIEW: AuditTimelineStatus.AWAITING_REVIEW,
    DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP: AuditTimelineStatus.APPROVED_FOR_MANUAL_NEXT_STEP,
    DashboardReviewStatus.REVISION_REQUESTED: AuditTimelineStatus.REVISION_REQUESTED,
    DashboardReviewStatus.REJECTED: AuditTimelineStatus.REJECTED,
}

_AUTOFILL_STATUS = {
    "awaiting_start_confirmation": AuditTimelineStatus.AWAITING_START_CONFIRMATION,
    "awaiting_population_confirmation": AuditTimelineStatus.AWAITING_POPULATION_CONFIRMATION,
    "populated": AuditTimelineStatus.PREPARED_FOR_MANUAL_FIELD_ENTRY,
    "completed": AuditTimelineStatus.PREPARED_FOR_MANUAL_FIELD_ENTRY,
    "cancelled": AuditTimelineStatus.CANCELLED,
    "blocked": AuditTimelineStatus.BLOCKED,
}


@dataclass(frozen=True)
class AuditTimelineService:
    """Build selected-job audit pages from injected, existing local sources."""

    autofill_session_repository: AutofillSessionRepository | None = None

    def page(
        self,
        workspace: DashboardWorkspace,
        job_key: str,
        *,
        filters: AuditTimelineFilters | None = None,
        request: AuditTimelinePageRequest | None = None,
        autofill_session: StoredAutofillSession | None = None,
        checkpoint_summary: CurrentCheckpointSummary | None = None,
    ) -> AuditTimelinePage:
        """Return a deterministic, sanitized projection without mutating any source."""
        active_filters = filters or AuditTimelineFilters()
        page_request = request or AuditTimelinePageRequest()
        findings: list[AuditIntegrityFinding] = []
        entries: list[AuditTimelineEntry] = []

        records = {record.job_key for record in workspace.records}
        if job_key not in records:
            findings.append(
                _finding(
                    "AUDIT_JOB_NOT_IN_WORKSPACE",
                    "The selected job is not available in this workspace.",
                    "Reload the selected review record before viewing its audit history.",
                )
            )
        else:
            _validate_dashboard_linkage(workspace.audit_events, records, findings)
            entries.extend(self._dashboard_entries(workspace.audit_events, job_key, findings))
            stored = autofill_session or self._load_autofill(job_key, findings)
            if stored is not None and _valid_stored_session(stored):
                entries.extend(self._autofill_entries(stored, job_key, findings))
                if checkpoint_summary is None:
                    checkpoint_summary = _session_summary(stored)
            elif stored is not None:
                findings.append(
                    _finding(
                        "AUDIT_AUTOFILL_SOURCE_MALFORMED",
                        "The local autofill audit source is malformed or unsupported.",
                        "Restore a valid local autofill session source.",
                        AuditTimelineSource.AUTOFILL,
                    )
                )

        entries = _deduplicate(entries, findings)
        filtered = _filter(entries, active_filters)
        ordered = sorted(filtered, key=_sort_key)
        counts = _counts(ordered)
        page_entries, next_cursor = _paginate(ordered, page_request, findings)
        return AuditTimelinePage(
            job_key=job_key,
            entries=tuple(page_entries),
            next_cursor=next_cursor,
            counts=counts,
            integrity_findings=tuple(_dedupe_findings(findings)),
            checkpoint_summary=checkpoint_summary,
        )

    def _load_autofill(
        self, job_key: str, findings: list[AuditIntegrityFinding]
    ) -> StoredAutofillSession | None:
        if self.autofill_session_repository is None:
            return None
        try:
            stored = self.autofill_session_repository.find_for_job(job_key)
            return stored
        except Exception:  # noqa: BLE001 - source failures must remain sanitized in a read-only view.
            findings.append(
                _finding(
                    "AUDIT_AUTOFILL_SOURCE_UNAVAILABLE",
                    "The local autofill audit source is unavailable.",
                    "Restore the local session source before relying on its audit visibility.",
                    AuditTimelineSource.AUTOFILL,
                )
            )
            return None

    @staticmethod
    def _dashboard_entries(
        events: Iterable[DashboardAuditEvent],
        job_key: str,
        findings: list[AuditIntegrityFinding],
    ) -> list[AuditTimelineEntry]:
        entries: list[AuditTimelineEntry] = []
        identifiers: set[str] = set()
        for event in events:
            if not _valid_dashboard_event(event):
                findings.append(
                    _finding(
                        "AUDIT_DASHBOARD_EVENT_MALFORMED",
                        "A dashboard audit event is malformed or unsupported.",
                        "Inspect the local dashboard audit source.",
                        AuditTimelineSource.DASHBOARD_REVIEW,
                    )
                )
                continue
            if event.job_key != job_key:
                continue
            if event.event_id in identifiers:
                findings.append(
                    _finding(
                        "AUDIT_DUPLICATE_DASHBOARD_IDENTIFIER",
                        "Duplicate dashboard audit identifiers were detected.",
                        "Inspect the local dashboard audit source before relying on duplicate events.",
                        AuditTimelineSource.DASHBOARD_REVIEW,
                    )
                )
            identifiers.add(event.event_id)
            transition = _dashboard_transition(event, findings)
            if transition is None:
                continue
            entries.append(
                AuditTimelineEntry(
                    job_key=job_key,
                    source=AuditTimelineSource.DASHBOARD_REVIEW,
                    category=AuditTimelineCategory.REVIEW_DECISION,
                    action=AuditTimelineAction(event.action.value),
                    transition=transition,
                    timestamp=event.timestamp,
                    source_key=_source_key("dashboard", event.event_id),
                    note_recorded=bool(event.reason_or_note and event.reason_or_note.strip()),
                    reviewer_recorded=bool(event.reviewer_label and event.reviewer_label.strip()),
                )
            )
        return entries

    @staticmethod
    def _autofill_entries(
        stored: StoredAutofillSession,
        job_key: str,
        findings: list[AuditIntegrityFinding],
    ) -> list[AuditTimelineEntry]:
        if stored.session.job_key != job_key:
            findings.append(
                _finding(
                    "AUDIT_AUTOFILL_SESSION_JOB_MISMATCH",
                    "A local autofill session does not match the selected job.",
                    "Restore a session linked to the selected review record.",
                    AuditTimelineSource.AUTOFILL,
                )
            )
            return []
        entries: list[AuditTimelineEntry] = []
        for event in stored.events:
            entry = _autofill_entry(stored.session.session_id, event, job_key, findings)
            if entry is not None:
                entries.append(entry)
        _validate_current_session_consistency(stored, findings)
        return entries


def _dashboard_transition(
    event: DashboardAuditEvent, findings: list[AuditIntegrityFinding]
) -> AuditStatusTransition | None:
    if event.previous_status not in _DASHBOARD_STATUS or event.new_status not in _DASHBOARD_STATUS:
        findings.append(
            _finding(
                "AUDIT_DASHBOARD_STATUS_UNSUPPORTED",
                "A dashboard audit event has an unsupported status transition.",
                "Inspect the local dashboard audit source.",
                AuditTimelineSource.DASHBOARD_REVIEW,
            )
        )
        return None
    valid = {
        "approved": ("awaiting_review", "approved_for_manual_next_step"),
        "revision_requested": ("awaiting_review", "revision_requested"),
        "rejected": ("awaiting_review", "rejected"),
        "resubmitted_for_review": ("revision_requested", "awaiting_review"),
    }
    expected = valid.get(event.action.value)
    observed = (event.previous_status.value, event.new_status.value)
    if expected != observed:
        findings.append(
            _finding(
                "AUDIT_DASHBOARD_TRANSITION_CONFLICT",
                "A dashboard audit event has a conflicting internal transition.",
                "Inspect the local dashboard audit source before relying on this event.",
                AuditTimelineSource.DASHBOARD_REVIEW,
            )
        )
    return AuditStatusTransition(
        previous=_DASHBOARD_STATUS[event.previous_status],
        current=_DASHBOARD_STATUS[event.new_status],
    )


def _autofill_entry(
    session_id: str,
    event: AutofillAuditEvent,
    job_key: str,
    findings: list[AuditIntegrityFinding],
) -> AuditTimelineEntry | None:
    if not _valid_autofill_event(event):
        findings.append(
            _finding(
                "AUDIT_AUTOFILL_EVENT_MALFORMED",
                "A local autofill audit event is malformed or unsupported.",
                "Inspect the local autofill audit source.",
                AuditTimelineSource.AUTOFILL,
            )
        )
        return None
    if event.job_key != job_key or event.session_id != session_id:
        findings.append(
            _finding(
                "AUDIT_AUTOFILL_EVENT_LINKAGE_INVALID",
                "A local autofill audit event has invalid session or job linkage.",
                "Inspect the local autofill audit source.",
                AuditTimelineSource.AUTOFILL,
            )
        )
        return None
    category = (
        AuditTimelineCategory.AUTOFILL_FIELD
        if event.field_identifier is not None
        else AuditTimelineCategory.AUTOFILL_SESSION
    )
    if (
        event.action
        in {
            AutofillAuditAction.FIELD_PREPARED,
            AutofillAuditAction.FIELD_POPULATED,
            AutofillAuditAction.FIELD_SKIPPED,
        }
        and event.field_identifier is None
    ):
        findings.append(
            _finding(
                "AUDIT_AUTOFILL_EVENT_SHAPE_INVALID",
                "A local autofill field event is incomplete.",
                "Inspect the local autofill audit source.",
                AuditTimelineSource.AUTOFILL,
            )
        )
        return None
    return AuditTimelineEntry(
        job_key=job_key,
        source=AuditTimelineSource.AUTOFILL,
        category=category,
        action=AuditTimelineAction(event.action.value),
        timestamp=event.timestamp,
        source_key=_source_key(
            "autofill", session_id, event.action.value, event.field_identifier or "session"
        ),
    )


def _session_summary(stored: StoredAutofillSession) -> CurrentCheckpointSummary:
    status = _AUTOFILL_STATUS.get(stored.session.status.value, AuditTimelineStatus.BLOCKED)
    return CurrentCheckpointSummary(
        status=status,
        reference_key=_source_key("autofill-session", stored.session.session_id),
        compatible=not _current_session_inconsistent(stored),
    )


def _validate_dashboard_linkage(
    events: Iterable[DashboardAuditEvent],
    record_keys: set[str],
    findings: list[AuditIntegrityFinding],
) -> None:
    for event in events:
        event_key = getattr(event, "job_key", None)
        if not isinstance(event_key, str) or event_key not in record_keys:
            findings.append(
                _finding(
                    "AUDIT_DASHBOARD_EVENT_JOB_INVALID",
                    "A dashboard audit event is not linked to a workspace review record.",
                    "Inspect the local dashboard audit source.",
                    AuditTimelineSource.DASHBOARD_REVIEW,
                )
            )


def _valid_dashboard_event(event: object) -> bool:
    timestamp = getattr(event, "timestamp", None)
    return bool(
        isinstance(event, DashboardAuditEvent)
        and isinstance(event.event_id, str)
        and event.event_id
        and isinstance(event.job_key, str)
        and event.job_key
        and isinstance(event.action, DashboardReviewAction)
        and isinstance(event.previous_status, DashboardReviewStatus)
        and isinstance(event.new_status, DashboardReviewStatus)
        and isinstance(event.reviewer_label, str)
        and (event.reason_or_note is None or isinstance(event.reason_or_note, str))
        and isinstance(timestamp, datetime)
        and timestamp.utcoffset() is not None
    )


def _valid_autofill_event(event: object) -> bool:
    timestamp = getattr(event, "timestamp", None)
    return bool(
        isinstance(event, AutofillAuditEvent)
        and isinstance(event.session_id, str)
        and event.session_id
        and isinstance(event.job_key, str)
        and event.job_key
        and isinstance(event.action, AutofillAuditAction)
        and (event.field_identifier is None or isinstance(event.field_identifier, str))
        and isinstance(timestamp, datetime)
        and timestamp.utcoffset() is not None
    )


def _valid_stored_session(stored: object) -> bool:
    if not isinstance(stored, StoredAutofillSession) or not isinstance(
        stored.session, AutofillSession
    ):
        return False
    return bool(
        isinstance(stored.session.session_id, str)
        and stored.session.session_id
        and isinstance(stored.session.job_key, str)
        and stored.session.job_key
        and isinstance(stored.session.status, AutofillSessionStatus)
        and isinstance(stored.events, tuple)
    )


def _validate_current_session_consistency(
    stored: StoredAutofillSession, findings: list[AuditIntegrityFinding]
) -> None:
    if _current_session_inconsistent(stored):
        findings.append(
            _finding(
                "AUDIT_CURRENT_CHECKPOINT_INCONSISTENT",
                "The current local checkpoint is inconsistent with its audit history.",
                "Reload the local session source before relying on its checkpoint summary.",
                AuditTimelineSource.AUTOFILL,
            )
        )


def _current_session_inconsistent(stored: StoredAutofillSession) -> bool:
    actions = {event.action for event in stored.events if _valid_autofill_event(event)}
    status = stored.session.status.value
    return (AutofillAuditAction.SESSION_CANCELLED in actions and status != "cancelled") or (
        AutofillAuditAction.FIELD_POPULATED in actions and status not in {"populated", "completed"}
    )


def _source_key(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"audit:{digest[:32]}"


def _finding(
    code: str,
    message: str,
    recovery_guidance: str,
    source: AuditTimelineSource | None = None,
) -> AuditIntegrityFinding:
    return AuditIntegrityFinding(
        code=code,
        message=message,
        recovery_guidance=recovery_guidance,
        source=source,
    )


def _dedupe_findings(
    findings: Iterable[AuditIntegrityFinding],
) -> list[AuditIntegrityFinding]:
    unique: dict[tuple[str, AuditTimelineSource | None], AuditIntegrityFinding] = {}
    for finding in findings:
        unique.setdefault((finding.code, finding.source), finding)
    return [unique[key] for key in sorted(unique, key=lambda item: (item[0], str(item[1])))]


def _deduplicate(
    entries: Iterable[AuditTimelineEntry], findings: list[AuditIntegrityFinding]
) -> list[AuditTimelineEntry]:
    by_source_key: dict[str, list[AuditTimelineEntry]] = {}
    for entry in entries:
        by_source_key.setdefault(entry.source_key, []).append(entry)
    result: list[AuditTimelineEntry] = []
    for source_key in sorted(by_source_key):
        candidates = sorted(by_source_key[source_key], key=_sort_key)
        entry = candidates[0]
        if len(candidates) > 1:
            findings.append(
                _finding(
                    "AUDIT_DUPLICATE_SOURCE_KEY",
                    "Duplicate audit source keys were detected.",
                    "Inspect the affected local audit source before relying on duplicate events.",
                    entry.source,
                )
            )
        result.append(entry)
    return result


def _filter(
    entries: Iterable[AuditTimelineEntry], filters: AuditTimelineFilters
) -> list[AuditTimelineEntry]:
    result: list[AuditTimelineEntry] = []
    for entry in entries:
        if filters.sources and entry.source not in filters.sources:
            continue
        if filters.categories and entry.category not in filters.categories:
            continue
        if filters.actions and entry.action not in filters.actions:
            continue
        if filters.statuses and not _has_status(entry, filters.statuses):
            continue
        if filters.from_timestamp and entry.timestamp < filters.from_timestamp:
            continue
        if filters.to_timestamp and entry.timestamp > filters.to_timestamp:
            continue
        result.append(entry)
    return result


def _has_status(entry: AuditTimelineEntry, statuses: frozenset[AuditTimelineStatus]) -> bool:
    return bool(
        entry.transition
        and (entry.transition.previous in statuses or entry.transition.current in statuses)
    )


def _sort_key(entry: AuditTimelineEntry) -> tuple[float, str, str, str, str, bool, bool]:
    transition = entry.transition
    previous = transition.previous.value if transition and transition.previous else ""
    current = transition.current.value if transition and transition.current else ""
    return (
        -entry.timestamp.timestamp(),
        entry.source.value,
        entry.source_key,
        entry.category.value,
        f"{entry.action.value}:{previous}:{current}",
        entry.note_recorded,
        entry.reviewer_recorded,
    )


def _counts(entries: Iterable[AuditTimelineEntry]) -> AuditTimelineCounts:
    values = list(entries)
    return AuditTimelineCounts(
        total=len(values),
        dashboard_review=sum(
            entry.source == AuditTimelineSource.DASHBOARD_REVIEW for entry in values
        ),
        autofill=sum(entry.source == AuditTimelineSource.AUTOFILL for entry in values),
        review_decisions=sum(
            entry.category == AuditTimelineCategory.REVIEW_DECISION for entry in values
        ),
        autofill_sessions=sum(
            entry.category == AuditTimelineCategory.AUTOFILL_SESSION for entry in values
        ),
        autofill_fields=sum(
            entry.category == AuditTimelineCategory.AUTOFILL_FIELD for entry in values
        ),
    )


def _paginate(
    entries: list[AuditTimelineEntry],
    request: AuditTimelinePageRequest,
    findings: list[AuditIntegrityFinding],
) -> tuple[list[AuditTimelineEntry], str | None]:
    start = 0
    if request.cursor:
        cursor = _decode_cursor(request.cursor)
        if cursor is None:
            findings.append(
                _finding(
                    "AUDIT_CURSOR_INVALID",
                    "The requested audit page cursor is invalid.",
                    "Reload the audit timeline from its first page.",
                )
            )
            return [], None
        for index, entry in enumerate(entries):
            if (entry.timestamp.isoformat(), entry.source_key) == cursor:
                start = index + 1
                break
        else:
            findings.append(
                _finding(
                    "AUDIT_CURSOR_STALE",
                    "The requested audit page cursor is no longer available.",
                    "Reload the audit timeline from its first page.",
                )
            )
            return [], None
    page = entries[start : start + request.page_size]
    next_cursor = None
    if start + request.page_size < len(entries) and page:
        last = page[-1]
        next_cursor = _encode_cursor(last.timestamp.isoformat(), last.source_key)
    return page, next_cursor


def _encode_cursor(timestamp: str, source_key: str) -> str:
    payload = json.dumps([timestamp, source_key], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str] | None:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if (
            not isinstance(payload, list)
            or len(payload) != 2
            or not all(isinstance(item, str) and item for item in payload)
        ):
            return None
        timestamp = datetime.fromisoformat(payload[0])
        if timestamp.utcoffset() is None:
            return None
        if not payload[1].startswith("audit:"):
            return None
        return payload[0], payload[1]
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return None
