"""Strict verification of claims used in personalized applications."""

from collections.abc import Iterator

from pydantic import Field

from app.models.candidate import StrictModel
from app.models.evidence import EvidenceBank, EvidenceRecord, EvidenceStatus
from app.models.personalization import (
    ApplicationClaim,
    ClaimUsage,
    PersonalizedApplication,
)


class ClaimVerificationError(ValueError):
    """Raised when an application claim fails evidence verification."""


class ClaimVerificationResult(StrictModel):
    """Summary of a successful claim-verification operation."""

    candidate_name: str = Field(min_length=1)
    verified_claim_count: int = Field(ge=0)
    verified_evidence_ids: list[str] = Field(default_factory=list)


def _normalize_claim_text(value: str) -> str:
    """Ignore only capitalization, spacing, and punctuation differences."""
    return "".join(
        character
        for character in value.casefold()
        if character.isalnum()
    )


def _index_authoritative_evidence(
    evidence_bank: EvidenceBank,
) -> dict[str, EvidenceRecord]:
    """Index authoritative records and reject duplicate identifiers."""
    records_by_id: dict[str, EvidenceRecord] = {}

    for record in evidence_bank.records:
        if record.evidence_id in records_by_id:
            raise ClaimVerificationError(
                "Evidence bank contains duplicate evidence ID: "
                f"{record.evidence_id}"
            )

        records_by_id[record.evidence_id] = record

    return records_by_id


def _iter_application_claims(
    application: PersonalizedApplication,
) -> Iterator[tuple[str, ApplicationClaim, ClaimUsage]]:
    """Yield every application claim with its expected usage context."""
    for index, claim in enumerate(application.resume.claims):
        yield f"resume.claims[{index}]", claim, ClaimUsage.RESUME

    for index, claim in enumerate(application.cover_letter.claims):
        yield (
            f"cover_letter.claims[{index}]",
            claim,
            ClaimUsage.COVER_LETTER,
        )

    for answer_index, answer in enumerate(application.application_answers):
        for claim_index, claim in enumerate(answer.claims):
            yield (
                "application_answers"
                f"[{answer_index}].claims[{claim_index}]",
                claim,
                ClaimUsage.APPLICATION_ANSWER,
            )


def _verify_claim(
    *,
    field_path: str,
    claim: ApplicationClaim,
    expected_usage: ClaimUsage,
    authoritative_records: dict[str, EvidenceRecord],
) -> list[str]:
    """Verify one claim against authoritative evidence records."""
    if claim.usage != expected_usage:
        raise ClaimVerificationError(
            f"{field_path} has an incorrect claim usage."
        )

    referenced_ids: list[str] = []
    referenced_records: list[EvidenceRecord] = []
    seen_ids: set[str] = set()

    for supplied_record in claim.evidence:
        evidence_id = supplied_record.evidence_id

        if evidence_id in seen_ids:
            raise ClaimVerificationError(
                f"{field_path} contains duplicate evidence ID: "
                f"{evidence_id}"
            )

        seen_ids.add(evidence_id)

        authoritative_record = authoritative_records.get(evidence_id)

        if authoritative_record is None:
            raise ClaimVerificationError(
                f"{field_path} references unknown evidence ID: "
                f"{evidence_id}"
            )

        if supplied_record != authoritative_record:
            raise ClaimVerificationError(
                f"{field_path} contains a modified evidence record: "
                f"{evidence_id}"
            )

        if (
            authoritative_record.status != EvidenceStatus.VERIFIED
            or authoritative_record.requires_confirmation
        ):
            raise ClaimVerificationError(
                f"{field_path} references unverified evidence: "
                f"{evidence_id}"
            )

        referenced_ids.append(evidence_id)
        referenced_records.append(authoritative_record)

    normalized_claim = _normalize_claim_text(claim.text)

    has_exact_support = any(
        normalized_claim == _normalize_claim_text(record.claim)
        for record in referenced_records
    )

    if not has_exact_support:
        raise ClaimVerificationError(
            f"{field_path} is not an exact normalized match for its "
            "referenced evidence."
        )

    return referenced_ids


def verify_application_claims(
    application: PersonalizedApplication,
    evidence_bank: EvidenceBank,
) -> ClaimVerificationResult:
    """Verify every application claim against its authoritative evidence."""
    if application.candidate_name != evidence_bank.candidate_name:
        raise ClaimVerificationError(
            "Application candidate does not match the evidence-bank candidate."
        )

    authoritative_records = _index_authoritative_evidence(evidence_bank)
    verified_claim_count = 0
    verified_evidence_ids: list[str] = []
    seen_verified_ids: set[str] = set()

    for field_path, claim, expected_usage in _iter_application_claims(
        application
    ):
        claim_evidence_ids = _verify_claim(
            field_path=field_path,
            claim=claim,
            expected_usage=expected_usage,
            authoritative_records=authoritative_records,
        )
        verified_claim_count += 1

        for evidence_id in claim_evidence_ids:
            if evidence_id not in seen_verified_ids:
                seen_verified_ids.add(evidence_id)
                verified_evidence_ids.append(evidence_id)

    return ClaimVerificationResult(
        candidate_name=application.candidate_name,
        verified_claim_count=verified_claim_count,
        verified_evidence_ids=verified_evidence_ids,
    )