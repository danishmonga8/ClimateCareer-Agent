"""Command-line interface for read-only public job discovery."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from app.discovery.ashby import collect_ashby_jobs
from app.discovery.filtering import DiscoveryFilter
from app.discovery.greenhouse import collect_greenhouse_jobs
from app.discovery.http import JobCollectorError
from app.discovery.lever import LeverRegion, collect_lever_jobs
from app.discovery.service import build_discovery_snapshot
from app.models.job import EmploymentType, WorkArrangement
from app.services.discovery_repository import (
    DiscoveryStorageError,
    save_discovery_snapshot,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build arguments for the supported public ATS collectors."""
    parser = argparse.ArgumentParser(
        description="Collect public job listings without submitting applications."
    )
    parser.add_argument("--company", required=True, help="Employer display name.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("documents/private/discovered_jobs.json"),
        help="Private JSON destination for the discovery snapshot.",
    )
    parser.add_argument("--include", action="append", default=[], help="Required keyword.")
    parser.add_argument("--exclude", action="append", default=[], help="Excluded keyword.")
    parser.add_argument("--location", action="append", default=[], help="Location match.")
    parser.add_argument(
        "--work-arrangement",
        action="append",
        choices=list(WorkArrangement),
        default=[],
    )
    parser.add_argument(
        "--employment-type",
        action="append",
        choices=list(EmploymentType),
        default=[],
    )
    parser.add_argument(
        "--require-all-keywords",
        action="store_true",
        help="Require every --include keyword instead of any keyword.",
    )

    subparsers = parser.add_subparsers(dest="provider", required=True)
    greenhouse = subparsers.add_parser("greenhouse")
    greenhouse.add_argument("--board", required=True, help="Public board token.")

    lever = subparsers.add_parser("lever")
    lever.add_argument("--site", required=True, help="Public Lever site name.")
    lever.add_argument(
        "--region",
        choices=list(LeverRegion),
        default=LeverRegion.GLOBAL,
    )

    ashby = subparsers.add_parser("ashby")
    ashby.add_argument("--board", required=True, help="Public jobs page name.")
    ashby.add_argument(
        "--no-compensation",
        action="store_true",
        help="Do not request public compensation fields.",
    )
    return parser


def _collect_jobs(args: argparse.Namespace):  # type: ignore[no-untyped-def]
    if args.provider == "greenhouse":
        return collect_greenhouse_jobs(args.board, args.company)
    if args.provider == "lever":
        return collect_lever_jobs(
            args.site,
            args.company,
            region=LeverRegion(args.region),
        )
    if args.provider == "ashby":
        return collect_ashby_jobs(
            args.board,
            args.company,
            include_compensation=not args.no_compensation,
        )
    raise JobCollectorError(f"Unsupported provider: {args.provider}")


def main(arguments: Sequence[str] | None = None) -> int:
    """Collect, filter, deduplicate, and privately store public jobs."""
    args = build_parser().parse_args(arguments)
    criteria = DiscoveryFilter(
        include_keywords=args.include,
        exclude_keywords=args.exclude,
        locations=args.location,
        work_arrangements=args.work_arrangement,
        employment_types=args.employment_type,
        require_all_keywords=args.require_all_keywords,
    )

    try:
        jobs = _collect_jobs(args)
        snapshot = build_discovery_snapshot([jobs], criteria=criteria)
        save_discovery_snapshot(snapshot, args.output)
    except (JobCollectorError, DiscoveryStorageError):
        logger.error("Job discovery failed. Check the local configuration and try again.")
        return 1

    logger.info("Collected public listings: %d", len(jobs))
    logger.info("Listings retained after filtering and deduplication: %d", len(snapshot.jobs))
    logger.info("Private discovery snapshot recorded locally.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
