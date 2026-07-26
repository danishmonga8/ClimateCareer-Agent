"""Fresh-gated, local-only controller for reference-only field-entry sessions."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.dashboard.data_loader import load_dashboard_data
from app.models.autofill import (
    AutofillPreparationRequest,
    AutofillQualityStatus,
    AutofillSession,
    AutofillSessionStatus,
    AutofillTransitionRequest,
    FieldClassification,
)
from app.models.candidate import CandidateProfile
from app.models.dashboard_review import DashboardReviewStatus
from app.services.autofill_audit_service import (
    AutofillAuditAction,
    AutofillAuditEvent,
    append_event,
)
from app.services.autofill_repository import AutofillSessionRepository, StoredAutofillSession
from app.services.autofill_service import (
    AutofillError,
    confirm_population,
    confirm_start,
    prepare_session,
)
from app.services.profile_completeness import assess_profile_completeness
from app.services.quality_control_service import QualityReport, QualityStatus, check_review_quality


class AutofillGateError(ValueError):
    """Sanitized failure raised before any session transition or field entry."""


@dataclass(frozen=True, repr=False)
class TransientResolverContext:
    """Operation-local data that must never be returned or persisted."""

    workspace_ref: str
    workspace_path: Path = field(repr=False)
    profile: CandidateProfile = field(repr=False)
    evidence_paths: tuple[Path, ...] = field(repr=False)
    workflow_checkpoint_directory: Path | None = field(default=None, repr=False)


ResolveContext = Callable[
    [str, str, tuple[str, ...], str | None],
    TransientResolverContext,
]


@dataclass(frozen=True, repr=False)
class FreshGateResult:
    """Operation-local validation outcome; it never enters a resolver context."""

    context: TransientResolverContext = field(repr=False)
    quality: QualityReport


@dataclass
class LocalAutofillController:
    """Controller whose public operations accept opaque typed request models only."""

    resolve_context: ResolveContext | None = None
    session_repository: AutofillSessionRepository | None = None
    sessions: dict[str, AutofillSession] = field(default_factory=dict)
    events: list[AutofillAuditEvent] = field(default_factory=list)

    def prepare(self, request: AutofillPreparationRequest) -> AutofillSession:
        """Freshly validate approved artifacts before creating a local session."""
        gate = self._gate_preparation(request)
        session = prepare_session(
            gate.context.profile,
            request.workspace_ref,
            request.profile_artifact_ref,
            request.evidence_artifact_refs,
            request.job_key,
            request.expected_revision,
            request.material_version_ref,
            request.workflow_checkpoint_ref,
            request.selected_identifiers,
            request.session_id,
        )
        session = self._with_quality(session, gate.quality)
        events = self._events_for_preparation(session)
        self._commit(session, events)
        return session

    def start(self, request: AutofillTransitionRequest) -> AutofillSession:
        """Process only an explicit first confirmation after a fresh internal gate."""
        session = self._session(request.session_id)
        self._match_request(session, request, require_selected=True)
        if not request.confirmed:
            return self.cancel(request)
        gate = self._gate_transition(session, request)
        session = self._with_quality(session, gate.quality)
        if session.status == AutofillSessionStatus.AWAITING_POPULATION_CONFIRMATION:
            return session
        if session.status != AutofillSessionStatus.AWAITING_START_CONFIRMATION:
            raise AutofillGateError("This autofill session cannot be confirmed.")
        try:
            updated = confirm_start(session, True)
        except AutofillError as error:
            raise AutofillGateError("This autofill session cannot be confirmed.") from error
        self._commit(
            updated,
            self._with_event(
                updated,
                AutofillAuditAction.SESSION_CONFIRMED,
                events=self._session_events(updated),
            ),
        )
        return updated

    def populate(self, request: AutofillTransitionRequest) -> AutofillSession:
        """Mark exact selected local fields populated after a fresh second confirmation."""
        session = self._session(request.session_id)
        self._match_request(session, request, require_selected=True)
        if not request.confirmed:
            return self.cancel(request)
        gate = self._gate_transition(session, request)
        session = self._with_quality(session, gate.quality)
        if session.status == AutofillSessionStatus.POPULATED:
            return session
        if session.status != AutofillSessionStatus.AWAITING_POPULATION_CONFIRMATION:
            raise AutofillGateError("This autofill session cannot populate fields.")
        try:
            updated = confirm_population(session, True)
        except AutofillError as error:
            raise AutofillGateError("This autofill session cannot populate fields.") from error
        events = self._with_event(
            updated,
            AutofillAuditAction.SESSION_COMPLETED,
            events=self._session_events(updated),
        )
        for item in updated.fields:
            if (
                item.classification == FieldClassification.ELIGIBLE
                and item.identifier not in updated.skipped_identifiers
            ):
                events = self._with_event(
                    updated, AutofillAuditAction.FIELD_POPULATED, item.identifier, events
                )
        self._commit(updated, events)
        return updated

    def skip(self, request: AutofillTransitionRequest) -> AutofillSession:
        """Record an intentional manual skip without retaining any field value."""
        session = self._session(request.session_id)
        self._match_request(session, request, require_selected=False)
        gate = self._gate_transition(session, request)
        session = self._with_quality(session, gate.quality)
        if session.status != AutofillSessionStatus.AWAITING_POPULATION_CONFIRMATION:
            raise AutofillGateError("This autofill session cannot skip fields now.")
        eligible = {
            field.identifier
            for field in session.fields
            if field.classification == FieldClassification.ELIGIBLE
        }
        if not request.selected_identifiers or not set(request.selected_identifiers).issubset(
            eligible
        ):
            raise AutofillGateError("Only selected eligible fields can be skipped.")
        skipped = tuple(
            identifier
            for identifier in (*session.skipped_identifiers, *request.selected_identifiers)
            if identifier in eligible
        )
        updated = session.model_copy(update={"skipped_identifiers": tuple(dict.fromkeys(skipped))})
        events = self._session_events(updated)
        for identifier in request.selected_identifiers:
            events = self._with_event(
                updated, AutofillAuditAction.FIELD_SKIPPED, identifier, events
            )
        self._commit(updated, events)
        return updated

    def cancel(self, request: AutofillTransitionRequest) -> AutofillSession:
        """Safely and idempotently cancel without resolving private artifacts."""
        session = self._session(request.session_id)
        self._match_request(session, request, require_selected=False)
        if session.status == AutofillSessionStatus.CANCELLED:
            return session
        if session.status in {AutofillSessionStatus.POPULATED, AutofillSessionStatus.COMPLETED}:
            raise AutofillGateError("This autofill session is already complete.")
        updated = session.model_copy(update={"status": AutofillSessionStatus.CANCELLED})
        self._commit(
            updated,
            self._with_event(
                updated,
                AutofillAuditAction.SESSION_CANCELLED,
                events=self._session_events(updated),
            ),
        )
        return updated

    def _gate_preparation(self, request: AutofillPreparationRequest) -> FreshGateResult:
        return self._gate(
            workspace_ref=request.workspace_ref,
            profile_artifact_ref=request.profile_artifact_ref,
            evidence_artifact_refs=request.evidence_artifact_refs,
            job_key=request.job_key,
            expected_revision=request.expected_revision,
            material_version_ref=request.material_version_ref,
            workflow_checkpoint_ref=request.workflow_checkpoint_ref,
        )

    def _gate_transition(
        self, session: AutofillSession, request: AutofillTransitionRequest
    ) -> FreshGateResult:
        return self._gate(
            workspace_ref=session.workspace_ref,
            profile_artifact_ref=session.profile_artifact_ref,
            evidence_artifact_refs=session.evidence_artifact_refs,
            job_key=session.job_key,
            expected_revision=session.expected_revision,
            material_version_ref=session.material_version_ref,
            workflow_checkpoint_ref=session.workflow_checkpoint_ref,
        )

    def _gate(
        self,
        *,
        workspace_ref: str,
        profile_artifact_ref: str,
        evidence_artifact_refs: tuple[str, ...],
        job_key: str,
        expected_revision: int,
        material_version_ref: str,
        workflow_checkpoint_ref: str | None,
    ) -> FreshGateResult:
        if self.resolve_context is None:
            raise AutofillGateError("Trusted artifact resolution is unavailable.")
        try:
            context = self.resolve_context(
                workspace_ref,
                profile_artifact_ref,
                evidence_artifact_refs,
                workflow_checkpoint_ref,
            )
            if context.workspace_ref != workspace_ref or not context.evidence_paths:
                raise ValueError
            if bool(workflow_checkpoint_ref) != bool(context.workflow_checkpoint_directory):
                raise ValueError
            data = load_dashboard_data(context.workspace_path)
            view = next((item for item in data.jobs if item.record.job_key == job_key), None)
            if (
                view is None
                or view.job is None
                or view.record.status != DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP
                or view.record.revision != expected_revision
                or view.record.artifacts.profile_artifact_ref != profile_artifact_ref
                or tuple(view.record.artifacts.evidence_artifact_refs) != evidence_artifact_refs
                or material_version_ref not in {item.version for item in view.record.materials}
            ):
                raise ValueError
            report = check_review_quality(
                context.workspace_path,
                job_key,
                expected_revision,
                evidence_path=context.evidence_paths[0],
                workflow_directory=context.workflow_checkpoint_directory,
                allow_approved_for_manual_next_step=True,
            )
            if report.status == QualityStatus.BLOCKED:
                raise ValueError
            completeness = assess_profile_completeness(context.profile)
            if any(item.blocks_autofill_when_requested for item in completeness.missing_fields):
                raise ValueError
            return FreshGateResult(context=context, quality=report)
        except AutofillGateError:
            raise
        except Exception as error:
            raise AutofillGateError(
                "Fresh local validation could not authorize this autofill transition."
            ) from error

    def _match_request(
        self,
        session: AutofillSession,
        request: AutofillTransitionRequest,
        *,
        require_selected: bool,
    ) -> None:
        if (
            session.workspace_ref != request.workspace_ref
            or session.profile_artifact_ref != request.profile_artifact_ref
            or session.evidence_artifact_refs != request.evidence_artifact_refs
            or session.expected_revision != request.expected_revision
            or session.material_version_ref != request.material_version_ref
            or session.workflow_checkpoint_ref != request.workflow_checkpoint_ref
        ):
            raise AutofillGateError("This autofill confirmation is stale or incompatible.")
        if require_selected:
            expected = tuple(
                field.identifier
                for field in session.fields
                if (
                    field.classification == FieldClassification.ELIGIBLE
                    and field.identifier not in session.skipped_identifiers
                )
            )
            if request.selected_identifiers != expected:
                raise AutofillGateError("The selected fields changed; reload before confirming.")

    @staticmethod
    def _with_quality(session: AutofillSession, report: QualityReport) -> AutofillSession:
        return session.model_copy(
            update={
                "last_quality_status": AutofillQualityStatus(report.status.value),
                "quality_warning_count": report.warning_count,
            }
        )

    def _session(self, session_id: str) -> AutofillSession:
        if session_id in self.sessions:
            return self.sessions[session_id]
        if self.session_repository is None:
            raise AutofillGateError("Autofill session is unavailable.")
        try:
            stored = self.session_repository.load(session_id)
        except Exception as error:
            raise AutofillGateError("Autofill session is unavailable.") from error
        self.sessions[session_id] = stored.session
        self.events = list(stored.events)
        return stored.session

    def _events_for_preparation(self, session: AutofillSession) -> list[AutofillAuditEvent]:
        events = self._with_event(session, AutofillAuditAction.SESSION_PREPARED, events=[])
        for item in session.fields:
            events = self._with_event(
                session, AutofillAuditAction.FIELD_PREPARED, item.identifier, events
            )
        return events

    def _session_events(self, session: AutofillSession) -> list[AutofillAuditEvent]:
        return [event for event in self.events if event.session_id == session.session_id]

    def _with_event(
        self,
        session: AutofillSession,
        action: AutofillAuditAction,
        field_identifier: str | None = None,
        events: list[AutofillAuditEvent] | None = None,
    ) -> list[AutofillAuditEvent]:
        return append_event(
            self.events if events is None else events,
            AutofillAuditEvent(
                session_id=session.session_id,
                job_key=session.job_key,
                action=action,
                field_identifier=field_identifier,
            ),
        )

    def _commit(self, session: AutofillSession, events: list[AutofillAuditEvent]) -> None:
        """Persist before exposing a transition, keeping storage failures fail-closed."""
        if self.session_repository is not None:
            try:
                self.session_repository.save(
                    StoredAutofillSession(session=session, events=tuple(events))
                )
            except Exception as error:
                raise AutofillGateError("Autofill session could not be safely recorded.") from error
        self.sessions[session.session_id] = session
        self.events = events
