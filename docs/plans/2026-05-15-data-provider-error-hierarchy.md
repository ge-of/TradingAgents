---
initiative: trading-platform
phase: 2
slice: 2A-S1
status: planned
worktree: main
depends_on:
  - docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md
  - docs/superpowers/specs/2026-05-04-platform-roadmap-design.md
  - docs/project-architecture-guidelines.md
---

# DataProviderError Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared data-provider exception vocabulary that future Massive, yfinance, Alpha Vantage, IBKR, screener, macro, and portfolio slices can use for fallback and diagnostics without changing agent-facing tool signatures.

**Architecture:** Create `tradingagents/dataflows/exceptions.py` as the data-layer-owned provider error contract. Keep `route_to_vendor()` behavior unchanged in this slice except that the existing `AlphaVantageRateLimitError` should inherit from the shared `ProviderRateLimitError` while remaining import-compatible for existing callers.

**Tech Stack:** Python 3.10+ exception classes, existing `tradingagents/dataflows/` package, pytest unit tests, no new dependencies.

---

## Scope

- Add `tradingagents/dataflows/exceptions.py`.
- Define `DataProviderError`, `ProviderRateLimitError`, `ProviderAuthError`, `ProviderUnavailableError`, and `ProviderNoDataError`.
- Preserve existing imports of `AlphaVantageRateLimitError`.
- Make `AlphaVantageRateLimitError` a `ProviderRateLimitError` subclass.
- Add focused unit tests for attributes, string messages, retryability defaults, and Alpha Vantage compatibility.

## Non-Goals

- Do not broaden `route_to_vendor()` fallback to catch `DataProviderError`; that is Slice `2A-S3`.
- Do not rewrite yfinance, Alpha Vantage indicator/fundamental/news functions, or any provider adapters to raise the new classes broadly; that starts in Slice `2A-S2` and later provider slices.
- Do not add Massive/Polygon code, credentials, config keys, or `VENDOR_METHODS` registrations.
- Do not change LangChain tool signatures or report string formats.
- Do not introduce Pydantic or any new dependency for exception metadata.

## File Structure

- Create: `tradingagents/dataflows/exceptions.py`
- Modify: `tradingagents/dataflows/alpha_vantage_common.py`
- Optional modify: `tradingagents/dataflows/__init__.py`
- Test: `tests/test_data_provider_exceptions.py`

## Task 1: Lock The Shared Exception Contract With Failing Tests

**Files:**
- Create: `tests/test_data_provider_exceptions.py`

- [ ] **Step 1: Add tests for base provider error metadata**

Create `tests/test_data_provider_exceptions.py`:

```python
import pytest

from tradingagents.dataflows.exceptions import (
    DataProviderError,
    ProviderAuthError,
    ProviderNoDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


@pytest.mark.unit
def test_data_provider_error_exposes_diagnostic_metadata():
    error = DataProviderError(
        "request failed",
        provider="massive",
        method="get_stock_data",
        retryable=True,
        status_code=502,
        details={"ticker": "AAPL"},
    )

    assert error.message == "request failed"
    assert error.provider == "massive"
    assert error.method == "get_stock_data"
    assert error.retryable is True
    assert error.status_code == 502
    assert error.details == {"ticker": "AAPL"}
    assert str(error) == (
        "request failed "
        "[provider=massive method=get_stock_data status_code=502 retryable=True]"
    )


@pytest.mark.unit
def test_data_provider_error_copies_details_mapping():
    details = {"ticker": "MSFT"}
    error = DataProviderError("request failed", details=details)

    details["ticker"] = "AAPL"

    assert error.details == {"ticker": "MSFT"}
```

- [ ] **Step 2: Add tests for subclass defaults**

Append to `tests/test_data_provider_exceptions.py`:

```python
@pytest.mark.unit
def test_provider_auth_error_is_not_retryable_by_default():
    error = ProviderAuthError("missing API key", provider="massive")

    assert isinstance(error, DataProviderError)
    assert error.retryable is False
    assert error.provider == "massive"


@pytest.mark.unit
def test_provider_rate_limit_error_is_retryable_and_tracks_retry_after():
    error = ProviderRateLimitError(
        "rate limited",
        provider="alpha_vantage",
        method="get_news",
        retry_after=60,
    )

    assert isinstance(error, DataProviderError)
    assert error.retryable is True
    assert error.retry_after == 60
    assert error.details == {"retry_after": 60}


@pytest.mark.unit
def test_provider_unavailable_error_is_retryable_by_default():
    error = ProviderUnavailableError(
        "upstream timeout",
        provider="yfinance",
        method="get_stock_data",
        status_code=503,
    )

    assert error.retryable is True
    assert error.status_code == 503


@pytest.mark.unit
def test_provider_no_data_error_is_not_retryable_by_default():
    error = ProviderNoDataError(
        "no price bars found",
        provider="massive",
        method="get_stock_data",
    )

    assert isinstance(error, DataProviderError)
    assert error.retryable is False
```

- [ ] **Step 3: Add tests for Alpha Vantage compatibility**

Append to `tests/test_data_provider_exceptions.py`:

```python
from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError


@pytest.mark.unit
def test_alpha_vantage_rate_limit_error_uses_shared_rate_limit_contract():
    error = AlphaVantageRateLimitError("Alpha Vantage rate limit exceeded")

    assert isinstance(error, ProviderRateLimitError)
    assert isinstance(error, DataProviderError)
    assert error.provider == "alpha_vantage"
    assert error.retryable is True
    assert str(error) == (
        "Alpha Vantage rate limit exceeded "
        "[provider=alpha_vantage retryable=True]"
    )
```

- [ ] **Step 4: Run the focused tests and confirm RED**

```bash
uv run pytest tests/test_data_provider_exceptions.py -q
```

Expected result: import failure for `tradingagents.dataflows.exceptions` before implementation.

## Task 2: Implement The Shared Error Hierarchy

**Files:**
- Create: `tradingagents/dataflows/exceptions.py`

- [ ] **Step 1: Add the base exception class**

Create `tradingagents/dataflows/exceptions.py`:

```python
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
```

- [ ] **Step 2: Add provider-specific subclasses**

Append to `tradingagents/dataflows/exceptions.py`:

```python
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
```

- [ ] **Step 3: Run the focused tests**

```bash
uv run pytest tests/test_data_provider_exceptions.py -q
```

Expected result: Alpha Vantage compatibility test still fails until Task 3.

## Task 3: Bridge AlphaVantageRateLimitError Into The Shared Contract

**Files:**
- Modify: `tradingagents/dataflows/alpha_vantage_common.py`

- [ ] **Step 1: Import the shared rate-limit error**

In `tradingagents/dataflows/alpha_vantage_common.py`, add the import near the other imports:

```python
from .exceptions import ProviderRateLimitError
```

- [ ] **Step 2: Change the class inheritance while preserving the class name**

Replace the current `AlphaVantageRateLimitError` class:

```python
class AlphaVantageRateLimitError(Exception):
    """Exception raised when Alpha Vantage API rate limit is exceeded."""
    pass
```

with:

```python
class AlphaVantageRateLimitError(ProviderRateLimitError):
    """Exception raised when Alpha Vantage API rate limit is exceeded."""

    def __init__(self, message: str) -> None:
        super().__init__(message, provider="alpha_vantage")
```

- [ ] **Step 3: Run the focused tests and confirm GREEN**

```bash
uv run pytest tests/test_data_provider_exceptions.py -q
```

Expected result: all tests in `tests/test_data_provider_exceptions.py` pass.

## Task 4: Decide Whether To Export From The Package Init

**Files:**
- Optional modify: `tradingagents/dataflows/__init__.py`

- [ ] **Step 1: Inspect current package usage before editing**

```bash
rg -n "from tradingagents.dataflows import|import tradingagents.dataflows" tradingagents tests
```

- [ ] **Step 2: Prefer direct imports unless package-level exports are already used**

If there is no existing package-level export pattern, leave `tradingagents/dataflows/__init__.py` unchanged and import exceptions from `tradingagents.dataflows.exceptions`.

If package-level exports are already used, add:

```python
from .exceptions import (
    DataProviderError,
    ProviderAuthError,
    ProviderNoDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)

__all__ = [
    "DataProviderError",
    "ProviderAuthError",
    "ProviderNoDataError",
    "ProviderRateLimitError",
    "ProviderUnavailableError",
]
```

- [ ] **Step 3: Re-run the focused tests if `__init__.py` changed**

```bash
uv run pytest tests/test_data_provider_exceptions.py -q
```

## Task 5: Run Regression Verification

- [ ] **Step 1: Run the focused provider tests**

```bash
uv run pytest tests/test_data_provider_exceptions.py tests/test_dataflows_config.py -q
```

Expected result: both provider exception and dataflows config tests pass.

- [ ] **Step 2: Run the existing tests that are most likely to catch import or config breakage**

```bash
uv run pytest tests/test_capabilities.py tests/test_model_validation.py tests/test_structured_agents.py -q
```

Expected result: all selected tests pass.

- [ ] **Step 3: Run a static search for accidental router behavior changes**

```bash
git diff -- tradingagents/dataflows/interface.py
```

Expected result: no diff for `tradingagents/dataflows/interface.py` in this slice.

## Task 6: Documentation Drift Checkpoint

- [ ] **Step 1: Compare shipped behavior to the roadmap docs**

Check whether implementation stayed inside the existing `2A-S1` boundary in:

- `docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md`
- `docs/superpowers/specs/2026-05-04-platform-roadmap-design.md`
- `docs/project-architecture-guidelines.md`

- [ ] **Step 2: Update docs only if implementation scope changed**

No docs update is expected if the implementation only adds `exceptions.py` and makes `AlphaVantageRateLimitError` inherit from `ProviderRateLimitError`. Update docs if any of these happen:

- `route_to_vendor()` starts catching `DataProviderError`.
- Provider modules begin raising the shared errors broadly.
- No-data semantics are defined beyond class naming.
- Massive/Polygon, IBKR, macro providers, or structured equity schemas are added.

- [ ] **Step 3: Record the checkpoint in the closeout**

Use this wording if no docs update is needed:

```text
Docs drift checkpoint: no durable docs update needed; this slice implements the already-planned `2A-S1` provider error vocabulary without changing router fallback behavior, structured data contracts, provider registrations, or user-facing workflows.
```

## Task 7: Commit The Slice

- [ ] **Step 1: Review the exact diff**

```bash
git diff -- tradingagents/dataflows/exceptions.py tradingagents/dataflows/alpha_vantage_common.py tests/test_data_provider_exceptions.py tradingagents/dataflows/__init__.py
```

- [ ] **Step 2: Stage only intended files**

```bash
git add tradingagents/dataflows/exceptions.py tradingagents/dataflows/alpha_vantage_common.py tests/test_data_provider_exceptions.py
```

Only include `tradingagents/dataflows/__init__.py` if Task 4 changed it.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(data): add provider error hierarchy"
```

## Completion Criteria

- `tradingagents/dataflows/exceptions.py` exists and defines the shared provider error hierarchy.
- `AlphaVantageRateLimitError` remains import-compatible and is now a `ProviderRateLimitError`.
- Agent-facing tool signatures and `route_to_vendor()` fallback behavior are unchanged.
- Focused and regression tests listed in Task 5 pass.
- Documentation drift checkpoint is completed and summarized.

