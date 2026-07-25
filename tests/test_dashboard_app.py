"""Smoke tests for the local Streamlit dashboard states."""

from pathlib import Path

import pytest


def test_dashboard_renders_empty_workspace(tmp_path) -> None:
    streamlit_testing = pytest.importorskip("streamlit.testing.v1")
    from app.models.dashboard_review import DashboardWorkspace
    from app.services.dashboard_repository import save_dashboard_workspace

    workspace_path = tmp_path / "dashboard.json"
    save_dashboard_workspace(DashboardWorkspace(), workspace_path)
    app = streamlit_testing.AppTest.from_file(str(Path(__file__).parents[1] / "dashboard.py"))
    app.run()
    app.text_input[0].set_value(str(workspace_path))
    app.run()

    assert not app.exception
    assert any("Human Approval Dashboard" in title.value for title in app.title)
    assert any("no review records" in info.value for info in app.info)
