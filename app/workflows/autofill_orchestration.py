"""Interrupted LangGraph lifecycle for locally controlled field entry.

This graph has no browser, HTTP, upload, email, authentication, or submission
node.  It delegates every transition to ``LocalAutofillController``.
"""

from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.models.autofill import (
    AutofillPreparationRequest,
    AutofillSession,
    AutofillTransitionRequest,
    AutofillWorkflowSnapshot,
    AutofillWorkflowStage,
)
from app.services.autofill_controller import AutofillGateError, LocalAutofillController
from app.workflows.autofill_repository import AutofillWorkflowRepository


class AutofillWorkflowError(ValueError):
    """Sanitized interruption or resume failure."""


class AutofillWorkflowState(TypedDict):
    """LangGraph state with opaque references and identifier-level metadata only."""

    workflow_id: str
    session_id: str
    job_key: str
    workspace_ref: str
    profile_artifact_ref: str
    evidence_artifact_refs: tuple[str, ...]
    expected_revision: int
    material_version_ref: str
    workflow_checkpoint_ref: str | None
    selected_identifiers: tuple[str, ...]
    field_classifications: dict[str, str]
    status: str
    blocking_codes: tuple[str, ...]


class AutofillWorkflow:
    """Restart-safe controller-backed LangGraph wrapper with genuine interrupts."""

    def __init__(
        self,
        controller: LocalAutofillController,
        checkpoint_repository: AutofillWorkflowRepository,
    ) -> None:
        self.controller = controller
        self.checkpoint_repository = checkpoint_repository
        self.checkpointer = InMemorySaver()
        graph = StateGraph(AutofillWorkflowState)
        graph.add_node("prepare_session", self._prepare_session)
        graph.add_node("confirm_session", self._confirm_session)
        graph.add_node("confirm_fields", self._confirm_fields)
        graph.add_node("manual_review", self._manual_review)
        graph.add_edge(START, "prepare_session")
        graph.add_conditional_edges(
            "prepare_session",
            self._after_prepare,
            {"confirm_session": "confirm_session", "end": END},
        )
        graph.add_conditional_edges(
            "confirm_session",
            self._after_start,
            {"confirm_fields": "confirm_fields", "end": END},
        )
        graph.add_conditional_edges(
            "confirm_fields",
            self._after_population,
            {"confirm_fields": "confirm_fields", "manual_review": "manual_review", "end": END},
        )
        graph.add_edge("manual_review", END)
        self.graph = graph.compile(checkpointer=self.checkpointer)

    def begin(self, request: AutofillPreparationRequest) -> AutofillWorkflowSnapshot:
        """Prepare once and stop before the first explicit confirmation."""
        workflow_id = str(uuid4())
        state = {
            "workflow_id": workflow_id,
            "session_id": workflow_id,
            "job_key": request.job_key,
            "workspace_ref": request.workspace_ref,
            "profile_artifact_ref": request.profile_artifact_ref,
            "evidence_artifact_refs": request.evidence_artifact_refs,
            "expected_revision": request.expected_revision,
            "material_version_ref": request.material_version_ref,
            "workflow_checkpoint_ref": request.workflow_checkpoint_ref,
            "selected_identifiers": request.selected_identifiers,
            "field_classifications": {},
            "status": AutofillWorkflowStage.BLOCKED.value,
            "blocking_codes": (),
        }
        config = {"configurable": {"thread_id": workflow_id}}
        self.graph.invoke(state, config)
        snapshot = self._snapshot(self.graph.get_state(config).values)
        self.checkpoint_repository.save(snapshot)
        return snapshot

    def resume(self, workflow_id: str, decision: dict[str, object]) -> AutofillWorkflowSnapshot:
        """Resume only a persisted interrupted stage; no decision is inferred."""
        snapshot = self.checkpoint_repository.load(workflow_id)
        if snapshot.status in {AutofillWorkflowStage.CANCELLED, AutofillWorkflowStage.BLOCKED}:
            raise AutofillWorkflowError("This local autofill workflow cannot be resumed.")
        config = {"configurable": {"thread_id": workflow_id}}
        try:
            self.graph.invoke(Command(resume=decision), config)
            state = self.graph.get_state(config).values
        except Exception:  # noqa: BLE001 - a restarted memory checkpointer has no interrupt task.
            state = self._resume_from_snapshot(snapshot, decision)
        result = self._snapshot(state)
        self.checkpoint_repository.save(result)
        return result

    def resume_transition(
        self, action: str, request: AutofillTransitionRequest
    ) -> AutofillWorkflowSnapshot:
        """Resume using a typed opaque transition request from a deliberate UI action."""
        allowed = {
            "confirm_session_start",
            "confirm_exact_selected_fields",
            "skip",
            "cancel",
        }
        if action not in allowed:
            raise AutofillWorkflowError("This local autofill transition is invalid.")
        return self.resume(
            request.session_id,
            {
                "action": action,
                "confirmed": request.confirmed,
                "session_id": request.session_id,
                "expected_revision": request.expected_revision,
                "material_version_ref": request.material_version_ref,
                "selected_identifiers": list(request.selected_identifiers),
            },
        )

    def _prepare_session(self, state: AutofillWorkflowState) -> dict[str, object]:
        try:
            session = self.controller.prepare(
                AutofillPreparationRequest(
                    workspace_ref=state["workspace_ref"],
                    profile_artifact_ref=state["profile_artifact_ref"],
                    evidence_artifact_refs=state["evidence_artifact_refs"],
                    job_key=state["job_key"],
                    expected_revision=state["expected_revision"],
                    material_version_ref=state["material_version_ref"],
                    workflow_checkpoint_ref=state["workflow_checkpoint_ref"],
                    selected_identifiers=state["selected_identifiers"],
                    session_id=state["session_id"],
                )
            )
        except (AutofillGateError, ValueError):
            return {
                "status": AutofillWorkflowStage.BLOCKED.value,
                "blocking_codes": ("AUTOFILL_GATE_BLOCKED",),
            }
        return self._state_from_session(
            session, AutofillWorkflowStage.AWAITING_SESSION_CONFIRMATION
        )

    def _confirm_session(self, state: AutofillWorkflowState) -> dict[str, object]:
        decision = interrupt(self._interrupt_payload(state, "confirm_session_start"))
        return self._apply_start_decision(state, decision)

    def _confirm_fields(self, state: AutofillWorkflowState) -> dict[str, object]:
        decision = interrupt(self._interrupt_payload(state, "confirm_exact_selected_fields"))
        return self._apply_field_decision(state, decision)

    def _manual_review(self, state: AutofillWorkflowState) -> dict[str, object]:
        interrupt(
            {
                "stage": AutofillWorkflowStage.PREPARED_FOR_MANUAL_FIELD_ENTRY.value,
                "session_id": state["session_id"],
                "message": "Prepared for manual field entry.",
            }
        )
        return {}

    def _apply_start_decision(
        self, state: AutofillWorkflowState, decision: object
    ) -> dict[str, object]:
        if isinstance(decision, dict) and decision.get("action") == "cancel":
            try:
                session = self.controller.cancel(self._transition_request(state, confirmed=False))
            except AutofillGateError:
                return {
                    "status": AutofillWorkflowStage.BLOCKED.value,
                    "blocking_codes": ("CANCELLATION_INVALID",),
                }
            return self._state_from_session(session, AutofillWorkflowStage.CANCELLED)
        if not self._valid_decision(decision, state, "confirm_session_start"):
            return {
                "status": AutofillWorkflowStage.BLOCKED.value,
                "blocking_codes": ("START_CONFIRMATION_INVALID",),
            }
        request = self._transition_request(state, confirmed=True)
        try:
            session = self.controller.start(request)
        except AutofillGateError:
            return {
                "status": AutofillWorkflowStage.BLOCKED.value,
                "blocking_codes": ("START_CONFIRMATION_BLOCKED",),
            }
        return self._state_from_session(session, AutofillWorkflowStage.AWAITING_FIELD_CONFIRMATION)

    def _apply_field_decision(
        self, state: AutofillWorkflowState, decision: object
    ) -> dict[str, object]:
        if isinstance(decision, dict) and decision.get("action") == "cancel":
            try:
                session = self.controller.cancel(self._transition_request(state, confirmed=False))
            except AutofillGateError:
                return {
                    "status": AutofillWorkflowStage.BLOCKED.value,
                    "blocking_codes": ("CANCELLATION_INVALID",),
                }
            return self._state_from_session(session, AutofillWorkflowStage.CANCELLED)
        if isinstance(decision, dict) and decision.get("action") == "skip":
            requested = decision.get("selected_identifiers")
            if not isinstance(requested, list) or not all(
                isinstance(item, str) for item in requested
            ):
                return {
                    "status": AutofillWorkflowStage.BLOCKED.value,
                    "blocking_codes": ("FIELD_SELECTION_INVALID",),
                }
            try:
                session = self.controller.skip(
                    self._transition_request(state, confirmed=True, selected=tuple(requested))
                )
            except AutofillGateError:
                return {
                    "status": AutofillWorkflowStage.BLOCKED.value,
                    "blocking_codes": ("FIELD_SELECTION_INVALID",),
                }
            return self._state_from_session(
                session, AutofillWorkflowStage.AWAITING_FIELD_CONFIRMATION
            )
        if not self._valid_decision(decision, state, "confirm_exact_selected_fields"):
            return {
                "status": AutofillWorkflowStage.BLOCKED.value,
                "blocking_codes": ("FIELD_CONFIRMATION_INVALID",),
            }
        try:
            session = self.controller.populate(self._transition_request(state, confirmed=True))
        except AutofillGateError:
            return {
                "status": AutofillWorkflowStage.BLOCKED.value,
                "blocking_codes": ("FIELD_CONFIRMATION_BLOCKED",),
            }
        return self._state_from_session(
            session, AutofillWorkflowStage.PREPARED_FOR_MANUAL_FIELD_ENTRY
        )

    def _resume_from_snapshot(
        self, snapshot: AutofillWorkflowSnapshot, decision: dict[str, object]
    ) -> dict[str, object]:
        state = snapshot.model_dump(mode="python")
        if snapshot.status == AutofillWorkflowStage.AWAITING_SESSION_CONFIRMATION:
            return {**state, **self._apply_start_decision(state, decision)}
        if snapshot.status == AutofillWorkflowStage.AWAITING_FIELD_CONFIRMATION:
            return {**state, **self._apply_field_decision(state, decision)}
        if snapshot.status == AutofillWorkflowStage.PREPARED_FOR_MANUAL_FIELD_ENTRY:
            return state
        raise AutofillWorkflowError("This local autofill workflow cannot be resumed.")

    @staticmethod
    def _after_prepare(state: AutofillWorkflowState) -> str:
        return (
            "end" if state["status"] == AutofillWorkflowStage.BLOCKED.value else "confirm_session"
        )

    @staticmethod
    def _after_start(state: AutofillWorkflowState) -> str:
        return (
            "confirm_fields"
            if state["status"] == AutofillWorkflowStage.AWAITING_FIELD_CONFIRMATION.value
            else "end"
        )

    @staticmethod
    def _after_population(state: AutofillWorkflowState) -> str:
        if state["status"] == AutofillWorkflowStage.AWAITING_FIELD_CONFIRMATION.value:
            return "confirm_fields"
        if state["status"] == AutofillWorkflowStage.PREPARED_FOR_MANUAL_FIELD_ENTRY.value:
            return "manual_review"
        return "end"

    @staticmethod
    def _interrupt_payload(state: AutofillWorkflowState, action: str) -> dict[str, object]:
        return {
            "action": action,
            "session_id": state["session_id"],
            "expected_revision": state["expected_revision"],
            "material_version_ref": state["material_version_ref"],
            "selected_identifiers": state["selected_identifiers"],
        }

    @staticmethod
    def _valid_decision(decision: object, state: AutofillWorkflowState, action: str) -> bool:
        return bool(
            isinstance(decision, dict)
            and decision.get("action") == action
            and decision.get("confirmed") is True
            and decision.get("session_id") == state["session_id"]
            and decision.get("expected_revision") == state["expected_revision"]
            and decision.get("material_version_ref") == state["material_version_ref"]
            and tuple(decision.get("selected_identifiers", ()))
            == tuple(state["selected_identifiers"])
        )

    @staticmethod
    def _transition_request(
        state: AutofillWorkflowState,
        *,
        confirmed: bool,
        selected: tuple[str, ...] | None = None,
    ) -> AutofillTransitionRequest:
        return AutofillTransitionRequest(
            session_id=state["session_id"],
            workspace_ref=state["workspace_ref"],
            profile_artifact_ref=state["profile_artifact_ref"],
            evidence_artifact_refs=state["evidence_artifact_refs"],
            expected_revision=state["expected_revision"],
            material_version_ref=state["material_version_ref"],
            workflow_checkpoint_ref=state["workflow_checkpoint_ref"],
            selected_identifiers=state["selected_identifiers"] if selected is None else selected,
            confirmed=confirmed,
        )

    @staticmethod
    def _state_from_session(
        session: AutofillSession, stage: AutofillWorkflowStage
    ) -> dict[str, object]:
        return {
            "workflow_id": session.session_id,
            "session_id": session.session_id,
            "job_key": session.job_key,
            "workspace_ref": session.workspace_ref,
            "profile_artifact_ref": session.profile_artifact_ref,
            "evidence_artifact_refs": session.evidence_artifact_refs,
            "expected_revision": session.expected_revision,
            "material_version_ref": session.material_version_ref,
            "workflow_checkpoint_ref": session.workflow_checkpoint_ref,
            "selected_identifiers": tuple(
                field.identifier
                for field in session.fields
                if field.classification.value == "eligible"
                and field.identifier not in session.skipped_identifiers
            ),
            "field_classifications": {
                field.identifier: field.classification.value for field in session.fields
            },
            "status": stage.value,
            "blocking_codes": (),
        }

    @staticmethod
    def _snapshot(state: dict[str, object]) -> AutofillWorkflowSnapshot:
        return AutofillWorkflowSnapshot.model_validate(state)
