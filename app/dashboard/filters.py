"""Pure, deterministic filtering and sorting for the review queue."""

from dataclasses import dataclass, field
from datetime import date

from app.dashboard.data_loader import DashboardJobView
from app.models.dashboard_review import DashboardReviewStatus


@dataclass(frozen=True)
class QueueFilters:
    """Optional review-queue constraints supplied by the dashboard."""

    search: str = ""
    statuses: frozenset[DashboardReviewStatus] = field(default_factory=frozenset)
    minimum_score: float | None = None
    maximum_score: float | None = None
    companies: frozenset[str] = field(default_factory=frozenset)
    sources: frozenset[str] = field(default_factory=frozenset)
    locations: frozenset[str] = field(default_factory=frozenset)
    discovered_from: date | None = None
    discovered_to: date | None = None


def _score(view: DashboardJobView) -> float | None:
    return view.score.overall_score if view.score else None


def filter_queue(
    views: tuple[DashboardJobView, ...] | list[DashboardJobView],
    filters: QueueFilters,
) -> list[DashboardJobView]:
    """Filter jobs locally without modifying source artifacts."""
    search = filters.search.casefold().strip()
    results: list[DashboardJobView] = []
    for view in views:
        job = view.job
        if filters.statuses and view.record.status not in filters.statuses:
            continue
        if job is None:
            if search or filters.companies or filters.sources or filters.locations:
                continue
            results.append(view)
            continue
        score = _score(view)
        if filters.minimum_score is not None and (score is None or score < filters.minimum_score):
            continue
        if filters.maximum_score is not None and (score is None or score > filters.maximum_score):
            continue
        if filters.companies and job.company not in filters.companies:
            continue
        if filters.sources and job.source.value not in filters.sources:
            continue
        if filters.locations and (job.location or "Unspecified") not in filters.locations:
            continue
        discovered_date = job.discovered_at.date()
        if filters.discovered_from and discovered_date < filters.discovered_from:
            continue
        if filters.discovered_to and discovered_date > filters.discovered_to:
            continue
        searchable = " ".join(
            [job.title, job.company, job.location or "", job.source.value]
        ).casefold()
        if search and search not in searchable:
            continue
        results.append(view)
    return results


def sort_queue(views: list[DashboardJobView], sort_by: str) -> list[DashboardJobView]:
    """Return a deterministic queue order with missing scores last."""
    if sort_by == "Oldest discovered":
        return sorted(
            views,
            key=lambda view: (
                view.job is None,
                view.job.discovered_at if view.job else date.max,
                view.record.job_key,
            ),
        )
    if sort_by == "Company A–Z":
        return sorted(
            views,
            key=lambda view: (
                view.job is None,
                view.job.company.casefold() if view.job else "",
                view.record.job_key,
            ),
        )
    return sorted(
        views,
        key=lambda view: (
            _score(view) is None,
            -(_score(view) or 0),
            view.job.company.casefold() if view.job else "",
            view.record.job_key,
        ),
    )
