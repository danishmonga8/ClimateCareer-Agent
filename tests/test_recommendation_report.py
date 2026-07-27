"""Tests for deterministic recommendation-report generation."""

from pathlib import Path

from app.models.scoring import (
    HardConstraintCheck,
    HardConstraintStatus,
    JobRelevanceScore,
    ScoreComponent,
    WeightScheme,
)
from app.services.recommendation_report import (
    render_recommendation_report,
    save_recommendation_report,
)


def _create_scoring_result() -> JobRelevanceScore:
    """Create a complete scoring result without making an API request."""
    weights = WeightScheme()

    components = [
        ScoreComponent(
            category=category,
            awarded_points=maximum_points * 0.8,
            maximum_points=maximum_points,
            rationale="The candidate has relevant verified experience.",
            matched_evidence=["Verified environmental analytics experience."],
            missing_items=["Production deployment evidence is limited."],
        )
        for category, maximum_points in weights.as_mapping().items()
    ]

    return JobRelevanceScore(
        company="Sample Climate Company",
        job_title="Environmental Data Scientist",
        weight_scheme=weights,
        components=components,
        hard_constraints=[
            HardConstraintCheck(
                requirement="Python experience",
                status=HardConstraintStatus.PASSED,
                explanation="Python experience is verified.",
            )
        ],
        strongest_alignments=["Environmental data analysis"],
        transferable_skills=["Predictive modelling"],
        recommended_resume_changes=["Emphasize verified environmental modelling work."],
        uncertainty_notes=["Commercial deployment is not verified."],
        confidence_score=0.9,
    )


def test_recommendation_report_is_complete_and_saved(
    tmp_path: Path,
) -> None:
    """A scoring result should become a readable saved Markdown report."""
    result = _create_scoring_result()
    report = render_recommendation_report(result)

    assert "# Job Relevance Recommendation Report" in report
    assert "Sample Climate Company" in report
    assert "80.00/100" in report
    assert "Excellent Match Prioritize" not in report
    assert "Strong Match Apply" in report
    assert "Python experience is verified." in report
    assert "Commercial deployment is not verified." in report
    assert "does not authorize automatic application submission" in report

    output_path = tmp_path / "recommendation_report.md"
    saved_path = save_recommendation_report(result, output_path)

    assert saved_path == output_path.resolve()
    assert saved_path.read_text(encoding="utf-8") == report
