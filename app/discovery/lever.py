"""Read-only collector for Lever public Postings API listings."""

from enum import StrEnum
from typing import Any

import httpx

from app.discovery.http import JobCollectorError, get_public_json, validate_board_identifier
from app.discovery.normalization import (
    normalize_employment_type,
    normalize_optional_text,
    normalize_salary,
    normalize_text,
    normalize_work_arrangement,
    parse_unix_milliseconds,
)
from app.models.discovery import DiscoveredJob, JobSource


class LeverRegion(StrEnum):
    """Supported public Lever Postings API regions."""

    GLOBAL = "global"
    EU = "eu"


LEVER_BASE_URLS = {
    LeverRegion.GLOBAL: "https://api.lever.co/v0/postings/{site}",
    LeverRegion.EU: "https://api.eu.lever.co/v0/postings/{site}",
}


def _description(payload: dict[str, Any]) -> str:
    direct = normalize_text(payload.get("descriptionPlain"))
    if direct:
        return direct

    sections = [normalize_text(payload.get("openingPlain"))]
    lists = payload.get("lists")
    if isinstance(lists, list):
        for item in lists:
            if isinstance(item, dict):
                sections.extend(
                    [normalize_text(item.get("text")), normalize_text(item.get("content"))]
                )
    sections.append(normalize_text(payload.get("additionalPlain")))
    return "\n".join(section for section in sections if section)


def collect_lever_jobs(
    site: str,
    company: str,
    *,
    region: LeverRegion | str = LeverRegion.GLOBAL,
    client: httpx.Client | None = None,
) -> list[DiscoveredJob]:
    """Collect and normalize published jobs from one Lever site."""
    board = validate_board_identifier(site, "Lever site")
    company_name = normalize_text(company)
    if not company_name:
        raise JobCollectorError("Lever company name cannot be blank.")

    try:
        selected_region = LeverRegion(region)
    except ValueError as error:
        raise JobCollectorError(f"Unsupported Lever region: {region!r}") from error

    payload = get_public_json(
        LEVER_BASE_URLS[selected_region].format(site=board),
        params={"mode": "json"},
        client=client,
    )
    if not isinstance(payload, list):
        raise JobCollectorError("Lever returned an invalid jobs payload.")

    jobs: list[DiscoveredJob] = []
    for raw_job in payload:
        if not isinstance(raw_job, dict):
            raise JobCollectorError("Lever returned an invalid job record.")

        categories = raw_job.get("categories")
        categories = categories if isinstance(categories, dict) else {}
        location = normalize_optional_text(categories.get("location"))
        source_job_id = normalize_text(raw_job.get("id"))
        salary = normalize_optional_text(raw_job.get("salaryDescriptionPlain"))
        if not salary:
            salary = normalize_salary(raw_job.get("salaryRange"))

        try:
            jobs.append(
                DiscoveredJob(
                    source=JobSource.LEVER,
                    source_board=board,
                    source_job_id=source_job_id,
                    company=company_name,
                    title=normalize_text(raw_job.get("text")),
                    job_url=normalize_text(raw_job.get("hostedUrl")),
                    apply_url=normalize_optional_text(raw_job.get("applyUrl")),
                    location=location,
                    work_arrangement=normalize_work_arrangement(
                        raw_job.get("workplaceType"), location=location
                    ),
                    employment_type=normalize_employment_type(categories.get("commitment")),
                    department=normalize_optional_text(categories.get("department")),
                    team=normalize_optional_text(categories.get("team")),
                    description=_description(raw_job),
                    salary_text=salary,
                    date_posted=parse_unix_milliseconds(raw_job.get("createdAt")),
                    metadata={"country": raw_job.get("country")},
                )
            )
        except (TypeError, ValueError) as error:
            raise JobCollectorError(
                f"Lever job {source_job_id or '<unknown>'} is invalid."
            ) from error

    return jobs
