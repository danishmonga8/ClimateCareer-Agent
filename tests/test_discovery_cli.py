"""Tests for the read-only discovery command-line interface."""

from pathlib import Path

import discovery_cli
from app.models.discovery import DiscoveredJob, JobSource


def _job() -> DiscoveredJob:
    return DiscoveredJob(
        source=JobSource.GREENHOUSE,
        source_board="acme",
        source_job_id="1",
        company="Acme Climate",
        title="Climate Scientist",
        job_url="https://example.com/jobs/1",
        description="Analyse climate data.",
    )


def test_discovery_cli_collects_filters_and_saves(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    output_path = tmp_path / "jobs.json"
    calls: list[tuple[str, str]] = []

    def fake_collector(board: str, company: str):  # type: ignore[no-untyped-def]
        calls.append((board, company))
        return [_job()]

    monkeypatch.setattr(discovery_cli, "collect_greenhouse_jobs", fake_collector)

    result = discovery_cli.main(
        [
            "--company",
            "Acme Climate",
            "--output",
            str(output_path),
            "--include",
            "climate",
            "greenhouse",
            "--board",
            "acme",
        ]
    )

    assert result == 0
    assert calls == [("acme", "Acme Climate")]
    assert output_path.is_file()


def test_discovery_cli_returns_nonzero_for_collector_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.discovery.http import JobCollectorError

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise JobCollectorError("Public board unavailable")

    monkeypatch.setattr(discovery_cli, "collect_ashby_jobs", fail)

    result = discovery_cli.main(["--company", "Acme Climate", "ashby", "--board", "acme"])

    assert result == 1
