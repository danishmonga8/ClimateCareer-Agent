"""Offline trust-boundary tests for opaque local artifact resolution."""

import hashlib
from pathlib import Path

import pytest

from app.models.candidate import CandidateProfile, ContactInformation
from app.models.evidence import EvidenceBank
from app.services.artifact_resolver import (
    ArtifactResolutionError,
    TrustedArtifactResolver,
    _registered_path,
    resolve_evidence,
    resolve_profile,
)
from app.services.evidence_repository import save_evidence_bank
from app.services.profile_service import save_candidate_profile


def _profile() -> CandidateProfile:
    return CandidateProfile(
        full_name="Fictional Candidate",
        contact=ContactInformation(emails=["candidate@example.test"], phone="555-0100"),
        source_document="fictional-source.pdf",
    )


def _entry(reference: str, workspace: str, kind: str, path: Path, root: Path) -> dict[str, str]:
    return {
        "workspace_id": workspace,
        "artifact_id": reference,
        "kind": kind,
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_external_trusted_root_resolves_valid_artifacts_without_leaking_paths(tmp_path) -> None:
    root = tmp_path / "approved"
    root.mkdir()
    profile_path = root / "profile.json"
    evidence_path = root / "evidence.json"
    save_candidate_profile(_profile(), profile_path)
    save_evidence_bank(
        EvidenceBank(
            candidate_name="Fictional Candidate",
            source_document="fictional-source.pdf",
            source_sha256="a" * 64,
        ),
        evidence_path,
    )
    registry = {
        "artifact:profile:1": _entry(
            "artifact:profile:1", "workspace:1", "profile", profile_path, root
        ),
        "artifact:evidence:1": _entry(
            "artifact:evidence:1", "workspace:1", "evidence", evidence_path, root
        ),
    }

    assert (
        resolve_profile(
            "artifact:profile:1", registry, "workspace:1", {"workspace:1": root}
        ).full_name
        == "Fictional Candidate"
    )
    assert (
        resolve_evidence(
            "artifact:evidence:1", registry, "workspace:1", {"workspace:1": root}
        ).records
        == []
    )
    trusted = TrustedArtifactResolver(registry, {"workspace:1": root})
    assert trusted.profile("artifact:profile:1", "workspace:1").full_name == "Fictional Candidate"
    with pytest.raises(ArtifactResolutionError) as captured:
        _registered_path(
            "artifact:profile:1", registry, "profile", "workspace:missing", {"workspace:1": root}
        )
    assert str(root) not in str(captured.value)


@pytest.mark.parametrize("relative_path", ["../outside.json", "", "C:/outside.json"])
def test_registry_cannot_select_or_escape_trusted_root(tmp_path, relative_path) -> None:
    root = tmp_path / "approved"
    root.mkdir()
    profile_path = root / "profile.json"
    save_candidate_profile(_profile(), profile_path)
    record = _entry("artifact:profile:1", "workspace:1", "profile", profile_path, root)
    record["relative_path"] = relative_path
    record["root"] = str(tmp_path / "outside")

    with pytest.raises(
        ArtifactResolutionError, match="unavailable, stale, or incompatible"
    ) as captured:
        _registered_path(
            "artifact:profile:1",
            {"artifact:profile:1": record},
            "profile",
            "workspace:1",
            {"workspace:1": root},
        )
    assert str(root) not in str(captured.value)
    assert "outside" not in str(captured.value)


def test_digest_kind_symlink_and_prefix_confusion_fail_closed(tmp_path) -> None:
    root = tmp_path / "approved"
    root.mkdir()
    profile_path = root / "profile.json"
    save_candidate_profile(_profile(), profile_path)
    registry = {
        "artifact:profile:1": _entry(
            "artifact:profile:1", "workspace:1", "profile", profile_path, root
        )
    }
    registry["artifact:profile:1"]["kind"] = "evidence"
    with pytest.raises(ArtifactResolutionError):
        _registered_path(
            "artifact:profile:1", registry, "profile", "workspace:1", {"workspace:1": root}
        )


def test_tampered_artifact_or_cross_workspace_binding_fails_again_on_fresh_resolution(
    tmp_path,
) -> None:
    root = tmp_path / "approved"
    root.mkdir()
    profile_path = root / "profile.json"
    save_candidate_profile(_profile(), profile_path)
    registry = {
        "artifact:profile:1": _entry(
            "artifact:profile:1", "workspace:1", "profile", profile_path, root
        )
    }
    _registered_path(
        "artifact:profile:1", registry, "profile", "workspace:1", {"workspace:1": root}
    )
    profile_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ArtifactResolutionError) as captured:
        _registered_path(
            "artifact:profile:1", registry, "profile", "workspace:1", {"workspace:1": root}
        )
    assert str(profile_path) not in str(captured.value)
    registry["artifact:profile:1"]["workspace_id"] = "workspace:other"
    with pytest.raises(ArtifactResolutionError):
        _registered_path(
            "artifact:profile:1", registry, "profile", "workspace:1", {"workspace:1": root}
        )
    registry["artifact:profile:1"] = _entry(
        "artifact:profile:1", "workspace:1", "profile", profile_path, root
    )
    registry["artifact:profile:1"]["sha256"] = "b" * 64
    with pytest.raises(ArtifactResolutionError):
        _registered_path(
            "artifact:profile:1", registry, "profile", "workspace:1", {"workspace:1": root}
        )
    outside_root = tmp_path / "approved-other"
    outside_root.mkdir()
    outside = outside_root / "profile.json"
    save_candidate_profile(_profile(), outside)
    registry["artifact:profile:1"] = {
        **_entry("artifact:profile:1", "workspace:1", "profile", outside, outside_root),
        "relative_path": "../approved-other/profile.json",
    }
    with pytest.raises(ArtifactResolutionError):
        _registered_path(
            "artifact:profile:1", registry, "profile", "workspace:1", {"workspace:1": root}
        )
    link = root / "link.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks are unavailable in this local test environment.")
    registry["artifact:profile:1"] = _entry(
        "artifact:profile:1", "workspace:1", "profile", link, root
    )
    with pytest.raises(ArtifactResolutionError):
        _registered_path(
            "artifact:profile:1", registry, "profile", "workspace:1", {"workspace:1": root}
        )
