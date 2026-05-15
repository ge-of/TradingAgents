# TradingAgents Roadmap Phase / Initiative / Slice Decomposition

## Purpose

This document decomposes the platform roadmap into product phases, architecture-owned initiatives, and PR-sized implementation slices. It is the durable planning layer between the high-level roadmap spec and task-level implementation plans.

The current strategic shift is **data layer first**: prove structured provider contracts and the Massive/Polygon adapter before building screener, macro, or portfolio features on top of them.

## Decomposition Model

```text
Phase
  Initiative
    Slice
      Goal
      Scope
      Non-goals
      Tests
      Docs checkpoint
      Exit criteria
```

Use phases for product capabilities, initiatives for architectural boundaries, and slices for independently testable implementation increments. Every slice should be small enough to review and merge without requiring future slices to prove it works.

## Slice Rules

1. One architecture boundary per slice.
2. Every slice must be independently testable.
3. Data contracts ship before LLM-facing agents consume the data.
4. Graph topology changes are isolated slices.
5. Cross-ticker orchestration stays outside the per-ticker graph.
6. Each slice ends with a documentation drift checkpoint.
7. Credentialed/live-provider work needs mocked verification plus an optional live-smoke command.

## Phase 1: Batch Mode

Batch mode is already present as `tradingagents/batch/`. This phase now focuses on confirming the shipped baseline and closing narrow polish gaps.

### Initiative 1A: Batch Shipped Baseline

#### Slice 1A-S1: Confirm Current Batch Behavior And Tests

Goal: Establish the current batch implementation as a known baseline before adding data-layer dependencies.

Scope:
- Review `tradingagents/batch/runner.py`, `tradingagents/batch/report.py`, and `cli/main.py`.
- Run focused batch tests.
- Record any behavior gaps as future slices rather than changing code opportunistically.

Non-goals:
- No provider changes.
- No screener or macro integration.

Tests:
- `tests/unit/test_batch_runner.py`
- `tests/unit/test_batch_report.py`
- `tests/unit/test_batch_cli.py`
- `tests/unit/test_batch_integration.py`

Docs checkpoint:
- Update roadmap status if the baseline differs from the spec.

Exit criteria:
- Batch behavior and remaining gaps are explicit.

#### Slice 1A-S2: Close Report/CLI Polish Gaps

Goal: Fix narrow batch UX or report issues found in Slice 1A-S1.

Scope:
- Batch-only CLI validation.
- Batch-only report formatting.
- Batch-only path safety or fault isolation defects.

Non-goals:
- No new data providers.
- No parallel execution.
- No screener chaining changes.

Tests:
- Focused batch CLI/report tests for each fixed behavior.

Docs checkpoint:
- Update batch report/CLI examples if user-visible behavior changes.

Exit criteria:
- Batch remains a stable wrapper over `TradingAgentsGraph.propagate()`.

## Phase 2: Data Layer Foundation

Phase 2 is the next execution focus. It creates the structured data and provider foundation that Screener, Macro Intelligence, and Portfolio Optimizer need. Massive is implemented before IBKR because it is stateless HTTP, easier to mock, and proves the provider contract without local gateway setup.

### Initiative 2A: Provider Error And Availability Contract

#### Slice 2A-S1: DataProviderError Hierarchy

Goal: Create a shared provider error hierarchy for fallback and user-visible diagnostics.

Scope:
- Add `tradingagents/dataflows/exceptions.py`.
- Define `DataProviderError`, `ProviderRateLimitError`, `ProviderAuthError`, `ProviderUnavailableError`, and `ProviderNoDataError`.
- Keep existing agent-facing tool signatures unchanged.

Non-goals:
- No provider adapter rewrite.
- No router fallback behavior change yet.

Tests:
- Unit tests for exception attributes and string messages.

Docs checkpoint:
- Add provider error contract to roadmap and architecture docs if implementation changes the expected boundary.

Exit criteria:
- Provider code has a shared error vocabulary available.

#### Slice 2A-S2: Explicit No-Data Vs Provider-Error Semantics

Goal: Separate valid no-data results from provider/network/auth failures.

Scope:
- Define no-data conventions for structured data functions.
- Document which situations raise `ProviderNoDataError` versus return empty structured data.
- Add helper functions if needed for provider adapters.

Non-goals:
- No Massive adapter yet.
- No broad yfinance/Alpha Vantage rewrite beyond tests/helpers needed for the contract.

Tests:
- Contract tests for no-data and provider-error handling.

Docs checkpoint:
- Update roadmap error-handling section if semantics differ from the current spec.

Exit criteria:
- Future adapters can implement the same failure contract consistently.

#### Slice 2A-S3: Router Fallback Contract Tests

Goal: Prove `route_to_vendor()` fallback behavior for shared provider errors.

Scope:
- Add tests showing `DataProviderError` triggers fallback.
- Preserve existing Alpha Vantage rate-limit fallback behavior.
- Keep agent tool signatures unchanged.

Non-goals:
- No provider-specific adapter work.

Tests:
- Mocked router tests for primary failure, fallback success, and all providers failing.

Docs checkpoint:
- Update architecture guidelines only if fallback behavior becomes a project-wide extension rule.

Exit criteria:
- Router fallback is no longer Alpha-Vantage-specific.

### Initiative 2B: Structured Equity Data Contract

#### Slice 2B-S1: Structured Equity Schemas

Goal: Define the typed data contracts consumed by Screener and Portfolio Optimizer.

Scope:
- Create structured equity schema module.
- Add `FundamentalsSnapshot`, `PriceHistory`, `IndicatorSeries`, and availability metadata.
- Preserve string/report tool outputs separately.

Non-goals:
- No provider implementation.
- No screener filters.

Tests:
- Dataclass/schema tests.
- Serialization tests if cache/report code needs it.

Docs checkpoint:
- Keep schema names aligned with the roadmap spec.

Exit criteria:
- Structured equity types are importable and tested.

#### Slice 2B-S2: Structured Data Entry Points

Goal: Create provider-neutral functions for structured price, fundamentals, and indicators.

Scope:
- Add structured data module entry points.
- Route through config/provider selection.
- Return typed structures or provider errors.

Non-goals:
- No Massive implementation yet beyond placeholder dispatch.
- No CLI changes.

Tests:
- Entry-point tests with fake provider functions.
- Config isolation tests.

Docs checkpoint:
- Update architecture guidelines if a new module ownership rule is needed.

Exit criteria:
- Callers can depend on stable structured data APIs.

#### Slice 2B-S3: No-Look-Ahead / As-Of Contract Tests

Goal: Make date handling a first-class data contract.

Scope:
- Add tests proving structured data ignores observations after `as_of`.
- Define default date behavior for each structured entry point.
- Ensure invalid dates fail before provider calls.

Non-goals:
- No screener implementation.

Tests:
- As-of filtering tests.
- Invalid-date tests.

Docs checkpoint:
- Add no-look-ahead expectations to durable docs if not already covered.

Exit criteria:
- Structured data cannot accidentally include future observations.

#### Slice 2B-S4: Structured-To-Markdown Formatting Boundary

Goal: Preserve agent-facing prose tools while structured callers use typed data.

Scope:
- Add formatters that render structured data into existing report-style Markdown.
- Keep `route_to_vendor()` callers receiving strings.

Non-goals:
- No prompt rewrites.
- No graph topology changes.

Tests:
- Formatter tests.
- Existing tool-wrapper tests still pass.

Docs checkpoint:
- Update roadmap if report shape changes.

Exit criteria:
- Structured and prose data paths have a clear conversion boundary.

### Initiative 2C: Massive/Polygon Market Data Adapter

#### Slice 2C-S1: Massive Config And Credential Detection

Goal: Add Massive as the first new data provider identity.

Scope:
- Add `MASSIVE_API_KEY` support.
- Add provider config names using `massive`.
- Optionally accept `polygon` as a legacy alias in config normalization.

Non-goals:
- No API calls yet.
- No IBKR work.

Tests:
- Missing-key tests name `MASSIVE_API_KEY`.
- Config alias tests if `polygon` is supported.

Docs checkpoint:
- Update `.env.example` and README provider setup docs.

Exit criteria:
- Provider selection can identify Massive without making network calls.

#### Slice 2C-S2: Massive Historical Aggregates / OHLCV Adapter

Goal: Fetch and normalize historical OHLCV data from Massive.

Scope:
- Implement historical aggregates adapter with `requests`.
- Normalize to `PriceHistory`.
- Respect `as_of` and date range boundaries.

Non-goals:
- No fundamentals.
- No screener filters.

Tests:
- Mocked HTTP response parsing.
- Rate-limit/auth/server-error normalization.
- No-look-ahead tests.

Docs checkpoint:
- Document optional live smoke command gated by `MASSIVE_API_KEY`.

Exit criteria:
- A mocked Massive-backed structured price-history path passes tests.

#### Slice 2C-S3: Massive Ticker Reference / Details Adapter

Goal: Normalize Massive ticker metadata needed by future screeners and reports.

Scope:
- Add reference/details parsing for ticker name, market, exchange, currency, locale, and active status.
- Return explicit missing-field availability records.

Non-goals:
- No universe membership API dependency.
- No fundamentals parser.

Tests:
- Mocked reference response tests.
- Missing-field tests.

Docs checkpoint:
- Update structured data contract if metadata fields become formal schemas.

Exit criteria:
- Ticker metadata can be fetched and normalized independently.

#### Slice 2C-S4: Dividends, Splits, And Corporate Actions

Goal: Normalize corporate actions that affect historical analysis and screening.

Scope:
- Add dividend and split structured outputs.
- Preserve path for adjusted/unadjusted price semantics.

Non-goals:
- No portfolio tax-lot logic.
- No execution modeling.

Tests:
- Mocked dividends/splits parsing.
- Empty response/no-data behavior.

Docs checkpoint:
- Document adjusted price assumptions.

Exit criteria:
- Corporate action data is available to future screeners and portfolio metrics.

#### Slice 2C-S5: Provider Error / Rate-Limit Normalization

Goal: Ensure Massive errors participate in the shared provider contract.

Scope:
- Map HTTP 401/403, 429, 5xx, malformed responses, and timeouts to provider errors.
- Include safe diagnostic messages without exposing secrets.

Non-goals:
- No retry policy beyond what is explicitly designed.

Tests:
- Mocked HTTP status tests.
- Timeout tests.

Docs checkpoint:
- Update provider setup troubleshooting if needed.

Exit criteria:
- Massive adapter failures are deterministic and testable.

#### Slice 2C-S6: Mocked Adapter Test Suite

Goal: Consolidate adapter coverage before any live smoke test.

Scope:
- Run full mocked Massive adapter test set.
- Add fixtures for common Massive payloads.

Non-goals:
- No live network requirement.

Tests:
- Full Massive unit suite.

Docs checkpoint:
- None unless fixture behavior documents a durable contract.

Exit criteria:
- Adapter behavior is proven without credentials.

#### Slice 2C-S7: Optional Live Smoke Check

Goal: Provide an honest credential-gated check for real Massive connectivity.

Scope:
- Add a smoke command or documented pytest marker that runs only when `MASSIVE_API_KEY` is present.
- Keep it out of default CI.

Non-goals:
- No CI dependency on paid/provider quota.

Tests:
- Skip behavior without key.
- Live check documented but optional.

Docs checkpoint:
- README provider smoke section.

Exit criteria:
- Contributors can verify real provider connectivity without making the default suite flaky.

### Initiative 2D: Massive/Polygon Fundamentals Adapter

#### Slice 2D-S1: Financial Statement Response Parser

Goal: Normalize Massive financial statement responses into structured snapshots.

Scope:
- Parse balance sheet, income statement, and cashflow fields available from Massive.
- Preserve fiscal period and filing date metadata.

Non-goals:
- No derived ratios yet.

Tests:
- Mocked financial statement payload tests.
- Missing statement tests.

Docs checkpoint:
- Document statement coverage limits.

Exit criteria:
- Financial statement data can populate `FundamentalsSnapshot` inputs.

#### Slice 2D-S2: Ratios And Derived Metric Normalization

Goal: Compute or normalize ratios needed by screeners.

Scope:
- P/E, P/B, P/S, debt-to-equity, free-cash-flow yield, dividend yield where data allows.
- Mark unavailable fields explicitly.

Non-goals:
- No valuation model.

Tests:
- Derived metric tests.
- Missing denominator tests.

Docs checkpoint:
- Document derived metric formulas.

Exit criteria:
- Value/growth/dividend screeners have typed metric inputs.

#### Slice 2D-S3: Missing-Field Availability Records

Goal: Make partial fundamentals responses safe for downstream filters.

Scope:
- Add availability metadata for fields missing from provider responses.
- Ensure screeners can distinguish missing data from a failed provider call.

Non-goals:
- No imputation.

Tests:
- Missing-field availability tests.

Docs checkpoint:
- Update missing-data semantics if needed.

Exit criteria:
- Downstream code can skip or warn on missing fields deterministically.

#### Slice 2D-S4: Fundamentals Structured Contract Tests

Goal: Lock the fundamentals contract before screener work starts.

Scope:
- Run focused structured fundamentals suite.
- Include provider success, no-data, partial-data, and error cases.

Non-goals:
- No screener presets.

Tests:
- Full structured fundamentals suite.

Docs checkpoint:
- Roadmap docs should be current before moving into Phase 3.

Exit criteria:
- Screener implementation can rely on structured fundamentals.

### Initiative 2E: Provider Routing And Internal Adoption

#### Slice 2E-S1: Register Massive Provider In Router/Config

Goal: Make Massive available through existing provider configuration.

Scope:
- Register Massive report wrappers in `VENDOR_METHODS`.
- Add default config examples.
- Keep yfinance as default unless explicitly changed.

Non-goals:
- No user-facing default provider switch unless separately approved.

Tests:
- Router registration tests.
- Tool-level provider override tests.

Docs checkpoint:
- README and `.env.example` provider setup.

Exit criteria:
- Users can opt into Massive through config.

#### Slice 2E-S2: Tool-Level Fallback Chain Tests

Goal: Prove category-level and tool-level fallbacks across providers.

Scope:
- Tests for primary Massive failure falling back to yfinance/Alpha Vantage where supported.
- Tests for unsupported provider names.

Non-goals:
- No live provider calls.

Tests:
- Mocked routing tests.

Docs checkpoint:
- Update provider fallback docs if behavior is user-visible.

Exit criteria:
- Fallback behavior is deterministic and documented.

#### Slice 2E-S3: Route `_fetch_returns()` Through Structured Data

Goal: Remove the graph's direct yfinance dependency for reflection return lookup.

Scope:
- Replace direct `yfinance` call in graph return fetch with structured price history.
- Preserve memory reflection behavior and labels.

Non-goals:
- No memory schema redesign.

Tests:
- Mocked return calculation tests.
- Benchmark fallback tests.

Docs checkpoint:
- Update architecture guidelines only if graph/data boundary wording changes.

Exit criteria:
- Graph internals no longer bypass structured data for returns.

#### Slice 2E-S4: Provider Setup Docs

Goal: Make Massive setup explicit without turning docs into a session log.

Scope:
- `.env.example`
- README provider setup
- Optional live smoke command documentation

Non-goals:
- No long provider comparison matrix.

Tests:
- Documentation-only; run markdown/diff checks if available.

Docs checkpoint:
- This slice is the checkpoint.

Exit criteria:
- A new user can configure Massive from durable docs.

#### Slice 2E-S5: Architecture Boundary Checkpoint

Goal: Close Phase 2 with architectural docs aligned to implementation.

Scope:
- Review `docs/project-architecture-guidelines.md` if it is tracked or intentionally added.
- Review roadmap spec and decomposition doc.
- Record any boundary changes from implementation.

Non-goals:
- No new feature code.

Tests:
- None beyond docs checks.

Docs checkpoint:
- This is the phase-level docs checkpoint.

Exit criteria:
- Phase 2 is ready as the substrate for Screener.

## Phase 3: Screener

Phase 3 builds the quantitative screener on the Phase 2 structured equity contract.

### Initiative 3A: Screener Core

#### Slice 3A-S1: ScreenCandidate And ScreenResult

Goal: Define the screener result contract.

Scope:
- `ScreenCandidate`
- `ScreenResult`
- skipped/missing-data records

Non-goals:
- No filter execution.

Tests:
- Dataclass/result helper tests.

Docs checkpoint:
- Align with roadmap spec.

Exit criteria:
- Screener outputs have stable typed containers.

#### Slice 3A-S2: Deterministic Filter Execution

Goal: Run configured filters over structured equity data.

Scope:
- Filter functions.
- pass/fail metrics.
- no LLM calls.

Non-goals:
- No presets.
- No CLI.

Tests:
- Filter pass/fail tests.
- Missing-data tests.

Docs checkpoint:
- Document filter semantics if formulas are user-visible.

Exit criteria:
- A caller can screen a supplied ticker list deterministically.

#### Slice 3A-S3: Missing-Data Skip Semantics

Goal: Make partial provider data safe for screening.

Scope:
- Explicit skipped reasons.
- Warnings/logging behavior.

Non-goals:
- No imputation.

Tests:
- Missing metric tests.

Docs checkpoint:
- Update screener docs with skip behavior.

Exit criteria:
- Missing provider fields cannot silently pass filters.

#### Slice 3A-S4: Result Sorting And Limit Behavior

Goal: Make ranked candidate lists stable.

Scope:
- Sort by metric.
- Limit.
- deterministic tie behavior.

Non-goals:
- No LLM ranking.

Tests:
- Sorting/tie/limit tests.

Docs checkpoint:
- CLI examples should describe sorting.

Exit criteria:
- Screener result order is deterministic.

### Initiative 3B: Screener Presets And Universes

#### Slice 3B-S1: Built-In Universes

Goal: Provide static deterministic universes.

Scope:
- S&P 500, NASDAQ 100, Dow 30 lists.
- Custom list API.

Non-goals:
- No dynamic index membership API.

Tests:
- Universe lookup tests.
- Unknown universe tests.

Docs checkpoint:
- Document static universe limitation.

Exit criteria:
- Screener can resolve initial universes without external APIs.

#### Slice 3B-S2: Value Preset

Goal: Add the first opinionated screener preset.

Scope:
- Low P/E.
- Low P/B.
- High free-cash-flow yield.
- Low debt-to-equity.

Non-goals:
- No macro-aware filter adjustment.

Tests:
- Preset config tests.
- End-to-end mocked value screen.

Docs checkpoint:
- Document formula thresholds.

Exit criteria:
- `value` preset works over mocked structured data.

#### Slice 3B-S3: Growth, Dividend, And Momentum Presets

Goal: Add remaining initial presets.

Scope:
- `growth`
- `dividend`
- `momentum`

Non-goals:
- No agent-driven screening.

Tests:
- Preset tests for each mode.

Docs checkpoint:
- Add preset summaries.

Exit criteria:
- Initial preset family is complete.

#### Slice 3B-S4: Custom Ticker List Support

Goal: Let users screen explicit tickers.

Scope:
- Python API custom ticker lists.
- CLI comma-separated ticker list.

Non-goals:
- No file import unless separately scoped.

Tests:
- Normalization tests.
- Invalid/empty list tests.

Docs checkpoint:
- CLI examples.

Exit criteria:
- Users can screen arbitrary ticker lists.

### Initiative 3C: Screener CLI And Batch Chain

#### Slice 3C-S1: `tradingagents screen`

Goal: Add the primary screener command.

Scope:
- `--universe`
- `--date`
- `--preset`
- `--limit`

Non-goals:
- No batch chaining.

Tests:
- Typer command tests.
- Validation tests.

Docs checkpoint:
- README command example.

Exit criteria:
- CLI can run mocked screener output.

#### Slice 3C-S2: Saved Screen Reports

Goal: Persist screen output.

Scope:
- `~/.tradingagents/logs/screens/<date>/`
- Markdown or JSON summary.

Non-goals:
- No batch reports.

Tests:
- Path safety.
- Report write tests.

Docs checkpoint:
- Report location docs.

Exit criteria:
- Screener output is reproducible from saved artifact.

#### Slice 3C-S3: `--analyze` Chain Into BatchRunner

Goal: Connect screener candidates to batch analysis.

Scope:
- Pass `ScreenResult.tickers` into `BatchRunner`.
- Preserve the same `date`.

Non-goals:
- No per-candidate config overrides.

Tests:
- Mocked chain test.
- Batch fault isolation still passes.

Docs checkpoint:
- CLI example.

Exit criteria:
- Screener-to-batch flow works without bypassing graph APIs.

#### Slice 3C-S4: End-To-End Mocked CLI Tests

Goal: Close Phase 3 with mocked end-to-end confidence.

Scope:
- Screen command.
- Preset.
- Saved output.
- Optional batch chain.

Non-goals:
- No live provider dependency.

Tests:
- End-to-end mocked CLI suite.

Docs checkpoint:
- Phase 3 docs closure.

Exit criteria:
- Screener is ready for macro-aware extensions.

## Phase 4: Macro Intelligence

Macro Intelligence remains data-first, but it now starts after the Phase 2 data-layer foundation. The existing macro implementation plan is still valid at the task level once its phase metadata points to Phase 4.

### Initiative 4A: Macro Data Contract

Slices:
- 4A-S1: Macro schemas and report renderer.
- 4A-S2: Macro registry and config defaults.
- 4A-S3: Macro cache.
- 4A-S4: FRED adapter.
- 4A-S5: optional BLS/EIA availability stubs.

### Initiative 4B: Macro Regime Snapshot

Slices:
- 4B-S1: indicator snapshot builder.
- 4B-S2: deterministic regime classification.
- 4B-S3: no-look-ahead/stale-data tests.
- 4B-S4: `get_macro_regime` tool wrapper.

### Initiative 4C: Macro Analyst

Slices:
- 4C-S1: Macro Analyst factory.
- 4C-S2: `AgentState` / `GraphSetup` / `ConditionalLogic` wiring.
- 4C-S3: CLI analyst selection and report output.
- 4C-S4: graph state propagation tests.

### Initiative 4D: Macro Integration

Slices:
- 4D-S1: batch shared macro context.
- 4D-S2: screener macro-aware preset hooks.
- 4D-S3: portfolio regime input contract.

## Phase 5: Portfolio Optimizer

Portfolio work is last because it consumes batch outputs, structured equity data, screener candidates, macro regime context, and portfolio-level state.

### Initiative 5A: Portfolio State And Persistence

Slices:
- 5A-S1: `Position` and `Portfolio` schemas.
- 5A-S2: JSON store and append-only history.
- 5A-S3: portfolio import/export.
- 5A-S4: path/idempotency tests.

### Initiative 5B: Portfolio Metrics

Slices:
- 5B-S1: current value and weights.
- 5B-S2: volatility/correlation inputs.
- 5B-S3: exposure and concentration metrics.
- 5B-S4: macro regime input attachment.

### Initiative 5C: Allocation Optimizers

Slices:
- 5C-S1: equal weight.
- 5C-S2: rating weighted.
- 5C-S3: risk parity.
- 5C-S4: mean variance.

### Initiative 5D: Portfolio Strategist

Slices:
- 5D-S1: `StrategyDecision` schema.
- 5D-S2: strategist prompt and structured fallback.
- 5D-S3: portfolio-level history context.
- 5D-S4: report renderer.

### Initiative 5E: Portfolio CLI

Slices:
- 5E-S1: portfolio init/add/import/status.
- 5E-S2: optimize command.
- 5E-S3: saved reports.
- 5E-S4: end-to-end mocked flow.

## Next Execution Horizon

The next practical horizon is Phase 2 through the first Massive-backed structured price-history proof point.

1. 2A-S1 DataProviderError hierarchy.
2. 2A-S2 explicit no-data vs provider-error semantics.
3. 2B-S1 structured equity schemas.
4. 2B-S2 structured data entry points.
5. 2C-S1 Massive config and credential detection.
6. 2C-S2 Massive historical aggregates/OHLCV adapter.
7. 2E-S1 register Massive provider in router/config.

This horizon should produce a tested Massive-backed structured price-history path without touching screener, macro, or portfolio implementation.

## Current Stop Conditions

- Do not change the default market-data provider until Massive is proven through mocked tests and optional live smoke.
- Do not build Screener on prose report parsing.
- Do not add Macro Analyst before macro snapshots exist.
- Do not add Portfolio Strategist before portfolio state and metrics exist.
- Do not make live provider credentials required for the default test suite.
- Do not introduce broker execution or trade placement.
