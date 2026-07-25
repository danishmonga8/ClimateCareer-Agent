"""Read-only collector for Greenhouse public Job Board API listings."""

from typing import Any

import httpx

from app.discovery.http import (
    JobCollectorError,
    get_public_json,
    validate_board_identifier,
)
from app.discovery.normalization import (
    normalize_employment_type,
    normalize_optional_text,
    normalize_text,
    normalize_work_arrangement,
    parse_datetime,
)
from app.models.discovery import DiscoveredJob, JobSource

GREENHOUSE_JOBS_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


def _department_name(payload: dict[str, Any]) -> str | None:
    departments = payload.get("departments")
    if not isinstance(departments, list):
        return None
    for department in departments:
        if isinstance(department, dict):
            name = normalize_optional_text(department.get("name"))
            if name:
                return name
    return None


def collect_greenhouse_jobs(
    board_token: str,
    company: str,
    *,
    client: httpx.Client | None = None,
) -> list[DiscoveredJob]:
    """Collect and normalize all published jobs on one public board."""
    board = validate_board_identifier(board_token, "Greenhouse board token")
    company_name = normalize_text(company)
    if not company_name:
        raise JobCollectorError("Greenhouse company name cannot be blank.")

    payload = get_public_json(
        GREENHOUSE_JOBS_URL.format(board=board),
        params={"content": "true"},
        client=client,
    )
    raw_jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(raw_jobs, list):
        raise JobCollectorError("Greenhouse returned an invalid jobs payload.")

    jobs: list[DiscoveredJob] = []
    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            raise JobCollectorError("Greenhouse returned an invalid job record.")

        location_payload = raw_job.get("location")
        location = (
            normalize_optional_text(location_payload.get("name"))
            if isinstance(location_payload, dict)
            else None
        )
        source_job_id = normalize_text(raw_job.get("id"))

        try:
            jobs.append(
                DiscoveredJob(
                    source=JobSource.GREENHOUSE,
                    source_board=board,
                    source_job_id=source_job_id,
                    company=company_name,
                    title=normalize_text(raw_job.get("title")),
                    job_url=normalize_text(raw_job.get("absolute_url")),
                    location=location,
                    work_arrangement=normalize_work_arrangement(None, location=location),
                    employment_type=normalize_employment_type(raw_job.get("employment_type")),
                    department=_department_name(raw_job),
                    description=normalize_text(raw_job.get("content")),
                    date_updated=parse_datetime(raw_job.get("updated_at")),
                    metadata={
                        "internal_job_id": raw_job.get("internal_job_id"),
                        "requisition_id": raw_job.get("requisition_id"),
                        "language": raw_job.get("language"),
                    },
                )
            )
        except (TypeError, ValueError) as error:
            raise JobCollectorError(
                f"Greenhouse job {source_job_id or '<unknown>'} is invalid."
            ) from error

    return jobs
