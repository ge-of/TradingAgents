# Phase 2C-S1 Massive Config And Credential Detection Design

## Roadmap Slice

Slice `2C-S1` adds Massive as a provider identity without making API calls. The roadmap scope is limited to `MASSIVE_API_KEY` support, provider config names using `massive`, optional `polygon` alias normalization, and provider setup docs. It explicitly excludes API calls and IBKR work.

## Current Repo Context

- `tradingagents/default_config.py` owns `data_vendors` and `tool_vendors`; defaults are still `yfinance`.
- `tradingagents/dataflows/config.py` deep-copies and one-level merges config updates but does not normalize provider aliases.
- `tradingagents/dataflows/exceptions.py` already has `ProviderAuthError` for missing or invalid provider credentials.
- `tradingagents/dataflows/structured.py` has provider-neutral structured entry points and an empty structured provider registry.
- `.env.example` and `README.md` list current API keys but do not mention `MASSIVE_API_KEY`.

## Approaches Considered

1. Add Massive directly to `VENDOR_METHODS` and `STRUCTURED_VENDOR_METHODS`.
   - Pros: provider name becomes discoverable immediately through the routers.
   - Cons: implies callable provider implementations before the adapter slices exist and risks agent-facing router behavior changing too early.

2. Add a small Massive identity module plus config alias normalization.
   - Pros: gives later adapter slices a credential helper and stable provider name while preserving router behavior and avoiding network calls.
   - Cons: introduces a new module that is not yet registered as a provider implementation.

3. Only update docs and `.env.example`.
   - Pros: smallest diff.
   - Cons: does not satisfy the roadmap exit criteria because code still cannot detect the key or normalize the provider name.

## Recommended Design

Use approach 2. Add `tradingagents/dataflows/massive.py` with provider constants, `normalize_massive_provider_name()`, and `get_massive_api_key()`. Missing keys raise `ProviderAuthError` with `provider="massive"` and a message naming `MASSIVE_API_KEY`; no HTTP client or endpoint logic is added in this slice.

Update `tradingagents/dataflows/config.py` so `set_config()` normalizes provider names inside `data_vendors` and `tool_vendors`. The only alias added in this slice is `polygon -> massive`. Keep `yfinance`, `alpha_vantage`, and existing unknown provider values otherwise unchanged.

Update `tradingagents/default_config.py` comments, `.env.example`, and `README.md` to document optional Massive setup while keeping `yfinance` as the default. Do not add Massive to `VENDOR_METHODS` or `STRUCTURED_VENDOR_METHODS` yet.

## Test And Docs Boundary

Tests should be mocked and environment-local only:

- Missing key raises `ProviderAuthError` and names `MASSIVE_API_KEY`.
- Present key is returned without mutation.
- `polygon` is normalized to `massive` in `data_vendors` and `tool_vendors`.
- Default config still uses `yfinance`.

Docs change only for provider setup: `.env.example` and README required API key list. No architecture doc update is needed unless implementation changes the provider boundary described in `docs/project-architecture-guidelines.md`.

## Scope Guards

- No API calls.
- No Massive OHLCV, ticker details, dividends, splits, or error-normalization implementation.
- No `VENDOR_METHODS` registration.
- No agent-facing `route_to_vendor()` behavior change.
- No Phase 2D fundamentals, screener, portfolio, macro, graph, prompts, CLI UX, or IBKR work.

## Self-Review

- Scope creep check: the design stops at provider identity, config aliasing, key detection, and docs.
- Contradiction check: it preserves the structured/prose boundary and keeps Massive below `dataflows`.
- Ambiguity check: `polygon` is a legacy config alias only; the canonical provider name is `massive`.
- Test boundary check: no default test requires live credentials or network access.
