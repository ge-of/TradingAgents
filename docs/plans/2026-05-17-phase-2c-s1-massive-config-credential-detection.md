# Phase 2C-S1 Massive Config And Credential Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Massive provider identity, config alias normalization, and `MASSIVE_API_KEY` detection without making provider API calls.

**Architecture:** Keep this slice below the dataflows boundary. Add a small Massive identity/credential helper module, normalize `polygon` to canonical provider name `massive` in dataflow config, and document optional setup while keeping all provider routers unregistered until later adapter slices.

**Tech Stack:** Python 3.10+, existing `tradingagents.dataflows.config`, existing provider exception hierarchy, pytest, README and `.env.example` docs.

---

## Context To Read First

- `docs/project-architecture-guidelines.md`
- `docs/superpowers/specs/2026-05-15-roadmap-phase-initiative-slice-decomposition.md`
- `docs/superpowers/specs/2026-05-17-phase-2c-s1-massive-config-credential-detection-design.md`
- `tradingagents/default_config.py`
- `tradingagents/dataflows/config.py`
- `tradingagents/dataflows/exceptions.py`
- `tests/test_dataflows_config.py`
- `.env.example`
- `README.md`

## Expected Git Diff Scope

Expected modified or created files:

- Create: `tradingagents/dataflows/massive.py`
- Create: `tests/test_massive_config.py`
- Modify: `tradingagents/dataflows/config.py`
- Modify: `tradingagents/default_config.py`
- Modify: `.env.example`
- Modify: `README.md`

No expected changes:

- `tradingagents/dataflows/interface.py`
- `tradingagents/dataflows/structured.py`
- Any graph, agent, screener, macro, portfolio, IBKR, prompt, or CLI files

## Hard Non-Goals

- Do not make network calls.
- Do not register Massive in `VENDOR_METHODS` or `STRUCTURED_VENDOR_METHODS`.
- Do not implement OHLCV, ticker details, dividends, splits, corporate actions, or error response mapping.
- Do not require `MASSIVE_API_KEY` for default tests.
- Do not broaden into Phase 2D, screener, portfolio, macro, graph, prompts, CLI UX, or IBKR.

### Task 1: Massive Credential Helper

**Files:**
- Create: `tests/test_massive_config.py`
- Create: `tradingagents/dataflows/massive.py`

- [ ] **Step 1: Write failing credential tests**

Create `tests/test_massive_config.py` with:

```python
import pytest

from tradingagents.dataflows.exceptions import ProviderAuthError
from tradingagents.dataflows.massive import MASSIVE_API_KEY_ENV, get_massive_api_key


@pytest.mark.unit
def test_get_massive_api_key_returns_configured_key(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "massive-test-key")

    assert get_massive_api_key() == "massive-test-key"


@pytest.mark.unit
def test_get_massive_api_key_raises_provider_auth_error_when_missing(monkeypatch):
    monkeypatch.delenv(MASSIVE_API_KEY_ENV, raising=False)

    with pytest.raises(ProviderAuthError) as exc_info:
        get_massive_api_key()

    error = exc_info.value
    assert error.provider == "massive"
    assert error.method == "credential_detection"
    assert error.retryable is False
    assert MASSIVE_API_KEY_ENV in error.message
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
uv run pytest tests/test_massive_config.py -q
```

Expected: FAIL because `tradingagents.dataflows.massive` does not exist.

- [ ] **Step 3: Add the minimal Massive helper**

Create `tradingagents/dataflows/massive.py`:

```python
"""Massive provider identity and credential helpers."""

from __future__ import annotations

import os

from .exceptions import ProviderAuthError

MASSIVE_PROVIDER = "massive"
MASSIVE_LEGACY_PROVIDER_ALIASES = {"polygon": MASSIVE_PROVIDER}
MASSIVE_API_KEY_ENV = "MASSIVE_API_KEY"


def normalize_massive_provider_name(provider: str) -> str:
    normalized = provider.strip().lower()
    return MASSIVE_LEGACY_PROVIDER_ALIASES.get(normalized, normalized)


def get_massive_api_key() -> str:
    api_key = os.getenv(MASSIVE_API_KEY_ENV)
    if api_key:
        return api_key

    raise ProviderAuthError(
        f"{MASSIVE_API_KEY_ENV} environment variable is not set.",
        provider=MASSIVE_PROVIDER,
        method="credential_detection",
    )
```

- [ ] **Step 4: Run the credential tests**

Run:

```bash
uv run pytest tests/test_massive_config.py -q
```

Expected: PASS for the credential tests.

### Task 2: Config Alias Normalization

**Files:**
- Modify: `tests/test_massive_config.py`
- Modify: `tradingagents/dataflows/config.py`

- [ ] **Step 1: Add failing alias tests**

Append to `tests/test_massive_config.py`:

```python
import copy

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


@pytest.mark.unit
def test_polygon_alias_normalizes_to_massive_in_data_vendors():
    config_module.set_config({"data_vendors": {"core_stock_apis": "polygon"}})

    assert config_module.get_config()["data_vendors"]["core_stock_apis"] == "massive"


@pytest.mark.unit
def test_polygon_alias_normalizes_inside_comma_separated_fallback_chain():
    config_module.set_config({"data_vendors": {"core_stock_apis": "polygon, yfinance"}})

    assert config_module.get_config()["data_vendors"]["core_stock_apis"] == "massive,yfinance"


@pytest.mark.unit
def test_polygon_alias_normalizes_to_massive_in_tool_vendors():
    config_module.set_config({"tool_vendors": {"get_price_history": "polygon"}})

    assert config_module.get_config()["tool_vendors"]["get_price_history"] == "massive"
```

- [ ] **Step 2: Run the alias tests to verify they fail**

Run:

```bash
uv run pytest tests/test_massive_config.py -q
```

Expected: FAIL because `set_config()` preserves `polygon`.

- [ ] **Step 3: Normalize provider config values in `config.py`**

Modify `tradingagents/dataflows/config.py`:

```python
from copy import deepcopy
from typing import Dict, Optional

import tradingagents.default_config as default_config
from tradingagents.dataflows.massive import normalize_massive_provider_name


def _normalize_provider_chain(value):
    if not isinstance(value, str):
        return value

    providers = [part.strip() for part in value.split(",") if part.strip()]
    if not providers:
        return value
    return ",".join(normalize_massive_provider_name(provider) for provider in providers)


def _normalize_provider_config(config: Dict) -> Dict:
    normalized = deepcopy(config)
    for key in ("data_vendors", "tool_vendors"):
        vendor_map = normalized.get(key)
        if not isinstance(vendor_map, dict):
            continue
        normalized[key] = {
            method_or_category: _normalize_provider_chain(provider_chain)
            for method_or_category, provider_chain in vendor_map.items()
        }
    return normalized
```

Then call `_normalize_provider_config()` inside `set_config()` before merging:

```python
incoming = _normalize_provider_config(config)
```

- [ ] **Step 4: Run config tests**

Run:

```bash
uv run pytest tests/test_massive_config.py tests/test_dataflows_config.py -q
```

Expected: PASS.

### Task 3: Provider Setup Docs

**Files:**
- Modify: `tradingagents/default_config.py`
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Update default config comments**

In `tradingagents/default_config.py`, update the `data_vendors` option comments only:

```python
"core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance, massive
"technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
"fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
"news_data": "yfinance",             # Options: alpha_vantage, yfinance
```

- [ ] **Step 2: Update `.env.example`**

Add below the LLM provider keys:

```dotenv
# Optional market data providers
ALPHA_VANTAGE_API_KEY=
MASSIVE_API_KEY=
```

- [ ] **Step 3: Update README required APIs**

Add Massive below Alpha Vantage in the API key example:

```bash
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage
export MASSIVE_API_KEY=...         # Massive market data
```

Add one short sentence after the block:

```markdown
Massive is optional and remains opt-in through data vendor configuration; `polygon` is accepted as a legacy config alias for `massive`.
```

### Task 4: Verification And Commit

**Files:**
- All files from Tasks 1-3

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run pytest tests/test_massive_config.py tests/test_dataflows_config.py tests/test_data_provider_exceptions.py -q
```

Expected: PASS.

- [ ] **Step 2: Run diff hygiene checks**

Run:

```bash
git diff --check
git diff -- tradingagents/dataflows/interface.py tradingagents/dataflows/structured.py
```

Expected: `git diff --check` prints no errors, and the router/structured diff command prints no diff.

- [ ] **Step 3: Inspect expected diff scope**

Run:

```bash
git status --short
git diff -- tradingagents/dataflows/massive.py tradingagents/dataflows/config.py tradingagents/default_config.py tests/test_massive_config.py README.md .env.example
```

Expected: only the planned files changed, plus any pre-existing unrelated untracked `.DS_Store` files.

- [ ] **Step 4: Docs drift checkpoint**

Use this exact checkpoint language in the PR or final response:

```text
Docs drift checkpoint: README and .env.example now document optional Massive setup and MASSIVE_API_KEY. No architecture or roadmap docs changed because this slice only adds provider identity, alias normalization, and credential detection; it does not add provider calls, router registration, or user-facing behavior.
```

- [ ] **Step 5: Selectively stage and commit**

Run:

```bash
git add tradingagents/dataflows/massive.py tradingagents/dataflows/config.py tradingagents/default_config.py tests/test_massive_config.py README.md .env.example
git commit -m "feat(data): add massive provider identity"
```

Expected: commit succeeds and does not stage unrelated `.DS_Store` files.
