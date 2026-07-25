"""Tests for the personalization command-line interface."""

import json
from unittest.mock import Mock

import personalization_cli
from app.agents.personalization_agent import PersonalizationError
from app.models.personalization import (
    PersonalizedApplication,
    TailoredCoverLetter,
    TailoredResume,
)


def make_application() -> PersonalizedApplication:
    """Create a minimal valid personalized application draft."""
    return PersonalizedApplication(
        candidate_name="Sample Candidate",
        job_title="Environmental Data Scientist",
        employer="Example Climate Company",
        job_url="https://example.com/jobs/123",
        resume=TailoredResume(
            professional_headline="Environmental Data Scientist",
        ),
        cover_letter=TailoredCoverLetter(
            body=(
                "I am applying for the Environmental Data "
                "Scientist position."
            ),
        ),
    )


def test_personalization_cli_saves_application(
    tmp_path,
    monkeypatch,
) -> None:
    """The CLI should load inputs, personalize, and save the draft."""
    profile = object()
    evidence_bank = object()
    job = object()
    application = make_application()

    profile_path = tmp_path / "profile.json"
    evidence_path = tmp_path / "evidence.json"
    job_path = tmp_path / "job.json"
    questions_path = tmp_path / "questions.json"
    output_path = tmp_path / "personalized_application.json"

    questions_path.write_text(
        json.dumps(
            [
                "Describe your relevant modelling experience.",
                "What is your expected salary?",
            ]
        ),
        encoding="utf-8",
    )

    load_profile = Mock(return_value=profile)
    load_evidence = Mock(return_value=evidence_bank)
    load_job = Mock(return_value=job)
    personalize = Mock(return_value=application)
    save_application = Mock(
        return_value=output_path.resolve()
    )

    monkeypatch.setattr(
        personalization_cli,
        "load_candidate_profile",
        load_profile,
    )
    monkeypatch.setattr(
        personalization_cli,
        "load_evidence_bank",
        load_evidence,
    )
    monkeypatch.setattr(
        personalization_cli,
        "load_job_description",
        load_job,
    )
    monkeypatch.setattr(
        personalization_cli,
        "personalize_application",
        personalize,
    )
    monkeypatch.setattr(
        personalization_cli,
        "save_personalized_application",
        save_application,
    )

    result = personalization_cli.main(
        [
            "--profile",
            str(profile_path),
            "--evidence",
            str(evidence_path),
            "--job",
            str(job_path),
            "--questions",
            str(questions_path),
            "--output",
            str(output_path),
        ]
    )

    assert result == 0
    load_profile.assert_called_once_with(profile_path)
    load_evidence.assert_called_once_with(evidence_path)
    load_job.assert_called_once_with(job_path)
    personalize.assert_called_once_with(
        profile=profile,
        evidence_bank=evidence_bank,
        job=job,
        application_questions=[
            "Describe your relevant modelling experience.",
            "What is your expected salary?",
        ],
    )
    save_application.assert_called_once_with(
        application,
        output_path,
    )


def test_invalid_question_file_is_rejected(
    tmp_path,
    monkeypatch,
) -> None:
    """The CLI must reject questions not supplied as an array."""
    questions_path = tmp_path / "questions.json"
    questions_path.write_text(
        '{"question": "Why do you want this role?"}',
        encoding="utf-8",
    )

    personalize = Mock()
    monkeypatch.setattr(
        personalization_cli,
        "personalize_application",
        personalize,
    )

    result = personalization_cli.main(
        ["--questions", str(questions_path)]
    )

    assert result == 1
    personalize.assert_not_called()


def test_personalization_failure_returns_nonzero(
    monkeypatch,
) -> None:
    """A safe personalization failure should return exit code one."""
    monkeypatch.setattr(
        personalization_cli,
        "load_candidate_profile",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        personalization_cli,
        "load_evidence_bank",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        personalization_cli,
        "load_job_description",
        Mock(return_value=object()),
    )

    personalize = Mock(
        side_effect=PersonalizationError(
            "Candidate information does not match."
        )
    )
    save_application = Mock()

    monkeypatch.setattr(
        personalization_cli,
        "personalize_application",
        personalize,
    )
    monkeypatch.setattr(
        personalization_cli,
        "save_personalized_application",
        save_application,
    )

    result = personalization_cli.main([])

    assert result == 1
    save_application.assert_not_called()