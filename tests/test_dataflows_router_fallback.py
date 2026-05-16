import copy

import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows import interface
from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.exceptions import DataProviderError, ProviderUnavailableError


@pytest.fixture(autouse=True)
def reset_dataflows_config():
    set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))
    yield
    set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))


@pytest.mark.unit
def test_route_to_vendor_falls_back_after_data_provider_error(monkeypatch):
    calls = []

    def failing_primary(*args, **kwargs):
        calls.append(("alpha_vantage", args, kwargs))
        raise DataProviderError(
            "primary provider failed",
            provider="alpha_vantage",
            method="get_stock_data",
            retryable=True,
        )

    def fallback_provider(*args, **kwargs):
        calls.append(("yfinance", args, kwargs))
        return "fallback stock data"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "alpha_vantage": failing_primary,
            "yfinance": fallback_provider,
        },
    )
    set_config({"data_vendors": {"core_stock_apis": "alpha_vantage"}})

    result = interface.route_to_vendor(
        "get_stock_data",
        "AAPL",
        "2026-05-01",
        "2026-05-02",
    )

    assert result == "fallback stock data"
    assert [call[0] for call in calls] == ["alpha_vantage", "yfinance"]
    assert calls[0][1] == ("AAPL", "2026-05-01", "2026-05-02")


@pytest.mark.unit
def test_route_to_vendor_preserves_alpha_vantage_rate_limit_fallback(monkeypatch):
    calls = []

    def rate_limited_primary(*args, **kwargs):
        calls.append("alpha_vantage")
        raise AlphaVantageRateLimitError("Alpha Vantage rate limit exceeded")

    def fallback_provider(*args, **kwargs):
        calls.append("yfinance")
        return "fallback after rate limit"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "alpha_vantage": rate_limited_primary,
            "yfinance": fallback_provider,
        },
    )
    set_config({"data_vendors": {"core_stock_apis": "alpha_vantage"}})

    result = interface.route_to_vendor(
        "get_stock_data",
        "MSFT",
        "2026-05-01",
        "2026-05-02",
    )

    assert result == "fallback after rate limit"
    assert calls == ["alpha_vantage", "yfinance"]


@pytest.mark.unit
def test_route_to_vendor_raises_runtime_error_when_all_providers_fail(monkeypatch):
    calls = []

    def failing_alpha(*args, **kwargs):
        calls.append("alpha_vantage")
        raise DataProviderError(
            "alpha failed",
            provider="alpha_vantage",
            method="get_stock_data",
        )

    def failing_yfinance(*args, **kwargs):
        calls.append("yfinance")
        raise ProviderUnavailableError(
            "yfinance unavailable",
            provider="yfinance",
            method="get_stock_data",
        )

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "alpha_vantage": failing_alpha,
            "yfinance": failing_yfinance,
        },
    )
    set_config({"data_vendors": {"core_stock_apis": "alpha_vantage"}})

    with pytest.raises(RuntimeError, match="No available vendor for 'get_stock_data'"):
        interface.route_to_vendor(
            "get_stock_data",
            "NVDA",
            "2026-05-01",
            "2026-05-02",
        )

    assert calls == ["alpha_vantage", "yfinance"]
