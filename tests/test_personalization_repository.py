"""Tests for private personalized-application storage."""

import pytest

from app.models.evidence import EvidenceRecord, EvidenceStatus
from app.models.personalization import (
    ApplicationClaim,
    ClaimUsage,
    PersonalizedApplication,
    TailoredCoverLetter,
    TailoredResume,
)
from app.services.personalization_repository import (
    ApplicationStorageError,
    load_personalized_application,
    save_personalized_application,
)


def make_application() -> PersonalizedApplication:
    """Create a valid evidence-backed application draft."""
    evidence = EvidenceRecord(
        evidence_id="evidence-001",
        claim="Developed environmental predictive models using Python",
        source_document="candidate_cv.pdf",
        confidence_score=0.95,
        status=EvidenceStatus.VERIFIED,
        allowed_in_resume=True,
        allowed_in_cover_letter=True,
        requires_confirmation=False,
    )

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
            body=("I am applying for the Environmental Data Scientist position."),
            claims=[cover_letter_claim],
        ),
    )


def test_personalized_application_round_trip(tmp_path) -> None:
    """A validated application should survive private JSON storage."""
    application = make_application()
    output_path = tmp_path / "personalized_application.json"

    saved_path = save_personalized_application(
        application,
        output_path,
    )
    loaded_application = load_personalized_application(saved_path)

    assert saved_path == output_path.resolve()
    assert loaded_application == application
    assert loaded_application.candidate_name == "Sample Candidate"
    assert loaded_application.resume.claims[0].evidence[0].evidence_id == ("evidence-001")


def test_non_json_storage_path_is_rejected(tmp_path) -> None:
    """Application storage must use a JSON destination."""
    with pytest.raises(
        ApplicationStorageError,
        match=r"must use a \.json file",
    ):
        save_personalized_application(
            make_application(),
            tmp_path / "personalized_application.txt",
        )


def test_invalid_application_json_is_rejected(tmp_path) -> None:
    """Malformed or schema-invalid JSON must not be loaded."""
    input_path = tmp_path / "personalized_application.json"
    input_path.write_text(
        '{"candidate_name": "Incomplete Candidate"}',
        encoding="utf-8",
    )

    with pytest.raises(
        ApplicationStorageError,
        match="Unable to load a valid personalized application",
    ):
        load_personalized_application(input_path)
