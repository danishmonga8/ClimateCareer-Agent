"""Tests for the Candidate Profile Agent."""

from unittest.mock import Mock

from app.agents.candidate_agent import (
    CandidateExtractionResult,
    ExtractedProfessionalLink,
    extract_candidate_profile,
)
from app.core.settings import Settings
from app.models.candidate import ContactInformation


def test_candidate_agent_uses_structured_output_without_api_call(
    monkeypatch,
) -> None:
    """The agent should convert structured output into a safe profile."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")
    settings = Settings(_env_file=None)

    extracted = CandidateExtractionResult(
        full_name="Sample Candidate",
        professional_headline="Environmental Data Scientist",
        contact=ContactInformation(
            emails=["candidate@example.com"],
            location="India",
        ),
        links=[
            ExtractedProfessionalLink(
                label="LinkedIn",
                url="https://www.linkedin.com/in/sample-candidate/",
            )
        ],
        languages=["English"],
    )

    mock_client = Mock()
    mock_client.responses.parse.return_value.output_parsed = extracted

    profile = extract_candidate_profile(
        "Sample Candidate CV with environmental data science experience.",
        "sample_cv.pdf",
        client=mock_client,
        settings=settings,
    )

    assert profile.full_name == "Sample Candidate"
    assert profile.source_document == "sample_cv.pdf"
    assert str(profile.links[0].url).startswith("https://www.linkedin.com/")
    assert profile.sensitive_information.work_authorization is None
    assert profile.sensitive_information.salary_expectation is None

    call_arguments = mock_client.responses.parse.call_args.kwargs
    assert call_arguments["model"] == "gpt-5.6-luna"
    assert call_arguments["text_format"] is CandidateExtractionResult