"""Tests for the initial ClimateCareer-Agent environment."""

import fitz
import openai
import pydantic
import streamlit


def test_phase_one_dependencies_are_available() -> None:
    """Confirm that essential Phase 1 packages can be imported."""
    assert pydantic.VERSION
    assert fitz.VersionBind
    assert streamlit.__version__
    assert openai.__version__