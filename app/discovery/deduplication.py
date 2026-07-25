"""Stable exact and cross-source deduplication for discovered jobs."""

import re
from urllib.parse import urlsplit, urlunsplit

from app.models.discovery import DiscoveredJob

NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def _normalized_key_text(value: str | None) -> str:
    return NON_ALPHANUMERIC.sub(" ", (value or "").casefold()).strip()


def _canonical_url(value: object) -> str:
    parsed = urlsplit(str(value))
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            parsed.path.rstrip("/"),
            "",
            "",
        )
    )


def _source_key(job: DiscoveredJob) -> tuple[str, str, str]:
    return (
        job.source.value,
        job.source_board.casefold(),
        job.source_job_id.casefold(),
    )


def _semantic_key(job: DiscoveredJob) -> tuple[str, str, str]:
    return (
        _normalized_key_text(job.company),
        _normalized_key_text(job.title),
        _normalized_key_text(job.location),
    )


def _quality(job: DiscoveredJob) -> tuple[int, int, float]:
    populated_fields = sum(
        value is not None
        for value in (
            job.apply_url,
            job.location,
            job.department,
            job.team,
            job.salary_text,
            job.date_posted,
            job.date_updated,
        )
    )
    timestamp = job.date_updated or job.date_posted or job.discovered_at
    return populated_fields, len(job.description), timestamp.timestamp()


def _is_duplicate(left: DiscoveredJob, right: DiscoveredJob) -> bool:
    return (
        _source_key(left) == _source_key(right)
        or _canonical_url(left.job_url) == _canonical_url(right.job_url)
        or _semantic_key(left) == _semantic_key(right)
    )


def deduplicate_jobs(jobs: list[DiscoveredJob]) -> list[DiscoveredJob]:
    """Remove duplicates while retaining the richest record in stable order."""
    retained: list[DiscoveredJob] = []

    for job in jobs:
        matching_indices = [
            index for index, existing in enumerate(retained) if _is_duplicate(existing, job)
        ]
        if not matching_indices:
            retained.append(job)
            continue

        first_index = matching_indices[0]
        candidates = [retained[index] for index in matching_indices]
        candidates.append(job)
        retained[first_index] = max(candidates, key=_quality)

        for duplicate_index in reversed(matching_indices[1:]):
            del retained[duplicate_index]

    return retained
