"""Smoke tests for the local Streamlit dashboard states."""

from datetime import UTC, datetime
from pathlib import Path

import pytest


def test_dashboard_renders_empty_workspace(tmp_path) -> None:
    streamlit_testing = pytest.importorskip("streamlit.testing.v1")
    from app.models.dashboard_review import DashboardWorkspace
    from app.services.dashboard_repository import save_dashboard_workspace

    workspace_path = tmp_path / "dashboard.json"
    save_dashboard_workspace(DashboardWorkspace(), workspace_path)
    app = streamlit_testing.AppTest.from_file(str(Path(__file__).parents[1] / "dashboard.py"))
    app.run()
    app.text_input[0].set_value(str(workspace_path))
    app.run()

    assert not app.exception
    assert any("Human Approval Dashboard" in title.value for title in app.title)
    assert any("no review records" in info.value for info in app.info)


def test_dashboard_renders_job_queue_and_confirmation_before_decision(tmp_path) -> None:
    streamlit_testing = pytest.importorskip("streamlit.testing.v1")
    from app.models.dashboard_review import (
        ArtifactReferences,
        DashboardReviewRecord,
        DashboardWorkspace,
    )
    from app.models.discovery import DiscoveredJob, DiscoverySnapshot, JobSource
    from app.services.dashboard_repository import (
        load_dashboard_workspace,
        save_dashboard_workspace,
    )
    from app.services.discovery_repository import save_discovery_snapshot

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
                    description="Fictional plain-text job description.",
                    discovered_at=datetime(2026, 7, 25, tzinfo=UTC),
                )
            ]
        ),
        tmp_path / "jobs.json",
    )
    workspace_path = tmp_path / "dashboard.json"
    save_dashboard_workspace(
        DashboardWorkspace(
            records=[
                DashboardReviewRecord(
                    source=JobSource.MANUAL,
                    source_board="fictional",
                    source_job_id="job-1",
                    artifacts=ArtifactReferences(discovery_snapshot="jobs.json"),
                )
            ]
        ),
        workspace_path,
    )
    app = streamlit_testing.AppTest.from_file(str(Path(__file__).parents[1] / "dashboard.py"))
    app.run()
    app.text_input[0].set_value(str(workspace_path))
    app.run()

    assert not app.exception
    assert len(app.radio) == 1
    assert any(button.label == "Approve for manual next step" for button in app.button)
    next(button for button in app.button if button.label == "Request revision").click()
    app.run()
    assert not app.exception
    assert len(load_dashboard_workspace(workspace_path).audit_events) == 0


def test_dashboard_reloads_linked_application_before_approval(tmp_path) -> None:
    streamlit_testing = pytest.importorskip("streamlit.testing.v1")
    from app.models.dashboard_review import (
        ArtifactReferences,
        DashboardReviewRecord,
        DashboardWorkspace,
    )
    from app.models.discovery import DiscoveredJob, DiscoverySnapshot, JobSource
    from app.models.personalization import (
        PersonalizedApplication,
        ReviewItem,
        TailoredCoverLetter,
        TailoredResume,
    )
    from app.services.dashboard_repository import (
        load_dashboard_workspace,
        save_dashboard_workspace,
    )
    from app.services.discovery_repository import save_discovery_snapshot
    from app.services.personalization_repository import save_personalized_application

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
                    description="Fictional plain-text job description.",
                    discovered_at=datetime(2026, 7, 25, tzinfo=UTC),
                )
            ]
        ),
        tmp_path / "jobs.json",
    )
    application_path = tmp_path / "application.json"
    application = PersonalizedApplication(
        candidate_name="Avery Rowan",
        job_title="Climate Analyst",
        employer="Fictional Climate Lab",
        job_url="https://example.test/jobs/1",
        resume=TailoredResume(),
        cover_letter=TailoredCoverLetter(body="Fictional draft."),
    )
    save_personalized_application(application, application_path)
    workspace_path = tmp_path / "dashboard.json"
    save_dashboard_workspace(
        DashboardWorkspace(
            records=[
                DashboardReviewRecord(
                    source=JobSource.MANUAL,
                    source_board="fictional",
                    source_job_id="job-1",
                    artifacts=ArtifactReferences(
                        discovery_snapshot="jobs.json",
                        personalized_application="application.json",
                    ),
                )
            ]
        ),
        workspace_path,
    )
    app = streamlit_testing.AppTest.from_file(str(Path(__file__).parents[1] / "dashboard.py"))
    app.run()
    app.text_input[0].set_value(str(workspace_path))
    app.run()

    from dashboard import _load_current_review_context

    save_personalized_application(
        application.model_copy(
            update={
                "review_items": [
                    ReviewItem(field_path="cover_letter", reason="Fictional reviewer check.")
                ]
            }
        ),
        application_path,
    )

    _workspace, current_view = _load_current_review_context(
        workspace_path,
        "manual:fictional:job-1",
    )

    assert not app.exception
    assert current_view is not None
    assert current_view.application is not None
    assert any(not item.resolved for item in current_view.application.review_items)
    assert not load_dashboard_workspace(workspace_path).audit_events
