"""Tests for explainable scoring-result storage."""

from pathlib import Path

from app.models.scoring import (
    JobRelevanceScore,
    ScoreComponent,
    WeightScheme,
)
from app.services.scoring_repository import (
    load_scoring_result,
    save_scoring_result,
)


def test_scoring_result_survives_save_and_load(tmp_path: Path) -> None:
    """Stored category scores should recalculate the same total."""
    weights = WeightScheme()

    result = JobRelevanceScore(
        company="Sample Company",
        job_title="Environmental Data Scientist",
        weight_scheme=weights,
        components=[
            ScoreComponent(
                category=category,
                awarded_points=maximum * 0.8,
                maximum_points=maximum,
                rationale="Strong verified alignment.",
            )
            for category, maximum in weights.as_mapping().items()
        ],
        confidence_score=0.9,
    )

    output_path = tmp_path / "scoring_result.json"
    saved_path = save_scoring_result(result, output_path)
    loaded_result = load_scoring_result(saved_path)

    assert loaded_result.overall_score == 80
    assert loaded_result.company == "Sample Company"
    assert len(loaded_result.components) == 8
