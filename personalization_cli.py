"""Command-line interface for evidence-constrained personalization."""

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path

from app.agents.personalization_agent import (
    PersonalizationError,
    personalize_application,
)
from app.services.evidence_repository import (
    EvidenceStorageError,
    load_evidence_bank,
)
from app.services.job_repository import (
    JobStorageError,
    load_job_description,
)
from app.services.personalization_repository import (
    ApplicationStorageError,
    save_personalized_application,
)
from app.services.profile_service import (
    ProfileStorageError,
    load_candidate_profile,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


class PersonalizationInputError(ValueError):
    """Raised when personalization CLI input is invalid."""


def create_argument_parser() -> argparse.ArgumentParser:
    """Create command-line arguments for application personalization."""
    parser = argparse.ArgumentParser(
        description=(
            "Create an evidence-backed resume, cover letter, and draft application answers."
        )
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("documents/private/candidate_profile.json"),
        help="Private candidate-profile JSON file.",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("documents/private/evidence_bank.json"),
        help="Private verified evidence-bank JSON file.",
    )
    parser.add_argument(
        "--job",
        type=Path,
        default=Path("documents/private/structured_job.json"),
        help="Private structured job-description JSON file.",
    )
    parser.add_argument(
        "--questions",
        type=Path,
        help=("Optional UTF-8 JSON file containing an array of application-question strings."),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("documents/private/personalized_application.json"),
        help="Private JSON destination for the application draft.",
    )
    return parser


def _load_application_questions(path: Path | None) -> list[str]:
    """Load and validate optional application questions."""
    if path is None:
        return []

    resolved_path = path.expanduser().resolve()

    if not resolved_path.is_file():
        raise PersonalizationInputError("Application-question file does not exist.")

    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PersonalizationInputError(
            "Unable to read valid application-question JSON."
        ) from error

    if not isinstance(payload, list):
        raise PersonalizationInputError("Application questions must be supplied as a JSON array.")

    if any(not isinstance(question, str) or not question.strip() for question in payload):
        raise PersonalizationInputError("Every application question must be a non-empty string.")

    return [question.strip() for question in payload]


def main(arguments: Sequence[str] | None = None) -> int:
    """Create and privately store one personalized application draft."""
    parser = create_argument_parser()
    parsed_arguments = parser.parse_args(arguments)

    try:
        questions = _load_application_questions(parsed_arguments.questions)
        profile = load_candidate_profile(parsed_arguments.profile)
        evidence_bank = load_evidence_bank(parsed_arguments.evidence)
        job = load_job_description(parsed_arguments.job)

        application = personalize_application(
            profile=profile,
            evidence_bank=evidence_bank,
            job=job,
            application_questions=questions,
        )
        save_personalized_application(
            application,
            parsed_arguments.output,
        )
    except (
        PersonalizationInputError,
        ProfileStorageError,
        EvidenceStorageError,
        JobStorageError,
        PersonalizationError,
        ApplicationStorageError,
    ):
        logger.error("Application personalization failed. Check the local inputs and try again.")
        return 1

    logger.info("Application personalization completed.")
    logger.info("Resume claims: %d", len(application.resume.claims))
    logger.info(
        "Cover-letter claims: %d",
        len(application.cover_letter.claims),
    )
    logger.info(
        "Application questions: %d",
        len(application.application_answers),
    )
    logger.info(
        "Items requiring human review: %d",
        len(application.review_items),
    )
    logger.info("Status: %s", application.status.value)
    logger.info("Private application draft recorded locally.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
