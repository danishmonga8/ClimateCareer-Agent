"""Tests for strict application-claim verification."""

import pytest

from app.models.evidence import EvidenceBank, EvidenceRecord, EvidenceStatus
from app.models.personalization import (
    ApplicationClaim,
    ApplicationQuestionAnswer,
    ClaimUsage,
    PersonalizedApplication,
    TailoredCoverLetter,
    TailoredResume,
)
from app.services.claim_verification import (
    ClaimVerificationError,
    verify_application_claims,
)

CLAIM_TEXT = "Developed environmental predictive models using Python"


def make_verified_evidence() -> EvidenceRecord:
    """Create one authoritative verified evidence record."""
    return EvidenceRecord(
        evidence_id="evidence-001",
        claim=CLAIM_TEXT,
        source_document="candidate_cv.pdf",
        source_section="Professional Experience",
        source_excerpt="Developed environmental models using Python.",
        confidence_score=0.98,
        status=EvidenceStatus.VERIFIED,
        allowed_in_resume=True,
        allowed_in_cover_letter=True,
        requires_confirmation=False,
    )


def make_evidence_bank(
    records: list[EvidenceRecord] | None = None,
    candidate_name: str = "Sample Candidate",
) -> EvidenceBank:
    """Create an authoritative evidence bank."""
    return EvidenceBank(
        candidate_name=candidate_name,
        source_document="candidate_cv.pdf",
        source_sha256="a" * 64,
        records=records or [make_verified_evidence()],
    )


def make_application(
    *,
    evidence: list[EvidenceRecord] | None = None,
    claim_text: str = CLAIM_TEXT,
    candidate_name: str = "Sample Candidate",
    include_all_document_types: bool = False,
) -> PersonalizedApplication:
    """Create a personalized application containing evidence-backed claims."""
    supplied_evidence = evidence or [make_verified_evidence()]

    resume_claim = ApplicationClaim(
        text=claim_text,
        usage=ClaimUsage.RESUME,
        evidence=supplied_evidence,
    )

    cover_letter_claims: list[ApplicationClaim] = []
    application_answers: list[ApplicationQuestionAnswer] = []

    if include_all_document_types:
        cover_letter_claims.append(
            ApplicationClaim(
                text=f"{CLAIM_TEXT}.",
                usage=ClaimUsage.COVER_LETTER,
                evidence=supplied_evidence,
            )
        )
        application_answers.append(
            ApplicationQuestionAnswer(
                question="Describe your relevant modelling experience.",
                answer=CLAIM_TEXT,
                claims=[
                    ApplicationClaim(
                        text=CLAIM_TEXT,
                        usage=ClaimUsage.APPLICATION_ANSWER,
                        evidence=supplied_evidence,
                    )
                ],
                requires_confirmation=False,
            )
        )

    return PersonalizedApplication(
        candidate_name=candidate_name,
        job_title="Environmental Data Scientist",
        employer="Example Climate Company",
        job_url="https://example.com/jobs/123",
        resume=TailoredResume(claims=[resume_claim]),
        cover_letter=TailoredCoverLetter(
            body="Application for the advertised position.",
            claims=cover_letter_claims,
        ),
        application_answers=application_answers,
    )


def test_all_document_claims_are_verified() -> None:
    """Claims from every supported document type should be checked."""
    evidence = make_verified_evidence()
    application = make_application(
        evidence=[evidence],
        include_all_document_types=True,
    )

    result = verify_application_claims(
        application=application,
        evidence_bank=make_evidence_bank([evidence]),
    )

    assert result.verified_claim_count == 3
    assert result.verified_evidence_ids == ["evidence-001"]


def test_capitalization_spacing_and_punctuation_are_accepted() -> None:
    """Safe formatting variations should not alter claim meaning."""
    application = make_application(
        claim_text=("  DEVELOPED environmental predictive models using Python!!!  ")
    )

    result = verify_application_claims(
        application=application,
        evidence_bank=make_evidence_bank(),
    )

    assert result.verified_claim_count == 1


def test_unverified_paraphrase_is_rejected() -> None:
    """A semantic paraphrase must not pass strict verification."""
    application = make_application(claim_text="Built advanced climate AI systems with Python.")

    with pytest.raises(
        ClaimVerificationError,
        match="not an exact normalized match",
    ):
        verify_application_claims(
            application=application,
            evidence_bank=make_evidence_bank(),
        )


def test_unknown_evidence_id_is_rejected() -> None:
    """Claims must not reference evidence outside the authoritative bank."""
    unknown_record = make_verified_evidence().model_copy(update={"evidence_id": "unknown-001"})
    application = make_application(evidence=[unknown_record])

    with pytest.raises(
        ClaimVerificationError,
        match="unknown evidence ID",
    ):
        verify_application_claims(
            application=application,
            evidence_bank=make_evidence_bank(),
        )


def test_modified_evidence_record_is_rejected() -> None:
    """Embedded evidence must match the authoritative record exactly."""
    modified_record = make_verified_evidence().model_copy(
        update={"source_excerpt": "Modified supporting text."}
    )
    application = make_application(evidence=[modified_record])

    with pytest.raises(
        ClaimVerificationError,
        match="modified evidence record",
    ):
        verify_application_claims(
            application=application,
            evidence_bank=make_evidence_bank(),
        )


def test_duplicate_evidence_ids_in_claim_are_rejected() -> None:
    """A claim must not reference the same evidence record twice."""
    evidence = make_verified_evidence()
    application = make_application(evidence=[evidence, evidence])

    with pytest.raises(
        ClaimVerificationError,
        match="contains duplicate evidence ID",
    ):
        verify_application_claims(
            application=application,
            evidence_bank=make_evidence_bank([evidence]),
        )


def test_duplicate_authoritative_evidence_ids_are_rejected() -> None:
    """The authoritative bank must contain unique evidence IDs."""
    first_record = make_verified_evidence()
    second_record = first_record.model_copy(
        update={"claim": "A different claim with the same identifier."}
    )

    with pytest.raises(
        ClaimVerificationError,
        match="Evidence bank contains duplicate evidence ID",
    ):
        verify_application_claims(
            application=make_application(evidence=[first_record]),
            evidence_bank=make_evidence_bank([first_record, second_record]),
        )


def test_candidate_mismatch_is_rejected() -> None:
    """Evidence belonging to another candidate must not be accepted."""
    with pytest.raises(
        ClaimVerificationError,
        match="candidate does not match",
    ):
        verify_application_claims(
            application=make_application(),
            evidence_bank=make_evidence_bank(candidate_name="Different Candidate"),
        )
