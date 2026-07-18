"""Shared workflow state for the ClimateCareer-Agent LangGraph."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import TypedDict
from uuid import uuid4

from app.models.candidate import CandidateProfile
from app.models.job import JobDescription
from app.models.scoring import JobRelevanceScore


class WorkflowStage(StrEnum):
    """Current stage of an application workflow."""

    CREATED = "created"
    CANDIDATE_PROFILE_READY = "candidate_profile_ready"
    JOB_PARSED = "job_parsed"
    ELIGIBILITY_CHECKED = "eligibility_checked"
    SCORED = "scored"
    SHORTLISTED = "shortlisted"
    PERSONALIZATION = "personalization"
    QUALITY_REVIEW = "quality_review"
    AWAITING_APPROVAL = "awaiting_approval"
    READY_FOR_AUTOFILL = "ready_for_autofill"
    AUTOFILLED = "autofilled"
    APPLIED = "applied"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    FAILED = "failed"


class ApprovalStatus(StrEnum):
    """Human approval status for controlled actions."""

    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"


class ApplicationState(TypedDict):
    """Information shared between LangGraph workflow nodes."""

    workflow_id: str
    stage: WorkflowStage
    approval_status: ApprovalStatus

    candidate_profile: CandidateProfile | None
    job_description: JobDescription | None
    relevance_score: JobRelevanceScore | None

    evidence_bank: list[dict[str, object]]
    company_research: dict[str, object]

    tailored_resume: str | None
    cover_letter: str | None
    recruiter_email: str | None
    application_answers: dict[str, str]

    required_manual_inputs: list[str]
    quality_control_flags: list[str]
    errors: list[str]
    audit_log: list[str]

    created_at: datetime
    updated_at: datetime


def create_initial_state() -> ApplicationState:
    """Create an independent, empty workflow state."""
    current_time = datetime.now(UTC)

    return ApplicationState(
        workflow_id=str(uuid4()),
        stage=WorkflowStage.CREATED,
        approval_status=ApprovalStatus.NOT_REQUESTED,
        candidate_profile=None,
        job_description=None,
        relevance_score=None,
        evidence_bank=[],
        company_research={},
        tailored_resume=None,
        cover_letter=None,
        recruiter_email=None,
        application_answers={},
        required_manual_inputs=[],
        quality_control_flags=[],
        errors=[],
        audit_log=["Workflow created."],
        created_at=current_time,
        updated_at=current_time,
    )