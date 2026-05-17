"""Massive provider identity and credential helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import TYPE_CHECKING, Any

import pandas as pd
import requests

from .availability import ProviderResultRole, normalize_provider_result
from .exceptions import ProviderAuthError, ProviderRateLimitError, ProviderUnavailableError

if TYPE_CHECKING:
    from .structured import PriceHistory

MASSIVE_PROVIDER = "massive"
MASSIVE_LEGACY_PROVIDER_ALIASES = {"polygon": MASSIVE_PROVIDER}
MASSIVE_API_KEY_ENV = "MASSIVE_API_KEY"
MASSIVE_BASE_URL = "https://api.massive.com"
MASSIVE_TIMEOUT_SECONDS = 10


def normalize_massive_provider_name(provider: str) -> str:
    normalized = provider.strip().lower()
    return MASSIVE_LEGACY_PROVIDER_ALIASES.get(normalized, normalized)


def get_massive_api_key() -> str:
    api_key = os.getenv(MASSIVE_API_KEY_ENV)
    if api_key:
        return api_key

    raise ProviderAuthError(
        f"{MASSIVE_API_KEY_ENV} environment variable is not set.",
        provider=MASSIVE_PROVIDER,
        method="credential_detection",
    )


def _daily_aggs_url(ticker: str, start: str, end: str) -> str:
    return f"{MASSIVE_BASE_URL}/v2/aggs/ticker/{ticker.upper()}/range/1/day/{start}/{end}"


def _timestamp_ms_to_date(value: int | float) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()


def _raise_for_massive_status(response: requests.Response, method: str) -> None:
    status_code = response.status_code
    if status_code == 200:
        return

    if status_code in {401, 403}:
        raise ProviderAuthError(
            f"Massive {method} request failed with HTTP {status_code}",
            provider=MASSIVE_PROVIDER,
            method=method,
            status_code=status_code,
        )

    if status_code == 429:
        retry_after_header = response.headers.get("Retry-After")
        retry_after = int(retry_after_header) if retry_after_header and retry_after_header.isdigit() else None
        raise ProviderRateLimitError(
            f"Massive {method} request failed with HTTP {status_code}",
            provider=MASSIVE_PROVIDER,
            method=method,
            status_code=status_code,
            retry_after=retry_after,
        )

    raise ProviderUnavailableError(
        f"Massive {method} request failed with HTTP {status_code}",
        provider=MASSIVE_PROVIDER,
        method=method,
        status_code=status_code,
    )


def _parse_aggregate_rows(payload: dict[str, Any], ticker: str, start: str, end: str) -> pd.DataFrame:
    from .structured import PRICE_HISTORY_COLUMNS

    rows = normalize_provider_result(
        payload.get("results", []),
        provider=MASSIVE_PROVIDER,
        method="get_price_history",
        role=ProviderResultRole.REQUIRED,
        no_data_message=f"No Massive OHLCV bars found for {ticker.upper()} from {start} to {end}",
        details={"ticker": ticker.upper(), "start": start, "end": end},
    )
    try:
        records = [
            {
                "Date": _timestamp_ms_to_date(row["t"]),
                "Open": float(row["o"]),
                "High": float(row["h"]),
                "Low": float(row["l"]),
                "Close": float(row["c"]),
                "Volume": int(row["v"]),
            }
            for row in rows
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderUnavailableError(
            "Massive get_price_history response was malformed",
            provider=MASSIVE_PROVIDER,
            method="get_price_history",
        ) from exc
    return pd.DataFrame(records, columns=PRICE_HISTORY_COLUMNS)


def get_massive_price_history(
    ticker: str,
    start: str,
    end: str,
    *,
    session: requests.Session | None = None,
) -> PriceHistory:
    from .structured import PriceHistory

    api_key = get_massive_api_key()
    client = session or requests.Session()
    try:
        response = client.get(
            _daily_aggs_url(ticker, start, end),
            params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key},
            timeout=MASSIVE_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        raise ProviderUnavailableError(
            "Massive get_price_history request timed out",
            provider=MASSIVE_PROVIDER,
            method="get_price_history",
        ) from exc
    except requests.RequestException as exc:
        raise ProviderUnavailableError(
            "Massive get_price_history request failed",
            provider=MASSIVE_PROVIDER,
            method="get_price_history",
        ) from exc

    _raise_for_massive_status(response, "get_price_history")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderUnavailableError(
            "Massive get_price_history response was not valid JSON",
            provider=MASSIVE_PROVIDER,
            method="get_price_history",
        ) from exc
    data = _parse_aggregate_rows(payload, ticker, start, end)
    return PriceHistory(ticker=ticker.upper(), start=start, end=end, data=data)
