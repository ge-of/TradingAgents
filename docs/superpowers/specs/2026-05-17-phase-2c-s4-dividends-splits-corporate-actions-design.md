# Phase 2C-S4 Dividends, Splits, And Corporate Actions Design

## Roadmap Slice

Slice `2C-S4` normalizes corporate actions that affect historical analysis and screening. The roadmap requires dividend and split structured outputs, a preserved path for adjusted and unadjusted price semantics, mocked parsing tests, empty response/no-data behavior, and documentation of adjusted price assumptions. It excludes portfolio tax-lot logic and execution modeling.

## Current Repo Context

- `docs/project-architecture-guidelines.md` already states that empty dividends, splits, and corporate-action collections are valid optional structured results.
- `ProviderResultRole.OPTIONAL` already supports returning empty child collections unchanged.
- `PriceHistory` currently carries OHLCV data but no explicit adjusted/unadjusted flag.
- Massive price-history work from Slice `2C-S2` should use adjusted daily bars by default, while this slice provides the separate corporate action data needed by future unadjusted calculations.

## Approaches Considered

1. Add dividend and split lists directly onto `PriceHistory`.
   - Pros: keeps related market data together.
   - Cons: couples price bars to optional corporate actions and makes no-action results harder to reason about.

2. Add separate `DividendEvent`, `SplitEvent`, and `CorporateActions` structured contracts.
   - Pros: makes optional empty collections explicit and gives future screeners/portfolio metrics a stable typed source.
   - Cons: adds a new structured entry point and more schema tests.

3. Defer schemas and only document adjusted price assumptions.
   - Pros: smallest diff.
   - Cons: does not satisfy the roadmap exit criteria that corporate action data be available to future workflows.

## Recommended Design

Use approach 2. Add structured dataclasses:

- `DividendEvent`
- `SplitEvent`
- `CorporateActions`

Add `get_corporate_actions(ticker, start, end)` under the `core_stock_apis` structured category. The Massive adapter should fetch dividends and splits separately, normalize both into typed lists, and return an empty list when no events exist in the requested range. Only a failed provider request should raise provider errors.

Preserve adjusted/unadjusted semantics by keeping corporate actions separate from `PriceHistory` and documenting that the Massive price-history adapter uses adjusted bars by default. Future unadjusted support should add an explicit parameter or separate entry point; it should not silently reinterpret existing `PriceHistory`.

## Test And Docs Boundary

Tests should be mocked:

- Successful dividend payload maps to `DividendEvent`.
- Successful split payload maps to `SplitEvent`.
- Empty dividends and splits return empty lists.
- Structured routing calls the Massive corporate action adapter.
- Provider errors still propagate through shared provider errors.

Docs should update README provider notes with the adjusted price assumption. Architecture docs already contain the optional empty corporate-action behavior, so no architecture update is needed unless implementation changes that contract.

## Scope Guards

- No portfolio tax-lot logic.
- No execution modeling.
- No screener metrics or filters.
- No new price adjustment calculations.
- No fundamentals, ticker universe membership, graph, prompts, CLI UX, macro, portfolio optimizer, Phase 2D, or IBKR work.
- No default live provider calls.

## Self-Review

- Scope creep check: the design adds typed corporate-action data only.
- Contradiction check: empty corporate-action collections remain valid optional results, matching the architecture doc.
- Ambiguity check: adjusted price behavior is documented as an assumption, not silently changed in `PriceHistory`.
- Test boundary check: all default tests use mocked provider responses.
