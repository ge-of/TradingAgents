---
initiative: trading-platform
phase: 2
slice: 2B-S2
status: planned
worktree: main
depends_on:
  - docs/plans/2026-05-16-structured-equity-schemas.md
  - docs/plans/2026-05-16-router-fallback-contract.md
  - docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md
  - docs/superpowers/specs/2026-05-04-platform-roadmap-design.md
  - docs/project-architecture-guidelines.md
---

# Structured Data Entry Points Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add provider-neutral structured equity entry points for price history, fundamentals, and indicators so future consumers can call typed data APIs without using agent-facing report strings.

**Architecture:** Extend `tradingagents/dataflows/structured.py` with a small structured-provider registry and dispatcher separate from `route_to_vendor()`. The dispatcher reads the existing `data_vendors` and `tool_vendors` config keys, calls registered structured provider functions, falls back on `DataProviderError`, and returns the typed dataclasses added in 2B-S1. This slice proves the entry-point contract with fake providers only; real yfinance, Alpha Vantage, Massive, and IBKR adapters come later.

**Tech Stack:** Python 3.10+, standard-library callables/type hints, existing `dataflows.config`, existing `DataProviderError` hierarchy, pytest, pandas already present in the repo, no new dependencies.

---

## Brainstormed Approach

Considered options:

1. Reuse `route_to_vendor()` and `VENDOR_METHODS` for structured calls.
   - Pros: one router.
   - Cons: mixes string/report tools with typed structured functions and risks breaking agent-facing report boundaries.

2. Add one-off config selection inside each public entry point.
   - Pros: shortest code.
   - Cons: duplicates fallback/config behavior across price, fundamentals, and indicators.

3. Add a separate structured dispatcher in `structured.py`.
   - Pros: keeps agent-facing routing untouched, centralizes structured fallback, and gives future adapters a typed registry.
   - Cons: introduces a small second registry.

Recommendation: option 3. It best matches the architecture docs: string/report tools stay separate from structured numeric contracts.

## Scope

- Extend `tradingagents/dataflows/structured.py`.
- Add `STRUCTURED_VENDOR_METHODS`.
- Add structured methods:
  - `get_price_history(ticker, start, end) -> PriceHistory`
  - `get_fundamentals_snapshot(ticker, as_of) -> FundamentalsSnapshot`
  - `get_indicator_series(ticker, indicator, as_of, window) -> IndicatorSeries`
- Route through existing `data_vendors` category config and `tool_vendors` method override config.
- Fall back across registered structured providers when a provider raises `DataProviderError`.
- Add fake-provider tests in `tests/test_structured_data_entry_points.py`.

## Non-Goals

- No yfinance structured implementation.
- No Alpha Vantage structured implementation.
- No Massive/Polygon or IBKR implementation.
- No config keys, credentials, `.env.example` changes, or new provider names.
- No `VENDOR_METHODS` changes.
- No `route_to_vendor()` changes.
- No CLI, screener, portfolio, graph, or `_fetch_returns()` adoption.
- No serialization/cache/report rendering helpers.

## File Structure

- Modify: `tradingagents/dataflows/structured.py`
- Create: `tests/test_structured_data_entry_points.py`
- No change expected: `tradingagents/dataflows/interface.py`
- No change expected: provider adapter modules
- No change expected: `tradingagents/default_config.py`
- No change expected: `.env.example`

## Task 1: Lock Structured Entry Point Contract With Failing Tests

**Files:**
- Create: `tests/test_structured_data_entry_points.py`

- [ ] **Step 1: Add test scaffolding and price-history category selection test**

Create `tests/test_structured_data_entry_points.py`:

```python
import copy

import pandas as pd
import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from tradingagents.dataflows import structured
from tradingagents.dataflows.exceptions import DataProviderError, ProviderUnavailableError
from tradingagents.dataflows.structured import (
    FundamentalsSnapshot,
    IndicatorSeries,
    PriceHistory,
)


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


@pytest.mark.unit
def test_get_price_history_uses_category_configured_structured_provider(monkeypatch):
    calls = []

    def fake_price_history(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append((ticker, start, end))
        return PriceHistory(
            ticker=ticker,
            start=start,
            end=end,
            data=pd.DataFrame(
                {
                    "Date": ["2026-05-15"],
                    "Open": [100.0],
                    "High": [105.0],
                    "Low": [99.0],
                    "Close": [104.0],
                    "Volume": [1_000_000],
                }
            ),
        )

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "fake_prices",
        fake_price_history,
    )
    config_module.set_config({"data_vendors": {"core_stock_apis": "fake_prices"}})

    result = structured.get_price_history("AAPL", "2026-05-01", "2026-05-16")

    assert isinstance(result, PriceHistory)
    assert result.ticker == "AAPL"
    assert result.start == "2026-05-01"
    assert result.end == "2026-05-16"
    assert calls == [("AAPL", "2026-05-01", "2026-05-16")]
```

- [ ] **Step 2: Add tool-level override test**

Append to `tests/test_structured_data_entry_points.py`:

```python
@pytest.mark.unit
def test_structured_tool_vendor_overrides_category_vendor(monkeypatch):
    calls = []

    def category_provider(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append("category")
        return PriceHistory(ticker=ticker, start=start, end=end, data=pd.DataFrame())

    def override_provider(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append("override")
        return PriceHistory(
            ticker=ticker,
            start=start,
            end=end,
            data=pd.DataFrame({"Date": ["2026-05-15"]}),
        )

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "category_prices",
        category_provider,
    )
    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "override_prices",
        override_provider,
    )
    config_module.set_config(
        {
            "data_vendors": {"core_stock_apis": "category_prices"},
            "tool_vendors": {"get_price_history": "override_prices"},
        }
    )

    result = structured.get_price_history("MSFT", "2026-05-01", "2026-05-16")

    assert result.data["Date"].tolist() == ["2026-05-15"]
    assert calls == ["override"]
```

- [ ] **Step 3: Add fallback and all-providers-failing tests**

Append to `tests/test_structured_data_entry_points.py`:

```python
@pytest.mark.unit
def test_structured_entry_point_falls_back_on_data_provider_error(monkeypatch):
    calls = []

    def failing_provider(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append("primary")
        raise ProviderUnavailableError(
            "primary unavailable",
            provider="primary_prices",
            method="get_price_history",
        )

    def fallback_provider(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append("fallback")
        return PriceHistory(
            ticker=ticker,
            start=start,
            end=end,
            data=pd.DataFrame({"Date": ["2026-05-15"], "Close": [104.0]}),
        )

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "primary_prices",
        failing_provider,
    )
    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "fallback_prices",
        fallback_provider,
    )
    config_module.set_config({"data_vendors": {"core_stock_apis": "primary_prices"}})

    result = structured.get_price_history("NVDA", "2026-05-01", "2026-05-16")

    assert result.ticker == "NVDA"
    assert calls == ["primary", "fallback"]


@pytest.mark.unit
def test_structured_entry_point_raises_runtime_error_when_no_provider_succeeds(monkeypatch):
    calls = []

    def failing_provider(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append("primary")
        raise DataProviderError(
            "provider failed",
            provider="primary_prices",
            method="get_price_history",
        )

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "primary_prices",
        failing_provider,
    )
    config_module.set_config({"data_vendors": {"core_stock_apis": "primary_prices"}})

    with pytest.raises(RuntimeError, match="No available structured provider for 'get_price_history'"):
        structured.get_price_history("NVDA", "2026-05-01", "2026-05-16")

    assert calls == ["primary"]
```

- [ ] **Step 4: Add fundamentals and indicator entry point tests**

Append to `tests/test_structured_data_entry_points.py`:

```python
@pytest.mark.unit
def test_get_fundamentals_snapshot_routes_through_fundamental_data_config(monkeypatch):
    calls = []

    def fake_fundamentals(ticker: str, as_of: str) -> FundamentalsSnapshot:
        calls.append((ticker, as_of))
        return FundamentalsSnapshot(
            ticker=ticker,
            as_of=as_of,
            market_cap=3_000_000_000_000,
            pe_ratio_trailing=28.5,
        )

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_fundamentals_snapshot"],
        "fake_fundamentals",
        fake_fundamentals,
    )
    config_module.set_config({"data_vendors": {"fundamental_data": "fake_fundamentals"}})

    result = structured.get_fundamentals_snapshot("AAPL", "2026-05-16")

    assert isinstance(result, FundamentalsSnapshot)
    assert result.market_cap == 3_000_000_000_000
    assert calls == [("AAPL", "2026-05-16")]


@pytest.mark.unit
def test_get_indicator_series_routes_through_technical_indicators_config(monkeypatch):
    calls = []

    def fake_indicator(ticker: str, indicator: str, as_of: str, window: int) -> IndicatorSeries:
        calls.append((ticker, indicator, as_of, window))
        return IndicatorSeries(
            ticker=ticker,
            indicator=indicator,
            as_of=as_of,
            window=window,
            values=pd.DataFrame({"Date": ["2026-05-15"], "RSI": [62.3]}),
            latest_value=62.3,
        )

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_indicator_series"],
        "fake_indicators",
        fake_indicator,
    )
    config_module.set_config({"data_vendors": {"technical_indicators": "fake_indicators"}})

    result = structured.get_indicator_series("AAPL", "rsi", "2026-05-16", 14)

    assert isinstance(result, IndicatorSeries)
    assert result.latest_value == 62.3
    assert calls == [("AAPL", "rsi", "2026-05-16", 14)]
```

- [ ] **Step 5: Add unsupported method guard test**

Append to `tests/test_structured_data_entry_points.py`:

```python
@pytest.mark.unit
def test_structured_dispatch_rejects_unknown_methods():
    with pytest.raises(ValueError, match="Structured method 'not_real' not supported"):
        structured.route_structured_method("not_real")
```

- [ ] **Step 6: Run focused tests and confirm RED**

```bash
uv run pytest tests/test_structured_data_entry_points.py -q
```

Expected result before implementation: import or attribute failure because the structured entry points and `STRUCTURED_VENDOR_METHODS` do not exist yet.

## Task 2: Add Structured Dispatcher And Entry Points

**Files:**
- Modify: `tradingagents/dataflows/structured.py`

- [ ] **Step 1: Add imports, category map, registry, and helper type**

In `tradingagents/dataflows/structured.py`, add these imports below the existing imports:

```python
from collections.abc import Callable
from typing import Any, TypeVar

from .config import get_config
from .exceptions import DataProviderError
```

Then add this after `PRICE_HISTORY_COLUMNS`:

```python
T = TypeVar("T")
StructuredProvider = Callable[..., Any]

STRUCTURED_METHOD_CATEGORIES = {
    "get_price_history": "core_stock_apis",
    "get_fundamentals_snapshot": "fundamental_data",
    "get_indicator_series": "technical_indicators",
}

STRUCTURED_VENDOR_METHODS: dict[str, dict[str, StructuredProvider]] = {
    "get_price_history": {},
    "get_fundamentals_snapshot": {},
    "get_indicator_series": {},
}
```

- [ ] **Step 2: Add config and fallback helpers**

Append this after the dataclass definitions and before `__all__`:

```python
def _get_structured_vendor_config(method: str) -> str:
    if method not in STRUCTURED_METHOD_CATEGORIES:
        raise ValueError(f"Structured method '{method}' not supported")

    config = get_config()
    tool_vendors = config.get("tool_vendors", {})
    if method in tool_vendors:
        return tool_vendors[method]

    category = STRUCTURED_METHOD_CATEGORIES[method]
    return config.get("data_vendors", {}).get(category, "default")


def _build_structured_fallback_chain(method: str) -> list[str]:
    vendor_config = _get_structured_vendor_config(method)
    configured_vendors = [vendor.strip() for vendor in vendor_config.split(",") if vendor.strip()]
    available_vendors = list(STRUCTURED_VENDOR_METHODS[method].keys())

    fallback_chain = configured_vendors.copy()
    for vendor in available_vendors:
        if vendor not in fallback_chain:
            fallback_chain.append(vendor)

    return fallback_chain
```

- [ ] **Step 3: Add `route_structured_method()`**

Append this after `_build_structured_fallback_chain()`:

```python
def route_structured_method(method: str, *args: Any, **kwargs: Any) -> Any:
    """Route a structured data request to the configured structured provider."""
    if method not in STRUCTURED_VENDOR_METHODS:
        raise ValueError(f"Structured method '{method}' not supported")

    for vendor in _build_structured_fallback_chain(method):
        provider_impl = STRUCTURED_VENDOR_METHODS[method].get(vendor)
        if provider_impl is None:
            continue

        try:
            return provider_impl(*args, **kwargs)
        except DataProviderError:
            continue

    raise RuntimeError(f"No available structured provider for '{method}'")
```

- [ ] **Step 4: Add public entry points**

Append this after `route_structured_method()`:

```python
def get_price_history(ticker: str, start: str, end: str) -> PriceHistory:
    """Return structured OHLCV history from the configured structured provider."""
    return route_structured_method("get_price_history", ticker, start, end)


def get_fundamentals_snapshot(ticker: str, as_of: str) -> FundamentalsSnapshot:
    """Return structured fundamentals from the configured structured provider."""
    return route_structured_method("get_fundamentals_snapshot", ticker, as_of)


def get_indicator_series(
    ticker: str,
    indicator: str,
    as_of: str,
    window: int,
) -> IndicatorSeries:
    """Return structured technical indicators from the configured structured provider."""
    return route_structured_method("get_indicator_series", ticker, indicator, as_of, window)
```

- [ ] **Step 5: Update `__all__`**

Replace the existing `__all__` list with:

```python
__all__ = [
    "AvailabilityStatus",
    "DataAvailability",
    "FundamentalsSnapshot",
    "IndicatorSeries",
    "PRICE_HISTORY_COLUMNS",
    "PriceHistory",
    "STRUCTURED_METHOD_CATEGORIES",
    "STRUCTURED_VENDOR_METHODS",
    "get_fundamentals_snapshot",
    "get_indicator_series",
    "get_price_history",
    "route_structured_method",
]
```

- [ ] **Step 6: Run focused tests and confirm GREEN**

```bash
uv run pytest tests/test_structured_data_entry_points.py -q
```

Expected result: all structured entry point tests pass.

## Task 3: Regression And Scope-Guard Verification

- [ ] **Step 1: Run structured and recent data-layer tests**

```bash
uv run pytest tests/test_structured_data_entry_points.py tests/test_structured_equity_schemas.py tests/test_data_provider_availability.py tests/test_dataflows_router_fallback.py tests/test_data_provider_exceptions.py tests/test_dataflows_config.py -q
```

Expected result: all selected tests pass.

- [ ] **Step 2: Confirm agent-facing router and provider adapters were not changed**

```bash
git diff -- tradingagents/dataflows/interface.py tradingagents/dataflows/y_finance.py tradingagents/dataflows/yfinance_news.py tradingagents/dataflows/alpha_vantage_common.py tradingagents/dataflows/alpha_vantage.py tradingagents/dataflows/alpha_vantage_stock.py tradingagents/dataflows/alpha_vantage_indicator.py tradingagents/dataflows/alpha_vantage_fundamentals.py tradingagents/dataflows/alpha_vantage_news.py
```

Expected result: no diff.

- [ ] **Step 3: Confirm no config, credential, or CLI changes were added**

```bash
git diff -- tradingagents/default_config.py .env.example cli/main.py
```

Expected result: no diff.

## Task 4: Documentation Drift Checkpoint

- [ ] **Step 1: Compare implementation to durable docs**

Check:

- `docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md`
- `docs/superpowers/specs/2026-05-04-platform-roadmap-design.md`
- `docs/project-architecture-guidelines.md`

- [ ] **Step 2: Update docs only if behavior drifted**

No docs update is expected if implementation stays inside this plan. The existing roadmap already defines 2B-S2 as structured entry points routed through config/provider selection, and architecture guidelines already assign numeric structured data access to `tradingagents/dataflows/`.

- [ ] **Step 3: Record checkpoint in closeout**

Use this wording if no docs update is needed:

```text
Docs drift checkpoint: no durable docs update needed; this slice implements the already-planned 2B-S2 structured entry points without provider adapter implementation, agent-facing router changes, config keys, credentials, CLI changes, or user-facing workflow changes.
```

## Task 5: Commit The Slice

- [ ] **Step 1: Stage only intended files**

```bash
git add docs/plans/2026-05-16-structured-data-entry-points.md tests/test_structured_data_entry_points.py tradingagents/dataflows/structured.py
```

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(data): add structured data entry points"
```

## Completion Criteria

- `get_price_history()`, `get_fundamentals_snapshot()`, and `get_indicator_series()` are importable from `tradingagents.dataflows.structured`.
- The entry points read existing dataflow config and support method-level overrides through `tool_vendors`.
- Structured providers can be registered in `STRUCTURED_VENDOR_METHODS`.
- `DataProviderError` subclasses trigger fallback across registered structured providers.
- Recent schema, provider availability, router fallback, provider exception, and config tests pass.
- No provider adapter implementation, agent-facing router change, config key, credential, CLI, screener, portfolio, graph, or report behavior change is introduced.
