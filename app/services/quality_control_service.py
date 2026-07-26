"""Read-only, sanitized quality gates for internal review decisions."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import Field

from app.dashboard.data_loader import load_dashboard_data
from app.models.candidate import StrictModel
from app.models.dashboard_review import DashboardReviewStatus
from app.services.claim_verification import ClaimVerificationError, verify_application_claims
from app.services.evidence_repository import load_evidence_bank
from app.workflows.repository import find_workflow_for_job
from app.workflows.state import WorkflowStage


class QualityStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    BLOCKED = "blocked"


class FindingSeverity(StrEnum):
    WARNING = "warning"
    BLOCKING = "blocking"


class QualityFinding(StrictModel):
    code: str = Field(min_length=1)
    severity: FindingSeverity
    message: str = Field(min_length=1)
    recovery_guidance: str = Field(min_length=1)


class QualityReport(StrictModel):
    status: QualityStatus
    job_key: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    blocking_count: int = Field(ge=0)
    findings: list[QualityFinding] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = "1.0"


class QualityControlError(ValueError):
    """Raised when a request itself is unsafe or cannot be read safely."""


def _finding(code: str, severity: FindingSeverity, message: str, guidance: str) -> QualityFinding:
    return QualityFinding(code=code, severity=severity, message=message, recovery_guidance=guidance)


def check_review_quality(
    workspace_path: str | Path,
    job_key: str,
    expected_revision: int,
    *,
    evidence_path: str | Path | None = None,
    workflow_directory: str | Path | None = None,
) -> QualityReport:
    """Evaluate current local artifacts without mutating them or exposing their content."""
    findings: list[QualityFinding] = []
    try:
        data = load_dashboard_data(workspace_path)
        view = next((item for item in data.jobs if item.record.job_key == job_key), None)
    except Exception as error:
        raise QualityControlError("Quality checks could not load the review workspace.") from error
    if view is None or view.job is None:
        findings.append(
            _finding(
                "WORKSPACE_JOB_INVALID",
                FindingSeverity.BLOCKING,
                "The selected job is unavailable or incompatible.",
                "Restore a valid matching discovery artifact.",
            )
        )
    else:
        if view.record.revision != expected_revision:
            findings.append(
                _finding(
                    "REVISION_STALE",
                    FindingSeverity.BLOCKING,
                    "The review revision changed.",
                    "Reload before deciding.",
                )
            )
        if view.record.status in {
            DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP,
            DashboardReviewStatus.REJECTED,
        }:
            findings.append(
                _finding(
                    "TERMINAL_DECISION",
                    FindingSeverity.BLOCKING,
                    "The internal decision is final.",
                    "Do not repeat or alter a final decision.",
                )
            )
    if view is None or view.application is None:
        findings.append(
            _finding(
                "APPLICATION_UNAVAILABLE",
                FindingSeverity.BLOCKING,
                "Required application materials are unavailable or invalid.",
                "Restore valid application materials.",
            )
        )
    else:
        application = view.application
        if any(not item.resolved for item in application.review_items):
            findings.append(
                _finding(
                    "REVIEW_ITEMS_UNRESOLVED",
                    FindingSeverity.BLOCKING,
                    "Required review items remain unresolved.",
                    "Resolve every required review item.",
                )
            )
        if any(answer.requires_confirmation for answer in application.application_answers):
            findings.append(
                _finding(
                    "ANSWERS_UNCONFIRMED",
                    FindingSeverity.BLOCKING,
                    "Required answers remain unconfirmed.",
                    "Confirm required answers directly with the candidate.",
                )
            )
        if evidence_path is None:
            findings.append(
                _finding(
                    "EVIDENCE_REFERENCE_MISSING",
                    FindingSeverity.BLOCKING,
                    "Authoritative evidence is required for approval checks.",
                    "Provide the local evidence-bank reference.",
                )
            )
        else:
            try:
                verify_application_claims(application, load_evidence_bank(evidence_path))
            except (ClaimVerificationError, OSError, TypeError, ValueError):
                findings.append(
                    _finding(
                        "CLAIM_EVIDENCE_INVALID",
                        FindingSeverity.BLOCKING,
                        "Application claims could not be verified.",
                        "Restore compatible verified evidence.",
                    )
                )
    if view is not None and view.score is None:
        findings.append(
            _finding(
                "OPTIONAL_SCORE_UNAVAILABLE",
                FindingSeverity.WARNING,
                "No optional score is available.",
                "Review the job and evidence manually.",
            )
        )
    if workflow_directory is not None:
        workflow = find_workflow_for_job(job_key, workflow_directory)
        if workflow is None:
            findings.append(
                _finding(
                    "WORKFLOW_CHECKPOINT_MISSING",
                    FindingSeverity.BLOCKING,
                    "The required workflow checkpoint is unavailable.",
                    "Restore a compatible local workflow checkpoint.",
                )
            )
        elif (
            workflow["review_revision"] != expected_revision
            or workflow["stage"] != WorkflowStage.AWAITING_HUMAN_REVIEW
        ):
            findings.append(
                _finding(
                    "WORKFLOW_STATE_CONFLICT",
                    FindingSeverity.BLOCKING,
                    "Workflow state conflicts with the current review.",
                    "Reload the workflow and resolve its state conflict.",
                )
            )
    findings.sort(key=lambda finding: (finding.severity.value, finding.code))
    blocked = sum(finding.severity == FindingSeverity.BLOCKING for finding in findings)
    warnings = len(findings) - blocked
    return QualityReport(
        status=QualityStatus.BLOCKED
        if blocked
        else QualityStatus.WARNING
        if warnings
        else QualityStatus.PASS,
        job_key=job_key,
        expected_revision=expected_revision,
        warning_count=warnings,
        blocking_count=blocked,
        findings=findings,
    )
