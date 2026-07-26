"""Regression tests for sanitized local CLI and repository boundaries."""

import logging
from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock

import pytest

import job_cli
import main as application_cli
import personalization_cli
import report_cli
from app.services.cv_parser import DocumentParsingError, parse_cv
from app.services.discovery_repository import load_discovery_snapshot
from app.services.document_service import validate_document
from app.services.evidence_repository import load_evidence_bank
from app.services.job_repository import load_job_description
from app.services.personalization_repository import load_personalized_application
from app.services.profile_service import load_candidate_profile
from app.services.scoring_repository import ScoringStorageError, load_scoring_result


@pytest.mark.parametrize(
    "loader",
    [
        load_candidate_profile,
        load_evidence_bank,
        load_job_description,
        load_scoring_result,
        load_personalized_application,
        load_discovery_snapshot,
    ],
)
def test_private_artifact_load_failures_hide_paths(
    tmp_path: Path,
    loader: Callable[[Path], object],
) -> None:
    """Storage errors must not expose private filesystem locations."""
    missing = tmp_path / "private_candidate_material.json"

    with pytest.raises(ValueError) as error:
        loader(missing)

    assert str(missing) not in str(error.value)
    assert missing.name not in str(error.value)


def test_document_validation_failure_hides_private_path(tmp_path: Path) -> None:
    """Document validation reports a recovery-safe error rather than a path."""
    missing = tmp_path / "candidate_cv.pdf"

    with pytest.raises(ValueError) as error:
        validate_document(missing)

    assert str(missing) not in str(error.value)
    assert missing.name not in str(error.value)


def test_cv_parser_failure_hides_private_filename(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A parser implementation failure must not echo the CV filename."""
    candidate_cv = tmp_path / "confidential_candidate_resume.pdf"
    candidate_cv.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        "app.services.cv_parser.fitz.open",
        Mock(side_effect=RuntimeError("private parser detail")),
    )

    with pytest.raises(DocumentParsingError) as error:
        parse_cv(candidate_cv)

    assert candidate_cv.name not in str(error.value)
    assert "private parser detail" not in str(error.value)


def test_cli_failures_hide_private_paths(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Supported command boundaries must not echo private input locations."""
    missing_job = tmp_path / "confidential_job.txt"
    missing_cv = tmp_path / "candidate_cv.pdf"
    missing_questions = tmp_path / "private_questions.json"

    with caplog.at_level(logging.INFO):
        assert job_cli.main(["--file", str(missing_job), "--url", "https://example.test/job"]) == 1
        assert application_cli.main(["--cv", str(missing_cv)]) == 1

    with pytest.raises(personalization_cli.PersonalizationInputError) as error:
        personalization_cli._load_application_questions(missing_questions)

    assert str(missing_job) not in caplog.text
    assert str(missing_cv) not in caplog.text
    assert str(missing_questions) not in str(error.value)


def test_report_cli_hides_unexpected_storage_detail(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Recommendation-report recovery must not echo a private storage error."""
    private_detail = "private-storage-detail-should-not-appear"
    monkeypatch.setattr(
        report_cli,
        "load_scoring_result",
        Mock(side_effect=ScoringStorageError(private_detail)),
    )

    with caplog.at_level(logging.INFO):
        assert report_cli.main([]) == 1

    assert private_detail not in caplog.text
    assert "Unable to generate recommendation report" in caplog.text
