---
initiative: trading-platform
phase: 2.5
status: planned
worktree: main
depends_on:
  - docs/superpowers/specs/2026-05-04-platform-roadmap-design.md
---

# Macro Intelligence Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a data-first macro intelligence layer that produces deterministic macro regime snapshots and then exposes them to TradingAgents through CLI commands and a selectable per-ticker Macro Analyst.

**Architecture:** Add a focused `tradingagents/macro/` package for structured macro series, provider adapters, caching, regime classification, and Markdown rendering. Keep provider APIs below the macro contract; the Macro Analyst consumes rendered snapshots through tool wrappers and writes `macro_report` into the existing per-ticker LangGraph state.

**Tech Stack:** Python dataclasses, `requests`, existing `DEFAULT_CONFIG`, Typer/Rich CLI, LangGraph agent wiring, pytest with mocked HTTP and LLM calls.

---

## File Structure

- `tradingagents/macro/schemas.py`: dataclasses for observations, series, indicator snapshots, availability, and regime snapshots.
- `tradingagents/macro/registry.py`: built-in indicator catalog, provider-chain resolution, and region validation.
- `tradingagents/macro/cache.py`: JSON cache under `macro_cache_dir`, keyed by region/provider/indicator/date.
- `tradingagents/macro/providers/fred.py`: first required provider adapter using FRED series observations.
- `tradingagents/macro/providers/bls.py`: optional BLS adapter that returns credential-missing availability until configured.
- `tradingagents/macro/providers/eia.py`: optional EIA adapter that returns credential-missing availability until configured.
- `tradingagents/macro/regime.py`: converts structured series into `MacroRegimeSnapshot` without LLM calls.
- `tradingagents/macro/report.py`: renders snapshots and availability records into Markdown.
- `tradingagents/agents/utils/macro_data_tools.py`: LangChain tool wrappers that render macro snapshots for agents.
- `tradingagents/agents/analysts/macro_analyst.py`: per-ticker analyst node consuming macro tools.
- Existing graph/CLI/report files: add the `macro` analyst selector, `macro_report` state propagation, CLI macro commands, and report output.

## Task 1: Macro Schemas And Markdown Renderer

**Files:**
- Create: `tradingagents/macro/__init__.py`
- Create: `tradingagents/macro/schemas.py`
- Create: `tradingagents/macro/report.py`
- Test: `tests/unit/test_macro_schemas.py`
- Test: `tests/unit/test_macro_report.py`

- [ ] **Step 1: Write the failing schema tests**

Create `tests/unit/test_macro_schemas.py`:

```python
from tradingagents.macro.schemas import (
    MacroDataAvailability,
    MacroIndicatorSnapshot,
    MacroObservation,
    MacroRegimeSnapshot,
    MacroSeries,
)


def test_macro_series_preserves_observations_and_as_of():
    series = MacroSeries(
        indicator="cpi_yoy",
        provider="fred",
        region="US",
        frequency="monthly",
        units="percent",
        observations=[
            MacroObservation(date="2026-03-01", value=3.1),
            MacroObservation(date="2026-04-01", value=3.0),
        ],
        as_of="2026-05-14",
    )

    assert series.indicator == "cpi_yoy"
    assert series.observations[-1].value == 3.0
    assert series.as_of == "2026-05-14"


def test_indicator_snapshot_tracks_trend_and_staleness():
    snapshot = MacroIndicatorSnapshot(
        indicator="fed_funds",
        provider="fred",
        region="US",
        as_of="2026-05-14",
        latest_date="2026-05-01",
        latest_value=4.5,
        previous_value=4.75,
        delta=-0.25,
        yoy_delta=-0.5,
        trend="falling",
        stale=False,
    )

    assert snapshot.trend == "falling"
    assert snapshot.stale is False


def test_regime_snapshot_groups_indicator_data_and_unavailable_records():
    unavailable = MacroDataAvailability(
        indicator="industrial_production",
        provider="fred",
        region="US",
        status="missing",
        message="No observation on or before 2026-05-14.",
    )
    regime = MacroRegimeSnapshot(
        as_of="2026-05-14",
        region="US",
        inflation_regime="cooling",
        growth_regime="slowing",
        labor_regime="balanced",
        policy_regime="restrictive",
        yield_curve_regime="inverted",
        liquidity_regime="tightening",
        energy_regime="benign",
        risk_flags=["yield_curve_inverted"],
        indicator_snapshots={},
        unavailable=[unavailable],
    )

    assert regime.region == "US"
    assert regime.unavailable[0].status == "missing"
    assert "yield_curve_inverted" in regime.risk_flags
```

- [ ] **Step 2: Run schema tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_schemas.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.macro'`.

- [ ] **Step 3: Create schema dataclasses**

Create `tradingagents/macro/schemas.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class MacroObservation:
    date: str
    value: Optional[float]
    is_revised: bool = False
    is_estimate: bool = False


@dataclass(frozen=True)
class MacroSeries:
    indicator: str
    provider: str
    region: str
    frequency: str
    units: str
    observations: List[MacroObservation]
    as_of: str


@dataclass(frozen=True)
class MacroIndicatorSnapshot:
    indicator: str
    provider: str
    region: str
    as_of: str
    latest_date: Optional[str]
    latest_value: Optional[float]
    previous_value: Optional[float]
    delta: Optional[float]
    yoy_delta: Optional[float]
    trend: str
    stale: bool


@dataclass(frozen=True)
class MacroDataAvailability:
    indicator: str
    provider: str
    region: str
    status: str
    message: str


@dataclass(frozen=True)
class MacroRegimeSnapshot:
    as_of: str
    region: str
    inflation_regime: str
    growth_regime: str
    labor_regime: str
    policy_regime: str
    yield_curve_regime: str
    liquidity_regime: str
    energy_regime: str
    risk_flags: List[str] = field(default_factory=list)
    indicator_snapshots: Dict[str, MacroIndicatorSnapshot] = field(default_factory=dict)
    unavailable: List[MacroDataAvailability] = field(default_factory=list)
```

Create `tradingagents/macro/__init__.py`:

```python
from tradingagents.macro.schemas import (
    MacroDataAvailability,
    MacroIndicatorSnapshot,
    MacroObservation,
    MacroRegimeSnapshot,
    MacroSeries,
)

__all__ = [
    "MacroDataAvailability",
    "MacroIndicatorSnapshot",
    "MacroObservation",
    "MacroRegimeSnapshot",
    "MacroSeries",
]
```

- [ ] **Step 4: Run schema tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_schemas.py -v`

Expected: PASS.

- [ ] **Step 5: Write the failing Markdown renderer tests**

Create `tests/unit/test_macro_report.py`:

```python
from tradingagents.macro.report import render_macro_regime_report
from tradingagents.macro.schemas import (
    MacroDataAvailability,
    MacroIndicatorSnapshot,
    MacroRegimeSnapshot,
)


def test_render_macro_regime_report_includes_regime_table_and_indicators():
    snapshot = MacroRegimeSnapshot(
        as_of="2026-05-14",
        region="US",
        inflation_regime="cooling",
        growth_regime="slowing",
        labor_regime="balanced",
        policy_regime="restrictive",
        yield_curve_regime="inverted",
        liquidity_regime="tightening",
        energy_regime="benign",
        risk_flags=["yield_curve_inverted"],
        indicator_snapshots={
            "cpi_yoy": MacroIndicatorSnapshot(
                indicator="cpi_yoy",
                provider="fred",
                region="US",
                as_of="2026-05-14",
                latest_date="2026-04-01",
                latest_value=3.0,
                previous_value=3.1,
                delta=-0.1,
                yoy_delta=-1.0,
                trend="falling",
                stale=False,
            )
        },
        unavailable=[],
    )

    md = render_macro_regime_report(snapshot)

    assert "# Macro Regime Snapshot" in md
    assert "**Region:** US" in md
    assert "| Inflation | cooling |" in md
    assert "| cpi_yoy | fred | 2026-04-01 | 3.0 | falling | No |" in md
    assert "yield_curve_inverted" in md


def test_render_macro_regime_report_includes_unavailable_records():
    snapshot = MacroRegimeSnapshot(
        as_of="2026-05-14",
        region="US",
        inflation_regime="unknown",
        growth_regime="unknown",
        labor_regime="unknown",
        policy_regime="unknown",
        yield_curve_regime="unknown",
        liquidity_regime="unknown",
        energy_regime="unknown",
        risk_flags=[],
        indicator_snapshots={},
        unavailable=[
            MacroDataAvailability(
                indicator="cpi_yoy",
                provider="fred",
                region="US",
                status="credential_missing",
                message="FRED_API_KEY is not set.",
            )
        ],
    )

    md = render_macro_regime_report(snapshot)

    assert "## Data Availability" in md
    assert "credential_missing" in md
    assert "FRED_API_KEY is not set." in md
```

- [ ] **Step 6: Run renderer tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_report.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.macro.report'`.

- [ ] **Step 7: Implement Markdown renderer**

Create `tradingagents/macro/report.py`:

```python
from __future__ import annotations

from tradingagents.macro.schemas import MacroRegimeSnapshot


def _fmt_value(value: object) -> str:
    if value is None:
        return "N/A"
    return str(value)


def _stale_label(stale: bool) -> str:
    return "Yes" if stale else "No"


def render_macro_regime_report(snapshot: MacroRegimeSnapshot) -> str:
    lines = [
        "# Macro Regime Snapshot",
        "",
        f"**Region:** {snapshot.region}",
        f"**As of:** {snapshot.as_of}",
        "",
        "## Regimes",
        "",
        "| Category | Regime |",
        "|----------|--------|",
        f"| Inflation | {snapshot.inflation_regime} |",
        f"| Growth | {snapshot.growth_regime} |",
        f"| Labor | {snapshot.labor_regime} |",
        f"| Policy | {snapshot.policy_regime} |",
        f"| Yield Curve | {snapshot.yield_curve_regime} |",
        f"| Liquidity | {snapshot.liquidity_regime} |",
        f"| Energy | {snapshot.energy_regime} |",
        "",
    ]

    if snapshot.risk_flags:
        lines.extend(["## Risk Flags", ""])
        lines.extend(f"- {flag}" for flag in snapshot.risk_flags)
        lines.append("")

    if snapshot.indicator_snapshots:
        lines.extend(
            [
                "## Indicators",
                "",
                "| Indicator | Provider | Latest Date | Latest Value | Trend | Stale |",
                "|-----------|----------|-------------|--------------|-------|-------|",
            ]
        )
        for indicator, item in sorted(snapshot.indicator_snapshots.items()):
            lines.append(
                f"| {indicator} | {item.provider} | {_fmt_value(item.latest_date)} | "
                f"{_fmt_value(item.latest_value)} | {item.trend} | {_stale_label(item.stale)} |"
            )
        lines.append("")

    if snapshot.unavailable:
        lines.extend(
            [
                "## Data Availability",
                "",
                "| Indicator | Provider | Status | Message |",
                "|-----------|----------|--------|---------|",
            ]
        )
        for item in snapshot.unavailable:
            lines.append(
                f"| {item.indicator} | {item.provider} | {item.status} | {item.message} |"
            )
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 8: Run Task 1 tests**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_schemas.py tests/unit/test_macro_report.py -v`

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

```bash
git add tradingagents/macro/__init__.py tradingagents/macro/schemas.py tradingagents/macro/report.py tests/unit/test_macro_schemas.py tests/unit/test_macro_report.py
git commit -m "feat(macro): add macro schemas and report renderer"
```

## Task 2: Macro Registry, Config Defaults, And Cache

**Files:**
- Create: `tradingagents/macro/registry.py`
- Create: `tradingagents/macro/cache.py`
- Modify: `tradingagents/default_config.py`
- Test: `tests/unit/test_macro_registry.py`
- Test: `tests/unit/test_macro_cache.py`

- [ ] **Step 1: Write failing registry tests**

Create `tests/unit/test_macro_registry.py`:

```python
import pytest

from tradingagents.macro.registry import (
    MacroIndicatorDefinition,
    get_indicator_definition,
    get_provider_chain,
    normalize_region,
)


def test_normalize_region_accepts_known_region_aliases():
    assert normalize_region("us") == "US"
    assert normalize_region("United States") == "US"


def test_normalize_region_rejects_unknown_region():
    with pytest.raises(ValueError, match="Unsupported macro region"):
        normalize_region("moon")


def test_get_indicator_definition_returns_builtin_indicator():
    definition = get_indicator_definition("cpi_yoy")

    assert isinstance(definition, MacroIndicatorDefinition)
    assert definition.family == "inflation"
    assert definition.default_provider == "fred"
    assert definition.provider_series_ids["fred"] == "CPIAUCSL"


def test_get_provider_chain_uses_config_and_keeps_default_provider_last():
    config = {
        "macro_default_provider_chain": {
            "inflation": ["bls", "fred"],
        }
    }

    assert get_provider_chain("cpi_yoy", config) == ["bls", "fred"]
```

- [ ] **Step 2: Run registry tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_registry.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.macro.registry'`.

- [ ] **Step 3: Implement registry**

Create `tradingagents/macro/registry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class MacroIndicatorDefinition:
    indicator: str
    family: str
    frequency: str
    units: str
    default_provider: str
    provider_series_ids: Dict[str, str]


REGION_ALIASES = {
    "US": "US",
    "USA": "US",
    "UNITED_STATES": "US",
    "UNITED STATES": "US",
}


INDICATORS: Dict[str, MacroIndicatorDefinition] = {
    "cpi_yoy": MacroIndicatorDefinition(
        indicator="cpi_yoy",
        family="inflation",
        frequency="monthly",
        units="index",
        default_provider="fred",
        provider_series_ids={"fred": "CPIAUCSL"},
    ),
    "unemployment_rate": MacroIndicatorDefinition(
        indicator="unemployment_rate",
        family="labor",
        frequency="monthly",
        units="percent",
        default_provider="fred",
        provider_series_ids={"fred": "UNRATE"},
    ),
    "fed_funds": MacroIndicatorDefinition(
        indicator="fed_funds",
        family="policy",
        frequency="monthly",
        units="percent",
        default_provider="fred",
        provider_series_ids={"fred": "FEDFUNDS"},
    ),
    "ten_year_treasury": MacroIndicatorDefinition(
        indicator="ten_year_treasury",
        family="policy",
        frequency="daily",
        units="percent",
        default_provider="fred",
        provider_series_ids={"fred": "DGS10"},
    ),
    "two_year_treasury": MacroIndicatorDefinition(
        indicator="two_year_treasury",
        family="policy",
        frequency="daily",
        units="percent",
        default_provider="fred",
        provider_series_ids={"fred": "DGS2"},
    ),
    "real_gdp": MacroIndicatorDefinition(
        indicator="real_gdp",
        family="growth",
        frequency="quarterly",
        units="billions_chained_2017_usd",
        default_provider="fred",
        provider_series_ids={"fred": "GDPC1"},
    ),
    "wti_crude": MacroIndicatorDefinition(
        indicator="wti_crude",
        family="energy",
        frequency="daily",
        units="usd_per_barrel",
        default_provider="fred",
        provider_series_ids={"fred": "DCOILWTICO"},
    ),
}


def normalize_region(region: str) -> str:
    key = region.strip().upper().replace("-", "_")
    normalized = REGION_ALIASES.get(key)
    if normalized is None:
        raise ValueError(f"Unsupported macro region: {region}")
    return normalized


def get_indicator_definition(indicator: str) -> MacroIndicatorDefinition:
    key = indicator.strip().lower()
    if key not in INDICATORS:
        raise ValueError(f"Unsupported macro indicator: {indicator}")
    return INDICATORS[key]


def get_provider_chain(indicator: str, config: dict) -> List[str]:
    definition = get_indicator_definition(indicator)
    configured = config.get("macro_default_provider_chain", {}).get(definition.family, [])
    chain = [provider for provider in configured if provider in definition.provider_series_ids]
    if definition.default_provider not in chain:
        chain.append(definition.default_provider)
    return chain
```

- [ ] **Step 4: Add config defaults**

Modify `tradingagents/default_config.py` inside `DEFAULT_CONFIG` near cache settings:

```python
    "macro_default_region": "US",
    "macro_default_provider_chain": {
        "inflation": ["fred"],
        "growth": ["fred"],
        "labor": ["fred"],
        "policy": ["fred"],
        "liquidity": ["fred"],
        "energy": ["fred"],
    },
    "macro_cache_dir": os.getenv(
        "TRADINGAGENTS_MACRO_CACHE_DIR",
        os.path.join(_TRADINGAGENTS_HOME, "cache", "macro"),
    ),
    "macro_snapshot_stale_days": 45,
```

- [ ] **Step 5: Run registry tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_registry.py -v`

Expected: PASS.

- [ ] **Step 6: Write failing cache tests**

Create `tests/unit/test_macro_cache.py`:

```python
from tradingagents.macro.cache import MacroCache
from tradingagents.macro.schemas import MacroObservation, MacroSeries


def test_cache_round_trips_series(tmp_path):
    cache = MacroCache(tmp_path)
    series = MacroSeries(
        indicator="cpi_yoy",
        provider="fred",
        region="US",
        frequency="monthly",
        units="index",
        observations=[MacroObservation(date="2026-04-01", value=3.0)],
        as_of="2026-05-14",
    )

    cache.write_series(series)
    loaded = cache.read_series("US", "fred", "cpi_yoy", "2026-05-14")

    assert loaded == series


def test_cache_miss_returns_none(tmp_path):
    cache = MacroCache(tmp_path)

    assert cache.read_series("US", "fred", "cpi_yoy", "2026-05-14") is None
```

- [ ] **Step 7: Run cache tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_cache.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.macro.cache'`.

- [ ] **Step 8: Implement JSON cache**

Create `tradingagents/macro/cache.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from tradingagents.macro.schemas import MacroObservation, MacroSeries


class MacroCache:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _series_path(self, region: str, provider: str, indicator: str, as_of: str) -> Path:
        safe_parts = [region.upper(), provider.lower(), indicator.lower()]
        return self.root.joinpath(*safe_parts, f"{as_of}.json")

    def write_series(self, series: MacroSeries) -> Path:
        path = self._series_path(series.region, series.provider, series.indicator, series.as_of)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(asdict(series), indent=2), encoding="utf-8")
        tmp_path.replace(path)
        return path

    def read_series(
        self, region: str, provider: str, indicator: str, as_of: str
    ) -> Optional[MacroSeries]:
        path = self._series_path(region, provider, indicator, as_of)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return MacroSeries(
            indicator=payload["indicator"],
            provider=payload["provider"],
            region=payload["region"],
            frequency=payload["frequency"],
            units=payload["units"],
            observations=[MacroObservation(**item) for item in payload["observations"]],
            as_of=payload["as_of"],
        )
```

- [ ] **Step 9: Run Task 2 tests**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_registry.py tests/unit/test_macro_cache.py -v`

Expected: PASS.

- [ ] **Step 10: Commit Task 2**

```bash
git add tradingagents/default_config.py tradingagents/macro/registry.py tradingagents/macro/cache.py tests/unit/test_macro_registry.py tests/unit/test_macro_cache.py
git commit -m "feat(macro): add registry and cache"
```

## Task 3: FRED Provider And Optional Adapter Stubs

**Files:**
- Create: `tradingagents/macro/providers/__init__.py`
- Create: `tradingagents/macro/providers/fred.py`
- Create: `tradingagents/macro/providers/bls.py`
- Create: `tradingagents/macro/providers/eia.py`
- Test: `tests/unit/test_macro_fred_provider.py`
- Test: `tests/unit/test_macro_optional_providers.py`

- [ ] **Step 1: Write failing FRED provider tests**

Create `tests/unit/test_macro_fred_provider.py`:

```python
from unittest.mock import Mock

from tradingagents.macro.providers.fred import fetch_fred_series


def test_fetch_fred_series_filters_observations_after_as_of(monkeypatch):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "observations": [
            {"date": "2026-03-01", "value": "3.1"},
            {"date": "2026-04-01", "value": "3.0"},
            {"date": "2026-06-01", "value": "2.8"},
            {"date": "2026-02-01", "value": "."},
        ]
    }
    get = Mock(return_value=response)
    monkeypatch.setattr("tradingagents.macro.providers.fred.requests.get", get)

    series = fetch_fred_series(
        indicator="cpi_yoy",
        series_id="CPIAUCSL",
        region="US",
        frequency="monthly",
        units="index",
        as_of="2026-05-14",
        api_key="test-key",
    )

    assert [obs.date for obs in series.observations] == ["2026-03-01", "2026-04-01"]
    assert series.observations[-1].value == 3.0
    assert series.provider == "fred"
    get.assert_called_once()


def test_fetch_fred_series_raises_named_error_for_missing_api_key():
    try:
        fetch_fred_series(
            indicator="cpi_yoy",
            series_id="CPIAUCSL",
            region="US",
            frequency="monthly",
            units="index",
            as_of="2026-05-14",
            api_key="",
        )
    except RuntimeError as exc:
        assert "FRED_API_KEY is not set" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")
```

- [ ] **Step 2: Run FRED tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_fred_provider.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.macro.providers'`.

- [ ] **Step 3: Implement FRED provider**

Create `tradingagents/macro/providers/__init__.py`:

```python
__all__ = []
```

Create `tradingagents/macro/providers/fred.py`:

```python
from __future__ import annotations

from typing import Optional

import requests

from tradingagents.macro.schemas import MacroObservation, MacroSeries


FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"


def _parse_float(value: str) -> Optional[float]:
    if value in ("", "."):
        return None
    return float(value)


def fetch_fred_series(
    *,
    indicator: str,
    series_id: str,
    region: str,
    frequency: str,
    units: str,
    as_of: str,
    api_key: str,
) -> MacroSeries:
    if not api_key:
        raise RuntimeError("FRED_API_KEY is not set.")

    response = requests.get(
        FRED_OBSERVATIONS_URL,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_end": as_of,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    observations = []
    for row in payload.get("observations", []):
        date = row["date"]
        if date > as_of:
            continue
        value = _parse_float(row.get("value", ""))
        if value is None:
            continue
        observations.append(MacroObservation(date=date, value=value))

    return MacroSeries(
        indicator=indicator,
        provider="fred",
        region=region,
        frequency=frequency,
        units=units,
        observations=observations,
        as_of=as_of,
    )
```

- [ ] **Step 4: Run FRED tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_fred_provider.py -v`

Expected: PASS.

- [ ] **Step 5: Write optional provider stub tests**

Create `tests/unit/test_macro_optional_providers.py`:

```python
from tradingagents.macro.providers.bls import describe_bls_unavailable
from tradingagents.macro.providers.eia import describe_eia_unavailable


def test_bls_unavailable_record_names_missing_key():
    record = describe_bls_unavailable("cpi_yoy", "US")

    assert record.provider == "bls"
    assert record.status == "credential_missing"
    assert "BLS_API_KEY" in record.message


def test_eia_unavailable_record_names_missing_key():
    record = describe_eia_unavailable("wti_crude", "US")

    assert record.provider == "eia"
    assert record.status == "credential_missing"
    assert "EIA_API_KEY" in record.message
```

- [ ] **Step 6: Run optional provider tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_optional_providers.py -v`

Expected: FAIL with `ModuleNotFoundError` for BLS/EIA modules.

- [ ] **Step 7: Implement optional provider unavailable records**

Create `tradingagents/macro/providers/bls.py`:

```python
from __future__ import annotations

from tradingagents.macro.schemas import MacroDataAvailability


def describe_bls_unavailable(indicator: str, region: str) -> MacroDataAvailability:
    return MacroDataAvailability(
        indicator=indicator,
        provider="bls",
        region=region,
        status="credential_missing",
        message="BLS_API_KEY is not set.",
    )
```

Create `tradingagents/macro/providers/eia.py`:

```python
from __future__ import annotations

from tradingagents.macro.schemas import MacroDataAvailability


def describe_eia_unavailable(indicator: str, region: str) -> MacroDataAvailability:
    return MacroDataAvailability(
        indicator=indicator,
        provider="eia",
        region=region,
        status="credential_missing",
        message="EIA_API_KEY is not set.",
    )
```

- [ ] **Step 8: Run Task 3 tests**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_fred_provider.py tests/unit/test_macro_optional_providers.py -v`

Expected: PASS.

- [ ] **Step 9: Commit Task 3**

```bash
git add tradingagents/macro/providers tests/unit/test_macro_fred_provider.py tests/unit/test_macro_optional_providers.py
git commit -m "feat(macro): add initial provider adapters"
```

## Task 4: Deterministic Macro Regime Builder

**Files:**
- Create: `tradingagents/macro/regime.py`
- Modify: `tradingagents/macro/__init__.py`
- Test: `tests/unit/test_macro_regime.py`

- [ ] **Step 1: Write failing regime tests**

Create `tests/unit/test_macro_regime.py`:

```python
from tradingagents.macro.regime import (
    build_indicator_snapshot,
    classify_macro_regime,
)
from tradingagents.macro.schemas import MacroObservation, MacroSeries


def _series(indicator, values):
    return MacroSeries(
        indicator=indicator,
        provider="fred",
        region="US",
        frequency="monthly",
        units="percent",
        observations=[
            MacroObservation(date=date, value=value)
            for date, value in values
        ],
        as_of="2026-05-14",
    )


def test_build_indicator_snapshot_uses_latest_observation_on_or_before_as_of():
    series = _series(
        "cpi_yoy",
        [
            ("2026-03-01", 3.2),
            ("2026-04-01", 3.0),
            ("2026-06-01", 2.7),
        ],
    )

    snapshot = build_indicator_snapshot(series, stale_days=45)

    assert snapshot.latest_date == "2026-04-01"
    assert snapshot.latest_value == 3.0
    assert snapshot.previous_value == 3.2
    assert snapshot.delta == -0.2
    assert snapshot.trend == "falling"
    assert snapshot.stale is False


def test_classify_macro_regime_sets_core_regimes_and_risk_flags():
    snapshots = {
        "cpi_yoy": build_indicator_snapshot(_series("cpi_yoy", [("2026-03-01", 3.2), ("2026-04-01", 3.0)]), 45),
        "unemployment_rate": build_indicator_snapshot(_series("unemployment_rate", [("2026-03-01", 4.0), ("2026-04-01", 4.1)]), 45),
        "fed_funds": build_indicator_snapshot(_series("fed_funds", [("2026-03-01", 4.75), ("2026-04-01", 4.75)]), 45),
        "ten_year_treasury": build_indicator_snapshot(_series("ten_year_treasury", [("2026-05-01", 4.0)]), 45),
        "two_year_treasury": build_indicator_snapshot(_series("two_year_treasury", [("2026-05-01", 4.5)]), 45),
        "real_gdp": build_indicator_snapshot(_series("real_gdp", [("2025-12-31", 23000.0), ("2026-03-31", 23100.0)]), 120),
        "wti_crude": build_indicator_snapshot(_series("wti_crude", [("2026-05-01", 75.0), ("2026-05-14", 74.0)]), 14),
    }

    regime = classify_macro_regime("2026-05-14", "US", snapshots, [])

    assert regime.inflation_regime == "cooling"
    assert regime.growth_regime == "expanding"
    assert regime.policy_regime == "restrictive"
    assert regime.yield_curve_regime == "inverted"
    assert "yield_curve_inverted" in regime.risk_flags
```

- [ ] **Step 2: Run regime tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_regime.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.macro.regime'`.

- [ ] **Step 3: Implement regime helpers**

Create `tradingagents/macro/regime.py`:

```python
from __future__ import annotations

from datetime import date
from typing import Dict, List

from tradingagents.macro.schemas import (
    MacroDataAvailability,
    MacroIndicatorSnapshot,
    MacroRegimeSnapshot,
    MacroSeries,
)


def _days_between(left: str, right: str) -> int:
    return (date.fromisoformat(left) - date.fromisoformat(right)).days


def _trend(delta: float | None) -> str:
    if delta is None:
        return "unknown"
    if delta > 0:
        return "rising"
    if delta < 0:
        return "falling"
    return "flat"


def build_indicator_snapshot(
    series: MacroSeries, stale_days: int
) -> MacroIndicatorSnapshot:
    observations = [obs for obs in series.observations if obs.date <= series.as_of and obs.value is not None]
    observations.sort(key=lambda obs: obs.date)
    latest = observations[-1] if observations else None
    previous = observations[-2] if len(observations) >= 2 else None
    latest_value = latest.value if latest else None
    previous_value = previous.value if previous else None
    delta = None
    if latest_value is not None and previous_value is not None:
        delta = round(latest_value - previous_value, 6)
    stale = True
    if latest is not None:
        stale = _days_between(series.as_of, latest.date) > stale_days
    yoy_delta = None
    if latest_value is not None and len(observations) >= 13:
        yoy_delta = round(latest_value - observations[-13].value, 6)
    return MacroIndicatorSnapshot(
        indicator=series.indicator,
        provider=series.provider,
        region=series.region,
        as_of=series.as_of,
        latest_date=latest.date if latest else None,
        latest_value=latest_value,
        previous_value=previous_value,
        delta=delta,
        yoy_delta=yoy_delta,
        trend=_trend(delta),
        stale=stale,
    )


def _inflation_regime(snapshots: Dict[str, MacroIndicatorSnapshot]) -> str:
    cpi = snapshots.get("cpi_yoy")
    if cpi is None or cpi.latest_value is None or cpi.delta is None:
        return "unknown"
    if cpi.latest_value >= 3.0 and cpi.delta > 0:
        return "accelerating"
    if cpi.latest_value >= 3.0:
        return "cooling" if cpi.delta < 0 else "sticky"
    return "cooling"


def _growth_regime(snapshots: Dict[str, MacroIndicatorSnapshot]) -> str:
    gdp = snapshots.get("real_gdp")
    if gdp is None or gdp.delta is None:
        return "unknown"
    if gdp.delta > 0:
        return "expanding"
    if gdp.delta < 0:
        return "contracting"
    return "slowing"


def _labor_regime(snapshots: Dict[str, MacroIndicatorSnapshot]) -> str:
    unemployment = snapshots.get("unemployment_rate")
    if unemployment is None or unemployment.latest_value is None or unemployment.delta is None:
        return "unknown"
    if unemployment.latest_value <= 4.0:
        return "tight"
    if unemployment.delta > 0.2:
        return "weakening"
    return "balanced"


def _policy_regime(snapshots: Dict[str, MacroIndicatorSnapshot]) -> str:
    fed_funds = snapshots.get("fed_funds")
    if fed_funds is None or fed_funds.latest_value is None:
        return "unknown"
    if fed_funds.latest_value >= 4.0:
        return "restrictive"
    if fed_funds.latest_value <= 2.0:
        return "easing"
    return "neutral"


def _yield_curve_regime(snapshots: Dict[str, MacroIndicatorSnapshot]) -> tuple[str, List[str]]:
    ten_year = snapshots.get("ten_year_treasury")
    two_year = snapshots.get("two_year_treasury")
    if ten_year is None or two_year is None:
        return "unknown", []
    if ten_year.latest_value is None or two_year.latest_value is None:
        return "unknown", []
    spread = ten_year.latest_value - two_year.latest_value
    if spread < 0:
        return "inverted", ["yield_curve_inverted"]
    if spread < 0.25:
        return "flat", []
    return "normal", []


def _energy_regime(snapshots: Dict[str, MacroIndicatorSnapshot]) -> str:
    energy = snapshots.get("wti_crude")
    if energy is None or energy.delta is None:
        return "unknown"
    if energy.delta > 5:
        return "shock"
    if energy.delta > 0:
        return "rising_pressure"
    return "benign"


def classify_macro_regime(
    as_of: str,
    region: str,
    indicator_snapshots: Dict[str, MacroIndicatorSnapshot],
    unavailable: List[MacroDataAvailability],
) -> MacroRegimeSnapshot:
    curve_regime, curve_flags = _yield_curve_regime(indicator_snapshots)
    return MacroRegimeSnapshot(
        as_of=as_of,
        region=region,
        inflation_regime=_inflation_regime(indicator_snapshots),
        growth_regime=_growth_regime(indicator_snapshots),
        labor_regime=_labor_regime(indicator_snapshots),
        policy_regime=_policy_regime(indicator_snapshots),
        yield_curve_regime=curve_regime,
        liquidity_regime="unknown",
        energy_regime=_energy_regime(indicator_snapshots),
        risk_flags=curve_flags,
        indicator_snapshots=indicator_snapshots,
        unavailable=unavailable,
    )
```

Modify `tradingagents/macro/__init__.py`:

```python
from tradingagents.macro.regime import build_indicator_snapshot, classify_macro_regime
from tradingagents.macro.schemas import (
    MacroDataAvailability,
    MacroIndicatorSnapshot,
    MacroObservation,
    MacroRegimeSnapshot,
    MacroSeries,
)

__all__ = [
    "MacroDataAvailability",
    "MacroIndicatorSnapshot",
    "MacroObservation",
    "MacroRegimeSnapshot",
    "MacroSeries",
    "build_indicator_snapshot",
    "classify_macro_regime",
]
```

- [ ] **Step 4: Run Task 4 tests**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_regime.py -v`

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add tradingagents/macro/__init__.py tradingagents/macro/regime.py tests/unit/test_macro_regime.py
git commit -m "feat(macro): classify macro regimes"
```

## Task 5: Macro Snapshot Builder And Tool Wrapper

**Files:**
- Modify: `tradingagents/macro/regime.py`
- Create: `tradingagents/agents/utils/macro_data_tools.py`
- Test: `tests/unit/test_macro_snapshot_builder.py`
- Test: `tests/unit/test_macro_data_tools.py`

- [ ] **Step 1: Write failing snapshot builder test**

Create `tests/unit/test_macro_snapshot_builder.py`:

```python
from tradingagents.macro.regime import build_macro_regime_snapshot
from tradingagents.macro.schemas import MacroObservation, MacroSeries


def test_build_macro_regime_snapshot_uses_cache_before_provider(monkeypatch, tmp_path):
    cached = MacroSeries(
        indicator="cpi_yoy",
        provider="fred",
        region="US",
        frequency="monthly",
        units="index",
        observations=[
            MacroObservation(date="2026-03-01", value=3.2),
            MacroObservation(date="2026-04-01", value=3.0),
        ],
        as_of="2026-05-14",
    )
    config = {
        "macro_cache_dir": str(tmp_path),
        "macro_snapshot_stale_days": 45,
        "macro_default_provider_chain": {"inflation": ["fred"]},
    }

    from tradingagents.macro.cache import MacroCache

    MacroCache(tmp_path).write_series(cached)

    def fail_fetch(*args, **kwargs):
        raise AssertionError("Provider should not be called when cache exists")

    monkeypatch.setattr("tradingagents.macro.regime.fetch_fred_series", fail_fetch)

    snapshot = build_macro_regime_snapshot(
        as_of="2026-05-14",
        region="US",
        config=config,
        indicators=["cpi_yoy"],
    )

    assert snapshot.indicator_snapshots["cpi_yoy"].latest_value == 3.0


def test_build_macro_regime_snapshot_records_provider_error(monkeypatch, tmp_path):
    config = {
        "macro_cache_dir": str(tmp_path),
        "macro_snapshot_stale_days": 45,
        "macro_default_provider_chain": {"inflation": ["fred"]},
    }

    def fail_fetch(*args, **kwargs):
        raise RuntimeError("FRED_API_KEY is not set.")

    monkeypatch.setattr("tradingagents.macro.regime.fetch_fred_series", fail_fetch)

    snapshot = build_macro_regime_snapshot(
        as_of="2026-05-14",
        region="US",
        config=config,
        indicators=["cpi_yoy"],
    )

    assert snapshot.inflation_regime == "unknown"
    assert snapshot.unavailable[0].status == "provider_error"
    assert "FRED_API_KEY" in snapshot.unavailable[0].message
```

- [ ] **Step 2: Run snapshot builder tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_snapshot_builder.py -v`

Expected: FAIL with `ImportError` for `build_macro_regime_snapshot`.

- [ ] **Step 3: Implement snapshot builder**

Add this to `tradingagents/macro/regime.py`:

```python
import os

from tradingagents.macro.cache import MacroCache
from tradingagents.macro.providers.fred import fetch_fred_series
from tradingagents.macro.registry import (
    INDICATORS,
    get_indicator_definition,
    get_provider_chain,
    normalize_region,
)
```

Add this function to `tradingagents/macro/regime.py`:

```python
def build_macro_regime_snapshot(
    *,
    as_of: str,
    region: str,
    config: dict,
    indicators: List[str] | None = None,
) -> MacroRegimeSnapshot:
    normalized_region = normalize_region(region)
    selected_indicators = indicators or list(INDICATORS.keys())
    cache = MacroCache(config["macro_cache_dir"])
    stale_days = config.get("macro_snapshot_stale_days", 45)
    snapshots: Dict[str, MacroIndicatorSnapshot] = {}
    unavailable: List[MacroDataAvailability] = []

    for indicator in selected_indicators:
        definition = get_indicator_definition(indicator)
        series = None
        provider_error = None
        for provider in get_provider_chain(indicator, config):
            series = cache.read_series(normalized_region, provider, indicator, as_of)
            if series is not None:
                break
            if provider == "fred":
                try:
                    series = fetch_fred_series(
                        indicator=indicator,
                        series_id=definition.provider_series_ids["fred"],
                        region=normalized_region,
                        frequency=definition.frequency,
                        units=definition.units,
                        as_of=as_of,
                        api_key=os.environ.get("FRED_API_KEY", ""),
                    )
                    cache.write_series(series)
                    break
                except Exception as exc:
                    provider_error = str(exc)
        if series is None:
            unavailable.append(
                MacroDataAvailability(
                    indicator=indicator,
                    provider=definition.default_provider,
                    region=normalized_region,
                    status="provider_error" if provider_error else "missing",
                    message=provider_error or f"No macro series available for {indicator}.",
                )
            )
            continue
        snapshots[indicator] = build_indicator_snapshot(series, stale_days)

    return classify_macro_regime(as_of, normalized_region, snapshots, unavailable)
```

Update `tradingagents/macro/__init__.py` to export `build_macro_regime_snapshot`.

- [ ] **Step 4: Run snapshot builder tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_snapshot_builder.py -v`

Expected: PASS.

- [ ] **Step 5: Write failing macro tool tests**

Create `tests/unit/test_macro_data_tools.py`:

```python
from tradingagents.agents.utils.macro_data_tools import get_macro_regime
from tradingagents.macro.schemas import MacroRegimeSnapshot


def test_get_macro_regime_renders_snapshot(monkeypatch, tmp_path):
    def fake_builder(*, as_of, region, config, indicators=None):
        return MacroRegimeSnapshot(
            as_of=as_of,
            region=region,
            inflation_regime="cooling",
            growth_regime="slowing",
            labor_regime="balanced",
            policy_regime="restrictive",
            yield_curve_regime="inverted",
            liquidity_regime="unknown",
            energy_regime="benign",
            risk_flags=["yield_curve_inverted"],
            indicator_snapshots={},
            unavailable=[],
        )

    monkeypatch.setattr(
        "tradingagents.agents.utils.macro_data_tools.build_macro_regime_snapshot",
        fake_builder,
    )

    result = get_macro_regime.invoke({"curr_date": "2026-05-14", "region": "US"})

    assert "# Macro Regime Snapshot" in result
    assert "| Inflation | cooling |" in result
```

- [ ] **Step 6: Run macro tool tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_data_tools.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.agents.utils.macro_data_tools'`.

- [ ] **Step 7: Implement macro tool wrapper**

Create `tradingagents/agents/utils/macro_data_tools.py`:

```python
from __future__ import annotations

from typing import Annotated, Optional

from langchain_core.tools import tool

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.macro.regime import build_macro_regime_snapshot
from tradingagents.macro.report import render_macro_regime_report


@tool
def get_macro_regime(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    region: Annotated[Optional[str], "Macro region such as US"] = None,
) -> str:
    """Return a rendered macro regime snapshot for the given date and region."""
    config = DEFAULT_CONFIG.copy()
    resolved_region = region or config.get("macro_default_region", "US")
    snapshot = build_macro_regime_snapshot(
        as_of=curr_date,
        region=resolved_region,
        config=config,
    )
    return render_macro_regime_report(snapshot)
```

- [ ] **Step 8: Export macro tool through agent utils**

Modify `tradingagents/agents/utils/agent_utils.py` after the `news_data_tools` import block:

```python
from tradingagents.agents.utils.macro_data_tools import (
    get_macro_regime,
)
```

- [ ] **Step 9: Run Task 5 tests**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_snapshot_builder.py tests/unit/test_macro_data_tools.py -v`

Expected: PASS.

- [ ] **Step 10: Commit Task 5**

```bash
git add tradingagents/macro/__init__.py tradingagents/macro/regime.py tradingagents/agents/utils/agent_utils.py tradingagents/agents/utils/macro_data_tools.py tests/unit/test_macro_snapshot_builder.py tests/unit/test_macro_data_tools.py
git commit -m "feat(macro): build snapshots and agent tool"
```

## Task 6: Macro CLI Commands

**Files:**
- Modify: `cli/main.py`
- Test: `tests/unit/test_macro_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/unit/test_macro_cli.py`:

```python
from typer.testing import CliRunner

from cli.main import app
from tradingagents.macro.schemas import MacroRegimeSnapshot


runner = CliRunner()


def test_macro_report_command_renders_markdown(monkeypatch):
    def fake_builder(*, as_of, region, config, indicators=None):
        return MacroRegimeSnapshot(
            as_of=as_of,
            region=region,
            inflation_regime="cooling",
            growth_regime="slowing",
            labor_regime="balanced",
            policy_regime="restrictive",
            yield_curve_regime="inverted",
            liquidity_regime="unknown",
            energy_regime="benign",
            risk_flags=[],
            indicator_snapshots={},
            unavailable=[],
        )

    monkeypatch.setattr("cli.main.build_macro_regime_snapshot", fake_builder)

    result = runner.invoke(app, ["macro", "report", "--date", "2026-05-14", "--region", "US"])

    assert result.exit_code == 0
    assert "Macro Regime Snapshot" in result.output
    assert "cooling" in result.output


def test_macro_report_rejects_invalid_date():
    result = runner.invoke(app, ["macro", "report", "--date", "bad-date", "--region", "US"])

    assert result.exit_code != 0
    assert "Invalid date format" in result.output
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_cli.py -v`

Expected: FAIL because the `macro` command group is not registered.

- [ ] **Step 3: Implement macro command group**

Modify `cli/main.py` near existing app command definitions:

```python
macro_app = typer.Typer(help="Macro regime snapshots and reports")
app.add_typer(macro_app, name="macro")
```

Add imports near top-level imports:

```python
from tradingagents.macro.regime import build_macro_regime_snapshot
from tradingagents.macro.report import render_macro_regime_report
```

Add helper and command:

```python
def _validate_cli_date(date: str) -> None:
    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        console.print(f"[red]Invalid date format: {date}. Expected YYYY-MM-DD.[/red]")
        raise typer.Exit(1)


@macro_app.command("report")
def macro_report(
    date: str = typer.Option(..., help="Macro snapshot date in YYYY-MM-DD format"),
    region: str = typer.Option("US", help="Macro region, initially US"),
):
    """Render a macro regime report."""
    _validate_cli_date(date)
    config = DEFAULT_CONFIG.copy()
    snapshot = build_macro_regime_snapshot(
        as_of=date,
        region=region,
        config=config,
    )
    console.print(Markdown(render_macro_regime_report(snapshot)))
```

- [ ] **Step 4: Run CLI tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_cli.py -v`

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```bash
git add cli/main.py tests/unit/test_macro_cli.py
git commit -m "feat(macro): add macro report CLI"
```

## Task 7: Macro Analyst Graph Wiring

**Files:**
- Create: `tradingagents/agents/analysts/macro_analyst.py`
- Modify: `tradingagents/agents/__init__.py`
- Modify: `tradingagents/agents/utils/agent_states.py`
- Modify: `tradingagents/graph/conditional_logic.py`
- Modify: `tradingagents/graph/setup.py`
- Modify: `tradingagents/graph/propagation.py`
- Modify: `cli/models.py`
- Modify: `cli/utils.py`
- Modify: `cli/main.py`
- Test: `tests/unit/test_macro_analyst_graph.py`
- Test: `tests/unit/test_macro_analyst_cli_selection.py`

- [ ] **Step 1: Write failing graph wiring tests**

Create `tests/unit/test_macro_analyst_graph.py`:

```python
from unittest.mock import MagicMock

from langgraph.prebuilt import ToolNode

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import GraphSetup


def test_initial_state_contains_macro_report():
    state = Propagator().create_initial_state("AAPL", "2026-05-14")

    assert state["macro_report"] == ""


def test_conditional_logic_routes_macro_tool_calls():
    logic = ConditionalLogic()
    state = {"messages": [MagicMock(tool_calls=[{"name": "get_macro_regime"}])]}

    assert logic.should_continue_macro(state) == "tools_macro"


def test_graph_setup_accepts_macro_analyst():
    llm = MagicMock()
    tool_nodes = {
        "macro": ToolNode([]),
    }
    setup = GraphSetup(
        quick_thinking_llm=llm,
        deep_thinking_llm=llm,
        tool_nodes=tool_nodes,
        conditional_logic=ConditionalLogic(),
    )

    workflow = setup.setup_graph(selected_analysts=["macro"])

    assert workflow is not None
```

- [ ] **Step 2: Run graph wiring tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_analyst_graph.py -v`

Expected: FAIL because `macro_report` and `should_continue_macro` are missing.

- [ ] **Step 3: Add state and routing**

Modify `tradingagents/agents/utils/agent_states.py`:

```python
    macro_report: Annotated[str, "Report from the Macro Analyst"]
```

Place it with other analyst reports after `news_report`.

Modify `tradingagents/graph/propagation.py` inside `create_initial_state()`:

```python
            "macro_report": "",
```

Modify `tradingagents/graph/conditional_logic.py`:

```python
    def should_continue_macro(self, state: AgentState):
        """Determine if macro analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_macro"
        return "Msg Clear Macro"
```

- [ ] **Step 4: Implement Macro Analyst factory**

Create `tradingagents/agents/analysts/macro_analyst.py`:

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_macro_regime,
)


def create_macro_analyst(llm):
    def macro_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])
        tools = [get_macro_regime]
        system_message = (
            "You are a macro analyst. Interpret the structured macro regime snapshot "
            "for the selected instrument. Focus on rates, inflation, growth, labor, "
            "liquidity, energy, currency or region exposure, and sector-specific "
            "macro risks. Do not make the final trading decision. End with a Markdown "
            "table of macro tailwinds, headwinds, and watch items."
            + get_language_instruction()
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant collaborating with other assistants. "
                    "Use the provided tools to progress towards answering the question. "
                    "You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])
        report = ""
        if len(result.tool_calls) == 0:
            report = result.content
        return {
            "messages": [result],
            "macro_report": report,
        }

    return macro_analyst_node
```

Modify `tradingagents/agents/__init__.py`:

```python
from .analysts.macro_analyst import create_macro_analyst
```

Add `"create_macro_analyst"` to `__all__`.

- [ ] **Step 5: Wire Macro Analyst into GraphSetup**

Modify `tradingagents/graph/setup.py` in the analyst creation block:

```python
        if "macro" in selected_analysts:
            analyst_nodes["macro"] = create_macro_analyst(
                self.quick_thinking_llm
            )
            delete_nodes["macro"] = create_msg_delete()
            tool_nodes["macro"] = self.tool_nodes["macro"]
```

Update the docstring options to include:

```python
                - "macro": Macro analyst
```

- [ ] **Step 6: Wire Macro Analyst into tool-node creation**

Modify `tradingagents/graph/trading_graph.py` in `_create_tool_nodes()` after the `news` tool node and before `fundamentals`:

```python
            "macro": ToolNode(
                [
                    get_macro_regime,
                ]
            ),
```

Modify the existing `from tradingagents.agents.utils.agent_utils import (...)` block in `tradingagents/graph/trading_graph.py` to include:

```python
    get_macro_regime,
```

- [ ] **Step 7: Run graph wiring tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_analyst_graph.py -v`

Expected: PASS.

- [ ] **Step 8: Write failing CLI selection tests**

Create `tests/unit/test_macro_analyst_cli_selection.py`:

```python
from cli.models import AnalystType
from cli.utils import ANALYST_ORDER


def test_macro_analyst_type_exists():
    assert AnalystType.MACRO.value == "macro"


def test_macro_analyst_is_selectable():
    choices = {display: value for display, value in ANALYST_ORDER}

    assert choices["Macro Analyst"] == AnalystType.MACRO
```

- [ ] **Step 9: Run CLI selection tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_analyst_cli_selection.py -v`

Expected: FAIL because `AnalystType.MACRO` is missing.

- [ ] **Step 10: Add CLI analyst selection and display mappings**

Modify `cli/models.py`:

```python
    MACRO = "macro"
```

Modify `cli/utils.py`:

```python
    ("Macro Analyst", AnalystType.MACRO),
```

Modify `cli/main.py` mappings:

```python
        "macro": "Macro Analyst",
```

```python
        "macro_report": ("macro", "Macro Analyst"),
```

Add `"macro_report"` to analyst section lists and titles:

```python
                "macro_report": "Macro Analysis",
```

Add saved report handling:

```python
    if final_state.get("macro_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "macro.md").write_text(final_state["macro_report"], encoding="utf-8")
        analyst_parts.append(("Macro Analyst", final_state["macro_report"]))
```

Add display report handling next to other analyst reports:

```python
    if final_state.get("macro_report"):
        analysts.append(("Macro Analyst", final_state["macro_report"]))
```

- [ ] **Step 11: Run Task 7 tests**

Run: `.venv/bin/python -m pytest tests/unit/test_macro_analyst_graph.py tests/unit/test_macro_analyst_cli_selection.py -v`

Expected: PASS.

- [ ] **Step 12: Commit Task 7**

```bash
git add tradingagents/agents/analysts/macro_analyst.py tradingagents/agents/__init__.py tradingagents/agents/utils/agent_states.py tradingagents/graph/conditional_logic.py tradingagents/graph/setup.py tradingagents/graph/propagation.py tradingagents/graph/trading_graph.py cli/models.py cli/utils.py cli/main.py tests/unit/test_macro_analyst_graph.py tests/unit/test_macro_analyst_cli_selection.py
git commit -m "feat(macro): add macro analyst graph node"
```

## Task 8: Batch Report Macro Context

**Files:**
- Modify: `tradingagents/batch/report.py`
- Modify: `tradingagents/batch/runner.py`
- Test: `tests/unit/test_batch_macro_report.py`

- [ ] **Step 1: Write failing batch macro report tests**

Create `tests/unit/test_batch_macro_report.py`:

```python
from tradingagents.batch.report import generate_summary_report
from tradingagents.batch.runner import BatchResult
from tradingagents.macro.schemas import MacroRegimeSnapshot


def test_batch_summary_includes_macro_context_once():
    macro = MacroRegimeSnapshot(
        as_of="2026-05-14",
        region="US",
        inflation_regime="cooling",
        growth_regime="slowing",
        labor_regime="balanced",
        policy_regime="restrictive",
        yield_curve_regime="inverted",
        liquidity_regime="unknown",
        energy_regime="benign",
        risk_flags=["yield_curve_inverted"],
        indicator_snapshots={},
        unavailable=[],
    )
    batch = BatchResult(date="2026-05-14", results=[], macro_snapshot=macro)

    md = generate_summary_report(batch)

    assert md.count("# Macro Regime Snapshot") == 1
    assert "yield_curve_inverted" in md
```

- [ ] **Step 2: Run batch macro report tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_batch_macro_report.py -v`

Expected: FAIL because `BatchResult` does not accept `macro_snapshot`.

- [ ] **Step 3: Add optional macro snapshot to BatchResult**

Modify `tradingagents/batch/runner.py`:

```python
from tradingagents.macro.schemas import MacroRegimeSnapshot
```

Update `BatchResult`:

```python
@dataclass
class BatchResult:
    date: str
    results: List[TickerResult] = field(default_factory=list)
    macro_snapshot: Optional[MacroRegimeSnapshot] = None
```

Update `BatchRunner.run()` signature:

```python
        macro_snapshot: Optional[MacroRegimeSnapshot] = None,
```

Initialize the batch with:

```python
        batch = BatchResult(date=date, macro_snapshot=macro_snapshot)
```

- [ ] **Step 4: Render macro context in batch summary**

Modify `tradingagents/batch/report.py`:

```python
from tradingagents.macro.report import render_macro_regime_report
```

Inside `generate_summary_report()` after the header block:

```python
    if batch.macro_snapshot is not None:
        lines.append("## Shared Macro Context")
        lines.append("")
        lines.append(render_macro_regime_report(batch.macro_snapshot))
        lines.append("")
```

- [ ] **Step 5: Run batch macro report tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_batch_macro_report.py -v`

Expected: PASS.

- [ ] **Step 6: Commit Task 8**

```bash
git add tradingagents/batch/runner.py tradingagents/batch/report.py tests/unit/test_batch_macro_report.py
git commit -m "feat(batch): include shared macro context"
```

## Task 9: Environment Docs And Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-05-04-platform-roadmap-design.md` if implementation changes architecture details from the spec

- [ ] **Step 1: Add environment examples**

Modify `.env.example`:

```dotenv
# Macro data providers
FRED_API_KEY=
BLS_API_KEY=
EIA_API_KEY=
TRADINGECONOMICS_API_KEY=

# Macro cache override
TRADINGAGENTS_MACRO_CACHE_DIR=
```

- [ ] **Step 2: Add README macro usage**

Add a concise README section:

````markdown
### Macro Regime Reports

TradingAgents can build a deterministic macro regime snapshot for a date and region:

```bash
tradingagents macro report --date 2026-05-14 --region US
```

The first implementation uses structured macro series through provider adapters, starting with FRED. Optional provider keys such as `BLS_API_KEY` and `EIA_API_KEY` enable broader coverage as adapters are added.
````

- [ ] **Step 3: Run focused macro and batch tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_macro_schemas.py \
  tests/unit/test_macro_report.py \
  tests/unit/test_macro_registry.py \
  tests/unit/test_macro_cache.py \
  tests/unit/test_macro_fred_provider.py \
  tests/unit/test_macro_optional_providers.py \
  tests/unit/test_macro_regime.py \
  tests/unit/test_macro_snapshot_builder.py \
  tests/unit/test_macro_data_tools.py \
  tests/unit/test_macro_cli.py \
  tests/unit/test_macro_analyst_graph.py \
  tests/unit/test_macro_analyst_cli_selection.py \
  tests/unit/test_batch_macro_report.py \
  -v
```

Expected: PASS.

- [ ] **Step 4: Run adjacent existing tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_batch_runner.py \
  tests/unit/test_batch_report.py \
  tests/unit/test_batch_cli.py \
  tests/test_env_overrides.py \
  tests/test_structured_agents.py \
  -v
```

Expected: PASS.

- [ ] **Step 5: Documentation drift checkpoint**

Check whether implementation changed any of these durable contracts:

- Agent graph topology
- AgentState fields
- CLI command family
- Config keys or env vars
- Data provider error handling
- Report output shape

If the implementation differs from the design spec, update `docs/superpowers/specs/2026-05-04-platform-roadmap-design.md` in the same task. If the implementation matches, write this in the PR self-review: "Docs drift checkpoint: roadmap spec already covers macro data contract, Macro Analyst graph integration, CLI commands, config keys, and report outputs; no additional durable docs changes needed."

- [ ] **Step 6: Commit Task 9**

```bash
git add .env.example README.md docs/superpowers/specs/2026-05-04-platform-roadmap-design.md
git commit -m "docs(macro): document macro configuration and usage"
```

## Final Verification

- [ ] **Run full test suite**

Run: `.venv/bin/python -m pytest -v`

Expected: PASS, excluding tests that explicitly require live provider credentials.

- [ ] **Inspect git history**

Run: `git log --oneline --max-count=12`

Expected: macro work is split into focused commits matching the task boundaries.

- [ ] **Inspect working tree**

Run: `git status --short --branch`

Expected: clean except unrelated pre-existing local files such as `.DS_Store`.

## Execution Notes

- Keep 2.5a and 2.5b deterministic. No LLM calls belong in schema, provider, cache, or regime tests.
- Do not make the Macro Analyst fetch provider APIs directly. It must call `get_macro_regime()`, which renders a structured snapshot.
- Do not add OpenBB as a dependency in this implementation. The source list is OpenBB-inspired, but this plan starts with focused direct adapters.
- Preserve the recommendation-engine boundary. Macro reports inform decisions; they do not place trades or claim forecast certainty.
