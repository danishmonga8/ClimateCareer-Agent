"""Tests for the candidate-profile models."""

from app.models.candidate import (
    CandidateProfile,
    ContactInformation,
    EducationRecord,
)


def test_candidate_profile_accepts_verified_information() -> None:
    """A valid profile should preserve verified candidate information."""
    profile = CandidateProfile(
        full_name="Sample Candidate",
        contact=ContactInformation(
            emails=["candidate@example.com"],
            location="India",
        ),
        education=[
            EducationRecord(
                degree="PhD",
                field_of_study="Environmental Science",
                institution="Sample University",
                start_year=2023,
                currently_enrolled=True,
            )
        ],
        source_document="master_cv.pdf",
    )

    assert profile.full_name == "Sample Candidate"
    assert profile.education[0].currently_enrolled is True
    assert profile.sensitive_information.salary_expectation is None
    assert profile.sensitive_information.requires_explicit_confirmation is True