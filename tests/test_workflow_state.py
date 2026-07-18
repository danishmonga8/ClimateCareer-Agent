"""Tests for the shared application workflow state."""

from app.workflows.state import (
    ApprovalStatus,
    WorkflowStage,
    create_initial_state,
)


def test_initial_workflow_state_is_safe_and_empty() -> None:
    """A new workflow must not be approved or contain invented information."""
    state = create_initial_state()

    assert state["stage"] == WorkflowStage.CREATED
    assert state["approval_status"] == ApprovalStatus.NOT_REQUESTED
    assert state["candidate_profile"] is None
    assert state["job_description"] is None
    assert state["relevance_score"] is None
    assert state["required_manual_inputs"] == []
    assert state["audit_log"] == ["Workflow created."]
    assert state["workflow_id"]