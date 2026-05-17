---
initiative: trading-platform
phase: 2
slice: 2B-S3
status: planned
worktree: main
depends_on:
  - docs/plans/2026-05-16-structured-equity-schemas.md
  - docs/plans/2026-05-16-structured-data-entry-points.md
  - docs/plans/2026-05-15-no-data-provider-error-semantics.md
  - docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md
  - docs/superpowers/specs/2026-05-04-platform-roadmap-design.md
  - docs/project-architecture-guidelines.md
---

# No-Look-Ahead As-Of Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce date validation and no-look-ahead behavior for structured equity entry points before any real provider adapter depends on them.

**Architecture:** Keep the structured dispatcher from 2B-S2, but wrap public structured entry points with narrow date-contract helpers in `tradingagents/dataflows/structured.py`. Dates fail fast before provider calls, provider results are filtered or rejected after dispatch, and this slice still uses fake providers only. No agent-facing router, provider adapter, config, credential, CLI, screener, portfolio, or graph behavior changes.

**Tech Stack:** Python 3.10+, standard-library `datetime`/`re`, existing dataclasses in `tradingagents.dataflows.structured`, existing `ProviderNoDataError`, pytest, pandas already present in the repo, no new dependencies.

---

## Brainstormed Approach

Considered options:

1. Contract tests only against fake providers.
   - Pros: smallest slice and no production behavior change.
   - Cons: does not prevent a future adapter from leaking rows after `as_of`; invalid date calls would still reach providers.

2. Provider-owned filtering only.
   - Pros: each adapter can use provider-specific timestamp fields and query semantics.
   - Cons: duplicates date validation and no-look-ahead rules across every provider, and gives structured callers no central guardrail.

3. Narrow structured entry-point helpers plus provider-owned query discipline.
   - Pros: validates caller dates once, filters typed results defensively, keeps provider adapters responsible for efficient historical queries, and stays inside `structured.py`.
   - Cons: adds small post-processing helpers that must avoid becoming a full adapter layer.

Recommendation: option 3. The slice should introduce narrow validation/filtering helpers, not just tests, because the roadmap explicitly requires invalid dates to fail before provider calls and structured data to ignore observations after `as_of`.

## Contract Decisions

- `YYYY-MM-DD` is the only accepted date format for structured equity dates. Empty strings, `None`, datetimes, slash dates, impossible dates, and start dates after end dates raise `ValueError` before any provider function runs.
- `get_price_history(ticker, start, end)` keeps its current signature. `start` and `end` are explicit and required; `end` is the as-of boundary. There is no implicit default to today's date. Returned `PriceHistory.data` is filtered to rows with `Date` between `start` and `end`, inclusive.
- `get_fundamentals_snapshot(ticker, as_of)` keeps its current signature. `as_of` is explicit and required. If a provider returns a `FundamentalsSnapshot.as_of` after the requested `as_of`, the structured layer raises `ProviderNoDataError` because no usable point-in-time snapshot remains.
- `get_indicator_series(ticker, indicator, as_of, window)` keeps its current signature. `as_of` is explicit and required, and `window` must be a positive integer before dispatch. Returned `IndicatorSeries.values` is filtered to rows with `Date <= as_of`, and `latest_value` is recomputed from the filtered rows when a numeric indicator column is available.
- Price and indicator dataframes must contain a `Date` column for this contract. Missing or fully filtered required top-level data raises `ProviderNoDataError`.
- Providers remain responsible for asking upstream APIs for the right historical range. These helpers are defensive contract enforcement, not provider adapters.

## Scope

- Add as-of contract tests with fake providers.
- Extend `tradingagents/dataflows/structured.py` with strict date parsing, range validation, dataframe filtering, and typed-result post-processing.
- Preserve current public entry point names and argument order:
  - `get_price_history(ticker, start, end) -> PriceHistory`
  - `get_fundamentals_snapshot(ticker, as_of) -> FundamentalsSnapshot`
  - `get_indicator_series(ticker, indicator, as_of, window) -> IndicatorSeries`
- Use `ProviderNoDataError` for successful provider responses that become unusable after date filtering.

## Non-Goals

- No screener implementation.
- No Massive/Polygon, yfinance, Alpha Vantage, or IBKR structured adapter implementation.
- No provider registration.
- No `route_to_vendor()` changes.
- No `VENDOR_METHODS` changes.
- No new config keys, credentials, `.env.example` edits, or CLI behavior.
- No portfolio, graph, prompt, batch, or report behavior changes.
- No broad parser layer for provider-specific response formats.

## File Structure

- Create: `tests/test_structured_as_of_contract.py`
- Modify: `tradingagents/dataflows/structured.py`
- No change expected: `tradingagents/dataflows/interface.py`
- No change expected: provider adapter modules under `tradingagents/dataflows/`
- No change expected: `tradingagents/default_config.py`
- No change expected: `.env.example`
- No change expected: `cli/`
- No change expected: `tradingagents/graph/`
- No change expected: `tradingagents/screener/`
- No change expected: portfolio modules

## Task 1: Lock No-Look-Ahead Behavior With Failing Tests

**Files:**
- Create: `tests/test_structured_as_of_contract.py`

- [ ] **Step 1: Add test scaffolding and price-history filtering test**

Create `tests/test_structured_as_of_contract.py`:

```python
import copy

import pandas as pd
import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from tradingagents.dataflows import structured
from tradingagents.dataflows.exceptions import ProviderNoDataError
from tradingagents.dataflows.structured import FundamentalsSnapshot, IndicatorSeries, PriceHistory


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


def register_structured_provider(monkeypatch, method: str, vendor: str, provider):
    monkeypatch.setitem(structured.STRUCTURED_VENDOR_METHODS[method], vendor, provider)
    category = structured.STRUCTURED_METHOD_CATEGORIES[method]
    config_module.set_config({"data_vendors": {category: vendor}})


@pytest.mark.unit
def test_price_history_treats_end_as_as_of_and_filters_future_rows(monkeypatch):
    calls = []

    def fake_price_history(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append((ticker, start, end))
        return PriceHistory(
            ticker=ticker,
            start=start,
            end=end,
            data=pd.DataFrame(
                {
                    "Date": ["2026-05-15", "2026-05-16", "2026-05-17"],
                    "Open": [100.0, 105.0, 200.0],
                    "High": [106.0, 110.0, 250.0],
                    "Low": [99.0, 104.0, 190.0],
                    "Close": [105.0, 108.0, 240.0],
                    "Volume": [1_000_000, 1_100_000, 9_999_999],
                }
            ),
            high_52w=250.0,
            low_52w=99.0,
            proximity_to_52w_high=-0.04,
        )

    register_structured_provider(monkeypatch, "get_price_history", "fake_prices", fake_price_history)

    result = structured.get_price_history("AAPL", "2026-05-15", "2026-05-16")

    assert calls == [("AAPL", "2026-05-15", "2026-05-16")]
    assert result.start == "2026-05-15"
    assert result.end == "2026-05-16"
    assert result.data["Date"].tolist() == ["2026-05-15", "2026-05-16"]
    assert result.high_52w == 110.0
    assert result.low_52w == 99.0
    assert result.proximity_to_52w_high == pytest.approx((108.0 / 110.0) - 1)
```

- [ ] **Step 2: Add fundamentals snapshot no-future test**

Append to `tests/test_structured_as_of_contract.py`:

```python
@pytest.mark.unit
def test_fundamentals_snapshot_rejects_provider_snapshot_after_as_of(monkeypatch):
    def fake_fundamentals(ticker: str, as_of: str) -> FundamentalsSnapshot:
        return FundamentalsSnapshot(
            ticker=ticker,
            as_of="2026-05-17",
            market_cap=3_000_000_000_000,
            pe_ratio_trailing=28.5,
        )

    register_structured_provider(
        monkeypatch,
        "get_fundamentals_snapshot",
        "fake_fundamentals",
        fake_fundamentals,
    )

    with pytest.raises(ProviderNoDataError) as exc_info:
        structured.get_fundamentals_snapshot("AAPL", "2026-05-16")

    assert exc_info.value.method == "get_fundamentals_snapshot"
    assert exc_info.value.details == {
        "ticker": "AAPL",
        "as_of": "2026-05-16",
        "snapshot_as_of": "2026-05-17",
    }
```

- [ ] **Step 3: Add indicator as-of filtering and latest-value recomputation test**

Append to `tests/test_structured_as_of_contract.py`:

```python
@pytest.mark.unit
def test_indicator_series_filters_after_as_of_and_recomputes_latest_value(monkeypatch):
    def fake_indicator(ticker: str, indicator: str, as_of: str, window: int) -> IndicatorSeries:
        return IndicatorSeries(
            ticker=ticker,
            indicator=indicator,
            as_of=as_of,
            window=window,
            values=pd.DataFrame(
                {
                    "Date": ["2026-05-15", "2026-05-16", "2026-05-17"],
                    "RSI": [62.3, 64.0, 99.0],
                }
            ),
            latest_value=99.0,
        )

    register_structured_provider(monkeypatch, "get_indicator_series", "fake_indicators", fake_indicator)

    result = structured.get_indicator_series("AAPL", "rsi", "2026-05-16", 14)

    assert result.values["Date"].tolist() == ["2026-05-15", "2026-05-16"]
    assert result.latest_value == 64.0
```

- [ ] **Step 4: Add invalid-date and invalid-window pre-dispatch tests**

Append to `tests/test_structured_as_of_contract.py`:

```python
@pytest.mark.unit
def test_invalid_price_history_dates_fail_before_provider_call(monkeypatch):
    calls = []

    def should_not_run(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append((ticker, start, end))
        return PriceHistory(ticker=ticker, start=start, end=end, data=pd.DataFrame())

    register_structured_provider(monkeypatch, "get_price_history", "fake_prices", should_not_run)

    with pytest.raises(ValueError, match="start must be a YYYY-MM-DD date"):
        structured.get_price_history("AAPL", "2026/05/15", "2026-05-16")

    with pytest.raises(ValueError, match="start must be on or before end"):
        structured.get_price_history("AAPL", "2026-05-17", "2026-05-16")

    assert calls == []


@pytest.mark.unit
def test_invalid_as_of_dates_fail_before_provider_call(monkeypatch):
    calls = []

    def should_not_run_fundamentals(ticker: str, as_of: str) -> FundamentalsSnapshot:
        calls.append(("fundamentals", ticker, as_of))
        return FundamentalsSnapshot(ticker=ticker, as_of=as_of)

    def should_not_run_indicator(
        ticker: str,
        indicator: str,
        as_of: str,
        window: int,
    ) -> IndicatorSeries:
        calls.append(("indicator", ticker, indicator, as_of, window))
        return IndicatorSeries(
            ticker=ticker,
            indicator=indicator,
            as_of=as_of,
            window=window,
            values=pd.DataFrame(),
        )

    register_structured_provider(
        monkeypatch,
        "get_fundamentals_snapshot",
        "fake_fundamentals",
        should_not_run_fundamentals,
    )
    register_structured_provider(monkeypatch, "get_indicator_series", "fake_indicators", should_not_run_indicator)

    with pytest.raises(ValueError, match="as_of must be a YYYY-MM-DD date"):
        structured.get_fundamentals_snapshot("AAPL", "2026-05-16T00:00:00")

    with pytest.raises(ValueError, match="as_of must be a YYYY-MM-DD date"):
        structured.get_indicator_series("AAPL", "rsi", "", 14)

    with pytest.raises(ValueError, match="window must be a positive integer"):
        structured.get_indicator_series("AAPL", "rsi", "2026-05-16", 0)

    assert calls == []
```

- [ ] **Step 5: Run the focused tests to confirm RED**

Run:

```bash
uv run pytest tests/test_structured_as_of_contract.py -q
```

Expected RED behavior before implementation:
- Price history returns the future `2026-05-17` row and does not recompute derived fields.
- Future fundamentals snapshot returns instead of raising `ProviderNoDataError`.
- Indicator `latest_value` remains `99.0`.
- Invalid dates reach fake providers instead of raising `ValueError` first.

## Task 2: Add Date Parsing And Dataframe Filtering Helpers

**Files:**
- Modify: `tradingagents/dataflows/structured.py`

- [ ] **Step 1: Add imports and strict ISO date parser**

In `tradingagents/dataflows/structured.py`, add these imports near the top:

```python
from datetime import date
import re
```

Add these helpers before `_get_structured_vendor_config()`:

```python
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_iso_date(value: str, field_name: str) -> date:
    if not isinstance(value, str) or not _ISO_DATE_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a YYYY-MM-DD date")

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid YYYY-MM-DD date") from exc


def _normalize_iso_date(value: str, field_name: str) -> str:
    return _parse_iso_date(value, field_name).isoformat()
```

- [ ] **Step 2: Add required dataframe date filter**

Append this helper after `_normalize_iso_date()`:

```python
def _filter_required_frame_by_date(
    frame: pd.DataFrame,
    *,
    ticker: str,
    method: str,
    provider: str | None,
    start: date | None = None,
    end: date,
) -> pd.DataFrame:
    if "Date" not in frame.columns:
        raise ProviderNoDataError(
            f"No usable dated rows returned for {ticker}",
            provider=provider,
            method=method,
            details={"ticker": ticker, "reason": "missing_date_column"},
        )

    working = frame.copy()
    parsed_dates = pd.to_datetime(working["Date"], errors="coerce")
    mask = parsed_dates.notna() & (parsed_dates.dt.date <= end)
    if start is not None:
        mask &= parsed_dates.dt.date >= start

    filtered = working.loc[mask].copy()
    if filtered.empty:
        details = {"ticker": ticker, "end": end.isoformat()}
        if start is not None:
            details["start"] = start.isoformat()
        raise ProviderNoDataError(
            f"No usable dated rows returned for {ticker} within the requested as-of window",
            provider=provider,
            method=method,
            details=details,
        )

    filtered["Date"] = parsed_dates.loc[filtered.index].dt.strftime("%Y-%m-%d")
    return filtered.reset_index(drop=True)
```

- [ ] **Step 3: Add typed result post-processors**

Append these helpers after `_filter_required_frame_by_date()`:

```python
def _enforce_price_history_contract(history: PriceHistory, start: date, end: date) -> PriceHistory:
    filtered = _filter_required_frame_by_date(
        history.data,
        ticker=history.ticker,
        method="get_price_history",
        provider=None,
        start=start,
        end=end,
    )

    high_52w = float(filtered["High"].max()) if "High" in filtered.columns else None
    low_52w = float(filtered["Low"].min()) if "Low" in filtered.columns else None
    latest_close = float(filtered["Close"].iloc[-1]) if "Close" in filtered.columns else None
    proximity = None
    if high_52w not in (None, 0.0) and latest_close is not None:
        proximity = (latest_close / high_52w) - 1

    return PriceHistory(
        ticker=history.ticker,
        start=start.isoformat(),
        end=end.isoformat(),
        data=filtered,
        high_52w=high_52w,
        low_52w=low_52w,
        proximity_to_52w_high=proximity,
        availability=history.availability,
    )


def _enforce_fundamentals_contract(
    snapshot: FundamentalsSnapshot,
    requested_as_of: date,
) -> FundamentalsSnapshot:
    snapshot_as_of = _parse_iso_date(snapshot.as_of, "snapshot.as_of")
    if snapshot_as_of > requested_as_of:
        raise ProviderNoDataError(
            f"No usable fundamentals snapshot for {snapshot.ticker} on or before {requested_as_of.isoformat()}",
            provider=None,
            method="get_fundamentals_snapshot",
            details={
                "ticker": snapshot.ticker,
                "as_of": requested_as_of.isoformat(),
                "snapshot_as_of": snapshot.as_of,
            },
        )
    return snapshot


def _latest_numeric_indicator_value(values: pd.DataFrame, indicator: str) -> float | None:
    candidate_columns = [indicator, indicator.upper()]
    candidate_columns.extend(col for col in values.columns if col not in {"Date", indicator, indicator.upper()})

    for column in candidate_columns:
        if column not in values.columns:
            continue
        numeric_values = pd.to_numeric(values[column], errors="coerce").dropna()
        if not numeric_values.empty:
            return float(numeric_values.iloc[-1])

    return None


def _enforce_indicator_series_contract(series: IndicatorSeries, requested_as_of: date) -> IndicatorSeries:
    filtered = _filter_required_frame_by_date(
        series.values,
        ticker=series.ticker,
        method="get_indicator_series",
        provider=None,
        end=requested_as_of,
    )

    return IndicatorSeries(
        ticker=series.ticker,
        indicator=series.indicator,
        as_of=requested_as_of.isoformat(),
        window=series.window,
        values=filtered,
        latest_value=_latest_numeric_indicator_value(filtered, series.indicator),
        availability=series.availability,
    )
```

- [ ] **Step 4: Add `ProviderNoDataError` import**

Update the existing exception import in `tradingagents/dataflows/structured.py`:

```python
from .exceptions import DataProviderError, ProviderNoDataError
```

## Task 3: Wire The Helpers Into Public Structured Entry Points

**Files:**
- Modify: `tradingagents/dataflows/structured.py`

- [ ] **Step 1: Validate and enforce `get_price_history()`**

Replace `get_price_history()` with:

```python
def get_price_history(ticker: str, start: str, end: str) -> PriceHistory:
    """Return structured OHLCV history from the configured structured provider."""
    start_date = _parse_iso_date(start, "start")
    end_date = _parse_iso_date(end, "end")
    if start_date > end_date:
        raise ValueError("start must be on or before end")

    history = route_structured_method("get_price_history", ticker, start_date.isoformat(), end_date.isoformat())
    return _enforce_price_history_contract(history, start_date, end_date)
```

- [ ] **Step 2: Validate and enforce `get_fundamentals_snapshot()`**

Replace `get_fundamentals_snapshot()` with:

```python
def get_fundamentals_snapshot(ticker: str, as_of: str) -> FundamentalsSnapshot:
    """Return structured fundamentals from the configured structured provider."""
    as_of_date = _parse_iso_date(as_of, "as_of")
    snapshot = route_structured_method("get_fundamentals_snapshot", ticker, as_of_date.isoformat())
    return _enforce_fundamentals_contract(snapshot, as_of_date)
```

- [ ] **Step 3: Validate and enforce `get_indicator_series()`**

Replace `get_indicator_series()` with:

```python
def get_indicator_series(
    ticker: str,
    indicator: str,
    as_of: str,
    window: int,
) -> IndicatorSeries:
    """Return structured technical indicators from the configured structured provider."""
    as_of_date = _parse_iso_date(as_of, "as_of")
    if not isinstance(window, int) or window <= 0:
        raise ValueError("window must be a positive integer")

    series = route_structured_method(
        "get_indicator_series",
        ticker,
        indicator,
        as_of_date.isoformat(),
        window,
    )
    return _enforce_indicator_series_contract(series, as_of_date)
```

- [ ] **Step 4: Keep helper functions private**

Do not add `_parse_iso_date`, `_filter_required_frame_by_date`, or `_enforce_*` helpers to `__all__`. They are implementation details for the public structured entry points.

## Task 4: Verify The Contract And Scope Guards

**Files:**
- Test: `tests/test_structured_as_of_contract.py`
- Test: existing structured/data-layer test files
- Inspect: scope-guarded files

- [ ] **Step 1: Run focused RED/GREEN suite**

Run:

```bash
uv run pytest tests/test_structured_as_of_contract.py -q
```

Expected GREEN behavior after implementation: all as-of contract tests pass.

- [ ] **Step 2: Run adjacent structured data tests**

Run:

```bash
uv run pytest tests/test_structured_as_of_contract.py tests/test_structured_data_entry_points.py tests/test_structured_equity_schemas.py tests/test_data_provider_availability.py -q
```

Expected result: all tests pass.

- [ ] **Step 3: Prove router, provider, config, credential, CLI, screener, portfolio, and graph behavior stayed out of scope**

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
tradingagents/dataflows/structured.py
```

- [ ] **Step 4: Check formatting and patch hygiene**

Run:

```bash
git diff --check
```

Expected result: no whitespace errors.

## Docs Drift Checkpoint

No durable docs update is expected if implementation stays inside this plan. The roadmap already calls out Slice 2B-S3 no-look-ahead/as-of contract tests, and `docs/project-architecture-guidelines.md` already requires screening and quantitative data consumers to require or default `as_of` and prevent look-ahead bias.

Docs drift checkpoint language for the implementation PR:

```text
Docs drift checkpoint: no durable docs update needed; this slice implements the already-planned 2B-S3 structured as-of/no-look-ahead contract without provider adapter implementation, agent-facing router changes, VENDOR_METHODS changes, config keys, credentials, CLI changes, screener behavior, portfolio behavior, graph behavior, or report behavior changes.
```

Update `docs/project-architecture-guidelines.md` only if implementation changes the public date-default rule, changes structured module ownership, or creates a new reusable adapter contract beyond the helper boundary described here.

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
git add tests/test_structured_as_of_contract.py tradingagents/dataflows/structured.py
```

- [ ] **Step 3: Confirm staged scope**

Run:

```bash
git diff --cached --name-only
```

Expected output:

```text
tests/test_structured_as_of_contract.py
tradingagents/dataflows/structured.py
```

- [ ] **Step 4: Commit**

Run:

```bash
git commit -m "feat(data): enforce structured as-of contracts"
```

## Exit Criteria

- `get_price_history()` rejects invalid ranges before provider dispatch and treats `end` as its as-of boundary.
- `get_fundamentals_snapshot()` rejects provider snapshots after the requested `as_of`.
- `get_indicator_series()` rejects invalid `as_of` and non-positive windows before provider dispatch, filters future rows, and recomputes `latest_value`.
- Fully filtered required top-level data raises `ProviderNoDataError`.
- Existing structured entry-point and schema tests still pass.
- No provider adapter, router fallback, config, credential, CLI, screener, portfolio, graph, or report behavior is introduced.
