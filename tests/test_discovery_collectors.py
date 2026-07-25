"""Tests for read-only public ATS collectors."""

import httpx
import pytest

from app.discovery.ashby import collect_ashby_jobs
from app.discovery.greenhouse import collect_greenhouse_jobs
from app.discovery.http import JobCollectorError
from app.discovery.lever import LeverRegion, collect_lever_jobs
from app.models.discovery import JobSource
from app.models.job import EmploymentType, WorkArrangement


def _client(payload: object, requests: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_greenhouse_collector_uses_public_get_and_normalizes_html() -> None:
    requests: list[httpx.Request] = []
    payload = {
        "jobs": [
            {
                "id": 123,
                "internal_job_id": 456,
                "title": " Climate Scientist ",
                "updated_at": "2026-07-20T12:00:00Z",
                "location": {"name": "Remote"},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
                "content": "&lt;p&gt;Model &amp;amp; analyse climate data.&lt;/p&gt;",
                "departments": [{"name": "Science"}],
            }
        ]
    }

    with _client(payload, requests) as client:
        jobs = collect_greenhouse_jobs("acme", "Acme Climate", client=client)

    assert len(jobs) == 1
    assert jobs[0].source == JobSource.GREENHOUSE
    assert jobs[0].source_job_id == "123"
    assert jobs[0].description == "Model & analyse climate data."
    assert jobs[0].department == "Science"
    assert jobs[0].work_arrangement == WorkArrangement.REMOTE
    assert requests[0].method == "GET"
    assert requests[0].url.params["content"] == "true"
    assert "authorization" not in requests[0].headers


def test_lever_collector_supports_eu_and_normalizes_categories() -> None:
    requests: list[httpx.Request] = []
    payload = [
        {
            "id": "lever-1",
            "text": "Environmental Data Scientist",
            "categories": {
                "location": "Berlin, Germany",
                "commitment": "Full-time",
                "department": "Research",
                "team": "Climate AI",
            },
            "descriptionPlain": "Analyse environmental datasets.",
            "hostedUrl": "https://jobs.eu.lever.co/acme/lever-1",
            "applyUrl": "https://jobs.eu.lever.co/acme/lever-1/apply",
            "workplaceType": "hybrid",
            "createdAt": 1784548800000,
            "salaryRange": {
                "currency": "EUR",
                "interval": "year",
                "min": 70000,
                "max": 90000,
            },
        }
    ]

    with _client(payload, requests) as client:
        jobs = collect_lever_jobs(
            "acme",
            "Acme Climate",
            region=LeverRegion.EU,
            client=client,
        )

    assert jobs[0].employment_type == EmploymentType.FULL_TIME
    assert jobs[0].work_arrangement == WorkArrangement.HYBRID
    assert jobs[0].salary_text == "EUR 70000 - 90000 year"
    assert jobs[0].date_posted is not None
    assert jobs[0].date_posted.isoformat() == "2026-07-20T12:00:00+00:00"
    assert requests[0].url.host == "api.eu.lever.co"
    assert requests[0].url.params["mode"] == "json"


def test_ashby_collector_excludes_unlisted_jobs() -> None:
    requests: list[httpx.Request] = []
    listed = {
        "title": "Carbon Analyst",
        "location": "Remote",
        "isListed": True,
        "isRemote": True,
        "workplaceType": "Remote",
        "descriptionPlain": "Measure organizational emissions.",
        "publishedAt": "2026-07-21T10:30:00+00:00",
        "employmentType": "FullTime",
        "jobUrl": "https://jobs.ashbyhq.com/acme/carbon-analyst",
        "applyUrl": "https://jobs.ashbyhq.com/acme/carbon-analyst/application",
        "compensation": {"scrapeableCompensationSalarySummary": "$80K - $100K"},
    }
    unlisted = {**listed, "title": "Hidden role", "isListed": False}

    with _client({"apiVersion": "1", "jobs": [listed, unlisted]}, requests) as client:
        jobs = collect_ashby_jobs("acme", "Acme Climate", client=client)

    assert [job.title for job in jobs] == ["Carbon Analyst"]
    assert jobs[0].source_job_id == "carbon-analyst"
    assert jobs[0].salary_text == "$80K - $100K"
    assert requests[0].url.params["includeCompensation"] == "true"


def test_collector_rejects_path_traversal_before_request() -> None:
    with pytest.raises(JobCollectorError, match="Invalid Greenhouse"):
        collect_greenhouse_jobs("../private", "Acme Climate")


def test_collector_wraps_http_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(JobCollectorError, match="Unable to collect"),
    ):
        collect_lever_jobs("acme", "Acme Climate", client=client)


def test_lever_collector_rejects_unknown_region_before_request() -> None:
    with pytest.raises(JobCollectorError, match="Unsupported Lever region"):
        collect_lever_jobs("acme", "Acme Climate", region="unknown")
