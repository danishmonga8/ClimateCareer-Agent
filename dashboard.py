"""Local Streamlit Human Approval Dashboard; it never performs external actions."""

from pathlib import Path

import streamlit as st

from app.dashboard.components import status_label
from app.dashboard.data_loader import DashboardJobView, load_dashboard_data
from app.dashboard.filters import QueueFilters, filter_queue, sort_queue
from app.dashboard.views import (
    render_audit_timeline,
    render_job_detail,
    render_materials,
    render_overview,
    render_score,
)
from app.models.dashboard_review import (
    DashboardReviewAction,
    DashboardReviewStatus,
    DashboardWorkspace,
)
from app.services.audit_timeline_service import AuditTimelineService
from app.services.autofill_dashboard_service import (
    AutofillDashboardError,
    AutofillDashboardService,
)
from app.services.dashboard_repository import (
    DashboardStorageError,
    save_dashboard_workspace,
    save_updated_dashboard_workspace,
)
from app.services.dashboard_review_service import (
    DashboardReviewError,
    apply_dashboard_decision,
    resubmit_for_review,
)
from app.services.quality_control_service import QualityStatus, check_review_quality
from app.workflows.orchestration import WorkflowOrchestrationError, WorkflowOrchestrator
from app.workflows.repository import find_workflow_for_job
from app.workflows.state import WorkflowDecision

st.set_page_config(page_title="Human Approval Dashboard", page_icon="✓", layout="wide")


def _workspace_input() -> Path:
    with st.sidebar:
        st.header("Review workspace")
        value = st.text_input(
            "Private workspace JSON",
            value="documents/private/dashboard_workspace.json",
            help="This local file references existing private artifacts.",
        )
        reviewer = st.text_input("Reviewer label", value="Local reviewer")
        evidence = st.text_input("Evidence bank JSON", value="documents/private/evidence_bank.json")
        st.session_state["reviewer_label"] = reviewer
        st.session_state["evidence_path"] = evidence
    return Path(value)


def _load(path: Path):
    try:
        return load_dashboard_data(path)
    except DashboardStorageError:
        st.info("Choose a valid private workspace JSON to begin reviewing jobs.")
        if st.button("Create an empty private workspace"):
            try:
                save_dashboard_workspace(DashboardWorkspace(), path)
                st.success(
                    "Empty workspace created. Add redacted artifact references as documented, then refresh."
                )
            except DashboardStorageError:
                st.error("The workspace could not be created. Check the location and try again.")
        return None


def _sidebar_filters(views: tuple[DashboardJobView, ...]) -> tuple[QueueFilters, str]:
    with st.sidebar:
        st.header("Filter queue")
        search = st.text_input("Search title, company, location, or source")
        statuses = st.multiselect(
            "Review status",
            list(DashboardReviewStatus),
            format_func=status_label,
        )
        scores = st.slider("Score range", 0, 100, (0, 100))
        include_missing_scores = st.checkbox("Include jobs without scores", value=True)
        companies = sorted({view.job.company for view in views if view.job})
        sources = sorted({view.job.source.value for view in views if view.job})
        locations = sorted({view.job.location or "Unspecified" for view in views if view.job})
        selected_companies = st.multiselect("Company", companies)
        selected_sources = st.multiselect("Source", sources)
        selected_locations = st.multiselect("Location", locations)
        discovered = st.date_input("Discovery date range", value=())
        sort_by = st.selectbox("Sort queue", ["Highest score", "Oldest discovered", "Company A–Z"])
    start = discovered[0] if isinstance(discovered, tuple) and len(discovered) == 2 else None
    end = discovered[1] if isinstance(discovered, tuple) and len(discovered) == 2 else None
    return (
        QueueFilters(
            search=search,
            statuses=frozenset(statuses),
            minimum_score=float(scores[0]),
            maximum_score=float(scores[1]),
            include_missing_scores=include_missing_scores,
            companies=frozenset(selected_companies),
            sources=frozenset(selected_sources),
            locations=frozenset(selected_locations),
            discovered_from=start,
            discovered_to=end,
        ),
        sort_by,
    )


def _load_current_review_context(
    workspace_path: Path,
    job_key: str,
) -> tuple[DashboardWorkspace, DashboardJobView | None]:
    """Reload the workspace and linked materials before a decision."""
    current_data = load_dashboard_data(workspace_path)
    current_view = next(
        (candidate for candidate in current_data.jobs if candidate.record.job_key == job_key),
        None,
    )
    return current_data.workspace, current_view


@st.dialog("Confirm internal review decision")
def _confirm_decision(
    workspace_path: Path,
    view: DashboardJobView,
    action: DashboardReviewAction | None,
) -> None:
    label = "Return to review" if action is None else action.value.replace("_", " ").title()
    st.write(f"Current revision: {view.record.revision}")
    st.warning(
        "This records an internal decision only. It does not submit an application or contact anyone."
    )
    note = st.text_area(
        "Reason or reviewer note",
        help="A reason is required for rejection and revision requests.",
    )
    confirmed = st.checkbox(
        "I confirm this internal decision", key=f"confirm-{view.record.job_key}"
    )
    if st.button(label, type="primary", disabled=not confirmed):
        try:
            checkpoint_directory = workspace_path.parent / "workflow_checkpoints"
            quality = check_review_quality(
                workspace_path,
                view.record.job_key,
                view.record.revision,
                evidence_path=st.session_state.get("evidence_path"),
                workflow_directory=checkpoint_directory
                if find_workflow_for_job(view.record.job_key, checkpoint_directory)
                else None,
            )
            if quality.status == QualityStatus.BLOCKED:
                raise DashboardReviewError("Quality checks blocked this internal approval.")
            workflow = find_workflow_for_job(view.record.job_key, checkpoint_directory)
            if workflow is not None:
                workflow_action = (
                    WorkflowDecision.REVISION_READY.value
                    if action is None
                    else {
                        DashboardReviewAction.APPROVED: WorkflowDecision.APPROVE.value,
                        DashboardReviewAction.REVISION_REQUESTED: WorkflowDecision.REQUEST_REVISION.value,
                        DashboardReviewAction.REJECTED: WorkflowDecision.REJECT.value,
                    }[action]
                )
                result = WorkflowOrchestrator(checkpoint_directory).resume(
                    workflow["workflow_id"],
                    {
                        "action": workflow_action,
                        "expected_revision": view.record.revision,
                        "reviewer_label": st.session_state.get("reviewer_label", "").strip(),
                        "reason_or_note": note,
                    },
                )
                if result["stage"].value == "recoverable_failure":
                    raise DashboardReviewError(
                        "Workflow recovery is required before another decision."
                    )
                st.success("Internal workflow decision saved. The dashboard will reload now.")
                st.rerun()
            current, current_view = _load_current_review_context(
                workspace_path,
                view.record.job_key,
            )
            if action is None:
                updated = resubmit_for_review(
                    current,
                    view.record.job_key,
                    view.record.revision,
                    st.session_state.get("reviewer_label", "").strip(),
                    note,
                )
            else:
                updated = apply_dashboard_decision(
                    current,
                    view.record.job_key,
                    action,
                    view.record.revision,
                    st.session_state.get("reviewer_label", "").strip(),
                    note,
                    linked_application=current_view.application if current_view else None,
                )
            save_updated_dashboard_workspace(current, updated, workspace_path)
        except (DashboardReviewError, DashboardStorageError, WorkflowOrchestrationError) as error:
            st.error(str(error))
            return
        st.success("Internal decision saved. The dashboard will reload now.")
        st.rerun()


def _render_controls(workspace_path: Path, view: DashboardJobView) -> None:
    st.subheader("Internal decision")
    st.caption("Approval is for a manual next step only; it is not an application submission.")
    workflow = find_workflow_for_job(
        view.record.job_key,
        workspace_path.parent / "workflow_checkpoints",
    )
    quality = check_review_quality(
        workspace_path,
        view.record.job_key,
        view.record.revision,
        evidence_path=st.session_state.get("evidence_path"),
        workflow_directory=workspace_path.parent / "workflow_checkpoints" if workflow else None,
    )
    st.caption(
        f"Quality status: {quality.status.value.upper()} · warnings: {quality.warning_count} · blocked: {quality.blocking_count}"
    )
    for finding in quality.findings:
        st.write(f"{finding.severity.value.upper()} {finding.code}: {finding.recovery_guidance}")
    if workflow is not None:
        st.caption(f"Workflow stage: {workflow['stage'].value.replace('_', ' ')}")
        if workflow["stage"].value == "recoverable_failure":
            st.warning("Workflow recovery is required before another internal decision.")
    if view.record.status == DashboardReviewStatus.REVISION_REQUESTED:
        if st.button("Mark revision ready for review", key=f"resubmit-{view.record.job_key}"):
            _confirm_decision(workspace_path, view, None)
        return
    if view.record.status in {
        DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP,
        DashboardReviewStatus.REJECTED,
    }:
        st.info("This internal decision is final and cannot be changed here.")
        return
    first, second, third = st.columns(3)
    if first.button(
        "Approve for manual next step", type="primary", key=f"approve-{view.record.job_key}"
    ):
        _confirm_decision(workspace_path, view, DashboardReviewAction.APPROVED)
    if second.button("Request revision", key=f"revision-{view.record.job_key}"):
        _confirm_decision(workspace_path, view, DashboardReviewAction.REVISION_REQUESTED)
    if third.button("Reject", key=f"reject-{view.record.job_key}"):
        _confirm_decision(workspace_path, view, DashboardReviewAction.REJECTED)


def _configured_autofill_service() -> AutofillDashboardService | None:
    """Return an explicitly injected trusted service; rendering never configures one."""
    service = st.session_state.get("_autofill_dashboard_service")
    return service if isinstance(service, AutofillDashboardService) else None


def _configured_audit_timeline_service() -> AuditTimelineService:
    """Return a read-only source adapter; rendering never creates local sessions."""
    configured = st.session_state.get("_audit_timeline_service")
    if isinstance(configured, AuditTimelineService):
        return configured
    autofill = _configured_autofill_service()
    return AuditTimelineService(
        autofill_session_repository=autofill.session_repository if autofill else None
    )


def _render_autofill_session(view: DashboardJobView) -> None:
    """Render sanitized Phase 8 metadata; reads never resolve or mutate artifacts."""
    st.subheader("Controlled field entry")
    st.caption("Local only. Field entry never submits, sends, uploads, or contacts anyone.")
    service = _configured_autofill_service()
    if service is None:
        st.info(
            "No controlled field-entry session is configured. Dashboard rendering will not create one."
        )
        return
    try:
        session = service.read_view(view.record)
    except AutofillDashboardError as error:
        st.warning(str(error))
        return
    if session is None:
        st.info(
            "No prepared local field-entry session exists for this job. Refresh will not create one."
        )
        return
    st.caption(
        f"Session ID: {session.session_id} · Status: {session.status.value.replace('_', ' ')}"
    )
    st.caption(f"Stable job identifier: {session.job_key}")
    st.caption(
        "Revision compatibility: "
        f"{'compatible' if session.revision_compatible else 'mismatch'} "
        f"(expected {session.expected_revision}, current {session.current_revision})"
    )
    st.caption(
        "Material-version compatibility: "
        f"{'compatible' if session.material_version_compatible else 'mismatch'}"
    )
    st.caption(
        "Artifact-reference compatibility: "
        f"{'compatible' if session.artifact_references_compatible else 'mismatch'}"
    )
    quality = session.quality_status.value.upper() if session.quality_status else "UNAVAILABLE"
    st.caption(f"Last fresh quality outcome: {quality} · warnings: {session.quality_warning_count}")
    stage = (
        session.workflow_stage.value.replace("_", " ") if session.workflow_stage else "unavailable"
    )
    st.caption(f"Workflow interruption stage: {stage}")
    metrics = st.columns(4)
    metrics[0].metric("Eligible", session.eligible_count)
    metrics[1].metric("Manual", session.manual_count)
    metrics[2].metric("Selected", session.selected_count)
    metrics[3].metric("Prepared", session.prepared_count)
    metrics = st.columns(4)
    metrics[0].metric("Populated", session.populated_count)
    metrics[1].metric("Skipped", session.skipped_count)
    metrics[2].metric("Blocked", session.blocked_count)
    metrics[3].metric("Fields", len(session.fields))
    st.caption("Field identifiers and classifications")
    for field in session.fields:
        st.write(f"{field.identifier}: {field.classification.value}")
    for code in session.blocking_codes:
        st.warning(f"BLOCKED {code}")
    for guidance in session.recovery_guidance:
        st.caption(f"Recovery: {guidance}")
    if session.status.value == "populated":
        st.success("Prepared for manual field entry.")
        return
    if session.status.value == "cancelled":
        st.info("This local field-entry session was cancelled safely.")
        return
    can_start = not session.blocking_codes and session.status.value == "awaiting_start_confirmation"
    can_populate = (
        not session.blocking_codes and session.status.value == "awaiting_population_confirmation"
    )
    start_confirmed = st.checkbox(
        "I confirm this specific prepared local session",
        key=f"autofill-start-confirm-{session.session_id}",
    )
    if st.button(
        "Confirm prepared session",
        key=f"autofill-start-{session.session_id}",
        disabled=not can_start or not start_confirmed,
    ):
        try:
            service.confirm_start(session)
        except AutofillDashboardError as error:
            st.error(str(error))
        else:
            st.rerun()
    selection_confirmed = st.checkbox(
        "I confirm these exact selected eligible field identifiers",
        key=f"autofill-fields-confirm-{session.session_id}",
    )
    if st.button(
        "Confirm exact selected fields",
        key=f"autofill-populate-{session.session_id}",
        disabled=not can_populate or not selection_confirmed,
    ):
        try:
            service.confirm_population(session)
        except AutofillDashboardError as error:
            st.error(str(error))
        else:
            st.rerun()
    skipped = st.multiselect(
        "Eligible fields to skip manually",
        list(session.selected_identifiers),
        key=f"autofill-skip-fields-{session.session_id}",
        disabled=not can_populate,
    )
    if st.button(
        "Skip selected fields",
        key=f"autofill-skip-{session.session_id}",
        disabled=not can_populate or not skipped,
    ):
        try:
            service.skip(session, tuple(skipped))
        except AutofillDashboardError as error:
            st.error(str(error))
        else:
            st.rerun()
    if st.button(
        "Cancel local field-entry session",
        key=f"autofill-cancel-{session.session_id}",
        disabled=session.status.value
        not in {
            "awaiting_start_confirmation",
            "awaiting_population_confirmation",
        },
    ):
        try:
            service.cancel(session)
        except AutofillDashboardError as error:
            st.error(str(error))
        else:
            st.rerun()


def main() -> None:
    """Render the local-only review dashboard."""
    st.title("Human Approval Dashboard")
    st.caption("Review and record internal decisions. This dashboard never submits applications.")
    workspace_path = _workspace_input()
    data = _load(workspace_path)
    if data is None:
        return
    for warning in dict.fromkeys(data.warnings):
        st.warning(warning)
    render_overview(data.workspace, data.jobs)
    filters, sort_by = _sidebar_filters(data.jobs)
    queue = sort_queue(filter_queue(data.jobs, filters), sort_by)
    st.subheader("Job review queue")
    if not data.jobs:
        st.info(
            "This workspace has no review records yet. Add redacted artifact references to begin."
        )
        return
    if not queue:
        st.info("No jobs match the current filters. Clear or broaden them to continue.")
        return
    labels = {
        view.record.job_key: (
            f"{view.job.title if view.job else 'Unavailable job'} — "
            f"{view.job.company if view.job else 'artifact unavailable'}"
        )
        for view in queue
    }
    selected_key = st.radio("Select a job to review", list(labels), format_func=labels.get)
    selected = next(view for view in queue if view.record.job_key == selected_key)
    for warning in selected.warnings:
        st.warning(warning)
    details, score, materials, history = st.tabs(
        ["Job details", "Score explanation", "Materials", "Review history"]
    )
    with details:
        render_job_detail(selected)
    with score:
        render_score(selected)
    with materials:
        render_materials(selected)
    with history:
        render_audit_timeline(
            data.workspace,
            selected.record.job_key,
            _configured_audit_timeline_service(),
        )
    _render_controls(workspace_path, selected)
    _render_autofill_session(selected)


if __name__ == "__main__":
    main()
