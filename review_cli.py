"""Command-line interface for human review of personalized applications."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from app.models.personalization import PersonalizedApplication
from app.services.application_review_service import (
    ApplicationReviewError,
    approve_application,
    begin_application_review,
    resolve_application_answer,
    resolve_review_item,
)
from app.services.personalization_repository import (
    ApplicationStorageError,
    load_personalized_application,
    save_personalized_application,
)


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
        help="Approve a fully reviewed application.",
    )
    _add_application_argument(approve_parser)
    approve_parser.add_argument(
        "--approval-note",
        required=True,
        help="Explicit user approval statement.",
    )

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
    unresolved_items = [
        item for item in application.review_items if not item.resolved
    ]
    unconfirmed_answers = [
        answer
        for answer in application.application_answers
        if answer.requires_confirmation
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
            print(
                f"Question requiring confirmation [{index}]: "
                f"{answer.question}"
            )

    for item in unresolved_items:
        print(f"Unresolved field: {item.field_path}")
        print(f"Reason: {item.reason}")


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

        elif args.command == "approve":
            updated_application = approve_application(
                application,
                approval_note=args.approval_note,
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
    ) as error:
        print(f"Application review failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())