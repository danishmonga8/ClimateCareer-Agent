"""Tests for the Job Description Parser Agent."""

from datetime import date
from unittest.mock import Mock

from app.agents.jd_parser_agent import (
    JobExtractionResult,
    parse_job_description,
)
from app.core.settings import Settings
from app.models.job import (
    JobRequirement,
    RequirementCategory,
    WorkArrangement,
)


def test_jd_parser_preserves_requirement_priority(monkeypatch) -> None:
    """Mandatory and preferred requirements must remain separate."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")
    settings = Settings(_env_file=None)

    extracted = JobExtractionResult(
        company="Sample Climate Company",
        title="Environmental Data Scientist",
        location="India",
        work_arrangement=WorkArrangement.HYBRID,
        mandatory_requirements=[
            JobRequirement(
                description="Python experience is required.",
                category=RequirementCategory.TECHNICAL_SKILL,
                normalized_keywords=["python"],
            )
        ],
        preferred_requirements=[
            JobRequirement(
                description="Geospatial experience is preferred.",
                category=RequirementCategory.DOMAIN_SKILL,
                normalized_keywords=["geospatial"],
            )
        ],
        required_skills=["Python"],
        preferred_skills=["Geospatial analytics"],
        extraction_confidence=0.96,
    )

    mock_client = Mock()
    mock_client.responses.parse.return_value.output_parsed = extracted

    job = parse_job_description(
        job_text="Python is required. Geospatial experience is preferred.",
        job_url="https://example.com/jobs/123",
        source="manual_input",
        discovery_date=date(2026, 7, 16),
        client=mock_client,
        settings=settings,
    )

    assert job.company == "Sample Climate Company"
    assert len(job.mandatory_requirements) == 1
    assert len(job.preferred_requirements) == 1
    assert str(job.job_url) == "https://example.com/jobs/123"
    assert job.extraction_confidence == 0.96