"""Tests for the structured job-description models."""

from datetime import date

from app.models.job import (
    JobDescription,
    JobRequirement,
    RequirementCategory,
    WorkArrangement,
)


def test_job_description_separates_mandatory_requirements() -> None:
    """Mandatory job requirements must remain separately identifiable."""
    job = JobDescription(
        company="Sample Climate Company",
        title="Environmental Data Scientist",
        job_url="https://example.com/jobs/123",
        source="company_careers_page",
        location="India",
        work_arrangement=WorkArrangement.HYBRID,
        discovery_date=date(2026, 7, 16),
        mandatory_requirements=[
            JobRequirement(
                description="Professional Python experience",
                category=RequirementCategory.TECHNICAL_SKILL,
                normalized_keywords=["python"],
            )
        ],
        preferred_requirements=[
            JobRequirement(
                description="Experience with geospatial data",
                category=RequirementCategory.DOMAIN_SKILL,
                normalized_keywords=["geospatial"],
            )
        ],
        raw_description="Seeking an environmental data scientist with Python experience.",
        extraction_confidence=0.95,
    )

    assert job.company == "Sample Climate Company"
    assert len(job.mandatory_requirements) == 1
    assert len(job.preferred_requirements) == 1
    assert job.extraction_confidence == 0.95
