"""Tests for atomic, append-only dashboard workspace persistence."""

import pytest

from app.models.dashboard_review import (
    ArtifactReferences,
    DashboardReviewAction,
    DashboardReviewRecord,
    DashboardWorkspace,
)
from app.models.discovery import JobSource
from app.services.dashboard_repository import (
    DashboardStorageError,
    load_dashboard_workspace,
    save_dashboard_workspace,
    save_updated_dashboard_workspace,
)
from app.services.dashboard_review_service import apply_dashboard_decision


def make_workspace() -> DashboardWorkspace:
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


def test_workspace_round_trip_is_atomic(tmp_path) -> None:
    path = tmp_path / "dashboard.json"
    save_dashboard_workspace(make_workspace(), path)

    assert load_dashboard_workspace(path).records[0].job_key == "manual:example:job-1"
    assert not (tmp_path / "dashboard.json.temporary").exists()


def test_updated_workspace_requires_unchanged_audit_prefix(tmp_path) -> None:
    path = tmp_path / "dashboard.json"
    original = make_workspace()
    save_dashboard_workspace(original, path)
    updated = apply_dashboard_decision(
        original,
        "manual:example:job-1",
        DashboardReviewAction.REJECTED,
        0,
        "Reviewer",
        "Not suitable.",
    )
    save_updated_dashboard_workspace(original, updated, path)

    changed = updated.model_copy(update={"audit_events": []})
    with pytest.raises(DashboardStorageError, match="changed"):
        save_updated_dashboard_workspace(original, changed, path)


def test_malformed_workspace_is_rejected_without_raw_parse_error(tmp_path) -> None:
    path = tmp_path / "dashboard.json"
    path.write_text("not json", encoding="utf-8")

    with pytest.raises(DashboardStorageError, match="valid dashboard workspace"):
        load_dashboard_workspace(path)
