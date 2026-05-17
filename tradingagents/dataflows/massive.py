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
    from .structured import CorporateActions, DividendEvent, PriceHistory, SplitEvent, TickerDetails

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


def _ticker_details_url(ticker: str) -> str:
    return f"{MASSIVE_BASE_URL}/v3/reference/tickers/{ticker.upper()}"


def _dividends_url() -> str:
    return f"{MASSIVE_BASE_URL}/v3/reference/dividends"


def _splits_url() -> str:
    return f"{MASSIVE_BASE_URL}/v3/reference/splits"


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


def _is_missing_reference_field(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _missing_ticker_detail_availability(field: str):
    from .structured import AvailabilityStatus, DataAvailability

    return DataAvailability(
        field=field,
        status=AvailabilityStatus.MISSING,
        message=f"Massive response did not include {field}",
        provider=MASSIVE_PROVIDER,
    )


def _parse_ticker_details(payload: dict[str, Any], ticker: str, as_of: str) -> TickerDetails:
    from .structured import TickerDetails

    if not isinstance(payload, dict):
        raise ProviderUnavailableError(
            "Massive get_ticker_details response was malformed",
            provider=MASSIVE_PROVIDER,
            method="get_ticker_details",
        )

    raw_details = normalize_provider_result(
        payload.get("results"),
        provider=MASSIVE_PROVIDER,
        method="get_ticker_details",
        role=ProviderResultRole.REQUIRED,
        no_data_message=f"No Massive ticker details found for {ticker.upper()} as of {as_of}",
        details={"ticker": ticker.upper(), "as_of": as_of},
    )
    if not isinstance(raw_details, dict):
        raise ProviderUnavailableError(
            "Massive get_ticker_details response was malformed",
            provider=MASSIVE_PROVIDER,
            method="get_ticker_details",
        )

    fields = {
        "name": raw_details.get("name"),
        "market": raw_details.get("market"),
        "exchange": raw_details.get("primary_exchange"),
        "currency": raw_details.get("currency_name"),
        "locale": raw_details.get("locale"),
        "active": raw_details.get("active"),
    }
    availability = [
        _missing_ticker_detail_availability(field)
        for field, value in fields.items()
        if _is_missing_reference_field(value)
    ]
    result_ticker = raw_details.get("ticker") or ticker

    return TickerDetails(
        ticker=str(result_ticker).upper(),
        as_of=as_of,
        name=fields["name"],
        market=fields["market"],
        exchange=fields["exchange"],
        currency=fields["currency"],
        locale=fields["locale"],
        active=fields["active"],
        availability=availability,
    )


def _corporate_action_details(params: dict[str, Any]) -> dict[str, Any]:
    start = params.get("ex_dividend_date.gte") or params.get("execution_date.gte") or params.get("date.gte")
    end = params.get("ex_dividend_date.lte") or params.get("execution_date.lte") or params.get("date.lte")
    return {"ticker": params.get("ticker"), "start": start, "end": end}


def _malformed_corporate_actions_error() -> ProviderUnavailableError:
    return ProviderUnavailableError(
        "Massive get_corporate_actions response was malformed",
        provider=MASSIVE_PROVIDER,
        method="get_corporate_actions",
    )


def _get_optional_massive_results(
    client: requests.Session,
    url: str,
    params: dict[str, Any],
    method: str,
) -> list[dict[str, Any]]:
    try:
        response = client.get(url, params=params, timeout=MASSIVE_TIMEOUT_SECONDS)
    except requests.Timeout as exc:
        raise ProviderUnavailableError(
            f"Massive {method} request timed out",
            provider=MASSIVE_PROVIDER,
            method=method,
        ) from exc
    except requests.RequestException as exc:
        raise ProviderUnavailableError(
            f"Massive {method} request failed",
            provider=MASSIVE_PROVIDER,
            method=method,
        ) from exc

    _raise_for_massive_status(response, method)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderUnavailableError(
            f"Massive {method} response was not valid JSON",
            provider=MASSIVE_PROVIDER,
            method=method,
        ) from exc

    if not isinstance(payload, dict):
        raise _malformed_corporate_actions_error()

    rows = normalize_provider_result(
        payload.get("results", []),
        provider=MASSIVE_PROVIDER,
        method=method,
        role=ProviderResultRole.OPTIONAL,
        details=_corporate_action_details(params),
    )
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise _malformed_corporate_actions_error()

    return rows


def _parse_dividend(row: dict[str, Any]) -> DividendEvent:
    from .structured import DividendEvent

    ex_dividend_date = row.get("ex_dividend_date")
    if not isinstance(ex_dividend_date, str) or not ex_dividend_date.strip():
        raise _malformed_corporate_actions_error()

    return DividendEvent(
        ticker=str(row.get("ticker", "")).upper(),
        ex_dividend_date=ex_dividend_date,
        pay_date=row.get("pay_date"),
        cash_amount=float(row["cash_amount"]) if row.get("cash_amount") is not None else None,
        currency=row.get("currency"),
    )


def _parse_split(row: dict[str, Any]) -> SplitEvent:
    from .structured import SplitEvent

    execution_date = row.get("execution_date")
    if not isinstance(execution_date, str) or not execution_date.strip():
        raise _malformed_corporate_actions_error()

    return SplitEvent(
        ticker=str(row.get("ticker", "")).upper(),
        execution_date=execution_date,
        split_from=float(row.get("split_from")),
        split_to=float(row.get("split_to")),
    )


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


def get_massive_ticker_details(
    ticker: str,
    as_of: str,
    *,
    session: requests.Session | None = None,
) -> TickerDetails:
    api_key = get_massive_api_key()
    client = session or requests.Session()
    try:
        response = client.get(
            _ticker_details_url(ticker),
            params={"date": as_of, "apiKey": api_key},
            timeout=MASSIVE_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        raise ProviderUnavailableError(
            "Massive get_ticker_details request timed out",
            provider=MASSIVE_PROVIDER,
            method="get_ticker_details",
        ) from exc
    except requests.RequestException as exc:
        raise ProviderUnavailableError(
            "Massive get_ticker_details request failed",
            provider=MASSIVE_PROVIDER,
            method="get_ticker_details",
        ) from exc

    _raise_for_massive_status(response, "get_ticker_details")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderUnavailableError(
            "Massive get_ticker_details response was not valid JSON",
            provider=MASSIVE_PROVIDER,
            method="get_ticker_details",
        ) from exc
    return _parse_ticker_details(payload, ticker, as_of)


def get_massive_corporate_actions(
    ticker: str,
    start: str,
    end: str,
    *,
    session: requests.Session | None = None,
) -> CorporateActions:
    from .structured import CorporateActions

    api_key = get_massive_api_key()
    client = session or requests.Session()
    normalized_ticker = ticker.upper()
    dividend_rows = _get_optional_massive_results(
        client,
        _dividends_url(),
        {
            "ticker": normalized_ticker,
            "ex_dividend_date.gte": start,
            "ex_dividend_date.lte": end,
            "apiKey": api_key,
        },
        "get_corporate_actions",
    )
    split_rows = _get_optional_massive_results(
        client,
        _splits_url(),
        {
            "ticker": normalized_ticker,
            "execution_date.gte": start,
            "execution_date.lte": end,
            "apiKey": api_key,
        },
        "get_corporate_actions",
    )
    try:
        dividends = [_parse_dividend(row) for row in dividend_rows]
        splits = [_parse_split(row) for row in split_rows]
    except (KeyError, TypeError, ValueError) as exc:
        raise _malformed_corporate_actions_error() from exc

    return CorporateActions(
        ticker=normalized_ticker,
        start=start,
        end=end,
        dividends=dividends,
        splits=splits,
    )
