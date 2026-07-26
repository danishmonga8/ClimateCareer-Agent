"""Tests for deterministic, sanitized internal quality reports."""

from types import SimpleNamespace

from app.models.dashboard_review import DashboardReviewStatus
from app.services import quality_control_service
from app.services.quality_control_service import QualityStatus, check_review_quality


def _view(*, revision: int = 2, score: object | None = object(), unresolved: bool = False):
    application = SimpleNamespace(
        review_items=[SimpleNamespace(resolved=not unresolved)],
        application_answers=[],
    )
    return SimpleNamespace(
        record=SimpleNamespace(
            job_key="manual:fictional:job-1",
            revision=revision,
            status=DashboardReviewStatus.AWAITING_REVIEW,
        ),
        job=object(),
        score=score,
        application=application,
    )


def test_pass_report_is_deterministic_and_contains_no_artifact_content(monkeypatch) -> None:
    monkeypatch.setattr(
        quality_control_service,
        "load_dashboard_data",
        lambda _: SimpleNamespace(jobs=[_view()]),
    )
    monkeypatch.setattr(quality_control_service, "load_evidence_bank", lambda _: object())
    monkeypatch.setattr(quality_control_service, "verify_application_claims", lambda *_: object())

    report = check_review_quality(
        "fictional-workspace.json", "manual:fictional:job-1", 2, evidence_path="evidence.json"
    )

    assert report.status == QualityStatus.PASS
    assert report.findings == []


def test_warning_and_blocking_findings_are_sanitized(monkeypatch) -> None:
    monkeypatch.setattr(
        quality_control_service,
        "load_dashboard_data",
        lambda _: SimpleNamespace(jobs=[_view(score=None, unresolved=True)]),
    )
    monkeypatch.setattr(quality_control_service, "load_evidence_bank", lambda _: object())
    monkeypatch.setattr(quality_control_service, "verify_application_claims", lambda *_: object())

    report = check_review_quality(
        "fictional-workspace.json", "manual:fictional:job-1", 1, evidence_path="evidence.json"
    )

    assert report.status == QualityStatus.BLOCKED
    assert [finding.code for finding in report.findings] == [
        "REVIEW_ITEMS_UNRESOLVED",
        "REVISION_STALE",
        "OPTIONAL_SCORE_UNAVAILABLE",
    ]
    assert all("fictional-workspace" not in finding.message for finding in report.findings)
