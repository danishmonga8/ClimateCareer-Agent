"""Tests for the evidence-constrained personalization agent."""

from datetime import date
from unittest.mock import Mock

import pytest

from app.agents.personalization_agent import (
    ApplicationAnswerSelection,
    PersonalizationError,
    PersonalizationSelectionResult,
    personalize_application,
)
from app.core.settings import Settings
from app.models.candidate import CandidateProfile, ContactInformation
from app.models.evidence import EvidenceBank, EvidenceRecord, EvidenceStatus
from app.models.job import JobDescription
from app.models.personalization import ApplicationStatus
from app.services.claim_verification import verify_application_claims

CLAIM_TEXT = "Developed environmental predictive models using Python"


def make_profile(
    candidate_name: str = "Sample Candidate",
) -> CandidateProfile:
    """Create a minimal candidate profile."""
    return CandidateProfile(
        full_name=candidate_name,
        contact=ContactInformation(
            emails=["candidate@example.com"],
        ),
        source_document="candidate_cv.pdf",
    )


def make_evidence(
    *,
    evidence_id: str = "evidence-001",
    allowed_in_resume: bool = True,
    allowed_in_cover_letter: bool = True,
) -> EvidenceRecord:
    """Create one authoritative verified evidence record."""
    return EvidenceRecord(
        evidence_id=evidence_id,
        claim=CLAIM_TEXT,
        source_document="candidate_cv.pdf",
        source_section="Professional Experience",
        source_excerpt="Developed environmental models using Python.",
        confidence_score=0.98,
        status=EvidenceStatus.VERIFIED,
        allowed_in_resume=allowed_in_resume,
        allowed_in_cover_letter=allowed_in_cover_letter,
        requires_confirmation=False,
    )


def make_bank(
    *,
    candidate_name: str = "Sample Candidate",
    evidence: EvidenceRecord | None = None,
) -> EvidenceBank:
    """Create an evidence bank."""
    return EvidenceBank(
        candidate_name=candidate_name,
        source_document="candidate_cv.pdf",
        source_sha256="a" * 64,
        records=[evidence or make_evidence()],
    )


def make_job() -> JobDescription:
    """Create a structured target job."""
    return JobDescription(
        company="Example Climate Company",
        title="Environmental Data Scientist",
        job_url="https://example.com/jobs/123",
        source="Example Careers",
        discovery_date=date(2026, 7, 25),
        required_skills=["Python", "environmental modelling"],
        raw_description="Use Python to develop environmental models.",
        extraction_confidence=0.95,
    )


def make_settings(monkeypatch) -> Settings:
    """Create test settings without loading a real API key."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")
    return Settings(_env_file=None)


def test_personalization_uses_authoritative_evidence(
    monkeypatch,
) -> None:
    """Selected IDs should become locally verified application claims."""
    evidence = make_evidence()
    bank = make_bank(evidence=evidence)
    selection = PersonalizationSelectionResult(
        resume_evidence_ids=["evidence-001"],
        cover_letter_evidence_ids=["evidence-001"],
        application_answers=[
            ApplicationAnswerSelection(
                question_index=0,
                evidence_ids=["evidence-001"],
                requires_confirmation=False,
            )
        ],
    )

    mock_client = Mock()
    mock_client.responses.parse.return_value.output_parsed = selection

    application = personalize_application(
        profile=make_profile(),
        evidence_bank=bank,
        job=make_job(),
        application_questions=["Describe your relevant modelling experience."],
        client=mock_client,
        settings=make_settings(monkeypatch),
    )

    assert application.status == ApplicationStatus.DRAFT
    assert application.resume.claims[0].evidence[0] == evidence
    assert application.cover_letter.claims[0].text == CLAIM_TEXT
    assert application.application_answers[0].answer == CLAIM_TEXT
    assert application.review_items == []

    verification = verify_application_claims(application, bank)

    assert verification.verified_claim_count == 3
    assert verification.verified_evidence_ids == ["evidence-001"]

    call_arguments = mock_client.responses.parse.call_args.kwargs
    assert call_arguments["model"] == "gpt-5.6-luna"
    assert call_arguments["text_format"] is PersonalizationSelectionResult


def test_unknown_selected_evidence_is_rejected(monkeypatch) -> None:
    """The model cannot introduce an evidence identifier."""
    selection = PersonalizationSelectionResult(
        resume_evidence_ids=["unknown-001"],
    )
    mock_client = Mock()
    mock_client.responses.parse.return_value.output_parsed = selection

    with pytest.raises(
        PersonalizationError,
        match="Unknown evidence ID selected",
    ):
        personalize_application(
            profile=make_profile(),
            evidence_bank=make_bank(),
            job=make_job(),
            client=mock_client,
            settings=make_settings(monkeypatch),
        )


def test_resume_permission_is_enforced(monkeypatch) -> None:
    """Evidence not permitted for resumes must remain excluded."""
    restricted_evidence = make_evidence(
        allowed_in_resume=False,
    )
    selection = PersonalizationSelectionResult(
        resume_evidence_ids=["evidence-001"],
    )
    mock_client = Mock()
    mock_client.responses.parse.return_value.output_parsed = selection

    with pytest.raises(
        PersonalizationError,
        match="not allowed in the resume",
    ):
        personalize_application(
            profile=make_profile(),
            evidence_bank=make_bank(evidence=restricted_evidence),
            job=make_job(),
            client=mock_client,
            settings=make_settings(monkeypatch),
        )


def test_candidate_mismatch_is_rejected_before_api_call(
    monkeypatch,
) -> None:
    """Evidence belonging to another candidate cannot be personalized."""
    mock_client = Mock()

    with pytest.raises(
        PersonalizationError,
        match="does not match",
    ):
        personalize_application(
            profile=make_profile(),
            evidence_bank=make_bank(candidate_name="Different Candidate"),
            job=make_job(),
            client=mock_client,
            settings=make_settings(monkeypatch),
        )

    mock_client.responses.parse.assert_not_called()


def test_uncertain_answer_creates_review_item(monkeypatch) -> None:
    """Missing evidence should leave the answer for human review."""
    selection = PersonalizationSelectionResult(
        application_answers=[
            ApplicationAnswerSelection(
                question_index=0,
                requires_confirmation=True,
                confirmation_reason=("The candidate must provide the expected salary."),
            )
        ],
    )
    mock_client = Mock()
    mock_client.responses.parse.return_value.output_parsed = selection

    application = personalize_application(
        profile=make_profile(),
        evidence_bank=make_bank(),
        job=make_job(),
        application_questions=["What is your expected salary?"],
        client=mock_client,
        settings=make_settings(monkeypatch),
    )

    answer = application.application_answers[0]

    assert answer.answer is None
    assert answer.requires_confirmation is True
    assert len(application.review_items) == 1
    assert application.review_items[0].resolved is False


def test_every_application_question_must_be_assessed(
    monkeypatch,
) -> None:
    """The model cannot silently omit an application question."""
    selection = PersonalizationSelectionResult(
        application_answers=[
            ApplicationAnswerSelection(
                question_index=0,
                requires_confirmation=True,
                confirmation_reason="User input is required.",
            )
        ],
    )
    mock_client = Mock()
    mock_client.responses.parse.return_value.output_parsed = selection

    with pytest.raises(
        PersonalizationError,
        match="did not assess every application question",
    ):
        personalize_application(
            profile=make_profile(),
            evidence_bank=make_bank(),
            job=make_job(),
            application_questions=[
                "Why are you interested in this role?",
                "When can you start?",
            ],
            client=mock_client,
            settings=make_settings(monkeypatch),
        )


def test_sensitive_question_cannot_be_auto_answered(
    monkeypatch,
) -> None:
    """Sensitive application fields always require human confirmation."""
    selection = PersonalizationSelectionResult(
        application_answers=[
            ApplicationAnswerSelection(
                question_index=0,
                evidence_ids=["evidence-001"],
                requires_confirmation=False,
            )
        ],
    )
    mock_client = Mock()
    mock_client.responses.parse.return_value.output_parsed = selection

    with pytest.raises(
        PersonalizationError,
        match="Sensitive application questions",
    ):
        personalize_application(
            profile=make_profile(),
            evidence_bank=make_bank(),
            job=make_job(),
            application_questions=["Are you legally authorized to work in this country?"],
            client=mock_client,
            settings=make_settings(monkeypatch),
        )
