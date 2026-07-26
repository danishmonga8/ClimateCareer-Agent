"""Generate readable recommendation reports from job-scoring results."""

from pathlib import Path

from app.models.scoring import JobRelevanceScore


class RecommendationReportError(RuntimeError):
    """Raised when a recommendation report cannot be saved."""


def _clean_text(value: str) -> str:
    """Convert model-generated text into a safe single Markdown line."""
    cleaned = " ".join(value.split())
    return cleaned.replace("<", "&lt;").replace(">", "&gt;")


def _bullet_lines(items: list[str]) -> list[str]:
    """Convert text items into Markdown bullets."""
    if not items:
        return ["- None reported."]

    return [f"- {_clean_text(item)}" for item in items]


def render_recommendation_report(
    result: JobRelevanceScore,
) -> str:
    """Render a complete job-recommendation report as Markdown."""
    recommendation = result.recommendation.value.replace("_", " ").title()

    lines = [
        "# Job Relevance Recommendation Report",
        "",
        f"**Company:** {_clean_text(result.company)}",
        f"**Role:** {_clean_text(result.job_title)}",
        f"**Overall score:** {result.overall_score:.2f}/100",
        f"**Recommendation:** {recommendation}",
        f"**Confidence:** {result.confidence_score:.0%}",
        "",
        "## Score Breakdown",
        "",
        "| Category | Score | Maximum |",
        "|---|---:|---:|",
    ]

    for component in result.components:
        category = component.category.value.replace("_", " ").title()
        lines.append(
            f"| {category} | {component.awarded_points:.2f} | {component.maximum_points:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Category Explanations",
            "",
        ]
    )

    for component in result.components:
        category = component.category.value.replace("_", " ").title()
        lines.extend(
            [
                f"### {category}",
                "",
                _clean_text(component.rationale),
                "",
                "**Matched evidence**",
                "",
                *_bullet_lines(component.matched_evidence),
                "",
                "**Missing items**",
                "",
                *_bullet_lines(component.missing_items),
                "",
            ]
        )

    lines.extend(
        [
            "## Hard Constraints",
            "",
        ]
    )

    if result.hard_constraints:
        for check in result.hard_constraints:
            status = check.status.value.upper().replace("_", " ")
            lines.extend(
                [
                    f"- **{status}:** {_clean_text(check.requirement)}",
                    f"  - {_clean_text(check.explanation)}",
                ]
            )
    else:
        lines.append("- No hard constraints were reported.")

    lines.extend(
        [
            "",
            "## Strongest Alignments",
            "",
            *_bullet_lines(result.strongest_alignments),
            "",
            "## Transferable Skills",
            "",
            *_bullet_lines(result.transferable_skills),
            "",
            "## Recommended Resume Changes",
            "",
            *_bullet_lines(result.recommended_resume_changes),
            "",
            "## Uncertainties Requiring Review",
            "",
            *_bullet_lines(result.uncertainty_notes),
            "",
            "## Human-Supervision Notice",
            "",
            (
                "This report supports human decision-making. It does not authorize "
                "automatic application submission, email sending, or unsupported "
                "candidate claims."
            ),
            "",
        ]
    )

    return "\n".join(lines)


def save_recommendation_report(
    result: JobRelevanceScore,
    output_path: Path,
) -> Path:
    """Save a Markdown report using an atomic file replacement."""
    resolved_path = output_path.expanduser().resolve()
    temporary_path = resolved_path.with_name(f"{resolved_path.name}.temporary")

    try:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            render_recommendation_report(result),
            encoding="utf-8",
        )
        temporary_path.replace(resolved_path)
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        raise RecommendationReportError("Could not save recommendation report.") from error

    return resolved_path
