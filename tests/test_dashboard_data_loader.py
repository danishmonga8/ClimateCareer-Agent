"""Tests for safe aggregation of existing artifacts into dashboard rows."""

from datetime import UTC, datetime

from app.dashboard.data_loader import load_dashboard_data
from app.models.dashboard_review import (
    ArtifactReferences,
    DashboardReviewRecord,
    DashboardWorkspace,
)
from app.models.discovery import DiscoveredJob, DiscoverySnapshot, JobSource
from app.services.dashboard_repository import save_dashboard_workspace
from app.services.discovery_repository import save_discovery_snapshot


def test_loader_keeps_job_when_optional_score_is_malformed(tmp_path) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    save_discovery_snapshot(
        DiscoverySnapshot(
            jobs=[
                DiscoveredJob(
                    source=JobSource.MANUAL,
                    source_board="example",
                    source_job_id="job-1",
                    company="Example Climate",
                    title="Climate Analyst",
                    job_url="https://example.test/jobs/1",
                    description="Analyse climate data.",
                    discovered_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            ]
        ),
        snapshot_path,
    )
    (tmp_path / "score.json").write_text("not json", encoding="utf-8")
    workspace_path = tmp_path / "dashboard.json"
    save_dashboard_workspace(
        DashboardWorkspace(
            records=[
                DashboardReviewRecord(
                    source=JobSource.MANUAL,
                    source_board="example",
                    source_job_id="job-1",
                    artifacts=ArtifactReferences(
                        discovery_snapshot="snapshot.json", scoring_result="score.json"
                    ),
                )
            ]
        ),
        workspace_path,
    )

    result = load_dashboard_data(workspace_path)

    assert result.jobs[0].job is not None
    assert result.jobs[0].score is None
    assert result.warnings == ("The optional scoring result is unavailable or invalid.",)
