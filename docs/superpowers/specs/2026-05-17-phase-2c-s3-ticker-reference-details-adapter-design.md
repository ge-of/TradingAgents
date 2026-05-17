# Phase 2C-S3 Massive Ticker Reference / Details Adapter Design

## Roadmap Slice

Slice `2C-S3` normalizes Massive ticker metadata needed by future screeners and reports. The required fields are ticker name, market, exchange, currency, locale, and active status. The slice must return explicit missing-field availability records. It excludes universe membership APIs and fundamentals parsing.

## Current Repo Context

- `DataAvailability` and `AvailabilityStatus` already exist in `tradingagents/dataflows/structured.py`.
- The structured registry currently covers price history, fundamentals snapshots, and indicators, but not ticker metadata.
- No existing dataflow module exposes a provider-neutral ticker details schema.
- Future screeners need ticker metadata, but universe membership is a separate Phase 3 concern.
- Slice `2C-S2` is expected to have established the Massive module pattern, fake session tests, and structured provider registration.

## Approaches Considered

1. Return a plain dictionary from `get_massive_ticker_details()`.
   - Pros: quick to implement and flexible.
   - Cons: weakens the structured contract and makes missing-field handling ad hoc.

2. Add a focused `TickerDetails` dataclass plus structured entry point.
   - Pros: matches existing structured dataclass patterns and makes availability records explicit.
   - Cons: requires a small schema extension and docs checkpoint.

3. Fold metadata into `FundamentalsSnapshot`.
   - Pros: avoids adding a new entry point.
   - Cons: blurs reference data with financial fundamentals and risks broadening into Phase 2D.

## Recommended Design

Use approach 2. Add `TickerDetails` to `tradingagents/dataflows/structured.py`:

- `ticker`
- `as_of`
- `name`
- `market`
- `exchange`
- `currency`
- `locale`
- `active`
- `availability`

Add `get_ticker_details(ticker, as_of)` as a structured entry point under the `core_stock_apis` category and register only `massive` as the first provider for that method. The Massive adapter should call a ticker reference/details endpoint, normalize fields, and attach `DataAvailability(status=AvailabilityStatus.MISSING)` records for missing optional fields. A completely missing `results` object is top-level no-data and should raise `ProviderNoDataError`.

## Test And Docs Boundary

Tests should be mocked:

- Successful reference payload maps to `TickerDetails`.
- Missing fields produce availability records instead of exceptions.
- Empty top-level response raises `ProviderNoDataError`.
- Structured routing uses `data_vendors.core_stock_apis` or tool override for `get_ticker_details`.

Because this slice introduces a formal structured metadata schema, update the architecture guidelines or structured contract docs with a short note that ticker reference metadata is a structured dataflow contract. Do not add a universe membership API.

## Scope Guards

- No universe membership, index constituents, or static universe lists.
- No fundamentals parsing or Phase 2D fields.
- No screener filters.
- No agent-facing `route_to_vendor()` or `VENDOR_METHODS` registration.
- No dividends, splits, corporate actions, graph, prompts, CLI UX, portfolio, macro, or IBKR work.
- No default live provider calls.

## Self-Review

- Scope creep check: the design adds only ticker reference metadata, not universes or fundamentals.
- Contradiction check: metadata becomes typed data for structured callers; LLM-facing tools remain string/report based.
- Ambiguity check: missing child fields become availability records, but missing top-level ticker details is no-data.
- Docs boundary check: a durable docs update is justified because a new formal structured schema is introduced.
