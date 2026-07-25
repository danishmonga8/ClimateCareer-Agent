"""Tests for private discovery snapshot storage."""

from pathlib import Path

import pytest

from app.models.discovery import DiscoveredJob, DiscoverySnapshot, JobSource
from app.services.discovery_repository import (
    DiscoveryStorageError,
    load_discovery_snapshot,
    save_discovery_snapshot,
)


def _snapshot() -> DiscoverySnapshot:
    return DiscoverySnapshot(
        jobs=[
            DiscoveredJob(
                source=JobSource.GREENHOUSE,
                source_board="acme",
                source_job_id="123",
                company="Acme Climate",
                title="Climate Scientist",
                job_url="https://example.com/jobs/123",
                description="Analyse climate observations.",
            )
        ]
    )


def test_discovery_snapshot_survives_atomic_round_trip(tmp_path: Path) -> None:
    output_path = tmp_path / "discovered_jobs.json"

    saved_path = save_discovery_snapshot(_snapshot(), output_path)
    loaded = load_discovery_snapshot(saved_path)

    assert saved_path == output_path.resolve()
    assert loaded.jobs[0].source_job_id == "123"
    assert not output_path.with_name("discovered_jobs.json.temporary").exists()


def test_discovery_snapshot_requires_json_path(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryStorageError, match=".json"):
        save_discovery_snapshot(_snapshot(), tmp_path / "jobs.txt")


def test_invalid_discovery_snapshot_is_rejected(tmp_path: Path) -> None:
    input_path = tmp_path / "jobs.json"
    input_path.write_text('{"jobs": [{"title": "incomplete"}]}', encoding="utf-8")

    with pytest.raises(DiscoveryStorageError, match="valid discovery"):
        load_discovery_snapshot(input_path)
