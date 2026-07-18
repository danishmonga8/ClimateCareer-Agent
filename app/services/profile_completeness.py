"""Candidate-profile completeness and manual-input assessment."""

from enum import StrEnum

from pydantic import Field, computed_field

from app.models.candidate import CandidateProfile, StrictModel


class RequirementLevel(StrEnum):
    """When a missing profile field is normally required."""

    ALWAYS_REQUIRED = "always_required"
    APPLICATION_DEPENDENT = "application_dependent"
    OPTIONAL = "optional"


class MissingProfileField(StrictModel):
    """One candidate field that requires manual input."""

    field_path: str = Field(min_length=1)
    label: str = Field(min_length=1)
    question: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    requirement_level: RequirementLevel
    blocks_autofill_when_requested: bool
    must_never_guess: bool = True


class ProfileCompletenessReport(StrictModel):
    """Summary of missing or manually controlled candidate information."""

    missing_fields: list[MissingProfileField] = Field(default_factory=list)
    identity_information_ready: bool

    @computed_field
    @property
    def requires_manual_input(self) -> bool:
        """Return whether any candidate-controlled answers are missing."""
        return bool(self.missing_fields)


def assess_profile_completeness(
    profile: CandidateProfile,
) -> ProfileCompletenessReport:
    """Identify missing information without guessing candidate answers."""
    missing: list[MissingProfileField] = []

    if not profile.contact.emails:
        missing.append(
            MissingProfileField(
                field_path="contact.emails",
                label="Email address",
                question="Which email address should applications use?",
                reason="An application email address is required.",
                requirement_level=RequirementLevel.ALWAYS_REQUIRED,
                blocks_autofill_when_requested=True,
            )
        )

    if not profile.contact.phone:
        missing.append(
            MissingProfileField(
                field_path="contact.phone",
                label="Telephone number",
                question="Which telephone number should applications use?",
                reason="Many application forms require a telephone number.",
                requirement_level=RequirementLevel.APPLICATION_DEPENDENT,
                blocks_autofill_when_requested=True,
            )
        )

    current_education = [
        record
        for record in profile.education
        if record.currently_enrolled
    ]

    if any(record.end_year is None for record in current_education):
        missing.append(
            MissingProfileField(
                field_path="education.expected_completion",
                label="Expected degree completion",
                question="What is your expected PhD completion date?",
                reason="The CV states that the PhD is ongoing but gives no completion date.",
                requirement_level=RequirementLevel.APPLICATION_DEPENDENT,
                blocks_autofill_when_requested=True,
            )
        )

    sensitive_checks = [
        (
            profile.sensitive_information.work_authorization,
            "sensitive_information.work_authorization",
            "Work authorization",
            "What countries or regions are you currently authorized to work in?",
            "Work authorization is a legal declaration.",
        ),
        (
            profile.sensitive_information.visa_sponsorship_required,
            "sensitive_information.visa_sponsorship_required",
            "Visa sponsorship",
            "Will you require employer visa sponsorship?",
            "Visa sponsorship must be answered by the candidate.",
        ),
        (
            profile.sensitive_information.notice_period,
            "sensitive_information.notice_period",
            "Notice period",
            "What is your current notice period or earliest joining date?",
            "The CV does not provide employment availability.",
        ),
        (
            profile.sensitive_information.salary_expectation,
            "sensitive_information.salary_expectation",
            "Salary expectation",
            "What salary range should be used when an application requires it?",
            "Salary expectations must never be inferred.",
        ),
    ]

    for value, field_path, label, question, reason in sensitive_checks:
        if value is None:
            missing.append(
                MissingProfileField(
                    field_path=field_path,
                    label=label,
                    question=question,
                    reason=reason,
                    requirement_level=RequirementLevel.APPLICATION_DEPENDENT,
                    blocks_autofill_when_requested=True,
                )
            )

    identity_ready = bool(
        profile.full_name
        and profile.contact.emails
        and profile.contact.location
    )

    return ProfileCompletenessReport(
        missing_fields=missing,
        identity_information_ready=identity_ready,
    )