"""Tests for local review-queue search, filters, boundaries, and sorting."""

from datetime import UTC, datetime

from app.dashboard.data_loader import DashboardJobView
from app.dashboard.filters import QueueFilters, filter_queue, sort_queue
from app.models.dashboard_review import ArtifactReferences, DashboardReviewRecord
from app.models.discovery import DiscoveredJob, JobSource


def make_view(
    job_id: str,
    company: str,
    location: str,
    discovered_at: datetime,
) -> DashboardJobView:
    record = DashboardReviewRecord(
        source=JobSource.MANUAL,
        source_board="example",
        source_job_id=job_id,
        artifacts=ArtifactReferences(discovery_snapshot="snapshot.json"),
    )
    return DashboardJobView(
        record=record,
        job=DiscoveredJob(
            source=JobSource.MANUAL,
            source_board="example",
            source_job_id=job_id,
            company=company,
            title="Climate Analyst",
            job_url=f"https://example.test/jobs/{job_id}",
            location=location,
            description="Analyse climate data.",
            discovered_at=discovered_at,
        ),
        score=None,
        application=None,
    )


def test_search_company_location_and_date_filters_are_local_and_inclusive() -> None:
    first = make_view("1", "Northwind", "Remote", datetime(2026, 1, 1, tzinfo=UTC))
    second = make_view("2", "Contoso", "London", datetime(2026, 1, 2, tzinfo=UTC))
    result = filter_queue(
        [first, second],
        QueueFilters(
            search="north",
            companies=frozenset({"Northwind"}),
            sources=frozenset({"manual"}),
            locations=frozenset({"Remote"}),
            discovered_from=datetime(2026, 1, 1, tzinfo=UTC).date(),
            discovered_to=datetime(2026, 1, 1, tzinfo=UTC).date(),
        ),
    )

    assert result == [first]
    assert sort_queue([second, first], "Company A–Z") == [second, first]
