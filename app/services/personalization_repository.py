"""Private JSON storage for personalized application drafts."""

from pathlib import Path

from pydantic import ValidationError

from app.models.personalization import PersonalizedApplication


class ApplicationStorageError(ValueError):
    """Raised when a personalized application cannot be loaded or stored."""


def _validate_json_path(path: Path) -> None:
    """Require JSON storage for personalized applications."""
    if path.suffix.lower() != ".json":
        raise ApplicationStorageError(
            "Personalized applications must use a .json file."
        )


def save_personalized_application(
    application: PersonalizedApplication,
    output_path: str | Path,
) -> Path:
    """Save a validated personalized application as private JSON."""
    path = Path(output_path).expanduser().resolve()
    _validate_json_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        path.write_text(
            application.model_dump_json(indent=2),
            encoding="utf-8",
        )
    except OSError as error:
        raise ApplicationStorageError(
            f"Unable to save personalized application: {path}"
        ) from error

    return path


def load_personalized_application(
    input_path: str | Path,
) -> PersonalizedApplication:
    """Load and validate a personalized-application JSON file."""
    path = Path(input_path).expanduser().resolve()
    _validate_json_path(path)

    if not path.is_file():
        raise ApplicationStorageError(
            f"Personalized application does not exist: {path}"
        )

    try:
        return PersonalizedApplication.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise ApplicationStorageError(
            f"Unable to load a valid personalized application: {path}"
        ) from error