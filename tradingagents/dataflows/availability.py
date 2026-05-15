"""Availability helpers for structured data provider adapters.

These helpers define top-level result semantics only. Adapter code should use
``ProviderResultRole.REQUIRED`` for the requested dataset itself and
``ProviderResultRole.OPTIONAL`` for child collections that can be legitimately
empty.
"""

from __future__ import annotations

from collections.abc import Mapping, Sized
from enum import Enum
from typing import Any, TypeVar

from .exceptions import ProviderNoDataError


T = TypeVar("T")


class ProviderResultRole(str, Enum):
    """Whether an empty provider result should raise or remain a valid result."""

    REQUIRED = "required"
    OPTIONAL = "optional"


def is_empty_provider_result(result: object) -> bool:
    """Return True when a provider result contains no usable top-level data."""
    if result is None:
        return True

    if isinstance(result, str):
        return result.strip() == ""

    empty = getattr(result, "empty", None)
    if isinstance(empty, bool):
        return empty

    if isinstance(result, Mapping):
        return len(result) == 0

    if isinstance(result, Sized):
        return len(result) == 0

    return False


def normalize_provider_result(
    result: T,
    *,
    provider: str,
    method: str,
    role: ProviderResultRole | str = ProviderResultRole.REQUIRED,
    no_data_message: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> T:
    """Return ``result`` or raise ``ProviderNoDataError`` for empty required data."""
    normalized_role = ProviderResultRole(role)
    if normalized_role is ProviderResultRole.OPTIONAL:
        return result

    if is_empty_provider_result(result):
        message = no_data_message or f"No data returned by {provider} for {method}"
        raise ProviderNoDataError(
            message,
            provider=provider,
            method=method,
            details=details,
        )

    return result
