"""Command-line entry point for ClimateCareer-Agent."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from app.agents.candidate_agent import (
    CandidateExtractionError,
    extract_candidate_profile,
)
from app.models.evidence import EvidenceStatus
from app.services.cv_parser import DocumentParsingError, parse_cv
from app.services.evidence_repository import (
    EvidenceStorageError,
    save_evidence_bank,
)
from app.services.evidence_service import build_evidence_bank
from app.services.profile_service import (
    ProfileStorageError,
    load_candidate_profile,
    save_candidate_profile,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="ClimateCareer-Agent Phase 1 command-line interface."
    )
    parser.add_argument(
        "--cv",
        type=Path,
        required=True,
        help="Path to the master CV in PDF or DOCX format.",
    )
    parser.add_argument(
        "--extract-profile",
        action="store_true",
        help="Use the configured LLM to extract a candidate profile.",
    )
    parser.add_argument(
        "--build-evidence",
        action="store_true",
        help="Build an evidence bank from the CV and stored profile.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("documents/private/candidate_profile.json"),
        help="Private JSON destination for the candidate profile.",
    )
    parser.add_argument(
        "--evidence-output",
        type=Path,
        default=Path("documents/private/evidence_bank.json"),
        help="Private JSON destination for the evidence bank.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Validate a CV and run selected Phase 1 operations."""
    parser = create_argument_parser()
    parsed_arguments = parser.parse_args(arguments)

    try:
        parsed_cv = parse_cv(parsed_arguments.cv)
    except DocumentParsingError as error:
        logger.error("CV processing failed: %s", error)
        return 1

    logger.info("CV validated and parsed successfully.")
    logger.info("File: %s", parsed_cv.filename)
    logger.info("Pages: %d", parsed_cv.page_count)
    logger.info("Extracted characters: %d", len(parsed_cv.text))
    logger.info(
        "Document fingerprint: %s...",
        parsed_cv.sha256_digest[:12],
    )

    profile = None

    if parsed_arguments.extract_profile:
        logger.info("Starting structured candidate-profile extraction.")

        try:
            profile = extract_candidate_profile(
                cv_text=parsed_cv.text,
                source_document=parsed_cv.filename,
            )
            saved_path = save_candidate_profile(
                profile,
                parsed_arguments.output,
            )
        except CandidateExtractionError as error:
            logger.error("Candidate extraction failed: %s", error)
            return 1
        except ProfileStorageError as error:
            logger.error("Candidate profile storage failed: %s", error)
            return 1

        logger.info("Candidate profile extracted and validated.")
        logger.info("Private profile saved to: %s", saved_path)

    if parsed_arguments.build_evidence:
        logger.info("Starting deterministic evidence-bank generation.")

        try:
            if profile is None:
                profile = load_candidate_profile(parsed_arguments.output)

            evidence_bank = build_evidence_bank(
                profile=profile,
                cv_text=parsed_cv.text,
                source_sha256=parsed_cv.sha256_digest,
            )
            evidence_path = save_evidence_bank(
                evidence_bank,
                parsed_arguments.evidence_output,
            )
        except ProfileStorageError as error:
            logger.error("Candidate profile loading failed: %s", error)
            return 1
        except EvidenceStorageError as error:
            logger.error("Evidence-bank storage failed: %s", error)
            return 1

        verified_count = sum(
            record.status == EvidenceStatus.VERIFIED
            for record in evidence_bank.records
        )
        review_count = sum(
            record.status == EvidenceStatus.REQUIRES_CONFIRMATION
            for record in evidence_bank.records
        )

        logger.info("Evidence bank generated successfully.")
        logger.info("Verified evidence records: %d", verified_count)
        logger.info("Records requiring confirmation: %d", review_count)
        logger.info("Private evidence bank saved to: %s", evidence_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())