"""Private storage services for validated candidate profiles."""

from pathlib import Path

from pydantic import ValidationError

from app.models.candidate import CandidateProfile


class ProfileStorageError(ValueError):
    """Raised when a candidate profile cannot be loaded or stored."""


def _validate_json_path(path: Path) -> None:
    """Require JSON storage for candidate profiles."""
    if path.suffix.lower() != ".json":
        raise ProfileStorageError("Candidate profiles must use a .json file.")


def save_candidate_profile(
    profile: CandidateProfile,
    output_path: str | Path,
) -> Path:
    """Save a validated candidate profile as formatted JSON."""
    path = Path(output_path).expanduser().resolve()
    _validate_json_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        path.write_text(
            profile.model_dump_json(indent=2),
            encoding="utf-8",
        )
    except OSError as error:
        raise ProfileStorageError(
            f"Unable to save candidate profile: {path}"
        ) from error

    return path


def load_candidate_profile(input_path: str | Path) -> CandidateProfile:
    """Load and validate a private candidate-profile JSON file."""
    path = Path(input_path).expanduser().resolve()
    _validate_json_path(path)

    if not path.is_file():
        raise ProfileStorageError(f"Candidate profile does not exist: {path}")

    try:
        return CandidateProfile.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise ProfileStorageError(
            f"Unable to load a valid candidate profile: {path}"
        ) from error