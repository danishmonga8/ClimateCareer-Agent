"""Private JSON storage for explainable relevance scores."""

from pathlib import Path

from pydantic import ValidationError

from app.models.scoring import JobRelevanceScore


class ScoringStorageError(ValueError):
    """Raised when a scoring result cannot be loaded or stored."""


def _validate_json_path(path: Path) -> None:
    """Require JSON storage for scoring results."""
    if path.suffix.lower() != ".json":
        raise ScoringStorageError("Scoring results must use a .json file.")


def save_scoring_result(
    result: JobRelevanceScore,
    output_path: str | Path,
) -> Path:
    """Save a validated score while excluding computed properties."""
    path = Path(output_path).expanduser().resolve()
    _validate_json_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        path.write_text(
            result.model_dump_json(
                indent=2,
                exclude_computed_fields=True,
            ),
            encoding="utf-8",
        )
    except OSError as error:
        raise ScoringStorageError(
            f"Unable to save scoring result: {path}"
        ) from error

    return path


def load_scoring_result(
    input_path: str | Path,
) -> JobRelevanceScore:
    """Load, validate, and recalculate a stored relevance score."""
    path = Path(input_path).expanduser().resolve()
    _validate_json_path(path)

    if not path.is_file():
        raise ScoringStorageError(f"Scoring result does not exist: {path}")

    try:
        return JobRelevanceScore.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise ScoringStorageError(
            f"Unable to load a valid scoring result: {path}"
        ) from error