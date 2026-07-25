"""Safe Streamlit views for dashboard detail and material review."""

import streamlit as st

from app.dashboard.components import render_status
from app.dashboard.data_loader import DashboardJobView
from app.models.dashboard_review import (
    DashboardAuditEvent,
    DashboardReviewStatus,
    DashboardWorkspace,
)


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
                f"{event.action.value.replace('_', ' ')} by {event.reviewer_label}"
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


def render_audit(workspace: DashboardWorkspace, job_key: str) -> None:
    """Show immutable events in chronological order."""
    events: list[DashboardAuditEvent] = [
        event for event in workspace.audit_events if event.job_key == job_key
    ]
    if not events:
        st.info("No internal review history exists for this job yet.")
        return
    for event in events:
        st.write(
            f"{event.timestamp.strftime('%Y-%m-%d %H:%M UTC')} — "
            f"{event.previous_status.value} → {event.new_status.value}"
        )
        st.caption(
            f"Action: {event.action.value.replace('_', ' ')} · Reviewer: {event.reviewer_label}"
        )
        if event.reason_or_note:
            st.write(event.reason_or_note)
