"""Offline LangGraph interruption tests for controlled field-entry sessions."""

import ast
import inspect

from app.models.autofill import AutofillWorkflowStage
from app.workflows.autofill_orchestration import AutofillWorkflow
from app.workflows.autofill_repository import AutofillWorkflowRepository
from tests.test_autofill_controller import _controller, _request


def _decision(snapshot, action: str) -> dict[str, object]:
    return {
        "action": action,
        "confirmed": True,
        "session_id": snapshot.session_id,
        "expected_revision": snapshot.expected_revision,
        "material_version_ref": snapshot.material_version_ref,
        "selected_identifiers": list(snapshot.selected_identifiers),
    }


def test_langgraph_requires_two_explicit_confirmations_and_final_manual_interrupt(
    monkeypatch, tmp_path
) -> None:
    controller, _ = _controller(monkeypatch, tmp_path)
    workflow = AutofillWorkflow(controller, AutofillWorkflowRepository(tmp_path / "workflow"))
    prepared = workflow.begin(_request())

    assert prepared.status == AutofillWorkflowStage.AWAITING_SESSION_CONFIRMATION
    assert workflow.checkpoint_repository.load(prepared.workflow_id) == prepared
    started = workflow.resume(prepared.workflow_id, _decision(prepared, "confirm_session_start"))
    assert started.status == AutofillWorkflowStage.AWAITING_FIELD_CONFIRMATION
    populated = workflow.resume(
        started.workflow_id, _decision(started, "confirm_exact_selected_fields")
    )
    assert populated.status == AutofillWorkflowStage.PREPARED_FOR_MANUAL_FIELD_ENTRY
    assert controller._session(populated.session_id).status.value == "populated"
    config = {"configurable": {"thread_id": populated.workflow_id}}
    interrupt_value = workflow.graph.get_state(config).tasks[0].interrupts[0].value
    assert interrupt_value["message"] == "Prepared for manual field entry."


def test_restart_never_auto_confirms_or_populates_and_invalid_decision_blocks(
    monkeypatch, tmp_path
) -> None:
    controller, _ = _controller(monkeypatch, tmp_path)
    workflow = AutofillWorkflow(controller, AutofillWorkflowRepository(tmp_path / "workflow"))
    prepared = workflow.begin(_request())
    restarted_controller, _ = _controller(monkeypatch, tmp_path)
    restarted = AutofillWorkflow(
        restarted_controller,
        AutofillWorkflowRepository(tmp_path / "workflow"),
    )

    snapshot = restarted.checkpoint_repository.load(prepared.workflow_id)
    assert (
        restarted_controller._session(snapshot.session_id).status.value
        == "awaiting_start_confirmation"
    )
    invalid = restarted.resume(snapshot.workflow_id, {"action": "confirm_session_start"})
    assert invalid.status == AutofillWorkflowStage.BLOCKED
    assert (
        restarted_controller._session(snapshot.session_id).status.value
        == "awaiting_start_confirmation"
    )


def test_cancellation_is_terminal_and_contains_only_reference_metadata(
    monkeypatch, tmp_path
) -> None:
    controller, _ = _controller(monkeypatch, tmp_path)
    workflow = AutofillWorkflow(controller, AutofillWorkflowRepository(tmp_path / "workflow"))
    prepared = workflow.begin(_request())
    cancelled = workflow.resume(
        prepared.workflow_id,
        {"action": "cancel", "session_id": prepared.session_id},
    )

    assert cancelled.status == AutofillWorkflowStage.CANCELLED
    serialized = cancelled.model_dump_json()
    assert "Fictional Candidate" not in serialized
    assert str(tmp_path) not in serialized


def test_restart_requires_a_new_valid_confirmation_before_each_transition(
    monkeypatch, tmp_path
) -> None:
    controller, _ = _controller(monkeypatch, tmp_path)
    first = AutofillWorkflow(controller, AutofillWorkflowRepository(tmp_path / "workflow"))
    prepared = first.begin(_request())
    restarted_controller, _ = _controller(monkeypatch, tmp_path)
    restarted = AutofillWorkflow(
        restarted_controller,
        AutofillWorkflowRepository(tmp_path / "workflow"),
    )

    started = restarted.resume(prepared.workflow_id, _decision(prepared, "confirm_session_start"))
    assert started.status == AutofillWorkflowStage.AWAITING_FIELD_CONFIRMATION
    assert (
        restarted_controller._session(started.session_id).status.value
        == "awaiting_population_confirmation"
    )

    false_confirmation = restarted.resume(
        started.workflow_id,
        {
            **_decision(started, "confirm_exact_selected_fields"),
            "confirmed": False,
        },
    )
    assert false_confirmation.status == AutofillWorkflowStage.BLOCKED
    assert (
        restarted_controller._session(started.session_id).status.value
        == "awaiting_population_confirmation"
    )


def test_reachable_phase_eight_modules_import_no_external_execution_capability() -> None:
    from app.services import autofill_controller, autofill_service
    from app.workflows import autofill_orchestration

    prohibited = {
        "httpx",
        "requests",
        "subprocess",
        "smtplib",
        "webbrowser",
        "selenium",
        "playwright",
    }
    for module in (autofill_service, autofill_controller, autofill_orchestration):
        tree = ast.parse(inspect.getsource(module))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not imports.intersection(prohibited)
