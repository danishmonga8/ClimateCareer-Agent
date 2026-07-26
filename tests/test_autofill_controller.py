"""Fictional offline tests for fresh-gated opaque controller transitions."""

from types import SimpleNamespace

import pytest

from app.models.autofill import AutofillPreparationRequest, AutofillTransitionRequest
from app.models.candidate import CandidateProfile, ContactInformation
from app.models.dashboard_review import DashboardReviewStatus
from app.services import autofill_controller
from app.services.autofill_controller import (
    AutofillGateError,
    LocalAutofillController,
    TransientResolverContext,
)
from app.services.autofill_repository import AutofillSessionRepository
from app.services.quality_control_service import QualityStatus


def _profile() -> CandidateProfile:
    return CandidateProfile(
        full_name="Fictional Candidate",
        contact=ContactInformation(
            emails=["candidate@example.test"], phone="555-0100", location="Fictional City"
        ),
        source_document="fictional-source.pdf",
    )


def _request() -> AutofillPreparationRequest:
    return AutofillPreparationRequest(
        workspace_ref="workspace:fictional",
        profile_artifact_ref="artifact:profile:fictional",
        evidence_artifact_refs=("artifact:evidence:fictional",),
        job_key="manual:fictional:job-1",
        expected_revision=1,
        material_version_ref="material:v1",
        selected_identifiers=("full_name", "email", "salary"),
    )


def _transition(
    session_id: str, *, confirmed: bool = True, selected: tuple[str, ...] = ("full_name", "email")
) -> AutofillTransitionRequest:
    return AutofillTransitionRequest(
        session_id=session_id,
        workspace_ref="workspace:fictional",
        profile_artifact_ref="artifact:profile:fictional",
        evidence_artifact_refs=("artifact:evidence:fictional",),
        expected_revision=1,
        material_version_ref="material:v1",
        selected_identifiers=selected,
        confirmed=confirmed,
    )


def _controller(monkeypatch, tmp_path, *, quality: QualityStatus = QualityStatus.PASS):
    calls: list[str] = []
    profile = _profile()
    context = TransientResolverContext(
        workspace_ref="workspace:fictional",
        workspace_path=tmp_path / "private-workspace.json",
        profile=profile,
        evidence_paths=(tmp_path / "private-evidence.json",),
    )
    view = SimpleNamespace(
        job=object(),
        record=SimpleNamespace(
            job_key="manual:fictional:job-1",
            status=DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP,
            revision=1,
            artifacts=SimpleNamespace(
                profile_artifact_ref="artifact:profile:fictional",
                evidence_artifact_refs=["artifact:evidence:fictional"],
            ),
            materials=[SimpleNamespace(version="material:v1")],
        ),
    )

    def resolve(*_):
        calls.append("resolve")
        return context

    monkeypatch.setattr(
        autofill_controller, "load_dashboard_data", lambda _: SimpleNamespace(jobs=[view])
    )
    monkeypatch.setattr(
        autofill_controller,
        "check_review_quality",
        lambda *_args, **_kwargs: SimpleNamespace(
            status=quality,
            warning_count=1 if quality == QualityStatus.WARNING else 0,
        ),
    )
    monkeypatch.setattr(
        autofill_controller,
        "assess_profile_completeness",
        lambda _: SimpleNamespace(missing_fields=[]),
    )
    return LocalAutofillController(
        resolve_context=resolve,
        session_repository=AutofillSessionRepository(tmp_path / "sessions"),
    ), calls


def test_controller_uses_opaque_requests_and_persists_no_paths_or_values(
    monkeypatch, tmp_path
) -> None:
    controller, calls = _controller(monkeypatch, tmp_path)
    session = controller.prepare(_request())
    started = controller.start(_transition(session.session_id))
    populated = controller.populate(_transition(session.session_id))

    assert populated.status.value == "populated"
    assert calls == ["resolve", "resolve", "resolve"]
    reloaded = AutofillSessionRepository(tmp_path / "sessions").load(session.session_id)
    persisted = (tmp_path / "sessions" / f"{session.session_id}.json").read_text(encoding="utf-8")
    assert reloaded.session.status == populated.status
    assert str(tmp_path) not in persisted
    assert "Fictional Candidate" not in persisted
    assert "candidate@example.test" not in persisted
    assert all("private-" not in event.model_dump_json() for event in reloaded.events)
    assert started.status.value == "awaiting_population_confirmation"


def test_quality_block_or_mismatched_confirmation_fails_before_mutation(
    monkeypatch, tmp_path
) -> None:
    controller, _ = _controller(monkeypatch, tmp_path, quality=QualityStatus.BLOCKED)
    with pytest.raises(AutofillGateError, match="Fresh local validation"):
        controller.prepare(_request())
    assert controller.sessions == {}
    assert controller.events == []

    controller, _ = _controller(monkeypatch, tmp_path)
    session = controller.prepare(_request())
    stale = _transition(session.session_id, selected=("email",))
    with pytest.raises(AutofillGateError, match="selected fields changed"):
        controller.start(stale)
    assert controller._session(session.session_id).status.value == "awaiting_start_confirmation"


def test_warning_quality_result_still_requires_and_allows_fresh_safeguards(
    monkeypatch, tmp_path
) -> None:
    controller, calls = _controller(monkeypatch, tmp_path, quality=QualityStatus.WARNING)
    session = controller.prepare(_request())
    controller.start(_transition(session.session_id))

    assert calls == ["resolve", "resolve"]
    assert (
        controller._session(session.session_id).status.value == "awaiting_population_confirmation"
    )


def test_fresh_gate_detects_tampering_between_confirmations_without_new_audit(
    monkeypatch, tmp_path
) -> None:
    controller, _ = _controller(monkeypatch, tmp_path)
    session = controller.prepare(_request())
    controller.start(_transition(session.session_id))
    event_count = len(controller.events)
    monkeypatch.setattr(
        autofill_controller,
        "check_review_quality",
        lambda *_args, **_kwargs: SimpleNamespace(
            status=QualityStatus.BLOCKED,
            warning_count=0,
        ),
    )

    with pytest.raises(AutofillGateError, match="Fresh local validation"):
        controller.populate(_transition(session.session_id))

    assert (
        controller._session(session.session_id).status.value == "awaiting_population_confirmation"
    )
    assert len(controller.events) == event_count


def test_restart_cancellation_and_replays_are_safe_and_idempotent(monkeypatch, tmp_path) -> None:
    controller, _ = _controller(monkeypatch, tmp_path)
    session = controller.prepare(_request())
    restarted, calls = _controller(monkeypatch, tmp_path)
    restored = restarted._session(session.session_id)
    assert restored.status.value == "awaiting_start_confirmation"
    assert calls == []
    started = restarted.start(_transition(session.session_id))
    assert restarted.start(_transition(session.session_id)).status == started.status
    populated = restarted.populate(_transition(session.session_id))
    assert restarted.populate(_transition(session.session_id)).status == populated.status
    assert [event.action.value for event in restarted.events].count("session_confirmed") == 1
    assert [event.action.value for event in restarted.events].count("field_populated") == 2

    second, _ = _controller(monkeypatch, tmp_path)
    cancellation = second.prepare(_request())
    cancelled = second.start(_transition(cancellation.session_id, confirmed=False))
    assert cancelled.status.value == "cancelled"
    assert (
        second.cancel(_transition(cancellation.session_id, confirmed=False)).status
        == cancelled.status
    )


def test_skip_is_audited_without_values_and_excluded_from_population(monkeypatch, tmp_path) -> None:
    controller, _ = _controller(monkeypatch, tmp_path)
    session = controller.prepare(_request())
    controller.start(_transition(session.session_id))
    skipped = controller.skip(_transition(session.session_id, selected=("email",)))
    populated = controller.populate(_transition(session.session_id, selected=("full_name",)))

    assert skipped.skipped_identifiers == ("email",)
    assert [
        event.field_identifier
        for event in controller.events
        if event.action.value == "field_populated"
    ] == ["full_name"]
    assert populated.status.value == "populated"


def test_storage_failure_never_exposes_an_advanced_session(monkeypatch, tmp_path) -> None:
    controller, _ = _controller(monkeypatch, tmp_path)

    class FailingRepository:
        def save(self, _stored) -> None:
            raise OSError("fictional private path")

    controller.session_repository = FailingRepository()  # type: ignore[assignment]
    with pytest.raises(AutofillGateError, match="could not be safely recorded") as captured:
        controller.prepare(_request())
    assert controller.sessions == {}
    assert controller.events == []
    assert "private path" not in str(captured.value)


def test_opaque_models_reject_paths_and_controller_has_no_path_transition_parameters() -> None:
    for unsafe_reference in ("../private", "C:private"):
        with pytest.raises(ValueError, match="opaque"):
            AutofillPreparationRequest(
                workspace_ref=unsafe_reference,
                profile_artifact_ref="artifact:profile",
                job_key="job",
                expected_revision=0,
                material_version_ref="v1",
            )
    assert "Path" not in str(LocalAutofillController.prepare.__annotations__)
    for transition in (
        LocalAutofillController.start,
        LocalAutofillController.populate,
        LocalAutofillController.skip,
        LocalAutofillController.cancel,
    ):
        assert set(transition.__annotations__) == {"request", "return"}
