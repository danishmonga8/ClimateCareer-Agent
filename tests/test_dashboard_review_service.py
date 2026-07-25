"""Tests for safe dashboard review state transitions and audit events."""

import ast
import inspect

import pytest

from app.models.dashboard_review import (
    ArtifactReferences,
    DashboardReviewAction,
    DashboardReviewRecord,
    DashboardReviewStatus,
    DashboardWorkspace,
)
from app.models.discovery import JobSource
from app.models.personalization import (
    PersonalizedApplication,
    ReviewItem,
    TailoredCoverLetter,
    TailoredResume,
)
from app.services import dashboard_review_service
from app.services.dashboard_review_service import (
    DashboardReviewError,
    apply_dashboard_decision,
    resubmit_for_review,
)


def make_workspace() -> DashboardWorkspace:
    """Create a minimal private dashboard workspace."""
    return DashboardWorkspace(
        records=[
            DashboardReviewRecord(
                source=JobSource.MANUAL,
                source_board="example",
                source_job_id="job-1",
                artifacts=ArtifactReferences(discovery_snapshot="snapshot.json"),
            )
        ]
    )


def make_application(unresolved: bool = False) -> PersonalizedApplication:
    """Create an application only for approval-gate checks."""
    return PersonalizedApplication(
        candidate_name="Test Candidate",
        job_title="Climate Analyst",
        employer="Example Climate",
        job_url="https://example.test/jobs/1",
        resume=TailoredResume(),
        cover_letter=TailoredCoverLetter(body="Draft letter."),
        review_items=[ReviewItem(field_path="cover_letter", reason="Check wording")]
        if unresolved
        else [],
    )


def test_approval_records_append_only_event_and_new_revision() -> None:
    workspace = make_workspace()
    updated = apply_dashboard_decision(
        workspace,
        "manual:example:job-1",
        DashboardReviewAction.APPROVED,
        0,
        "Reviewer",
        "Ready for manual next step.",
        linked_application=make_application(),
    )

    assert updated.records[0].status == DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP
    assert updated.records[0].revision == 1
    assert updated.audit_events[0].previous_status == DashboardReviewStatus.AWAITING_REVIEW
    assert updated.audit_events[0].reason_or_note == "Ready for manual next step."


@pytest.mark.parametrize(
    "action",
    [DashboardReviewAction.REVISION_REQUESTED, DashboardReviewAction.REJECTED],
)
def test_rejection_and_revision_require_reasons(action: DashboardReviewAction) -> None:
    with pytest.raises(DashboardReviewError, match="reason is required"):
        apply_dashboard_decision(make_workspace(), "manual:example:job-1", action, 0, "Reviewer")


def test_approval_blocks_unresolved_linked_application() -> None:
    with pytest.raises(DashboardReviewError, match="Resolve linked"):
        apply_dashboard_decision(
            make_workspace(),
            "manual:example:job-1",
            DashboardReviewAction.APPROVED,
            0,
            "Reviewer",
            linked_application=make_application(unresolved=True),
        )


def test_stale_and_terminal_decisions_are_rejected() -> None:
    updated = apply_dashboard_decision(
        make_workspace(),
        "manual:example:job-1",
        DashboardReviewAction.REJECTED,
        0,
        "Reviewer",
        "Not suitable.",
    )
    with pytest.raises(DashboardReviewError, match="terminal"):
        apply_dashboard_decision(
            updated,
            "manual:example:job-1",
            DashboardReviewAction.APPROVED,
            1,
            "Reviewer",
        )
    with pytest.raises(DashboardReviewError, match="changed"):
        apply_dashboard_decision(
            updated,
            "manual:example:job-1",
            DashboardReviewAction.APPROVED,
            0,
            "Reviewer",
        )


def test_revision_can_only_return_to_review_explicitly() -> None:
    requested = apply_dashboard_decision(
        make_workspace(),
        "manual:example:job-1",
        DashboardReviewAction.REVISION_REQUESTED,
        0,
        "Reviewer",
        "Clarify the cover letter.",
    )
    returned = resubmit_for_review(
        requested, "manual:example:job-1", 1, "Reviewer", "Materials updated."
    )

    assert returned.records[0].status == DashboardReviewStatus.AWAITING_REVIEW
    assert [event.action.value for event in returned.audit_events] == [
        "revision_requested",
        "resubmitted_for_review",
    ]


def test_decision_service_has_no_external_action_path() -> None:
    tree = ast.parse(inspect.getsource(dashboard_review_service))
    imported_modules = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert not imported_modules.intersection(
        {"httpx", "requests", "subprocess", "webbrowser", "openai", "smtplib"}
    )
