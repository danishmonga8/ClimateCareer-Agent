"""Models for human-supervised application personalization."""

from enum import StrEnum

from pydantic import Field, model_validator

from app.models.candidate import StrictModel
from app.models.evidence import EvidenceRecord, EvidenceStatus


class ApplicationStatus(StrEnum):
    """Human-review status of a personalized application."""

    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED_BY_USER = "approved_by_user"


class ClaimUsage(StrEnum):
    """Application-document location where a claim will be used."""

    RESUME = "resume"
    COVER_LETTER = "cover_letter"
    APPLICATION_ANSWER = "application_answer"


class ApplicationClaim(StrictModel):
    """One evidence-backed claim used in an application document."""

    text: str = Field(min_length=1)
    usage: ClaimUsage
    evidence: list[EvidenceRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence(self) -> "ApplicationClaim":
        """Allow only verified and appropriately permitted evidence."""

        if not self.evidence:
            raise ValueError(
                "Application claims require at least one evidence record."
            )

        for record in self.evidence:
            if (
                record.status != EvidenceStatus.VERIFIED
                or record.requires_confirmation
            ):
                raise ValueError(
                    "Application claims may use only verified evidence."
                )

            if (
                self.usage == ClaimUsage.RESUME
                and not record.allowed_in_resume
            ):
                raise ValueError(
                    "Evidence is not permitted for use in the resume."
                )

            if (
                self.usage == ClaimUsage.COVER_LETTER
                and not record.allowed_in_cover_letter
            ):
                raise ValueError(
                    "Evidence is not permitted for use in the cover letter."
                )

        return self


class TailoredResume(StrictModel):
    """Evidence-backed tailored resume content."""

    professional_headline: str | None = None
    professional_summary: str | None = None
    claims: list[ApplicationClaim] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_resume_usage(self) -> "TailoredResume":
        """Prevent non-resume claims from entering the resume."""

        for claim in self.claims:
            if claim.usage != ClaimUsage.RESUME:
                raise ValueError(
                    "Tailored resume claims must use the resume usage type."
                )

        return self


class TailoredCoverLetter(StrictModel):
    """Evidence-backed tailored cover-letter content."""

    body: str = Field(min_length=1)
    claims: list[ApplicationClaim] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_cover_letter_usage(
        self,
    ) -> "TailoredCoverLetter":
        """Prevent claims intended for other documents from being used."""

        for claim in self.claims:
            if claim.usage != ClaimUsage.COVER_LETTER:
                raise ValueError(
                    "Cover-letter claims must use the cover-letter usage type."
                )

        return self


class ApplicationQuestionAnswer(StrictModel):
    """A draft answer to one application question."""

    question: str = Field(min_length=1)
    answer: str | None = None
    claims: list[ApplicationClaim] = Field(default_factory=list)
    requires_confirmation: bool = True
    confirmation_reason: str | None = None

    @model_validator(mode="after")
    def enforce_human_confirmation(
        self,
    ) -> "ApplicationQuestionAnswer":
        """Ensure uncertain or missing answers remain under human review."""

        if self.requires_confirmation and not self.confirmation_reason:
            raise ValueError(
                "An answer requiring confirmation must explain why."
            )

        if not self.requires_confirmation and self.answer is None:
            raise ValueError(
                "A confirmed application answer cannot be empty."
            )

        for claim in self.claims:
            if claim.usage != ClaimUsage.APPLICATION_ANSWER:
                raise ValueError(
                    "Application-answer claims must use the "
                    "application-answer usage type."
                )

        return self


class ReviewItem(StrictModel):
    """One item requiring explicit human review."""

    field_path: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    resolved: bool = False
    resolution: str | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> "ReviewItem":
        """Require a recorded resolution for completed review items."""

        if self.resolved and not self.resolution:
            raise ValueError(
                "A resolved review item must record its resolution."
            )

        return self


class PersonalizedApplication(StrictModel):
    """Complete Phase 2 application package awaiting human approval."""

    candidate_name: str = Field(min_length=1)
    job_title: str = Field(min_length=1)
    employer: str = Field(min_length=1)
    job_url: str = Field(min_length=1)

    resume: TailoredResume
    cover_letter: TailoredCoverLetter
    application_answers: list[ApplicationQuestionAnswer] = Field(
        default_factory=list
    )
    review_items: list[ReviewItem] = Field(default_factory=list)

    status: ApplicationStatus = ApplicationStatus.DRAFT
    user_approval_note: str | None = None
    schema_version: str = "1.0"

    @model_validator(mode="after")
    def enforce_approval_safety(
        self,
    ) -> "PersonalizedApplication":
        """Block approval while any information still needs review."""

        if self.status == ApplicationStatus.APPROVED_BY_USER:
            has_unresolved_review = any(
                not item.resolved for item in self.review_items
            )
            has_unconfirmed_answer = any(
                answer.requires_confirmation
                for answer in self.application_answers
            )

            if has_unresolved_review or has_unconfirmed_answer:
                raise ValueError(
                    "Application cannot be approved while review "
                    "items remain."
                )

            if not self.user_approval_note:
                raise ValueError(
                    "User approval note is required before approval."
                )

        return self