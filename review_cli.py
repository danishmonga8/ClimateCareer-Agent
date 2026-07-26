"""Command-line interface for human review of personalized applications."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from app.dashboard.data_loader import load_dashboard_data
from app.models.dashboard_review import DashboardReviewAction
from app.models.personalization import PersonalizedApplication
from app.services.application_review_service import (
    ApplicationReviewError,
    begin_application_review,
    resolve_application_answer,
    resolve_review_item,
)
from app.services.dashboard_repository import save_updated_dashboard_workspace
from app.services.dashboard_review_service import apply_dashboard_decision
from app.services.personalization_repository import (
    ApplicationStorageError,
    load_personalized_application,
    save_personalized_application,
)
from app.services.quality_control_service import (
    QualityControlError,
    QualityStatus,
    check_review_quality,
)
from app.workflows.orchestration import WorkflowOrchestrator
from app.workflows.repository import find_workflow_for_job
from app.workflows.state import WorkflowDecision


def build_parser() -> argparse.ArgumentParser:
    """Build the application-review command-line parser."""
    parser = argparse.ArgumentParser(
        description="Review and approve a personalized application.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    status_parser = subparsers.add_parser(
        "status",
        help="Show the current application-review status.",
    )
    _add_application_argument(status_parser)

    quality_parser = subparsers.add_parser(
        "quality-check",
        help="Run read-only, sanitized internal quality checks.",
    )
    quality_parser.add_argument("--workspace", required=True, type=Path)
    quality_parser.add_argument("--job-key", required=True)
    quality_parser.add_argument("--expected-revision", required=True, type=int)
    quality_parser.add_argument("--evidence", required=True, type=Path)
    quality_parser.add_argument("--workflow-checkpoints", type=Path)

    begin_parser = subparsers.add_parser(
        "begin",
        help="Move a draft application into human review.",
    )
    _add_application_argument(begin_parser)

    answer_parser = subparsers.add_parser(
        "resolve-answer",
        help="Confirm an application answer.",
    )
    _add_application_argument(answer_parser)
    answer_parser.add_argument(
        "--question-index",
        required=True,
        type=int,
        help="Zero-based index of the application question.",
    )
    answer_parser.add_argument(
        "--answer",
        required=True,
        help="Human-confirmed answer.",
    )
    answer_parser.add_argument(
        "--resolution",
        required=True,
        help="Explanation of how the answer was confirmed.",
    )

    item_parser = subparsers.add_parser(
        "resolve-item",
        help="Resolve a non-answer review item.",
    )
    _add_application_argument(item_parser)
    item_parser.add_argument(
        "--field-path",
        required=True,
        help="Field path of the unresolved review item.",
    )
    item_parser.add_argument(
        "--resolution",
        required=True,
        help="Human resolution for the review item.",
    )

    approve_parser = subparsers.add_parser(
        "approve",
        help="Quality-gate and record internal approval for a manual next step.",
    )
    approve_parser.add_argument("--workspace", required=True, type=Path)
    approve_parser.add_argument("--job-key", required=True)
    approve_parser.add_argument("--expected-revision", required=True, type=int)
    approve_parser.add_argument("--reviewer-label", required=True)
    approve_parser.add_argument("--confirm", action="store_true")
    approve_parser.add_argument("--evidence", required=True, type=Path)
    approve_parser.add_argument("--workflow-checkpoints", type=Path)
    approve_parser.add_argument("--approval-note", required=True)

    return parser


def _add_application_argument(
    parser: argparse.ArgumentParser,
) -> None:
    """Add the saved-application path argument."""
    parser.add_argument(
        "--application",
        required=True,
        type=Path,
        help="Path to the personalized-application JSON file.",
    )


def _print_status(
    application: PersonalizedApplication,
) -> None:
    """Print the current human-review status."""
    unresolved_items = [item for item in application.review_items if not item.resolved]
    unconfirmed_answers = [
        answer for answer in application.application_answers if answer.requires_confirmation
    ]

    print(f"Candidate: {application.candidate_name}")
    print(f"Job title: {application.job_title}")
    print(f"Employer: {application.employer}")
    print(f"Status: {application.status.value}")
    print(f"Review items: {len(application.review_items)}")
    print(f"Unresolved review items: {len(unresolved_items)}")
    print(f"Unconfirmed answers: {len(unconfirmed_answers)}")

    if application.user_approval_note:
        print(f"Approval note: {application.user_approval_note}")

    for index, answer in enumerate(application.application_answers):
        if answer.requires_confirmation:
            print(f"Question requiring confirmation [{index}]: {answer.question}")

    for item in unresolved_items:
        print(f"Unresolved field: {item.field_path}")
        print(f"Reason: {item.reason}")


def _print_quality_report(report) -> None:
    """Print a deterministic report containing no artifact content or paths."""
    print(f"Quality status: {report.status.value.upper()}")
    print(f"Warnings: {report.warning_count}")
    print(f"Blocking findings: {report.blocking_count}")
    for finding in report.findings:
        print(f"{finding.severity.value.upper()} {finding.code}: {finding.message}")
        print(f"Recovery: {finding.recovery_guidance}")


def _save_application(
    application: PersonalizedApplication,
    application_path: Path,
) -> None:
    """Persist an updated application."""
    save_personalized_application(
        application,
        application_path,
    )
    print(f"Application saved: {application_path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the application-review CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "quality-check":
            report = check_review_quality(
                args.workspace,
                args.job_key,
                args.expected_revision,
                evidence_path=args.evidence,
                workflow_directory=args.workflow_checkpoints,
            )
            _print_quality_report(report)
            return 3 if report.status == QualityStatus.BLOCKED else 0

        if args.command == "approve":
            if not args.confirm:
                print("Approval requires --confirm.", file=sys.stderr)
                return 2
            report = check_review_quality(
                args.workspace,
                args.job_key,
                args.expected_revision,
                evidence_path=args.evidence,
                workflow_directory=args.workflow_checkpoints,
            )
            _print_quality_report(report)
            if report.status == QualityStatus.BLOCKED:
                return 3
            workflow = (
                find_workflow_for_job(args.job_key, args.workflow_checkpoints)
                if args.workflow_checkpoints
                else None
            )
            if workflow is not None:
                result = WorkflowOrchestrator(args.workflow_checkpoints).resume(
                    workflow["workflow_id"],
                    {
                        "action": WorkflowDecision.APPROVE.value,
                        "expected_revision": args.expected_revision,
                        "reviewer_label": args.reviewer_label,
                        "reason_or_note": args.approval_note,
                    },
                )
                if result["stage"].value == "recoverable_failure":
                    return 3
            else:
                data = load_dashboard_data(args.workspace)
                linked = next(
                    item.application for item in data.jobs if item.record.job_key == args.job_key
                )
                updated = apply_dashboard_decision(
                    data.workspace,
                    args.job_key,
                    DashboardReviewAction.APPROVED,
                    args.expected_revision,
                    args.reviewer_label,
                    args.approval_note,
                    linked_application=linked,
                )
                save_updated_dashboard_workspace(data.workspace, updated, args.workspace)
            print("Approved for manual next step. No application was submitted.")
            return 0

        application = load_personalized_application(
            args.application,
        )

        if args.command == "status":
            _print_status(application)
            return 0

        if args.command == "begin":
            updated_application = begin_application_review(
                application,
            )

        elif args.command == "resolve-answer":
            updated_application = resolve_application_answer(
                application,
                question_index=args.question_index,
                answer=args.answer,
                resolution=args.resolution,
            )

        elif args.command == "resolve-item":
            updated_application = resolve_review_item(
                application,
                field_path=args.field_path,
                resolution=args.resolution,
            )

        else:
            parser.error(f"Unsupported command: {args.command}")
            return 2

        _save_application(
            updated_application,
            args.application,
        )
        _print_status(updated_application)
        return 0

    except (
        ApplicationReviewError,
        ApplicationStorageError,
        QualityControlError,
    ) as error:
        print(f"Application review failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
