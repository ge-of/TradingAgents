# Phase 2C-S2 Massive Historical Aggregates / OHLCV Adapter Design

## Roadmap Slice

Slice `2C-S2` fetches and normalizes historical OHLCV data from Massive. The roadmap requires a `requests`-based historical aggregates adapter, `PriceHistory` normalization, `as_of` and date-range boundaries, mocked response parsing, provider-error tests, and no-look-ahead tests. It excludes fundamentals and screener filters.

## Current Repo Context

- `PriceHistory` already lives in `tradingagents/dataflows/structured.py` with `Date`, `Open`, `High`, `Low`, `Close`, and `Volume` as the expected frame columns.
- `get_price_history()` already validates dates and enforces the requested end date as the `as_of` boundary after provider dispatch.
- `STRUCTURED_VENDOR_METHODS["get_price_history"]` is currently the structured provider registry for price history.
- `ProviderAuthError`, `ProviderRateLimitError`, `ProviderUnavailableError`, and `ProviderNoDataError` already exist.
- Slice `2C-S1` is expected to provide `MASSIVE_PROVIDER`, `get_massive_api_key()`, and the canonical `massive` provider name.

## Approaches Considered

1. Implement only a parser and defer HTTP wiring.
   - Pros: very small and easy to test.
   - Cons: does not satisfy the roadmap requirement for a `requests` adapter or structured provider path.

2. Implement a narrow Massive price-history adapter and register it only in the structured price registry.
   - Pros: satisfies the roadmap while keeping agent-facing `route_to_vendor()` unchanged.
   - Cons: introduces a small amount of provider-specific HTTP behavior before the later error-normalization slice consolidates it.

3. Implement a generic Massive client plus all endpoint infrastructure now.
   - Pros: avoids later refactor work.
   - Cons: broadens this slice into ticker reference, corporate actions, and error-normalization architecture before those slices are ready.

## Recommended Design

Use approach 2. Add `get_massive_price_history(ticker, start, end, session=None)` to `tradingagents/dataflows/massive.py`. It should:

- Read `MASSIVE_API_KEY` through the Slice `2C-S1` helper.
- Build a daily aggregate request for the requested ticker and date range.
- Accept an injected `requests.Session`-compatible object for tests.
- Normalize response bars into a `PriceHistory` containing a pandas DataFrame with `PRICE_HISTORY_COLUMNS`.
- Raise `ProviderNoDataError` when the provider response succeeds but has no usable bars.
- Map basic HTTP and request failures to shared provider errors for this endpoint.

Register only this structured provider:

```python
STRUCTURED_VENDOR_METHODS["get_price_history"]["massive"] = get_massive_price_history
```

Do not register Massive in the agent-facing `VENDOR_METHODS`. The string/report tool path remains unchanged.

## Error Handling Boundary

This slice maps the statuses needed to keep the price adapter deterministic: missing credentials, 401/403, 429, 5xx, timeouts, malformed JSON, and empty results. Slice `2C-S5` will later centralize and harden error/rate-limit normalization across all Massive endpoints. Keep S2 helper names private if they are likely to be refactored in S5.

## Test And Docs Boundary

Tests are mocked and credential-local:

- Parse a successful aggregate payload into `PriceHistory`.
- Prove `structured.get_price_history()` routes to Massive when configured.
- Prove future-dated rows are filtered by the existing structured contract.
- Prove empty results raise `ProviderNoDataError`.
- Prove representative auth, rate-limit, server, timeout, and malformed responses raise shared provider errors.

Docs should add an optional live smoke command note gated by `MASSIVE_API_KEY`, but the command should be documented as future/optional until Slice `2C-S7` formalizes the smoke test.

## Scope Guards

- No fundamentals.
- No ticker reference/details.
- No dividends, splits, or corporate actions.
- No screener filters.
- No agent-facing `route_to_vendor()` or `VENDOR_METHODS` registration.
- No Phase 2D, screener, portfolio, macro, graph, prompts, CLI UX, or IBKR work.
- No default test should make a live network call.

## Self-Review

- Scope creep check: only the structured price-history path is added.
- Contradiction check: S2 includes endpoint-level provider error mapping because the roadmap asks for it, while S5 remains responsible for consolidation across all Massive endpoints.
- Ambiguity check: `end` is the `as_of` boundary; structured enforcement remains the final guard against look-ahead rows.
- Test boundary check: all tests inject fake sessions and do not require a real `MASSIVE_API_KEY`.
