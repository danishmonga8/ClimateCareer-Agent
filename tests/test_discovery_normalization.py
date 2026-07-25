"""Tests for deterministic cross-vendor normalization."""

from datetime import UTC

from app.discovery.normalization import (
    normalize_employment_type,
    normalize_text,
    normalize_work_arrangement,
    parse_datetime,
    parse_unix_milliseconds,
)
from app.models.job import EmploymentType, WorkArrangement


def test_html_is_decoded_and_markup_is_removed() -> None:
    assert normalize_text("&lt;p&gt;Climate &amp;amp; AI&lt;/p&gt;") == "Climate & AI"


def test_non_content_html_is_not_included_in_description() -> None:
    source = "<style>.hidden { display: none; }</style><p>Climate role</p><script>alert(1)</script>"

    assert normalize_text(source) == "Climate role"


def test_vendor_enums_are_normalized() -> None:
    assert normalize_employment_type("FullTime") == EmploymentType.FULL_TIME
    assert normalize_employment_type("Intern") == EmploymentType.INTERNSHIP
    assert normalize_work_arrangement("OnSite", location="London") == WorkArrangement.ONSITE


def test_naive_iso_datetime_is_made_explicitly_utc() -> None:
    parsed = parse_datetime("2026-07-25T10:00:00")
    assert parsed is not None
    assert parsed.tzinfo == UTC


def test_unix_millisecond_datetime_is_parsed_as_utc() -> None:
    parsed = parse_unix_milliseconds(1784548800000)
    assert parsed is not None
    assert parsed.isoformat() == "2026-07-20T12:00:00+00:00"
