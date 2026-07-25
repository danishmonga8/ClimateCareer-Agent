"""Private JSON storage for validated job-discovery snapshots."""

from pathlib import Path

from pydantic import ValidationError

from app.models.discovery import DiscoverySnapshot


class DiscoveryStorageError(ValueError):
    """Raised when a discovery snapshot cannot be loaded or stored."""


def _validate_json_path(path: Path) -> None:
    if path.suffix.lower() != ".json":
        raise DiscoveryStorageError("Discovery snapshots must use a .json file.")


def save_discovery_snapshot(
    snapshot: DiscoverySnapshot,
    output_path: str | Path,
) -> Path:
    """Atomically save one validated discovery snapshot as private JSON."""
    path = Path(output_path).expanduser().resolve()
    _validate_json_path(path)
    temporary_path = path.with_name(f"{path.name}.temporary")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            snapshot.model_dump_json(indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(path)
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        raise DiscoveryStorageError(f"Unable to save discovery snapshot: {path}") from error

    return path


def load_discovery_snapshot(input_path: str | Path) -> DiscoverySnapshot:
    """Load and validate one private discovery snapshot."""
    path = Path(input_path).expanduser().resolve()
    _validate_json_path(path)

    if not path.is_file():
        raise DiscoveryStorageError(f"Discovery snapshot does not exist: {path}")

    try:
        return DiscoverySnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError) as error:
        raise DiscoveryStorageError(f"Unable to load a valid discovery snapshot: {path}") from error
