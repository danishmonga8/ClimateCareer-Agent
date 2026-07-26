"""Private JSON storage for candidate evidence banks."""

from pathlib import Path

from pydantic import ValidationError

from app.models.evidence import EvidenceBank


class EvidenceStorageError(ValueError):
    """Raised when an evidence bank cannot be loaded or stored."""


def _validate_json_path(path: Path) -> None:
    """Require JSON storage for evidence banks."""
    if path.suffix.lower() != ".json":
        raise EvidenceStorageError("Evidence banks must use a .json file.")


def save_evidence_bank(
    evidence_bank: EvidenceBank,
    output_path: str | Path,
) -> Path:
    """Save a validated evidence bank as private formatted JSON."""
    path = Path(output_path).expanduser().resolve()
    _validate_json_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        path.write_text(
            evidence_bank.model_dump_json(indent=2),
            encoding="utf-8",
        )
    except OSError as error:
        raise EvidenceStorageError("Unable to save evidence bank.") from error

    return path


def load_evidence_bank(input_path: str | Path) -> EvidenceBank:
    """Load and validate a private evidence-bank JSON file."""
    path = Path(input_path).expanduser().resolve()
    _validate_json_path(path)

    if not path.is_file():
        raise EvidenceStorageError("Evidence bank does not exist.")

    try:
        return EvidenceBank.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise EvidenceStorageError("Unable to load a valid evidence bank.") from error
