import copy

import pandas as pd
import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from tradingagents.dataflows import structured
from tradingagents.dataflows.exceptions import DataProviderError, ProviderUnavailableError
from tradingagents.dataflows.structured import (
    FundamentalsSnapshot,
    IndicatorSeries,
    PriceHistory,
)


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


@pytest.mark.unit
def test_get_price_history_uses_category_configured_structured_provider(monkeypatch):
    calls = []

    def fake_price_history(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append((ticker, start, end))
        return PriceHistory(
            ticker=ticker,
            start=start,
            end=end,
            data=pd.DataFrame(
                {
                    "Date": ["2026-05-15"],
                    "Open": [100.0],
                    "High": [105.0],
                    "Low": [99.0],
                    "Close": [104.0],
                    "Volume": [1_000_000],
                }
            ),
        )

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "fake_prices",
        fake_price_history,
    )
    config_module.set_config({"data_vendors": {"core_stock_apis": "fake_prices"}})

    result = structured.get_price_history("AAPL", "2026-05-01", "2026-05-16")

    assert isinstance(result, PriceHistory)
    assert result.ticker == "AAPL"
    assert result.start == "2026-05-01"
    assert result.end == "2026-05-16"
    assert calls == [("AAPL", "2026-05-01", "2026-05-16")]


@pytest.mark.unit
def test_structured_tool_vendor_overrides_category_vendor(monkeypatch):
    calls = []

    def category_provider(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append("category")
        return PriceHistory(ticker=ticker, start=start, end=end, data=pd.DataFrame())

    def override_provider(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append("override")
        return PriceHistory(
            ticker=ticker,
            start=start,
            end=end,
            data=pd.DataFrame({"Date": ["2026-05-15"]}),
        )

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "category_prices",
        category_provider,
    )
    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "override_prices",
        override_provider,
    )
    config_module.set_config(
        {
            "data_vendors": {"core_stock_apis": "category_prices"},
            "tool_vendors": {"get_price_history": "override_prices"},
        }
    )

    result = structured.get_price_history("MSFT", "2026-05-01", "2026-05-16")

    assert result.data["Date"].tolist() == ["2026-05-15"]
    assert calls == ["override"]


@pytest.mark.unit
def test_structured_entry_point_falls_back_on_data_provider_error(monkeypatch):
    calls = []

    def failing_provider(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append("primary")
        raise ProviderUnavailableError(
            "primary unavailable",
            provider="primary_prices",
            method="get_price_history",
        )

    def fallback_provider(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append("fallback")
        return PriceHistory(
            ticker=ticker,
            start=start,
            end=end,
            data=pd.DataFrame({"Date": ["2026-05-15"], "Close": [104.0]}),
        )

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "primary_prices",
        failing_provider,
    )
    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "fallback_prices",
        fallback_provider,
    )
    config_module.set_config({"data_vendors": {"core_stock_apis": "primary_prices"}})

    result = structured.get_price_history("NVDA", "2026-05-01", "2026-05-16")

    assert result.ticker == "NVDA"
    assert calls == ["primary", "fallback"]


@pytest.mark.unit
def test_structured_entry_point_raises_runtime_error_when_no_provider_succeeds(monkeypatch):
    calls = []

    def failing_provider(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append("primary")
        raise DataProviderError(
            "provider failed",
            provider="primary_prices",
            method="get_price_history",
        )

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "primary_prices",
        failing_provider,
    )
    config_module.set_config({"data_vendors": {"core_stock_apis": "primary_prices"}})

    with pytest.raises(
        RuntimeError,
        match="No available structured provider for 'get_price_history'",
    ):
        structured.get_price_history("NVDA", "2026-05-01", "2026-05-16")

    assert calls == ["primary"]


@pytest.mark.unit
def test_get_fundamentals_snapshot_routes_through_fundamental_data_config(monkeypatch):
    calls = []

    def fake_fundamentals(ticker: str, as_of: str) -> FundamentalsSnapshot:
        calls.append((ticker, as_of))
        return FundamentalsSnapshot(
            ticker=ticker,
            as_of=as_of,
            market_cap=3_000_000_000_000,
            pe_ratio_trailing=28.5,
        )

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_fundamentals_snapshot"],
        "fake_fundamentals",
        fake_fundamentals,
    )
    config_module.set_config({"data_vendors": {"fundamental_data": "fake_fundamentals"}})

    result = structured.get_fundamentals_snapshot("AAPL", "2026-05-16")

    assert isinstance(result, FundamentalsSnapshot)
    assert result.market_cap == 3_000_000_000_000
    assert calls == [("AAPL", "2026-05-16")]


@pytest.mark.unit
def test_get_indicator_series_routes_through_technical_indicators_config(monkeypatch):
    calls = []

    def fake_indicator(ticker: str, indicator: str, as_of: str, window: int) -> IndicatorSeries:
        calls.append((ticker, indicator, as_of, window))
        return IndicatorSeries(
            ticker=ticker,
            indicator=indicator,
            as_of=as_of,
            window=window,
            values=pd.DataFrame({"Date": ["2026-05-15"], "RSI": [62.3]}),
            latest_value=62.3,
        )

    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_indicator_series"],
        "fake_indicators",
        fake_indicator,
    )
    config_module.set_config({"data_vendors": {"technical_indicators": "fake_indicators"}})

    result = structured.get_indicator_series("AAPL", "rsi", "2026-05-16", 14)

    assert isinstance(result, IndicatorSeries)
    assert result.latest_value == 62.3
    assert calls == [("AAPL", "rsi", "2026-05-16", 14)]


@pytest.mark.unit
def test_structured_dispatch_rejects_unknown_methods():
    with pytest.raises(ValueError, match="Structured method 'not_real' not supported"):
        structured.route_structured_method("not_real")
