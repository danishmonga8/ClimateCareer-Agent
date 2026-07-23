"""Command-line interface for generating a private recommendation report."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from app.services.recommendation_report import save_recommendation_report
from app.services.scoring_repository import load_scoring_result


DEFAULT_INPUT_PATH = Path("documents/private/scoring_result.json")
DEFAULT_OUTPUT_PATH = Path("documents/private/recommendation_report.md")

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Create and return the command-line argument parser."""

    parser = argparse.ArgumentParser(
        description="Generate a private recommendation report from a scoring result."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help=f"Scoring-result JSON file (default: {DEFAULT_INPUT_PATH}).",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Recommendation-report path (default: {DEFAULT_OUTPUT_PATH}).",
    )

    return parser


def get_field(result: object, field_name: str) -> Any:
    """Read a field from either a model object or a dictionary."""

    if isinstance(result, Mapping):
        return result[field_name]

    return getattr(result, field_name)


def display_value(value: Any) -> Any:
    """Return the stored value when the supplied value is an Enum."""

    if isinstance(value, Enum):
        return value.value

    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Generate the recommendation report and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        scoring_result = load_scoring_result(args.input)

        save_recommendation_report(
            scoring_result,
            args.output,
        )

        company = get_field(scoring_result, "company")
        role = get_field(scoring_result, "job_title")
        overall_score = float(get_field(scoring_result, "overall_score"))
        recommendation = display_value(
            get_field(scoring_result, "recommendation")
        )

        LOGGER.info("Recommendation report generated successfully.")
        LOGGER.info("Company: %s", company)
        LOGGER.info("Role: %s", role)
        LOGGER.info("Overall score: %.2f/100", overall_score)
        LOGGER.info("Recommendation: %s", recommendation)
        LOGGER.info("Private report saved to: %s", args.output.resolve())

        return 0

    except Exception as exc:
        LOGGER.error("Unable to generate recommendation report: %s", exc)
        return 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
    )

    raise SystemExit(main())