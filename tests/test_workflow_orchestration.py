"""Offline tests for durable LangGraph orchestration boundaries."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.personalization import ApplicationStatus
from app.workflows.orchestration import WorkflowOrchestrator, WorkflowServices
from app.workflows.repository import WorkflowCheckpointError, load_workflow_checkpoint
from app.workflows.state import WorkflowStage, create_initial_state


def _services() -> WorkflowServices:
    job = SimpleNamespace(
        source=SimpleNamespace(value="manual"),
        source_board="fictional",
        source_job_id="job-1",
    )
    application = SimpleNamespace(status=ApplicationStatus.NEEDS_REVIEW)
    return WorkflowServices(
        load_profile=lambda _: object(),
        load_evidence=lambda _: object(),
        load_discovery=lambda _: SimpleNamespace(jobs=[job]),
        load_score=lambda _: object(),
        load_application=lambda _: application,
        save_application=lambda *_: None,
    )


def _state() -> dict:
    return create_initial_state(
        workflow_id="fictional-workflow-1",
        job_key="manual:fictional:job-1",
        workspace_reference="dashboard.json",
        candidate_reference="profile.json",
        evidence_reference="evidence.json",
        discovery_reference="jobs.json",
        score_reference="score.json",
        application_reference="application.json",
    )


def test_successful_preparation_interrupts_and_persists_reference_only_state(tmp_path) -> None:
    orchestrator = WorkflowOrchestrator(tmp_path, _services())

    state = orchestrator.start(_state())

    assert state["stage"] == WorkflowStage.AWAITING_HUMAN_REVIEW
    assert state["completed_nodes"] == [
        "validate_inputs",
        "process_job",
        "load_score",
        "prepare_materials",
    ]
    reloaded = load_workflow_checkpoint(state["workflow_id"], tmp_path)
    assert reloaded["application_reference"] == "application.json"
    assert "candidate_profile" not in reloaded


def test_missing_score_is_recoverable_and_safe_to_reload(tmp_path) -> None:
    state = _state()
    state["score_reference"] = None

    result = WorkflowOrchestrator(tmp_path, _services()).start(state)

    assert result["stage"] == WorkflowStage.RECOVERABLE_FAILURE
    assert result["recoverable_errors"] == ["A scoring result is required before human review."]


def test_malformed_checkpoint_is_sanitized(tmp_path) -> None:
    path = Path(tmp_path) / "fictional-workflow-1.json"
    path.write_text('{"stage":"submitted"}', encoding="utf-8")

    with pytest.raises(WorkflowCheckpointError, match="unavailable or incompatible"):
        load_workflow_checkpoint("fictional-workflow-1", tmp_path)
