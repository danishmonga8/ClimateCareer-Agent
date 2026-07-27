"""Tests for human-controlled application review transitions."""

import pytest

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
from app.services.application_review_service import (
    ApplicationReviewError,
    approve_application,
    begin_application_review,
    resolve_application_answer,
    resolve_review_item,
)


def make_evidence() -> EvidenceRecord:
    """Create verified evidence for a sample application."""
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
    uncertain_answer: bool = False,
    review_items: list[ReviewItem] | None = None,
    status: ApplicationStatus = ApplicationStatus.DRAFT,
    approval_note: str | None = None,
) -> PersonalizedApplication:
    """Create a valid application in a requested review state."""
    evidence = make_evidence()

    resume_claim = ApplicationClaim(
        text=evidence.claim,
        usage=ClaimUsage.RESUME,
        evidence=[evidence],
    )
    cover_letter_claim = ApplicationClaim(
        text=evidence.claim,
        usage=ClaimUsage.COVER_LETTER,
        evidence=[evidence],
    )

    answers: list[ApplicationQuestionAnswer] = []
    items = list(review_items or [])

    if uncertain_answer:
        answers.append(
            ApplicationQuestionAnswer(
                question="What is your expected salary?",
                requires_confirmation=True,
                confirmation_reason="The candidate must confirm salary.",
            )
        )
        items.append(
            ReviewItem(
                field_path="application_answers[0].answer",
                reason="The candidate must confirm salary.",
            )
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
            body="I am applying for this position.",
            claims=[cover_letter_claim],
        ),
        application_answers=answers,
        review_items=items,
        status=status,
        user_approval_note=approval_note,
    )


def test_begin_review_changes_application_status() -> None:
    """A draft can enter explicit human review."""
    draft = make_application()

    reviewed = begin_application_review(draft)

    assert draft.status == ApplicationStatus.DRAFT
    assert reviewed.status == ApplicationStatus.NEEDS_REVIEW
    assert reviewed.candidate_name == draft.candidate_name


def test_approved_application_cannot_reenter_review() -> None:
    """Approved content cannot be silently reopened or changed."""
    reviewed = begin_application_review(make_application())
    approved = approve_application(
        reviewed,
        "I reviewed and approved this application.",
    )

    with pytest.raises(
        ApplicationReviewError,
        match="approved application cannot be modified",
    ):
        begin_application_review(approved)


def test_human_answer_resolves_confirmation_item() -> None:
    """A human answer should update both answer and review item."""
    application = begin_application_review(make_application(uncertain_answer=True))

    updated = resolve_application_answer(
        application,
        question_index=0,
        answer="My expected annual salary is ₹12,00,000.",
        resolution="Candidate directly confirmed the expected salary.",
    )

    answer = updated.application_answers[0]
    review_item = updated.review_items[0]

    assert answer.answer == "My expected annual salary is ₹12,00,000."
    assert answer.requires_confirmation is False
    assert answer.confirmation_reason is None
    assert review_item.resolved is True
    assert review_item.resolution == ("Candidate directly confirmed the expected salary.")


def test_answer_requires_matching_review_item() -> None:
    """An answer cannot be confirmed without its review record."""
    answer = ApplicationQuestionAnswer(
        question="When can you start?",
        requires_confirmation=True,
        confirmation_reason="The candidate must confirm availability.",
    )
    application = make_application().model_copy(update={"application_answers": [answer]})

    with pytest.raises(
        ApplicationReviewError,
        match="exactly one unresolved review item",
    ):
        resolve_application_answer(
            application,
            question_index=0,
            answer="I can start in four weeks.",
            resolution="Candidate confirmed availability.",
        )


def test_non_answer_review_item_can_be_resolved() -> None:
    """General quality-review items can record a human resolution."""
    item = ReviewItem(
        field_path="resume.professional_summary",
        reason="The summary requires a final wording review.",
    )
    application = begin_application_review(make_application(review_items=[item]))

    updated = resolve_review_item(
        application,
        field_path="resume.professional_summary",
        resolution="Candidate reviewed and accepted the wording.",
    )

    assert updated.review_items[0].resolved is True
    assert updated.review_items[0].resolution == ("Candidate reviewed and accepted the wording.")


def test_answer_item_requires_answer_resolution_function() -> None:
    """An answer item cannot be resolved without supplying its answer."""
    application = begin_application_review(make_application(uncertain_answer=True))

    with pytest.raises(
        ApplicationReviewError,
        match="resolve_application_answer",
    ):
        resolve_review_item(
            application,
            field_path="application_answers[0].answer",
            resolution="Confirmed.",
        )


def test_draft_cannot_be_approved_directly() -> None:
    """Approval requires an explicit human-review stage."""
    with pytest.raises(
        ApplicationReviewError,
        match="needs_review status",
    ):
        approve_application(
            make_application(),
            "I approve this application.",
        )


def test_unresolved_items_block_service_approval() -> None:
    """The service must reject approval while review remains incomplete."""
    application = begin_application_review(make_application(uncertain_answer=True))

    with pytest.raises(
        ApplicationReviewError,
        match="unresolved review items",
    ):
        approve_application(
            application,
            "I approve this application.",
        )


def test_reviewed_application_can_be_approved() -> None:
    """Completed human review can produce an approved application."""
    application = begin_application_review(make_application(uncertain_answer=True))
    resolved = resolve_application_answer(
        application,
        question_index=0,
        answer="My expected annual salary is ₹12,00,000.",
        resolution="Candidate directly confirmed the answer.",
    )

    approved = approve_application(
        resolved,
        "I reviewed and approved all application content.",
    )

    assert approved.status == ApplicationStatus.APPROVED_BY_USER
    assert approved.user_approval_note == ("I reviewed and approved all application content.")
    assert all(item.resolved for item in approved.review_items)
