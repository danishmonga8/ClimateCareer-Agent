"""Tests for secure document validation."""

from pathlib import Path

from app.services.document_service import validate_document


def test_valid_pdf_receives_document_fingerprint(tmp_path: Path) -> None:
    """A valid PDF should receive stable metadata and a SHA-256 fingerprint."""
    document = tmp_path / "sample_cv.pdf"
    document.write_bytes(b"%PDF-1.4\nSample CV content")

    result = validate_document(document)

    assert result.filename == "sample_cv.pdf"
    assert result.extension == ".pdf"
    assert result.size_bytes > 0
    assert len(result.sha256_digest) == 64
