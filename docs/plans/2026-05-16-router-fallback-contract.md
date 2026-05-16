---
initiative: trading-platform
phase: 2
slice: 2A-S3
status: planned
worktree: main
depends_on:
  - docs/plans/2026-05-15-data-provider-error-hierarchy.md
  - docs/plans/2026-05-15-no-data-provider-error-semantics.md
  - docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md
  - docs/project-architecture-guidelines.md
---

# Router Fallback Contract Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Broaden `route_to_vendor()` fallback so shared `DataProviderError` subclasses trigger provider fallback while agent-facing tool signatures remain unchanged.

**Architecture:** Add mocked router contract tests around the existing `tradingagents/dataflows/interface.py` dispatch path. Then replace the Alpha-Vantage-only catch in `route_to_vendor()` with the shared `DataProviderError` catch, relying on `AlphaVantageRateLimitError` inheritance to preserve existing rate-limit fallback behavior.

**Tech Stack:** Python 3.10+, pytest, existing dataflows config/router modules, no new dependencies.

---

## Scope

- Add `tests/test_dataflows_router_fallback.py`.
- Test primary `DataProviderError` fallback success.
- Test existing `AlphaVantageRateLimitError` fallback success still works.
- Test all available providers failing with `DataProviderError` still raises `RuntimeError`.
- Modify only `tradingagents/dataflows/interface.py` for router fallback behavior.

## Non-Goals

- No Massive/Polygon, IBKR, config keys, credentials, or `VENDOR_METHODS` registrations.
- No provider-specific yfinance or Alpha Vantage adapter rewrites.
- No structured equity schemas or structured entry points.
- No change to agent-facing tool signatures or return shapes.
- No retry policy, logging policy, or exception aggregation redesign.

## File Structure

- Create: `tests/test_dataflows_router_fallback.py`
- Modify: `tradingagents/dataflows/interface.py`
- No change expected: `tradingagents/dataflows/y_finance.py`
- No change expected: `tradingagents/dataflows/yfinance_news.py`
- No change expected: `tradingagents/dataflows/alpha_vantage*.py`
- No change expected: `tradingagents/default_config.py`
- No change expected: `.env.example`

## Task 1: Lock Router Fallback Behavior With Failing Tests

**Files:**
- Create: `tests/test_dataflows_router_fallback.py`

- [ ] **Step 1: Add router fallback tests**

Create `tests/test_dataflows_router_fallback.py`:

```python
import copy

import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows import interface
from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.exceptions import DataProviderError, ProviderUnavailableError


@pytest.fixture(autouse=True)
def reset_dataflows_config():
    set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))
    yield
    set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))


@pytest.mark.unit
def test_route_to_vendor_falls_back_after_data_provider_error(monkeypatch):
    calls = []

    def failing_primary(*args, **kwargs):
        calls.append(("alpha_vantage", args, kwargs))
        raise DataProviderError(
            "primary provider failed",
            provider="alpha_vantage",
            method="get_stock_data",
            retryable=True,
        )

    def fallback_provider(*args, **kwargs):
        calls.append(("yfinance", args, kwargs))
        return "fallback stock data"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "alpha_vantage": failing_primary,
            "yfinance": fallback_provider,
        },
    )
    set_config({"tool_vendors": {"get_stock_data": "alpha_vantage"}})

    result = interface.route_to_vendor("get_stock_data", "AAPL", "2026-05-01", "2026-05-02")

    assert result == "fallback stock data"
    assert [call[0] for call in calls] == ["alpha_vantage", "yfinance"]
    assert calls[0][1] == ("AAPL", "2026-05-01", "2026-05-02")
```

- [ ] **Step 2: Add Alpha Vantage compatibility test**

Append to `tests/test_dataflows_router_fallback.py`:

```python
@pytest.mark.unit
def test_route_to_vendor_preserves_alpha_vantage_rate_limit_fallback(monkeypatch):
    calls = []

    def rate_limited_primary(*args, **kwargs):
        calls.append("alpha_vantage")
        raise AlphaVantageRateLimitError("Alpha Vantage rate limit exceeded")

    def fallback_provider(*args, **kwargs):
        calls.append("yfinance")
        return "fallback after rate limit"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "alpha_vantage": rate_limited_primary,
            "yfinance": fallback_provider,
        },
    )
    set_config({"tool_vendors": {"get_stock_data": "alpha_vantage"}})

    result = interface.route_to_vendor("get_stock_data", "MSFT", "2026-05-01", "2026-05-02")

    assert result == "fallback after rate limit"
    assert calls == ["alpha_vantage", "yfinance"]
```

- [ ] **Step 3: Add all-providers-failing test**

Append to `tests/test_dataflows_router_fallback.py`:

```python
@pytest.mark.unit
def test_route_to_vendor_raises_runtime_error_when_all_providers_fail(monkeypatch):
    calls = []

    def failing_alpha(*args, **kwargs):
        calls.append("alpha_vantage")
        raise DataProviderError(
            "alpha failed",
            provider="alpha_vantage",
            method="get_stock_data",
        )

    def failing_yfinance(*args, **kwargs):
        calls.append("yfinance")
        raise ProviderUnavailableError(
            "yfinance unavailable",
            provider="yfinance",
            method="get_stock_data",
        )

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "alpha_vantage": failing_alpha,
            "yfinance": failing_yfinance,
        },
    )
    set_config({"tool_vendors": {"get_stock_data": "alpha_vantage"}})

    with pytest.raises(RuntimeError, match="No available vendor for 'get_stock_data'"):
        interface.route_to_vendor("get_stock_data", "NVDA", "2026-05-01", "2026-05-02")

    assert calls == ["alpha_vantage", "yfinance"]
```

- [ ] **Step 4: Run focused router tests and confirm RED**

```bash
uv run pytest tests/test_dataflows_router_fallback.py -q
```

Expected result before implementation: the `DataProviderError` fallback test fails because `route_to_vendor()` still catches only `AlphaVantageRateLimitError`.

## Task 2: Broaden Router Catch To Shared Provider Errors

**Files:**
- Modify: `tradingagents/dataflows/interface.py`

- [ ] **Step 1: Import the shared base error**

In `tradingagents/dataflows/interface.py`, replace:

```python
from .alpha_vantage_common import AlphaVantageRateLimitError
```

with:

```python
from .exceptions import DataProviderError
```

- [ ] **Step 2: Catch shared provider errors in the fallback loop**

Replace:

```python
        except AlphaVantageRateLimitError:
            continue  # Only rate limits trigger fallback
```

with:

```python
        except DataProviderError:
            continue
```

- [ ] **Step 3: Run focused router tests and confirm GREEN**

```bash
uv run pytest tests/test_dataflows_router_fallback.py -q
```

Expected result: all router fallback tests pass.

## Task 3: Regression And Scope-Guard Verification

- [ ] **Step 1: Run provider/router regression tests**

```bash
uv run pytest tests/test_dataflows_router_fallback.py tests/test_data_provider_exceptions.py tests/test_data_provider_availability.py tests/test_dataflows_config.py -q
```

Expected result: all selected tests pass.

- [ ] **Step 2: Confirm provider adapters were not rewritten**

```bash
git diff -- tradingagents/dataflows/y_finance.py tradingagents/dataflows/yfinance_news.py tradingagents/dataflows/alpha_vantage_common.py tradingagents/dataflows/alpha_vantage.py tradingagents/dataflows/alpha_vantage_stock.py tradingagents/dataflows/alpha_vantage_indicator.py tradingagents/dataflows/alpha_vantage_fundamentals.py tradingagents/dataflows/alpha_vantage_news.py
```

Expected result: no diff.

- [ ] **Step 3: Confirm no config, credentials, or provider registrations were added**

```bash
git diff -- tradingagents/default_config.py .env.example
```

Expected result: no diff.

## Task 4: Documentation Drift Checkpoint

- [ ] **Step 1: Review docs against shipped behavior**

Check:

- `docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md`
- `docs/project-architecture-guidelines.md`

- [ ] **Step 2: Update docs only if needed**

No docs update is expected if implementation stays inside this plan: the roadmap already scopes 2A-S3 as router fallback for shared provider errors, and architecture guidelines already say provider errors should normalize into the shared hierarchy if fallback should work beyond Alpha Vantage rate limits.

- [ ] **Step 3: Record checkpoint in closeout**

Use this wording if no docs update is needed:

```text
Docs drift checkpoint: no durable docs update needed; this slice implements the already-planned 2A-S3 router fallback behavior without provider adapter rewrites, provider registrations, config keys, credentials, or user-facing tool signature changes.
```

## Task 5: Commit The Slice

- [ ] **Step 1: Stage only intended files**

```bash
git add docs/plans/2026-05-16-router-fallback-contract.md tests/test_dataflows_router_fallback.py tradingagents/dataflows/interface.py
```

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(data): broaden router provider fallback"
```

## Completion Criteria

- `route_to_vendor()` catches shared `DataProviderError` subclasses for fallback.
- Existing `AlphaVantageRateLimitError` fallback behavior still works through inheritance.
- All configured available providers failing still raises `RuntimeError`.
- Agent-facing tool signatures and return shapes are unchanged.
- No Massive/Polygon, IBKR, provider config, credential, or adapter rewrite is introduced.
- Focused regression tests pass.
