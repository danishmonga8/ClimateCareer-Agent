"""Durable, sanitized snapshots for interrupted local autofill workflows."""

from pathlib import Path

from pydantic import ValidationError

from app.models.autofill import AutofillWorkflowSnapshot


class AutofillWorkflowCheckpointError(ValueError):
    """Sanitized local checkpoint failure."""


class AutofillWorkflowRepository:
    """Trusted local storage that never appears in workflow transition inputs."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory).expanduser().resolve()

    def save(self, snapshot: AutofillWorkflowSnapshot) -> None:
        try:
            target = self._path(snapshot.workflow_id)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f"{target.name}.temporary")
            temporary.write_text(snapshot.model_dump_json(), encoding="utf-8")
            temporary.replace(target)
        except (OSError, TypeError, ValueError) as error:
            raise AutofillWorkflowCheckpointError(
                "Autofill workflow checkpoint could not be saved."
            ) from error

    def load(self, workflow_id: str) -> AutofillWorkflowSnapshot:
        try:
            return AutofillWorkflowSnapshot.model_validate_json(
                self._path(workflow_id).read_text(encoding="utf-8")
            )
        except (OSError, TypeError, ValueError, ValidationError) as error:
            raise AutofillWorkflowCheckpointError(
                "Autofill workflow checkpoint is unavailable or incompatible."
            ) from error

    def _path(self, workflow_id: str) -> Path:
        if not workflow_id or any(character in workflow_id for character in '\\/:*?"<>|'):
            raise AutofillWorkflowCheckpointError(
                "Autofill workflow checkpoint is unavailable or incompatible."
            )
        return self._directory / f"{workflow_id}.json"
