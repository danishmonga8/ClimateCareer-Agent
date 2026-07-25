"""Shared HTTP safeguards for read-only public job collectors."""

import re
from collections.abc import Mapping
from typing import Any

import httpx

PUBLIC_USER_AGENT = "ClimateCareer-Agent/0.1 public-job-discovery"
BOARD_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


class JobCollectorError(RuntimeError):
    """Raised when a public job board cannot be collected safely."""


def validate_board_identifier(value: str, label: str) -> str:
    """Reject path traversal and ambiguous public board identifiers."""
    candidate = value.strip()
    if not BOARD_IDENTIFIER_PATTERN.fullmatch(candidate):
        raise JobCollectorError(f"Invalid {label}: {value!r}")
    return candidate


def get_public_json(
    url: str,
    *,
    params: Mapping[str, str | bool | int] | None = None,
    client: httpx.Client | None = None,
) -> Any:
    """Issue one unauthenticated GET and decode its JSON response."""
    owns_client = client is None
    active_client = client or httpx.Client(
        timeout=15.0,
        follow_redirects=True,
        headers={
            "Accept": "application/json",
            "User-Agent": PUBLIC_USER_AGENT,
        },
    )

    try:
        response = active_client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise JobCollectorError(f"Unable to collect public jobs from {url}") from error
    finally:
        if owns_client:
            active_client.close()
