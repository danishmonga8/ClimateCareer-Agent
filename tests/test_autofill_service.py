"""Offline safety tests for controlled local field-entry sessions."""

from app.models.autofill import AutofillSessionStatus, FieldClassification
from app.models.candidate import CandidateProfile, ContactInformation
from app.services.autofill_service import confirm_population, confirm_start, prepare_session


def test_only_allowlisted_existing_values_are_eligible() -> None:
    profile = CandidateProfile(
        full_name="Fictional Candidate",
        contact=ContactInformation(emails=["candidate@example.test"]),
        source_document="fictional.pdf",
    )
    session = prepare_session(
        profile,
        "workspace:fictional",
        "artifact:profile:fictional",
        ("artifact:evidence:fictional",),
        "manual:fictional:1",
        1,
        "material:v1",
        None,
        ("full_name", "email", "salary", "unknown"),
    )
    assert [field.classification for field in session.fields] == [
        FieldClassification.ELIGIBLE,
        FieldClassification.ELIGIBLE,
        FieldClassification.MANUAL,
        FieldClassification.MANUAL,
    ]
    assert all("Fictional Candidate" not in field.model_dump_json() for field in session.fields)


def test_two_confirmations_and_cancellation_never_submit() -> None:
    profile = CandidateProfile(
        full_name="Fictional Candidate",
        contact=ContactInformation(emails=["candidate@example.test"]),
        source_document="fictional.pdf",
    )
    session = prepare_session(
        profile,
        "workspace:fictional",
        "artifact:profile:fictional",
        ("artifact:evidence:fictional",),
        "manual:fictional:1",
        1,
        "material:v1",
        None,
        ("email",),
    )
    assert confirm_start(session, False).status == AutofillSessionStatus.CANCELLED
    started = confirm_start(session, True)
    assert started.status == AutofillSessionStatus.AWAITING_POPULATION_CONFIRMATION
    assert confirm_population(started, True).status == AutofillSessionStatus.POPULATED


def test_sensitive_and_ambiguous_categories_remain_manual() -> None:
    profile = CandidateProfile(
        full_name="Fictional Candidate",
        contact=ContactInformation(
            emails=["candidate@example.test"],
            phone="555-0100",
            location="Fictional City",
        ),
        source_document="fictional.pdf",
    )
    session = prepare_session(
        profile,
        "workspace:fictional",
        "artifact:profile:fictional",
        ("artifact:evidence:fictional",),
        "manual:fictional:1",
        1,
        "material:v1",
        None,
        ("password", "salary", "city", "work_authorization", "email"),
    )

    assert [field.classification for field in session.fields] == [
        FieldClassification.MANUAL,
        FieldClassification.MANUAL,
        FieldClassification.MANUAL,
        FieldClassification.MANUAL,
        FieldClassification.ELIGIBLE,
    ]
