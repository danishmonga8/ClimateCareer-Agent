"""Run the complete ClimateCareer-Agent Phase 1 workflow."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
PRIVATE_DIR = PROJECT_ROOT / "documents" / "private"


class WorkflowError(RuntimeError):
    """Raised when a workflow stage fails."""


def require_file(path: Path, description: str) -> None:
    """Confirm that a required file exists."""

    if not path.is_file():
        raise WorkflowError(f"{description} was not found: {path}")


def run_step(step_name: str, command: list[str]) -> None:
    """Run one workflow command and stop if it fails."""

    print(f"\n=== {step_name.upper()} ===")

    result = subprocess.run(
        [sys.executable, *command],
        cwd=PROJECT_ROOT,
        check=False,
    )

    if result.returncode != 0:
        raise WorkflowError(
            f"{step_name} failed with exit code {result.returncode}."
        )


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Run CV extraction, evidence generation, job parsing, "
            "relevance scoring, and recommendation-report generation."
        )
    )

    parser.add_argument(
        "--cv",
        type=Path,
        required=True,
        help="Path to the candidate CV in PDF or DOCX format.",
    )

    parser.add_argument(
        "--job-file",
        type=Path,
        required=True,
        help="Path to the UTF-8 job-description text file.",
    )

    parser.add_argument(
        "--job-url",
        required=True,
        help="Original job-advertisement URL.",
    )

    parser.add_argument(
        "--pure-ai-role",
        action="store_true",
        help=(
            "Apply the scoring configuration for a primarily "
            "AI-focused role."
        ),
    )

    return parser


def run_workflow(args: argparse.Namespace) -> None:
    """Run all Phase 1 workflow stages."""

    cv_path = args.cv.expanduser().resolve()
    job_file_path = args.job_file.expanduser().resolve()

    require_file(cv_path, "Candidate CV")
    require_file(job_file_path, "Job-description file")

    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)

    run_step(
        "Candidate profile and evidence generation",
        [
            str(PROJECT_ROOT / "main.py"),
            "--cv",
            str(cv_path),
            "--extract-profile",
            "--build-evidence",
        ],
    )

    require_file(
        PRIVATE_DIR / "candidate_profile.json",
        "Generated candidate profile",
    )

    require_file(
        PRIVATE_DIR / "evidence_bank.json",
        "Generated evidence bank",
    )

    run_step(
        "Job-description parsing",
        [
            str(PROJECT_ROOT / "job_cli.py"),
            "--file",
            str(job_file_path),
            "--url",
            args.job_url,
        ],
    )

    require_file(
        PRIVATE_DIR / "structured_job.json",
        "Generated structured job",
    )

    score_command = [str(PROJECT_ROOT / "score_cli.py")]

    if args.pure_ai_role:
        score_command.append("--pure-ai-role")

    run_step(
        "Candidate-job relevance scoring",
        score_command,
    )

    require_file(
        PRIVATE_DIR / "scoring_result.json",
        "Generated scoring result",
    )

    run_step(
        "Recommendation-report generation",
        [str(PROJECT_ROOT / "report_cli.py")],
    )

    report_path = PRIVATE_DIR / "recommendation_report.md"

    require_file(
        report_path,
        "Generated recommendation report",
    )

    print("\n=== WORKFLOW COMPLETED SUCCESSFULLY ===")
    print(
        "Candidate profile: "
        f"{PRIVATE_DIR / 'candidate_profile.json'}"
    )
    print(f"Evidence bank: {PRIVATE_DIR / 'evidence_bank.json'}")
    print(f"Structured job: {PRIVATE_DIR / 'structured_job.json'}")
    print(f"Scoring result: {PRIVATE_DIR / 'scoring_result.json'}")
    print(f"Recommendation report: {report_path}")


def main() -> int:
    """Run the unified workflow command."""

    parser = build_parser()
    args = parser.parse_args()

    try:
        run_workflow(args)
    except WorkflowError as error:
        print(f"\nWORKFLOW FAILED: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(
            "\nWorkflow cancelled by the user.",
            file=sys.stderr,
        )
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())