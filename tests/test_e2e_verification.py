"""Offline, fictional end-to-end verification of the Phase 1-4 workflow."""

from datetime import UTC, datetime
from unittest.mock import Mock

import httpx
import pytest

from app.agents.personalization_agent import (
    ApplicationAnswerSelection,
    PersonalizationSelectionResult,
    personalize_application,
)
from app.core.settings import Settings
from app.dashboard.data_loader import load_dashboard_data
from app.discovery.greenhouse import collect_greenhouse_jobs
from app.discovery.pipeline import evaluate_discovered_job
from app.discovery.service import build_discovery_snapshot
from app.models.candidate import CandidateProfile, ContactInformation
from app.models.dashboard_review import (
    ArtifactReferences,
    DashboardReviewAction,
    DashboardReviewRecord,
    DashboardReviewStatus,
    DashboardWorkspace,
    MaterialMetadata,
    MaterialType,
)
from app.models.discovery import DiscoveredJob, DiscoverySnapshot, JobSource
from app.models.evidence import EvidenceBank, EvidenceRecord, EvidenceStatus
from app.models.job import JobDescription
from app.models.scoring import JobRelevanceScore, ScoreComponent, WeightScheme
from app.services.application_review_service import (
    begin_application_review,
    resolve_application_answer,
)
from app.services.dashboard_repository import (
    DashboardStorageError,
    load_dashboard_workspace,
    save_dashboard_workspace,
    save_updated_dashboard_workspace,
)
from app.services.dashboard_review_service import (
    DashboardReviewError,
    apply_dashboard_decision,
    resubmit_for_review,
)
from app.services.discovery_repository import save_discovery_snapshot
from app.services.evidence_repository import load_evidence_bank, save_evidence_bank
from app.services.personalization_repository import save_personalized_application
from app.services.profile_service import load_candidate_profile, save_candidate_profile
from app.services.scoring_repository import save_scoring_result


def _profile() -> CandidateProfile:
    return CandidateProfile(
        full_name="Avery Rowan",
        contact=ContactInformation(emails=["avery@example.test"], location="Fictional City"),
        source_document="fictional_cv.pdf",
    )


def _evidence() -> EvidenceBank:
    record = EvidenceRecord(
        evidence_id="fictional-evidence-001",
        claim="Built Python models for environmental monitoring datasets.",
        source_document="fictional_cv.pdf",
        source_section="Projects",
        source_excerpt="Fictional climate monitoring project.",
        confidence_score=0.99,
        status=EvidenceStatus.VERIFIED,
        allowed_in_resume=True,
        allowed_in_cover_letter=True,
        requires_confirmation=False,
    )
    return EvidenceBank(
        candidate_name="Avery Rowan",
        source_document="fictional_cv.pdf",
        source_sha256="f" * 64,
        records=[record],
    )


def _job(job_id: str = "fictional-001") -> DiscoveredJob:
    return DiscoveredJob(
        source=JobSource.GREENHOUSE,
        source_board="fictional-climate",
        source_job_id=job_id,
        company="Northstar Climate Labs",
        title="Environmental Data Analyst",
        job_url=f"https://example.test/jobs/{job_id}",
        location="Remote",
        description="Analyse fictional environmental observations using Python.",
        discovered_at=datetime(2026, 7, 25, tzinfo=UTC),
    )


def _score(job: DiscoveredJob) -> JobRelevanceScore:
    weights = WeightScheme()
    return JobRelevanceScore(
        company=job.company,
        job_title=job.title,
        weight_scheme=weights,
        components=[
            ScoreComponent(
                category=category,
                awarded_points=maximum / 2,
                maximum_points=maximum,
                rationale="Offline fictional verification score.",
                matched_evidence=["Fictional verified evidence"],
                missing_items=["Confirm role-specific tooling"],
            )
            for category, maximum in weights.as_mapping().items()
        ],
        uncertainty_notes=["This is an offline verification fixture."],
        confidence_score=0.8,
    )


def _parser(**kwargs: object) -> JobDescription:
    return JobDescription(
        company="Untrusted parser company",
        title="Untrusted parser title",
        job_url=str(kwargs["job_url"]),
        source=str(kwargs["source"]),
        discovery_date=kwargs["discovery_date"],
        raw_description=str(kwargs["job_text"]),
        extraction_confidence=0.9,
    )


def _make_application(
    monkeypatch: pytest.MonkeyPatch,
    profile: CandidateProfile,
    evidence: EvidenceBank,
    job: JobDescription,
):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-placeholder")
    selection = PersonalizationSelectionResult(
        resume_evidence_ids=["fictional-evidence-001"],
        cover_letter_evidence_ids=["fictional-evidence-001"],
        application_answers=[
            ApplicationAnswerSelection(
                question_index=0,
                requires_confirmation=True,
                confirmation_reason="A fictional reviewer must confirm this answer.",
            )
        ],
    )
    client = Mock()
    client.responses.parse.return_value.output_parsed = selection
    return personalize_application(
        profile,
        evidence,
        job,
        application_questions=["What compensation range do you expect?"],
        client=client,
        settings=Settings(_env_file=None),
    )


def _write_artifacts(tmp_path, monkeypatch: pytest.MonkeyPatch):
    profile_path = save_candidate_profile(_profile(), tmp_path / "profile.json")
    evidence_path = save_evidence_bank(_evidence(), tmp_path / "evidence.json")
    profile = load_candidate_profile(profile_path)
    evidence = load_evidence_bank(evidence_path)
    discovered_job = _job()
    save_discovery_snapshot(DiscoverySnapshot(jobs=[discovered_job]), tmp_path / "jobs.json")

    evaluation = evaluate_discovered_job(
        discovered_job,
        profile,
        evidence,
        parser=_parser,
        scorer=lambda *_args, **_kwargs: _score(discovered_job),
    )
    assert evaluation.parsed_job.company == discovered_job.company
    score_path = save_scoring_result(evaluation.relevance_score, tmp_path / "score.json")

    application = _make_application(monkeypatch, profile, evidence, evaluation.parsed_job)
    in_review = begin_application_review(application)
    resolved = resolve_application_answer(
        in_review,
        0,
        "The fictional candidate will confirm compensation separately.",
        "Confirmed during offline verification.",
    )
    application_path = save_personalized_application(resolved, tmp_path / "application.json")
    return discovered_job, score_path, application_path


def _workspace(job: DiscoveredJob) -> DashboardWorkspace:
    return DashboardWorkspace(
        records=[
            DashboardReviewRecord(
                source=job.source,
                source_board=job.source_board,
                source_job_id=job.source_job_id,
                artifacts=ArtifactReferences(
                    discovery_snapshot="jobs.json",
                    scoring_result="score.json",
                    personalized_application="application.json",
                ),
                materials=[
                    MaterialMetadata(
                        material_type=MaterialType.TAILORED_RESUME,
                        version="fictional-v1",
                    )
                ],
            )
        ]
    )


def test_successful_offline_review_flow_persists_internal_approval(tmp_path, monkeypatch) -> None:
    job, _score_path, _application_path = _write_artifacts(tmp_path, monkeypatch)
    workspace_path = tmp_path / "dashboard.json"
    initial = _workspace(job)
    save_dashboard_workspace(initial, workspace_path)
    loaded = load_dashboard_data(workspace_path)

    assert loaded.jobs[0].job is not None
    assert loaded.jobs[0].score is not None
    assert loaded.jobs[0].application is not None
    approved = apply_dashboard_decision(
        loaded.workspace,
        loaded.jobs[0].record.job_key,
        DashboardReviewAction.APPROVED,
        expected_revision=0,
        reviewer_label="Offline reviewer",
        reason_or_note="Approved for a fictional manual next step.",
        material_version="fictional-v1",
        linked_application=loaded.jobs[0].application,
    )
    save_updated_dashboard_workspace(loaded.workspace, approved, workspace_path)
    reloaded = load_dashboard_workspace(workspace_path)

    assert reloaded.records[0].status == DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP
    assert reloaded.records[0].revision == 1
    assert len(reloaded.audit_events) == 1
    assert reloaded.audit_events[0].action == DashboardReviewAction.APPROVED


def test_revision_rejection_and_failure_recovery_are_safe(tmp_path, monkeypatch) -> None:
    job, _score_path, _application_path = _write_artifacts(tmp_path, monkeypatch)
    workspace_path = tmp_path / "dashboard.json"
    initial = _workspace(job)
    save_dashboard_workspace(initial, workspace_path)
    requested = apply_dashboard_decision(
        initial,
        initial.records[0].job_key,
        DashboardReviewAction.REVISION_REQUESTED,
        0,
        "Offline reviewer",
        "Clarify the fictional cover letter.",
        material_version="fictional-v1",
    )
    save_updated_dashboard_workspace(initial, requested, workspace_path)
    returned = resubmit_for_review(
        load_dashboard_workspace(workspace_path),
        initial.records[0].job_key,
        1,
        "Offline reviewer",
        "Revision checked without regeneration.",
    )
    save_updated_dashboard_workspace(requested, returned, workspace_path)
    approved = apply_dashboard_decision(
        returned,
        initial.records[0].job_key,
        DashboardReviewAction.APPROVED,
        2,
        "Offline reviewer",
    )
    save_updated_dashboard_workspace(returned, approved, workspace_path)

    assert approved.records[0].revision == 3
    assert approved.records[0].materials[0].version == "fictional-v1"
    with pytest.raises(DashboardReviewError, match="terminal"):
        apply_dashboard_decision(
            approved,
            initial.records[0].job_key,
            DashboardReviewAction.REJECTED,
            3,
            "Offline reviewer",
            "Too late.",
        )
    with pytest.raises(DashboardReviewError, match="changed"):
        apply_dashboard_decision(
            returned,
            initial.records[0].job_key,
            DashboardReviewAction.APPROVED,
            1,
            "Offline reviewer",
        )
    rejected_workspace = _workspace(_job("fictional-rejected"))
    rejected = apply_dashboard_decision(
        rejected_workspace,
        rejected_workspace.records[0].job_key,
        DashboardReviewAction.REJECTED,
        0,
        "Offline reviewer",
        "The fictional role is not a current priority.",
    )
    assert rejected.records[0].status == DashboardReviewStatus.REJECTED
    with pytest.raises(DashboardReviewError, match="terminal"):
        apply_dashboard_decision(
            rejected,
            rejected.records[0].job_key,
            DashboardReviewAction.REVISION_REQUESTED,
            1,
            "Offline reviewer",
            "This cannot reopen a final decision.",
        )
    malformed_workspace = tmp_path / "malformed.json"
    malformed_workspace.write_text("not JSON", encoding="utf-8")
    with pytest.raises(DashboardStorageError, match="valid dashboard workspace"):
        load_dashboard_workspace(malformed_workspace)


def test_duplicate_and_missing_optional_artifacts_produce_sanitized_warnings(tmp_path) -> None:
    job = _job()
    save_discovery_snapshot(
        DiscoverySnapshot(jobs=[job, job]),
        tmp_path / "jobs.json",
    )
    workspace_path = tmp_path / "dashboard.json"
    workspace = _workspace(job)
    workspace.records[0].artifacts = ArtifactReferences(
        discovery_snapshot="jobs.json",
        scoring_result="malformed-score.json",
        personalized_application="missing-application.json",
    )
    (tmp_path / "malformed-score.json").write_text("not JSON", encoding="utf-8")
    save_dashboard_workspace(workspace, workspace_path)

    loaded = load_dashboard_data(workspace_path)

    assert loaded.jobs[0].job is None
    assert loaded.jobs[0].score is None
    assert loaded.jobs[0].application is None
    assert all(str(tmp_path) not in warning for warning in loaded.warnings)
    assert len(loaded.warnings) == 3


def test_mocked_ats_collection_preserves_stable_identity_and_deduplicates() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": "fictional-ats-42",
                        "title": "Environmental Data Analyst",
                        "absolute_url": "https://example.test/jobs/fictional-ats-42",
                        "content": "Analyse fictional environmental observations using Python.",
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        collected = collect_greenhouse_jobs(
            "fictional-climate", "Northstar Climate Labs", client=client
        )

    snapshot = build_discovery_snapshot([collected, collected])

    assert (
        snapshot.jobs[0].source.value,
        snapshot.jobs[0].source_board,
        snapshot.jobs[0].source_job_id,
    ) == ("greenhouse", "fictional-climate", "fictional-ats-42")
    assert len(snapshot.jobs) == 1
    assert [request.method for request in requests] == ["GET"]


def test_storage_failure_is_sanitized_and_leaves_no_temporary_workspace(tmp_path) -> None:
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("fictional test blocker", encoding="utf-8")
    output_path = blocked_parent / "dashboard.json"

    with pytest.raises(DashboardStorageError, match="Unable to save dashboard workspace") as error:
        save_dashboard_workspace(DashboardWorkspace(), output_path)

    assert str(blocked_parent) not in str(error.value)
    assert not (tmp_path / "dashboard.json.temporary").exists()
