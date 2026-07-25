"""Read-only collector for Ashby public Job Postings API listings."""

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
    source_id_from_url,
)
from app.models.discovery import DiscoveredJob, JobSource

ASHBY_JOBS_URL = "https://api.ashbyhq.com/posting-api/job-board/{board}"


def collect_ashby_jobs(
    board_name: str,
    company: str,
    *,
    include_compensation: bool = True,
    client: httpx.Client | None = None,
) -> list[DiscoveredJob]:
    """Collect and normalize listed jobs from one public Ashby board."""
    board = validate_board_identifier(board_name, "Ashby board name")
    company_name = normalize_text(company)
    if not company_name:
        raise JobCollectorError("Ashby company name cannot be blank.")

    payload = get_public_json(
        ASHBY_JOBS_URL.format(board=board),
        params={"includeCompensation": str(include_compensation).lower()},
        client=client,
    )
    raw_jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(raw_jobs, list):
        raise JobCollectorError("Ashby returned an invalid jobs payload.")

    jobs: list[DiscoveredJob] = []
    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            raise JobCollectorError("Ashby returned an invalid job record.")
        if raw_job.get("isListed") is False:
            continue

        job_url = normalize_text(raw_job.get("jobUrl"))
        source_job_id = source_id_from_url(job_url)
        location = normalize_optional_text(raw_job.get("location"))
        compensation = raw_job.get("compensation")
        salary = None
        if isinstance(compensation, dict):
            salary = normalize_optional_text(
                compensation.get("scrapeableCompensationSalarySummary")
                or compensation.get("compensationTierSummary")
            )

        try:
            jobs.append(
                DiscoveredJob(
                    source=JobSource.ASHBY,
                    source_board=board,
                    source_job_id=source_job_id,
                    company=company_name,
                    title=normalize_text(raw_job.get("title")),
                    job_url=job_url,
                    apply_url=normalize_optional_text(raw_job.get("applyUrl")),
                    location=location,
                    work_arrangement=normalize_work_arrangement(
                        raw_job.get("workplaceType"),
                        location=location,
                        remote_hint=(
                            raw_job.get("isRemote")
                            if isinstance(raw_job.get("isRemote"), bool)
                            else None
                        ),
                    ),
                    employment_type=normalize_employment_type(raw_job.get("employmentType")),
                    department=normalize_optional_text(raw_job.get("department")),
                    team=normalize_optional_text(raw_job.get("team")),
                    description=normalize_text(
                        raw_job.get("descriptionPlain") or raw_job.get("descriptionHtml")
                    ),
                    salary_text=salary,
                    date_posted=parse_datetime(raw_job.get("publishedAt")),
                    metadata={"api_version": payload.get("apiVersion")},
                )
            )
        except (TypeError, ValueError) as error:
            raise JobCollectorError(
                f"Ashby job {source_job_id or '<unknown>'} is invalid."
            ) from error

    return jobs
