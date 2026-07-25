"""Tests for stable discovery deduplication."""

from app.discovery.deduplication import deduplicate_jobs
from app.models.discovery import DiscoveredJob, JobSource


def _job(**overrides: object) -> DiscoveredJob:
    data: dict[str, object] = {
        "source": JobSource.GREENHOUSE,
        "source_board": "acme",
        "source_job_id": "1",
        "company": "Acme Climate",
        "title": "Climate Scientist",
        "job_url": "https://example.com/jobs/1?tracking=abc",
        "location": "Remote",
        "description": "Analyse climate data.",
    }
    data.update(overrides)
    return DiscoveredJob.model_validate(data)


def test_exact_source_duplicates_keep_richer_record() -> None:
    original = _job()
    richer = _job(description="Analyse climate data and build operational forecasts.")

    assert deduplicate_jobs([original, richer]) == [richer]


def test_tracking_parameters_do_not_create_url_duplicates() -> None:
    original = _job()
    duplicate = _job(
        source=JobSource.LEVER,
        source_board="acme-lever",
        source_job_id="lever-9",
        job_url="https://example.com/jobs/1?source=lever",
    )

    assert len(deduplicate_jobs([original, duplicate])) == 1


def test_cross_source_company_title_location_duplicates_are_removed() -> None:
    original = _job()
    duplicate = _job(
        source=JobSource.ASHBY,
        source_board="acme-ashby",
        source_job_id="ashby-2",
        job_url="https://jobs.ashbyhq.com/acme/ashby-2",
        company="ACME climate",
        title="Climate-Scientist",
        location="remote",
    )

    assert len(deduplicate_jobs([original, duplicate])) == 1


def test_distinct_locations_are_retained() -> None:
    london = _job(location="London")
    berlin = _job(
        source_job_id="2",
        job_url="https://example.com/jobs/2",
        location="Berlin",
    )

    assert deduplicate_jobs([london, berlin]) == [london, berlin]


def test_record_linking_two_duplicate_groups_collapses_both() -> None:
    london = _job(location="London")
    berlin = _job(
        source=JobSource.LEVER,
        source_board="acme-lever",
        source_job_id="lever-2",
        job_url="https://example.com/jobs/2",
        location="Berlin",
    )
    bridge = _job(
        job_url="https://example.com/jobs/3",
        location="Berlin",
        description="A richer description connecting updated source data.",
    )

    assert deduplicate_jobs([london, berlin, bridge]) == [bridge]
