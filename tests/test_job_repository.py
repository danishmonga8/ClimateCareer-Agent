"""Tests for structured job-description storage."""

from datetime import date
from pathlib import Path

from app.models.job import JobDescription
from app.services.job_repository import (
    load_job_description,
    save_job_description,
)


def test_structured_job_survives_save_and_load(tmp_path: Path) -> None:
    """Validated job information should survive JSON persistence."""
    job = JobDescription(
        company="Sample Climate Company",
        title="Climate Data Scientist",
        job_url="https://example.com/jobs/123",
        source="manual_input",
        discovery_date=date(2026, 7, 16),
        required_skills=["Python"],
        raw_description="Python experience is required.",
        extraction_confidence=0.95,
    )

    output_path = tmp_path / "structured_job.json"
    saved_path = save_job_description(job, output_path)
    loaded_job = load_job_description(saved_path)

    assert loaded_job.company == "Sample Climate Company"
    assert loaded_job.title == "Climate Data Scientist"
    assert loaded_job.required_skills == ["Python"]
    assert loaded_job.extraction_confidence == 0.95