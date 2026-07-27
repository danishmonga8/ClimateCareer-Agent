"""Tests for the Phase 1 command-line interface."""

import json
from pathlib import Path

import fitz

from app.models.candidate import (
    CandidateProfile,
    ContactInformation,
    SkillCategory,
    SkillRecord,
)
from app.services.profile_service import save_candidate_profile
from main import main


def _create_test_pdf(path: Path, text: str) -> None:
    """Create a searchable PDF for CLI tests."""
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), text)
        pdf.save(path)


def test_cli_processes_valid_cv(tmp_path: Path) -> None:
    """The CLI should successfully process a readable PDF CV."""
    cv_path = tmp_path / "candidate_cv.pdf"
    _create_test_pdf(
        cv_path,
        "Candidate CV with Python experience",
    )

    exit_code = main(["--cv", str(cv_path)])

    assert exit_code == 0


def test_cli_builds_evidence_without_api_call(tmp_path: Path) -> None:
    """The CLI should build evidence from an existing private profile."""
    cv_path = tmp_path / "candidate_cv.pdf"
    profile_path = tmp_path / "candidate_profile.json"
    evidence_path = tmp_path / "evidence_bank.json"

    _create_test_pdf(
        cv_path,
        "CORE TECHNICAL SKILLS\nPython and environmental analytics",
    )

    profile = CandidateProfile(
        full_name="Sample Candidate",
        contact=ContactInformation(
            emails=["candidate@example.com"],
        ),
        skills=[
            SkillRecord(
                name="Python",
                category=SkillCategory.PROGRAMMING,
            )
        ],
        source_document="candidate_cv.pdf",
    )
    save_candidate_profile(profile, profile_path)

    exit_code = main(
        [
            "--cv",
            str(cv_path),
            "--build-evidence",
            "--output",
            str(profile_path),
            "--evidence-output",
            str(evidence_path),
        ]
    )

    stored_evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert len(stored_evidence["records"]) == 1
    assert stored_evidence["records"][0]["status"] == "verified"
