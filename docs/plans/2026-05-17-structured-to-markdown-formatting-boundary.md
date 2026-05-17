---
initiative: trading-platform
phase: 2
slice: 2B-S4
status: planned
worktree: main
depends_on:
  - docs/plans/2026-05-16-structured-equity-schemas.md
  - docs/plans/2026-05-16-structured-data-entry-points.md
  - docs/plans/2026-05-17-no-look-ahead-as-of-contract.md
  - docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md
  - docs/superpowers/specs/2026-05-04-platform-roadmap-design.md
  - docs/project-architecture-guidelines.md
---

# Structured-To-Markdown Formatting Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tested conversion boundary from structured equity dataclasses to deterministic report-style Markdown while leaving structured callers typed and agent-facing tools string-based.

**Architecture:** Create a sidecar formatter module under `tradingagents/dataflows/` that imports the structured equity dataclasses and renders them to Markdown/report strings. The module is pure formatting: it does not fetch data, register providers, alter `VENDOR_METHODS`, change `route_to_vendor()`, or wire agent tools to structured providers. Future provider adapter slices can call these formatters from string wrapper functions when they are explicitly ready to register a provider.

**Tech Stack:** Python 3.10+, existing structured dataclasses, pandas already present in the repo, pytest, no new dependencies.

---

## Brainstormed Approach

Considered options:

1. Add `to_markdown()` methods to `FundamentalsSnapshot`, `PriceHistory`, and `IndicatorSeries`.
   - Pros: formatter lives directly on the data objects.
   - Cons: couples the typed contract to presentation, grows `structured.py`, and makes future report variants harder to add.

2. Add a sidecar `tradingagents/dataflows/structured_markdown.py` module with pure formatter functions.
   - Pros: keeps dataclasses typed and focused, keeps render helpers next to the structured data package, and gives future string wrappers a stable conversion API.
   - Cons: adds one small module that callers must import explicitly.

3. Add provider wrapper functions and register them in `VENDOR_METHODS` now.
   - Pros: proves the end-to-end agent-facing route immediately.
   - Cons: widens this slice into provider/router behavior before Massive or another structured provider exists.

Recommendation: option 2. It preserves the typed/prose boundary called out in the roadmap and architecture docs without prematurely registering providers or changing agent-facing routes.

## Contract Decisions

- Formatter ownership: `tradingagents/dataflows/structured_markdown.py`.
- Function shape:
  - `format_fundamentals_snapshot_markdown(snapshot: FundamentalsSnapshot) -> str`
  - `format_price_history_markdown(history: PriceHistory) -> str`
  - `format_indicator_series_markdown(series: IndicatorSeries) -> str`
  - `format_data_availability_markdown(availability: Sequence[DataAvailability]) -> str`
  - `format_structured_data_markdown(result: FundamentalsSnapshot | PriceHistory | IndicatorSeries) -> str`
- Formatters are deterministic. They do not include wall-clock retrieval timestamps.
- Formatters omit unavailable optional numeric fields from primary metric sections and render explicit availability records under `## Data Availability`.
- Price history renders the existing report-string style: stock-data heading, total record count, derived 52-week metrics when present, then CSV rows from the typed dataframe.
- Fundamentals renders the existing label style used by the yfinance report path: `Label: value`, with deterministic `# As of: YYYY-MM-DD` instead of a retrieval timestamp.
- Indicator series renders the existing indicator report style: a `## INDICATOR values from start to as_of:` heading and one `YYYY-MM-DD: value` line per row.
- No formatter calls `route_to_vendor()`, changes provider config, or mutates structured objects.

## Scope

- Add formatter tests for fundamentals, price history, indicators, availability records, and generic dispatch.
- Add `tradingagents/dataflows/structured_markdown.py`.
- Keep agent-facing tools receiving strings through the existing router path. This slice only creates the conversion boundary; it does not wire the boundary into tool registration.
- Execute this implementation after 2B-S3 has landed, so `tests/test_structured_as_of_contract.py` exists for adjacent verification.

## Non-Goals

- No prompt rewrites.
- No graph topology changes.
- No Massive/Polygon, yfinance, Alpha Vantage, or IBKR structured adapter implementation.
- No provider registration.
- No `VENDOR_METHODS` changes.
- No `route_to_vendor()` changes.
- No new config keys, credentials, `.env.example` edits, or CLI behavior.
- No screener, portfolio, batch, or `_fetch_returns()` adoption.
- No report layout redesign outside structured equity formatter output.

## File Structure

- Create: `tradingagents/dataflows/structured_markdown.py`
- Create: `tests/test_structured_markdown_formatting.py`
- No change expected: `tradingagents/dataflows/structured.py`
- No change expected: `tradingagents/dataflows/interface.py`
- No change expected: provider adapter modules under `tradingagents/dataflows/`
- No change expected: `tradingagents/default_config.py`
- No change expected: `.env.example`
- No change expected: `cli/`
- No change expected: `tradingagents/graph/`
- No change expected: `tradingagents/screener/`
- No change expected: portfolio modules

## Task 1: Lock Formatter Behavior With Failing Tests

**Files:**
- Create: `tests/test_structured_markdown_formatting.py`

- [ ] **Step 1: Add imports and fundamentals formatter test**

Create `tests/test_structured_markdown_formatting.py`:

```python
import pandas as pd
import pytest

from tradingagents.dataflows.structured import (
    AvailabilityStatus,
    DataAvailability,
    FundamentalsSnapshot,
    IndicatorSeries,
    PriceHistory,
)
from tradingagents.dataflows.structured_markdown import (
    format_fundamentals_snapshot_markdown,
    format_indicator_series_markdown,
    format_price_history_markdown,
    format_structured_data_markdown,
)


@pytest.mark.unit
def test_format_fundamentals_snapshot_markdown_matches_report_style_labels():
    snapshot = FundamentalsSnapshot(
        ticker="AAPL",
        as_of="2026-05-16",
        market_cap=3_000_000_000_000,
        pe_ratio_trailing=28.5,
        price_to_book=None,
        dividend_yield=0.006,
        profit_margin=0.252,
        availability=[
            DataAvailability(
                field="price_to_book",
                status=AvailabilityStatus.MISSING,
                message="Provider did not return price_to_book",
                provider="fake_fundamentals",
            )
        ],
    )

    markdown = format_fundamentals_snapshot_markdown(snapshot)

    assert markdown.startswith("# Company Fundamentals for AAPL\n")
    assert "# As of: 2026-05-16" in markdown
    assert "Market Cap: $3,000,000,000,000" in markdown
    assert "PE Ratio (TTM): 28.5" in markdown
    assert "Dividend Yield: 0.6%" in markdown
    assert "Profit Margin: 25.2%" in markdown
    assert "## Data Availability" in markdown
    assert "- price_to_book: missing - Provider did not return price_to_book (provider: fake_fundamentals)" in markdown
    assert "None" not in markdown
```

- [ ] **Step 2: Add price-history Markdown/CSV test**

Append to `tests/test_structured_markdown_formatting.py`:

```python
@pytest.mark.unit
def test_format_price_history_markdown_renders_report_heading_metrics_and_csv():
    history = PriceHistory(
        ticker="AAPL",
        start="2026-05-15",
        end="2026-05-16",
        data=pd.DataFrame(
            {
                "Date": ["2026-05-15", "2026-05-16"],
                "Open": [100.0, 105.0],
                "High": [106.0, 110.0],
                "Low": [99.0, 104.0],
                "Close": [105.0, 108.0],
                "Volume": [1_000_000, 1_100_000],
            }
        ),
        high_52w=110.0,
        low_52w=99.0,
        proximity_to_52w_high=-0.0181818,
    )

    markdown = format_price_history_markdown(history)

    assert markdown.startswith("# Stock data for AAPL from 2026-05-15 to 2026-05-16\n")
    assert "# Total records: 2" in markdown
    assert "52 Week High: 110" in markdown
    assert "52 Week Low: 99" in markdown
    assert "Proximity to 52 Week High: -1.8%" in markdown
    assert "Date,Open,High,Low,Close,Volume" in markdown
    assert "2026-05-15,100.0,106.0,99.0,105.0,1000000" in markdown
    assert "2026-05-16,105.0,110.0,104.0,108.0,1100000" in markdown
```

- [ ] **Step 3: Add indicator formatter test**

Append to `tests/test_structured_markdown_formatting.py`:

```python
@pytest.mark.unit
def test_format_indicator_series_markdown_renders_date_value_lines_and_latest_value():
    series = IndicatorSeries(
        ticker="AAPL",
        indicator="rsi",
        as_of="2026-05-16",
        window=14,
        values=pd.DataFrame(
            {
                "Date": ["2026-05-15", "2026-05-16"],
                "RSI": [62.3, 64.0],
            }
        ),
        latest_value=64.0,
    )

    markdown = format_indicator_series_markdown(series)

    assert markdown.startswith("## RSI values from 2026-05-15 to 2026-05-16:\n")
    assert "2026-05-15: 62.3" in markdown
    assert "2026-05-16: 64.0" in markdown
    assert "Latest RSI: 64.0" in markdown
```

- [ ] **Step 4: Add generic dispatch and unsupported-type test**

Append to `tests/test_structured_markdown_formatting.py`:

```python
@pytest.mark.unit
def test_format_structured_data_markdown_dispatches_supported_types():
    snapshot = FundamentalsSnapshot(ticker="MSFT", as_of="2026-05-16", pe_ratio_trailing=30.0)
    history = PriceHistory(
        ticker="MSFT",
        start="2026-05-15",
        end="2026-05-16",
        data=pd.DataFrame({"Date": ["2026-05-16"], "Close": [420.0]}),
    )
    series = IndicatorSeries(
        ticker="MSFT",
        indicator="rsi",
        as_of="2026-05-16",
        window=14,
        values=pd.DataFrame({"Date": ["2026-05-16"], "RSI": [55.0]}),
        latest_value=55.0,
    )

    assert format_structured_data_markdown(snapshot) == format_fundamentals_snapshot_markdown(snapshot)
    assert format_structured_data_markdown(history) == format_price_history_markdown(history)
    assert format_structured_data_markdown(series) == format_indicator_series_markdown(series)

    with pytest.raises(TypeError, match="Unsupported structured data type for Markdown formatting"):
        format_structured_data_markdown({"ticker": "MSFT"})
```

- [ ] **Step 5: Run the focused tests to confirm RED**

Run:

```bash
uv run pytest tests/test_structured_markdown_formatting.py -q
```

Expected RED behavior before implementation: import failure for `tradingagents.dataflows.structured_markdown`.

## Task 2: Create The Structured Markdown Formatter Module

**Files:**
- Create: `tradingagents/dataflows/structured_markdown.py`

- [ ] **Step 1: Add imports, public type alias, and scalar formatting helpers**

Create `tradingagents/dataflows/structured_markdown.py`:

```python
"""Markdown renderers for structured equity data contracts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

import pandas as pd

from .structured import DataAvailability, FundamentalsSnapshot, IndicatorSeries, PriceHistory


StructuredMarkdownInput: TypeAlias = FundamentalsSnapshot | PriceHistory | IndicatorSeries


def _format_number(value: float) -> str:
    return f"{value:g}"


def _format_money(value: float) -> str:
    return f"${value:,.0f}"


def _format_percent(value: float) -> str:
    return f"{value:.1%}"


def _format_optional_metric(value: float | None, kind: str = "number") -> str | None:
    if value is None:
        return None
    if kind == "money":
        return _format_money(value)
    if kind == "percent":
        return _format_percent(value)
    return _format_number(value)
```

- [ ] **Step 2: Add availability renderer**

Append to `tradingagents/dataflows/structured_markdown.py`:

```python
def format_data_availability_markdown(availability: Sequence[DataAvailability]) -> str:
    """Render structured availability records as a Markdown section."""
    if not availability:
        return ""

    lines = ["## Data Availability"]
    for item in availability:
        provider_suffix = f" (provider: {item.provider})" if item.provider else ""
        lines.append(f"- {item.field}: {item.status.value} - {item.message}{provider_suffix}")

    return "\n".join(lines)
```

- [ ] **Step 3: Add fundamentals renderer**

Append to `tradingagents/dataflows/structured_markdown.py`:

```python
_FUNDAMENTAL_FIELDS = (
    ("Market Cap", "market_cap", "money"),
    ("PE Ratio (TTM)", "pe_ratio_trailing", "number"),
    ("Forward PE", "pe_ratio_forward", "number"),
    ("Price to Book", "price_to_book", "number"),
    ("Price to Sales", "price_to_sales", "number"),
    ("Enterprise Value", "enterprise_value", "money"),
    ("Revenue (TTM)", "revenue_ttm", "money"),
    ("Net Income (TTM)", "net_income_ttm", "money"),
    ("Free Cash Flow", "free_cash_flow", "money"),
    ("Profit Margin", "profit_margin", "percent"),
    ("Return on Equity", "roe", "percent"),
    ("Total Debt", "total_debt", "money"),
    ("Total Equity", "total_equity", "money"),
    ("Debt to Equity", "debt_to_equity", "number"),
    ("Current Ratio", "current_ratio", "number"),
    ("Dividend Yield", "dividend_yield", "percent"),
    ("Payout Ratio", "payout_ratio", "percent"),
    ("Revenue Growth YoY", "revenue_growth_yoy", "percent"),
    ("Earnings Growth YoY", "earnings_growth_yoy", "percent"),
    ("Free Cash Flow Yield", "free_cash_flow_yield", "percent"),
)


def format_fundamentals_snapshot_markdown(snapshot: FundamentalsSnapshot) -> str:
    """Render a fundamentals snapshot into report-style Markdown."""
    lines = [
        f"# Company Fundamentals for {snapshot.ticker.upper()}",
        f"# As of: {snapshot.as_of}",
        "",
    ]

    for label, attr, kind in _FUNDAMENTAL_FIELDS:
        rendered = _format_optional_metric(getattr(snapshot, attr), kind)
        if rendered is not None:
            lines.append(f"{label}: {rendered}")

    availability = format_data_availability_markdown(snapshot.availability)
    if availability:
        lines.extend(["", availability])

    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Add price-history renderer**

Append to `tradingagents/dataflows/structured_markdown.py`:

```python
def _dataframe_to_csv(frame: pd.DataFrame) -> str:
    return frame.to_csv(index=False).strip()


def format_price_history_markdown(history: PriceHistory) -> str:
    """Render structured OHLCV price history into report-style Markdown."""
    lines = [
        f"# Stock data for {history.ticker.upper()} from {history.start} to {history.end}",
        f"# Total records: {len(history.data)}",
    ]

    if history.high_52w is not None:
        lines.append(f"52 Week High: {_format_number(history.high_52w)}")
    if history.low_52w is not None:
        lines.append(f"52 Week Low: {_format_number(history.low_52w)}")
    if history.proximity_to_52w_high is not None:
        lines.append(f"Proximity to 52 Week High: {_format_percent(history.proximity_to_52w_high)}")

    lines.extend(["", _dataframe_to_csv(history.data)])

    availability = format_data_availability_markdown(history.availability)
    if availability:
        lines.extend(["", availability])

    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 5: Add indicator renderer and generic dispatcher**

Append to `tradingagents/dataflows/structured_markdown.py`:

```python
def _indicator_value_column(values: pd.DataFrame, indicator: str) -> str | None:
    for candidate in (indicator, indicator.upper()):
        if candidate in values.columns:
            return candidate

    for column in values.columns:
        if column != "Date":
            return column

    return None


def format_indicator_series_markdown(series: IndicatorSeries) -> str:
    """Render a structured indicator series into report-style Markdown."""
    value_column = _indicator_value_column(series.values, series.indicator)
    start = str(series.values["Date"].iloc[0]) if "Date" in series.values.columns and not series.values.empty else series.as_of
    heading = f"## {series.indicator.upper()} values from {start} to {series.as_of}:"
    lines = [heading, ""]

    if value_column is None or "Date" not in series.values.columns:
        lines.append("No indicator values available.")
    else:
        for _, row in series.values.iterrows():
            lines.append(f"{row['Date']}: {row[value_column]}")

    if series.latest_value is not None:
        lines.extend(["", f"Latest {series.indicator.upper()}: {_format_number(series.latest_value)}"])

    availability = format_data_availability_markdown(series.availability)
    if availability:
        lines.extend(["", availability])

    return "\n".join(lines).rstrip() + "\n"


def format_structured_data_markdown(result: StructuredMarkdownInput) -> str:
    """Dispatch a supported structured data object to its Markdown renderer."""
    if isinstance(result, FundamentalsSnapshot):
        return format_fundamentals_snapshot_markdown(result)
    if isinstance(result, PriceHistory):
        return format_price_history_markdown(result)
    if isinstance(result, IndicatorSeries):
        return format_indicator_series_markdown(result)

    raise TypeError("Unsupported structured data type for Markdown formatting")
```

- [ ] **Step 6: Add explicit exports**

Append to `tradingagents/dataflows/structured_markdown.py`:

```python
__all__ = [
    "StructuredMarkdownInput",
    "format_data_availability_markdown",
    "format_fundamentals_snapshot_markdown",
    "format_indicator_series_markdown",
    "format_price_history_markdown",
    "format_structured_data_markdown",
]
```

## Task 3: Verify Formatter Behavior And Preserve The Boundary

**Files:**
- Test: `tests/test_structured_markdown_formatting.py`
- Test: adjacent structured tests
- Inspect: router/provider/config/agent-facing files

- [ ] **Step 1: Run focused RED/GREEN suite**

Run:

```bash
uv run pytest tests/test_structured_markdown_formatting.py -q
```

Expected GREEN behavior after implementation:
- `test_format_fundamentals_snapshot_markdown_matches_report_style_labels` passes.
- `test_format_price_history_markdown_renders_report_heading_metrics_and_csv` passes.
- `test_format_indicator_series_markdown_renders_date_value_lines_and_latest_value` passes.
- `test_format_structured_data_markdown_dispatches_supported_types` passes.

- [ ] **Step 2: Run adjacent structured data tests**

Run:

```bash
uv run pytest tests/test_structured_markdown_formatting.py tests/test_structured_as_of_contract.py tests/test_structured_data_entry_points.py tests/test_structured_equity_schemas.py -q
```

Expected result: all tests pass.

- [ ] **Step 3: Prove no provider, router fallback, config, credential, CLI, screener, portfolio, or graph behavior changed**

Run:

```bash
git diff --exit-code -- tradingagents/dataflows/interface.py tradingagents/default_config.py .env.example cli tradingagents/graph tradingagents/screener
```

Expected result: no diff.

Run:

```bash
git diff --name-only -- tradingagents/dataflows
```

Expected output for this slice only:

```text
tradingagents/dataflows/structured_markdown.py
```

- [ ] **Step 4: Check formatting and patch hygiene**

Run:

```bash
git diff --check
```

Expected result: no whitespace errors.

## Docs Drift Checkpoint

No durable docs update is expected if implementation stays inside this plan. The roadmap already calls out Slice 2B-S4 as the structured-to-Markdown formatting boundary, and `docs/project-architecture-guidelines.md` already says structured output should use render helpers that preserve Markdown consumed by CLI, memory, reports, and tests.

Docs drift checkpoint language for the implementation PR:

```text
Docs drift checkpoint: no durable docs update needed; this slice adds the already-planned 2B-S4 structured-to-Markdown formatter boundary without provider adapter implementation, provider registration, agent-facing router changes, VENDOR_METHODS changes, config keys, credentials, prompt rewrites, CLI changes, screener behavior, portfolio behavior, or graph behavior changes.
```

Update `docs/project-architecture-guidelines.md` only if implementation changes formatter ownership, changes the public Markdown/report shape consumed by current agent tools, or wires structured formatters into the router earlier than this plan allows.

## Implementation Commit Instructions

- [ ] **Step 1: Review local status and preserve unrelated files**

Run:

```bash
git status --short
```

Expected before staging: only this slice's intended code/test files plus any pre-existing unrelated files such as `.DS_Store`.

- [ ] **Step 2: Selectively stage only this slice**

Run:

```bash
git add tests/test_structured_markdown_formatting.py tradingagents/dataflows/structured_markdown.py
```

- [ ] **Step 3: Confirm staged scope**

Run:

```bash
git diff --cached --name-only
```

Expected output:

```text
tests/test_structured_markdown_formatting.py
tradingagents/dataflows/structured_markdown.py
```

- [ ] **Step 4: Commit**

Run:

```bash
git commit -m "feat(data): add structured markdown formatters"
```

## Exit Criteria

- Structured fundamentals snapshots render deterministic report-style Markdown with explicit availability records.
- Structured price history renders deterministic stock-data report strings and CSV rows from typed data.
- Structured indicator series renders deterministic indicator report strings and latest values.
- A generic formatter dispatches only supported structured equity dataclasses.
- No provider adapter, provider registration, router fallback, config, credential, CLI, screener, portfolio, graph, prompt, or existing agent-facing tool behavior changes are introduced.
