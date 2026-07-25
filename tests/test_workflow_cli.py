"""Tests for the unified workflow CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import workflow_cli


def test_parser_requires_job_url() -> None:
    """The job URL must be supplied."""
    parser = workflow_cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--cv",
                "candidate.pdf",
                "--job-file",
                "job_description.txt",
            ]
        )


def test_require_file_rejects_missing_file(
    tmp_path: Path,
) -> None:
    """A missing required input must stop the workflow."""
    missing_file = tmp_path / "missing.pdf"

    with pytest.raises(
        workflow_cli.WorkflowError,
        match="Candidate CV was not found",
    ):
        workflow_cli.require_file(
            missing_file,
            "Candidate CV",
        )


def test_run_step_rejects_failed_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A nonzero subprocess result must stop the workflow."""

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        check: bool,
    ) -> argparse.Namespace:
        del command, cwd, check
        return argparse.Namespace(returncode=7)

    monkeypatch.setattr(
        workflow_cli.subprocess,
        "run",
        fake_run,
    )

    with pytest.raises(
        workflow_cli.WorkflowError,
        match="Example step failed with exit code 7",
    ):
        workflow_cli.run_step(
            "Example step",
            ["example_cli.py"],
        )


def test_complete_workflow_runs_phase_one_stages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The default workflow must retain all four Phase 1 stages."""
    cv_path = tmp_path / "candidate.pdf"
    job_path = tmp_path / "job_description.txt"
    private_dir = tmp_path / "documents" / "private"

    cv_path.write_bytes(b"example CV")
    job_path.write_text(
        "Example job description",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        workflow_cli,
        "PRIVATE_DIR",
        private_dir,
    )

    recorded_steps: list[tuple[str, list[str]]] = []

    def fake_run_step(
        step_name: str,
        command: list[str],
    ) -> None:
        recorded_steps.append((step_name, command))
        private_dir.mkdir(parents=True, exist_ok=True)

        if step_name == "Candidate profile and evidence generation":
            (private_dir / "candidate_profile.json").write_text(
                "{}",
                encoding="utf-8",
            )
            (private_dir / "evidence_bank.json").write_text(
                "{}",
                encoding="utf-8",
            )
        elif step_name == "Job-description parsing":
            (private_dir / "structured_job.json").write_text(
                "{}",
                encoding="utf-8",
            )
        elif step_name == "Candidate-job relevance scoring":
            (private_dir / "scoring_result.json").write_text(
                "{}",
                encoding="utf-8",
            )
        elif step_name == "Recommendation-report generation":
            (private_dir / "recommendation_report.md").write_text(
                "# Recommendation",
                encoding="utf-8",
            )

    monkeypatch.setattr(
        workflow_cli,
        "run_step",
        fake_run_step,
    )

    args = argparse.Namespace(
        cv=cv_path,
        job_file=job_path,
        job_url="https://example.com/jobs/123",
        pure_ai_role=True,
        personalize=False,
        questions=None,
    )

    workflow_cli.run_workflow(args)

    assert len(recorded_steps) == 4
    assert recorded_steps[0][0] == (
        "Candidate profile and evidence generation"
    )
    assert recorded_steps[1][0] == "Job-description parsing"
    assert recorded_steps[2][0] == (
        "Candidate-job relevance scoring"
    )
    assert recorded_steps[3][0] == (
        "Recommendation-report generation"
    )
    assert args.job_url in recorded_steps[1][1]
    assert "--pure-ai-role" in recorded_steps[2][1]


def test_personalization_runs_as_optional_fifth_stage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Personalization must run only when explicitly requested."""
    cv_path = tmp_path / "candidate.pdf"
    job_path = tmp_path / "job_description.txt"
    questions_path = tmp_path / "questions.json"
    private_dir = tmp_path / "documents" / "private"

    cv_path.write_bytes(b"example CV")
    job_path.write_text(
        "Example job description",
        encoding="utf-8",
    )
    questions_path.write_text(
        '["Why are you interested in this role?"]',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        workflow_cli,
        "PRIVATE_DIR",
        private_dir,
    )

    recorded_steps: list[tuple[str, list[str]]] = []

    def fake_run_step(
        step_name: str,
        command: list[str],
    ) -> None:
        recorded_steps.append((step_name, command))
        private_dir.mkdir(parents=True, exist_ok=True)

        generated_files = {
            "Candidate profile and evidence generation": [
                "candidate_profile.json",
                "evidence_bank.json",
            ],
            "Job-description parsing": [
                "structured_job.json",
            ],
            "Candidate-job relevance scoring": [
                "scoring_result.json",
            ],
            "Recommendation-report generation": [
                "recommendation_report.md",
            ],
            "Application personalization": [
                "personalized_application.json",
            ],
        }

        for filename in generated_files[step_name]:
            (private_dir / filename).write_text(
                "{}",
                encoding="utf-8",
            )

    monkeypatch.setattr(
        workflow_cli,
        "run_step",
        fake_run_step,
    )

    args = argparse.Namespace(
        cv=cv_path,
        job_file=job_path,
        job_url="https://example.com/jobs/123",
        pure_ai_role=False,
        personalize=True,
        questions=questions_path,
    )

    workflow_cli.run_workflow(args)

    assert len(recorded_steps) == 5
    assert recorded_steps[-1][0] == "Application personalization"
    assert recorded_steps[-1][1][0].endswith(
        "personalization_cli.py"
    )
    assert "--questions" in recorded_steps[-1][1]
    assert str(questions_path.resolve()) in recorded_steps[-1][1]


def test_questions_require_personalization(
    tmp_path: Path,
) -> None:
    """Application questions cannot be used without personalization."""
    args = argparse.Namespace(
        cv=tmp_path / "candidate.pdf",
        job_file=tmp_path / "job.txt",
        job_url="https://example.com/jobs/123",
        pure_ai_role=False,
        personalize=False,
        questions=tmp_path / "questions.json",
    )

    with pytest.raises(
        workflow_cli.WorkflowError,
        match="--questions requires the --personalize option",
    ):
        workflow_cli.run_workflow(args)