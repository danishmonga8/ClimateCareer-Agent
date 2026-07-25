"""Transparent local filtering for normalized discovered jobs."""

import re
from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.models.candidate import StrictModel
from app.models.discovery import DiscoveredJob
from app.models.job import EmploymentType, WorkArrangement

NON_ALPHANUMERIC = re.compile(r"[^\w]+", flags=re.UNICODE)


def _normalized_search_text(value: str) -> str:
    return " ".join(NON_ALPHANUMERIC.sub(" ", value.casefold()).split())


def _contains_term(text: str, term: str) -> bool:
    """Match a normalized word or phrase without partial-word collisions."""
    return f" {term} " in f" {text.replace(chr(10), ' ')} "


class DiscoveryFilter(StrictModel):
    """User-controlled criteria for selecting discovered jobs."""

    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    work_arrangements: list[WorkArrangement] = Field(default_factory=list)
    employment_types: list[EmploymentType] = Field(default_factory=list)
    posted_since: datetime | None = None
    require_all_keywords: bool = False
    include_jobs_without_posted_date: bool = True

    @field_validator("include_keywords", "exclude_keywords", "locations")
    @classmethod
    def clean_terms(cls, values: list[str]) -> list[str]:
        """Remove blank filters and normalize surrounding whitespace."""
        return [cleaned for value in values if (cleaned := " ".join(value.split()))]

    @model_validator(mode="after")
    def validate_posted_since(self) -> "DiscoveryFilter":
        """Require timezone-aware cutoffs for unambiguous comparisons."""
        if self.posted_since is not None and self.posted_since.tzinfo is None:
            raise ValueError("posted_since must include a timezone.")
        return self


def _searchable_text(job: DiscoveredJob) -> str:
    values = (
        job.company,
        job.title,
        job.location,
        job.department,
        job.team,
        job.description,
    )
    return "\n".join(_normalized_search_text(value) for value in values if value)


def _matches_filter(job: DiscoveredJob, criteria: DiscoveryFilter) -> bool:
    searchable = _searchable_text(job)
    include_terms = [_normalized_search_text(term) for term in criteria.include_keywords]
    exclude_terms = [_normalized_search_text(term) for term in criteria.exclude_keywords]

    if include_terms:
        matches = [_contains_term(searchable, term) for term in include_terms]
        if criteria.require_all_keywords and not all(matches):
            return False
        if not criteria.require_all_keywords and not any(matches):
            return False

    if any(_contains_term(searchable, term) for term in exclude_terms):
        return False

    if criteria.locations:
        location = _normalized_search_text(job.location or "")
        if not any(
            _contains_term(location, _normalized_search_text(term)) for term in criteria.locations
        ):
            return False

    if criteria.work_arrangements and job.work_arrangement not in criteria.work_arrangements:
        return False

    if criteria.employment_types and job.employment_type not in criteria.employment_types:
        return False

    if criteria.posted_since is not None:
        if job.date_posted is None:
            return criteria.include_jobs_without_posted_date
        if job.date_posted < criteria.posted_since:
            return False

    return True


def filter_discovered_jobs(
    jobs: list[DiscoveredJob],
    criteria: DiscoveryFilter,
) -> list[DiscoveredJob]:
    """Return matching jobs in their original discovery order."""
    return [job for job in jobs if _matches_filter(job, criteria)]
