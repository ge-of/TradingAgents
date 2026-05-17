# Phase 2C-S5 Provider Error / Rate-Limit Normalization Design

## Roadmap Slice

Slice `2C-S5` ensures Massive errors participate in the shared provider contract. It maps HTTP 401/403, 429, 5xx, malformed responses, and timeouts to provider errors, includes safe diagnostic messages without exposing secrets, and excludes retry policy unless explicitly designed.

## Current Repo Context

- `ProviderAuthError`, `ProviderRateLimitError`, and `ProviderUnavailableError` already carry provider, method, retryable, status code, and details.
- Earlier Phase 2C adapter slices should have added endpoint-level Massive error handling for price history, ticker details, and corporate actions.
- The likely duplication after Slices `2C-S2` through `2C-S4` is status checks, timeout handling, JSON parsing, and secret redaction.
- Default tests must remain mocked and must not call Massive.

## Approaches Considered

1. Leave endpoint-level error handling in each adapter.
   - Pros: no refactor risk.
   - Cons: duplicated logic drifts and makes safe diagnostics harder to guarantee.

2. Add one private Massive request helper and refactor existing Massive endpoints to use it.
   - Pros: deterministic, testable, and keeps normalization below the dataflows boundary.
   - Cons: touches all Massive adapter methods from prior slices.

3. Add a retrying Massive client class now.
   - Pros: creates a conventional provider client abstraction.
   - Cons: violates the roadmap non-goal by introducing retry policy and broad abstraction before needed.

## Recommended Design

Use approach 2. Add `request_massive_json(path, params, method, session=None)` or a private equivalent in `tradingagents/dataflows/massive.py`. It should:

- Add `apiKey` internally from `get_massive_api_key()`.
- Use an injected `requests.Session`-compatible object for tests.
- Map 401/403 to `ProviderAuthError`.
- Map 429 to `ProviderRateLimitError`, preserving integer `Retry-After` when present.
- Map 5xx, timeouts, request exceptions, and malformed JSON to `ProviderUnavailableError`.
- Include safe details such as method, path, status code, ticker, date range, and retry-after; exclude `apiKey` and raw response bodies that may include secrets.

Refactor price history, ticker details, dividends, and splits to call this helper. Do not add retries, backoff, caching, circuit breakers, CLI UX, or live checks.

## Test And Docs Boundary

Tests should be mocked:

- Status-code mapping for 401, 403, 429, 500, and unexpected non-200.
- Timeout and request-exception mapping.
- Malformed JSON mapping.
- `apiKey` is absent from exception string and details.
- Existing Massive adapter tests still pass after refactor.

Docs should update README troubleshooting only if the implementation introduces user-facing error meanings worth documenting. A short provider setup troubleshooting note is appropriate for 401/403 and 429.

## Scope Guards

- No retry policy.
- No live provider calls.
- No new endpoints.
- No provider registration changes.
- No agent-facing router changes.
- No Phase 2D, screener, portfolio, macro, graph, prompts, CLI UX, execution modeling, or IBKR work.

## Self-Review

- Scope creep check: the design centralizes error normalization only.
- Contradiction check: it strengthens the shared provider contract without changing no-data semantics.
- Ambiguity check: non-200 statuses outside 401/403/429/5xx become deterministic provider-unavailable errors unless a later slice designs something narrower.
- Test boundary check: secret redaction is tested directly and all default tests remain mocked.
