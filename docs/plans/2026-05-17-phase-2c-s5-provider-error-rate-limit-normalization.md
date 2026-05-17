# Phase 2C-S5 Provider Error Rate Limit Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize Massive HTTP, timeout, malformed-response, and rate-limit error handling into deterministic shared provider errors with safe diagnostics.

**Architecture:** Add one Massive request helper in `tradingagents/dataflows/massive.py` and refactor existing Massive adapter methods to use it. Keep no-data parsing in each adapter where domain semantics differ, keep tests mocked, and do not introduce retries or user-facing router changes.

**Tech Stack:** Python 3.10+, `requests`, existing provider exception hierarchy, existing Massive adapter tests, pytest fake sessions.

---

## Prerequisite State

Start from `main` after Slices `2C-S1` through `2C-S4` are merged. Stop if `tradingagents/dataflows/massive.py` does not contain Massive price history, ticker details, and corporate actions.

## Context To Read First

- `docs/project-architecture-guidelines.md`
- `docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md`
- `docs/superpowers/specs/2026-05-17-phase-2c-s5-provider-error-rate-limit-normalization-design.md`
- `tradingagents/dataflows/massive.py`
- `tradingagents/dataflows/exceptions.py`
- `tests/test_data_provider_exceptions.py`
- `tests/test_massive_price_history.py`
- `tests/test_massive_ticker_details.py`
- `tests/test_massive_corporate_actions.py`

## Expected Git Diff Scope

Expected modified or created files:

- Modify: `tradingagents/dataflows/massive.py`
- Create: `tests/test_massive_errors.py`
- Modify: existing Massive adapter tests only if imports/helpers need deduplication
- Modify: `README.md` if provider troubleshooting text is added

No expected changes:

- `tradingagents/dataflows/interface.py`
- `tradingagents/dataflows/structured.py`, unless a refactor reveals a direct registration typo from earlier slices
- Fundamentals, screener, portfolio, macro, graph, prompt, CLI, or IBKR files

## Hard Non-Goals

- Do not add retries, backoff, circuit breakers, or caching.
- Do not add new Massive endpoints.
- Do not change no-data versus optional-empty semantics.
- Do not change `route_to_vendor()` or `VENDOR_METHODS`.
- Do not require live credentials for default tests.
- Do not broaden into Phase 2D, screener, portfolio, macro, graph, prompts, CLI UX, or IBKR.

### Task 1: Central Error Mapping Tests

**Files:**
- Create: `tests/test_massive_errors.py`
- Modify: `tradingagents/dataflows/massive.py`

- [ ] **Step 1: Write failing HTTP status tests**

Create `tests/test_massive_errors.py`:

```python
import pytest
import requests

from tradingagents.dataflows.exceptions import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from tradingagents.dataflows.massive import MASSIVE_API_KEY_ENV, request_massive_json
from tests.test_massive_price_history import FakeResponse, FakeSession


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderRateLimitError),
        (500, ProviderUnavailableError),
        (503, ProviderUnavailableError),
        (418, ProviderUnavailableError),
    ],
)
def test_request_massive_json_maps_http_statuses(monkeypatch, status_code, expected_error):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "secret-test-key")
    session = FakeSession(FakeResponse({"error": "failed"}, status_code=status_code, headers={"Retry-After": "45"}))

    with pytest.raises(expected_error) as exc_info:
        request_massive_json("/v3/test", {"ticker": "AAPL"}, method="test_method", session=session)

    error = exc_info.value
    assert error.provider == "massive"
    assert error.method == "test_method"
    assert error.status_code == status_code
    assert "secret-test-key" not in str(error)
    assert "apiKey" not in error.details
```

- [ ] **Step 2: Add failing rate-limit retry-after assertion**

Append:

```python
@pytest.mark.unit
def test_request_massive_json_preserves_retry_after(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "secret-test-key")
    session = FakeSession(FakeResponse({"error": "limited"}, status_code=429, headers={"Retry-After": "45"}))

    with pytest.raises(ProviderRateLimitError) as exc_info:
        request_massive_json("/v3/test", {"ticker": "AAPL"}, method="test_method", session=session)

    assert exc_info.value.retry_after == 45
    assert exc_info.value.details["retry_after"] == 45
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_massive_errors.py -q
```

Expected: FAIL because `request_massive_json` does not exist.

- [ ] **Step 4: Add central request helper**

Add to `tradingagents/dataflows/massive.py`:

```python
from collections.abc import Mapping

from .exceptions import ProviderAuthError, ProviderRateLimitError, ProviderUnavailableError


def _safe_massive_details(path: str, params: Mapping[str, object], extra: Mapping[str, object] | None = None) -> dict:
    safe_params = {key: value for key, value in params.items() if key != "apiKey"}
    details = {"path": path, **safe_params}
    if extra:
        details.update(extra)
    return details


def _massive_url(path: str) -> str:
    return f"{MASSIVE_BASE_URL}{path}"


def _raise_massive_status_error(response, *, path: str, params: Mapping[str, object], method: str) -> None:
    status_code = response.status_code
    details = _safe_massive_details(path, params, {"status_code": status_code})
    if status_code in (401, 403):
        raise ProviderAuthError(
            f"Massive {method} request was rejected with HTTP {status_code}",
            provider=MASSIVE_PROVIDER,
            method=method,
            status_code=status_code,
            details=details,
        )
    if status_code == 429:
        retry_after_raw = response.headers.get("Retry-After")
        retry_after = int(retry_after_raw) if retry_after_raw and retry_after_raw.isdigit() else None
        raise ProviderRateLimitError(
            "Massive rate limit exceeded",
            provider=MASSIVE_PROVIDER,
            method=method,
            status_code=status_code,
            retry_after=retry_after,
            details=details,
        )
    if status_code != 200:
        raise ProviderUnavailableError(
            f"Massive {method} request failed with HTTP {status_code}",
            provider=MASSIVE_PROVIDER,
            method=method,
            status_code=status_code,
            details=details,
        )


def request_massive_json(
    path: str,
    params: Mapping[str, object],
    *,
    method: str,
    session: requests.Session | None = None,
) -> dict:
    api_key = get_massive_api_key()
    request_params = {**dict(params), "apiKey": api_key}
    client = session or requests.Session()
    try:
        response = client.get(
            _massive_url(path),
            params=request_params,
            timeout=MASSIVE_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        raise ProviderUnavailableError(
            f"Massive {method} request timed out",
            provider=MASSIVE_PROVIDER,
            method=method,
            details=_safe_massive_details(path, request_params),
        ) from exc
    except requests.RequestException as exc:
        raise ProviderUnavailableError(
            f"Massive {method} request failed",
            provider=MASSIVE_PROVIDER,
            method=method,
            details=_safe_massive_details(path, request_params),
        ) from exc

    _raise_massive_status_error(response, path=path, params=request_params, method=method)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderUnavailableError(
            f"Massive {method} response was not valid JSON",
            provider=MASSIVE_PROVIDER,
            method=method,
            details=_safe_massive_details(path, request_params),
        ) from exc
    if not isinstance(payload, dict):
        raise ProviderUnavailableError(
            f"Massive {method} response JSON was not an object",
            provider=MASSIVE_PROVIDER,
            method=method,
            details=_safe_massive_details(path, request_params),
        )
    return payload
```

- [ ] **Step 5: Run central status tests**

Run:

```bash
uv run pytest tests/test_massive_errors.py::test_request_massive_json_maps_http_statuses tests/test_massive_errors.py::test_request_massive_json_preserves_retry_after -q
```

Expected: PASS.

### Task 2: Timeout, Request Error, And Malformed JSON

**Files:**
- Modify: `tests/test_massive_errors.py`
- Modify: `tradingagents/dataflows/massive.py`

- [ ] **Step 1: Add failing transport and JSON tests**

Append to `tests/test_massive_errors.py`:

```python
class TimeoutSession:
    def get(self, url, params=None, timeout=None):
        raise requests.Timeout("timed out")


class ConnectionErrorSession:
    def get(self, url, params=None, timeout=None):
        raise requests.ConnectionError("connection failed")


class MalformedJsonResponse(FakeResponse):
    def json(self):
        raise ValueError("not json")


@pytest.mark.unit
@pytest.mark.parametrize("session", [TimeoutSession(), ConnectionErrorSession()])
def test_request_massive_json_maps_transport_errors(monkeypatch, session):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "secret-test-key")

    with pytest.raises(ProviderUnavailableError) as exc_info:
        request_massive_json("/v3/test", {"ticker": "AAPL"}, method="test_method", session=session)

    assert exc_info.value.provider == "massive"
    assert "secret-test-key" not in str(exc_info.value)
    assert "apiKey" not in exc_info.value.details


@pytest.mark.unit
def test_request_massive_json_maps_malformed_json(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "secret-test-key")
    session = FakeSession(MalformedJsonResponse("not-json"))

    with pytest.raises(ProviderUnavailableError) as exc_info:
        request_massive_json("/v3/test", {"ticker": "AAPL"}, method="test_method", session=session)

    assert "not valid JSON" in exc_info.value.message
    assert "secret-test-key" not in str(exc_info.value)
```

- [ ] **Step 2: Run transport tests**

Run:

```bash
uv run pytest tests/test_massive_errors.py -q
```

Expected: PASS after the helper from Task 1.

### Task 3: Refactor Existing Massive Adapters

**Files:**
- Modify: `tradingagents/dataflows/massive.py`
- Existing tests: `tests/test_massive_price_history.py`, `tests/test_massive_ticker_details.py`, `tests/test_massive_corporate_actions.py`

- [ ] **Step 1: Replace endpoint-local request code**

In `get_massive_price_history()`, replace direct `client.get()`, `_daily_aggs_url()`, `_raise_for_massive_status()`, and `response.json()` code with:

```python
payload = request_massive_json(
    f"/v2/aggs/ticker/{ticker.upper()}/range/1/day/{start}/{end}",
    {"adjusted": "true", "sort": "asc", "limit": 50000},
    method="get_price_history",
    session=session,
)
```

In `get_massive_ticker_details()`, use:

```python
payload = request_massive_json(
    f"/v3/reference/tickers/{ticker.upper()}",
    {"date": as_of},
    method="get_ticker_details",
    session=session,
)
```

In corporate action helpers, use:

```python
payload = request_massive_json(path, params, method=method, session=client)
```

Keep adapter-specific no-data and optional-empty parsing unchanged.

- [ ] **Step 2: Remove duplicated private status helpers**

Remove endpoint-local helpers that are fully replaced by `request_massive_json`, such as `_raise_for_massive_status()` if no tests or adapters still need it.

- [ ] **Step 3: Run existing Massive adapter tests**

Run:

```bash
uv run pytest tests/test_massive_price_history.py tests/test_massive_ticker_details.py tests/test_massive_corporate_actions.py tests/test_massive_errors.py -q
```

Expected: PASS.

### Task 4: Provider Troubleshooting Docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add short troubleshooting text if absent**

In the Massive provider setup area, add:

```markdown
Massive provider errors are normalized before fallback: HTTP 401/403 indicate missing, invalid, or unauthorized `MASSIVE_API_KEY`; HTTP 429 indicates provider rate limits or quota; HTTP 5xx, timeouts, and malformed responses are treated as provider-unavailable errors. Error diagnostics do not include the API key.
```

### Task 5: Verification And Commit

**Files:**
- All files from Tasks 1-4

- [ ] **Step 1: Run focused Massive error suite**

Run:

```bash
uv run pytest tests/test_massive_errors.py tests/test_massive_price_history.py tests/test_massive_ticker_details.py tests/test_massive_corporate_actions.py tests/test_data_provider_exceptions.py -q
```

Expected: PASS.

- [ ] **Step 2: Run structured regression tests**

Run:

```bash
uv run pytest tests/test_structured_data_entry_points.py tests/test_structured_as_of_contract.py tests/test_data_provider_availability.py -q
```

Expected: PASS.

- [ ] **Step 3: Run diff hygiene checks**

Run:

```bash
git diff --check
git diff -- tradingagents/dataflows/interface.py tradingagents/dataflows/structured.py
```

Expected: no whitespace errors, no router diff, and no structured schema diff unless a prior-slice registration typo had to be corrected.

- [ ] **Step 4: Inspect expected diff scope**

Run:

```bash
git status --short
git diff -- tradingagents/dataflows/massive.py tests/test_massive_errors.py README.md
```

Expected: only planned files changed, plus any existing Massive test helper adjustments and pre-existing unrelated untracked `.DS_Store` files.

- [ ] **Step 5: Docs drift checkpoint**

Use this exact checkpoint language in the PR or final response:

```text
Docs drift checkpoint: README now documents Massive auth, rate-limit, unavailable, timeout, and malformed-response troubleshooting. Architecture docs already define the shared provider error contract, and this slice only normalizes Massive into that existing contract.
```

- [ ] **Step 6: Selectively stage and commit**

Run:

```bash
git add tradingagents/dataflows/massive.py tests/test_massive_errors.py tests/test_massive_price_history.py tests/test_massive_ticker_details.py tests/test_massive_corporate_actions.py README.md
git commit -m "feat(data): normalize massive provider errors"
```

Expected: commit succeeds and does not stage unrelated `.DS_Store` files.
