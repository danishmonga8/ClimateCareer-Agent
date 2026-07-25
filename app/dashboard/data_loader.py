"""Safe aggregation of dashboard metadata and existing private artifacts."""

from dataclasses import dataclass
from pathlib import Path

from app.models.dashboard_review import DashboardReviewRecord, DashboardWorkspace
from app.models.discovery import DiscoveredJob
from app.models.personalization import PersonalizedApplication
from app.models.scoring import JobRelevanceScore
from app.services.dashboard_repository import load_dashboard_workspace
from app.services.discovery_repository import DiscoveryStorageError, load_discovery_snapshot
from app.services.personalization_repository import (
    ApplicationStorageError,
    load_personalized_application,
)
from app.services.scoring_repository import ScoringStorageError, load_scoring_result


@dataclass(frozen=True)
class DashboardJobView:
    """One review record with safely loaded optional artifact data."""

    record: DashboardReviewRecord
    job: DiscoveredJob | None
    score: JobRelevanceScore | None
    application: PersonalizedApplication | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DashboardLoadResult:
    """Workspace data and sanitized non-fatal artifact warnings."""

    workspace: DashboardWorkspace
    jobs: tuple[DashboardJobView, ...]
    warnings: tuple[str, ...] = ()


def _artifact_path(workspace_path: Path, reference: str) -> Path:
    candidate = Path(reference)
    return candidate if candidate.is_absolute() else workspace_path.parent / candidate


def _matching_job(record: DashboardReviewRecord, snapshot_path: Path) -> DiscoveredJob | None:
    snapshot = load_discovery_snapshot(snapshot_path)
    matches = [
        job
        for job in snapshot.jobs
        if (
            job.source == record.source
            and job.source_board == record.source_board
            and job.source_job_id == record.source_job_id
        )
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def load_dashboard_data(workspace_path: str | Path) -> DashboardLoadResult:
    """Load the workspace and artifacts without exposing path or parser failures."""
    resolved_workspace = Path(workspace_path).expanduser().resolve()
    workspace = load_dashboard_workspace(resolved_workspace)
    views: list[DashboardJobView] = []
    workspace_warnings: list[str] = []

    for record in workspace.records:
        warnings: list[str] = []
        job: DiscoveredJob | None = None
        score: JobRelevanceScore | None = None
        application: PersonalizedApplication | None = None
        try:
            job = _matching_job(
                record,
                _artifact_path(resolved_workspace, record.artifacts.discovery_snapshot),
            )
            if job is None:
                warnings.append("The linked discovery snapshot has no unique matching job.")
        except DiscoveryStorageError:
            warnings.append("The linked discovery snapshot is unavailable or invalid.")

        if record.artifacts.scoring_result:
            try:
                score = load_scoring_result(
                    _artifact_path(resolved_workspace, record.artifacts.scoring_result)
                )
            except ScoringStorageError:
                warnings.append("The optional scoring result is unavailable or invalid.")

        if record.artifacts.personalized_application:
            try:
                application = load_personalized_application(
                    _artifact_path(
                        resolved_workspace,
                        record.artifacts.personalized_application,
                    )
                )
            except ApplicationStorageError:
                warnings.append("The optional application material is unavailable or invalid.")

        views.append(
            DashboardJobView(
                record=record,
                job=job,
                score=score,
                application=application,
                warnings=tuple(warnings),
            )
        )
        workspace_warnings.extend(warnings)

    return DashboardLoadResult(
        workspace=workspace,
        jobs=tuple(views),
        warnings=tuple(workspace_warnings),
    )
