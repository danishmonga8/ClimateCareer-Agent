"""Integration of discovery records with existing parsing and scoring."""

from collections.abc import Callable
from typing import Any

from openai import OpenAI

from app.agents.jd_parser_agent import parse_job_description
from app.agents.scoring_agent import score_job_relevance
from app.core.settings import Settings
from app.models.candidate import CandidateProfile
from app.models.discovery import DiscoveredJob, DiscoveryEvaluation
from app.models.evidence import EvidenceBank
from app.models.job import JobDescription
from app.models.scoring import JobRelevanceScore

JobParser = Callable[..., JobDescription]
JobScorer = Callable[..., JobRelevanceScore]


def parse_discovered_job(
    job: DiscoveredJob,
    *,
    client: OpenAI | None = None,
    settings: Settings | None = None,
    parser: JobParser = parse_job_description,
) -> JobDescription:
    """Parse a discovered listing while preserving discovery provenance."""
    parser_options: dict[str, Any] = {
        "discovery_date": job.discovered_at.date(),
    }
    if client is not None:
        parser_options["client"] = client
    if settings is not None:
        parser_options["settings"] = settings

    parsed_job = parser(
        job_text=job.description,
        job_url=str(job.job_url),
        source=f"{job.source.value}:{job.source_board}",
        **parser_options,
    )

    trusted_fields: dict[str, Any] = {
        "company": job.company,
        "title": job.title,
        "job_url": job.job_url,
        "source": f"{job.source.value}:{job.source_board}",
        "discovery_date": job.discovered_at.date(),
    }
    if job.location is not None:
        trusted_fields["location"] = job.location
    if job.work_arrangement.value != "unspecified":
        trusted_fields["work_arrangement"] = job.work_arrangement
    if job.employment_type.value != "unknown":
        trusted_fields["employment_type"] = job.employment_type
    if job.date_posted is not None:
        trusted_fields["date_posted"] = job.date_posted.date()

    return JobDescription.model_validate({**parsed_job.model_dump(), **trusted_fields})


def score_discovered_job(
    profile: CandidateProfile,
    evidence_bank: EvidenceBank,
    parsed_job: JobDescription,
    *,
    pure_ai_role: bool = False,
    client: OpenAI | None = None,
    settings: Settings | None = None,
    scorer: JobScorer = score_job_relevance,
) -> JobRelevanceScore:
    """Score a parsed discovered job with the existing scoring agent."""
    scorer_options: dict[str, Any] = {"pure_ai_role": pure_ai_role}
    if client is not None:
        scorer_options["client"] = client
    if settings is not None:
        scorer_options["settings"] = settings

    return scorer(
        profile,
        evidence_bank,
        parsed_job,
        **scorer_options,
    )


def evaluate_discovered_job(
    job: DiscoveredJob,
    profile: CandidateProfile,
    evidence_bank: EvidenceBank,
    *,
    pure_ai_role: bool = False,
    parser_client: OpenAI | None = None,
    scorer_client: OpenAI | None = None,
    settings: Settings | None = None,
    parser: JobParser = parse_job_description,
    scorer: JobScorer = score_job_relevance,
) -> DiscoveryEvaluation:
    """Parse and score one normalized listing without submitting anything."""
    parsed_job = parse_discovered_job(
        job,
        client=parser_client,
        settings=settings,
        parser=parser,
    )
    relevance_score = score_discovered_job(
        profile,
        evidence_bank,
        parsed_job,
        pure_ai_role=pure_ai_role,
        client=scorer_client,
        settings=settings,
        scorer=scorer,
    )
    return DiscoveryEvaluation(
        discovered_job=job,
        parsed_job=parsed_job,
        relevance_score=relevance_score,
    )
