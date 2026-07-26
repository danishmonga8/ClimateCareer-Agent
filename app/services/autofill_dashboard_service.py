"""Read-only dashboard projection and deliberate local session controls."""

from dataclasses import dataclass

from app.models.autofill import (
    AutofillDashboardSessionView,
    AutofillSession,
    AutofillSessionStatus,
    AutofillTransitionRequest,
    AutofillWorkflowStage,
    FieldClassification,
)
from app.models.dashboard_review import DashboardReviewRecord, DashboardReviewStatus
from app.services.autofill_audit_service import AutofillAuditAction
from app.services.autofill_repository import AutofillSessionRepository, AutofillStorageError
from app.workflows.autofill_orchestration import AutofillWorkflow, AutofillWorkflowError
from app.workflows.autofill_repository import (
    AutofillWorkflowCheckpointError,
    AutofillWorkflowRepository,
)


class AutofillDashboardError(ValueError):
    """Sanitized dashboard-control failure."""


@dataclass(frozen=True)
class AutofillDashboardService:
    """Trusted integration surface; rendering reads snapshots and never resolves artifacts."""

    session_repository: AutofillSessionRepository
    workflow_repository: AutofillWorkflowRepository
    workflow: AutofillWorkflow

    def read_view(self, record: DashboardReviewRecord) -> AutofillDashboardSessionView | None:
        """Load only serialized session and workflow metadata; never mutate or validate gates."""
        try:
            stored = self.session_repository.find_for_job(record.job_key)
        except AutofillStorageError as error:
            raise AutofillDashboardError("Autofill session metadata is unavailable.") from error
        if stored is None:
            return None
        try:
            workflow = self.workflow_repository.load(stored.session.session_id)
        except AutofillWorkflowCheckpointError:
            workflow = None
        return _view(record, stored.session, stored.events, workflow)

    def confirm_start(self, view: AutofillDashboardSessionView) -> None:
        self._resume("confirm_session_start", view, confirmed=True)

    def confirm_population(self, view: AutofillDashboardSessionView) -> None:
        self._resume("confirm_exact_selected_fields", view, confirmed=True)

    def skip(self, view: AutofillDashboardSessionView, identifiers: tuple[str, ...]) -> None:
        if not identifiers or not set(identifiers).issubset(set(view.selected_identifiers)):
            raise AutofillDashboardError("Only currently selected eligible fields can be skipped.")
        self._resume("skip", view, confirmed=True, selected_identifiers=identifiers)

    def cancel(self, view: AutofillDashboardSessionView) -> None:
        self._resume("cancel", view, confirmed=False)

    def _resume(
        self,
        action: str,
        view: AutofillDashboardSessionView,
        *,
        confirmed: bool,
        selected_identifiers: tuple[str, ...] | None = None,
    ) -> None:
        if (action != "cancel" and view.blocking_codes) or view.status in {
            AutofillSessionStatus.CANCELLED,
            AutofillSessionStatus.POPULATED,
            AutofillSessionStatus.COMPLETED,
        }:
            raise AutofillDashboardError("This autofill session is not available for that action.")
        try:
            session = self.session_repository.load(view.session_id).session
            request = AutofillTransitionRequest(
                session_id=session.session_id,
                workspace_ref=session.workspace_ref,
                profile_artifact_ref=session.profile_artifact_ref,
                evidence_artifact_refs=session.evidence_artifact_refs,
                expected_revision=session.expected_revision,
                material_version_ref=session.material_version_ref,
                workflow_checkpoint_ref=session.workflow_checkpoint_ref,
                selected_identifiers=(
                    view.selected_identifiers
                    if selected_identifiers is None
                    else selected_identifiers
                ),
                confirmed=confirmed,
            )
            self.workflow.resume_transition(action, request)
        except (AutofillStorageError, AutofillWorkflowError, ValueError) as error:
            raise AutofillDashboardError(
                "Fresh local validation could not complete this autofill action."
            ) from error


def _view(
    record: DashboardReviewRecord,
    session: AutofillSession,
    events: tuple,
    workflow: object | None,
) -> AutofillDashboardSessionView:
    """Build a sanitized projection without consulting any private artifact loader."""
    artifact_compatible = (
        record.artifacts.profile_artifact_ref == session.profile_artifact_ref
        and tuple(record.artifacts.evidence_artifact_refs) == session.evidence_artifact_refs
    )
    material_compatible = session.material_version_ref in {
        material.version for material in record.materials
    }
    blocking_codes: list[str] = []
    guidance: list[str] = []
    if record.status != DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP:
        blocking_codes.append("AUTOFILL_APPROVAL_REQUIRED")
        guidance.append("Record an internal approval before using controlled field entry.")
    if record.revision != session.expected_revision:
        blocking_codes.append("AUTOFILL_REVISION_STALE")
        guidance.append("Reload the approved review package and prepare a new session.")
    if not material_compatible:
        blocking_codes.append("AUTOFILL_MATERIAL_VERSION_MISMATCH")
        guidance.append("Prepare a session for the current approved material version.")
    if not artifact_compatible:
        blocking_codes.append("AUTOFILL_ARTIFACT_REFERENCE_MISMATCH")
        guidance.append("Restore compatible opaque artifact references in the workspace.")
    workflow_stage = None
    if workflow is None:
        blocking_codes.append("AUTOFILL_WORKFLOW_CHECKPOINT_MISSING")
        guidance.append("Restore the matching local autofill workflow checkpoint.")
    else:
        workflow_stage = workflow.status
        if workflow.session_id != session.session_id:
            blocking_codes.append("AUTOFILL_WORKFLOW_SESSION_MISMATCH")
            guidance.append("Restore the matching local autofill workflow checkpoint.")
        expected_stage = {
            AutofillSessionStatus.AWAITING_START_CONFIRMATION: AutofillWorkflowStage.AWAITING_SESSION_CONFIRMATION,
            AutofillSessionStatus.AWAITING_POPULATION_CONFIRMATION: AutofillWorkflowStage.AWAITING_FIELD_CONFIRMATION,
            AutofillSessionStatus.POPULATED: AutofillWorkflowStage.PREPARED_FOR_MANUAL_FIELD_ENTRY,
            AutofillSessionStatus.CANCELLED: AutofillWorkflowStage.CANCELLED,
        }.get(session.status)
        if expected_stage is not None and workflow.status != expected_stage:
            blocking_codes.append("AUTOFILL_WORKFLOW_STAGE_CONFLICT")
            guidance.append("Reload the matching local workflow before taking another action.")
    selected = tuple(
        field.identifier
        for field in session.fields
        if (
            field.classification == FieldClassification.ELIGIBLE
            and field.identifier not in session.skipped_identifiers
        )
    )
    return AutofillDashboardSessionView(
        session_id=session.session_id,
        status=session.status,
        job_key=session.job_key,
        expected_revision=session.expected_revision,
        current_revision=record.revision,
        revision_compatible=record.revision == session.expected_revision,
        material_version_compatible=material_compatible,
        artifact_references_compatible=artifact_compatible,
        quality_status=session.last_quality_status,
        quality_warning_count=session.quality_warning_count,
        eligible_count=sum(
            field.classification == FieldClassification.ELIGIBLE for field in session.fields
        ),
        manual_count=sum(
            field.classification == FieldClassification.MANUAL for field in session.fields
        ),
        selected_count=len(selected),
        prepared_count=sum(event.action == AutofillAuditAction.FIELD_PREPARED for event in events),
        populated_count=sum(
            event.action == AutofillAuditAction.FIELD_POPULATED for event in events
        ),
        skipped_count=sum(event.action == AutofillAuditAction.FIELD_SKIPPED for event in events),
        blocked_count=len(blocking_codes),
        fields=session.fields,
        selected_identifiers=selected,
        workflow_stage=workflow_stage,
        blocking_codes=tuple(blocking_codes),
        recovery_guidance=tuple(dict.fromkeys(guidance)),
    )
