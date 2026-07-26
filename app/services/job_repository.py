"""Private JSON storage for validated job descriptions."""

from pathlib import Path

from pydantic import ValidationError

from app.models.job import JobDescription


class JobStorageError(ValueError):
    """Raised when structured job data cannot be loaded or stored."""


def _validate_json_path(path: Path) -> None:
    """Require JSON storage for structured job descriptions."""
    if path.suffix.lower() != ".json":
        raise JobStorageError("Structured jobs must use a .json file.")


def save_job_description(
    job: JobDescription,
    output_path: str | Path,
) -> Path:
    """Save a validated job description as formatted JSON."""
    path = Path(output_path).expanduser().resolve()
    _validate_json_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        path.write_text(
            job.model_dump_json(indent=2),
            encoding="utf-8",
        )
    except OSError as error:
        raise JobStorageError("Unable to save structured job.") from error

    return path


def load_job_description(input_path: str | Path) -> JobDescription:
    """Load and validate a structured job-description JSON file."""
    path = Path(input_path).expanduser().resolve()
    _validate_json_path(path)

    if not path.is_file():
        raise JobStorageError("Structured job does not exist.")

    try:
        return JobDescription.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise JobStorageError("Unable to load a valid structured job.") from error
