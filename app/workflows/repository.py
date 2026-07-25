"""Atomic, validated local snapshots for LangGraph workflow resume."""

from pathlib import Path

from pydantic import ValidationError

from app.workflows.state import WorkflowState, validate_workflow_state


class WorkflowCheckpointError(ValueError):
    """Raised without exposing checkpoint paths or parser details."""


def _path(directory: str | Path, workflow_id: str) -> Path:
    if not workflow_id or any(character in workflow_id for character in '\\/:*?"<>|'):
        raise WorkflowCheckpointError("Workflow checkpoint identifier is invalid.")
    return Path(directory).expanduser().resolve() / f"{workflow_id}.json"


def save_workflow_checkpoint(state: WorkflowState, directory: str | Path) -> Path:
    """Persist reference-only graph state atomically for later resume."""
    try:
        validated = validate_workflow_state(state)
        path = _path(directory, validated["workflow_id"])
        temporary = path.with_name(f"{path.name}.temporary")
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        temporary.write_text(
            json.dumps(validated, default=lambda value: value.isoformat(), indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
        return path
    except (OSError, TypeError, ValueError) as error:
        raise WorkflowCheckpointError("Unable to save a valid workflow checkpoint.") from error


def load_workflow_checkpoint(workflow_id: str, directory: str | Path) -> WorkflowState:
    """Load a validated local checkpoint while hiding filesystem details."""
    path = _path(directory, workflow_id)
    if not path.is_file():
        raise WorkflowCheckpointError("Workflow checkpoint is unavailable.")
    try:
        import json
        from datetime import datetime

        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        payload["updated_at"] = datetime.fromisoformat(payload["updated_at"])
        return validate_workflow_state(payload)
    except (OSError, TypeError, ValueError, ValidationError, KeyError) as error:
        raise WorkflowCheckpointError(
            "Workflow checkpoint is unavailable or incompatible."
        ) from error


def find_workflow_for_job(job_key: str, directory: str | Path) -> WorkflowState | None:
    """Return one valid local workflow snapshot for a dashboard job, if present."""
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        return None
    matches: list[WorkflowState] = []
    for path in root.glob("*.json"):
        try:
            state = load_workflow_checkpoint(path.stem, root)
        except WorkflowCheckpointError:
            continue
        if state["job_key"] == job_key:
            matches.append(state)
    return matches[0] if len(matches) == 1 else None
