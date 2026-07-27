"""Tests for private candidate-profile storage."""

import json
from pathlib import Path

from app.models.candidate import CandidateProfile, ContactInformation
from app.services.profile_service import save_candidate_profile


def test_candidate_profile_is_saved_as_valid_json(tmp_path: Path) -> None:
    """A validated profile should be saved as readable JSON."""
    profile = CandidateProfile(
        full_name="Sample Candidate",
        contact=ContactInformation(
            emails=["candidate@example.com"],
            location="India",
        ),
        source_document="sample_cv.pdf",
    )

    output_path = tmp_path / "candidate_profile.json"
    saved_path = save_candidate_profile(profile, output_path)

    stored_data = json.loads(saved_path.read_text(encoding="utf-8"))

    assert saved_path == output_path.resolve()
    assert stored_data["full_name"] == "Sample Candidate"
    assert stored_data["source_document"] == "sample_cv.pdf"
    assert stored_data["sensitive_information"]["salary_expectation"] is None
