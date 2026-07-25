"""Tests for discovery integration with existing parser and scorer."""

from typing import Any

from app.discovery.pipeline import evaluate_discovered_job, parse_discovered_job
from app.models.candidate import CandidateProfile, ContactInformation
from app.models.discovery import DiscoveredJob, JobSource
from app.models.evidence import EvidenceBank
from app.models.job import EmploymentType, JobDescription, WorkArrangement
from app.models.scoring import (
    JobRelevanceScore,
    ScoreCategory,
    ScoreComponent,
    WeightScheme,
)


def _discovered_job() -> DiscoveredJob:
    return DiscoveredJob(
        source=JobSource.GREENHOUSE,
        source_board="acme",
        source_job_id="123",
        company="Acme Climate",
        title="Climate Scientist",
        job_url="https://example.com/jobs/123",
        description="Analyse climate observations.",
    )


def _profile() -> CandidateProfile:
    return CandidateProfile(
        full_name="Sample Candidate",
        contact=ContactInformation(emails=["candidate@example.com"]),
        source_document="cv.pdf",
    )


def _evidence_bank() -> EvidenceBank:
    return EvidenceBank(
        candidate_name="Sample Candidate",
        source_document="cv.pdf",
        source_sha256="a" * 64,
    )


def _score() -> JobRelevanceScore:
    weights = WeightScheme()
    return JobRelevanceScore(
        company="Acme Climate",
        job_title="Climate Scientist",
        weight_scheme=weights,
        components=[
            ScoreComponent(
                category=category,
                awarded_points=0,
                maximum_points=maximum,
                rationale="No evidence assessed in integration test.",
            )
            for category, maximum in weights.as_mapping().items()
        ],
        confidence_score=0.5,
    )


def test_discovered_job_is_parsed_then_scored_with_provenance() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def parser(**kwargs: Any) -> JobDescription:
        calls.append(("parser", kwargs))
        return JobDescription(
            company="Acme Climate",
            title="Climate Scientist",
            job_url=kwargs["job_url"],
            source=kwargs["source"],
            discovery_date=kwargs["discovery_date"],
            raw_description=kwargs["job_text"],
            extraction_confidence=0.9,
        )

    def scorer(
        profile: CandidateProfile,
        evidence_bank: EvidenceBank,
        parsed_job: JobDescription,
        **kwargs: Any,
    ) -> JobRelevanceScore:
        assert profile.full_name == evidence_bank.candidate_name
        assert parsed_job.source == "greenhouse:acme"
        calls.append(("scorer", kwargs))
        return _score()

    discovered_job = _discovered_job()
    result = evaluate_discovered_job(
        discovered_job,
        _profile(),
        _evidence_bank(),
        pure_ai_role=True,
        parser=parser,
        scorer=scorer,
    )

    assert [name for name, _ in calls] == ["parser", "scorer"]
    assert calls[0][1]["discovery_date"] == discovered_job.discovered_at.date()
    assert calls[1][1]["pure_ai_role"] is True
    assert result.parsed_job.source == "greenhouse:acme"
    assert result.relevance_score.job_title == "Climate Scientist"


def test_pipeline_does_not_expose_submission_operations() -> None:
    from app.discovery import pipeline

    assert not hasattr(pipeline, "submit_application")
    assert set(ScoreCategory) == set(WeightScheme().as_mapping())


def test_parser_cannot_replace_trusted_discovery_fields() -> None:
    discovered_job = _discovered_job().model_copy(
        update={
            "location": "Remote - India",
            "work_arrangement": WorkArrangement.REMOTE,
            "employment_type": EmploymentType.FULL_TIME,
        }
    )

    def parser(**kwargs: Any) -> JobDescription:
        return JobDescription(
            company="Incorrect parser company",
            title="Incorrect parser title",
            job_url=kwargs["job_url"],
            source=kwargs["source"],
            location="Incorrect parser location",
            discovery_date=kwargs["discovery_date"],
            raw_description=kwargs["job_text"],
            extraction_confidence=0.9,
        )

    parsed = parse_discovered_job(discovered_job, parser=parser)

    assert parsed.company == "Acme Climate"
    assert parsed.title == "Climate Scientist"
    assert parsed.location == "Remote - India"
    assert parsed.work_arrangement == WorkArrangement.REMOTE
    assert parsed.employment_type == EmploymentType.FULL_TIME
