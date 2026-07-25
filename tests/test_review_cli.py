"""Tests for the human-review command-line interface."""

from pathlib import Path

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
from app.services.personalization_repository import (
    load_personalized_application,
    save_personalized_application,
)
from review_cli import main


def make_evidence() -> EvidenceRecord:
    """Create verified evidence for test applications."""
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
    general_review_item: bool = False,
) -> PersonalizedApplication:
    """Create a valid personalized application."""
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
    review_items: list[ReviewItem] = []

    if uncertain_answer:
        answers.append(
            ApplicationQuestionAnswer(
                question="What is your expected salary?",
                requires_confirmation=True,
                confirmation_reason=(
                    "The candidate must confirm the expected salary."
                ),
            )
        )
        review_items.append(
            ReviewItem(
                field_path="application_answers[0].answer",
                reason="The candidate must confirm the expected salary.",
            )
        )

    if general_review_item:
        review_items.append(
            ReviewItem(
                field_path="resume.professional_summary",
                reason="The candidate must review the summary wording.",
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
        review_items=review_items,
    )


def save_application(
    tmp_path: Path,
    application: PersonalizedApplication,
) -> Path:
    """Save and return a test application path."""
    application_path = tmp_path / "personalized_application.json"

    save_personalized_application(
        application,
        application_path,
    )

    return application_path


def test_status_displays_application_review_state(
    tmp_path: Path,
    capsys,
) -> None:
    """The status command should report pending review work."""
    application_path = save_application(
        tmp_path,
        make_application(uncertain_answer=True),
    )

    exit_code = main(
        [
            "status",
            "--application",
            str(application_path),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Status: draft" in output
    assert "Unresolved review items: 1" in output
    assert "Unconfirmed answers: 1" in output


def test_begin_command_starts_human_review(
    tmp_path: Path,
) -> None:
    """The begin command should persist needs-review status."""
    application_path = save_application(
        tmp_path,
        make_application(),
    )

    exit_code = main(
        [
            "begin",
            "--application",
            str(application_path),
        ]
    )

    saved_application = load_personalized_application(
        application_path,
    )

    assert exit_code == 0
    assert saved_application.status == ApplicationStatus.NEEDS_REVIEW


def test_resolve_answer_command_confirms_answer(
    tmp_path: Path,
) -> None:
    """The resolve-answer command should persist a human answer."""
    application_path = save_application(
        tmp_path,
        make_application(uncertain_answer=True),
    )

    assert (
        main(
            [
                "begin",
                "--application",
                str(application_path),
            ]
        )
        == 0
    )

    exit_code = main(
        [
            "resolve-answer",
            "--application",
            str(application_path),
            "--question-index",
            "0",
            "--answer",
            "My expected annual salary is INR 12,00,000.",
            "--resolution",
            "Candidate directly confirmed the expected salary.",
        ]
    )

    saved_application = load_personalized_application(
        application_path,
    )
    answer = saved_application.application_answers[0]
    review_item = saved_application.review_items[0]

    assert exit_code == 0
    assert answer.answer == (
        "My expected annual salary is INR 12,00,000."
    )
    assert answer.requires_confirmation is False
    assert review_item.resolved is True


def test_resolve_item_command_resolves_general_item(
    tmp_path: Path,
) -> None:
    """The resolve-item command should persist a human decision."""
    application_path = save_application(
        tmp_path,
        make_application(general_review_item=True),
    )

    assert (
        main(
            [
                "begin",
                "--application",
                str(application_path),
            ]
        )
        == 0
    )

    exit_code = main(
        [
            "resolve-item",
            "--application",
            str(application_path),
            "--field-path",
            "resume.professional_summary",
            "--resolution",
            "Candidate reviewed and accepted the wording.",
        ]
    )

    saved_application = load_personalized_application(
        application_path,
    )

    assert exit_code == 0
    assert saved_application.review_items[0].resolved is True
    assert saved_application.review_items[0].resolution == (
        "Candidate reviewed and accepted the wording."
    )


def test_approve_command_persists_user_approval(
    tmp_path: Path,
) -> None:
    """The approve command should persist explicit approval."""
    application_path = save_application(
        tmp_path,
        make_application(),
    )

    assert (
        main(
            [
                "begin",
                "--application",
                str(application_path),
            ]
        )
        == 0
    )

    exit_code = main(
        [
            "approve",
            "--application",
            str(application_path),
            "--approval-note",
            "I reviewed and approved all application content.",
        ]
    )

    saved_application = load_personalized_application(
        application_path,
    )

    assert exit_code == 0
    assert (
        saved_application.status
        == ApplicationStatus.APPROVED_BY_USER
    )
    assert saved_application.user_approval_note == (
        "I reviewed and approved all application content."
    )


def test_unresolved_items_block_approval(
    tmp_path: Path,
    capsys,
) -> None:
    """Approval should fail while review items remain unresolved."""
    application_path = save_application(
        tmp_path,
        make_application(uncertain_answer=True),
    )

    assert (
        main(
            [
                "begin",
                "--application",
                str(application_path),
            ]
        )
        == 0
    )

    exit_code = main(
        [
            "approve",
            "--application",
            str(application_path),
            "--approval-note",
            "I approve this application.",
        ]
    )

    error_output = capsys.readouterr().err
    saved_application = load_personalized_application(
        application_path,
    )

    assert exit_code == 1
    assert "Application review failed" in error_output
    assert saved_application.status == ApplicationStatus.NEEDS_REVIEW


def test_missing_application_returns_nonzero(
    tmp_path: Path,
    capsys,
) -> None:
    """A missing application file should produce a safe failure."""
    missing_path = tmp_path / "missing_application.json"

    exit_code = main(
        [
            "status",
            "--application",
            str(missing_path),
        ]
    )

    error_output = capsys.readouterr().err

    assert exit_code == 1
    assert "Application review failed" in error_output