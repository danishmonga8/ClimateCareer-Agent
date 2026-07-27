"""Tests for deterministic evidence-bank generation."""

from app.models.candidate import (
    CandidateProfile,
    ContactInformation,
    SkillCategory,
    SkillRecord,
)
from app.models.evidence import EvidenceStatus
from app.services.evidence_service import build_evidence_bank


def test_evidence_bank_separates_supported_and_unsupported_skills() -> None:
    """Only skills found in the source CV should become verified."""
    profile = CandidateProfile(
        full_name="Sample Candidate",
        contact=ContactInformation(
            emails=["candidate@example.com"],
        ),
        skills=[
            SkillRecord(
                name="Python",
                category=SkillCategory.PROGRAMMING,
            ),
            SkillRecord(
                name="Kubernetes",
                category=SkillCategory.OTHER,
            ),
        ],
        source_document="sample_cv.pdf",
    )

    bank = build_evidence_bank(
        profile=profile,
        cv_text="CORE TECHNICAL SKILLS\nPython and environmental analytics",
        source_sha256="a" * 64,
    )

    assert bank.records[0].status == EvidenceStatus.VERIFIED
    assert bank.records[0].allowed_in_resume is True
    assert bank.records[1].status == EvidenceStatus.REQUIRES_CONFIRMATION
    assert bank.records[1].allowed_in_resume is False


def test_cv_wording_variations_are_matched() -> None:
    """Common CV punctuation and abbreviation variations should match."""
    skill_names = [
        "Data cleaning and quality control",
        "Tree-based models",
        "Quantile regression",
        "Raster and vector processing",
        "Landslide triggering mechanisms",
    ]

    profile = CandidateProfile(
        full_name="Sample Candidate",
        contact=ContactInformation(
            emails=["candidate@example.com"],
        ),
        skills=[
            SkillRecord(
                name=name,
                category=SkillCategory.OTHER,
            )
            for name in skill_names
        ],
        source_document="sample_cv.pdf",
    )

    cv_text = """
    Experienced in data cleaning/QC and feature engineering.
    Applied clustering and tree-based models.
    Skilled in quantile
    regression and bootstrap analysis.
    QGIS for raster/vector processing.
    Hydroclimatic hazards and landslide triggering mechanisms.
    """

    bank = build_evidence_bank(
        profile=profile,
        cv_text=cv_text,
        source_sha256="a" * 64,
    )

    assert len(bank.records) == 5
    assert all(record.status == EvidenceStatus.VERIFIED for record in bank.records)
