"""Tests for discovery snapshot orchestration."""

from app.discovery.filtering import DiscoveryFilter
from app.discovery.service import build_discovery_snapshot
from app.models.discovery import DiscoveredJob, JobSource


def _job(identifier: str, title: str) -> DiscoveredJob:
    return DiscoveredJob(
        source=JobSource.GREENHOUSE,
        source_board="acme",
        source_job_id=identifier,
        company="Acme Climate",
        title=title,
        job_url=f"https://example.com/jobs/{identifier}",
        description=f"Description for {title}",
    )


def test_snapshot_service_flattens_filters_and_deduplicates() -> None:
    climate_job = _job("1", "Climate Scientist")
    duplicate = climate_job.model_copy(
        update={
            "description": (
                "A richer climate description with methods, responsibilities, and requirements."
            )
        }
    )
    unrelated = _job("2", "Accountant")

    snapshot = build_discovery_snapshot(
        [[climate_job], [duplicate, unrelated]],
        criteria=DiscoveryFilter(include_keywords=["scientist"]),
    )

    assert snapshot.jobs == [duplicate]
