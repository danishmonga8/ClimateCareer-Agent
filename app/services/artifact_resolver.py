"""Private local resolution of opaque Phase 8 artifact references.

Registry records deliberately contain only an opaque identifier, workspace binding,
kind, relative location, and digest.  Trusted workspace-root configuration is
injected separately and never selected from registry content.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from app.models.candidate import CandidateProfile
from app.models.evidence import EvidenceBank
from app.services.evidence_repository import load_evidence_bank
from app.services.profile_service import load_candidate_profile


class ArtifactResolutionError(ValueError):
    """Sanitized artifact resolution failure with no path or registry detail."""


Registry = Mapping[str, Mapping[str, str]]
TrustedRoots = Mapping[str, str | Path]


@dataclass(frozen=True, repr=False)
class TrustedArtifactResolver:
    """Resolver configured by a trusted workspace owner, never by a registry row."""

    _registry: Registry = field(repr=False)
    _approved_roots: TrustedRoots = field(repr=False)

    def profile(self, reference: str, workspace_id: str) -> CandidateProfile:
        return resolve_profile(reference, self._registry, workspace_id, self._approved_roots)

    def evidence(self, reference: str, workspace_id: str) -> EvidenceBank:
        return resolve_evidence(reference, self._registry, workspace_id, self._approved_roots)


def load_private_registry(registry_path: str | Path) -> dict[str, dict[str, str]]:
    """Load private metadata internally; callers must not serialize this result."""
    try:
        payload = json.loads(Path(registry_path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError
        return {
            str(reference): {str(key): str(value) for key, value in entry.items()}
            for reference, entry in payload.items()
            if isinstance(entry, dict)
        }
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ArtifactResolutionError(
            "Artifact registry is unavailable or incompatible."
        ) from error


def resolve_profile(
    reference: str,
    registry: Registry,
    workspace_id: str,
    approved_roots: TrustedRoots,
) -> CandidateProfile:
    """Resolve one profile transiently after strict trusted-root validation."""
    try:
        return load_candidate_profile(
            _registered_path(reference, registry, "profile", workspace_id, approved_roots)
        )
    except (ArtifactResolutionError, OSError, TypeError, ValueError) as error:
        raise ArtifactResolutionError(
            "Profile artifact reference is unavailable or incompatible."
        ) from error


def resolve_evidence(
    reference: str,
    registry: Registry,
    workspace_id: str,
    approved_roots: TrustedRoots,
) -> EvidenceBank:
    """Resolve one evidence bank transiently after strict trusted-root validation."""
    try:
        return load_evidence_bank(
            _registered_path(reference, registry, "evidence", workspace_id, approved_roots)
        )
    except (ArtifactResolutionError, OSError, TypeError, ValueError) as error:
        raise ArtifactResolutionError(
            "Evidence artifact reference is unavailable or incompatible."
        ) from error


def _registered_path(
    reference: str,
    registry: Registry,
    kind: str,
    workspace_id: str,
    approved_roots: TrustedRoots,
) -> Path:
    """Return an internal transient path only after containment and digest checks."""
    try:
        if not reference or not workspace_id:
            raise ValueError
        entry = registry[reference]
        if set(entry) != {"workspace_id", "artifact_id", "kind", "relative_path", "sha256"}:
            raise ValueError
        if entry["artifact_id"] != reference or entry["workspace_id"] != workspace_id:
            raise ValueError
        if entry["kind"] != kind:
            raise ValueError
        relative_text = entry["relative_path"]
        relative = Path(relative_text)
        if (
            not relative_text
            or relative.is_absolute()
            or relative.drive
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise ValueError
        configured_root = approved_roots[workspace_id]
        root = Path(configured_root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError
        candidate = root
        # Reject every link component before resolution so no in-root link can redirect.
        for component in relative.parts:
            candidate = candidate / component
            if candidate.is_symlink():
                raise ValueError
        final_target = candidate.resolve(strict=True)
        if (
            not final_target.is_relative_to(root)
            or final_target.is_symlink()
            or not final_target.is_file()
        ):
            raise ValueError
        if hashlib.sha256(final_target.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError
        return final_target
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise ArtifactResolutionError(
            "Artifact reference is unavailable, stale, or incompatible."
        ) from error
