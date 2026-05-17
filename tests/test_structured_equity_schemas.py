import copy

import pandas as pd
import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from tradingagents.dataflows import structured
from tradingagents.dataflows.exceptions import ProviderNoDataError
from tradingagents.dataflows.structured import (
    AvailabilityStatus,
    DataAvailability,
    FundamentalsSnapshot,
    IndicatorSeries,
    PRICE_HISTORY_COLUMNS,
    PriceHistory,
    TickerDetails,
)


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


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


@pytest.mark.unit
def test_ticker_details_tracks_reference_metadata_and_availability():
    availability = [
        DataAvailability(
            field="currency",
            status=AvailabilityStatus.MISSING,
            message="Massive response did not include currency",
            provider="massive",
        )
    ]

    details = TickerDetails(
        ticker="AAPL",
        as_of="2026-05-16",
        name="Apple Inc.",
        market="stocks",
        exchange="XNAS",
        currency=None,
        locale="us",
        active=True,
        availability=availability,
    )

    assert details.ticker == "AAPL"
    assert details.as_of == "2026-05-16"
    assert details.name == "Apple Inc."
    assert details.market == "stocks"
    assert details.exchange == "XNAS"
    assert details.currency is None
    assert details.locale == "us"
    assert details.active is True
    assert details.availability == availability


@pytest.mark.unit
def test_get_ticker_details_routes_through_core_stock_config(monkeypatch):
    calls = []

    def fake_details(ticker: str, as_of: str) -> TickerDetails:
        calls.append((ticker, as_of))
        return TickerDetails(ticker=ticker, as_of=as_of, name="Apple Inc.")

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_ticker_details"],
        "fake_details",
        fake_details,
    )
    config_module.set_config({"data_vendors": {"core_stock_apis": "fake_details"}})

    details = structured.get_ticker_details("AAPL", "2026-05-16")

    assert details.name == "Apple Inc."
    assert calls == [("AAPL", "2026-05-16")]


@pytest.mark.unit
def test_get_ticker_details_rejects_invalid_as_of_before_provider_call(monkeypatch):
    calls = []

    def should_not_run(ticker: str, as_of: str) -> TickerDetails:
        calls.append((ticker, as_of))
        return TickerDetails(ticker=ticker, as_of=as_of)

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_ticker_details"],
        "fake_details",
        should_not_run,
    )
    config_module.set_config({"data_vendors": {"core_stock_apis": "fake_details"}})

    with pytest.raises(ValueError, match="as_of must be a YYYY-MM-DD date"):
        structured.get_ticker_details("AAPL", "2026/05/16")

    assert calls == []


@pytest.mark.unit
def test_get_ticker_details_rejects_provider_metadata_after_as_of(monkeypatch):
    def future_details(ticker: str, as_of: str) -> TickerDetails:
        return TickerDetails(ticker=ticker, as_of="2026-05-17")

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_ticker_details"],
        "future_details",
        future_details,
    )
    config_module.set_config({"data_vendors": {"core_stock_apis": "future_details"}})

    with pytest.raises(ProviderNoDataError) as exc_info:
        structured.get_ticker_details("AAPL", "2026-05-16")

    assert exc_info.value.method == "get_ticker_details"
    assert exc_info.value.details == {
        "ticker": "AAPL",
        "as_of": "2026-05-16",
        "details_as_of": "2026-05-17",
    }
