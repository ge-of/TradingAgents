import copy

import pandas as pd
import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from tradingagents.dataflows import structured
from tradingagents.dataflows.exceptions import ProviderNoDataError
from tradingagents.dataflows.structured import FundamentalsSnapshot, IndicatorSeries, PriceHistory


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


def register_structured_provider(monkeypatch, method: str, vendor: str, provider):
    monkeypatch.setitem(structured.STRUCTURED_VENDOR_METHODS[method], vendor, provider)
    category = structured.STRUCTURED_METHOD_CATEGORIES[method]
    config_module.set_config({"data_vendors": {category: vendor}})


@pytest.mark.unit
def test_price_history_treats_end_as_as_of_and_filters_future_rows(monkeypatch):
    calls = []

    def fake_price_history(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append((ticker, start, end))
        return PriceHistory(
            ticker=ticker,
            start=start,
            end=end,
            data=pd.DataFrame(
                {
                    "Date": ["2026-05-15", "2026-05-16", "2026-05-17"],
                    "Open": [100.0, 105.0, 200.0],
                    "High": [106.0, 110.0, 250.0],
                    "Low": [99.0, 104.0, 190.0],
                    "Close": [105.0, 108.0, 240.0],
                    "Volume": [1_000_000, 1_100_000, 9_999_999],
                }
            ),
            high_52w=250.0,
            low_52w=99.0,
            proximity_to_52w_high=-0.04,
        )

    register_structured_provider(monkeypatch, "get_price_history", "fake_prices", fake_price_history)

    result = structured.get_price_history("AAPL", "2026-05-15", "2026-05-16")

    assert calls == [("AAPL", "2026-05-15", "2026-05-16")]
    assert result.start == "2026-05-15"
    assert result.end == "2026-05-16"
    assert result.data["Date"].tolist() == ["2026-05-15", "2026-05-16"]
    assert result.high_52w == 110.0
    assert result.low_52w == 99.0
    assert result.proximity_to_52w_high == pytest.approx((108.0 / 110.0) - 1)


@pytest.mark.unit
def test_price_history_sorts_filtered_rows_by_date_before_derived_metrics(monkeypatch):
    def fake_price_history(ticker: str, start: str, end: str) -> PriceHistory:
        return PriceHistory(
            ticker=ticker,
            start=start,
            end=end,
            data=pd.DataFrame(
                {
                    "Date": ["2026-05-17", "2026-05-16", "2026-05-15"],
                    "Open": [200.0, 105.0, 100.0],
                    "High": [250.0, 110.0, 106.0],
                    "Low": [190.0, 104.0, 99.0],
                    "Close": [240.0, 108.0, 105.0],
                    "Volume": [9_999_999, 1_100_000, 1_000_000],
                }
            ),
        )

    register_structured_provider(monkeypatch, "get_price_history", "fake_prices", fake_price_history)

    result = structured.get_price_history("AAPL", "2026-05-15", "2026-05-16")

    assert result.data["Date"].tolist() == ["2026-05-15", "2026-05-16"]
    assert result.proximity_to_52w_high == pytest.approx((108.0 / 110.0) - 1)


@pytest.mark.unit
def test_fundamentals_snapshot_rejects_provider_snapshot_after_as_of(monkeypatch):
    def fake_fundamentals(ticker: str, as_of: str) -> FundamentalsSnapshot:
        return FundamentalsSnapshot(
            ticker=ticker,
            as_of="2026-05-17",
            market_cap=3_000_000_000_000,
            pe_ratio_trailing=28.5,
        )

    register_structured_provider(
        monkeypatch,
        "get_fundamentals_snapshot",
        "fake_fundamentals",
        fake_fundamentals,
    )

    with pytest.raises(ProviderNoDataError) as exc_info:
        structured.get_fundamentals_snapshot("AAPL", "2026-05-16")

    assert exc_info.value.method == "get_fundamentals_snapshot"
    assert exc_info.value.details == {
        "ticker": "AAPL",
        "as_of": "2026-05-16",
        "snapshot_as_of": "2026-05-17",
    }


@pytest.mark.unit
def test_indicator_series_filters_after_as_of_and_recomputes_latest_value(monkeypatch):
    def fake_indicator(ticker: str, indicator: str, as_of: str, window: int) -> IndicatorSeries:
        return IndicatorSeries(
            ticker=ticker,
            indicator=indicator,
            as_of=as_of,
            window=window,
            values=pd.DataFrame(
                {
                    "Date": ["2026-05-15", "2026-05-16", "2026-05-17"],
                    "RSI": [62.3, 64.0, 99.0],
                }
            ),
            latest_value=99.0,
        )

    register_structured_provider(monkeypatch, "get_indicator_series", "fake_indicators", fake_indicator)

    result = structured.get_indicator_series("AAPL", "rsi", "2026-05-16", 14)

    assert result.values["Date"].tolist() == ["2026-05-15", "2026-05-16"]
    assert result.latest_value == 64.0


@pytest.mark.unit
def test_indicator_series_sorts_filtered_rows_by_date_before_latest_value(monkeypatch):
    def fake_indicator(ticker: str, indicator: str, as_of: str, window: int) -> IndicatorSeries:
        return IndicatorSeries(
            ticker=ticker,
            indicator=indicator,
            as_of=as_of,
            window=window,
            values=pd.DataFrame(
                {
                    "Date": ["2026-05-17", "2026-05-16", "2026-05-15"],
                    "RSI": [99.0, 64.0, 62.3],
                }
            ),
            latest_value=99.0,
        )

    register_structured_provider(monkeypatch, "get_indicator_series", "fake_indicators", fake_indicator)

    result = structured.get_indicator_series("AAPL", "rsi", "2026-05-16", 14)

    assert result.values["Date"].tolist() == ["2026-05-15", "2026-05-16"]
    assert result.latest_value == 64.0


@pytest.mark.unit
def test_required_dated_data_raises_provider_no_data_when_missing_or_filtered(monkeypatch):
    def price_history_missing_date(ticker: str, start: str, end: str) -> PriceHistory:
        return PriceHistory(
            ticker=ticker,
            start=start,
            end=end,
            data=pd.DataFrame({"Close": [108.0]}),
        )

    def indicator_all_future(ticker: str, indicator: str, as_of: str, window: int) -> IndicatorSeries:
        return IndicatorSeries(
            ticker=ticker,
            indicator=indicator,
            as_of=as_of,
            window=window,
            values=pd.DataFrame({"Date": ["2026-05-17"], "RSI": [99.0]}),
            latest_value=99.0,
        )

    register_structured_provider(monkeypatch, "get_price_history", "fake_prices", price_history_missing_date)
    register_structured_provider(monkeypatch, "get_indicator_series", "fake_indicators", indicator_all_future)

    with pytest.raises(ProviderNoDataError) as price_exc:
        structured.get_price_history("AAPL", "2026-05-15", "2026-05-16")

    assert price_exc.value.method == "get_price_history"
    assert price_exc.value.details == {"ticker": "AAPL", "reason": "missing_date_column"}

    with pytest.raises(ProviderNoDataError) as indicator_exc:
        structured.get_indicator_series("AAPL", "rsi", "2026-05-16", 14)

    assert indicator_exc.value.method == "get_indicator_series"
    assert indicator_exc.value.details == {"ticker": "AAPL", "end": "2026-05-16"}


@pytest.mark.unit
def test_invalid_price_history_dates_fail_before_provider_call(monkeypatch):
    calls = []

    def should_not_run(ticker: str, start: str, end: str) -> PriceHistory:
        calls.append((ticker, start, end))
        return PriceHistory(ticker=ticker, start=start, end=end, data=pd.DataFrame())

    register_structured_provider(monkeypatch, "get_price_history", "fake_prices", should_not_run)

    with pytest.raises(ValueError, match="start must be a YYYY-MM-DD date"):
        structured.get_price_history("AAPL", "2026/05/15", "2026-05-16")

    with pytest.raises(ValueError, match="start must be on or before end"):
        structured.get_price_history("AAPL", "2026-05-17", "2026-05-16")

    assert calls == []


@pytest.mark.unit
def test_invalid_as_of_dates_fail_before_provider_call(monkeypatch):
    calls = []

    def should_not_run_fundamentals(ticker: str, as_of: str) -> FundamentalsSnapshot:
        calls.append(("fundamentals", ticker, as_of))
        return FundamentalsSnapshot(ticker=ticker, as_of=as_of)

    def should_not_run_indicator(
        ticker: str,
        indicator: str,
        as_of: str,
        window: int,
    ) -> IndicatorSeries:
        calls.append(("indicator", ticker, indicator, as_of, window))
        return IndicatorSeries(
            ticker=ticker,
            indicator=indicator,
            as_of=as_of,
            window=window,
            values=pd.DataFrame(),
        )

    register_structured_provider(
        monkeypatch,
        "get_fundamentals_snapshot",
        "fake_fundamentals",
        should_not_run_fundamentals,
    )
    register_structured_provider(monkeypatch, "get_indicator_series", "fake_indicators", should_not_run_indicator)

    with pytest.raises(ValueError, match="as_of must be a YYYY-MM-DD date"):
        structured.get_fundamentals_snapshot("AAPL", "2026-05-16T00:00:00")

    with pytest.raises(ValueError, match="as_of must be a YYYY-MM-DD date"):
        structured.get_indicator_series("AAPL", "rsi", "", 14)

    with pytest.raises(ValueError, match="window must be a positive integer"):
        structured.get_indicator_series("AAPL", "rsi", "2026-05-16", 0)

    assert calls == []
