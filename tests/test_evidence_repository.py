"""Tests for candidate-profile loading and evidence-bank storage."""

import json
from pathlib import Path

from app.models.candidate import CandidateProfile, ContactInformation
from app.models.evidence import EvidenceBank
from app.services.evidence_repository import save_evidence_bank
from app.services.profile_service import (
    load_candidate_profile,
    save_candidate_profile,
)


def test_private_profile_and_evidence_bank_can_be_persisted(
    tmp_path: Path,
) -> None:
    """Validated private data should survive a save-and-load cycle."""
    profile = CandidateProfile(
        full_name="Sample Candidate",
        contact=ContactInformation(
            emails=["candidate@example.com"],
        ),
        source_document="sample_cv.pdf",
    )

    profile_path = save_candidate_profile(
        profile,
        tmp_path / "candidate_profile.json",
    )
    loaded_profile = load_candidate_profile(profile_path)

    bank = EvidenceBank(
        candidate_name=loaded_profile.full_name,
        source_document=loaded_profile.source_document,
        source_sha256="a" * 64,
    )
    evidence_path = save_evidence_bank(
        bank,
        tmp_path / "evidence_bank.json",
    )

    stored_evidence = json.loads(
        evidence_path.read_text(encoding="utf-8")
    )

    assert loaded_profile.full_name == "Sample Candidate"
    assert stored_evidence["candidate_name"] == "Sample Candidate"
    assert stored_evidence["source_sha256"] == "a" * 64