"""Massive provider identity and credential helpers."""

from __future__ import annotations

from collections.abc import Mapping
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


def _safe_massive_details(
    path: str,
    params: Mapping[str, object],
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    safe_params = {key: value for key, value in params.items() if key != "apiKey"}
    details: dict[str, object] = {"path": path, **safe_params}
    if extra:
        details.update(extra)
    return details


def _massive_url(path: str) -> str:
    return f"{MASSIVE_BASE_URL}{path}"


def _raise_massive_status_error(
    response: requests.Response,
    *,
    path: str,
    params: Mapping[str, object],
    method: str,
) -> None:
    status_code = response.status_code
    if status_code == 200:
        return

    details = _safe_massive_details(path, params, {"status_code": status_code})
    if status_code in {401, 403}:
        raise ProviderAuthError(
            f"Massive {method} request was rejected with HTTP {status_code}",
            provider=MASSIVE_PROVIDER,
            method=method,
            status_code=status_code,
            details=details,
        )

    if status_code == 429:
        retry_after_header = response.headers.get("Retry-After")
        retry_after = (
            int(retry_after_header.strip())
            if retry_after_header and retry_after_header.strip().isdigit()
            else None
        )
        raise ProviderRateLimitError(
            "Massive rate limit exceeded",
            provider=MASSIVE_PROVIDER,
            method=method,
            status_code=status_code,
            retry_after=retry_after,
            details=details,
        )

    raise ProviderUnavailableError(
        f"Massive {method} request failed with HTTP {status_code}",
        provider=MASSIVE_PROVIDER,
        method=method,
        status_code=status_code,
        details=details,
    )


def request_massive_json(
    path: str,
    params: Mapping[str, object],
    *,
    method: str,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    api_key = get_massive_api_key()
    request_params = {**dict(params), "apiKey": api_key}
    client = session or requests.Session()
    try:
        response = client.get(
            _massive_url(path),
            params=request_params,
            timeout=MASSIVE_TIMEOUT_SECONDS,
        )
    except requests.Timeout:
        raise ProviderUnavailableError(
            f"Massive {method} request timed out",
            provider=MASSIVE_PROVIDER,
            method=method,
            details=_safe_massive_details(path, request_params),
        ) from None
    except requests.RequestException:
        raise ProviderUnavailableError(
            f"Massive {method} request failed",
            provider=MASSIVE_PROVIDER,
            method=method,
            details=_safe_massive_details(path, request_params),
        ) from None

    _raise_massive_status_error(response, path=path, params=request_params, method=method)
    try:
        payload = response.json()
    except ValueError:
        raise ProviderUnavailableError(
            f"Massive {method} response was not valid JSON",
            provider=MASSIVE_PROVIDER,
            method=method,
            details=_safe_massive_details(path, request_params),
        ) from None

    if not isinstance(payload, dict):
        raise ProviderUnavailableError(
            f"Massive {method} response JSON was not an object",
            provider=MASSIVE_PROVIDER,
            method=method,
            details=_safe_massive_details(path, request_params),
        )
    return payload


def _timestamp_ms_to_date(value: int | float) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()


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
    path: str,
    params: dict[str, Any],
    method: str,
    *,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    payload = request_massive_json(path, params, method=method, session=session)
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

    payload = request_massive_json(
        f"/v2/aggs/ticker/{ticker.upper()}/range/1/day/{start}/{end}",
        {"adjusted": "true", "sort": "asc", "limit": 50000},
        method="get_price_history",
        session=session,
    )
    data = _parse_aggregate_rows(payload, ticker, start, end)
    return PriceHistory(ticker=ticker.upper(), start=start, end=end, data=data)


def get_massive_ticker_details(
    ticker: str,
    as_of: str,
    *,
    session: requests.Session | None = None,
) -> TickerDetails:
    payload = request_massive_json(
        f"/v3/reference/tickers/{ticker.upper()}",
        {"date": as_of},
        method="get_ticker_details",
        session=session,
    )
    return _parse_ticker_details(payload, ticker, as_of)


def get_massive_corporate_actions(
    ticker: str,
    start: str,
    end: str,
    *,
    session: requests.Session | None = None,
) -> CorporateActions:
    from .structured import CorporateActions

    client = session or requests.Session()
    normalized_ticker = ticker.upper()
    dividend_rows = _get_optional_massive_results(
        "/v3/reference/dividends",
        {
            "ticker": normalized_ticker,
            "ex_dividend_date.gte": start,
            "ex_dividend_date.lte": end,
        },
        "get_corporate_actions",
        session=client,
    )
    split_rows = _get_optional_massive_results(
        "/v3/reference/splits",
        {
            "ticker": normalized_ticker,
            "execution_date.gte": start,
            "execution_date.lte": end,
        },
        "get_corporate_actions",
        session=client,
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
