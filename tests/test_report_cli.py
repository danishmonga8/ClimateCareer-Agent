"""Tests for the recommendation-report command-line interface."""

from pathlib import Path
from unittest.mock import patch

from app.models.scoring import (
    JobRelevanceScore,
    ScoreComponent,
    WeightScheme,
)
from report_cli import main


def test_report_cli_generates_markdown_report(tmp_path: Path) -> None:
    """The CLI should load a scoring result and save its report."""
    input_path = tmp_path / "scoring_result.json"
    output_path = tmp_path / "recommendation_report.md"

    weights = WeightScheme()

    scoring_result = JobRelevanceScore(
        company="Sample Climate Company",
        job_title="Environmental Data Scientist",
        weight_scheme=weights,
        components=[
            ScoreComponent(
                category=category,
                awarded_points=maximum_points * 0.8,
                maximum_points=maximum_points,
                rationale="Strong verified alignment.",
            )
            for category, maximum_points in weights.as_mapping().items()
        ],
        confidence_score=0.9,
    )

    with patch(
        "report_cli.load_scoring_result",
        return_value=scoring_result,
    ) as mocked_loader:
        exit_code = main(
            [
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ]
        )

    mocked_loader.assert_called_once_with(input_path)

    assert exit_code == 0
    assert output_path.exists()

    report = output_path.read_text(encoding="utf-8")

    assert "# Job Relevance Recommendation Report" in report
    assert "Sample Climate Company" in report
    assert "Environmental Data Scientist" in report
    assert "80.00/100" in report
    assert "Strong Match Apply" in report
