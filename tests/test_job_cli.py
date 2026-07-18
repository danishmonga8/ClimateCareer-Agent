"""Tests for the manual job-description command."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app.models.job import JobDescription
from job_cli import main


def test_job_cli_saves_mocked_structured_job(tmp_path: Path) -> None:
    """The CLI should save parsed data without making a real API call."""
    job_file = tmp_path / "job.txt"
    output_file = tmp_path / "structured_job.json"
    job_file.write_text(
        "Python experience is required.",
        encoding="utf-8",
    )

    mocked_job = JobDescription(
        company="Sample Company",
        title="Environmental Data Scientist",
        job_url="https://example.com/jobs/123",
        source="manual_input",
        discovery_date=date(2026, 7, 16),
        required_skills=["Python"],
        raw_description="Python experience is required.",
        extraction_confidence=0.95,
    )

    with patch(
        "job_cli.parse_job_description",
        return_value=mocked_job,
    ):
        exit_code = main(
            [
                "--file",
                str(job_file),
                "--url",
                "https://example.com/jobs/123",
                "--output",
                str(output_file),
            ]
        )

    stored_job = json.loads(
        output_file.read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert stored_job["company"] == "Sample Company"
    assert stored_job["title"] == "Environmental Data Scientist"