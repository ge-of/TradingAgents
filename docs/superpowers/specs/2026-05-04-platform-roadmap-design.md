# TradingAgents Platform Roadmap — Design Spec

## Overview

Extension of the TradingAgents multi-agent LLM trading framework with five major capabilities: batch multi-ticker analysis, quantitative stock screening, structured macro intelligence, data provider upgrades, and LLM-guided portfolio optimization. The system remains a decision/recommendation engine — no trade execution.

## Build Order

```
Phase 1: Batch Mode          → smallest lift, unlocks everything else
Phase 2: Screener            → quantitative filtering, chains into batch
Phase 2.5: Macro Intelligence → structured macro data + macro analysis agent
Phase 3: Data Provider Swap  → IBKR / Massive.com for data quality
Phase 4: Portfolio Optimizer  → full portfolio management + LLM strategist
```

Each phase is independently shippable.

## Prerequisite: Data Contract Layer

Before Phase 2 (Screener), Phase 2.5 (Macro Intelligence), and Phase 3 (Data Provider Swap) can work, the data layer needs a structural fix. Today, `route_to_vendor()` returns formatted report strings designed for LLM consumption (e.g., `get_fundamentals` returns a prose paragraph, not a dict with `pe_ratio: 12.5`). The screener needs structured numeric data, macro intelligence needs structured time-series snapshots, and new providers need a stable return contract.

**Fix (built as part of Phase 2):** Add a structured data access layer alongside the existing string-returning tools.

- New module: `tradingagents/dataflows/structured.py`
- The existing `@tool`-decorated functions and `route_to_vendor()` string outputs remain unchanged — agents continue to receive report strings.
- The screener, macro layer, portfolio optimizer, and `_fetch_returns()` (which currently imports yfinance directly at `trading_graph.py:191-221`) all use structured contracts instead.
- When new data providers are added in Phase 3, they implement the structured contract directly, and the string-formatting layer wraps them for agent consumption.

This is not a separate phase — it's built incrementally as part of Phases 2 and 3.

### Concrete Schemas

```python
@dataclass
class FundamentalsSnapshot:
    """Structured fundamentals data for a single ticker at a point in time."""
    ticker: str
    as_of: str                          # YYYY-MM-DD
    # Valuation
    market_cap: Optional[float]         # USD
    pe_ratio_trailing: Optional[float]
    pe_ratio_forward: Optional[float]
    price_to_book: Optional[float]
    price_to_sales: Optional[float]
    enterprise_value: Optional[float]   # USD
    # Profitability
    revenue_ttm: Optional[float]        # USD
    net_income_ttm: Optional[float]     # USD
    free_cash_flow: Optional[float]     # USD
    profit_margin: Optional[float]      # decimal (0.15 = 15%)
    roe: Optional[float]               # decimal
    # Balance sheet
    total_debt: Optional[float]         # USD
    total_equity: Optional[float]       # USD
    debt_to_equity: Optional[float]     # ratio
    current_ratio: Optional[float]
    # Dividends
    dividend_yield: Optional[float]     # decimal
    payout_ratio: Optional[float]       # decimal
    # Growth
    revenue_growth_yoy: Optional[float] # decimal
    earnings_growth_yoy: Optional[float] # decimal
    # Derived (computed, not from provider)
    free_cash_flow_yield: Optional[float] # FCF / market_cap

@dataclass
class PriceHistory:
    """OHLCV price history for a ticker."""
    ticker: str
    start: str                          # YYYY-MM-DD
    end: str                            # YYYY-MM-DD
    data: pd.DataFrame                  # columns: Date, Open, High, Low, Close, Volume
    # Derived
    high_52w: Optional[float]
    low_52w: Optional[float]
    proximity_to_52w_high: Optional[float]  # decimal (0.0 = at high, -0.2 = 20% below)

@dataclass
class IndicatorSeries:
    """Technical indicator values for a ticker."""
    ticker: str
    indicator: str                      # e.g. "rsi", "macd"
    as_of: str                          # YYYY-MM-DD
    window: int                         # look-back days
    values: pd.DataFrame                # indicator-specific columns
    latest_value: Optional[float]       # most recent value for simple indicators (RSI, etc.)
```

**Vendor mapping:** Each provider module implements functions that return these schemas. For the initial yfinance implementation in `structured.py`, this means parsing the text output of existing yfinance functions (e.g., extracting `"P/E Ratio (TTM): 28.5"` → `pe_ratio_trailing: 28.5`). For new providers in Phase 3, they return structured data natively and a separate formatting function wraps it into report strings for `VENDOR_METHODS`.

**Missing data:** All numeric fields are `Optional[float]`. When a provider doesn't have a field, it's `None`. Screener filters skip tickers where the filtered field is `None` (logged as a warning).

---

## Phase 1: Batch Mode

### Purpose

Run the existing agent pipeline across multiple tickers in a single invocation, collect structured results, and output a ranked summary.

### Architecture

New module: `tradingagents/batch/runner.py`

**BatchRunner** takes a list of tickers, a date, and a config. It loops over `TradingAgentsGraph.propagate()` for each ticker, collecting results into a `BatchResult` dataclass.

```python
@dataclass
class TickerResult:
    ticker: str
    rating: str                    # Buy | Overweight | Hold | Underweight | Sell
    final_state: Dict[str, Any]
    error: Optional[str] = None    # populated if analysis failed for this ticker

@dataclass
class BatchResult:
    date: str
    results: List[TickerResult]

    def ranked(self) -> List[TickerResult]:
        """Return results ordered Buy > Overweight > Hold > Underweight > Sell."""
        ...

    def buys(self) -> List[TickerResult]:
        """Return only Buy and Overweight results."""
        ...
```

### Design Decisions

- **Sequential execution.** Tickers run one at a time. Parallelism is a future optimization — LLM rate limits and API costs make sequential the safer default.
- **Fault isolation.** If one ticker fails (bad data, LLM error), the error is captured in `TickerResult.error` and the batch continues. No single failure aborts the run.
- **Memory log integration.** Each ticker gets its own memory log entry automatically (existing `propagate()` behavior). No changes needed.
- **Config reuse.** All tickers in a batch share the same config (same LLM provider, models, debate rounds). Per-ticker config overrides are out of scope.

### CLI

```bash
tradingagents batch --tickers AAPL,MSFT,GOOGL,NVDA --date 2026-05-04
```

### Python API

```python
from tradingagents.batch import BatchRunner

runner = BatchRunner(config=config)
results = runner.run(["AAPL", "MSFT", "GOOGL"], "2026-05-04")
for r in results.ranked():
    print(f"{r.ticker}: {r.rating}")
```

### Report Generation

`propagate()` returns `(final_state, rating)` and writes JSON state logs + memory entries, but does not generate markdown reports. The CLI's markdown report generation (`cli/main.py:639-726`) is a separate code path tied to the interactive streaming display.

`BatchRunner` owns its own report generation:
- Extracts key fields from `final_state` (analyst reports, debate summaries, final decision) for each ticker.
- Generates per-ticker markdown summaries and a consolidated multi-ticker ranking table.
- Does not reuse the CLI's `save_report_to_disk()` because batch output is a consolidated multi-ticker report, not single-ticker output. The per-ticker field extraction logic may be shared via a common helper in `tradingagents/batch/report.py`.

### Output

- Consolidated markdown report saved to `~/.tradingagents/logs/batch/<date>/summary.md`
- Per-ticker markdown summaries saved to `~/.tradingagents/logs/batch/<date>/<ticker>.md`
- Per-ticker JSON state logs saved in the existing location (`~/.tradingagents/logs/<ticker>/TradingAgentsStrategy_logs/`) by `propagate()` automatically
- Summary table printed to console with ticker, rating, and key metrics

### Files to Create/Modify

- **Create:** `tradingagents/batch/__init__.py`, `tradingagents/batch/runner.py`, `tradingagents/batch/report.py`
- **Modify:** `cli/main.py` (add `batch` command)

---

## Phase 2: Stock Screener / Value-Buy Finder

### Purpose

Quantitative screening engine that filters a stock universe down to candidates based on configurable fundamental and technical criteria. Optionally chains into batch mode for deep agent analysis of results.

### Architecture

New module: `tradingagents/screener/`

```
tradingagents/screener/
    __init__.py
    screener.py      # Screener class — composes filters, runs against universe
    filters.py       # Individual filter functions
    presets.py       # Pre-built filter combinations
    universes.py     # Built-in ticker lists (S&P 500, NASDAQ 100, etc.)
```

**Screener** pulls data via the new structured data layer (`tradingagents/dataflows/structured.py`), not the string-returning `route_to_vendor()` used by agents. The structured layer calls the same underlying vendor functions but returns typed dicts/DataFrames suitable for numeric filtering. The screener must call `set_config()` before accessing data to ensure the correct vendor is selected (the router reads from a global config singleton in `dataflows/config.py`).

### Filter Design

Filters are composable and config-driven. Each filter is a function that takes a ticker's data dict and returns a boolean pass/fail plus the metric value.

```python
screen = Screener(config=config)
candidates = screen.run(
    universe="sp500",
    date="2026-05-04",              # required — all metrics computed as-of this date
    filters={
        "pe_ratio": {"max": 15},
        "price_to_book": {"max": 1.5},
        "free_cash_flow_yield": {"min": 0.05},
        "debt_to_equity": {"max": 0.5},
    },
    sort_by="free_cash_flow_yield",
    limit=20,
)
```

The `date` parameter is required. All fundamental snapshots, price history, and technical indicators are computed as-of this date to prevent look-ahead bias. When chaining to batch via `--analyze`, the same date is passed through.

**Built-in filters (initial set):**
- P/E ratio (trailing, forward)
- Price-to-book
- Free cash flow yield
- Debt-to-equity
- Dividend yield
- Market cap (min/max)
- Revenue growth (YoY)
- RSI (overbought/oversold)
- 52-week high/low proximity

**Presets:**
- `value` — low P/E, low P/B, high FCF yield, low debt
- `growth` — high revenue growth, moderate P/E
- `dividend` — high dividend yield, low payout ratio
- `momentum` — RSI range, proximity to 52-week high

### Universe Sources

Static ticker lists stored in `screener/universes.py`. Lists are plain Python lists of ticker strings — no external API needed to resolve index membership.

Initial universes: S&P 500, NASDAQ 100, Dow 30. Users can pass a custom list.

### Screener Result Type

```python
@dataclass
class ScreenCandidate:
    ticker: str
    metrics: Dict[str, Optional[float]]  # filter key → value (e.g. {"pe_ratio": 12.3, ...})

@dataclass
class ScreenResult:
    date: str
    universe: str
    filters_applied: Dict[str, Dict]
    candidates: List[ScreenCandidate]    # passing tickers, sorted by sort_by
    skipped: List[Tuple[str, str]]       # (ticker, reason) for tickers with missing data
    
    @property
    def tickers(self) -> List[str]:
        """Convenience: just the ticker symbols."""
        return [c.ticker for c in self.candidates]
```

### Integration with Batch Mode

Screener output plugs directly into `BatchRunner` via the `tickers` property:

```python
candidates = screen.run(universe="sp500", date="2026-05-04", filters={...})
results = runner.run(candidates.tickers, "2026-05-04")
```

### CLI

```bash
tradingagents screen --universe sp500 --date 2026-05-04 --preset value --limit 20
tradingagents screen --universe sp500 --date 2026-05-04 --pe-max 15 --pb-max 1.5 --fcf-yield-min 0.05 --analyze
```

`--date` defaults to today if omitted.

`--analyze` flag chains into batch mode automatically, running the full agent pipeline on screened candidates.

### Output

- Table of candidates with key metrics (P/E, P/B, FCF yield, etc.)
- When `--analyze` is used: full batch analysis report follows
- Saved to `~/.tradingagents/logs/screens/<date>/`

### No LLM Calls

The screener is pure quantitative filtering. LLM-driven screening (where a lightweight agent evaluates each candidate) is a future addition to the roadmap, not part of this phase.

### Files to Create/Modify

- **Create:** `tradingagents/screener/__init__.py`, `screener.py`, `filters.py`, `presets.py`, `universes.py`
- **Create:** `tradingagents/dataflows/structured.py` (structured data access layer — see Prerequisite section)
- **Modify:** `cli/main.py` (add `screen` command)

---

## Phase 2.5: Macro Intelligence Layer

### Purpose

Add structured macroeconomic context to TradingAgents before the broader market-data provider swap. Macro intelligence is data-first: raw macro series are normalized into typed snapshots, deterministic regime labels are computed from those snapshots, and only then does an optional Macro Analyst interpret the regime for a specific ticker. The system remains a recommendation engine, not an economic forecasting or trade-execution system.

### Build Slices

```
Phase 2.5a: Macro Data Contract   → schemas, provider adapters, cache, missing-data semantics
Phase 2.5b: Macro Regime Snapshot → deterministic date/region regime classification
Phase 2.5c: Macro Analyst         → per-ticker LangGraph analyst using the shared snapshot
```

This phase is independently shippable in slices. 2.5a and 2.5b should not require LLM calls. 2.5c adds the LLM-facing analyst node after the data contract is stable.

### Architecture

New module: `tradingagents/macro/`

```
tradingagents/macro/
    __init__.py
    schemas.py          # MacroSeries, MacroIndicatorSnapshot, MacroRegimeSnapshot
    registry.py         # indicator catalog and provider/source mapping
    providers/
        __init__.py
        fred.py
        bls.py
        oecd.py
        imf.py
        ecb.py
        federal_reserve.py
        eia.py
        tradingeconomics.py
        econdb.py
    regime.py           # raw series -> MacroRegimeSnapshot
    cache.py            # ~/.tradingagents/cache/macro/
    report.py           # Markdown rendering for snapshots
```

The macro module owns structured macro data and deterministic regime construction. Agent tools consume rendered macro snapshot reports; they do not call provider APIs directly.

### Data Contract

```python
@dataclass
class MacroObservation:
    date: str
    value: Optional[float]
    is_revised: bool = False
    is_estimate: bool = False


@dataclass
class MacroSeries:
    indicator: str
    provider: str
    region: str
    frequency: str
    units: str
    observations: List[MacroObservation]
    as_of: str


@dataclass
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
    trend: str  # rising | falling | flat | unknown
    stale: bool


@dataclass
class MacroDataAvailability:
    indicator: str
    provider: str
    region: str
    status: str  # available | missing | stale | provider_error | credential_missing
    message: str


@dataclass
class MacroRegimeSnapshot:
    as_of: str
    region: str
    inflation_regime: str      # cooling | sticky | accelerating | unknown
    growth_regime: str         # expanding | slowing | contracting | unknown
    labor_regime: str          # tight | balanced | weakening | unknown
    policy_regime: str         # easing | neutral | restrictive | unknown
    yield_curve_regime: str    # normal | flat | inverted | steepening | unknown
    liquidity_regime: str      # abundant | tightening | stressed | unknown
    energy_regime: str         # benign | rising_pressure | shock | unknown
    risk_flags: List[str]
    indicator_snapshots: Dict[str, MacroIndicatorSnapshot]
    unavailable: List[MacroDataAvailability]
```

All snapshots are date-aware. The `as_of` date is the maximum date the caller is allowed to know, so regime construction must not use later macro observations. Missing or stale data is represented explicitly in `MacroDataAvailability` and in `unknown` regime labels; missing data is not silently ignored.

### Provider/API Strategy

Use OpenBB's macro/economy surface as the reference map for source coverage, but do not add OpenBB as a hard dependency in the first implementation slice. Start with direct, focused adapters and preserve an internal provider-neutral contract.

Initial required adapter:
- `fred` for US macro series and rates.

Initial optional adapters:
- `bls` for CPI, unemployment, and labor detail.
- `eia` for energy inputs.

Later adapters:
- `oecd`, `imf`, `ecb`, `federal_reserve`, `tradingeconomics`, `econdb`.

Representative indicator families:
- Inflation: CPI, core CPI, PCE, inflation expectations.
- Growth: real GDP, industrial production, retail sales, composite leading indicators.
- Labor: unemployment, nonfarm payrolls, participation, wage growth.
- Policy/rates: Fed funds, policy rates, Treasury yields, yield curve spreads.
- Liquidity/financial conditions: money measures, central bank holdings, financial conditions indexes.
- Energy: oil, natural gas, gasoline, electricity, and energy inventory signals.
- Events/documents: economic calendar and FOMC documents as contextual inputs.

Config keys:

```python
"macro_default_region": "US",
"macro_default_provider_chain": {
    "inflation": ["fred", "bls"],
    "growth": ["fred", "oecd", "imf"],
    "labor": ["fred", "bls"],
    "policy": ["fred", "federal_reserve", "ecb"],
    "liquidity": ["fred", "federal_reserve"],
    "energy": ["eia", "fred"],
},
"macro_cache_dir": os.path.join(_TRADINGAGENTS_HOME, "cache", "macro"),
"macro_snapshot_stale_days": 45,
```

Provider credential env vars:
- `FRED_API_KEY`
- `BLS_API_KEY`
- `EIA_API_KEY`
- `TRADINGECONOMICS_API_KEY`

Adapters should normalize transport/auth/rate-limit failures into the shared data-provider error hierarchy planned for Phase 3. A missing credential should produce a `MacroDataAvailability(status="credential_missing")` record when the indicator is optional, and a named error when the requested provider is required.

### Macro Regime Snapshot

`MacroRegimeSnapshot` is the first user-facing product of this phase. It should be deterministic and testable. Regime labels are computed from rolling deltas, year-over-year changes, threshold comparisons, yield-curve spreads, and stale-data checks. No LLM classification is used in 2.5a or 2.5b.

Example usage:

```python
from tradingagents.macro import build_macro_regime_snapshot

snapshot = build_macro_regime_snapshot(
    as_of="2026-05-04",
    region="US",
    config=config,
)
```

The snapshot is shared by:
- Screener presets that choose different filters in restrictive, inflationary, or recession-risk regimes.
- Batch reports that include one macro section for the run date.
- The Macro Analyst node, which turns the shared snapshot into a ticker-specific report.
- The future portfolio optimizer, which can use regime flags when estimating concentration and risk.

### Macro Analyst

The Macro Analyst is a per-ticker LangGraph analyst node added after the macro snapshot contract exists.

New agent module:

```
tradingagents/agents/analysts/macro_analyst.py
```

State and graph changes:
- Add `macro_report` to `AgentState`.
- Add a `macro` analyst selector key.
- Register `create_macro_analyst()` in `tradingagents/agents/__init__.py`.
- Add `Macro Analyst`, `tools_macro`, and `Msg Clear Macro` in `GraphSetup`.
- Add `should_continue_macro()` in `ConditionalLogic`.
- Initialize `macro_report` in `Propagator.create_initial_state()`.

Tool wrapper:

```
tradingagents/agents/utils/macro_data_tools.py
```

Initial tool:
- `get_macro_regime(curr_date, region="US") -> str`

The tool builds or loads a structured snapshot, then returns Markdown from `tradingagents/macro/report.py`. The Macro Analyst prompt interprets the snapshot for the selected ticker/sector: rate sensitivity, inflation sensitivity, growth cyclicality, labor/cost pressure, energy exposure, currency/region exposure, and major macro risks. It does not make final Buy/Sell decisions.

### CLI And Reports

Add macro commands:

```bash
tradingagents macro snapshot --date 2026-05-04 --region US
tradingagents macro report --date 2026-05-04 --region US
```

Add Macro Analyst to the existing interactive analyst selection:

```text
Market Analyst
Sentiment Analyst
News Analyst
Fundamentals Analyst
Macro Analyst
```

Report outputs:
- Macro snapshots saved under `~/.tradingagents/logs/macro/<region>/<date>/`.
- Single-ticker saved reports include `1_analysts/macro.md` when selected.
- Batch summaries can include one shared macro regime section when invoked with macro context.

Batch macro context should be computed once per `(date, region)`, not once per ticker. Per-ticker Macro Analyst runs still happen inside each graph run if the `macro` analyst is selected.

### Testing

- Schema tests for `MacroSeries`, `MacroIndicatorSnapshot`, `MacroDataAvailability`, and `MacroRegimeSnapshot`.
- Provider adapter tests with mocked HTTP payloads, missing credentials, stale data, and no-data responses.
- Cache tests for date/region/provider keying and atomic writes.
- Regime tests for deterministic classification thresholds and no-look-ahead behavior.
- Tool wrapper tests proving `get_macro_regime()` renders Markdown from a structured snapshot.
- Graph tests proving `macro_report` propagates through `AgentState`.
- CLI tests for command registration, date/region validation, and non-interactive output.
- Batch/report tests proving shared macro context appears once and per-ticker failures remain isolated.

### Files to Create/Modify

- **Create:** `tradingagents/macro/__init__.py`, `schemas.py`, `registry.py`, `regime.py`, `cache.py`, `report.py`
- **Create:** `tradingagents/macro/providers/__init__.py`, `fred.py`, `bls.py`, `eia.py`
- **Create:** `tradingagents/agents/analysts/macro_analyst.py`
- **Create:** `tradingagents/agents/utils/macro_data_tools.py`
- **Modify:** `tradingagents/agents/utils/agent_states.py`, `tradingagents/graph/setup.py`, `tradingagents/graph/conditional_logic.py`, `tradingagents/graph/propagation.py`
- **Modify:** `tradingagents/agents/__init__.py`, `cli/models.py`, `cli/utils.py`, `cli/main.py`
- **Modify:** `tradingagents/batch/report.py`, `tradingagents/default_config.py`, `.env.example`

---

## Phase 3: Data Provider Swap

### Purpose

Replace yfinance with higher-quality data sources (IBKR and/or Massive.com) by adding new vendor modules that plug into the existing vendor-routing abstraction.

### Architecture

The existing data layer already supports this pattern. `route_to_vendor()` in `tradingagents/dataflows/interface.py` dispatches tool calls to vendor implementations based on config. Adding a new provider requires:

1. New module implementing the vendor functions
2. Registration in `VENDOR_METHODS`
3. Config switch

### New Modules

**`tradingagents/dataflows/ibkr.py`**

- Implements: `get_ibkr_stock()`, `get_ibkr_indicators()`, `get_ibkr_fundamentals()`, `get_ibkr_news()`, etc.
- Each function implements the structured data contract (returns `FundamentalsSnapshot`, `PriceHistory`, etc. as defined in `structured.py`).
- Separate string-formatting wrappers (e.g., `get_ibkr_stock_report()`) convert structured output to report strings and are registered in `VENDOR_METHODS` for agent consumption via `route_to_vendor()`.
- The structured functions themselves (e.g., `get_ibkr_stock_structured()`) are called directly by the screener and portfolio optimizer, not through `VENDOR_METHODS`.
- Connection via `ib_insync` library. Requires IB Gateway or TWS running locally.
- Module-level connection manager (singleton) handles session lifecycle: connect on first data request, reuse across calls, disconnect on teardown.
- Connection params from env vars: `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`.

**`tradingagents/dataflows/massive.py`**

- Implements the same function signatures.
- REST API with API key auth — stateless HTTP calls.
- Key from env var: `MASSIVE_API_KEY`.

### Registration

```python
# in interface.py VENDOR_METHODS
"get_stock_data": {
    "alpha_vantage": get_alpha_vantage_stock,
    "yfinance": get_YFin_data_online,
    "ibkr": get_ibkr_stock,
    "massive": get_massive_stock,
}
```

### Config

```python
config["data_vendors"] = {
    "core_stock_apis": "ibkr",
    "technical_indicators": "ibkr",
    "fundamental_data": "ibkr",
    "news_data": "massive",  # can mix providers per category
}
```

### Fallback

The existing fallback logic in `route_to_vendor()` only catches `AlphaVantageRateLimitError` (`interface.py:157-162`). This needs broadening:

- Define a base `DataProviderError` exception class in `tradingagents/dataflows/exceptions.py`.
- Each provider wraps its connection/HTTP/auth errors into `DataProviderError` subclasses.
- `route_to_vendor()` catches `DataProviderError` (not just the Alpha Vantage variant) to trigger fallback.
- Provider-specific errors (IBKR disconnect, Massive HTTP 5xx, yfinance rate limit) all inherit from `DataProviderError`.
- **Existing providers must also be updated:** yfinance and Alpha Vantage functions currently catch broad exceptions and return `"Error ..."` strings (e.g., `y_finance.py:301`, `alpha_vantage_indicator.py:220`). These must be changed to raise `DataProviderError` on provider/network/auth failures, reserving return values for successful data or explicit no-data results. This is in scope for Phase 3.

### Direct yfinance Usage

`_fetch_returns()` in `trading_graph.py:191-221` imports yfinance directly for memory reflection, bypassing the data layer. As part of this phase, this call must be routed through the structured data layer so the data provider swap is fully isolated.

### What Doesn't Change

Agent prompts, graph topology, CLI commands, screener, and batch mode. The swap is invisible to everything above the data layer. Tool function signatures stay the same — only the underlying implementations change.

### Files to Create/Modify

- **Create:** `tradingagents/dataflows/ibkr.py`, `tradingagents/dataflows/massive.py`, `tradingagents/dataflows/exceptions.py`
- **Modify:** `tradingagents/dataflows/interface.py` (register new vendors in `VENDOR_METHODS`, broaden fallback to catch `DataProviderError`)
- **Modify:** `tradingagents/dataflows/y_finance.py`, `tradingagents/dataflows/alpha_vantage_*.py` (replace error-string returns with `DataProviderError` raises)
- **Modify:** `tradingagents/graph/trading_graph.py` (route `_fetch_returns()` through structured data layer)
- **Modify:** `tradingagents/macro/providers/*` as needed to have macro adapters use the same shared provider error hierarchy
- **Modify:** `.env.example` (add `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`, `MASSIVE_API_KEY`)

---

## Phase 4: Portfolio Optimizer

### Purpose

Full portfolio management layer that tracks positions, produces allocation recommendations using both quantitative methods and an LLM strategist agent, and suggests rebalancing actions. Decision/recommendation only — no execution.

### Architecture

New module: `tradingagents/portfolio/`

```
tradingagents/portfolio/
    __init__.py
    portfolio.py       # Portfolio class — holdings, cash, weights
    store.py           # Persistence to ~/.tradingagents/portfolio/
    optimizer.py       # Quantitative allocation strategies
    strategist.py      # LLM Portfolio Strategist agent
    schemas.py         # Pydantic models for strategy decisions
```

### 4a. Portfolio State & Persistence

**Portfolio class** tracks:
- Holdings: list of `Position(ticker, shares, avg_cost_basis, current_value)`
- Cash balance
- Computed properties: total value, allocation weights, per-position P&L

**Persistence:**
- Portfolio state: `~/.tradingagents/portfolio/portfolio.json`
- Change history: `~/.tradingagents/portfolio/history.jsonl` (append-only log of every change with timestamp)
- No broker connection — positions are manually declared or imported from CSV/JSON

```python
portfolio = Portfolio(cash=100000)
portfolio.add_position("AAPL", shares=50, cost_basis=185.00)
portfolio.add_position("MSFT", shares=30, cost_basis=420.00)
portfolio.save()
```

### 4b. Quantitative Allocation Engine

**Optimizer** takes batch analysis results plus current portfolio state, produces target allocations.

**Built-in strategies:**
- **Equal weight** — equal allocation across all Buy/Overweight tickers
- **Rating-weighted** — Buy gets 2x the weight of Overweight; Hold/Underweight/Sell excluded
- **Risk parity** — inverse volatility weighting using historical price data from the data layer
- **Mean-variance** — Markowitz optimization using scipy (maximize Sharpe ratio subject to constraints)

**Output:** `RebalanceProposal`
```python
@dataclass
class RebalanceAction:
    ticker: str
    current_weight: float
    target_weight: float
    action: str              # "buy" | "sell" | "hold" | "new" | "exit"
    shares_delta: int
    estimated_cost: float

@dataclass
class RebalanceProposal:
    strategy: str
    actions: List[RebalanceAction]
    expected_portfolio_metrics: Dict  # total value, diversification ratio, etc.
```

### 4c. LLM Portfolio Strategist Agent

**Post-pipeline agent** — runs after batch analysis completes, not inside the per-ticker graph. This is intentionally separate from the existing per-ticker "Portfolio Manager" graph node, which makes a Buy/Hold/Sell decision for a single ticker. The Portfolio Strategist reasons across all tickers simultaneously about allocation, concentration risk, and correlation — a fundamentally different scope.

The per-ticker graph and its state schema (`AgentState` in `agent_states.py`) remain unchanged. The strategist operates on `BatchResult` + `Portfolio` + `RebalanceProposal` as inputs, not on `AgentState`.

**Receives as context:**
- All per-ticker analysis summaries and ratings from the batch run
- Current portfolio state (positions, weights, P&L)
- Quantitative allocation proposal from 4b
- Cross-ticker correlation data (computed from price history via the structured data layer)
- Past portfolio strategy decisions from `~/.tradingagents/portfolio/history.jsonl` (the portfolio-level change log, not the per-ticker `TradingMemoryLog`). The existing per-ticker memory log stores individual trading decisions and reflections; the strategist needs portfolio-level allocation history instead.

**Produces a `StrategyDecision`:**
```python
class TickerAllocation(BaseModel):
    ticker: str
    weight: float
    rationale: str

class RebalanceRecommendation(BaseModel):
    ticker: str
    action: str              # buy | sell | hold | new | exit
    rationale: str

class StrategyDecision(BaseModel):
    allocations: List[TickerAllocation]
    rebalance_actions: List[RebalanceRecommendation]
    portfolio_thesis: str     # overall strategy narrative
    risk_assessment: str      # cross-portfolio risk factors (concentration, correlation, sector exposure)
```

The strategist can override or adjust the quantitative proposal based on qualitative reasoning (e.g., "three of these picks are semiconductor stocks — reduce concentration risk").

### Integration

Chains from the existing pipeline:

```
Screen → Batch Analyze → Quantitative Allocate → LLM Strategist → Report
```

### CLI

```bash
tradingagents portfolio init --cash 100000
tradingagents portfolio add --ticker AAPL --shares 50 --cost-basis 185.00
tradingagents portfolio import --file positions.csv
tradingagents portfolio status
tradingagents portfolio optimize --strategy rating-weighted
tradingagents portfolio optimize --strategy risk-parity --with-strategist
```

### Python API

```python
from tradingagents.portfolio import Portfolio, Optimizer
from tradingagents.portfolio.strategist import PortfolioStrategist

portfolio = Portfolio.load()
results = runner.run(portfolio.tickers + new_candidates, "2026-05-04")

proposal = Optimizer(strategy="risk_parity").optimize(portfolio, results)
decision = PortfolioStrategist(config=config).evaluate(portfolio, results, proposal)
```

### Output

Markdown report with:
- Current portfolio snapshot (positions, weights, P&L)
- Quantitative allocation proposal
- LLM strategist adjustments and reasoning
- Final recommended actions
- Risk assessment

Saved to `~/.tradingagents/portfolio/reports/<date>/`.

### Files to Create/Modify

- **Create:** `tradingagents/portfolio/__init__.py`, `portfolio.py`, `store.py`, `optimizer.py`, `strategist.py`, `schemas.py`
- **Modify:** `cli/main.py` (add `portfolio` command group)

Note: The strategist lives in `tradingagents/portfolio/strategist.py`, not under `tradingagents/agents/`. It is a portfolio-level orchestrator that calls the LLM directly (via `create_llm_client`), not a per-ticker graph node. Existing agents under `tradingagents/agents/` are all per-ticker graph nodes — the strategist is architecturally distinct.

---

## Future Roadmap (Out of Scope)

These items are acknowledged but not designed in this spec:

- **LLM-driven screening** — agent-based filtering where a lightweight LLM evaluates each candidate before full analysis
- **Parallel analyst execution** — run analysts concurrently within the per-ticker graph using LangGraph fan-out
- **Backtesting framework** — replay historical decisions against actual outcomes
- **Additional market data providers** — Polygon.io, IEX Cloud, etc. (same pattern as Phase 3)
- **OpenBB macro adapter** — optional future adapter if direct macro adapters become too costly or OpenBB provides materially better normalization

---

## Cross-Cutting Concerns

### Error Handling

- Batch mode: per-ticker fault isolation, errors captured in results
- Screener: skip tickers with missing data, log warnings
- Macro: represent missing, stale, or credential-limited indicators explicitly in `MacroDataAvailability`
- Data providers: broadened fallback chain in `route_to_vendor()` catches `DataProviderError` base class
- Portfolio: validate positions on load, reject invalid state

### Configuration

All new features use the existing `DEFAULT_CONFIG` pattern. New config keys:
- `batch_save_dir` — where batch reports are saved
- `screener_default_universe` — default universe for screening
- `macro_default_region` — default region for macro snapshots and analyst context
- `macro_default_provider_chain` — provider fallback chain per macro indicator family
- `macro_cache_dir` — where structured macro series and snapshots are cached
- `macro_snapshot_stale_days` — age threshold for stale macro observations
- `portfolio_dir` — where portfolio state is persisted
- `portfolio_optimizer_strategy` — default allocation strategy

### Dependencies

New pip dependencies:
- Phase 1: None
- Phase 2: None
- Phase 2.5: None for the first FRED/BLS/EIA adapters if implemented with `requests`; optional provider-specific SDKs must be justified per adapter
- Phase 3: `ib_insync` (IBKR), `requests` (already present, for Massive.com)
- Phase 4: `scipy` (for mean-variance optimization)
