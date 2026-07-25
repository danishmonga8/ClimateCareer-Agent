"""Application service for building normalized discovery snapshots."""

from collections.abc import Iterable

from app.discovery.deduplication import deduplicate_jobs
from app.discovery.filtering import DiscoveryFilter, filter_discovered_jobs
from app.models.discovery import DiscoveredJob, DiscoverySnapshot


def build_discovery_snapshot(
    job_batches: Iterable[Iterable[DiscoveredJob]],
    *,
    criteria: DiscoveryFilter | None = None,
) -> DiscoverySnapshot:
    """Flatten, filter, and deduplicate public collector results."""
    jobs = [job for batch in job_batches for job in batch]
    if criteria is not None:
        jobs = filter_discovered_jobs(jobs, criteria)
    return DiscoverySnapshot(jobs=deduplicate_jobs(jobs))
