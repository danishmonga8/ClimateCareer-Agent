"""Tests for CV text extraction."""

from pathlib import Path

import fitz

from app.services.cv_parser import parse_cv


def test_pdf_cv_text_is_extracted(tmp_path: Path) -> None:
    """Text should be extracted from a valid searchable PDF."""
    cv_path = tmp_path / "sample_cv.pdf"

    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text(
            (72, 72),
            "Sample Candidate\nPython and environmental data science",
        )
        pdf.save(cv_path)

    result = parse_cv(cv_path)

    assert result.filename == "sample_cv.pdf"
    assert result.page_count == 1
    assert "Sample Candidate" in result.text
    assert "environmental data science" in result.text
    assert len(result.sha256_digest) == 64
