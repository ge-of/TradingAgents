# Phase 2C-S2 Historical Aggregates OHLCV Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a mocked, structured Massive historical OHLCV adapter that returns `PriceHistory` and participates in the structured price-history entry point.

**Architecture:** Extend the Slice `2C-S1` Massive module with one price-history function and register it only in `STRUCTURED_VENDOR_METHODS["get_price_history"]`. Keep HTTP behavior injectable for tests, normalize aggregate bars into the existing `PriceHistory` contract, and leave agent-facing report tools unchanged.

**Tech Stack:** Python 3.10+, `requests`, pandas, existing `PriceHistory`, existing provider exceptions, pytest with fake sessions.

---

## Prerequisite State

Start from `main` after Slice `2C-S1` is merged. Stop and complete `2C-S1` first if `tradingagents/dataflows/massive.py` does not define `MASSIVE_PROVIDER`, `MASSIVE_API_KEY_ENV`, and `get_massive_api_key()`.

## Context To Read First

- `docs/project-architecture-guidelines.md`
- `docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md`
- `docs/superpowers/specs/2026-05-17-phase-2c-s2-historical-aggregates-ohlcv-adapter-design.md`
- `tradingagents/dataflows/massive.py`
- `tradingagents/dataflows/structured.py`
- `tradingagents/dataflows/exceptions.py`
- `tradingagents/dataflows/availability.py`
- `tests/test_structured_as_of_contract.py`
- `tests/test_structured_data_entry_points.py`

## Expected Git Diff Scope

Expected modified or created files:

- Modify: `tradingagents/dataflows/massive.py`
- Modify: `tradingagents/dataflows/structured.py`
- Create: `tests/test_massive_price_history.py`
- Modify: `README.md`

No expected changes:

- `tradingagents/dataflows/interface.py`
- `tradingagents/default_config.py`, except if `2C-S1` was not already merged
- Any fundamentals, ticker reference, corporate actions, screener, portfolio, macro, graph, prompt, CLI, or IBKR files

## Hard Non-Goals

- Do not make live network calls while implementing or verifying.
- Do not add fundamentals, ticker metadata, dividends, splits, or corporate actions.
- Do not register Massive in `VENDOR_METHODS` or change `route_to_vendor()`.
- Do not add retries or a broad client abstraction beyond the private helpers needed for this endpoint.
- Do not require `MASSIVE_API_KEY` for default tests.
- Do not broaden into Phase 2D, screener, portfolio, macro, graph, prompts, CLI UX, or IBKR.

### Task 1: Mocked Aggregate Parsing

**Files:**
- Create: `tests/test_massive_price_history.py`
- Modify: `tradingagents/dataflows/massive.py`

- [ ] **Step 1: Write the failing aggregate parsing test**

Create `tests/test_massive_price_history.py`:

```python
import pandas as pd
import pytest

from tradingagents.dataflows.massive import MASSIVE_API_KEY_ENV, get_massive_price_history
from tradingagents.dataflows.structured import PRICE_HISTORY_COLUMNS, PriceHistory


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.response


@pytest.mark.unit
def test_get_massive_price_history_parses_daily_aggregates(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(
        FakeResponse(
            {
                "ticker": "AAPL",
                "results": [
                    {"t": 1778803200000, "o": 100.0, "h": 105.0, "l": 99.0, "c": 104.0, "v": 1234567},
                    {"t": 1778889600000, "o": 104.0, "h": 110.0, "l": 103.0, "c": 108.0, "v": 2234567},
                ],
            }
        )
    )

    result = get_massive_price_history("aapl", "2026-05-15", "2026-05-16", session=session)

    assert isinstance(result, PriceHistory)
    assert result.ticker == "AAPL"
    assert result.start == "2026-05-15"
    assert result.end == "2026-05-16"
    assert tuple(result.data.columns) == PRICE_HISTORY_COLUMNS
    assert result.data.to_dict("records") == [
        {"Date": "2026-05-15", "Open": 100.0, "High": 105.0, "Low": 99.0, "Close": 104.0, "Volume": 1234567},
        {"Date": "2026-05-16", "Open": 104.0, "High": 110.0, "Low": 103.0, "Close": 108.0, "Volume": 2234567},
    ]
    assert session.calls[0]["params"]["apiKey"] == "test-key"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_massive_price_history.py::test_get_massive_price_history_parses_daily_aggregates -q
```

Expected: FAIL because `get_massive_price_history` does not exist.

- [ ] **Step 3: Implement minimal aggregate parsing**

Add to `tradingagents/dataflows/massive.py`:

```python
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

from .availability import ProviderResultRole, normalize_provider_result
from .exceptions import ProviderNoDataError, ProviderUnavailableError
from .structured import PRICE_HISTORY_COLUMNS, PriceHistory

MASSIVE_BASE_URL = "https://api.massive.com"
MASSIVE_TIMEOUT_SECONDS = 10


def _daily_aggs_url(ticker: str, start: str, end: str) -> str:
    return f"{MASSIVE_BASE_URL}/v2/aggs/ticker/{ticker.upper()}/range/1/day/{start}/{end}"


def _timestamp_ms_to_date(value: int | float) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()


def _parse_aggregate_rows(payload: dict[str, Any], ticker: str, start: str, end: str) -> pd.DataFrame:
    rows = normalize_provider_result(
        payload.get("results", []),
        provider=MASSIVE_PROVIDER,
        method="get_price_history",
        role=ProviderResultRole.REQUIRED,
        no_data_message=f"No Massive OHLCV bars found for {ticker.upper()} from {start} to {end}",
        details={"ticker": ticker.upper(), "start": start, "end": end},
    )
    records = [
        {
            "Date": _timestamp_ms_to_date(row["t"]),
            "Open": float(row["o"]),
            "High": float(row["h"]),
            "Low": float(row["l"]),
            "Close": float(row["c"]),
            "Volume": int(row["v"]),
        }
        for row in rows
    ]
    return pd.DataFrame(records, columns=PRICE_HISTORY_COLUMNS)


def get_massive_price_history(
    ticker: str,
    start: str,
    end: str,
    *,
    session: requests.Session | None = None,
) -> PriceHistory:
    api_key = get_massive_api_key()
    client = session or requests.Session()
    response = client.get(
        _daily_aggs_url(ticker, start, end),
        params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key},
        timeout=MASSIVE_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise ProviderUnavailableError(
            f"Massive aggregate request failed with HTTP {response.status_code}",
            provider=MASSIVE_PROVIDER,
            method="get_price_history",
            status_code=response.status_code,
        )
    payload = response.json()
    data = _parse_aggregate_rows(payload, ticker, start, end)
    return PriceHistory(ticker=ticker.upper(), start=start, end=end, data=data)
```

- [ ] **Step 4: Run the parsing test**

Run:

```bash
uv run pytest tests/test_massive_price_history.py::test_get_massive_price_history_parses_daily_aggregates -q
```

Expected: PASS.

### Task 2: Structured Price Registry

**Files:**
- Modify: `tests/test_massive_price_history.py`
- Modify: `tradingagents/dataflows/structured.py`

- [ ] **Step 1: Add failing structured routing test**

Append to `tests/test_massive_price_history.py`:

```python
import copy

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from tradingagents.dataflows import structured


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


@pytest.mark.unit
def test_massive_price_history_is_registered_for_structured_routing(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(FakeResponse({"ticker": "AAPL", "results": [{"t": 1778803200000, "o": 1, "h": 2, "l": 1, "c": 2, "v": 10}]}))
    monkeypatch.setattr("tradingagents.dataflows.massive.requests.Session", lambda: session)
    config_module.set_config({"data_vendors": {"core_stock_apis": "massive"}})

    result = structured.get_price_history("AAPL", "2026-05-15", "2026-05-16")

    assert result.ticker == "AAPL"
    assert result.data["Date"].tolist() == ["2026-05-15"]
```

- [ ] **Step 2: Run the routing test to verify it fails**

Run:

```bash
uv run pytest tests/test_massive_price_history.py::test_massive_price_history_is_registered_for_structured_routing -q
```

Expected: FAIL because the `massive` structured provider is not registered.

- [ ] **Step 3: Register only the structured price provider**

Modify `tradingagents/dataflows/structured.py` after `STRUCTURED_VENDOR_METHODS` is defined:

```python
from .massive import get_massive_price_history

STRUCTURED_VENDOR_METHODS["get_price_history"]["massive"] = get_massive_price_history
```

If importing `massive.py` creates a circular import because `massive.py` imports `PriceHistory`, move the registration to the bottom of `structured.py` after `PriceHistory` and public functions are defined:

```python
from .massive import get_massive_price_history as _get_massive_price_history

STRUCTURED_VENDOR_METHODS["get_price_history"]["massive"] = _get_massive_price_history
```

- [ ] **Step 4: Run structured routing tests**

Run:

```bash
uv run pytest tests/test_massive_price_history.py tests/test_structured_data_entry_points.py tests/test_structured_as_of_contract.py -q
```

Expected: PASS.

### Task 3: Error And No-Data Cases

**Files:**
- Modify: `tests/test_massive_price_history.py`
- Modify: `tradingagents/dataflows/massive.py`

- [ ] **Step 1: Add failing error tests**

Append to `tests/test_massive_price_history.py`:

```python
import requests

from tradingagents.dataflows.exceptions import (
    ProviderAuthError,
    ProviderNoDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


@pytest.mark.unit
def test_massive_price_history_raises_no_data_for_empty_results(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(FakeResponse({"ticker": "AAPL", "results": []}))

    with pytest.raises(ProviderNoDataError) as exc_info:
        get_massive_price_history("AAPL", "2026-05-15", "2026-05-16", session=session)

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_price_history"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderRateLimitError),
        (500, ProviderUnavailableError),
    ],
)
def test_massive_price_history_maps_http_errors(monkeypatch, status_code, expected_error):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(FakeResponse({"error": "failed"}, status_code=status_code, headers={"Retry-After": "30"}))

    with pytest.raises(expected_error) as exc_info:
        get_massive_price_history("AAPL", "2026-05-15", "2026-05-16", session=session)

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_price_history"
    assert "test-key" not in str(exc_info.value)


@pytest.mark.unit
def test_massive_price_history_maps_timeout(monkeypatch):
    class TimeoutSession:
        def get(self, url, params=None, timeout=None):
            raise requests.Timeout("request timed out")

    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")

    with pytest.raises(ProviderUnavailableError):
        get_massive_price_history("AAPL", "2026-05-15", "2026-05-16", session=TimeoutSession())
```

- [ ] **Step 2: Run the error tests to verify they fail**

Run:

```bash
uv run pytest tests/test_massive_price_history.py -q
```

Expected: FAIL until status-specific mapping and timeout handling are added.

- [ ] **Step 3: Add endpoint-level error mapping**

Update `tradingagents/dataflows/massive.py` with private helpers:

```python
from .exceptions import ProviderAuthError, ProviderRateLimitError, ProviderUnavailableError


def _raise_for_massive_status(response, method: str) -> None:
    status_code = response.status_code
    if status_code in (401, 403):
        raise ProviderAuthError(
            f"Massive {method} request was rejected with HTTP {status_code}",
            provider=MASSIVE_PROVIDER,
            method=method,
            status_code=status_code,
        )
    if status_code == 429:
        retry_after = response.headers.get("Retry-After")
        raise ProviderRateLimitError(
            "Massive rate limit exceeded",
            provider=MASSIVE_PROVIDER,
            method=method,
            status_code=status_code,
            retry_after=int(retry_after) if retry_after and retry_after.isdigit() else None,
        )
    if status_code >= 500:
        raise ProviderUnavailableError(
            f"Massive {method} request failed with HTTP {status_code}",
            provider=MASSIVE_PROVIDER,
            method=method,
            status_code=status_code,
        )
    if status_code != 200:
        raise ProviderUnavailableError(
            f"Massive {method} request failed with HTTP {status_code}",
            provider=MASSIVE_PROVIDER,
            method=method,
            status_code=status_code,
        )
```

Wrap `client.get()` and `response.json()`:

```python
try:
    response = client.get(...)
except requests.Timeout as exc:
    raise ProviderUnavailableError(
        "Massive get_price_history request timed out",
        provider=MASSIVE_PROVIDER,
        method="get_price_history",
    ) from exc

_raise_for_massive_status(response, "get_price_history")
try:
    payload = response.json()
except ValueError as exc:
    raise ProviderUnavailableError(
        "Massive get_price_history response was not valid JSON",
        provider=MASSIVE_PROVIDER,
        method="get_price_history",
    ) from exc
```

- [ ] **Step 4: Run the full Massive price tests**

Run:

```bash
uv run pytest tests/test_massive_price_history.py -q
```

Expected: PASS.

### Task 4: README Smoke Note

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a short optional smoke note**

Under the Massive setup text from `2C-S1`, add:

```markdown
The Massive adapter is covered by mocked tests by default. A real provider smoke check is optional and should only be run when `MASSIVE_API_KEY` is set; the dedicated smoke test is introduced in Slice 2C-S7.
```

### Task 5: Verification And Commit

**Files:**
- All files from Tasks 1-4

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run pytest tests/test_massive_price_history.py tests/test_structured_data_entry_points.py tests/test_structured_as_of_contract.py tests/test_data_provider_exceptions.py -q
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
git diff -- tradingagents/dataflows/massive.py tradingagents/dataflows/structured.py tests/test_massive_price_history.py README.md
```

Expected: only planned files changed, plus any pre-existing unrelated untracked `.DS_Store` files.

- [ ] **Step 4: Docs drift checkpoint**

Use this exact checkpoint language in the PR or final response:

```text
Docs drift checkpoint: README now notes that Massive live checks are optional and credential-gated. Architecture docs do not need changes because this slice follows the existing structured data boundary and does not alter agent-facing router behavior.
```

- [ ] **Step 5: Selectively stage and commit**

Run:

```bash
git add tradingagents/dataflows/massive.py tradingagents/dataflows/structured.py tests/test_massive_price_history.py README.md
git commit -m "feat(data): add massive price history adapter"
```

Expected: commit succeeds and does not stage unrelated `.DS_Store` files.
