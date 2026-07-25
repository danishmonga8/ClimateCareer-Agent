"""Public, read-only job-discovery collectors and utilities."""

from app.discovery.ashby import collect_ashby_jobs
from app.discovery.deduplication import deduplicate_jobs
from app.discovery.filtering import DiscoveryFilter, filter_discovered_jobs
from app.discovery.greenhouse import collect_greenhouse_jobs
from app.discovery.http import JobCollectorError
from app.discovery.lever import LeverRegion, collect_lever_jobs
from app.discovery.pipeline import evaluate_discovered_job, parse_discovered_job
from app.discovery.service import build_discovery_snapshot

__all__ = [
    "DiscoveryFilter",
    "JobCollectorError",
    "LeverRegion",
    "build_discovery_snapshot",
    "collect_ashby_jobs",
    "collect_greenhouse_jobs",
    "collect_lever_jobs",
    "deduplicate_jobs",
    "evaluate_discovered_job",
    "filter_discovered_jobs",
    "parse_discovered_job",
]
