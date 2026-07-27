"""Tests for explainable job-relevance scoring."""

from app.models.scoring import (
    ApplicationRecommendation,
    HardConstraintCheck,
    HardConstraintStatus,
    JobRelevanceScore,
    ScoreComponent,
    WeightScheme,
)


def test_high_score_is_overridden_by_hard_failure() -> None:
    """A hard eligibility failure must override a high score."""
    weights = WeightScheme()

    components = [
        ScoreComponent(
            category=category,
            awarded_points=maximum,
            maximum_points=maximum,
            rationale="The candidate fully matches this category.",
        )
        for category, maximum in weights.as_mapping().items()
    ]

    result = JobRelevanceScore(
        company="Sample Company",
        job_title="Climate Data Scientist",
        weight_scheme=weights,
        components=components,
        hard_constraints=[
            HardConstraintCheck(
                requirement="Existing work authorization is mandatory.",
                status=HardConstraintStatus.FAILED,
                explanation="The requirement is not currently satisfied.",
            )
        ],
        confidence_score=0.95,
    )

    assert result.overall_score == 100
    assert result.recommendation == ApplicationRecommendation.DO_NOT_APPLY
