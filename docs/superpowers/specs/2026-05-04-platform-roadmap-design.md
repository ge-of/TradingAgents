# TradingAgents Platform Roadmap — Design Spec

## Overview

Extension of the TradingAgents multi-agent LLM trading framework with four major features: batch multi-ticker analysis, quantitative stock screening, data provider upgrades, and LLM-guided portfolio optimization. The system remains a decision/recommendation engine — no trade execution.

## Build Order

```
Phase 1: Batch Mode          → smallest lift, unlocks everything else
Phase 2: Screener            → quantitative filtering, chains into batch
Phase 3: Data Provider Swap  → IBKR / Massive.com for data quality
Phase 4: Portfolio Optimizer  → full portfolio management + LLM strategist
```

Each phase is independently shippable.

## Prerequisite: Data Contract Layer

Before Phase 2 (Screener) and Phase 3 (Data Provider Swap) can work, the data layer needs a structural fix. Today, `route_to_vendor()` returns formatted report strings designed for LLM consumption (e.g., `get_fundamentals` returns a prose paragraph, not a dict with `pe_ratio: 12.5`). The screener needs structured numeric data, and new providers need a stable return contract.

**Fix (built as part of Phase 2):** Add a structured data access layer alongside the existing string-returning tools.

- New module: `tradingagents/dataflows/structured.py`
- Provides functions like `get_fundamentals_structured(ticker) -> Dict[str, float]` that call the same underlying vendor functions but parse the results into typed dicts/DataFrames.
- The existing `@tool`-decorated functions and `route_to_vendor()` string outputs remain unchanged — agents continue to receive report strings.
- The screener, portfolio optimizer, and `_fetch_returns()` (which currently imports yfinance directly at `trading_graph.py:191-221`) all use the structured layer instead.
- When new data providers are added in Phase 3, they implement the structured contract directly, and the string-formatting layer wraps them for agent consumption.

This is not a separate phase — it's built incrementally as part of Phases 2 and 3.

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
- Generates per-ticker markdown summaries and a consolidated ranking table.
- Does not reuse the CLI's `save_report_to_disk()` directly — that function expects the interactive streaming state shape.

### Output

- Consolidated markdown report saved to `~/.tradingagents/logs/batch/<date>/summary.md`
- Per-ticker markdown summaries saved to `~/.tradingagents/logs/batch/<date>/<ticker>.md`
- Per-ticker JSON state logs saved in the existing location (`~/.tradingagents/logs/<ticker>/<date>/`) by `propagate()` automatically
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

### Integration with Batch Mode

Screener output is a list of tickers that plugs directly into `BatchRunner`:

```python
candidates = screen.run(universe="sp500", filters={...})
results = runner.run(candidates.tickers, "2026-05-04")
```

### CLI

```bash
tradingagents screen --universe sp500 --preset value --limit 20
tradingagents screen --universe sp500 --pe-max 15 --pb-max 1.5 --fcf-yield-min 0.05 --analyze
```

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
- Each function implements the structured data contract (returns typed dicts/DataFrames matching the schema defined in `structured.py`). A formatting wrapper converts structured output to report strings for agent consumption via the existing `route_to_vendor()` path.
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

### Direct yfinance Usage

`_fetch_returns()` in `trading_graph.py:191-221` imports yfinance directly for memory reflection, bypassing the data layer. As part of this phase, this call must be routed through the structured data layer so the data provider swap is fully isolated.

### What Doesn't Change

Agent prompts, graph topology, CLI commands, screener, and batch mode. The swap is invisible to everything above the data layer. Tool function signatures stay the same — only the underlying implementations change.

### Files to Create/Modify

- **Create:** `tradingagents/dataflows/ibkr.py`, `tradingagents/dataflows/massive.py`, `tradingagents/dataflows/exceptions.py`
- **Modify:** `tradingagents/dataflows/interface.py` (register new vendors in `VENDOR_METHODS`, broaden fallback to catch `DataProviderError`)
- **Modify:** `tradingagents/graph/trading_graph.py` (route `_fetch_returns()` through structured data layer)
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
- Cross-ticker correlation data (computed from price history)
- Past portfolio decisions from memory log

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
- **Create:** `tradingagents/agents/strategist/portfolio_strategist.py`
- **Modify:** `cli/main.py` (add `portfolio` command group)

---

## Future Roadmap (Out of Scope)

These items are acknowledged but not designed in this spec:

- **LLM-driven screening** — agent-based filtering where a lightweight LLM evaluates each candidate before full analysis
- **Parallel analyst execution** — run analysts concurrently within the per-ticker graph using LangGraph fan-out
- **Backtesting framework** — replay historical decisions against actual outcomes
- **Additional data providers** — Polygon.io, IEX Cloud, etc. (same pattern as Phase 3)

---

## Cross-Cutting Concerns

### Error Handling

- Batch mode: per-ticker fault isolation, errors captured in results
- Screener: skip tickers with missing data, log warnings
- Data providers: broadened fallback chain in `route_to_vendor()` catches `DataProviderError` base class
- Portfolio: validate positions on load, reject invalid state

### Configuration

All new features use the existing `DEFAULT_CONFIG` pattern. New config keys:
- `batch_save_dir` — where batch reports are saved
- `screener_default_universe` — default universe for screening
- `portfolio_dir` — where portfolio state is persisted
- `portfolio_optimizer_strategy` — default allocation strategy

### Dependencies

New pip dependencies:
- Phase 1: None
- Phase 2: None
- Phase 3: `ib_insync` (IBKR), `requests` (already present, for Massive.com)
- Phase 4: `scipy` (for mean-variance optimization)
