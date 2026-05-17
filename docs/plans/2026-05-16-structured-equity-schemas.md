---
initiative: trading-platform
phase: 2
slice: 2B-S1
status: planned
worktree: main
depends_on:
  - docs/plans/2026-05-16-router-fallback-contract.md
  - docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md
  - docs/superpowers/specs/2026-05-04-platform-roadmap-design.md
  - docs/project-architecture-guidelines.md
---

# Structured Equity Schemas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add importable, tested structured equity dataclasses for future screener, portfolio, and provider-adapter slices.

**Architecture:** Create `tradingagents/dataflows/structured.py` as the structured equity contract module called out in the roadmap. This slice defines schemas only: `FundamentalsSnapshot`, `PriceHistory`, `IndicatorSeries`, `DataAvailability`, and `AvailabilityStatus`. It does not fetch provider data, register providers, alter report-string tools, or route callers through the new schemas.

**Tech Stack:** Python 3.10+, standard-library dataclasses/enums, pandas DataFrame type annotations already used by the repo, pytest, no new dependencies.

---

## Scope

- Create `tradingagents/dataflows/structured.py`.
- Add `FundamentalsSnapshot`, `PriceHistory`, and `IndicatorSeries`.
- Add `DataAvailability` and `AvailabilityStatus` for missing/stale/available field metadata.
- Add focused schema tests in `tests/test_structured_equity_schemas.py`.
- Keep names and fields aligned with the roadmap schema block.

## Non-Goals

- No provider implementation.
- No yfinance, Alpha Vantage, Massive/Polygon, or IBKR adapter changes.
- No config keys, credentials, provider registrations, or `VENDOR_METHODS` changes.
- No `route_to_vendor()` changes.
- No screener filters, portfolio optimizer, or structured data entry points.
- No serialization helpers unless later cache/report code needs them.

## File Structure

- Create: `tradingagents/dataflows/structured.py`
- Create: `tests/test_structured_equity_schemas.py`
- No change expected: `tradingagents/dataflows/interface.py`
- No change expected: provider adapter modules
- No change expected: `tradingagents/default_config.py`
- No change expected: `.env.example`

## Task 1: Lock Schema Contract With Failing Tests

**Files:**
- Create: `tests/test_structured_equity_schemas.py`

- [ ] **Step 1: Add tests for fundamentals schema defaults and availability**

Create `tests/test_structured_equity_schemas.py`:

```python
import pandas as pd
import pytest

from tradingagents.dataflows.structured import (
    AvailabilityStatus,
    DataAvailability,
    FundamentalsSnapshot,
    IndicatorSeries,
    PRICE_HISTORY_COLUMNS,
    PriceHistory,
)


@pytest.mark.unit
def test_fundamentals_snapshot_defaults_optional_metrics_and_availability():
    availability = [
        DataAvailability(
            field="price_to_book",
            status=AvailabilityStatus.MISSING,
            message="Provider did not return price_to_book",
            provider="yfinance",
        )
    ]

    snapshot = FundamentalsSnapshot(
        ticker="AAPL",
        as_of="2026-05-16",
        market_cap=3_000_000_000_000,
        pe_ratio_trailing=28.5,
        availability=availability,
    )

    assert snapshot.ticker == "AAPL"
    assert snapshot.as_of == "2026-05-16"
    assert snapshot.market_cap == 3_000_000_000_000
    assert snapshot.pe_ratio_trailing == 28.5
    assert snapshot.pe_ratio_forward is None
    assert snapshot.price_to_book is None
    assert snapshot.free_cash_flow_yield is None
    assert snapshot.availability == availability
```

- [ ] **Step 2: Add tests for default availability list isolation**

Append to `tests/test_structured_equity_schemas.py`:

```python
@pytest.mark.unit
def test_schema_availability_lists_do_not_share_mutable_defaults():
    first = FundamentalsSnapshot(ticker="AAPL", as_of="2026-05-16")
    second = FundamentalsSnapshot(ticker="MSFT", as_of="2026-05-16")

    first.availability.append(
        DataAvailability(
            field="market_cap",
            status=AvailabilityStatus.MISSING,
            message="missing market cap",
        )
    )

    assert len(first.availability) == 1
    assert second.availability == []
```

- [ ] **Step 3: Add tests for price history schema**

Append to `tests/test_structured_equity_schemas.py`:

```python
@pytest.mark.unit
def test_price_history_tracks_ohlcv_dataframe_and_derived_metrics():
    data = pd.DataFrame(
        {
            "Date": ["2026-05-15"],
            "Open": [100.0],
            "High": [105.0],
            "Low": [99.0],
            "Close": [104.0],
            "Volume": [1_000_000],
        }
    )

    history = PriceHistory(
        ticker="AAPL",
        start="2026-05-01",
        end="2026-05-16",
        data=data,
        high_52w=110.0,
        low_52w=80.0,
        proximity_to_52w_high=-0.0545,
    )

    assert PRICE_HISTORY_COLUMNS == ("Date", "Open", "High", "Low", "Close", "Volume")
    assert history.data is data
    assert tuple(history.data.columns) == PRICE_HISTORY_COLUMNS
    assert history.high_52w == 110.0
    assert history.low_52w == 80.0
    assert history.proximity_to_52w_high == -0.0545
    assert history.availability == []
```

- [ ] **Step 4: Add tests for indicator and availability metadata**

Append to `tests/test_structured_equity_schemas.py`:

```python
@pytest.mark.unit
def test_indicator_series_and_availability_metadata_are_importable_contracts():
    values = pd.DataFrame({"Date": ["2026-05-15"], "RSI": [62.3]})
    availability = DataAvailability(
        field="latest_value",
        status=AvailabilityStatus.AVAILABLE,
        message="latest RSI value available",
        provider="alpha_vantage",
    )

    series = IndicatorSeries(
        ticker="AAPL",
        indicator="rsi",
        as_of="2026-05-16",
        window=14,
        values=values,
        latest_value=62.3,
        availability=[availability],
    )

    assert series.ticker == "AAPL"
    assert series.indicator == "rsi"
    assert series.as_of == "2026-05-16"
    assert series.window == 14
    assert series.values is values
    assert series.latest_value == 62.3
    assert series.availability == [availability]
    assert AvailabilityStatus.MISSING.value == "missing"
    assert AvailabilityStatus.STALE.value == "stale"
```

- [ ] **Step 5: Run focused tests and confirm RED**

```bash
uv run pytest tests/test_structured_equity_schemas.py -q
```

Expected result before implementation: import failure for `tradingagents.dataflows.structured`.

## Task 2: Implement Structured Equity Schema Module

**Files:**
- Create: `tradingagents/dataflows/structured.py`

- [ ] **Step 1: Add availability metadata types**

Create `tradingagents/dataflows/structured.py`:

```python
"""Structured equity data contracts for provider-neutral consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import pandas as pd


PRICE_HISTORY_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume")


class AvailabilityStatus(str, Enum):
    """Availability status for structured fields or child datasets."""

    AVAILABLE = "available"
    MISSING = "missing"
    STALE = "stale"


@dataclass
class DataAvailability:
    """Availability metadata for a structured field or child dataset."""

    field: str
    status: AvailabilityStatus
    message: str
    provider: str | None = None
```

- [ ] **Step 2: Add `FundamentalsSnapshot`**

Append to `tradingagents/dataflows/structured.py`:

```python
@dataclass
class FundamentalsSnapshot:
    """Structured fundamentals data for a single ticker at a point in time."""

    ticker: str
    as_of: str
    market_cap: float | None = None
    pe_ratio_trailing: float | None = None
    pe_ratio_forward: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    enterprise_value: float | None = None
    revenue_ttm: float | None = None
    net_income_ttm: float | None = None
    free_cash_flow: float | None = None
    profit_margin: float | None = None
    roe: float | None = None
    total_debt: float | None = None
    total_equity: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    dividend_yield: float | None = None
    payout_ratio: float | None = None
    revenue_growth_yoy: float | None = None
    earnings_growth_yoy: float | None = None
    free_cash_flow_yield: float | None = None
    availability: list[DataAvailability] = field(default_factory=list)
```

- [ ] **Step 3: Add `PriceHistory` and `IndicatorSeries`**

Append to `tradingagents/dataflows/structured.py`:

```python
@dataclass
class PriceHistory:
    """OHLCV price history for a ticker."""

    ticker: str
    start: str
    end: str
    data: pd.DataFrame
    high_52w: float | None = None
    low_52w: float | None = None
    proximity_to_52w_high: float | None = None
    availability: list[DataAvailability] = field(default_factory=list)


@dataclass
class IndicatorSeries:
    """Technical indicator values for a ticker."""

    ticker: str
    indicator: str
    as_of: str
    window: int
    values: pd.DataFrame
    latest_value: float | None = None
    availability: list[DataAvailability] = field(default_factory=list)
```

- [ ] **Step 4: Add explicit exports**

Append to `tradingagents/dataflows/structured.py`:

```python
__all__ = [
    "AvailabilityStatus",
    "DataAvailability",
    "FundamentalsSnapshot",
    "IndicatorSeries",
    "PRICE_HISTORY_COLUMNS",
    "PriceHistory",
]
```

- [ ] **Step 5: Run focused tests and confirm GREEN**

```bash
uv run pytest tests/test_structured_equity_schemas.py -q
```

Expected result: all structured schema tests pass.

## Task 3: Regression And Scope-Guard Verification

- [ ] **Step 1: Run schema and recent data-layer tests**

```bash
uv run pytest tests/test_structured_equity_schemas.py tests/test_data_provider_availability.py tests/test_dataflows_router_fallback.py tests/test_data_provider_exceptions.py -q
```

Expected result: all selected tests pass.

- [ ] **Step 2: Confirm provider adapters and router/config were not changed**

```bash
git diff -- tradingagents/dataflows/interface.py tradingagents/dataflows/y_finance.py tradingagents/dataflows/yfinance_news.py tradingagents/dataflows/alpha_vantage_common.py tradingagents/dataflows/alpha_vantage.py tradingagents/dataflows/alpha_vantage_stock.py tradingagents/dataflows/alpha_vantage_indicator.py tradingagents/dataflows/alpha_vantage_fundamentals.py tradingagents/dataflows/alpha_vantage_news.py tradingagents/default_config.py .env.example
```

Expected result: no diff.

## Task 4: Documentation Drift Checkpoint

- [ ] **Step 1: Compare implementation to durable docs**

Check:

- `docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md`
- `docs/superpowers/specs/2026-05-04-platform-roadmap-design.md`
- `docs/project-architecture-guidelines.md`

- [ ] **Step 2: Update docs only if behavior drifted**

No docs update is expected if implementation stays inside this plan: this slice creates the schema names and field shapes already described by the roadmap and architecture docs.

- [ ] **Step 3: Record checkpoint in closeout**

Use this wording if no docs update is needed:

```text
Docs drift checkpoint: no durable docs update needed; this slice implements the already-planned 2B-S1 structured equity schema names and fields without provider implementation, router changes, config keys, credentials, or user-facing workflow changes.
```

## Task 5: Commit The Slice

- [ ] **Step 1: Stage only intended files**

```bash
git add docs/plans/2026-05-16-structured-equity-schemas.md tests/test_structured_equity_schemas.py tradingagents/dataflows/structured.py
```

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(data): add structured equity schemas"
```

## Completion Criteria

- `tradingagents/dataflows/structured.py` is importable.
- `FundamentalsSnapshot`, `PriceHistory`, `IndicatorSeries`, and availability metadata exist and are tested.
- Recent provider error, availability, and router fallback tests still pass.
- No provider adapter, router, config, credential, or user-facing report behavior changes are introduced.
