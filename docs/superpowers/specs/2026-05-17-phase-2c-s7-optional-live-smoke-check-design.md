# Phase 2C-S7 Optional Live Smoke Check Design

## Roadmap Slice

Slice `2C-S7` provides an honest credential-gated check for real Massive connectivity. The smoke check must run only when `MASSIVE_API_KEY` is present, stay out of default CI, test skip behavior without a key, and be documented in README. It must not create a CI dependency on paid provider quota.

## Current Repo Context

- Pytest already defines `integration` and `smoke` markers.
- Existing live-style tests in the repo skip when provider keys are absent or set to `placeholder`.
- The Massive mocked suite from Slice `2C-S6` should already prove adapter behavior without credentials.
- Live provider checks are only for contributor confidence, not for default correctness.

## Approaches Considered

1. Add a CLI command for Massive smoke checks.
   - Pros: user-friendly.
   - Cons: adds CLI surface and UX work beyond the dataflows slice.

2. Add a dedicated pytest smoke file gated by both `MASSIVE_API_KEY` and `RUN_MASSIVE_LIVE_SMOKE=1`.
   - Pros: explicit, easy to document, and naturally excluded from default CI by skip behavior.
   - Cons: contributors must run a longer command.

3. Add a live test that runs whenever `MASSIVE_API_KEY` exists.
   - Pros: convenient for local users with keys.
   - Cons: dangerous in CI or shell environments that happen to have credentials, and it can burn quota unexpectedly.

## Recommended Design

Use approach 2. Add `tests/test_massive_live_smoke.py` with:

- A small helper that returns true only when `RUN_MASSIVE_LIVE_SMOKE=1` and `MASSIVE_API_KEY` exists and is not `placeholder`.
- Unit tests proving the helper stays disabled without the flag or without a real key.
- One `@pytest.mark.integration` and `@pytest.mark.smoke` test that calls the structured Massive price-history path for a narrow known ticker/date range.

The live test should use the existing public structured adapter path, not private parser helpers, so it proves real connectivity through the same surface a contributor would use.

## Test And Docs Boundary

Default test runs should collect and skip the live smoke test unless explicitly enabled. The README should include the exact command and a warning that the smoke check may consume provider quota.

No production code should change unless a small helper is needed to make the live test call the existing public adapter cleanly.

## Scope Guards

- No default CI dependency on Massive or paid quota.
- No new CLI command.
- No live calls during ordinary `pytest`.
- No new adapter behavior or endpoints.
- No retry policy.
- No Phase 2D, screener, portfolio, macro, graph, prompts, CLI UX, execution modeling, or IBKR work.

## Self-Review

- Scope creep check: this is a single optional pytest smoke check plus README docs.
- Contradiction check: the default suite remains mocked and credential-free.
- Ambiguity check: both a real key and `RUN_MASSIVE_LIVE_SMOKE=1` are required.
- Test boundary check: skip behavior is tested without contacting Massive.
