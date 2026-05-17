# Phase 2C-S6 Mocked Adapter Test Suite Design

## Roadmap Slice

Slice `2C-S6` consolidates adapter coverage before any live smoke test. The roadmap scope is to run the full mocked Massive adapter test set and add fixtures for common Massive payloads. It has no live network requirement.

## Current Repo Context

- Prior Phase 2C plans introduce mocked tests for config, price history, ticker details, corporate actions, and error normalization.
- Those tests are expected to use inline fake payloads and small fake session classes.
- The repo currently has no `tests/fixtures/` directory.
- `tests/conftest.py` already controls API-key environment behavior for test safety.

## Approaches Considered

1. Leave all payloads inline in individual tests.
   - Pros: no fixture indirection.
   - Cons: duplicated payloads make the final mocked suite harder to audit.

2. Add JSON fixtures and shared fake Massive response/session helpers under `tests/`.
   - Pros: keeps the full adapter suite readable, reusable, and credential-free.
   - Cons: requires updating earlier tests to import shared helpers.

3. Add a broad integration-style mocked suite that calls every public adapter in one test.
   - Pros: quick end-to-end coverage.
   - Cons: hides failures and makes tests less diagnostic than focused unit tests.

## Recommended Design

Use approach 2. Add common fixtures under `tests/fixtures/massive/` and a test helper module such as `tests/massive_fakes.py` for fake responses, fake sessions, and fixture loading. Update Massive tests from Slices `2C-S2` through `2C-S5` to use shared fixtures where it improves clarity.

The suite should stay unit-level and fully mocked. It should prove:

- Config/key detection does not require real credentials.
- Price history parses fixture aggregates.
- Ticker details parses fixture metadata and missing-field fixture variants.
- Corporate actions parses fixture dividends and splits, including empty responses.
- Error normalization maps statuses, timeouts, and malformed JSON without leaking `apiKey`.

## Test And Docs Boundary

No production behavior should change. If test helper extraction requires tiny import adjustments in tests, keep them test-only. Do not add live smoke tests in this slice.

No durable docs update is required unless fixture contents encode a contract not already captured by the adapter tests. File names and test assertions should carry the contract.

## Scope Guards

- No live network calls.
- No `MASSIVE_API_KEY` requirement.
- No new adapter endpoints or provider behavior.
- No provider registration changes.
- No README smoke instructions beyond what prior slices already added.
- No Phase 2D, screener, portfolio, macro, graph, prompts, CLI UX, execution modeling, or IBKR work.

## Self-Review

- Scope creep check: the design consolidates mocked tests and fixtures only.
- Contradiction check: it deliberately comes before S7 live smoke and keeps default verification credential-free.
- Ambiguity check: fixtures are for repeatable unit tests, not canonical provider documentation.
- Test boundary check: the full Massive unit suite remains runnable without network access.
