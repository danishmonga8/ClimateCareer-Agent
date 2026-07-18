"""Command-line interface for manually supplied job descriptions."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from app.agents.jd_parser_agent import JobParsingError, parse_job_description
from app.services.job_repository import (
    JobStorageError,
    save_job_description,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create command-line arguments for manual job parsing."""
    parser = argparse.ArgumentParser(
        description="Parse a manually supplied job description."
    )
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to a UTF-8 text file containing the job description.",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Original public URL of the job advertisement.",
    )
    parser.add_argument(
        "--source",
        default="manual_input",
        help="Source name for the job advertisement.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("documents/private/structured_job.json"),
        help="Private JSON destination for the parsed job.",
    )
    return parser


def _read_job_text(path: Path) -> str:
    """Read a UTF-8 job-description file."""
    resolved_path = path.expanduser().resolve()

    if not resolved_path.is_file():
        raise JobParsingError(
            f"Job-description file does not exist: {resolved_path}"
        )

    try:
        text = resolved_path.read_text(encoding="utf-8")
    except OSError as error:
        raise JobParsingError(
            f"Unable to read job-description file: {resolved_path}"
        ) from error

    if not text.strip():
        raise JobParsingError("Job-description file is empty.")

    return text


def main(arguments: Sequence[str] | None = None) -> int:
    """Parse and privately store one manual job description."""
    parser = create_argument_parser()
    parsed_arguments = parser.parse_args(arguments)

    try:
        job_text = _read_job_text(parsed_arguments.file)
        job = parse_job_description(
            job_text=job_text,
            job_url=parsed_arguments.url,
            source=parsed_arguments.source,
        )
        saved_path = save_job_description(
            job,
            parsed_arguments.output,
        )
    except JobParsingError as error:
        logger.error("Job parsing failed: %s", error)
        return 1
    except JobStorageError as error:
        logger.error("Job storage failed: %s", error)
        return 1

    logger.info("Job description parsed and validated.")
    logger.info("Company: %s", job.company)
    logger.info("Role: %s", job.title)
    logger.info(
        "Mandatory requirements: %d",
        len(job.mandatory_requirements),
    )
    logger.info(
        "Preferred requirements: %d",
        len(job.preferred_requirements),
    )
    logger.info("Structured job saved to: %s", saved_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())