"""Tests for the internal-only LangGraph workflow state."""

import pytest

from app.workflows.state import WorkflowStage, create_initial_state, validate_workflow_state


def test_initial_workflow_state_is_reference_only_and_awaits_no_approval() -> None:
    state = create_initial_state()

    assert state["stage"] == WorkflowStage.INPUT_VALIDATION
    assert state["score_reference"] is None
    assert state["application_reference"] is None
    assert state["warnings"] == []
    assert state["workflow_id"]


@pytest.mark.parametrize("legacy_stage", ["applied", "autofilled", "submitted"])
def test_legacy_external_action_stages_fail_closed(legacy_stage: str) -> None:
    state = create_initial_state()
    state["stage"] = legacy_stage  # type: ignore[typeddict-item]

    with pytest.raises(ValueError, match="incompatible"):
        validate_workflow_state(state)
