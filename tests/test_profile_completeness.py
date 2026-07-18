"""Tests for candidate-profile completeness checks."""

from app.models.candidate import CandidateProfile, ContactInformation
from app.services.profile_completeness import assess_profile_completeness


def test_sensitive_application_fields_are_never_assumed() -> None:
    """Missing legal and financial fields must require manual input."""
    profile = CandidateProfile(
        full_name="Sample Candidate",
        contact=ContactInformation(
            emails=["candidate@example.com"],
            location="India",
        ),
        source_document="sample_cv.pdf",
    )

    report = assess_profile_completeness(profile)
    missing_paths = {
        field.field_path
        for field in report.missing_fields
    }

    assert report.identity_information_ready is True
    assert report.requires_manual_input is True
    assert "sensitive_information.work_authorization" in missing_paths
    assert "sensitive_information.visa_sponsorship_required" in missing_paths
    assert "sensitive_information.notice_period" in missing_paths
    assert "sensitive_information.salary_expectation" in missing_paths