import pandas as pd
import pytest

from tradingagents.dataflows.structured import (
    AvailabilityStatus,
    DataAvailability,
    FundamentalsSnapshot,
    IndicatorSeries,
    PRICE_HISTORY_COLUMNS,
    PriceHistory,
)


@pytest.mark.unit
def test_fundamentals_snapshot_defaults_optional_metrics_and_availability():
    availability = [
        DataAvailability(
            field="price_to_book",
            status=AvailabilityStatus.MISSING,
            message="Provider did not return price_to_book",
            provider="yfinance",
        )
    ]

    snapshot = FundamentalsSnapshot(
        ticker="AAPL",
        as_of="2026-05-16",
        market_cap=3_000_000_000_000,
        pe_ratio_trailing=28.5,
        availability=availability,
    )

    assert snapshot.ticker == "AAPL"
    assert snapshot.as_of == "2026-05-16"
    assert snapshot.market_cap == 3_000_000_000_000
    assert snapshot.pe_ratio_trailing == 28.5
    assert snapshot.pe_ratio_forward is None
    assert snapshot.price_to_book is None
    assert snapshot.free_cash_flow_yield is None
    assert snapshot.availability == availability


@pytest.mark.unit
def test_schema_availability_lists_do_not_share_mutable_defaults():
    first = FundamentalsSnapshot(ticker="AAPL", as_of="2026-05-16")
    second = FundamentalsSnapshot(ticker="MSFT", as_of="2026-05-16")

    first.availability.append(
        DataAvailability(
            field="market_cap",
            status=AvailabilityStatus.MISSING,
            message="missing market cap",
        )
    )

    assert len(first.availability) == 1
    assert second.availability == []


@pytest.mark.unit
def test_price_history_tracks_ohlcv_dataframe_and_derived_metrics():
    data = pd.DataFrame(
        {
            "Date": ["2026-05-15"],
            "Open": [100.0],
            "High": [105.0],
            "Low": [99.0],
            "Close": [104.0],
            "Volume": [1_000_000],
        }
    )

    history = PriceHistory(
        ticker="AAPL",
        start="2026-05-01",
        end="2026-05-16",
        data=data,
        high_52w=110.0,
        low_52w=80.0,
        proximity_to_52w_high=-0.0545,
    )

    assert PRICE_HISTORY_COLUMNS == ("Date", "Open", "High", "Low", "Close", "Volume")
    assert history.data is data
    assert tuple(history.data.columns) == PRICE_HISTORY_COLUMNS
    assert history.high_52w == 110.0
    assert history.low_52w == 80.0
    assert history.proximity_to_52w_high == -0.0545
    assert history.availability == []


@pytest.mark.unit
def test_indicator_series_and_availability_metadata_are_importable_contracts():
    values = pd.DataFrame({"Date": ["2026-05-15"], "RSI": [62.3]})
    availability = DataAvailability(
        field="latest_value",
        status=AvailabilityStatus.AVAILABLE,
        message="latest RSI value available",
        provider="alpha_vantage",
    )

    series = IndicatorSeries(
        ticker="AAPL",
        indicator="rsi",
        as_of="2026-05-16",
        window=14,
        values=values,
        latest_value=62.3,
        availability=[availability],
    )

    assert series.ticker == "AAPL"
    assert series.indicator == "rsi"
    assert series.as_of == "2026-05-16"
    assert series.window == 14
    assert series.values is values
    assert series.latest_value == 62.3
    assert series.availability == [availability]
    assert AvailabilityStatus.MISSING.value == "missing"
    assert AvailabilityStatus.STALE.value == "stale"
