"""Streamlit tests for the read-only sanitized audit timeline."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


def _workspace_with_history(tmp_path, count: int = 2):
    from app.models.dashboard_review import (
        ArtifactReferences,
        DashboardAuditEvent,
        DashboardReviewAction,
        DashboardReviewRecord,
        DashboardReviewStatus,
        DashboardWorkspace,
    )
    from app.models.discovery import DiscoveredJob, DiscoverySnapshot, JobSource
    from app.services.dashboard_repository import save_dashboard_workspace
    from app.services.discovery_repository import save_discovery_snapshot

    record = DashboardReviewRecord(
        source=JobSource.MANUAL,
        source_board="fictional",
        source_job_id="job-1",
        artifacts=ArtifactReferences(discovery_snapshot="jobs.json"),
    )
    save_discovery_snapshot(
        DiscoverySnapshot(
            jobs=[
                DiscoveredJob(
                    source=JobSource.MANUAL,
                    source_board="fictional",
                    source_job_id="job-1",
                    company="Fictional Climate Lab",
                    title="Climate Analyst",
                    job_url="https://example.test/jobs/1",
                    description="Fictional job description.",
                    discovered_at=datetime(2026, 7, 26, tzinfo=UTC),
                )
            ]
        ),
        tmp_path / "jobs.json",
    )
    events = [
        DashboardAuditEvent(
            event_id=f"event-{index}",
            job_key=record.job_key,
            previous_status=DashboardReviewStatus.AWAITING_REVIEW,
            new_status=DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP,
            action=DashboardReviewAction.APPROVED,
            reviewer_label="Private Fictional Reviewer",
            reason_or_note="Private fictional review note that must not render.",
            timestamp=datetime(2026, 7, 26, tzinfo=UTC) + timedelta(seconds=index),
        )
        for index in range(count)
    ]
    workspace_path = tmp_path / "dashboard.json"
    save_dashboard_workspace(
        DashboardWorkspace(records=[record], audit_events=events), workspace_path
    )
    return workspace_path


def _rendered_text(app) -> str:
    groups = (app.caption, app.markdown, app.info, app.warning, app.text, app.title)
    return "\n".join(item.value for group in groups for item in group)


def test_dashboard_timeline_redacts_notes_and_reviewers_and_never_writes(tmp_path) -> None:
    streamlit_testing = pytest.importorskip("streamlit.testing.v1")
    workspace_path = _workspace_with_history(tmp_path)
    before = workspace_path.read_bytes()
    app = streamlit_testing.AppTest.from_file(str(Path(__file__).parents[1] / "dashboard.py"))
    app.run()
    app.text_input[0].set_value(str(workspace_path))
    app.run()

    text = _rendered_text(app)
    assert not app.exception
    assert "Review note recorded" in text
    assert "Reviewer recorded" in text
    assert "Private Fictional Reviewer" not in text
    assert "Private fictional review note" not in text
    assert workspace_path.read_bytes() == before


def test_dashboard_timeline_filters_and_pagination_are_read_only(tmp_path) -> None:
    streamlit_testing = pytest.importorskip("streamlit.testing.v1")
    workspace_path = _workspace_with_history(tmp_path, count=26)
    before = workspace_path.read_bytes()
    app = streamlit_testing.AppTest.from_file(str(Path(__file__).parents[1] / "dashboard.py"))
    app.run()
    app.text_input[0].set_value(str(workspace_path))
    app.run()

    source_filter = next(item for item in app.multiselect if item.label == "Audit sources")
    source_filter.set_value(["dashboard_review"])
    app.run()
    assert not app.exception
    assert not app.exception
    next_button = next(item for item in app.button if item.label == "Earlier audit events")
    assert not next_button.disabled
    next_button.click()
    app.run()

    assert not app.exception
    assert workspace_path.read_bytes() == before
    assert any(metric.label == "Visible events" for metric in app.metric)


def test_dashboard_timeline_projects_configured_autofill_events_without_values(tmp_path) -> None:
    streamlit_testing = pytest.importorskip("streamlit.testing.v1")
    from app.models.autofill import AutofillSession, AutofillSessionStatus
    from app.services.audit_timeline_service import AuditTimelineService
    from app.services.autofill_audit_service import AutofillAuditAction, AutofillAuditEvent
    from app.services.autofill_repository import AutofillSessionRepository, StoredAutofillSession

    workspace_path = _workspace_with_history(tmp_path)
    repository = AutofillSessionRepository(tmp_path / "sessions")
    repository.save(
        StoredAutofillSession(
            session=AutofillSession(
                session_id="session-fictional-1",
                job_key="manual:fictional:job-1",
                workspace_ref="workspace:fictional",
                profile_artifact_ref="artifact:profile:fictional",
                evidence_artifact_refs=("artifact:evidence:fictional",),
                expected_revision=0,
                material_version_ref="material:v1",
                status=AutofillSessionStatus.AWAITING_START_CONFIRMATION,
            ),
            events=(
                AutofillAuditEvent(
                    session_id="session-fictional-1",
                    job_key="manual:fictional:job-1",
                    action=AutofillAuditAction.FIELD_PREPARED,
                    field_identifier="full_name",
                    timestamp=datetime(2026, 7, 26, 1, tzinfo=UTC),
                ),
            ),
        )
    )
    before_workspace = workspace_path.read_bytes()
    before_session = (tmp_path / "sessions" / "session-fictional-1.json").read_bytes()
    app = streamlit_testing.AppTest.from_file(str(Path(__file__).parents[1] / "dashboard.py"))
    app.session_state["_audit_timeline_service"] = AuditTimelineService(repository)
    app.run()
    app.text_input[0].set_value(str(workspace_path))
    app.run()

    text = _rendered_text(app)
    assert not app.exception
    assert any(metric.label == "Autofill events" and metric.value == "1" for metric in app.metric)
    assert "full_name" not in text
    assert workspace_path.read_bytes() == before_workspace
    assert (tmp_path / "sessions" / "session-fictional-1.json").read_bytes() == before_session
