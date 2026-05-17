# Phase 2C-S7 Optional Live Smoke Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional credential-gated Massive live smoke check that is skipped by default and documented for contributors.

**Architecture:** Add one pytest smoke file using existing `integration` and `smoke` markers. The live test is gated by both `RUN_MASSIVE_LIVE_SMOKE=1` and a non-placeholder `MASSIVE_API_KEY`, and it exercises the public structured Massive price-history path rather than private parser helpers.

**Tech Stack:** Python 3.10+, pytest markers, existing Massive structured adapter, README docs.

---

## Prerequisite State

Start from `main` after Slices `2C-S1` through `2C-S6` are merged. Stop if the mocked Massive adapter suite is not passing.

## Context To Read First

- `docs/project-architecture-guidelines.md`
- `docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md`
- `docs/superpowers/specs/2026-05-17-phase-2c-s7-optional-live-smoke-check-design.md`
- `pyproject.toml`
- `tests/conftest.py`
- `tests/test_deepseek_reasoning.py`
- `tradingagents/dataflows/structured.py`
- `tradingagents/dataflows/massive.py`
- `README.md`

## Expected Git Diff Scope

Expected modified or created files:

- Create: `tests/test_massive_live_smoke.py`
- Modify: `README.md`

No expected changes:

- Massive adapter implementation files, unless a prior slice forgot to export the public structured path
- `pyproject.toml`, because `integration` and `smoke` markers already exist
- CLI, graph, prompts, screener, macro, portfolio, Phase 2D, execution, or IBKR files

## Hard Non-Goals

- Do not make live calls during implementation unless the user explicitly provides credentials and asks for it.
- Do not make live calls in default tests.
- Do not add a CLI command.
- Do not add retries or quota management.
- Do not change adapter behavior.
- Do not broaden into Phase 2D, screener, portfolio, macro, graph, prompts, CLI UX, execution modeling, or IBKR.

### Task 1: Smoke Gate Helper And Skip Behavior

**Files:**
- Create: `tests/test_massive_live_smoke.py`

- [ ] **Step 1: Write skip-gate helper tests**

Create `tests/test_massive_live_smoke.py`:

```python
import os

import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from tradingagents.dataflows import structured
from tradingagents.dataflows.massive import MASSIVE_API_KEY_ENV

RUN_FLAG_ENV = "RUN_MASSIVE_LIVE_SMOKE"


def _massive_live_smoke_enabled() -> bool:
    key = os.environ.get(MASSIVE_API_KEY_ENV, "")
    return os.environ.get(RUN_FLAG_ENV) == "1" and bool(key) and key != "placeholder"


@pytest.mark.unit
def test_massive_live_smoke_disabled_without_flag(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "real-looking-key")
    monkeypatch.delenv(RUN_FLAG_ENV, raising=False)

    assert _massive_live_smoke_enabled() is False


@pytest.mark.unit
def test_massive_live_smoke_disabled_without_real_key(monkeypatch):
    monkeypatch.setenv(RUN_FLAG_ENV, "1")
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "placeholder")

    assert _massive_live_smoke_enabled() is False
```

- [ ] **Step 2: Run skip-gate tests**

Run:

```bash
uv run pytest tests/test_massive_live_smoke.py::test_massive_live_smoke_disabled_without_flag tests/test_massive_live_smoke.py::test_massive_live_smoke_disabled_without_real_key -q
```

Expected: PASS without making network calls.

### Task 2: Optional Live Smoke Test

**Files:**
- Modify: `tests/test_massive_live_smoke.py`

- [ ] **Step 1: Add credential-gated live test**

Append to `tests/test_massive_live_smoke.py`:

```python
@pytest.mark.integration
@pytest.mark.smoke
@pytest.mark.skipif(
    not _massive_live_smoke_enabled(),
    reason="Set RUN_MASSIVE_LIVE_SMOKE=1 and MASSIVE_API_KEY to run the Massive live smoke check",
)
def test_massive_live_price_history_smoke(monkeypatch):
    config = default_config.DEFAULT_CONFIG.copy()
    config["data_vendors"] = {
        **default_config.DEFAULT_CONFIG["data_vendors"],
        "core_stock_apis": "massive",
    }
    config_module.set_config(config)

    result = structured.get_price_history("AAPL", "2026-01-02", "2026-01-05")

    assert result.ticker == "AAPL"
    assert not result.data.empty
    assert result.data["Date"].max() <= "2026-01-05"
```

- [ ] **Step 2: Verify default skip behavior**

Run:

```bash
uv run pytest tests/test_massive_live_smoke.py -q
```

Expected: the two unit helper tests pass and `test_massive_live_price_history_smoke` is skipped unless both `RUN_MASSIVE_LIVE_SMOKE=1` and a non-placeholder `MASSIVE_API_KEY` are set. No live call is made by default.

- [ ] **Step 3: Document the optional live command but do not run it by default**

Do not run this command during implementation unless the user explicitly asks and provides/authorizes credentials:

```bash
RUN_MASSIVE_LIVE_SMOKE=1 MASSIVE_API_KEY=... uv run pytest tests/test_massive_live_smoke.py -q -m "integration and smoke"
```

Expected when authorized with a valid key: the live smoke test either passes with non-empty AAPL price history or fails with a normalized Massive provider error that does not expose the key.

### Task 3: README Provider Smoke Section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add optional Massive smoke docs**

In the provider setup section, add:

````markdown
#### Optional Massive live smoke check

The default test suite uses mocked Massive payloads and does not require provider credentials. To verify real Massive connectivity locally, run the smoke check explicitly:

```bash
RUN_MASSIVE_LIVE_SMOKE=1 MASSIVE_API_KEY=... uv run pytest tests/test_massive_live_smoke.py -q -m "integration and smoke"
```

This command may consume provider quota. Do not enable it in default CI.
````

- [ ] **Step 2: Confirm README diff is limited**

Run:

```bash
git diff -- README.md
```

Expected: only the optional Massive smoke section is added or updated.

### Task 4: Verification And Commit

**Files:**
- All files from Tasks 1-3

- [ ] **Step 1: Run default-safe smoke file verification**

Run:

```bash
uv run pytest tests/test_massive_live_smoke.py -q
```

Expected: two helper tests pass and the live smoke test is skipped unless explicitly enabled. No live network call is made by default.

- [ ] **Step 2: Run mocked Massive regression suite**

Run:

```bash
uv run pytest tests/test_massive_config.py tests/test_massive_price_history.py tests/test_massive_ticker_details.py tests/test_massive_corporate_actions.py tests/test_massive_errors.py tests/test_massive_live_smoke.py -q
```

Expected: mocked tests pass and live smoke remains skipped by default.

- [ ] **Step 3: Run diff hygiene checks**

Run:

```bash
git diff --check
git diff -- tradingagents/dataflows/massive.py tradingagents/dataflows/structured.py tradingagents/dataflows/interface.py pyproject.toml
```

Expected: no whitespace errors and no production or marker config diff for this slice.

- [ ] **Step 4: Inspect expected diff scope**

Run:

```bash
git status --short
git diff -- tests/test_massive_live_smoke.py README.md
```

Expected: only the smoke test and README changed, plus any pre-existing unrelated untracked `.DS_Store` files.

- [ ] **Step 5: Docs drift checkpoint**

Use this exact checkpoint language in the PR or final response:

```text
Docs drift checkpoint: README now documents the optional Massive live smoke command and warns that it is quota-consuming and excluded from default CI. No architecture docs changed because adapter behavior and provider boundaries did not change.
```

- [ ] **Step 6: Selectively stage and commit**

Run:

```bash
git add tests/test_massive_live_smoke.py README.md
git commit -m "test(data): add optional massive live smoke"
```

Expected: commit succeeds and does not stage unrelated `.DS_Store` files.
