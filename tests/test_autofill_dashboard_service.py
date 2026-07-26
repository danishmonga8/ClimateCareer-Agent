"""Offline tests for sanitized, deliberate Phase 8 dashboard controls."""

import pytest

from app.models.autofill import AutofillSessionStatus, AutofillWorkflowStage
from app.models.dashboard_review import (
    ArtifactReferences,
    DashboardReviewRecord,
    DashboardReviewStatus,
    MaterialMetadata,
    MaterialType,
)
from app.models.discovery import JobSource
from app.services.autofill_dashboard_service import (
    AutofillDashboardError,
    AutofillDashboardService,
)
from app.workflows.autofill_orchestration import AutofillWorkflow
from app.workflows.autofill_repository import AutofillWorkflowRepository
from tests.test_autofill_controller import _controller, _request


def _record(
    *,
    revision: int = 1,
    status: DashboardReviewStatus = DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP,
) -> DashboardReviewRecord:
    return DashboardReviewRecord(
        source=JobSource.MANUAL,
        source_board="fictional",
        source_job_id="job-1",
        artifacts=ArtifactReferences(
            discovery_snapshot="jobs.json",
            profile_artifact_ref="artifact:profile:fictional",
            evidence_artifact_refs=["artifact:evidence:fictional"],
        ),
        status=status,
        revision=revision,
        materials=[
            MaterialMetadata(material_type=MaterialType.TAILORED_RESUME, version="material:v1")
        ],
    )


def _service(monkeypatch, tmp_path):
    controller, calls = _controller(monkeypatch, tmp_path)
    workflow_repository = AutofillWorkflowRepository(tmp_path / "workflow")
    workflow = AutofillWorkflow(controller, workflow_repository)
    prepared = workflow.begin(_request())
    return (
        AutofillDashboardService(controller.session_repository, workflow_repository, workflow),
        prepared,
        calls,
    )


def test_read_only_dashboard_projection_never_resolves_or_mutates(monkeypatch, tmp_path) -> None:
    service, prepared, calls = _service(monkeypatch, tmp_path)

    view = service.read_view(_record())

    assert view is not None
    assert view.session_id == prepared.session_id
    assert view.status == AutofillSessionStatus.AWAITING_START_CONFIRMATION
    assert view.workflow_stage == AutofillWorkflowStage.AWAITING_SESSION_CONFIRMATION
    assert view.revision_compatible
    assert view.material_version_compatible
    assert view.artifact_references_compatible
    assert view.quality_status is not None
    assert calls == ["resolve"]
    serialized = view.model_dump_json()
    assert "Fictional Candidate" not in serialized
    assert "candidate@example.test" not in serialized
    assert str(tmp_path) not in serialized


def test_dashboard_controls_use_workflow_and_two_confirmation_stages(monkeypatch, tmp_path) -> None:
    service, _prepared, _calls = _service(monkeypatch, tmp_path)
    record = _record()
    first = service.read_view(record)
    assert first is not None

    service.confirm_start(first)
    second = service.read_view(record)
    assert second is not None
    assert second.status == AutofillSessionStatus.AWAITING_POPULATION_CONFIRMATION
    assert second.workflow_stage == AutofillWorkflowStage.AWAITING_FIELD_CONFIRMATION
    service.skip(second, ("email",))
    third = service.read_view(record)
    assert third is not None
    assert third.selected_identifiers == ("full_name",)
    service.confirm_population(third)
    finished = service.read_view(record)
    assert finished is not None
    assert finished.status == AutofillSessionStatus.POPULATED
    assert finished.workflow_stage == AutofillWorkflowStage.PREPARED_FOR_MANUAL_FIELD_ENTRY
    assert finished.populated_count == 1
    assert finished.skipped_count == 1


@pytest.mark.parametrize(
    "record",
    [
        _record(revision=2),
        _record(status=DashboardReviewStatus.REJECTED),
        _record(status=DashboardReviewStatus.AWAITING_REVIEW),
    ],
)
def test_stale_or_terminal_dashboard_views_disable_actions(monkeypatch, tmp_path, record) -> None:
    service, _prepared, calls = _service(monkeypatch, tmp_path)
    view = service.read_view(record)
    assert view is not None
    assert view.blocking_codes

    with pytest.raises(AutofillDashboardError, match="not available"):
        service.confirm_start(view)
    assert calls == ["resolve"]


def test_dashboard_cancel_is_deliberate_and_idempotent(monkeypatch, tmp_path) -> None:
    service, _prepared, _calls = _service(monkeypatch, tmp_path)
    view = service.read_view(_record())
    assert view is not None

    service.cancel(view)
    cancelled = service.read_view(_record())
    assert cancelled is not None
    assert cancelled.status == AutofillSessionStatus.CANCELLED
    with pytest.raises(AutofillDashboardError, match="not available"):
        service.cancel(cancelled)
