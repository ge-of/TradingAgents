# TradingAgents Project Architecture Guidelines

Last reviewed: 2026-05-14

This document is a project reference for extending TradingAgents without eroding the design choices already built into the repository. It is not a session log. Keep it focused on architectural boundaries, extension patterns, and implementation rules that future contributors can apply.

## Purpose

TradingAgents is a multi-agent LLM financial research and trading-decision framework. It is a recommendation engine, not a broker or trade-execution system. New work should preserve that boundary unless the project intentionally opens a separate execution initiative with explicit safety, compliance, and credential-handling design.

The core architecture is built around a per-ticker LangGraph workflow. Each run produces analyst reports, debate summaries, a trader proposal, risk debate output, and a final portfolio-manager decision. The primary user-facing artifact remains Markdown/prose, while structured schemas are used selectively where downstream code needs stable machine-readable decisions.

## High-Level Architecture

```text
                  +----------------------------+
                  | CLI / Python API           |
                  | cli.main / main.py         |
                  +-------------+--------------+
                                |
                 +--------------+---------------+
                 |                              |
        tradingagents batch             TradingAgentsGraph
        BatchRunner.run()               propagate(ticker,date)
        multi-ticker loop               per-ticker graph run
                 |                              |
                 +---------------+--------------+
                                 |
                          LangGraph AgentState
                                 |
 START
   |
   v
 [Selected Analyst Nodes]
   |  market / sentiment / news / fundamentals
   |  analyst -> ToolNode -> analyst -> Msg Clear
   v
 Bull Researcher <----> Bear Researcher
   | bounded by max_debate_rounds
   v
 Research Manager
   |
   v
 Trader
   |
   v
 Aggressive Risk -> Conservative Risk -> Neutral Risk
   ^                                      |
   | bounded by max_risk_discuss_rounds   |
   +--------------------------------------+
   |
   v
 Portfolio Manager
   |
   +--> final_trade_decision markdown
   +--> deterministic rating parse
   +--> JSON state log
   +--> append-only decision memory log
   +--> optional CLI/batch markdown reports

 Data path:
 Agent @tool wrappers -> route_to_vendor() -> yfinance / Alpha Vantage

 LLM path:
 create_llm_client() -> provider-specific LangChain chat model wrapper
```

## Module Responsibilities

`tradingagents/graph/` owns orchestration. `TradingAgentsGraph` wires config, LLM clients, memory, tool nodes, graph setup, checkpointing, reflection, and signal processing. `GraphSetup` owns the LangGraph topology. `ConditionalLogic` owns loop routing. `Propagator` owns initial state and graph invocation arguments.

`tradingagents/agents/` owns agent factories and prompt behavior. Analyst agents gather evidence. Researcher and risk agents debate. Manager/trader agents synthesize decisions. Shared state types live in `agents/utils/agent_states.py`.

`tradingagents/agents/schemas.py` owns typed decision schemas and render helpers. Keep structured output concentrated here unless a new feature truly needs a stable typed contract.

`tradingagents/dataflows/` owns market, news, social, and fundamentals data access. Existing LangChain tools call `route_to_vendor()` and return strings/report blocks for LLM consumption. Numeric screening or portfolio optimization should use a separate structured data contract instead of scraping prose tool output.
Ticker reference metadata, when needed by downstream quantitative workflows, should use structured data contracts with explicit missing-field availability records rather than agent-facing prose reports.

`tradingagents/llm_clients/` owns provider abstraction, model catalog, API-key mapping, validation, content normalization, and provider quirks. Add provider quirks through capability tables or provider client wrappers, not scattered checks in agents.

`tradingagents/batch/` owns multi-ticker orchestration as a wrapper around the existing per-ticker graph. It should not duplicate graph internals.

`cli/` owns interactive UX, Rich rendering, command registration, API-key prompting, report display, and user-facing run controls.

`tests/` should encode architectural contracts, not just happy paths. Existing examples cover structured-agent fallback, safe ticker path handling, checkpoint resume, provider capabilities, config isolation, and batch fault isolation.

## Core Design Decisions To Preserve

### Keep LangGraph As The Orchestration Boundary

The per-ticker pipeline is a graph, not a procedural script. New per-ticker agents should be added through `GraphSetup`, `AgentState`, and `ConditionalLogic` so they participate in the same checkpoint, state, and report flow.

Avoid bypassing `TradingAgentsGraph.propagate()` for work that is semantically part of one ticker analysis. External orchestration such as batch mode may call `propagate()`, but should treat it as the stable per-ticker contract.

### Preserve The Role Pipeline

The current role sequence is intentional:

```text
Analysts -> Bull/Bear Research -> Research Manager -> Trader -> Risk Debate -> Portfolio Manager
```

Additions should respect that separation. Analyst nodes gather evidence. Debate nodes argue. Manager nodes synthesize. The Trader proposes a transaction. The Portfolio Manager decides. Do not make analyst nodes final decision makers or make the Portfolio Manager fetch raw data unless there is a deliberate redesign.

### Prose Is The Primary Artifact, Structured Output Is Selective

Most reports are Markdown/prose because they are read by users and by downstream agents. Structured output is used where deterministic downstream behavior matters: Research Manager, Trader, and Portfolio Manager. Render helpers convert typed Pydantic objects back to Markdown so existing reports, memory logs, and parsers remain stable.

When adding structured output:

- Define schemas centrally in `tradingagents/agents/schemas.py` or a feature-owned schema module.
- Keep render helpers next to schemas.
- Preserve the Markdown shape consumed by CLI, memory, reports, and tests.
- Provide graceful free-text fallback when a provider does not support structured output.

### Keep Data Provider Choice Below The Tool Boundary

Agent tools should remain provider-neutral. They call `route_to_vendor()` and receive report strings. Provider selection comes from `DEFAULT_CONFIG`, `dataflows/config.py`, `data_vendors`, and `tool_vendors`.

New provider work should register provider implementations in the router rather than adding provider-specific logic to agent prompts. If a feature needs numeric fields, add or use a structured data layer instead of parsing agent-facing Markdown in business logic.

### Treat Batch Mode As External Orchestration

Batch mode loops over tickers and calls `TradingAgentsGraph.propagate()` for each ticker. It ranks, summarizes, and writes batch reports, but the per-ticker analysis contract remains the graph. Keep batch sequential by default unless rate-limit handling, cost controls, and failure semantics are designed explicitly.

### Keep Memory Append-Only And Outcome-Gated

The decision memory log stores final decisions first, then resolves outcomes later when price data is available. It injects completed same-ticker and recent cross-ticker lessons into the Portfolio Manager prompt. Do not reintroduce per-agent opaque memory stores unless there is a clear reason and an explicit retrieval contract.

### Keep Checkpoints Per Ticker And Date

Checkpoint resume is for long or interrupted LangGraph runs. It uses deterministic ticker/date thread IDs and per-ticker SQLite databases. New graph work should remain compatible with checkpoint replay: nodes should be deterministic enough to resume from persisted state and should not rely on hidden global mutation for correctness.

### Validate Filesystem Path Inputs

Tickers can come from users, LLM tool calls, or prompt-influenced data. Any ticker used in a path must pass `safe_ticker_component()`. Apply this rule to caches, reports, checkpoints, batch outputs, and any future persistence directories.

## Extension Guidelines

### Adding A New Agent

Use this path when the new capability belongs inside a single ticker analysis.

1. Add state fields to `AgentState` only if the output must be consumed later.
2. Add the agent factory under the correct role folder in `tradingagents/agents/`.
3. Register the node and edges in `GraphSetup`.
4. Add routing logic to `ConditionalLogic` if the node loops or branches.
5. Update CLI display/report section mapping if the output is user-facing.
6. Add tests that prove state shape, report propagation, and fallback behavior.

Do not add a graph node for cross-ticker portfolio allocation. That belongs outside the per-ticker graph.

### Adding A New Data Provider

Use the existing router pattern:

1. Implement provider functions under `tradingagents/dataflows/`.
2. Register them in `VENDOR_METHODS`.
3. Add config keys or vendor names in `DEFAULT_CONFIG` only when needed.
4. Keep agent tool signatures unchanged.
5. Normalize provider errors into a shared error hierarchy if fallback should work beyond Alpha Vantage rate limits.
6. Add tests for routing, fallback, missing credentials, and return shape.

For providers that return structured numeric data, keep the structured contract separate from the string/report wrappers used by LLM tools.

### Adding Screening Or Quantitative Features

Screening should not depend on LLM-facing report strings. It should consume typed fundamentals, price history, and indicator data. Keep the screener pure quantitative unless an explicit LLM screening phase is designed.

Important constraints:

- Always require or default an `as_of` date and prevent look-ahead bias.
- Treat missing numeric data as a first-class outcome.
- Keep universes and presets deterministic and testable.
- Chain into `BatchRunner` by passing tickers, not by bypassing the graph.

### Adding Portfolio Optimization

Portfolio optimization is cross-ticker and should live outside the per-ticker graph. It should consume `BatchResult`, current portfolio state, structured price/fundamental data, and explicit optimizer settings.

Keep the naming distinction clear:

- Existing `Portfolio Manager`: per-ticker LangGraph node that makes a final position rating.
- Future Portfolio Strategist or Optimizer: cross-ticker orchestration that reasons about allocations, concentration, correlation, and rebalance proposals.

Do not store cross-portfolio state in the per-ticker memory log. Portfolio-level state should have its own persistence and history contract.

### Adding LLM Providers Or Models

Use the existing LLM client pattern:

1. Add provider or model options to the model catalog.
2. Add API-key env mapping if the provider needs credentials.
3. Add capability-table entries for structured output or tool-calling quirks.
4. Keep response content normalized to plain strings.
5. Add focused tests for validation, warning behavior, and provider-specific request shaping.

Avoid putting provider-specific prompt workarounds inside agent factories.

### Adding CLI Commands

CLI commands should be thin orchestration and display layers. They should validate user inputs, assemble config, call package APIs, and render results. Business logic belongs under `tradingagents/`.

For new commands:

- Validate dates and ticker lists before running expensive work.
- Use `DEFAULT_CONFIG.copy()` plus explicit overrides.
- Keep report writing in package code when reports are part of a feature contract.
- Preserve non-interactive command support where practical.
- Add Typer `CliRunner` tests for command registration, validation, and output.

## Error Handling Principles

- Per-ticker batch failures should be captured in `TickerResult.error`, not abort the whole batch.
- Provider rate limits and transient API errors should be distinguishable from valid no-data responses.
- Missing credentials should name the exact environment variable.
- Feature code should not silently swallow failures that change the user-visible decision.
- Graceful degradation is acceptable for supplemental data sources when the prompt explicitly receives an unavailable/no-data marker.

### Provider No-Data Contract

Structured data adapters distinguish required top-level data from optional child collections.

- Raise `ProviderNoDataError` when a provider request succeeds but the requested required dataset has no usable rows or entity data after ticker, date, or `as_of` filtering. Examples include unknown tickers, unsupported tickers, no OHLCV bars in the requested date range, empty required fundamentals responses, and all required rows being filtered out.
- Return empty structured collections when emptiness is the valid domain answer for an optional child collection. Examples include no news articles, no insider transactions, no dividends, no splits, and no corporate-action events in range.
- Return partial structured objects with `None` fields or availability records when the entity exists but individual fields are missing.
- Raise `ProviderAuthError`, `ProviderRateLimitError`, or `ProviderUnavailableError` for credential/entitlement failures, quota/rate-limit failures, transport/timeouts, HTTP 5xx, and malformed provider responses.
- Keep caller validation errors, such as unsupported indicators or invalid date formats, as `ValueError`.
- Keep `route_to_vendor()` fallback broadening out of this contract slice; Slice `2A-S3` owns router fallback behavior.

## Testing Expectations

Scale tests to the architectural risk:

- Agent prompt/schema changes: schema render tests, fallback tests, downstream parser tests.
- Graph topology changes: state propagation and conditional routing tests.
- Data provider changes: router/config/fallback tests plus no-look-ahead tests.
- Persistence changes: path safety, idempotency, atomic write, and resume/replay tests.
- CLI changes: command registration, validation failures, and summarized output tests.
- Batch/cross-ticker changes: fault isolation, ranking order, report writes, and unsafe ticker handling.

Prefer small mocked tests for LLM-facing behavior. Use smoke scripts only for optional real-provider verification.

## Architecture Review Checklist For New Features

Before implementing a feature, answer these questions in the plan or PR:

1. Is this per-ticker analysis, cross-ticker orchestration, data access, provider support, CLI UX, or persistence?
2. Which existing module owns that responsibility?
3. Does the feature need LangGraph state, or can it call `propagate()` externally?
4. Does it consume prose reports or require structured numeric/typed data?
5. What user-facing Markdown/report shape changes?
6. What config keys or environment variables are required?
7. How does it behave when one ticker, provider, or LLM call fails?
8. Does any input become a filesystem path?
9. What tests prove the architectural contract?
10. Does durable documentation need to change?

## Current Roadmap Boundaries

Batch mode exists as a `tradingagents/batch/` package. Screener, structured numeric data access, IBKR/Massive provider modules, and a persistent cross-ticker portfolio optimizer are roadmap-level concepts unless and until those packages are added.

When implementing those roadmap items, preserve these boundaries:

- Structured data access should sit alongside agent-facing string tools.
- Screener should be quantitative and date-aware.
- Provider swaps should be invisible above the data layer.
- Portfolio optimization should be cross-ticker and separate from the current per-ticker Portfolio Manager node.

## Maintenance Notes

Keep this document high-signal. Update it when an implementation changes an architectural boundary, module ownership, data contract, persistence model, CLI command family, or extension rule. Do not append session summaries or PR logs here.
