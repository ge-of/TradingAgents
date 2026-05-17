# Phase 2C-S6 Mocked Adapter Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the Massive adapter unit tests around shared mocked payload fixtures so the full adapter suite proves behavior without credentials or network access.

**Architecture:** Add test-only JSON fixtures and fake session helpers under `tests/`, then update existing Massive unit tests to use those fixtures. Keep production adapter code unchanged unless a previous slice left duplicated test-only helper code in production by mistake.

**Tech Stack:** Python 3.10+, pytest, JSON fixtures, existing Massive adapter tests, no live provider access.

---

## Prerequisite State

Start from `main` after Slices `2C-S1` through `2C-S5` are merged. Stop if the Massive adapter test files from earlier slices are missing.

## Context To Read First

- `docs/project-architecture-guidelines.md`
- `docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md`
- `docs/superpowers/specs/2026-05-17-phase-2c-s6-mocked-adapter-test-suite-design.md`
- `tests/test_massive_config.py`
- `tests/test_massive_price_history.py`
- `tests/test_massive_ticker_details.py`
- `tests/test_massive_corporate_actions.py`
- `tests/test_massive_errors.py`
- `tests/conftest.py`

## Expected Git Diff Scope

Expected modified or created files:

- Create: `tests/massive_fakes.py`
- Create: `tests/fixtures/massive/aggregates_daily_success.json`
- Create: `tests/fixtures/massive/ticker_details_success.json`
- Create: `tests/fixtures/massive/ticker_details_missing_fields.json`
- Create: `tests/fixtures/massive/dividends_success.json`
- Create: `tests/fixtures/massive/splits_success.json`
- Create: `tests/fixtures/massive/empty_results.json`
- Modify: `tests/test_massive_price_history.py`
- Modify: `tests/test_massive_ticker_details.py`
- Modify: `tests/test_massive_corporate_actions.py`
- Modify: `tests/test_massive_errors.py` only if it can reuse shared fakes cleanly

No expected changes:

- Production files under `tradingagents/`
- README or durable docs unless a fixture contract needs explanation
- Graph, prompt, CLI, screener, macro, portfolio, Phase 2D, or IBKR files

## Hard Non-Goals

- Do not make network calls.
- Do not require `MASSIVE_API_KEY`.
- Do not change provider adapter behavior.
- Do not add live smoke tests.
- Do not modify router registration.
- Do not broaden into Phase 2D, screener, portfolio, macro, graph, prompts, CLI UX, execution modeling, or IBKR.

### Task 1: Shared Test Fakes

**Files:**
- Create: `tests/massive_fakes.py`
- Modify: existing Massive tests after helper creation

- [ ] **Step 1: Create shared fake helpers**

Create `tests/massive_fakes.py`:

```python
import json
from pathlib import Path


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "massive"


def load_massive_fixture(name: str) -> dict:
    with (FIXTURE_ROOT / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


class FakeMassiveResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = str(payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeMassiveSession:
    def __init__(self, responses):
        if not isinstance(responses, list):
            responses = [responses]
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.responses.pop(0)
```

- [ ] **Step 2: Run import check**

Run:

```bash
uv run python -c "from tests.massive_fakes import FakeMassiveResponse, FakeMassiveSession, load_massive_fixture; print('ok')"
```

Expected: prints `ok`.

### Task 2: Payload Fixtures

**Files:**
- Create: `tests/fixtures/massive/aggregates_daily_success.json`
- Create: `tests/fixtures/massive/ticker_details_success.json`
- Create: `tests/fixtures/massive/ticker_details_missing_fields.json`
- Create: `tests/fixtures/massive/dividends_success.json`
- Create: `tests/fixtures/massive/splits_success.json`
- Create: `tests/fixtures/massive/empty_results.json`

- [ ] **Step 1: Add price aggregate fixture**

Create `tests/fixtures/massive/aggregates_daily_success.json`:

```json
{
  "ticker": "AAPL",
  "results": [
    {"t": 1778803200000, "o": 100.0, "h": 105.0, "l": 99.0, "c": 104.0, "v": 1234567},
    {"t": 1778889600000, "o": 104.0, "h": 110.0, "l": 103.0, "c": 108.0, "v": 2234567}
  ]
}
```

- [ ] **Step 2: Add ticker details fixtures**

Create `tests/fixtures/massive/ticker_details_success.json`:

```json
{
  "results": {
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "market": "stocks",
    "primary_exchange": "XNAS",
    "currency_name": "usd",
    "locale": "us",
    "active": true
  }
}
```

Create `tests/fixtures/massive/ticker_details_missing_fields.json`:

```json
{
  "results": {
    "ticker": "AAPL",
    "active": true
  }
}
```

- [ ] **Step 3: Add corporate action fixtures**

Create `tests/fixtures/massive/dividends_success.json`:

```json
{
  "results": [
    {
      "ticker": "AAPL",
      "ex_dividend_date": "2026-05-10",
      "pay_date": "2026-05-20",
      "cash_amount": 0.26,
      "currency": "usd"
    }
  ]
}
```

Create `tests/fixtures/massive/splits_success.json`:

```json
{
  "results": [
    {
      "ticker": "AAPL",
      "execution_date": "2026-05-12",
      "split_from": 1,
      "split_to": 4
    }
  ]
}
```

Create `tests/fixtures/massive/empty_results.json`:

```json
{
  "results": []
}
```

- [ ] **Step 4: Validate fixture JSON**

Run:

```bash
uv run python -m json.tool tests/fixtures/massive/aggregates_daily_success.json
uv run python -m json.tool tests/fixtures/massive/ticker_details_success.json
uv run python -m json.tool tests/fixtures/massive/ticker_details_missing_fields.json
uv run python -m json.tool tests/fixtures/massive/dividends_success.json
uv run python -m json.tool tests/fixtures/massive/splits_success.json
uv run python -m json.tool tests/fixtures/massive/empty_results.json
```

Expected: each command prints formatted JSON and exits 0.

### Task 3: Refactor Massive Tests To Fixtures

**Files:**
- Modify: `tests/test_massive_price_history.py`
- Modify: `tests/test_massive_ticker_details.py`
- Modify: `tests/test_massive_corporate_actions.py`
- Modify: `tests/test_massive_errors.py`

- [ ] **Step 1: Update price-history tests**

In `tests/test_massive_price_history.py`, replace local fake classes with imports:

```python
from tests.massive_fakes import FakeMassiveResponse, FakeMassiveSession, load_massive_fixture
```

Use fixtures in success tests:

```python
session = FakeMassiveSession(FakeMassiveResponse(load_massive_fixture("aggregates_daily_success.json")))
```

- [ ] **Step 2: Update ticker-details tests**

In `tests/test_massive_ticker_details.py`, use:

```python
from tests.massive_fakes import FakeMassiveResponse, FakeMassiveSession, load_massive_fixture

session = FakeMassiveSession(FakeMassiveResponse(load_massive_fixture("ticker_details_success.json")))
```

For missing fields:

```python
session = FakeMassiveSession(FakeMassiveResponse(load_massive_fixture("ticker_details_missing_fields.json")))
```

- [ ] **Step 3: Update corporate-actions tests**

In `tests/test_massive_corporate_actions.py`, use:

```python
from tests.massive_fakes import FakeMassiveResponse, FakeMassiveSession, load_massive_fixture

session = FakeMassiveSession(
    [
        FakeMassiveResponse(load_massive_fixture("dividends_success.json")),
        FakeMassiveResponse(load_massive_fixture("splits_success.json")),
    ]
)
```

For empty responses:

```python
session = FakeMassiveSession(
    [
        FakeMassiveResponse(load_massive_fixture("empty_results.json")),
        FakeMassiveResponse(load_massive_fixture("empty_results.json")),
    ]
)
```

- [ ] **Step 4: Update error tests if useful**

In `tests/test_massive_errors.py`, import `FakeMassiveResponse` and `FakeMassiveSession` from `tests.massive_fakes` if the file still imports them from another test module.

- [ ] **Step 5: Run the refactored Massive unit tests**

Run:

```bash
uv run pytest tests/test_massive_config.py tests/test_massive_price_history.py tests/test_massive_ticker_details.py tests/test_massive_corporate_actions.py tests/test_massive_errors.py -q
```

Expected: PASS and no test makes a live network call.

### Task 4: Full Mocked Adapter Suite Verification

**Files:**
- All files from Tasks 1-3

- [ ] **Step 1: Run full data-provider focused suite**

Run:

```bash
uv run pytest tests/test_massive_config.py tests/test_massive_price_history.py tests/test_massive_ticker_details.py tests/test_massive_corporate_actions.py tests/test_massive_errors.py tests/test_structured_data_entry_points.py tests/test_structured_as_of_contract.py tests/test_data_provider_availability.py tests/test_data_provider_exceptions.py -q
```

Expected: PASS.

- [ ] **Step 2: Run diff hygiene checks**

Run:

```bash
git diff --check
git diff -- tradingagents/dataflows/massive.py tradingagents/dataflows/structured.py tradingagents/dataflows/interface.py
```

Expected: no whitespace errors and no production code diff for this test-suite slice.

- [ ] **Step 3: Inspect expected diff scope**

Run:

```bash
git status --short
git diff -- tests/massive_fakes.py tests/fixtures/massive tests/test_massive_price_history.py tests/test_massive_ticker_details.py tests/test_massive_corporate_actions.py tests/test_massive_errors.py
```

Expected: only test helper, fixture, and Massive test files changed, plus any pre-existing unrelated untracked `.DS_Store` files.

- [ ] **Step 4: Docs drift checkpoint**

Use this exact checkpoint language in the PR or final response:

```text
Docs drift checkpoint: no durable docs update was needed; this slice only consolidates mocked Massive test fixtures and helper code, without changing provider behavior, setup, APIs, schemas, or user-facing workflows.
```

- [ ] **Step 5: Selectively stage and commit**

Run:

```bash
git add tests/massive_fakes.py tests/fixtures/massive tests/test_massive_price_history.py tests/test_massive_ticker_details.py tests/test_massive_corporate_actions.py tests/test_massive_errors.py
git commit -m "test(data): consolidate massive adapter fixtures"
```

Expected: commit succeeds and does not stage unrelated `.DS_Store` files.
