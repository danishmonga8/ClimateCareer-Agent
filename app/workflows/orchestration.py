"""Local LangGraph orchestration for the existing human-review workflow."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.dashboard.data_loader import load_dashboard_data
from app.models.dashboard_review import DashboardReviewAction
from app.models.personalization import ApplicationStatus
from app.services.application_review_service import begin_application_review
from app.services.dashboard_repository import save_updated_dashboard_workspace
from app.services.dashboard_review_service import apply_dashboard_decision, resubmit_for_review
from app.services.discovery_repository import load_discovery_snapshot
from app.services.evidence_repository import load_evidence_bank
from app.services.personalization_repository import (
    load_personalized_application,
    save_personalized_application,
)
from app.services.profile_service import load_candidate_profile
from app.services.quality_control_service import QualityStatus, check_review_quality
from app.services.scoring_repository import load_scoring_result
from app.workflows.repository import load_workflow_checkpoint, save_workflow_checkpoint
from app.workflows.state import (
    WorkflowDecision,
    WorkflowStage,
    WorkflowState,
    validate_workflow_state,
)


class WorkflowOrchestrationError(ValueError):
    """Raised for safe-to-display workflow errors."""


@dataclass(frozen=True)
class WorkflowServices:
    """Injectable local operations; tests can replace every artifact/model operation."""

    load_profile: Callable[[str], object] = load_candidate_profile
    load_evidence: Callable[[str], object] = load_evidence_bank
    load_discovery: Callable[[str], object] = load_discovery_snapshot
    load_score: Callable[[str], object] = load_scoring_result
    load_application: Callable[[str], object] = load_personalized_application
    save_application: Callable[[object, str], object] = save_personalized_application


def _now() -> datetime:
    return datetime.now(UTC)


class WorkflowOrchestrator:
    """Durable coordinator that delegates all business rules to Phase 1-5 services."""

    def __init__(self, checkpoint_directory: str | Path, services: WorkflowServices | None = None):
        self.checkpoint_directory = Path(checkpoint_directory)
        self.services = services or WorkflowServices()
        self.checkpointer = InMemorySaver()
        graph = StateGraph(WorkflowState)
        graph.add_node("validate_inputs", self._validate_inputs)
        graph.add_node("process_job", self._process_job)
        graph.add_node("load_score", self._load_score)
        graph.add_node("prepare_materials", self._prepare_materials)
        graph.add_node("human_review", self._human_review)
        graph.add_edge(START, "validate_inputs")
        graph.add_edge("validate_inputs", "process_job")
        graph.add_edge("process_job", "load_score")
        graph.add_edge("load_score", "prepare_materials")
        graph.add_edge("prepare_materials", "human_review")
        graph.add_edge("human_review", END)
        self.graph = graph.compile(checkpointer=self.checkpointer)

    def _update(self, state: WorkflowState, stage: WorkflowStage, node: str) -> dict[str, Any]:
        completed = [*state["completed_nodes"]]
        if node not in completed:
            completed.append(node)
        return {"stage": stage, "completed_nodes": completed, "updated_at": _now()}

    def _recoverable(self, state: WorkflowState, message: str) -> dict[str, Any]:
        return {
            "stage": WorkflowStage.RECOVERABLE_FAILURE,
            "recoverable_errors": [*state["recoverable_errors"], message],
            "updated_at": _now(),
        }

    def _validate_inputs(self, state: WorkflowState) -> dict[str, Any]:
        try:
            self.services.load_profile(state["candidate_reference"])
            self.services.load_evidence(state["evidence_reference"])
        except (OSError, TypeError, ValueError, AttributeError):
            return self._recoverable(state, "Candidate inputs are unavailable or invalid.")
        return self._update(state, WorkflowStage.JOB_PROCESSING, "validate_inputs")

    def _process_job(self, state: WorkflowState) -> dict[str, Any]:
        if state["stage"] == WorkflowStage.RECOVERABLE_FAILURE:
            return {}
        try:
            snapshot = self.services.load_discovery(state["discovery_reference"])
            matches = [
                job
                for job in snapshot.jobs
                if f"{job.source.value}:{job.source_board}:{job.source_job_id}" == state["job_key"]
            ]
            if len(matches) != 1:
                return self._recoverable(
                    state, "The discovery snapshot has no unique matching job."
                )
        except (OSError, TypeError, ValueError, AttributeError):
            return self._recoverable(state, "The discovery snapshot is unavailable or invalid.")
        return self._update(state, WorkflowStage.SCORING, "process_job")

    def _load_score(self, state: WorkflowState) -> dict[str, Any]:
        if state["stage"] == WorkflowStage.RECOVERABLE_FAILURE:
            return {}
        if not state["score_reference"]:
            return self._recoverable(state, "A scoring result is required before human review.")
        try:
            self.services.load_score(state["score_reference"])
        except (OSError, TypeError, ValueError, AttributeError):
            return self._recoverable(state, "The scoring result is unavailable or invalid.")
        return self._update(state, WorkflowStage.PERSONALIZATION, "load_score")

    def _prepare_materials(self, state: WorkflowState) -> dict[str, Any]:
        if state["stage"] == WorkflowStage.RECOVERABLE_FAILURE:
            return {}
        if not state["application_reference"]:
            return self._recoverable(
                state, "Application materials are required before human review."
            )
        try:
            application = self.services.load_application(state["application_reference"])
            if application.status == ApplicationStatus.DRAFT:
                self.services.save_application(
                    begin_application_review(application), state["application_reference"]
                )
            elif application.status == ApplicationStatus.APPROVED_BY_USER:
                return self._recoverable(state, "The linked application is already final.")
        except (OSError, TypeError, ValueError, AttributeError):
            return self._recoverable(state, "Application materials are unavailable or invalid.")
        return self._update(state, WorkflowStage.AWAITING_HUMAN_REVIEW, "prepare_materials")

    def _human_review(self, state: WorkflowState) -> dict[str, Any]:
        if state["stage"] != WorkflowStage.AWAITING_HUMAN_REVIEW:
            return {}
        decision = interrupt(
            {"workflow_id": state["workflow_id"], "revision": state["review_revision"]}
        )
        return self._apply_decision(state, decision)

    def _apply_decision(self, state: WorkflowState, decision: object) -> dict[str, Any]:
        if not isinstance(decision, dict):
            return self._recoverable(state, "A confirmed internal decision is required.")
        try:
            action = WorkflowDecision(str(decision.get("action", "")))
            expected_revision = int(decision.get("expected_revision"))
            reviewer = str(decision.get("reviewer_label", "")).strip()
            note = str(decision.get("reason_or_note", "")).strip() or None
        except (TypeError, ValueError):
            return self._recoverable(
                state, "The internal decision is invalid. Reload and try again."
            )
        if action not in {
            WorkflowDecision.APPROVE,
            WorkflowDecision.REQUEST_REVISION,
            WorkflowDecision.REJECT,
        }:
            return self._recoverable(state, "This decision cannot be processed at human review.")
        if action == WorkflowDecision.APPROVE:
            report = check_review_quality(
                state["workspace_reference"],
                state["job_key"],
                expected_revision,
                evidence_path=state["evidence_reference"],
                workflow_directory=self.checkpoint_directory,
            )
            if report.status == QualityStatus.BLOCKED:
                return self._recoverable(state, "Quality checks blocked this internal approval.")
        try:
            data = load_dashboard_data(state["workspace_reference"])
            record = next(
                item.record for item in data.jobs if item.record.job_key == state["job_key"]
            )
            linked = next(
                item.application for item in data.jobs if item.record.job_key == state["job_key"]
            )
            mapping = {
                WorkflowDecision.APPROVE: DashboardReviewAction.APPROVED,
                WorkflowDecision.REQUEST_REVISION: DashboardReviewAction.REVISION_REQUESTED,
                WorkflowDecision.REJECT: DashboardReviewAction.REJECTED,
            }
            updated = apply_dashboard_decision(
                data.workspace,
                state["job_key"],
                mapping[action],
                expected_revision,
                reviewer,
                note,
                linked_application=linked,
            )
            save_updated_dashboard_workspace(data.workspace, updated, state["workspace_reference"])
        except (OSError, TypeError, ValueError, AttributeError):
            return self._recoverable(
                state, "The decision could not be saved. Reload and try again."
            )
        stage = {
            WorkflowDecision.APPROVE: WorkflowStage.APPROVED_FOR_MANUAL_NEXT_STEP,
            WorkflowDecision.REQUEST_REVISION: WorkflowStage.REVISION_REQUESTED,
            WorkflowDecision.REJECT: WorkflowStage.REJECTED,
        }[action]
        return {"stage": stage, "review_revision": record.revision + 1, "updated_at": _now()}

    def start(self, state: WorkflowState) -> WorkflowState:
        """Run local preparation once and stop at the LangGraph human interrupt."""
        validated = validate_workflow_state(state)
        config = {"configurable": {"thread_id": validated["workflow_id"]}}
        self.graph.invoke(validated, config)
        result = validate_workflow_state(self.graph.get_state(config).values)
        save_workflow_checkpoint(result, self.checkpoint_directory)
        return result

    def resume(self, workflow_id: str, decision: dict[str, object]) -> WorkflowState:
        """Resume a live interrupt or safely restore a persisted local checkpoint."""
        state = load_workflow_checkpoint(workflow_id, self.checkpoint_directory)
        if state["stage"] in {WorkflowStage.APPROVED_FOR_MANUAL_NEXT_STEP, WorkflowStage.REJECTED}:
            raise WorkflowOrchestrationError("This internal workflow decision is final.")
        if state["stage"] == WorkflowStage.REVISION_REQUESTED:
            return self._return_revision(state, decision)
        if state["stage"] != WorkflowStage.AWAITING_HUMAN_REVIEW:
            raise WorkflowOrchestrationError("This workflow is not awaiting a human decision.")
        config = {"configurable": {"thread_id": workflow_id}}
        try:
            self.graph.invoke(Command(resume=decision), config)
            result = validate_workflow_state(self.graph.get_state(config).values)
        except Exception:  # noqa: BLE001 - LangGraph can raise implementation-specific resume errors.
            result = validate_workflow_state({**state, **self._apply_decision(state, decision)})
        save_workflow_checkpoint(result, self.checkpoint_directory)
        return result

    def _return_revision(self, state: WorkflowState, decision: dict[str, object]) -> WorkflowState:
        if decision.get("action") != WorkflowDecision.REVISION_READY.value:
            raise WorkflowOrchestrationError(
                "A revision must be marked ready before resuming review."
            )
        try:
            data = load_dashboard_data(state["workspace_reference"])
            updated = resubmit_for_review(
                data.workspace,
                state["job_key"],
                int(decision.get("expected_revision")),
                str(decision.get("reviewer_label", "")).strip(),
                str(decision.get("reason_or_note", "")).strip() or None,
            )
            save_updated_dashboard_workspace(data.workspace, updated, state["workspace_reference"])
        except Exception as error:
            raise WorkflowOrchestrationError(
                "The revision could not be returned to review."
            ) from error
        result = validate_workflow_state(
            {
                **state,
                "stage": WorkflowStage.AWAITING_HUMAN_REVIEW,
                "review_revision": state["review_revision"] + 1,
                "updated_at": _now(),
            }
        )
        save_workflow_checkpoint(result, self.checkpoint_directory)
        return result
