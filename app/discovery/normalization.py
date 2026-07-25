"""Deterministic normalization helpers for public job-board payloads."""

from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from typing import ClassVar
from urllib.parse import unquote, urlparse

from app.models.job import EmploymentType, WorkArrangement


class _TextExtractor(HTMLParser):
    """Extract readable text without executing or preserving markup."""

    BLOCK_TAGS: ClassVar[frozenset[str]] = frozenset(
        {
            "br",
            "div",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "p",
            "section",
            "tr",
        }
    )
    IGNORED_TAGS: ClassVar[frozenset[str]] = frozenset({"script", "style", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        normalized_tag = tag.casefold()
        if normalized_tag in self.IGNORED_TAGS:
            self.ignored_depth += 1
        elif not self.ignored_depth and normalized_tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in self.IGNORED_TAGS and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and normalized_tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)


def normalize_text(value: object) -> str:
    """Convert optional plain text or HTML into compact readable text."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if not isinstance(value, str):
        return ""

    decoded = unescape(unescape(value))
    parser = _TextExtractor()
    parser.feed(decoded)
    parser.close()
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)


def normalize_optional_text(value: object) -> str | None:
    """Normalize optional text and represent blank values as null."""
    normalized = normalize_text(value)
    return normalized or None


def parse_datetime(value: object) -> datetime | None:
    """Parse an ISO timestamp and ensure it has an explicit timezone."""
    if not isinstance(value, str) or not value.strip():
        return None

    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def parse_unix_milliseconds(value: object) -> datetime | None:
    """Parse a Unix timestamp expressed in milliseconds as UTC."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None

    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


def normalize_work_arrangement(
    value: object,
    *,
    location: str | None = None,
    remote_hint: bool | None = None,
) -> WorkArrangement:
    """Map vendor workplace labels to the shared job model."""
    normalized = normalize_text(value).casefold().replace("_", "-")
    location_text = (location or "").casefold()

    if "hybrid" in normalized or "hybrid" in location_text:
        return WorkArrangement.HYBRID
    if remote_hint is True or "remote" in normalized or "remote" in location_text:
        return WorkArrangement.REMOTE
    if normalized in {"on-site", "onsite", "in-office", "office"}:
        return WorkArrangement.ONSITE
    return WorkArrangement.UNSPECIFIED


def normalize_employment_type(value: object) -> EmploymentType:
    """Map common ATS employment labels to the shared job model."""
    normalized = "".join(
        character for character in normalize_text(value).casefold() if character.isalnum()
    )
    mappings = {
        "fulltime": EmploymentType.FULL_TIME,
        "parttime": EmploymentType.PART_TIME,
        "contract": EmploymentType.CONTRACT,
        "contractor": EmploymentType.CONTRACT,
        "intern": EmploymentType.INTERNSHIP,
        "internship": EmploymentType.INTERNSHIP,
        "temporary": EmploymentType.TEMPORARY,
        "temp": EmploymentType.TEMPORARY,
    }
    return mappings.get(normalized, EmploymentType.UNKNOWN)


def source_id_from_url(value: object) -> str:
    """Extract the stable final path segment from a public job URL."""
    if not isinstance(value, str):
        return ""
    path_parts = [part for part in urlparse(value).path.split("/") if part]
    return unquote(path_parts[-1]).strip() if path_parts else ""


def normalize_salary(value: object) -> str | None:
    """Render a vendor salary range without inventing missing units."""
    if not isinstance(value, dict):
        return normalize_optional_text(value)

    minimum = value.get("min")
    maximum = value.get("max")
    currency = normalize_text(value.get("currency"))
    interval = normalize_text(value.get("interval"))

    if minimum is None and maximum is None:
        return None

    amount = (
        f"{minimum} - {maximum}"
        if minimum is not None and maximum is not None
        else str(minimum if minimum is not None else maximum)
    )
    return " ".join(part for part in (currency, amount, interval) if part)
