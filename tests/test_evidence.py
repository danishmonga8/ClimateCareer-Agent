"""Tests for the candidate evidence bank."""

import pytest
from pydantic import ValidationError

from app.models.evidence import EvidenceRecord, EvidenceStatus


def test_unverified_claim_cannot_be_used_in_resume() -> None:
    """Unsupported claims must be blocked from application documents."""
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id="skill-001",
            claim="Ten years of production MLOps experience",
            source_document="sample_cv.pdf",
            confidence_score=0.1,
            status=EvidenceStatus.REQUIRES_CONFIRMATION,
            allowed_in_resume=True,
            allowed_in_cover_letter=False,
            requires_confirmation=True,
        )