"""Structured equity data contracts for provider-neutral consumers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd

from .config import get_config
from .exceptions import DataProviderError


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


def _get_structured_vendor_config(method: str) -> str:
    if method not in STRUCTURED_METHOD_CATEGORIES:
        raise ValueError(f"Structured method '{method}' not supported")

    config = get_config()
    tool_vendors = config.get("tool_vendors", {})
    if method in tool_vendors:
        return tool_vendors[method]

    category = STRUCTURED_METHOD_CATEGORIES[method]
    return config.get("data_vendors", {}).get(category, "default")


def _build_structured_fallback_chain(method: str) -> list[str]:
    vendor_config = _get_structured_vendor_config(method)
    configured_vendors = [vendor.strip() for vendor in vendor_config.split(",") if vendor.strip()]
    available_vendors = list(STRUCTURED_VENDOR_METHODS[method].keys())

    fallback_chain = configured_vendors.copy()
    for vendor in available_vendors:
        if vendor not in fallback_chain:
            fallback_chain.append(vendor)

    return fallback_chain


def route_structured_method(method: str, *args: Any, **kwargs: Any) -> Any:
    """Route a structured data request to the configured structured provider."""
    if method not in STRUCTURED_VENDOR_METHODS:
        raise ValueError(f"Structured method '{method}' not supported")

    for vendor in _build_structured_fallback_chain(method):
        provider_impl = STRUCTURED_VENDOR_METHODS[method].get(vendor)
        if provider_impl is None:
            continue

        try:
            return provider_impl(*args, **kwargs)
        except DataProviderError:
            continue

    raise RuntimeError(f"No available structured provider for '{method}'")


def get_price_history(ticker: str, start: str, end: str) -> PriceHistory:
    """Return structured OHLCV history from the configured structured provider."""
    return route_structured_method("get_price_history", ticker, start, end)


def get_fundamentals_snapshot(ticker: str, as_of: str) -> FundamentalsSnapshot:
    """Return structured fundamentals from the configured structured provider."""
    return route_structured_method("get_fundamentals_snapshot", ticker, as_of)


def get_indicator_series(
    ticker: str,
    indicator: str,
    as_of: str,
    window: int,
) -> IndicatorSeries:
    """Return structured technical indicators from the configured structured provider."""
    return route_structured_method("get_indicator_series", ticker, indicator, as_of, window)


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
