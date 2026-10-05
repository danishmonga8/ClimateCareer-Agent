"""Atomic private JSON storage for dashboard review workspaces."""

from pathlib import Path

from pydantic import ValidationError

from app.models.dashboard_review import DashboardWorkspace


class DashboardStorageError(ValueError):
    """Raised when a dashboard workspace cannot be safely persisted."""


def _workspace_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() != ".json":
        raise DashboardStorageError("Dashboard workspaces must use a .json file.")
    return path


def load_dashboard_workspace(input_path: str | Path) -> DashboardWorkspace:
    """Load and validate a private dashboard workspace."""
    path = _workspace_path(input_path)
    if not path.is_file():
        raise DashboardStorageError("Dashboard workspace does not exist.")
    try:
        return DashboardWorkspace.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValidationError) as error:
        raise DashboardStorageError("Unable to load a valid dashboard workspace.") from error


def _atomic_write(workspace: DashboardWorkspace, path: Path) -> Path:
    temporary_path = path.with_name(f"{path.name}.temporary")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(workspace.model_dump_json(indent=2), encoding="utf-8")
        temporary_path.replace(path)
    except OSError as error:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            # The parent may itself be a file or otherwise inaccessible. The
            # original storage failure remains the useful, sanitized error.
            pass
        raise DashboardStorageError("Unable to save dashboard workspace.") from error
    return path


def save_dashboard_workspace(
    workspace: DashboardWorkspace,
    output_path: str | Path,
) -> Path:
    """Create or replace a validated workspace atomically."""
    return _atomic_write(workspace, _workspace_path(output_path))


def save_updated_dashboard_workspace(
    previous: DashboardWorkspace,
    updated: DashboardWorkspace,
    output_path: str | Path,
) -> Path:
    """Persist an update only when current data and audit history are unchanged."""
    path = _workspace_path(output_path)
    current = load_dashboard_workspace(path)
    if current.model_dump(mode="json") != previous.model_dump(mode="json"):
        raise DashboardStorageError("Dashboard workspace changed; reload before saving.")

    prefix_length = len(previous.audit_events)
    if updated.audit_events[:prefix_length] != previous.audit_events:
        raise DashboardStorageError("Dashboard audit history is append-only.")
    if len(updated.audit_events) < prefix_length:
        raise DashboardStorageError("Dashboard audit history cannot be removed.")
    return _atomic_write(updated, path)
