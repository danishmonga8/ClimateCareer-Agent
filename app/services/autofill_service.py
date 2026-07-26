"""Mockable local field-entry preparation; never controls a browser or submission."""

from app.models.autofill import (
    AutofillField,
    AutofillSession,
    AutofillSessionStatus,
    FieldClassification,
)
from app.models.candidate import CandidateProfile
from app.services.autofill_audit_service import (
    AutofillAuditAction,
    AutofillAuditEvent,
    append_event,
)

ALLOWLIST = {
    "full_name",
    "email",
    "phone",
    "city",
    "region",
    "postal_code",
    "country",
    "linkedin_url",
    "github_url",
    "portfolio_url",
    "employer",
    "job_title",
    "institution",
    "degree",
    "field_of_study",
    "employment_dates",
    "education_dates",
    "skills",
}


class AutofillError(ValueError):
    """Raised for safe, local session-control failures."""


def prepare_session(
    profile: CandidateProfile,
    workspace_ref: str,
    profile_artifact_ref: str,
    evidence_artifact_refs: tuple[str, ...],
    job_key: str,
    expected_revision: int,
    material_version_ref: str,
    workflow_checkpoint_ref: str | None,
    selected_identifiers: tuple[str, ...],
    session_id: str | None = None,
) -> AutofillSession:
    """Classify selected identifiers without retaining resolved field values."""
    fields: list[AutofillField] = []
    for identifier in selected_identifiers:
        eligible = identifier in ALLOWLIST and _has_value(profile, identifier)
        fields.append(
            AutofillField(
                identifier=identifier,
                classification=FieldClassification.ELIGIBLE
                if eligible
                else FieldClassification.MANUAL,
                source_reference=profile_artifact_ref if eligible else None,
            )
        )
    return AutofillSession(
        **({"session_id": session_id} if session_id is not None else {}),
        job_key=job_key,
        workspace_ref=workspace_ref,
        profile_artifact_ref=profile_artifact_ref,
        evidence_artifact_refs=evidence_artifact_refs,
        expected_revision=expected_revision,
        material_version_ref=material_version_ref,
        workflow_checkpoint_ref=workflow_checkpoint_ref,
        fields=fields,
        status=AutofillSessionStatus.AWAITING_START_CONFIRMATION,
    )


def confirm_start(session: AutofillSession, confirmed: bool) -> AutofillSession:
    if not confirmed:
        return session.model_copy(update={"status": AutofillSessionStatus.CANCELLED})
    if session.status != AutofillSessionStatus.AWAITING_START_CONFIRMATION:
        raise AutofillError("This autofill session cannot be started.")
    return session.model_copy(
        update={"status": AutofillSessionStatus.AWAITING_POPULATION_CONFIRMATION}
    )


def confirm_population(session: AutofillSession, confirmed: bool) -> AutofillSession:
    if not confirmed:
        return session.model_copy(update={"status": AutofillSessionStatus.CANCELLED})
    if session.status != AutofillSessionStatus.AWAITING_POPULATION_CONFIRMATION:
        raise AutofillError("This autofill session cannot populate fields.")
    return session.model_copy(update={"status": AutofillSessionStatus.POPULATED})


def session_audit(session: AutofillSession) -> list[AutofillAuditEvent]:
    """Return sanitized prepared/populated identifiers without field values."""
    action = (
        AutofillAuditAction.FIELD_POPULATED
        if session.status == AutofillSessionStatus.POPULATED
        else AutofillAuditAction.FIELD_PREPARED
    )
    events = [
        AutofillAuditEvent(
            session_id=session.session_id,
            job_key=session.job_key,
            action=AutofillAuditAction.SESSION_PREPARED,
        )
    ]
    for field in session.fields:
        events = append_event(
            events,
            AutofillAuditEvent(
                session_id=session.session_id,
                job_key=session.job_key,
                action=action,
                field_identifier=field.identifier,
            ),
        )
    return events


def _has_value(profile: CandidateProfile, identifier: str) -> bool:
    if identifier == "full_name":
        return bool(profile.full_name)
    if identifier == "email":
        return bool(profile.contact.emails)
    if identifier == "phone":
        return bool(profile.contact.phone)
    if identifier in {
        "city",
        "region",
        "postal_code",
        "country",
        "employer",
        "job_title",
        "employment_dates",
        "institution",
        "degree",
        "field_of_study",
        "education_dates",
        "skills",
    }:
        # Existing profile models do not represent these target values with a
        # deterministic field-level mapping, so they remain manual.
        return False
    target = identifier.removesuffix("_url").replace("_", " ")
    return any(target in link.label.casefold().replace("_", " ") for link in profile.links)
