"""Typed, internal-only state for the LangGraph review workflow."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import TypedDict
from uuid import uuid4


class WorkflowStage(StrEnum):
    """Stages that never represent an external action."""

    INPUT_VALIDATION = "input_validation"
    JOB_PROCESSING = "job_processing"
    SCORING = "scoring"
    PERSONALIZATION = "personalization"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    REVISION_REQUESTED = "revision_requested"
    APPROVED_FOR_MANUAL_NEXT_STEP = "approved_for_manual_next_step"
    REJECTED = "rejected"
    RECOVERABLE_FAILURE = "recoverable_failure"
    FAILED = "failed"


class WorkflowDecision(StrEnum):
    """Explicit internal decisions accepted at the human-review checkpoint."""

    APPROVE = "approve"
    REQUEST_REVISION = "request_revision"
    REJECT = "reject"
    REVISION_READY = "revision_ready"


class WorkflowState(TypedDict):
    """LangGraph state containing references and redacted operational metadata only."""

    workflow_id: str
    job_key: str
    workspace_reference: str
    candidate_reference: str
    evidence_reference: str
    discovery_reference: str
    score_reference: str | None
    application_reference: str | None
    stage: WorkflowStage
    review_revision: int
    warnings: list[str]
    recoverable_errors: list[str]
    completed_nodes: list[str]
    created_at: datetime
    updated_at: datetime


_PROHIBITED_LEGACY_STAGES = {"applied", "autofilled", "ready_for_autofill", "submitted"}


def create_initial_state(
    *,
    job_key: str = "",
    workspace_reference: str = "",
    candidate_reference: str = "",
    evidence_reference: str = "",
    discovery_reference: str = "",
    score_reference: str | None = None,
    application_reference: str | None = None,
    workflow_id: str | None = None,
) -> WorkflowState:
    """Create a reference-only workflow state without an approval decision."""
    now = datetime.now(UTC)
    return {
        "workflow_id": workflow_id or str(uuid4()),
        "job_key": job_key,
        "workspace_reference": workspace_reference,
        "candidate_reference": candidate_reference,
        "evidence_reference": evidence_reference,
        "discovery_reference": discovery_reference,
        "score_reference": score_reference,
        "application_reference": application_reference,
        "stage": WorkflowStage.INPUT_VALIDATION,
        "review_revision": 0,
        "warnings": [],
        "recoverable_errors": [],
        "completed_nodes": [],
        "created_at": now,
        "updated_at": now,
    }


def validate_workflow_state(state: WorkflowState | dict[str, object]) -> WorkflowState:
    """Fail closed on malformed or legacy external-action workflow data."""
    raw_stage = str(state.get("stage", ""))
    if raw_stage in _PROHIBITED_LEGACY_STAGES:
        raise ValueError("Workflow checkpoint is incompatible with the local approval workflow.")
    try:
        stage = WorkflowStage(raw_stage)
    except ValueError as error:
        raise ValueError("Workflow checkpoint has an invalid internal stage.") from error
    required = {
        "workflow_id",
        "job_key",
        "workspace_reference",
        "candidate_reference",
        "evidence_reference",
        "discovery_reference",
        "review_revision",
        "warnings",
        "recoverable_errors",
        "completed_nodes",
        "created_at",
        "updated_at",
    }
    if not required.issubset(state):
        raise ValueError("Workflow checkpoint is incomplete.")
    validated = dict(state)
    validated["stage"] = stage
    return validated  # type: ignore[return-value]
