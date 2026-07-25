"""Tests for transparent discovery filtering."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.discovery.filtering import DiscoveryFilter, filter_discovered_jobs
from app.models.discovery import DiscoveredJob, JobSource
from app.models.job import EmploymentType, WorkArrangement


def _job(**overrides: object) -> DiscoveredJob:
    data: dict[str, object] = {
        "source": JobSource.GREENHOUSE,
        "source_board": "acme",
        "source_job_id": "1",
        "company": "Acme Climate",
        "title": "Climate Data Scientist",
        "job_url": "https://example.com/jobs/1",
        "location": "London, UK",
        "work_arrangement": WorkArrangement.HYBRID,
        "employment_type": EmploymentType.FULL_TIME,
        "description": "Build remote-sensing machine-learning systems.",
        "date_posted": datetime(2026, 7, 20, tzinfo=UTC),
    }
    data.update(overrides)
    return DiscoveredJob.model_validate(data)


def test_filter_combines_keywords_location_and_enums() -> None:
    jobs = [
        _job(),
        _job(
            source_job_id="2",
            company="Acme Holdings",
            title="Finance Director",
            description="Lead corporate reporting.",
        ),
    ]
    criteria = DiscoveryFilter(
        include_keywords=["climate", "remote sensing"],
        require_all_keywords=True,
        locations=["UK"],
        work_arrangements=[WorkArrangement.HYBRID],
        employment_types=[EmploymentType.FULL_TIME],
    )

    assert filter_discovered_jobs(jobs, criteria) == [jobs[0]]


def test_filter_can_exclude_missing_and_old_posting_dates() -> None:
    cutoff = datetime(2026, 7, 15, tzinfo=UTC)
    jobs = [
        _job(),
        _job(source_job_id="2", date_posted=None),
        _job(source_job_id="3", date_posted=datetime(2026, 7, 1, tzinfo=UTC)),
    ]
    criteria = DiscoveryFilter(
        posted_since=cutoff,
        include_jobs_without_posted_date=False,
    )

    assert filter_discovered_jobs(jobs, criteria) == [jobs[0]]


def test_filter_rejects_ambiguous_naive_cutoff() -> None:
    naive_cutoff = datetime(2026, 7, 1, tzinfo=UTC).replace(tzinfo=None)
    with pytest.raises(ValidationError, match="timezone"):
        DiscoveryFilter(posted_since=naive_cutoff)


def test_filter_does_not_match_partial_words() -> None:
    jobs = [
        _job(title="Paid Media Specialist", description="Manage campaigns."),
        _job(
            source_job_id="2",
            job_url="https://example.com/jobs/2",
            title="AI Scientist",
        ),
    ]

    assert filter_discovered_jobs(
        jobs,
        DiscoveryFilter(include_keywords=["AI"]),
    ) == [jobs[1]]
