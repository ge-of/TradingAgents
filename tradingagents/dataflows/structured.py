"""Structured equity data contracts for provider-neutral consumers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
import re
from typing import Any

import pandas as pd

from .config import get_config
from .exceptions import DataProviderError, ProviderNoDataError


PRICE_HISTORY_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume")

StructuredProvider = Callable[..., Any]

STRUCTURED_METHOD_CATEGORIES = {
    "get_price_history": "core_stock_apis",
    "get_fundamentals_snapshot": "fundamental_data",
    "get_indicator_series": "technical_indicators",
}

STRUCTURED_VENDOR_METHODS: dict[str, dict[str, StructuredProvider]] = {
    "get_price_history": {},
    "get_fundamentals_snapshot": {},
    "get_indicator_series": {},
}
EXPLICIT_ONLY_STRUCTURED_VENDORS = {"massive"}


class AvailabilityStatus(str, Enum):
    """Availability status for structured fields or child datasets."""

    AVAILABLE = "available"
    MISSING = "missing"
    STALE = "stale"


@dataclass
class DataAvailability:
    """Availability metadata for a structured field or child dataset."""

    field: str
    status: AvailabilityStatus
    message: str
    provider: str | None = None


@dataclass
class FundamentalsSnapshot:
    """Structured fundamentals data for a single ticker at a point in time."""

    ticker: str
    as_of: str
    market_cap: float | None = None
    pe_ratio_trailing: float | None = None
    pe_ratio_forward: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    enterprise_value: float | None = None
    revenue_ttm: float | None = None
    net_income_ttm: float | None = None
    free_cash_flow: float | None = None
    profit_margin: float | None = None
    roe: float | None = None
    total_debt: float | None = None
    total_equity: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    dividend_yield: float | None = None
    payout_ratio: float | None = None
    revenue_growth_yoy: float | None = None
    earnings_growth_yoy: float | None = None
    free_cash_flow_yield: float | None = None
    availability: list[DataAvailability] = field(default_factory=list)


@dataclass
class PriceHistory:
    """OHLCV price history for a ticker."""

    ticker: str
    start: str
    end: str
    data: pd.DataFrame
    high_52w: float | None = None
    low_52w: float | None = None
    proximity_to_52w_high: float | None = None
    availability: list[DataAvailability] = field(default_factory=list)


@dataclass
class IndicatorSeries:
    """Technical indicator values for a ticker."""

    ticker: str
    indicator: str
    as_of: str
    window: int
    values: pd.DataFrame
    latest_value: float | None = None
    availability: list[DataAvailability] = field(default_factory=list)


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_iso_date(value: str, field_name: str) -> date:
    if not isinstance(value, str) or not _ISO_DATE_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a YYYY-MM-DD date")

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid YYYY-MM-DD date") from exc


def _normalize_iso_date(value: str, field_name: str) -> str:
    return _parse_iso_date(value, field_name).isoformat()


def _filter_required_frame_by_date(
    frame: pd.DataFrame,
    *,
    ticker: str,
    method: str,
    provider: str | None,
    start: date | None = None,
    end: date,
) -> pd.DataFrame:
    if "Date" not in frame.columns:
        raise ProviderNoDataError(
            f"No usable dated rows returned for {ticker}",
            provider=provider,
            method=method,
            details={"ticker": ticker, "reason": "missing_date_column"},
        )

    working = frame.copy()
    parsed_dates = pd.to_datetime(working["Date"], errors="coerce")
    mask = parsed_dates.notna() & (parsed_dates.dt.date <= end)
    if start is not None:
        mask &= parsed_dates.dt.date >= start

    filtered = working.loc[mask].copy()
    if filtered.empty:
        details = {"ticker": ticker, "end": end.isoformat()}
        if start is not None:
            details["start"] = start.isoformat()
        raise ProviderNoDataError(
            f"No usable dated rows returned for {ticker} within the requested as-of window",
            provider=provider,
            method=method,
            details=details,
        )

    filtered_dates = parsed_dates.loc[filtered.index]
    ordered_index = filtered_dates.sort_values(kind="mergesort").index
    filtered = filtered.loc[ordered_index].copy()
    filtered["Date"] = parsed_dates.loc[ordered_index].dt.strftime("%Y-%m-%d").to_numpy()
    return filtered.reset_index(drop=True)


def _enforce_price_history_contract(history: PriceHistory, start: date, end: date) -> PriceHistory:
    filtered = _filter_required_frame_by_date(
        history.data,
        ticker=history.ticker,
        method="get_price_history",
        provider=None,
        start=start,
        end=end,
    )

    high_52w = float(filtered["High"].max()) if "High" in filtered.columns else None
    low_52w = float(filtered["Low"].min()) if "Low" in filtered.columns else None
    latest_close = float(filtered["Close"].iloc[-1]) if "Close" in filtered.columns else None
    proximity = None
    if high_52w not in (None, 0.0) and latest_close is not None:
        proximity = (latest_close / high_52w) - 1

    return PriceHistory(
        ticker=history.ticker,
        start=start.isoformat(),
        end=end.isoformat(),
        data=filtered,
        high_52w=high_52w,
        low_52w=low_52w,
        proximity_to_52w_high=proximity,
        availability=history.availability,
    )


def _enforce_fundamentals_contract(
    snapshot: FundamentalsSnapshot,
    requested_as_of: date,
) -> FundamentalsSnapshot:
    snapshot_as_of = _parse_iso_date(snapshot.as_of, "snapshot.as_of")
    if snapshot_as_of > requested_as_of:
        raise ProviderNoDataError(
            f"No usable fundamentals snapshot for {snapshot.ticker} on or before {requested_as_of.isoformat()}",
            provider=None,
            method="get_fundamentals_snapshot",
            details={
                "ticker": snapshot.ticker,
                "as_of": requested_as_of.isoformat(),
                "snapshot_as_of": snapshot.as_of,
            },
        )
    return snapshot


def _latest_numeric_indicator_value(values: pd.DataFrame, indicator: str) -> float | None:
    candidate_columns = [indicator, indicator.upper()]
    candidate_columns.extend(col for col in values.columns if col not in {"Date", indicator, indicator.upper()})

    for column in candidate_columns:
        if column not in values.columns:
            continue
        numeric_values = pd.to_numeric(values[column], errors="coerce").dropna()
        if not numeric_values.empty:
            return float(numeric_values.iloc[-1])

    return None


def _enforce_indicator_series_contract(series: IndicatorSeries, requested_as_of: date) -> IndicatorSeries:
    filtered = _filter_required_frame_by_date(
        series.values,
        ticker=series.ticker,
        method="get_indicator_series",
        provider=None,
        end=requested_as_of,
    )

    return IndicatorSeries(
        ticker=series.ticker,
        indicator=series.indicator,
        as_of=requested_as_of.isoformat(),
        window=series.window,
        values=filtered,
        latest_value=_latest_numeric_indicator_value(filtered, series.indicator),
        availability=series.availability,
    )


def _get_structured_vendor_config(method: str) -> str:
    if method not in STRUCTURED_METHOD_CATEGORIES:
        raise ValueError(f"Structured method '{method}' not supported")

    config = get_config()
    tool_vendors = config.get("tool_vendors", {})
    if method in tool_vendors:
        return tool_vendors[method]

    category = STRUCTURED_METHOD_CATEGORIES[method]
    return config.get("data_vendors", {}).get(category, "default")


def _configured_structured_vendors(method: str) -> list[str]:
    vendor_config = _get_structured_vendor_config(method)
    return [vendor.strip() for vendor in vendor_config.split(",") if vendor.strip()]


def _build_structured_fallback_chain(method: str) -> list[str]:
    configured_vendors = _configured_structured_vendors(method)
    available_vendors = list(STRUCTURED_VENDOR_METHODS[method].keys())

    fallback_chain = configured_vendors.copy()
    for vendor in available_vendors:
        if vendor not in fallback_chain:
            if vendor in EXPLICIT_ONLY_STRUCTURED_VENDORS:
                continue
            fallback_chain.append(vendor)

    return fallback_chain


def route_structured_method(method: str, *args: Any, **kwargs: Any) -> Any:
    """Route a structured data request to the configured structured provider."""
    if method not in STRUCTURED_VENDOR_METHODS:
        raise ValueError(f"Structured method '{method}' not supported")

    configured_vendors = set(_configured_structured_vendors(method))
    for vendor in _build_structured_fallback_chain(method):
        provider_impl = STRUCTURED_VENDOR_METHODS[method].get(vendor)
        if provider_impl is None:
            continue

        try:
            return provider_impl(*args, **kwargs)
        except DataProviderError as exc:
            if vendor in EXPLICIT_ONLY_STRUCTURED_VENDORS and vendor in configured_vendors:
                raise exc
            continue

    raise RuntimeError(f"No available structured provider for '{method}'")


def get_price_history(ticker: str, start: str, end: str) -> PriceHistory:
    """Return structured OHLCV history from the configured structured provider."""
    start_date = _parse_iso_date(start, "start")
    end_date = _parse_iso_date(end, "end")
    if start_date > end_date:
        raise ValueError("start must be on or before end")

    history = route_structured_method("get_price_history", ticker, start_date.isoformat(), end_date.isoformat())
    return _enforce_price_history_contract(history, start_date, end_date)


def get_fundamentals_snapshot(ticker: str, as_of: str) -> FundamentalsSnapshot:
    """Return structured fundamentals from the configured structured provider."""
    as_of_date = _parse_iso_date(as_of, "as_of")
    snapshot = route_structured_method("get_fundamentals_snapshot", ticker, as_of_date.isoformat())
    return _enforce_fundamentals_contract(snapshot, as_of_date)


def get_indicator_series(
    ticker: str,
    indicator: str,
    as_of: str,
    window: int,
) -> IndicatorSeries:
    """Return structured technical indicators from the configured structured provider."""
    as_of_date = _parse_iso_date(as_of, "as_of")
    if not isinstance(window, int) or window <= 0:
        raise ValueError("window must be a positive integer")

    series = route_structured_method(
        "get_indicator_series",
        ticker,
        indicator,
        as_of_date.isoformat(),
        window,
    )
    return _enforce_indicator_series_contract(series, as_of_date)


from .massive import get_massive_price_history as _get_massive_price_history

STRUCTURED_VENDOR_METHODS["get_price_history"]["massive"] = _get_massive_price_history


__all__ = [
    "AvailabilityStatus",
    "DataAvailability",
    "FundamentalsSnapshot",
    "IndicatorSeries",
    "PRICE_HISTORY_COLUMNS",
    "PriceHistory",
    "STRUCTURED_METHOD_CATEGORIES",
    "STRUCTURED_VENDOR_METHODS",
    "get_fundamentals_snapshot",
    "get_indicator_series",
    "get_price_history",
    "route_structured_method",
]
