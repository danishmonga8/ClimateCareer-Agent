"""Tests for normalized public job-discovery records."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.discovery import DiscoveredJob, JobSource
from app.models.job import EmploymentType, WorkArrangement


def test_discovered_job_accepts_valid_public_listing() -> None:
    job = DiscoveredJob(
        source=JobSource.GREENHOUSE,
        source_board="example",
        source_job_id="12345",
        company="Example Climate",
        title="Remote Sensing Scientist",
        job_url="https://boards.greenhouse.io/example/jobs/12345",
        location="Remote",
        work_arrangement=WorkArrangement.REMOTE,
        employment_type=EmploymentType.FULL_TIME,
        description="Develop satellite-data calibration workflows.",
    )

    assert job.company == "Example Climate"
    assert job.source == JobSource.GREENHOUSE
    assert job.discovered_at.tzinfo is not None


def test_discovered_job_rejects_blank_description() -> None:
    with pytest.raises(ValidationError):
        DiscoveredJob(
            source=JobSource.GREENHOUSE,
            source_board="example",
            source_job_id="12345",
            company="Example Climate",
            title="Remote Sensing Scientist",
            job_url="https://boards.greenhouse.io/example/jobs/12345",
            description="   ",
        )


def test_discovered_job_rejects_invalid_url() -> None:
    with pytest.raises(ValidationError):
        DiscoveredJob(
            source=JobSource.LEVER,
            source_board="example",
            source_job_id="abc",
            company="Example Climate",
            title="Environmental Data Scientist",
            job_url="not-a-valid-url",
            description="Analyse environmental datasets.",
        )


def test_discovered_job_rejects_naive_timestamp() -> None:
    naive_timestamp = datetime(2026, 7, 25, tzinfo=UTC).replace(tzinfo=None)

    with pytest.raises(ValidationError, match="timezone"):
        DiscoveredJob(
            source=JobSource.ASHBY,
            source_board="example",
            source_job_id="abc",
            company="Example Climate",
            title="Environmental Data Scientist",
            job_url="https://jobs.ashbyhq.com/example/abc",
            description="Analyse environmental datasets.",
            date_posted=naive_timestamp,
        )
