"""Human-controlled review transitions for personalized applications."""

from pydantic import ValidationError

from app.models.personalization import (
    ApplicationStatus,
    PersonalizedApplication,
)


class ApplicationReviewError(ValueError):
    """Raised when an application review action is unsafe or invalid."""


def _validated_application(
    payload: dict,
    action: str,
) -> PersonalizedApplication:
    """Revalidate an application after a controlled state transition."""
    try:
        return PersonalizedApplication.model_validate(payload)
    except ValidationError as error:
        raise ApplicationReviewError(
            f"Unable to {action} the personalized application."
        ) from error


def _reject_approved_application(
    application: PersonalizedApplication,
) -> None:
    """Prevent approved applications from being silently changed."""
    if application.status == ApplicationStatus.APPROVED_BY_USER:
        raise ApplicationReviewError(
            "An approved application cannot be modified."
        )


def begin_application_review(
    application: PersonalizedApplication,
) -> PersonalizedApplication:
    """Move an application draft into explicit human review."""
    _reject_approved_application(application)

    payload = application.model_dump(mode="python")
    payload["status"] = ApplicationStatus.NEEDS_REVIEW
    payload["user_approval_note"] = None

    return _validated_application(
        payload,
        "begin review of",
    )


def resolve_application_answer(
    application: PersonalizedApplication,
    question_index: int,
    answer: str,
    resolution: str,
) -> PersonalizedApplication:
    """Record a human-confirmed answer and resolve its review item."""
    _reject_approved_application(application)

    normalized_answer = answer.strip()
    normalized_resolution = resolution.strip()

    if not normalized_answer:
        raise ApplicationReviewError(
            "A confirmed application answer cannot be empty."
        )

    if not normalized_resolution:
        raise ApplicationReviewError(
            "An answer resolution note cannot be empty."
        )

    if (
        question_index < 0
        or question_index >= len(application.application_answers)
    ):
        raise ApplicationReviewError(
            f"Application-question index is out of range: {question_index}"
        )

    selected_answer = application.application_answers[question_index]

    if not selected_answer.requires_confirmation:
        raise ApplicationReviewError(
            "The selected application answer is already confirmed."
        )

    field_path = f"application_answers[{question_index}].answer"

    matching_items = [
        index
        for index, item in enumerate(application.review_items)
        if item.field_path == field_path and not item.resolved
    ]

    if len(matching_items) != 1:
        raise ApplicationReviewError(
            "The application answer must have exactly one unresolved "
            "review item."
        )

    payload = application.model_dump(mode="python")
    answer_payload = payload["application_answers"][question_index]
    answer_payload["answer"] = normalized_answer
    answer_payload["requires_confirmation"] = False
    answer_payload["confirmation_reason"] = None

    review_index = matching_items[0]
    review_payload = payload["review_items"][review_index]
    review_payload["resolved"] = True
    review_payload["resolution"] = normalized_resolution

    payload["status"] = ApplicationStatus.NEEDS_REVIEW
    payload["user_approval_note"] = None

    return _validated_application(
        payload,
        "resolve an application answer in",
    )


def resolve_review_item(
    application: PersonalizedApplication,
    field_path: str,
    resolution: str,
) -> PersonalizedApplication:
    """Resolve a non-answer review item with a human decision."""
    _reject_approved_application(application)

    normalized_path = field_path.strip()
    normalized_resolution = resolution.strip()

    if not normalized_path:
        raise ApplicationReviewError(
            "A review-item field path cannot be empty."
        )

    if not normalized_resolution:
        raise ApplicationReviewError(
            "A review-item resolution cannot be empty."
        )

    if (
        normalized_path.startswith("application_answers[")
        and normalized_path.endswith("].answer")
    ):
        raise ApplicationReviewError(
            "Application-answer review items must be resolved with "
            "resolve_application_answer."
        )

    matching_items = [
        index
        for index, item in enumerate(application.review_items)
        if item.field_path == normalized_path and not item.resolved
    ]

    if not matching_items:
        raise ApplicationReviewError(
            f"No unresolved review item was found: {normalized_path}"
        )

    if len(matching_items) > 1:
        raise ApplicationReviewError(
            f"Multiple unresolved review items were found: {normalized_path}"
        )

    payload = application.model_dump(mode="python")
    review_payload = payload["review_items"][matching_items[0]]
    review_payload["resolved"] = True
    review_payload["resolution"] = normalized_resolution

    payload["status"] = ApplicationStatus.NEEDS_REVIEW
    payload["user_approval_note"] = None

    return _validated_application(
        payload,
        "resolve a review item in",
    )


def approve_application(
    application: PersonalizedApplication,
    approval_note: str,
) -> PersonalizedApplication:
    """Approve an application only after explicit completed review."""
    if application.status != ApplicationStatus.NEEDS_REVIEW:
        raise ApplicationReviewError(
            "An application must be in needs_review status before approval."
        )

    normalized_note = approval_note.strip()

    if not normalized_note:
        raise ApplicationReviewError(
            "A user approval note cannot be empty."
        )

    if any(not item.resolved for item in application.review_items):
        raise ApplicationReviewError(
            "Application cannot be approved with unresolved review items."
        )

    if any(
        answer.requires_confirmation
        for answer in application.application_answers
    ):
        raise ApplicationReviewError(
            "Application cannot be approved with unconfirmed answers."
        )

    payload = application.model_dump(mode="python")
    payload["status"] = ApplicationStatus.APPROVED_BY_USER
    payload["user_approval_note"] = normalized_note

    return _validated_application(
        payload,
        "approve",
    )