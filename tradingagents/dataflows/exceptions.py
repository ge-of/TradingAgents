"""Shared exceptions for data provider failures and availability semantics."""

from __future__ import annotations

from typing import Any, Mapping


class DataProviderError(Exception):
    """Base class for provider failures that can participate in fallback logic."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        method: str | None = None,
        retryable: bool = False,
        status_code: int | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.provider = provider
        self.method = method
        self.retryable = retryable
        self.status_code = status_code
        self.details = dict(details or {})
        super().__init__(message)

    def __str__(self) -> str:
        metadata = []
        if self.provider:
            metadata.append(f"provider={self.provider}")
        if self.method:
            metadata.append(f"method={self.method}")
        if self.status_code is not None:
            metadata.append(f"status_code={self.status_code}")
        metadata.append(f"retryable={self.retryable}")

        if not metadata:
            return self.message

        return f"{self.message} [{' '.join(metadata)}]"


class ProviderAuthError(DataProviderError):
    """Provider credentials or entitlement are missing or invalid."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class ProviderRateLimitError(DataProviderError):
    """Provider rate limits or quota limits prevented a successful response."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: int | None = None,
        details: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        merged_details = dict(details or {})
        if retry_after is not None:
            merged_details["retry_after"] = retry_after
        self.retry_after = retry_after
        kwargs.setdefault("retryable", True)
        super().__init__(message, details=merged_details, **kwargs)


class ProviderUnavailableError(DataProviderError):
    """Provider transport, timeout, or upstream availability failure."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class ProviderNoDataError(DataProviderError):
    """Provider responded successfully but no usable data exists for the request."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)
