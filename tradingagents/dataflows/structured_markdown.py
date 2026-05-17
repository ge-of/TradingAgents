"""Markdown renderers for structured equity data contracts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

import pandas as pd

from .structured import DataAvailability, FundamentalsSnapshot, IndicatorSeries, PriceHistory


StructuredMarkdownInput: TypeAlias = FundamentalsSnapshot | PriceHistory | IndicatorSeries


def _format_number(value: float) -> str:
    return f"{value:g}"


def _format_money(value: float) -> str:
    return f"${value:,.0f}"


def _format_percent(value: float) -> str:
    return f"{value:.1%}"


def _format_optional_metric(value: float | None, kind: str = "number") -> str | None:
    if value is None:
        return None
    if kind == "money":
        return _format_money(value)
    if kind == "percent":
        return _format_percent(value)
    return _format_number(value)


def format_data_availability_markdown(availability: Sequence[DataAvailability]) -> str:
    """Render structured availability records as a Markdown section."""
    if not availability:
        return ""

    lines = ["## Data Availability"]
    for item in availability:
        provider_suffix = f" (provider: {item.provider})" if item.provider else ""
        lines.append(f"- {item.field}: {item.status.value} - {item.message}{provider_suffix}")

    return "\n".join(lines)


_FUNDAMENTAL_FIELDS = (
    ("Market Cap", "market_cap", "money"),
    ("PE Ratio (TTM)", "pe_ratio_trailing", "number"),
    ("Forward PE", "pe_ratio_forward", "number"),
    ("Price to Book", "price_to_book", "number"),
    ("Price to Sales", "price_to_sales", "number"),
    ("Enterprise Value", "enterprise_value", "money"),
    ("Revenue (TTM)", "revenue_ttm", "money"),
    ("Net Income (TTM)", "net_income_ttm", "money"),
    ("Free Cash Flow", "free_cash_flow", "money"),
    ("Profit Margin", "profit_margin", "percent"),
    ("Return on Equity", "roe", "percent"),
    ("Total Debt", "total_debt", "money"),
    ("Total Equity", "total_equity", "money"),
    ("Debt to Equity", "debt_to_equity", "number"),
    ("Current Ratio", "current_ratio", "number"),
    ("Dividend Yield", "dividend_yield", "percent"),
    ("Payout Ratio", "payout_ratio", "percent"),
    ("Revenue Growth YoY", "revenue_growth_yoy", "percent"),
    ("Earnings Growth YoY", "earnings_growth_yoy", "percent"),
    ("Free Cash Flow Yield", "free_cash_flow_yield", "percent"),
)


def format_fundamentals_snapshot_markdown(snapshot: FundamentalsSnapshot) -> str:
    """Render a fundamentals snapshot into report-style Markdown."""
    lines = [
        f"# Company Fundamentals for {snapshot.ticker.upper()}",
        f"# As of: {snapshot.as_of}",
        "",
    ]

    for label, attr, kind in _FUNDAMENTAL_FIELDS:
        rendered = _format_optional_metric(getattr(snapshot, attr), kind)
        if rendered is not None:
            lines.append(f"{label}: {rendered}")

    availability = format_data_availability_markdown(snapshot.availability)
    if availability:
        lines.extend(["", availability])

    return "\n".join(lines).rstrip() + "\n"


def _dataframe_to_csv(frame: pd.DataFrame) -> str:
    return frame.to_csv(index=False).strip()


def format_price_history_markdown(history: PriceHistory) -> str:
    """Render structured OHLCV price history into report-style Markdown."""
    lines = [
        f"# Stock data for {history.ticker.upper()} from {history.start} to {history.end}",
        f"# Total records: {len(history.data)}",
    ]

    if history.high_52w is not None:
        lines.append(f"52 Week High: {_format_number(history.high_52w)}")
    if history.low_52w is not None:
        lines.append(f"52 Week Low: {_format_number(history.low_52w)}")
    if history.proximity_to_52w_high is not None:
        lines.append(f"Proximity to 52 Week High: {_format_percent(history.proximity_to_52w_high)}")

    lines.extend(["", _dataframe_to_csv(history.data)])

    availability = format_data_availability_markdown(history.availability)
    if availability:
        lines.extend(["", availability])

    return "\n".join(lines).rstrip() + "\n"


def _indicator_value_column(values: pd.DataFrame, indicator: str) -> str | None:
    for candidate in (indicator, indicator.upper()):
        if candidate in values.columns:
            return candidate

    for column in values.columns:
        if column != "Date":
            return column

    return None


def format_indicator_series_markdown(series: IndicatorSeries) -> str:
    """Render a structured indicator series into report-style Markdown."""
    value_column = _indicator_value_column(series.values, series.indicator)
    start = (
        str(series.values["Date"].iloc[0])
        if "Date" in series.values.columns and not series.values.empty
        else series.as_of
    )
    heading = f"## {series.indicator.upper()} values from {start} to {series.as_of}:"
    lines = [heading, ""]

    if value_column is None or "Date" not in series.values.columns:
        lines.append("No indicator values available.")
    else:
        for _, row in series.values.iterrows():
            lines.append(f"{row['Date']}: {row[value_column]}")

    if series.latest_value is not None:
        lines.extend(["", f"Latest {series.indicator.upper()}: {series.latest_value}"])

    availability = format_data_availability_markdown(series.availability)
    if availability:
        lines.extend(["", availability])

    return "\n".join(lines).rstrip() + "\n"


def format_structured_data_markdown(result: StructuredMarkdownInput) -> str:
    """Dispatch a supported structured data object to its Markdown renderer."""
    if isinstance(result, FundamentalsSnapshot):
        return format_fundamentals_snapshot_markdown(result)
    if isinstance(result, PriceHistory):
        return format_price_history_markdown(result)
    if isinstance(result, IndicatorSeries):
        return format_indicator_series_markdown(result)

    raise TypeError("Unsupported structured data type for Markdown formatting")


__all__ = [
    "StructuredMarkdownInput",
    "format_data_availability_markdown",
    "format_fundamentals_snapshot_markdown",
    "format_indicator_series_markdown",
    "format_price_history_markdown",
    "format_structured_data_markdown",
]
