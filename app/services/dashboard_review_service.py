"""Validated internal decisions for dashboard review records."""

from datetime import UTC, datetime

from app.models.dashboard_review import (
    DashboardAuditEvent,
    DashboardReviewAction,
    DashboardReviewRecord,
    DashboardReviewStatus,
    DashboardWorkspace,
)
from app.models.personalization import PersonalizedApplication


class DashboardReviewError(ValueError):
    """Raised when a dashboard decision is invalid or stale."""


def _record_index(workspace: DashboardWorkspace, job_key: str) -> int:
    for index, record in enumerate(workspace.records):
        if record.job_key == job_key:
            return index
    raise DashboardReviewError("The selected job is not in this workspace.")


def _validate_revision(record: DashboardReviewRecord, expected_revision: int) -> None:
    if expected_revision != record.revision:
        raise DashboardReviewError("This review changed; reload before deciding.")


def _replace_record(
    workspace: DashboardWorkspace,
    index: int,
    status: DashboardReviewStatus,
) -> DashboardWorkspace:
    payload = workspace.model_dump(mode="python")
    payload["records"][index]["status"] = status
    payload["records"][index]["revision"] += 1
    for material in payload["records"][index]["materials"]:
        material["review_status"] = status
    return DashboardWorkspace.model_validate(payload)


def _append_event(
    workspace: DashboardWorkspace,
    record: DashboardReviewRecord,
    status: DashboardReviewStatus,
    action: DashboardReviewAction,
    reviewer_label: str,
    reason_or_note: str | None,
    material_version: str | None,
) -> DashboardWorkspace:
    normalized_reviewer = reviewer_label.strip()
    if not normalized_reviewer:
        raise DashboardReviewError("A reviewer label is required.")
    payload = workspace.model_dump(mode="python")
    payload["audit_events"].append(
        DashboardAuditEvent(
            job_key=record.job_key,
            previous_status=record.status,
            new_status=status,
            action=action,
            reviewer_label=normalized_reviewer,
            reason_or_note=reason_or_note,
            material_version=material_version,
            timestamp=datetime.now(UTC),
        ).model_dump(mode="python")
    )
    return DashboardWorkspace.model_validate(payload)


def apply_dashboard_decision(
    workspace: DashboardWorkspace,
    job_key: str,
    action: DashboardReviewAction,
    expected_revision: int,
    reviewer_label: str,
    reason_or_note: str | None = None,
    material_version: str | None = None,
    linked_application: PersonalizedApplication | None = None,
) -> DashboardWorkspace:
    """Apply an internal decision without interacting with external services."""
    index = _record_index(workspace, job_key)
    record = workspace.records[index]
    _validate_revision(record, expected_revision)
    if record.status in {
        DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP,
        DashboardReviewStatus.REJECTED,
    }:
        raise DashboardReviewError("Approved and rejected decisions are terminal.")

    normalized_reason = reason_or_note.strip() if reason_or_note else None
    targets = {
        DashboardReviewAction.APPROVED: DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP,
        DashboardReviewAction.REVISION_REQUESTED: DashboardReviewStatus.REVISION_REQUESTED,
        DashboardReviewAction.REJECTED: DashboardReviewStatus.REJECTED,
    }
    if action not in targets:
        raise DashboardReviewError("Use resubmit_for_review to return a revision to review.")
    if (
        action
        in {
            DashboardReviewAction.REVISION_REQUESTED,
            DashboardReviewAction.REJECTED,
        }
        and not normalized_reason
    ):
        raise DashboardReviewError("A reason is required for rejection or revision requests.")
    if (
        action == DashboardReviewAction.APPROVED
        and linked_application is not None
        and (
            any(not item.resolved for item in linked_application.review_items)
            or any(
                answer.requires_confirmation for answer in linked_application.application_answers
            )
        )
    ):
        raise DashboardReviewError("Resolve linked application review items before approval.")

    with_event = _append_event(
        workspace,
        record,
        targets[action],
        action,
        reviewer_label,
        normalized_reason,
        material_version,
    )
    return _replace_record(with_event, index, targets[action])


def resubmit_for_review(
    workspace: DashboardWorkspace,
    job_key: str,
    expected_revision: int,
    reviewer_label: str,
    note: str | None = None,
) -> DashboardWorkspace:
    """Return a requested revision to review without regenerating material."""
    index = _record_index(workspace, job_key)
    record = workspace.records[index]
    _validate_revision(record, expected_revision)
    if record.status != DashboardReviewStatus.REVISION_REQUESTED:
        raise DashboardReviewError("Only a requested revision can return to review.")
    with_event = _append_event(
        workspace,
        record,
        DashboardReviewStatus.AWAITING_REVIEW,
        DashboardReviewAction.RESUBMITTED_FOR_REVIEW,
        reviewer_label,
        note.strip() if note else None,
        None,
    )
    return _replace_record(with_event, index, DashboardReviewStatus.AWAITING_REVIEW)
