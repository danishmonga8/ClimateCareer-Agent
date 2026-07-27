"""Explainable job-relevance scoring models."""

from enum import StrEnum

from pydantic import Field, computed_field, model_validator

from app.models.candidate import StrictModel


class ScoreCategory(StrEnum):
    """Categories used in the 100-point relevance score."""

    TECHNICAL_SKILLS = "technical_skills"
    DOMAIN_ALIGNMENT = "domain_alignment"
    TRANSFERABLE_AI = "transferable_ai"
    RESEARCH_MODELLING = "research_modelling"
    EDUCATION_EXPERIENCE = "education_experience"
    GEOSPATIAL_ENVIRONMENTAL = "geospatial_environmental"
    LOCATION_WORK_MODE = "location_work_mode"
    CAREER_GROWTH = "career_growth"


class HardConstraintStatus(StrEnum):
    """Possible outcomes of a hard-eligibility check."""

    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    REQUIRES_REVIEW = "requires_review"


class ApplicationRecommendation(StrEnum):
    """Final recommendation after scoring and eligibility checking."""

    PRIORITIZE = "excellent_match_prioritize"
    APPLY = "strong_match_apply"
    APPLY_SELECTIVELY = "moderate_match_apply_selectively"
    STRATEGIC_STRETCH = "stretch_apply_if_strategic"
    DO_NOT_APPLY = "low_match_do_not_apply"
    MANUAL_REVIEW = "manual_review_required"


class WeightScheme(StrictModel):
    """Configurable category weights that must total 100 points."""

    technical_skills: float = 25
    domain_alignment: float = 20
    transferable_ai: float = 15
    research_modelling: float = 10
    education_experience: float = 10
    geospatial_environmental: float = 10
    location_work_mode: float = 5
    career_growth: float = 5

    @model_validator(mode="after")
    def validate_total_weight(self) -> "WeightScheme":
        """Ensure that all scoring weights total exactly 100."""
        if abs(sum(self.as_mapping().values()) - 100) > 0.001:
            raise ValueError("Scoring weights must total exactly 100 points.")
        return self

    def as_mapping(self) -> dict[ScoreCategory, float]:
        """Return weights indexed by scoring category."""
        return {
            ScoreCategory.TECHNICAL_SKILLS: self.technical_skills,
            ScoreCategory.DOMAIN_ALIGNMENT: self.domain_alignment,
            ScoreCategory.TRANSFERABLE_AI: self.transferable_ai,
            ScoreCategory.RESEARCH_MODELLING: self.research_modelling,
            ScoreCategory.EDUCATION_EXPERIENCE: self.education_experience,
            ScoreCategory.GEOSPATIAL_ENVIRONMENTAL: self.geospatial_environmental,
            ScoreCategory.LOCATION_WORK_MODE: self.location_work_mode,
            ScoreCategory.CAREER_GROWTH: self.career_growth,
        }

    @classmethod
    def for_pure_ai_role(cls) -> "WeightScheme":
        """Redistribute geospatial points for roles with no geospatial component."""
        return cls(
            technical_skills=30,
            domain_alignment=20,
            transferable_ai=20,
            research_modelling=10,
            education_experience=10,
            geospatial_environmental=0,
            location_work_mode=5,
            career_growth=5,
        )


class ScoreComponent(StrictModel):
    """One explainable category-level score."""

    category: ScoreCategory
    awarded_points: float = Field(ge=0)
    maximum_points: float = Field(ge=0)
    rationale: str = Field(min_length=1)
    matched_evidence: list[str] = Field(default_factory=list)
    missing_items: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_awarded_points(self) -> "ScoreComponent":
        """Prevent awarded points from exceeding the category maximum."""
        if self.awarded_points > self.maximum_points:
            raise ValueError("Awarded points cannot exceed maximum points.")
        return self


class HardConstraintCheck(StrictModel):
    """Result of checking one non-negotiable job requirement."""

    requirement: str = Field(min_length=1)
    status: HardConstraintStatus
    explanation: str = Field(min_length=1)


class JobRelevanceScore(StrictModel):
    """Complete explainable relevance assessment for one job."""

    company: str = Field(min_length=1)
    job_title: str = Field(min_length=1)
    weight_scheme: WeightScheme = Field(default_factory=WeightScheme)
    components: list[ScoreComponent] = Field(min_length=8, max_length=8)
    hard_constraints: list[HardConstraintCheck] = Field(default_factory=list)
    strongest_alignments: list[str] = Field(default_factory=list)
    transferable_skills: list[str] = Field(default_factory=list)
    recommended_resume_changes: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)
    confidence_score: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_components(self) -> "JobRelevanceScore":
        """Require every category once and enforce the selected weights."""
        expected_weights = self.weight_scheme.as_mapping()
        observed_categories = [component.category for component in self.components]

        if len(set(observed_categories)) != len(observed_categories):
            raise ValueError("Each scoring category must appear exactly once.")

        if set(observed_categories) != set(ScoreCategory):
            raise ValueError("All eight scoring categories must be provided.")

        for component in self.components:
            expected_maximum = expected_weights[component.category]
            if abs(component.maximum_points - expected_maximum) > 0.001:
                raise ValueError(
                    f"Incorrect maximum for {component.category.value}: "
                    f"expected {expected_maximum}."
                )

        return self

    @computed_field
    @property
    def overall_score(self) -> float:
        """Calculate the final numerical score out of 100."""
        return round(sum(item.awarded_points for item in self.components), 2)

    @computed_field
    @property
    def recommendation(self) -> ApplicationRecommendation:
        """Calculate the recommendation while respecting hard failures."""
        if any(check.status == HardConstraintStatus.FAILED for check in self.hard_constraints):
            return ApplicationRecommendation.DO_NOT_APPLY

        if any(
            check.status
            in {
                HardConstraintStatus.UNKNOWN,
                HardConstraintStatus.REQUIRES_REVIEW,
            }
            for check in self.hard_constraints
        ):
            return ApplicationRecommendation.MANUAL_REVIEW

        if self.overall_score >= 85:
            return ApplicationRecommendation.PRIORITIZE
        if self.overall_score >= 75:
            return ApplicationRecommendation.APPLY
        if self.overall_score >= 65:
            return ApplicationRecommendation.APPLY_SELECTIVELY
        if self.overall_score >= 55:
            return ApplicationRecommendation.STRATEGIC_STRETCH
        return ApplicationRecommendation.DO_NOT_APPLY
