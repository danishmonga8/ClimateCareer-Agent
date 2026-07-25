"""Small, accessible presentation helpers for the Streamlit dashboard."""

import streamlit as st

from app.models.dashboard_review import DashboardReviewStatus

STATUS_LABELS = {
    DashboardReviewStatus.AWAITING_REVIEW: "Awaiting review",
    DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP: "Approved for manual next step",
    DashboardReviewStatus.REVISION_REQUESTED: "Revision requested",
    DashboardReviewStatus.REJECTED: "Rejected",
}


def status_label(status: DashboardReviewStatus) -> str:
    """Return status text that does not imply an external submission."""
    return STATUS_LABELS[status]


def render_status(status: DashboardReviewStatus) -> None:
    """Render a text status using colour as a secondary signal only."""
    label = status_label(status)
    if status == DashboardReviewStatus.APPROVED_FOR_MANUAL_NEXT_STEP:
        st.success(f"✓ {label}")
    elif status == DashboardReviewStatus.REVISION_REQUESTED:
        st.warning(f"↺ {label}")
    elif status == DashboardReviewStatus.REJECTED:
        st.error(f"× {label}")
    else:
        st.info(f"• {label}")
