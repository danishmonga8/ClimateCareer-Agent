"""Atomic local persistence for reference-only controlled field-entry sessions."""

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.models.autofill import AutofillSession
from app.services.autofill_audit_service import AutofillAuditEvent


class AutofillStorageError(ValueError):
    """Sanitized failure while reading or atomically persisting one session."""


@dataclass(frozen=True)
class StoredAutofillSession:
    """A reference-only session and its append-only sanitized audit history."""

    session: AutofillSession
    events: tuple[AutofillAuditEvent, ...]


class AutofillSessionRepository:
    """Trusted local storage configured outside controller transition requests."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory).expanduser().resolve()

    def save(self, stored: StoredAutofillSession) -> None:
        """Atomically replace one validated reference-only snapshot."""
        try:
            path = self._path(stored.session.session_id)
            payload = {
                "session": stored.session.model_dump(mode="json"),
                "events": [event.model_dump(mode="json") for event in stored.events],
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f"{path.name}.temporary")
            temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            temporary.replace(path)
        except (OSError, TypeError, ValueError) as error:
            raise AutofillStorageError("Autofill session could not be saved.") from error

    def load(self, session_id: str) -> StoredAutofillSession:
        """Load only serialized metadata; this never resolves artifacts or transitions state."""
        try:
            payload = json.loads(self._path(session_id).read_text(encoding="utf-8"))
            return StoredAutofillSession(
                session=AutofillSession.model_validate(payload["session"]),
                events=tuple(AutofillAuditEvent.model_validate(item) for item in payload["events"]),
            )
        except (
            OSError,
            TypeError,
            ValueError,
            KeyError,
            ValidationError,
            json.JSONDecodeError,
        ) as error:
            raise AutofillStorageError("Autofill session is unavailable or invalid.") from error

    def find_for_job(self, job_key: str) -> StoredAutofillSession | None:
        """Read one unambiguous local session without resolving its artifacts."""
        try:
            if not self._directory.is_dir():
                return None
            matches: list[StoredAutofillSession] = []
            for path in self._directory.glob("*.json"):
                try:
                    stored = self.load(path.stem)
                except AutofillStorageError:
                    continue
                if stored.session.job_key == job_key:
                    matches.append(stored)
            return matches[0] if len(matches) == 1 else None
        except OSError as error:
            raise AutofillStorageError("Autofill session is unavailable or invalid.") from error

    def _path(self, session_id: str) -> Path:
        if not session_id or any(character in session_id for character in '\\/:*?"<>|'):
            raise AutofillStorageError("Autofill session is unavailable or invalid.")
        return self._directory / f"{session_id}.json"
