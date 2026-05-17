# Phase 2C-S4 Dividends Splits And Corporate Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured Massive dividends and splits output for future screeners and portfolio metrics without changing price-history semantics.

**Architecture:** Add focused corporate-action dataclasses and a provider-neutral `get_corporate_actions()` structured entry point. Implement Massive dividends and splits parsing in `tradingagents/dataflows/massive.py`, register only the structured corporate-action method, and document that adjusted price history remains a separate explicit concern.

**Tech Stack:** Python 3.10+, dataclasses, existing structured data registry, existing Massive fake-session test pattern, existing provider exceptions, pytest.

---

## Prerequisite State

Start from `main` after Slices `2C-S1`, `2C-S2`, and `2C-S3` are merged. Stop if the Massive module and structured registry patterns from those slices are absent.

## Context To Read First

- `docs/project-architecture-guidelines.md`
- `docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md`
- `docs/superpowers/specs/2026-05-17-phase-2c-s4-dividends-splits-corporate-actions-design.md`
- `tradingagents/dataflows/structured.py`
- `tradingagents/dataflows/massive.py`
- `tradingagents/dataflows/availability.py`
- `tests/test_data_provider_availability.py`
- `tests/test_massive_price_history.py`

## Expected Git Diff Scope

Expected modified or created files:

- Modify: `tradingagents/dataflows/structured.py`
- Modify: `tradingagents/dataflows/massive.py`
- Modify: `tests/test_structured_equity_schemas.py`
- Create: `tests/test_massive_corporate_actions.py`
- Modify: `README.md`

No expected changes:

- `tradingagents/dataflows/interface.py`
- Fundamentals, screener, portfolio, macro, graph, prompt, CLI, or IBKR files

## Hard Non-Goals

- Do not add tax-lot, rebalance, execution, or broker logic.
- Do not compute adjusted or unadjusted price series in this slice.
- Do not add screener filters or portfolio metrics.
- Do not register Massive in `VENDOR_METHODS` or change `route_to_vendor()`.
- Do not require live credentials for default tests.
- Do not broaden into Phase 2D, screener, portfolio, macro, graph, prompts, CLI UX, or IBKR.

### Task 1: Corporate Action Schemas

**Files:**
- Modify: `tests/test_structured_equity_schemas.py`
- Modify: `tradingagents/dataflows/structured.py`

- [ ] **Step 1: Write failing schema tests**

Append to `tests/test_structured_equity_schemas.py`:

```python
from tradingagents.dataflows.structured import CorporateActions, DividendEvent, SplitEvent


@pytest.mark.unit
def test_corporate_actions_hold_dividends_splits_and_availability():
    dividend = DividendEvent(
        ticker="AAPL",
        ex_dividend_date="2026-05-10",
        pay_date="2026-05-20",
        cash_amount=0.26,
        currency="usd",
    )
    split = SplitEvent(
        ticker="AAPL",
        execution_date="2026-05-12",
        split_from=1.0,
        split_to=4.0,
    )
    availability = [
        DataAvailability(
            field="dividends",
            status=AvailabilityStatus.AVAILABLE,
            message="dividend events available",
            provider="massive",
        )
    ]

    actions = CorporateActions(
        ticker="AAPL",
        start="2026-05-01",
        end="2026-05-31",
        dividends=[dividend],
        splits=[split],
        availability=availability,
    )

    assert actions.dividends == [dividend]
    assert actions.splits == [split]
    assert actions.availability == availability
```

- [ ] **Step 2: Run the schema test to verify it fails**

Run:

```bash
uv run pytest tests/test_structured_equity_schemas.py::test_corporate_actions_hold_dividends_splits_and_availability -q
```

Expected: FAIL because the corporate-action dataclasses do not exist.

- [ ] **Step 3: Add corporate-action dataclasses and structured method**

Add to `tradingagents/dataflows/structured.py`:

```python
@dataclass
class DividendEvent:
    """Cash dividend event for a ticker."""

    ticker: str
    ex_dividend_date: str
    pay_date: str | None = None
    cash_amount: float | None = None
    currency: str | None = None


@dataclass
class SplitEvent:
    """Stock split event for a ticker."""

    ticker: str
    execution_date: str
    split_from: float
    split_to: float


@dataclass
class CorporateActions:
    """Structured corporate actions for a ticker over a date range."""

    ticker: str
    start: str
    end: str
    dividends: list[DividendEvent] = field(default_factory=list)
    splits: list[SplitEvent] = field(default_factory=list)
    availability: list[DataAvailability] = field(default_factory=list)
```

Add method category, registry slot, entry point, and exports:

```python
STRUCTURED_METHOD_CATEGORIES["get_corporate_actions"] = "core_stock_apis"
STRUCTURED_VENDOR_METHODS["get_corporate_actions"] = {}


def get_corporate_actions(ticker: str, start: str, end: str) -> CorporateActions:
    start_date = _parse_iso_date(start, "start")
    end_date = _parse_iso_date(end, "end")
    if start_date > end_date:
        raise ValueError("start must be on or before end")
    return route_structured_method("get_corporate_actions", ticker, start_date.isoformat(), end_date.isoformat())
```

- [ ] **Step 4: Run schema tests**

Run:

```bash
uv run pytest tests/test_structured_equity_schemas.py -q
```

Expected: PASS.

### Task 2: Massive Dividends And Splits Parser

**Files:**
- Create: `tests/test_massive_corporate_actions.py`
- Modify: `tradingagents/dataflows/massive.py`

- [ ] **Step 1: Write failing parser tests**

Create `tests/test_massive_corporate_actions.py`:

```python
import copy

import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from tradingagents.dataflows import structured
from tradingagents.dataflows.massive import MASSIVE_API_KEY_ENV, get_massive_corporate_actions
from tradingagents.dataflows.structured import CorporateActions
from tests.test_massive_price_history import FakeResponse


class SequenceSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


@pytest.mark.unit
def test_get_massive_corporate_actions_parses_dividends_and_splits(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = SequenceSession(
        [
            FakeResponse({"results": [{"ticker": "AAPL", "ex_dividend_date": "2026-05-10", "pay_date": "2026-05-20", "cash_amount": 0.26, "currency": "usd"}]}),
            FakeResponse({"results": [{"ticker": "AAPL", "execution_date": "2026-05-12", "split_from": 1, "split_to": 4}]}),
        ]
    )

    result = get_massive_corporate_actions("aapl", "2026-05-01", "2026-05-31", session=session)

    assert isinstance(result, CorporateActions)
    assert result.ticker == "AAPL"
    assert result.start == "2026-05-01"
    assert result.end == "2026-05-31"
    assert result.dividends[0].cash_amount == 0.26
    assert result.dividends[0].currency == "usd"
    assert result.splits[0].split_from == 1.0
    assert result.splits[0].split_to == 4.0
    assert len(session.calls) == 2
```

- [ ] **Step 2: Add failing empty-response test**

Append:

```python
@pytest.mark.unit
def test_get_massive_corporate_actions_allows_empty_optional_collections(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = SequenceSession([FakeResponse({"results": []}), FakeResponse({"results": []})])

    result = get_massive_corporate_actions("AAPL", "2026-05-01", "2026-05-31", session=session)

    assert result.dividends == []
    assert result.splits == []
```

- [ ] **Step 3: Run parser tests to verify they fail**

Run:

```bash
uv run pytest tests/test_massive_corporate_actions.py -q
```

Expected: FAIL because `get_massive_corporate_actions` does not exist.

- [ ] **Step 4: Implement Massive corporate-action parsing**

Add to `tradingagents/dataflows/massive.py`:

```python
from .structured import CorporateActions, DividendEvent, SplitEvent


def _dividends_url() -> str:
    return f"{MASSIVE_BASE_URL}/v3/reference/dividends"


def _splits_url() -> str:
    return f"{MASSIVE_BASE_URL}/v3/reference/splits"


def _parse_dividend(row: dict) -> DividendEvent:
    return DividendEvent(
        ticker=str(row.get("ticker", "")).upper(),
        ex_dividend_date=str(row.get("ex_dividend_date")),
        pay_date=row.get("pay_date"),
        cash_amount=float(row["cash_amount"]) if row.get("cash_amount") is not None else None,
        currency=row.get("currency"),
    )


def _parse_split(row: dict) -> SplitEvent:
    return SplitEvent(
        ticker=str(row.get("ticker", "")).upper(),
        execution_date=str(row.get("execution_date")),
        split_from=float(row.get("split_from")),
        split_to=float(row.get("split_to")),
    )


def _get_optional_massive_results(client, url: str, params: dict, method: str) -> list[dict]:
    response = client.get(url, params=params, timeout=MASSIVE_TIMEOUT_SECONDS)
    _raise_for_massive_status(response, method)
    payload = response.json()
    return normalize_provider_result(
        payload.get("results", []),
        provider=MASSIVE_PROVIDER,
        method=method,
        role=ProviderResultRole.OPTIONAL,
        details={"ticker": params["ticker"], "start": params.get("date.gte"), "end": params.get("date.lte")},
    )


def get_massive_corporate_actions(
    ticker: str,
    start: str,
    end: str,
    *,
    session: requests.Session | None = None,
) -> CorporateActions:
    api_key = get_massive_api_key()
    client = session or requests.Session()
    normalized_ticker = ticker.upper()
    common_params = {"ticker": normalized_ticker, "apiKey": api_key}
    dividend_rows = _get_optional_massive_results(
        client,
        _dividends_url(),
        {**common_params, "ex_dividend_date.gte": start, "ex_dividend_date.lte": end},
        "get_corporate_actions",
    )
    split_rows = _get_optional_massive_results(
        client,
        _splits_url(),
        {**common_params, "execution_date.gte": start, "execution_date.lte": end},
        "get_corporate_actions",
    )
    return CorporateActions(
        ticker=normalized_ticker,
        start=start,
        end=end,
        dividends=[_parse_dividend(row) for row in dividend_rows],
        splits=[_parse_split(row) for row in split_rows],
    )
```

- [ ] **Step 5: Run parser tests**

Run:

```bash
uv run pytest tests/test_massive_corporate_actions.py -q
```

Expected: PASS.

### Task 3: Structured Routing

**Files:**
- Modify: `tests/test_massive_corporate_actions.py`
- Modify: `tradingagents/dataflows/structured.py`

- [ ] **Step 1: Add failing routing test**

Append to `tests/test_massive_corporate_actions.py`:

```python
@pytest.mark.unit
def test_structured_get_corporate_actions_routes_to_massive(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = SequenceSession([FakeResponse({"results": []}), FakeResponse({"results": []})])
    monkeypatch.setattr("tradingagents.dataflows.massive.requests.Session", lambda: session)
    config_module.set_config({"data_vendors": {"core_stock_apis": "massive"}})

    result = structured.get_corporate_actions("AAPL", "2026-05-01", "2026-05-31")

    assert result.ticker == "AAPL"
    assert result.dividends == []
    assert result.splits == []
```

- [ ] **Step 2: Run routing test to verify it fails**

Run:

```bash
uv run pytest tests/test_massive_corporate_actions.py::test_structured_get_corporate_actions_routes_to_massive -q
```

Expected: FAIL until Massive is registered for `get_corporate_actions`.

- [ ] **Step 3: Register the Massive corporate-action provider**

At the structured Massive registration point, add:

```python
from .massive import get_massive_corporate_actions as _get_massive_corporate_actions

STRUCTURED_VENDOR_METHODS["get_corporate_actions"]["massive"] = _get_massive_corporate_actions
```

- [ ] **Step 4: Run routing tests**

Run:

```bash
uv run pytest tests/test_massive_corporate_actions.py tests/test_structured_data_entry_points.py tests/test_structured_equity_schemas.py -q
```

Expected: PASS.

### Task 4: Document Adjusted Price Assumption

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add adjusted price note**

In the Massive provider setup section, add:

```markdown
Massive historical price history uses adjusted daily bars by default. Dividends and splits are exposed separately through structured corporate-action data so future workflows can explicitly choose adjusted or unadjusted semantics.
```

### Task 5: Verification And Commit

**Files:**
- All files from Tasks 1-4

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run pytest tests/test_massive_corporate_actions.py tests/test_structured_equity_schemas.py tests/test_data_provider_availability.py tests/test_massive_price_history.py tests/test_massive_ticker_details.py -q
```

Expected: PASS.

- [ ] **Step 2: Run diff hygiene checks**

Run:

```bash
git diff --check
git diff -- tradingagents/dataflows/interface.py
```

Expected: no whitespace errors and no diff in `tradingagents/dataflows/interface.py`.

- [ ] **Step 3: Inspect expected diff scope**

Run:

```bash
git status --short
git diff -- tradingagents/dataflows/structured.py tradingagents/dataflows/massive.py tests/test_structured_equity_schemas.py tests/test_massive_corporate_actions.py README.md
```

Expected: only planned files changed, plus any pre-existing unrelated untracked `.DS_Store` files.

- [ ] **Step 4: Docs drift checkpoint**

Use this exact checkpoint language in the PR or final response:

```text
Docs drift checkpoint: README now documents that Massive price history uses adjusted daily bars by default and that dividends/splits are exposed separately for explicit future adjusted/unadjusted workflows. Architecture docs already covered empty corporate-action collections as valid optional results, so no architecture update was needed.
```

- [ ] **Step 5: Selectively stage and commit**

Run:

```bash
git add tradingagents/dataflows/structured.py tradingagents/dataflows/massive.py tests/test_structured_equity_schemas.py tests/test_massive_corporate_actions.py README.md
git commit -m "feat(data): add massive corporate actions"
```

Expected: commit succeeds and does not stage unrelated `.DS_Store` files.
