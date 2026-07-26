"""Reference-only local persistence tests for controlled field-entry sessions."""

import pytest

from app.models.autofill import AutofillField, AutofillSession, FieldClassification
from app.services.autofill_audit_service import AutofillAuditAction, AutofillAuditEvent
from app.services.autofill_repository import (
    AutofillSessionRepository,
    AutofillStorageError,
    StoredAutofillSession,
)


def _stored(job_key: str = "manual:fictional:job-1") -> StoredAutofillSession:
    session = AutofillSession(
        session_id="fictional-session-1",
        job_key=job_key,
        workspace_ref="workspace:fictional",
        profile_artifact_ref="artifact:profile:fictional",
        evidence_artifact_refs=("artifact:evidence:fictional",),
        expected_revision=1,
        material_version_ref="material:v1",
        fields=[
            AutofillField(
                identifier="email",
                classification=FieldClassification.ELIGIBLE,
                source_reference="artifact:profile:fictional",
            )
        ],
    )
    return StoredAutofillSession(
        session=session,
        events=(
            AutofillAuditEvent(
                session_id=session.session_id,
                job_key=session.job_key,
                action=AutofillAuditAction.SESSION_PREPARED,
            ),
        ),
    )


def test_persistence_round_trip_and_read_only_lookup_contain_reference_metadata_only(
    tmp_path,
) -> None:
    repository = AutofillSessionRepository(tmp_path / "sessions")
    stored = _stored()
    repository.save(stored)

    loaded = repository.load(stored.session.session_id)
    found = repository.find_for_job(stored.session.job_key)
    payload = (tmp_path / "sessions" / "fictional-session-1.json").read_text(encoding="utf-8")

    assert loaded == stored
    assert found == stored
    assert "Fictional Candidate" not in payload
    assert "candidate@example.test" not in payload
    assert str(tmp_path) not in payload
    assert set(loaded.session.model_dump()) >= {
        "workspace_ref",
        "profile_artifact_ref",
        "evidence_artifact_refs",
        "material_version_ref",
    }


def test_malformed_or_ambiguous_session_lookup_fails_closed(tmp_path) -> None:
    repository = AutofillSessionRepository(tmp_path / "sessions")
    repository.save(_stored("manual:fictional:job-1"))
    repository.save(
        StoredAutofillSession(
            session=_stored("manual:fictional:job-1").session.model_copy(
                update={"session_id": "fictional-session-2"}
            ),
            events=(),
        )
    )
    (tmp_path / "sessions" / "malformed.json").write_text("not-json", encoding="utf-8")

    assert repository.find_for_job("manual:fictional:job-1") is None
    with pytest.raises(AutofillStorageError, match="unavailable or invalid"):
        repository.load("malformed")
