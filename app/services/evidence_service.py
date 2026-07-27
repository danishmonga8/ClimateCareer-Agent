"""Deterministic evidence-bank generation from candidate profiles and CV text."""

import re
from hashlib import sha256

from app.models.candidate import CandidateProfile, SkillCategory
from app.models.evidence import EvidenceBank, EvidenceRecord, EvidenceStatus

MATCHING_STOPWORDS = {
    "and",
    "or",
    "with",
    "the",
    "of",
    "in",
    "to",
    "for",
}


def _normalize_text(value: str) -> str:
    """Normalize CV language and common abbreviations."""
    normalized = value.casefold()
    normalized = re.sub(r"\bqc\b", "quality control", normalized)
    normalized = re.sub(r"\blulc\b", "land use land cover", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _significant_tokens(value: str) -> set[str]:
    """Return meaningful tokens used for conservative phrase matching."""
    return {token for token in _normalize_text(value).split() if token not in MATCHING_STOPWORDS}


def _find_source_excerpt(query: str, cv_text: str) -> str | None:
    """Find CV evidence using one-to-three-line text windows."""
    query_tokens = _significant_tokens(query)

    if not query_tokens:
        return None

    lines = [line.strip() for line in cv_text.splitlines() if line.strip()]

    for start_index in range(len(lines)):
        for window_size in range(1, 4):
            window = " ".join(lines[start_index : start_index + window_size])

            if query_tokens.issubset(_significant_tokens(window)):
                return window[:500]

    return None


def _create_evidence_id(category: str, claim: str) -> str:
    """Create a stable evidence identifier without exposing the claim."""
    digest = sha256(f"{category}:{claim}".encode()).hexdigest()
    return f"{category}-{digest[:12]}"


def _extract_quantitative_evidence(text: str) -> list[str]:
    """Extract conservative numeric values from a supported statement."""
    return re.findall(
        r"\b\d+(?:,\d{3})*(?:\.\d+)?(?:%|×)?\b",
        text,
    )


def _job_families_for_skill(category: SkillCategory) -> list[str]:
    """Map skill categories to suitable job families."""
    mapping = {
        SkillCategory.PROGRAMMING: [
            "Data Science",
            "AI Engineering",
            "Environmental Data Science",
        ],
        SkillCategory.MACHINE_LEARNING: [
            "Machine Learning",
            "Data Science",
            "Climate AI",
        ],
        SkillCategory.GENERATIVE_AI: [
            "Generative AI",
            "RAG Engineering",
            "Agentic AI",
        ],
        SkillCategory.STATISTICAL_MODELLING: [
            "Climate Risk",
            "CAT Modelling",
            "Predictive Risk Modelling",
        ],
        SkillCategory.GEOSPATIAL: [
            "Geospatial Data Science",
            "Earth Observation",
            "Environmental Analytics",
        ],
        SkillCategory.DOMAIN_EXPERTISE: [
            "Climate Risk",
            "Natural Hazard Modelling",
            "Environmental Data Science",
        ],
        SkillCategory.OTHER: ["Data Science"],
    }
    return mapping[category]


def _build_record(
    *,
    category: str,
    claim: str,
    source_document: str,
    source_section: str,
    source_excerpt: str | None,
    tools: list[str] | None = None,
    domain: str | None = None,
    associated_project: str | None = None,
    suitable_job_families: list[str] | None = None,
) -> EvidenceRecord:
    """Create a safely classified evidence record."""
    is_verified = source_excerpt is not None
    status = EvidenceStatus.VERIFIED if is_verified else EvidenceStatus.REQUIRES_CONFIRMATION

    return EvidenceRecord(
        evidence_id=_create_evidence_id(category, claim),
        claim=claim,
        source_document=source_document,
        source_section=source_section,
        source_excerpt=source_excerpt,
        associated_project=associated_project,
        tools=tools or [],
        domain=domain,
        quantitative_evidence=_extract_quantitative_evidence(source_excerpt or ""),
        suitable_job_families=suitable_job_families or [],
        confidence_score=0.98 if is_verified else 0.35,
        status=status,
        allowed_in_resume=is_verified,
        allowed_in_cover_letter=is_verified,
        requires_confirmation=not is_verified,
        notes=None if is_verified else "Supporting CV text was not found.",
    )


def build_evidence_bank(
    profile: CandidateProfile,
    cv_text: str,
    source_sha256: str,
) -> EvidenceBank:
    """Build traceable evidence records from a profile and its source CV."""
    records: list[EvidenceRecord] = []

    for skill in profile.skills:
        records.append(
            _build_record(
                category="skill",
                claim=f"Candidate has experience with {skill.name}.",
                source_document=profile.source_document,
                source_section="Core Technical Skills",
                source_excerpt=_find_source_excerpt(skill.name, cv_text),
                tools=[skill.name],
                domain=skill.category.value,
                suitable_job_families=_job_families_for_skill(skill.category),
            )
        )

    for education in profile.education:
        excerpt = _find_source_excerpt(education.degree, cv_text)
        institution_found = _find_source_excerpt(
            education.institution,
            cv_text,
        )

        if institution_found is None:
            excerpt = None

        records.append(
            _build_record(
                category="education",
                claim=(
                    f"{education.degree} in "
                    f"{education.field_of_study or 'unspecified field'} "
                    f"at {education.institution}."
                ),
                source_document=profile.source_document,
                source_section="Education",
                source_excerpt=excerpt,
                domain=education.field_of_study,
                suitable_job_families=["All Target Roles"],
            )
        )

    for experience in profile.experience:
        excerpt = _find_source_excerpt(experience.title, cv_text)
        organization_found = _find_source_excerpt(
            experience.organization,
            cv_text,
        )

        if organization_found is None:
            excerpt = None

        records.append(
            _build_record(
                category="experience",
                claim=f"{experience.title} at {experience.organization}.",
                source_document=profile.source_document,
                source_section="Professional Experience",
                source_excerpt=excerpt,
                domain="professional_experience",
                suitable_job_families=["All Target Roles"],
            )
        )

    for project in profile.projects:
        records.append(
            _build_record(
                category="project",
                claim=f"Completed project: {project.name}.",
                source_document=profile.source_document,
                source_section="Selected Portfolio Projects",
                source_excerpt=_find_source_excerpt(project.name, cv_text),
                associated_project=project.name,
                tools=project.tools,
                domain="portfolio_project",
                suitable_job_families=["All Target Roles"],
            )
        )

    for certification in profile.certifications_and_awards:
        records.append(
            _build_record(
                category="credential",
                claim=certification.name,
                source_document=profile.source_document,
                source_section="Certifications and Awards",
                source_excerpt=_find_source_excerpt(
                    certification.name,
                    cv_text,
                ),
                domain=certification.category,
                suitable_job_families=["All Target Roles"],
            )
        )

    return EvidenceBank(
        candidate_name=profile.full_name,
        source_document=profile.source_document,
        source_sha256=source_sha256,
        records=records,
    )
