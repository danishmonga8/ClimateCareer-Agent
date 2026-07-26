"""Command-line interface for explainable job-relevance scoring."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from app.agents.scoring_agent import JobScoringError, score_job_relevance
from app.models.scoring import HardConstraintStatus
from app.services.evidence_repository import (
    EvidenceStorageError,
    load_evidence_bank,
)
from app.services.job_repository import (
    JobStorageError,
    load_job_description,
)
from app.services.profile_service import (
    ProfileStorageError,
    load_candidate_profile,
)
from app.services.scoring_repository import (
    ScoringStorageError,
    save_scoring_result,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


class ScoringInputError(ValueError):
    """Raised when scoring input files do not belong together."""


def create_argument_parser() -> argparse.ArgumentParser:
    """Create command-line arguments for job scoring."""
    parser = argparse.ArgumentParser(
        description="Calculate an explainable candidate-job relevance score."
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
        "--output",
        type=Path,
        default=Path("documents/private/scoring_result.json"),
        help="Private JSON destination for the scoring result.",
    )
    parser.add_argument(
        "--pure-ai-role",
        action="store_true",
        help="Use the documented weight redistribution for pure AI roles.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Load private inputs, score the job, and save the result."""
    parser = create_argument_parser()
    parsed_arguments = parser.parse_args(arguments)

    try:
        profile = load_candidate_profile(parsed_arguments.profile)
        evidence_bank = load_evidence_bank(parsed_arguments.evidence)
        job = load_job_description(parsed_arguments.job)

        if evidence_bank.candidate_name != profile.full_name:
            raise ScoringInputError("Evidence bank and candidate profile names do not match.")

        if evidence_bank.source_document != profile.source_document:
            raise ScoringInputError("Evidence bank and profile source documents do not match.")

        result = score_job_relevance(
            profile=profile,
            evidence_bank=evidence_bank,
            job=job,
            pure_ai_role=parsed_arguments.pure_ai_role,
        )
        save_scoring_result(
            result,
            parsed_arguments.output,
        )
    except (
        ProfileStorageError,
        EvidenceStorageError,
        JobStorageError,
        ScoringStorageError,
        ScoringInputError,
        JobScoringError,
    ):
        logger.error("Job scoring failed. Check the local inputs and try again.")
        return 1

    logger.info("Job relevance scoring completed.")
    logger.info("Overall score: %.2f/100", result.overall_score)
    logger.info("Recommendation: %s", result.recommendation.value)
    logger.info("Confidence: %.2f", result.confidence_score)

    for component in result.components:
        logger.info(
            "%s: %.2f/%.2f",
            component.category.value,
            component.awarded_points,
            component.maximum_points,
        )

    failed_constraints = [
        check for check in result.hard_constraints if check.status == HardConstraintStatus.FAILED
    ]
    logger.info("Hard eligibility failures: %d", len(failed_constraints))
    logger.info("Private scoring result recorded locally.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
