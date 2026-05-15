---
initiative: trading-platform
phase: 2
slice: 2A-S2
status: planned
worktree: main
depends_on:
  - docs/plans/2026-05-15-data-provider-error-hierarchy.md
  - docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md
  - docs/superpowers/specs/2026-05-04-platform-roadmap-design.md
  - docs/project-architecture-guidelines.md
---

# Explicit No-Data Vs Provider-Error Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define and test the narrow data-provider availability contract that separates successful no-data outcomes from provider failures before future structured adapters depend on it.

**Architecture:** Add a small `tradingagents/dataflows/availability.py` helper module owned by the data layer. Structured adapters use it to raise `ProviderNoDataError` only when a required top-level dataset is empty, while optional empty collections remain valid structured results. Existing agent-facing report wrappers, `route_to_vendor()` fallback behavior, provider registrations, config keys, and credentials stay unchanged in this slice.

**Tech Stack:** Python 3.10+, existing provider exception hierarchy, pytest, pandas already present in the project, no new dependencies.

---

## Baseline Evidence

- `tradingagents/dataflows/exceptions.py` already defines `DataProviderError`, `ProviderAuthError`, `ProviderRateLimitError`, `ProviderUnavailableError`, and `ProviderNoDataError`.
- `tradingagents/dataflows/interface.py` still catches only `AlphaVantageRateLimitError` for fallback; broad `DataProviderError` fallback belongs to Slice `2A-S3`.
- yfinance wrappers currently return no-data report strings for empty successful responses and `"Error ..."` strings for caught exceptions.
- Alpha Vantage common request handling raises `AlphaVantageRateLimitError` for rate-limit/API-key messages, while several wrappers still return raw strings or `"Error ..."` strings.

## Contract Definition

Use these semantics for structured data adapters and future provider modules:

- Raise `ProviderNoDataError` when the provider request succeeds but the requested required top-level dataset has no usable rows or entity data after ticker/date/as-of filtering. Examples: unknown or unsupported ticker, no OHLCV bars in the requested date range, no fundamentals object for the requested ticker, or all required rows filtered out by `as_of`.
- Return an empty structured collection when the empty value is the valid domain answer for an optional child collection. Examples: no news articles, no insider transactions, no dividends, no splits, no corporate-action events in range.
- Return partial structured objects with `None` fields or later availability records when the entity exists but individual fields are missing. Missing optional fields are not provider failures and are not top-level no-data.
- Raise `ProviderAuthError`, `ProviderRateLimitError`, or `ProviderUnavailableError` for credentials/entitlement failures, quota/rate-limit failures, transport/timeouts, HTTP 5xx, and malformed provider responses.
- Keep caller validation errors, such as unsupported indicator names or invalid date formats, as `ValueError`.
- Do not parse agent-facing no-data strings in business logic. Existing report wrappers may keep returning prose strings until later structured entry-point slices adopt this helper.

## Scope

- Create `tradingagents/dataflows/availability.py`.
- Add `ProviderResultRole`, `is_empty_provider_result()`, and `normalize_provider_result()`.
- Add focused unit tests in `tests/test_data_provider_availability.py`.
- Add a concise architecture-doc section that records the no-data/provider-error contract.
- Preserve existing `tests/test_data_provider_exceptions.py` behavior from Slice `2A-S1`.

## Non-Goals

- Do not broaden `route_to_vendor()` fallback to catch `DataProviderError`; that is Slice `2A-S3`.
- Do not add Massive/Polygon, IBKR, config keys, credentials, `.env.example` entries, or `VENDOR_METHODS` registrations.
- Do not rewrite yfinance or Alpha Vantage adapters broadly.
- Do not change LangChain tool signatures or report string shapes.
- Do not add structured equity schemas; that is Slice `2B-S1`.
- Do not route `_fetch_returns()` through structured data; that is a later Phase 2 adoption slice.

## File Structure

- Create: `tradingagents/dataflows/availability.py`
- Create: `tests/test_data_provider_availability.py`
- Modify: `docs/project-architecture-guidelines.md`
- No change expected: `tradingagents/dataflows/interface.py`
- No change expected: `tradingagents/dataflows/y_finance.py`
- No change expected: `tradingagents/dataflows/yfinance_news.py`
- No change expected: `tradingagents/dataflows/alpha_vantage*.py`
- No change expected: `tradingagents/default_config.py`
- No change expected: `.env.example`

## Task 1: Lock The Availability Contract With Failing Tests

**Files:**
- Create: `tests/test_data_provider_availability.py`

- [ ] **Step 1: Add tests for empty top-level result classification**

Create `tests/test_data_provider_availability.py`:

```python
import pandas as pd
import pytest

from tradingagents.dataflows.availability import (
    ProviderResultRole,
    is_empty_provider_result,
    normalize_provider_result,
)
from tradingagents.dataflows.exceptions import ProviderNoDataError


@pytest.mark.unit
@pytest.mark.parametrize(
    "result",
    [
        None,
        "",
        [],
        {},
        pd.DataFrame(),
    ],
)
def test_empty_provider_results_are_classified_as_no_top_level_data(result):
    assert is_empty_provider_result(result) is True
```

- [ ] **Step 2: Add tests for partial data and legacy report strings**

Append to `tests/test_data_provider_availability.py`:

```python
@pytest.mark.unit
@pytest.mark.parametrize(
    "result",
    [
        "No data found for symbol 'AAPL'",
        [None],
        {"pe_ratio": None},
        pd.DataFrame({"close": [101.25]}),
    ],
)
def test_non_empty_provider_results_preserve_partial_or_report_data(result):
    assert is_empty_provider_result(result) is False
```

This preserves a key boundary: the helper classifies structural emptiness, not prose content. Later structured adapters should not parse report strings.

- [ ] **Step 3: Add tests for required empty results raising `ProviderNoDataError`**

Append to `tests/test_data_provider_availability.py`:

```python
@pytest.mark.unit
def test_required_empty_provider_result_raises_no_data_error():
    with pytest.raises(ProviderNoDataError) as exc_info:
        normalize_provider_result(
            pd.DataFrame(),
            provider="yfinance",
            method="get_stock_data",
            role=ProviderResultRole.REQUIRED,
            no_data_message="No price bars found for AAPL from 2026-05-01 to 2026-05-02",
            details={
                "ticker": "AAPL",
                "start_date": "2026-05-01",
                "end_date": "2026-05-02",
            },
        )

    error = exc_info.value
    assert error.provider == "yfinance"
    assert error.method == "get_stock_data"
    assert error.retryable is False
    assert error.details == {
        "ticker": "AAPL",
        "start_date": "2026-05-01",
        "end_date": "2026-05-02",
    }
    assert error.message == "No price bars found for AAPL from 2026-05-01 to 2026-05-02"
```

- [ ] **Step 4: Add tests for optional empty collections returning unchanged**

Append to `tests/test_data_provider_availability.py`:

```python
@pytest.mark.unit
def test_optional_empty_provider_result_is_returned_unchanged():
    result = []

    returned = normalize_provider_result(
        result,
        provider="yfinance",
        method="get_news",
        role=ProviderResultRole.OPTIONAL,
        no_data_message="No news articles found for AAPL",
        details={"ticker": "AAPL"},
    )

    assert returned is result
```

- [ ] **Step 5: Add tests for required non-empty results returning unchanged**

Append to `tests/test_data_provider_availability.py`:

```python
@pytest.mark.unit
def test_required_non_empty_provider_result_is_returned_unchanged():
    result = pd.DataFrame({"Date": ["2026-05-01"], "Close": [101.25]})

    returned = normalize_provider_result(
        result,
        provider="alpha_vantage",
        method="get_stock_data",
        role=ProviderResultRole.REQUIRED,
        no_data_message="No price bars found",
    )

    assert returned is result
```

- [ ] **Step 6: Run the focused tests and confirm RED**

```bash
uv run pytest tests/test_data_provider_availability.py -q
```

Expected result: import failure for `tradingagents.dataflows.availability` before implementation.

## Task 2: Implement The Availability Helper Module

**Files:**
- Create: `tradingagents/dataflows/availability.py`

- [ ] **Step 1: Add the module, enum, and empty-result classifier**

Create `tradingagents/dataflows/availability.py`:

```python
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
```

- [ ] **Step 2: Add normalization for required vs optional results**

Append to `tradingagents/dataflows/availability.py`:

```python
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
```

- [ ] **Step 3: Run the focused tests and confirm GREEN**

```bash
uv run pytest tests/test_data_provider_availability.py -q
```

Expected result: all tests in `tests/test_data_provider_availability.py` pass.

## Task 3: Document The Contract In Architecture Guidelines

**Files:**
- Modify: `docs/project-architecture-guidelines.md`

- [ ] **Step 1: Check the document state before editing**

```bash
git status --short docs/project-architecture-guidelines.md
```

Expected current state in this planning checkout: `?? docs/project-architecture-guidelines.md`. Treat the file as a requested architecture input. Before staging it, review the final diff and confirm no unrelated user edits were pulled into the slice.

- [ ] **Step 2: Add the provider no-data contract under Error Handling Principles**

In `docs/project-architecture-guidelines.md`, add this subsection immediately after the existing `## Error Handling Principles` bullet list:

```markdown
### Provider No-Data Contract

Structured data adapters distinguish required top-level data from optional child collections.

- Raise `ProviderNoDataError` when a provider request succeeds but the requested required dataset has no usable rows or entity data after ticker, date, or `as_of` filtering. Examples include unknown tickers, unsupported tickers, no OHLCV bars in the requested date range, empty required fundamentals responses, and all required rows being filtered out.
- Return empty structured collections when emptiness is the valid domain answer for an optional child collection. Examples include no news articles, no insider transactions, no dividends, no splits, and no corporate-action events in range.
- Return partial structured objects with `None` fields or availability records when the entity exists but individual fields are missing.
- Raise `ProviderAuthError`, `ProviderRateLimitError`, or `ProviderUnavailableError` for credential/entitlement failures, quota/rate-limit failures, transport/timeouts, HTTP 5xx, and malformed provider responses.
- Keep caller validation errors, such as unsupported indicators or invalid date formats, as `ValueError`.
- Keep `route_to_vendor()` fallback broadening out of this contract slice; Slice `2A-S3` owns router fallback behavior.
```

- [ ] **Step 3: Confirm the docs diff is narrow**

```bash
git diff -- docs/project-architecture-guidelines.md
```

Expected result: only the provider no-data contract subsection is added.

## Task 4: Run Regression And Scope-Guard Verification

**Files:**
- Test: `tests/test_data_provider_availability.py`
- Test: `tests/test_data_provider_exceptions.py`
- Test: `tests/test_dataflows_config.py`
- Guard: `tradingagents/dataflows/interface.py`
- Guard: `tradingagents/dataflows/y_finance.py`
- Guard: `tradingagents/dataflows/yfinance_news.py`
- Guard: `tradingagents/dataflows/alpha_vantage_common.py`
- Guard: `tradingagents/dataflows/alpha_vantage.py`
- Guard: `tradingagents/dataflows/alpha_vantage_stock.py`
- Guard: `tradingagents/dataflows/alpha_vantage_indicator.py`
- Guard: `tradingagents/dataflows/alpha_vantage_fundamentals.py`
- Guard: `tradingagents/dataflows/alpha_vantage_news.py`
- Guard: `tradingagents/default_config.py`
- Guard: `.env.example`

- [ ] **Step 1: Run focused provider contract tests**

```bash
uv run pytest tests/test_data_provider_availability.py tests/test_data_provider_exceptions.py tests/test_dataflows_config.py -q
```

Expected result: all selected tests pass.

- [ ] **Step 2: Confirm router fallback was not broadened**

```bash
git diff -- tradingagents/dataflows/interface.py
```

Expected result: no diff.

- [ ] **Step 3: Confirm existing yfinance and Alpha Vantage wrappers were not broadly rewritten**

```bash
git diff -- tradingagents/dataflows/y_finance.py tradingagents/dataflows/yfinance_news.py tradingagents/dataflows/alpha_vantage_common.py tradingagents/dataflows/alpha_vantage.py tradingagents/dataflows/alpha_vantage_stock.py tradingagents/dataflows/alpha_vantage_indicator.py tradingagents/dataflows/alpha_vantage_fundamentals.py tradingagents/dataflows/alpha_vantage_news.py
```

Expected result: no diff for this slice.

- [ ] **Step 4: Confirm no provider registrations, config keys, or credentials were added**

```bash
git diff -- tradingagents/default_config.py .env.example
```

Expected result: no diff.

- [ ] **Step 5: Inspect the full intended diff**

```bash
git diff -- tradingagents/dataflows/availability.py tests/test_data_provider_availability.py docs/project-architecture-guidelines.md
```

Expected result: only the new availability helper, new tests, and architecture-doc contract section are present.

## Task 5: Documentation Drift Checkpoint

- [ ] **Step 1: Compare shipped behavior to roadmap docs**

Review the implementation against:

- `docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md`
- `docs/superpowers/specs/2026-05-04-platform-roadmap-design.md`
- `docs/project-architecture-guidelines.md`

- [ ] **Step 2: Update roadmap docs only if implementation scope changed**

No roadmap-doc update is expected if implementation stays inside this plan. Update the roadmap/spec docs only if any of these happen:

- `route_to_vendor()` starts catching `DataProviderError`.
- yfinance or Alpha Vantage wrappers are rewritten to raise shared errors broadly.
- Massive/Polygon, IBKR, provider config keys, credentials, or `VENDOR_METHODS` registrations are added.
- Structured equity schemas or structured entry points are added.

- [ ] **Step 3: Record the checkpoint in closeout**

Use this wording if no additional docs update is needed:

```text
Docs drift checkpoint: architecture guidelines now document the explicit no-data/provider-error contract; roadmap docs already scoped this work as Slice 2A-S2, and no router fallback, provider registration, config, credential, or structured schema behavior changed.
```

## Task 6: Commit The Slice

- [ ] **Step 1: Review git status**

```bash
git status --short
```

Expected result: intended changes include:

- `tradingagents/dataflows/availability.py`
- `tests/test_data_provider_availability.py`
- `docs/project-architecture-guidelines.md`

Unrelated `.DS_Store` files or other user-owned untracked files must remain unstaged.

- [ ] **Step 2: Stage only intended files**

```bash
git add tradingagents/dataflows/availability.py tests/test_data_provider_availability.py docs/project-architecture-guidelines.md
```

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(data): define provider no-data semantics"
```

## Completion Criteria

- `tradingagents/dataflows/availability.py` defines a tested required-vs-optional provider result helper.
- Required empty top-level structured results raise `ProviderNoDataError`.
- Optional empty structured collections return unchanged.
- Existing provider exception tests still pass.
- `route_to_vendor()` fallback behavior remains unchanged for Slice `2A-S3`.
- No Massive/Polygon, IBKR, config, credential, or provider-registration changes are introduced.
- No broad yfinance or Alpha Vantage adapter rewrite is introduced.
- Documentation drift checkpoint is completed and summarized.
