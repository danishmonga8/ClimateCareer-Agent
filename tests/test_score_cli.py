"""Tests for the explainable job-scoring command."""

from datetime import date
from pathlib import Path
from unittest.mock import patch

from app.models.candidate import CandidateProfile, ContactInformation
from app.models.evidence import EvidenceBank
from app.models.job import JobDescription
from app.models.scoring import (
    JobRelevanceScore,
    ScoreComponent,
    WeightScheme,
)
from app.services.evidence_repository import save_evidence_bank
from app.services.job_repository import save_job_description
from app.services.profile_service import save_candidate_profile
from app.services.scoring_repository import load_scoring_result
from score_cli import main


def test_score_cli_saves_mocked_result(tmp_path: Path) -> None:
    """The CLI should combine private inputs and save a validated result."""
    profile_path = tmp_path / "candidate_profile.json"
    evidence_path = tmp_path / "evidence_bank.json"
    job_path = tmp_path / "structured_job.json"
    output_path = tmp_path / "scoring_result.json"

    profile = CandidateProfile(
        full_name="Sample Candidate",
        contact=ContactInformation(
            emails=["candidate@example.com"],
            location="India",
        ),
        source_document="sample_cv.pdf",
    )
    save_candidate_profile(profile, profile_path)

    evidence = EvidenceBank(
        candidate_name="Sample Candidate",
        source_document="sample_cv.pdf",
        source_sha256="a" * 64,
    )
    save_evidence_bank(evidence, evidence_path)

    job = JobDescription(
        company="Sample Company",
        title="Environmental Data Scientist",
        job_url="https://example.com/jobs/123",
        source="manual_input",
        discovery_date=date(2026, 7, 16),
        raw_description="Environmental data-science role.",
        extraction_confidence=0.95,
    )
    save_job_description(job, job_path)

    weights = WeightScheme()
    mocked_result = JobRelevanceScore(
        company=job.company,
        job_title=job.title,
        weight_scheme=weights,
        components=[
            ScoreComponent(
                category=category,
                awarded_points=maximum * 0.8,
                maximum_points=maximum,
                rationale="Strong verified alignment.",
            )
            for category, maximum in weights.as_mapping().items()
        ],
        confidence_score=0.9,
    )

    with patch(
        "score_cli.score_job_relevance",
        return_value=mocked_result,
    ):
        exit_code = main(
            [
                "--profile",
                str(profile_path),
                "--evidence",
                str(evidence_path),
                "--job",
                str(job_path),
                "--output",
                str(output_path),
            ]
        )

    stored_result = load_scoring_result(output_path)

    assert exit_code == 0
    assert stored_result.overall_score == 80
    assert stored_result.company == "Sample Company"