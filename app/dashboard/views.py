"""Safe Streamlit views for dashboard detail and material review."""

from datetime import UTC, datetime, time

import streamlit as st

from app.dashboard.components import render_status
from app.dashboard.data_loader import DashboardJobView
from app.models.audit_timeline import (
    AuditTimelineAction,
    AuditTimelineCategory,
    AuditTimelineFilters,
    AuditTimelinePageRequest,
    AuditTimelineSource,
    AuditTimelineStatus,
)
from app.models.dashboard_review import (
    DashboardReviewStatus,
    DashboardWorkspace,
)
from app.services.audit_timeline_service import AuditTimelineService


def render_overview(workspace: DashboardWorkspace, views: tuple[DashboardJobView, ...]) -> None:
    """Show review counts and recent internal activity."""
    counts = {status: 0 for status in DashboardReviewStatus}
    for record in workspace.records:
        counts[record.status] += 1
    columns = st.columns(5)
    columns[0].metric("Total discovered jobs", len(views))
    columns[1].metric("Awaiting review", counts[DashboardReviewStatus.AWAITING_REVIEW])
    columns[2].metric("Approved", counts[DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP])
    columns[3].metric("Revision requested", counts[DashboardReviewStatus.REVISION_REQUESTED])
    columns[4].metric("Rejected", counts[DashboardReviewStatus.REJECTED])
    if workspace.audit_events:
        st.subheader("Recent internal activity")
        for event in reversed(workspace.audit_events[-5:]):
            st.caption(
                f"{event.timestamp.strftime('%Y-%m-%d %H:%M UTC')} — "
                f"{event.action.value.replace('_', ' ')} - Reviewer recorded"
            )
    else:
        st.caption("No internal review actions have been recorded yet.")


def render_job_detail(view: DashboardJobView) -> None:
    """Render trusted job fields and automation disclosures as plain text."""
    if view.job is None:
        st.warning("Trusted job details are unavailable for this review record.")
        return
    job = view.job
    st.subheader(f"{job.title} — {job.company}")
    render_status(view.record.status)
    st.caption(
        f"{job.location or 'Location unspecified'} · {job.source.value} · "
        f"discovered {job.discovered_at.strftime('%Y-%m-%d')}"
    )
    st.markdown("**Trusted source information**")
    st.write(f"Source board: {job.source_board}")
    st.text(str(job.job_url))
    st.markdown("**Normalized job description**")
    st.text(job.description)


def render_score(view: DashboardJobView) -> None:
    """Render explainable scores, gaps, constraints, and uncertainty."""
    if view.score is None:
        st.info("No score is available for this job yet.")
        return
    score = view.score
    st.metric("Overall relevance score", f"{score.overall_score:.0f}/100")
    st.warning(
        "Automated recommendation — review the evidence and constraints before deciding: "
        f"{score.recommendation.value.replace('_', ' ')}"
    )
    for component in score.components:
        with st.expander(component.category.value.replace("_", " ").title()):
            st.write(f"{component.awarded_points:g}/{component.maximum_points:g} points")
            st.write(component.rationale)
            if component.matched_evidence:
                st.write("Matched evidence: " + "; ".join(component.matched_evidence))
            if component.missing_items:
                st.write("Gaps: " + "; ".join(component.missing_items))
    if score.hard_constraints:
        st.markdown("**Hard constraints**")
        for constraint in score.hard_constraints:
            st.write(
                f"{constraint.status.value}: {constraint.requirement} — {constraint.explanation}"
            )
    if score.uncertainty_notes:
        st.markdown("**Uncertainties and warnings**")
        for note in score.uncertainty_notes:
            st.warning(note)


def render_materials(view: DashboardJobView) -> None:
    """Preview linked material without regenerating or editing it."""
    application = view.application
    if application is None:
        st.info("No linked application materials are available for this job.")
        return
    resume, cover_letter, answers, evidence = st.tabs(
        ["Tailored résumé", "Cover letter", "Application answers", "Supporting evidence"]
    )
    with resume:
        st.write(application.resume.professional_headline or "No tailored headline available.")
        st.write(application.resume.professional_summary or "No tailored summary available.")
        for claim in application.resume.claims:
            st.write(f"• {claim.text}")
    with cover_letter:
        st.text(application.cover_letter.body)
    with answers:
        if not application.application_answers:
            st.info("No application answers are available.")
        for answer in application.application_answers:
            st.write(answer.question)
            st.text(answer.answer or "Awaiting human confirmation")
    with evidence:
        claims = application.resume.claims + application.cover_letter.claims
        if not claims:
            st.info("No supporting evidence is linked to this material.")
        for claim in claims:
            st.write(claim.text)


def render_audit_timeline(
    workspace: DashboardWorkspace,
    job_key: str,
    service: AuditTimelineService,
) -> None:
    """Render a selected-job audit projection without changing any audit source."""
    key_prefix = f"audit-timeline-{job_key}"
    sources = st.multiselect(
        "Audit sources",
        [source.value for source in AuditTimelineSource],
        format_func=lambda value: value.replace("_", " ").title(),
        key=f"{key_prefix}-sources",
    )
    categories = st.multiselect(
        "Event categories",
        [category.value for category in AuditTimelineCategory],
        format_func=lambda value: value.replace("_", " ").title(),
        key=f"{key_prefix}-categories",
    )
    actions = st.multiselect(
        "Actions",
        [action.value for action in AuditTimelineAction],
        format_func=lambda value: value.replace("_", " ").title(),
        key=f"{key_prefix}-actions",
    )
    statuses = st.multiselect(
        "Statuses",
        [status.value for status in AuditTimelineStatus],
        format_func=lambda value: value.replace("_", " ").title(),
        key=f"{key_prefix}-statuses",
    )
    selected_dates = st.date_input("Audit time range", value=(), key=f"{key_prefix}-dates")
    from_timestamp = None
    to_timestamp = None
    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        from_timestamp = datetime.combine(selected_dates[0], time.min, tzinfo=UTC)
        to_timestamp = datetime.combine(selected_dates[1], time.max, tzinfo=UTC)
    filters = AuditTimelineFilters(
        sources=frozenset(AuditTimelineSource(value) for value in sources),
        categories=frozenset(AuditTimelineCategory(value) for value in categories),
        actions=frozenset(AuditTimelineAction(value) for value in actions),
        statuses=frozenset(AuditTimelineStatus(value) for value in statuses),
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )
    signature = filters.model_dump_json()
    signature_key = f"{key_prefix}-filter-signature"
    cursor_key = f"{key_prefix}-cursor"
    if st.session_state.get(signature_key) != signature:
        st.session_state[signature_key] = signature
        st.session_state[cursor_key] = None
    page = service.page(
        workspace,
        job_key,
        filters=filters,
        request=AuditTimelinePageRequest(cursor=st.session_state.get(cursor_key)),
    )
    metrics = st.columns(4)
    metrics[0].metric("Visible events", page.counts.total)
    metrics[1].metric("Review events", page.counts.dashboard_review)
    metrics[2].metric("Autofill events", page.counts.autofill)
    metrics[3].metric("Integrity warnings", len(page.integrity_findings))
    for finding in page.integrity_findings:
        st.warning(f"{finding.code}: {finding.message}")
        st.caption(f"Recovery: {finding.recovery_guidance}")
    if page.checkpoint_summary is not None:
        summary = page.checkpoint_summary
        st.caption(
            f"{summary.label}: {summary.status.value.replace('_', ' ')} "
            f"- {'compatible' if summary.compatible else 'inconsistent'}"
        )
    if not page.entries:
        st.info("No sanitized audit events match the selected filters.")
    for entry in page.entries:
        st.write(
            f"{entry.timestamp.strftime('%Y-%m-%d %H:%M UTC')} - "
            f"{entry.source.value.replace('_', ' ')} - {entry.action.value.replace('_', ' ')}"
        )
        if entry.transition is not None:
            previous = (
                entry.transition.previous.value.replace("_", " ")
                if entry.transition.previous
                else "not recorded"
            )
            current = (
                entry.transition.current.value.replace("_", " ")
                if entry.transition.current
                else "not recorded"
            )
            st.caption(f"Internal status: {previous} -> {current}")
        indicators: list[str] = []
        if entry.note_recorded:
            indicators.append("Review note recorded")
        if entry.reviewer_recorded:
            indicators.append("Reviewer recorded")
        if indicators:
            st.caption(" - ".join(indicators))
    pagination = st.columns(2)
    if pagination[0].button(
        "Earlier audit events",
        key=f"{key_prefix}-next",
        disabled=page.next_cursor is None,
    ):
        st.session_state[cursor_key] = page.next_cursor
        st.rerun()
    if pagination[1].button("First audit page", key=f"{key_prefix}-first"):
        st.session_state[cursor_key] = None
        st.rerun()
