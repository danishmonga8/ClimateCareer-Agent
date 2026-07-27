"""Safety tests for Phase 2 application personalization."""

import pytest
from pydantic import ValidationError

from app.models.evidence import EvidenceRecord, EvidenceStatus
from app.models.personalization import (
    ApplicationClaim,
    ApplicationQuestionAnswer,
    ApplicationStatus,
    ClaimUsage,
    PersonalizedApplication,
    ReviewItem,
    TailoredCoverLetter,
    TailoredResume,
)


def make_verified_evidence() -> EvidenceRecord:
    """Create verified evidence permitted in application documents."""

    return EvidenceRecord(
        evidence_id="evidence-001",
        claim="Developed environmental predictive models using Python",
        source_document="candidate_cv.pdf",
        confidence_score=0.95,
        status=EvidenceStatus.VERIFIED,
        allowed_in_resume=True,
        allowed_in_cover_letter=True,
        requires_confirmation=False,
    )


def make_application(
    *,
    status: ApplicationStatus = ApplicationStatus.DRAFT,
    answers: list[ApplicationQuestionAnswer] | None = None,
    review_items: list[ReviewItem] | None = None,
    approval_note: str | None = None,
) -> PersonalizedApplication:
    """Create a valid example personalized application."""

    resume_claim = ApplicationClaim(
        text="Developed environmental predictive models using Python.",
        usage=ClaimUsage.RESUME,
        evidence=[make_verified_evidence()],
    )

    cover_letter_claim = ApplicationClaim(
        text="My research includes environmental predictive modelling.",
        usage=ClaimUsage.COVER_LETTER,
        evidence=[make_verified_evidence()],
    )

    return PersonalizedApplication(
        candidate_name="Sample Candidate",
        job_title="Environmental Data Scientist",
        employer="Example Climate Company",
        job_url="https://example.com/jobs/123",
        resume=TailoredResume(
            professional_headline="Environmental Data Scientist",
            claims=[resume_claim],
        ),
        cover_letter=TailoredCoverLetter(
            body="I am applying for the Environmental Data Scientist role.",
            claims=[cover_letter_claim],
        ),
        application_answers=answers or [],
        review_items=review_items or [],
        status=status,
        user_approval_note=approval_note,
    )


def test_new_application_starts_as_draft() -> None:
    """Every new personalized application must begin as a draft."""

    application = make_application()

    assert application.status == ApplicationStatus.DRAFT


def test_claim_without_evidence_is_rejected() -> None:
    """Unsupported claims must never enter application documents."""

    with pytest.raises(
        ValidationError,
        match="require at least one evidence record",
    ):
        ApplicationClaim(
            text="Led a global production AI team.",
            usage=ClaimUsage.RESUME,
            evidence=[],
        )


def test_unverified_evidence_is_rejected() -> None:
    """Evidence requiring confirmation cannot support a claim."""

    unverified_evidence = EvidenceRecord(
        evidence_id="evidence-002",
        claim="Ten years of production MLOps experience",
        source_document="candidate_cv.pdf",
        confidence_score=0.2,
        status=EvidenceStatus.REQUIRES_CONFIRMATION,
        allowed_in_resume=False,
        allowed_in_cover_letter=False,
        requires_confirmation=True,
    )

    with pytest.raises(
        ValidationError,
        match="only verified evidence",
    ):
        ApplicationClaim(
            text="Ten years of production MLOps experience.",
            usage=ClaimUsage.RESUME,
            evidence=[unverified_evidence],
        )


def test_resume_rejects_evidence_not_allowed_in_resume() -> None:
    """Verified evidence must also be permitted for resume use."""

    restricted_evidence = EvidenceRecord(
        evidence_id="evidence-003",
        claim="Example verified claim",
        source_document="candidate_cv.pdf",
        confidence_score=0.9,
        status=EvidenceStatus.VERIFIED,
        allowed_in_resume=False,
        allowed_in_cover_letter=True,
        requires_confirmation=False,
    )

    with pytest.raises(
        ValidationError,
        match="not permitted for use in the resume",
    ):
        ApplicationClaim(
            text="Example verified claim.",
            usage=ClaimUsage.RESUME,
            evidence=[restricted_evidence],
        )


def test_uncertain_answer_requires_review_reason() -> None:
    """Uncertain answers must explain why confirmation is needed."""

    with pytest.raises(
        ValidationError,
        match="must explain why",
    ):
        ApplicationQuestionAnswer(
            question="Are you legally authorized to work here?",
            answer=None,
            requires_confirmation=True,
        )


def test_unresolved_items_block_user_approval() -> None:
    """Approval must fail while review items remain unresolved."""

    unresolved_item = ReviewItem(
        field_path="sensitive_information.work_authorization",
        reason="The CV does not verify work authorization.",
    )

    with pytest.raises(
        ValidationError,
        match="cannot be approved while review items remain",
    ):
        make_application(
            status=ApplicationStatus.APPROVED_BY_USER,
            review_items=[unresolved_item],
            approval_note="I approve this application.",
        )


def test_confirmed_application_can_be_approved() -> None:
    """Approval is allowed after all review items are resolved."""

    resolved_item = ReviewItem(
        field_path="preferences.open_to_relocation",
        reason="Relocation preference required confirmation.",
        resolved=True,
        resolution="Candidate confirmed willingness to relocate.",
    )

    application = make_application(
        status=ApplicationStatus.APPROVED_BY_USER,
        review_items=[resolved_item],
        approval_note="I reviewed and approved all application content.",
    )

    assert application.status == ApplicationStatus.APPROVED_BY_USER


def test_phase_two_has_no_submission_state() -> None:
    """Phase 2 must not contain an application-submission state."""

    assert "submitted" not in {status.value for status in ApplicationStatus}
    assert not hasattr(PersonalizedApplication, "submit")
