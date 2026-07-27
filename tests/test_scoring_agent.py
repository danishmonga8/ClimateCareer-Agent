"""Tests for the explainable Job Relevance Scoring Agent."""

from datetime import date
from unittest.mock import Mock

from app.agents.scoring_agent import (
    CategoryAssessment,
    ScoringExtractionResult,
    score_job_relevance,
)
from app.core.settings import Settings
from app.models.candidate import CandidateProfile, ContactInformation
from app.models.evidence import EvidenceBank
from app.models.job import JobDescription
from app.models.scoring import (
    ApplicationRecommendation,
    ScoreCategory,
)


def test_scoring_agent_applies_fixed_weights(monkeypatch) -> None:
    """Python, not the model, should apply the 100-point weights."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")
    settings = Settings(_env_file=None)

    profile = CandidateProfile(
        full_name="Sample Candidate",
        contact=ContactInformation(
            emails=["candidate@example.com"],
            location="India",
        ),
        source_document="sample_cv.pdf",
    )

    evidence_bank = EvidenceBank(
        candidate_name="Sample Candidate",
        source_document="sample_cv.pdf",
        source_sha256="a" * 64,
    )

    job = JobDescription(
        company="Sample Company",
        title="Environmental Data Scientist",
        job_url="https://example.com/jobs/123",
        source="manual_input",
        discovery_date=date(2026, 7, 16),
        raw_description="Environmental data-science role.",
        extraction_confidence=0.95,
    )

    extracted = ScoringExtractionResult(
        category_assessments=[
            CategoryAssessment(
                category=category,
                fit_ratio=0.8,
                rationale="The candidate has strong relevant evidence.",
            )
            for category in ScoreCategory
        ],
        strongest_alignments=["Environmental data analysis"],
        confidence_score=0.9,
    )

    mock_client = Mock()
    mock_client.responses.parse.return_value.output_parsed = extracted

    result = score_job_relevance(
        profile,
        evidence_bank,
        job,
        client=mock_client,
        settings=settings,
    )

    assert result.overall_score == 80
    assert result.recommendation == ApplicationRecommendation.APPLY
    assert len(result.components) == 8
    assert sum(component.maximum_points for component in result.components) == 100
