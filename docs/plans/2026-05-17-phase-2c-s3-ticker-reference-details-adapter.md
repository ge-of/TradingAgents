# Phase 2C-S3 Ticker Reference Details Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a structured Massive ticker details adapter with explicit missing-field availability metadata.

**Architecture:** Extend the structured data contract with a focused `TickerDetails` dataclass and `get_ticker_details()` entry point. Implement the Massive adapter in `tradingagents/dataflows/massive.py`, register it only in the structured registry, and keep universe membership, fundamentals, and agent-facing report routing out of scope.

**Tech Stack:** Python 3.10+, dataclasses, existing structured data registry, existing provider exceptions and availability metadata, pytest with fake sessions.

---

## Prerequisite State

Start from `main` after Slices `2C-S1` and `2C-S2` are merged. Stop if `tradingagents/dataflows/massive.py` does not provide Massive credential helpers and the price-history adapter pattern.

## Context To Read First

- `docs/project-architecture-guidelines.md`
- `docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md`
- `docs/superpowers/specs/2026-05-17-phase-2c-s3-ticker-reference-details-adapter-design.md`
- `tradingagents/dataflows/structured.py`
- `tradingagents/dataflows/massive.py`
- `tradingagents/dataflows/exceptions.py`
- `tests/test_structured_equity_schemas.py`
- `tests/test_massive_price_history.py`

## Expected Git Diff Scope

Expected modified or created files:

- Modify: `tradingagents/dataflows/structured.py`
- Modify: `tradingagents/dataflows/massive.py`
- Modify: `tests/test_structured_equity_schemas.py`
- Create: `tests/test_massive_ticker_details.py`
- Modify: `docs/project-architecture-guidelines.md`

No expected changes:

- `tradingagents/dataflows/interface.py`
- Fundamentals adapter files
- Screener, macro, portfolio, graph, prompt, CLI, or IBKR files

## Hard Non-Goals

- Do not add universe membership or index constituent APIs.
- Do not parse financial statements or fundamentals.
- Do not add screener filters or presets.
- Do not register Massive in `VENDOR_METHODS` or change `route_to_vendor()`.
- Do not require live credentials for default tests.
- Do not broaden into Phase 2D, screener, portfolio, macro, graph, prompts, CLI UX, or IBKR.

### Task 1: TickerDetails Structured Schema

**Files:**
- Modify: `tests/test_structured_equity_schemas.py`
- Modify: `tradingagents/dataflows/structured.py`

- [ ] **Step 1: Write the failing schema test**

Append to `tests/test_structured_equity_schemas.py`:

```python
from tradingagents.dataflows.structured import TickerDetails


@pytest.mark.unit
def test_ticker_details_tracks_reference_metadata_and_availability():
    availability = [
        DataAvailability(
            field="currency",
            status=AvailabilityStatus.MISSING,
            message="Massive response did not include currency",
            provider="massive",
        )
    ]

    details = TickerDetails(
        ticker="AAPL",
        as_of="2026-05-16",
        name="Apple Inc.",
        market="stocks",
        exchange="XNAS",
        currency=None,
        locale="us",
        active=True,
        availability=availability,
    )

    assert details.ticker == "AAPL"
    assert details.as_of == "2026-05-16"
    assert details.name == "Apple Inc."
    assert details.market == "stocks"
    assert details.exchange == "XNAS"
    assert details.currency is None
    assert details.locale == "us"
    assert details.active is True
    assert details.availability == availability
```

- [ ] **Step 2: Run the schema test to verify it fails**

Run:

```bash
uv run pytest tests/test_structured_equity_schemas.py::test_ticker_details_tracks_reference_metadata_and_availability -q
```

Expected: FAIL because `TickerDetails` does not exist.

- [ ] **Step 3: Add `TickerDetails` and registry entries**

Modify `tradingagents/dataflows/structured.py`:

```python
@dataclass
class TickerDetails:
    """Structured reference metadata for a ticker."""

    ticker: str
    as_of: str
    name: str | None = None
    market: str | None = None
    exchange: str | None = None
    currency: str | None = None
    locale: str | None = None
    active: bool | None = None
    availability: list[DataAvailability] = field(default_factory=list)
```

Add the method category and registry slot:

```python
STRUCTURED_METHOD_CATEGORIES = {
    "get_price_history": "core_stock_apis",
    "get_ticker_details": "core_stock_apis",
    "get_fundamentals_snapshot": "fundamental_data",
    "get_indicator_series": "technical_indicators",
}

STRUCTURED_VENDOR_METHODS: dict[str, dict[str, StructuredProvider]] = {
    "get_price_history": {},
    "get_ticker_details": {},
    "get_fundamentals_snapshot": {},
    "get_indicator_series": {},
}
```

Add the public entry point:

```python
def get_ticker_details(ticker: str, as_of: str) -> TickerDetails:
    """Return structured reference metadata from the configured provider."""
    as_of_date = _parse_iso_date(as_of, "as_of")
    details = route_structured_method("get_ticker_details", ticker, as_of_date.isoformat())
    return details
```

Add `TickerDetails` and `get_ticker_details` to `__all__`.

- [ ] **Step 4: Run schema tests**

Run:

```bash
uv run pytest tests/test_structured_equity_schemas.py -q
```

Expected: PASS.

### Task 2: Massive Ticker Details Parser

**Files:**
- Create: `tests/test_massive_ticker_details.py`
- Modify: `tradingagents/dataflows/massive.py`

- [ ] **Step 1: Write failing parser tests**

Create `tests/test_massive_ticker_details.py`:

```python
import copy

import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from tradingagents.dataflows import structured
from tradingagents.dataflows.exceptions import ProviderNoDataError
from tradingagents.dataflows.massive import MASSIVE_API_KEY_ENV, get_massive_ticker_details
from tradingagents.dataflows.structured import AvailabilityStatus, TickerDetails
from tests.test_massive_price_history import FakeResponse, FakeSession


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


@pytest.mark.unit
def test_get_massive_ticker_details_parses_reference_payload(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(
        FakeResponse(
            {
                "results": {
                    "ticker": "AAPL",
                    "name": "Apple Inc.",
                    "market": "stocks",
                    "primary_exchange": "XNAS",
                    "currency_name": "usd",
                    "locale": "us",
                    "active": True,
                }
            }
        )
    )

    result = get_massive_ticker_details("aapl", "2026-05-16", session=session)

    assert isinstance(result, TickerDetails)
    assert result.ticker == "AAPL"
    assert result.as_of == "2026-05-16"
    assert result.name == "Apple Inc."
    assert result.market == "stocks"
    assert result.exchange == "XNAS"
    assert result.currency == "usd"
    assert result.locale == "us"
    assert result.active is True
    assert result.availability == []
    assert session.calls[0]["params"]["date"] == "2026-05-16"
    assert session.calls[0]["params"]["apiKey"] == "test-key"
```

- [ ] **Step 2: Add failing missing-field and no-data tests**

Append to `tests/test_massive_ticker_details.py`:

```python
@pytest.mark.unit
def test_get_massive_ticker_details_records_missing_fields(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(FakeResponse({"results": {"ticker": "AAPL", "active": True}}))

    result = get_massive_ticker_details("AAPL", "2026-05-16", session=session)

    missing_fields = {item.field for item in result.availability if item.status is AvailabilityStatus.MISSING}
    assert missing_fields == {"name", "market", "exchange", "currency", "locale"}
    assert all(item.provider == "massive" for item in result.availability)


@pytest.mark.unit
def test_get_massive_ticker_details_raises_no_data_for_missing_results(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(FakeResponse({"results": None}))

    with pytest.raises(ProviderNoDataError) as exc_info:
        get_massive_ticker_details("AAPL", "2026-05-16", session=session)

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_ticker_details"
```

- [ ] **Step 3: Run parser tests to verify they fail**

Run:

```bash
uv run pytest tests/test_massive_ticker_details.py -q
```

Expected: FAIL because `get_massive_ticker_details` does not exist.

- [ ] **Step 4: Implement Massive details parsing**

Add to `tradingagents/dataflows/massive.py`:

```python
from .structured import AvailabilityStatus, DataAvailability, TickerDetails


def _ticker_details_url(ticker: str) -> str:
    return f"{MASSIVE_BASE_URL}/v3/reference/tickers/{ticker.upper()}"


def _missing_availability(field: str) -> DataAvailability:
    return DataAvailability(
        field=field,
        status=AvailabilityStatus.MISSING,
        message=f"Massive response did not include {field}",
        provider=MASSIVE_PROVIDER,
    )


def _field_or_missing(results: dict, source_field: str, target_field: str, availability: list[DataAvailability]):
    value = results.get(source_field)
    if value in (None, ""):
        availability.append(_missing_availability(target_field))
        return None
    return value


def get_massive_ticker_details(
    ticker: str,
    as_of: str,
    *,
    session: requests.Session | None = None,
) -> TickerDetails:
    api_key = get_massive_api_key()
    client = session or requests.Session()
    response = client.get(
        _ticker_details_url(ticker),
        params={"date": as_of, "apiKey": api_key},
        timeout=MASSIVE_TIMEOUT_SECONDS,
    )
    _raise_for_massive_status(response, "get_ticker_details")
    payload = response.json()
    results = normalize_provider_result(
        payload.get("results"),
        provider=MASSIVE_PROVIDER,
        method="get_ticker_details",
        role=ProviderResultRole.REQUIRED,
        no_data_message=f"No Massive ticker details found for {ticker.upper()} on {as_of}",
        details={"ticker": ticker.upper(), "as_of": as_of},
    )
    availability: list[DataAvailability] = []
    return TickerDetails(
        ticker=str(results.get("ticker") or ticker).upper(),
        as_of=as_of,
        name=_field_or_missing(results, "name", "name", availability),
        market=_field_or_missing(results, "market", "market", availability),
        exchange=_field_or_missing(results, "primary_exchange", "exchange", availability),
        currency=_field_or_missing(results, "currency_name", "currency", availability),
        locale=_field_or_missing(results, "locale", "locale", availability),
        active=results.get("active"),
        availability=availability,
    )
```

- [ ] **Step 5: Run parser tests**

Run:

```bash
uv run pytest tests/test_massive_ticker_details.py -q
```

Expected: PASS.

### Task 3: Structured Routing

**Files:**
- Modify: `tests/test_massive_ticker_details.py`
- Modify: `tradingagents/dataflows/structured.py`

- [ ] **Step 1: Add failing structured routing test**

Append to `tests/test_massive_ticker_details.py`:

```python
@pytest.mark.unit
def test_structured_get_ticker_details_routes_to_massive(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(FakeResponse({"results": {"ticker": "AAPL", "name": "Apple Inc.", "active": True}}))
    monkeypatch.setattr("tradingagents.dataflows.massive.requests.Session", lambda: session)
    config_module.set_config({"data_vendors": {"core_stock_apis": "massive"}})

    result = structured.get_ticker_details("AAPL", "2026-05-16")

    assert result.ticker == "AAPL"
    assert result.name == "Apple Inc."
```

- [ ] **Step 2: Run routing test to verify it fails**

Run:

```bash
uv run pytest tests/test_massive_ticker_details.py::test_structured_get_ticker_details_routes_to_massive -q
```

Expected: FAIL until the Massive provider is registered for `get_ticker_details`.

- [ ] **Step 3: Register the Massive details provider**

At the same registration point used for `get_massive_price_history`, add:

```python
from .massive import get_massive_ticker_details as _get_massive_ticker_details

STRUCTURED_VENDOR_METHODS["get_ticker_details"]["massive"] = _get_massive_ticker_details
```

- [ ] **Step 4: Run structured routing tests**

Run:

```bash
uv run pytest tests/test_massive_ticker_details.py tests/test_structured_data_entry_points.py tests/test_structured_equity_schemas.py -q
```

Expected: PASS.

### Task 4: Docs Drift Checkpoint

**Files:**
- Modify: `docs/project-architecture-guidelines.md`

- [ ] **Step 1: Add structured metadata contract wording**

In `docs/project-architecture-guidelines.md`, under the `tradingagents/dataflows/` module responsibility paragraph, add one concise sentence:

```markdown
Ticker reference metadata, when needed by downstream quantitative workflows, should use structured data contracts with explicit missing-field availability records rather than agent-facing prose reports.
```

- [ ] **Step 2: Confirm the docs diff is narrow**

Run:

```bash
git diff -- docs/project-architecture-guidelines.md
```

Expected: only the one sentence above is added.

### Task 5: Verification And Commit

**Files:**
- All files from Tasks 1-4

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run pytest tests/test_massive_ticker_details.py tests/test_structured_equity_schemas.py tests/test_structured_data_entry_points.py tests/test_massive_price_history.py -q
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
git diff -- tradingagents/dataflows/structured.py tradingagents/dataflows/massive.py tests/test_structured_equity_schemas.py tests/test_massive_ticker_details.py docs/project-architecture-guidelines.md
```

Expected: only planned files changed, plus any pre-existing unrelated untracked `.DS_Store` files.

- [ ] **Step 4: Docs drift checkpoint**

Use this exact checkpoint language in the PR or final response:

```text
Docs drift checkpoint: architecture guidelines now note that ticker reference metadata belongs in structured data contracts with missing-field availability records. No README update is needed because no new credential, command, or user-facing setup behavior is introduced.
```

- [ ] **Step 5: Selectively stage and commit**

Run:

```bash
git add tradingagents/dataflows/structured.py tradingagents/dataflows/massive.py tests/test_structured_equity_schemas.py tests/test_massive_ticker_details.py docs/project-architecture-guidelines.md
git commit -m "feat(data): add massive ticker details adapter"
```

Expected: commit succeeds and does not stage unrelated `.DS_Store` files.
