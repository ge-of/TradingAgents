"""Structured equity data contracts for provider-neutral consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import pandas as pd


PRICE_HISTORY_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume")


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


__all__ = [
    "AvailabilityStatus",
    "DataAvailability",
    "FundamentalsSnapshot",
    "IndicatorSeries",
    "PRICE_HISTORY_COLUMNS",
    "PriceHistory",
]
