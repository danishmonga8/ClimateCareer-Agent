"""Reference-only models for locally controlled field-entry sessions."""

from enum import StrEnum
from uuid import uuid4

from pydantic import Field, field_validator

from app.models.candidate import StrictModel


class AutofillSessionStatus(StrEnum):
    PREPARED = "prepared"
    AWAITING_START_CONFIRMATION = "awaiting_start_confirmation"
    AWAITING_POPULATION_CONFIRMATION = "awaiting_population_confirmation"
    POPULATED = "populated"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class AutofillWorkflowStage(StrEnum):
    """Internal checkpoints for controlled local field entry only."""

    AWAITING_SESSION_CONFIRMATION = "awaiting_session_confirmation"
    AWAITING_FIELD_CONFIRMATION = "awaiting_field_confirmation"
    PREPARED_FOR_MANUAL_FIELD_ENTRY = "prepared_for_manual_field_entry"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class AutofillQualityStatus(StrEnum):
    """Sanitized outcome of the most recent successful fresh Phase 7 check."""

    PASS = "pass"
    WARNING = "warning"


class FieldClassification(StrEnum):
    ELIGIBLE = "eligible"
    MANUAL = "manual"


class AutofillField(StrictModel):
    identifier: str = Field(min_length=1)
    classification: FieldClassification
    source_reference: str | None = None

    @field_validator("source_reference")
    @classmethod
    def validate_source_reference(cls, value: str | None) -> str | None:
        return _opaque_reference(value)


class AutofillSession(StrictModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    job_key: str = Field(min_length=1)
    workspace_ref: str = Field(min_length=1)
    profile_artifact_ref: str = Field(min_length=1)
    evidence_artifact_refs: tuple[str, ...] = ()
    expected_revision: int = Field(ge=0)
    material_version_ref: str = Field(min_length=1)
    workflow_checkpoint_ref: str | None = None
    fields: list[AutofillField] = Field(default_factory=list)
    skipped_identifiers: tuple[str, ...] = ()
    last_quality_status: AutofillQualityStatus | None = None
    quality_warning_count: int = Field(default=0, ge=0)
    status: AutofillSessionStatus = AutofillSessionStatus.PREPARED

    @field_validator(
        "workspace_ref",
        "profile_artifact_ref",
        "evidence_artifact_refs",
        "material_version_ref",
        "workflow_checkpoint_ref",
        mode="before",
    )
    @classmethod
    def validate_opaque_references(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            return tuple(_opaque_reference(item) for item in value)
        return _opaque_reference(value)


class AutofillTransitionRequest(StrictModel):
    """Opaque, deliberate transition request; contains no resolved artifact data."""

    session_id: str = Field(min_length=1)
    workspace_ref: str = Field(min_length=1)
    profile_artifact_ref: str = Field(min_length=1)
    evidence_artifact_refs: tuple[str, ...] = ()
    expected_revision: int = Field(ge=0)
    material_version_ref: str = Field(min_length=1)
    workflow_checkpoint_ref: str | None = None
    selected_identifiers: tuple[str, ...] = ()
    confirmed: bool = False

    @field_validator(
        "workspace_ref",
        "profile_artifact_ref",
        "evidence_artifact_refs",
        "material_version_ref",
        "workflow_checkpoint_ref",
        mode="before",
    )
    @classmethod
    def validate_opaque_references(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            return tuple(_opaque_reference(item) for item in value)
        return _opaque_reference(value)


class AutofillPreparationRequest(StrictModel):
    """Opaque request for one deliberate, locally controlled session."""

    workspace_ref: str = Field(min_length=1)
    profile_artifact_ref: str = Field(min_length=1)
    evidence_artifact_refs: tuple[str, ...] = ()
    job_key: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    material_version_ref: str = Field(min_length=1)
    workflow_checkpoint_ref: str | None = None
    selected_identifiers: tuple[str, ...] = ()
    session_id: str | None = None

    @field_validator(
        "workspace_ref",
        "profile_artifact_ref",
        "evidence_artifact_refs",
        "material_version_ref",
        "workflow_checkpoint_ref",
        mode="before",
    )
    @classmethod
    def validate_opaque_references(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            return tuple(_opaque_reference(item) for item in value)
        return _opaque_reference(value)


def _opaque_reference(value: object) -> str | None:
    """Reject values that could be paths or private artifact contents."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Artifact references must be opaque logical identifiers.")
    normalized = value.strip()
    if (
        not normalized
        or normalized in {".", ".."}
        or ".." in normalized
        or (len(normalized) > 1 and normalized[0].isalpha() and normalized[1] == ":")
        or any(character in normalized for character in ("/", "\\", "\x00"))
    ):
        raise ValueError("Artifact references must be opaque logical identifiers.")
    return normalized


class AutofillWorkflowSnapshot(StrictModel):
    """Reference-only durable state for a paused controlled-autofill workflow."""

    workflow_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    job_key: str = Field(min_length=1)
    workspace_ref: str = Field(min_length=1)
    profile_artifact_ref: str = Field(min_length=1)
    evidence_artifact_refs: tuple[str, ...] = ()
    expected_revision: int = Field(ge=0)
    material_version_ref: str = Field(min_length=1)
    workflow_checkpoint_ref: str | None = None
    selected_identifiers: tuple[str, ...] = ()
    field_classifications: dict[str, FieldClassification] = Field(default_factory=dict)
    status: AutofillWorkflowStage
    blocking_codes: tuple[str, ...] = ()

    @field_validator(
        "workspace_ref",
        "profile_artifact_ref",
        "evidence_artifact_refs",
        "material_version_ref",
        "workflow_checkpoint_ref",
        mode="before",
    )
    @classmethod
    def validate_opaque_references(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            return tuple(_opaque_reference(item) for item in value)
        return _opaque_reference(value)


class AutofillDashboardSessionView(StrictModel):
    """Sanitized, read-only dashboard projection of one local session."""

    session_id: str = Field(min_length=1)
    status: AutofillSessionStatus
    job_key: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    current_revision: int = Field(ge=0)
    revision_compatible: bool
    material_version_compatible: bool
    artifact_references_compatible: bool
    quality_status: AutofillQualityStatus | None = None
    quality_warning_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    manual_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    prepared_count: int = Field(ge=0)
    populated_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    fields: list[AutofillField] = Field(default_factory=list)
    selected_identifiers: tuple[str, ...] = ()
    workflow_stage: AutofillWorkflowStage | None = None
    blocking_codes: tuple[str, ...] = ()
    recovery_guidance: tuple[str, ...] = ()
