import copy

import pandas as pd
import pytest
import requests

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from tradingagents.dataflows import structured
from tradingagents.dataflows.exceptions import (
    DataProviderError,
    ProviderAuthError,
    ProviderNoDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from tradingagents.dataflows.massive import MASSIVE_API_KEY_ENV, get_massive_price_history
from tradingagents.dataflows.structured import PRICE_HISTORY_COLUMNS, PriceHistory


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.response


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


@pytest.mark.unit
def test_get_massive_price_history_parses_daily_aggregates(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(
        FakeResponse(
            {
                "ticker": "AAPL",
                "results": [
                    {"t": 1778803200000, "o": 100.0, "h": 105.0, "l": 99.0, "c": 104.0, "v": 1234567},
                    {"t": 1778889600000, "o": 104.0, "h": 110.0, "l": 103.0, "c": 108.0, "v": 2234567},
                ],
            }
        )
    )

    result = get_massive_price_history("aapl", "2026-05-15", "2026-05-16", session=session)

    assert isinstance(result, PriceHistory)
    assert result.ticker == "AAPL"
    assert result.start == "2026-05-15"
    assert result.end == "2026-05-16"
    assert tuple(result.data.columns) == PRICE_HISTORY_COLUMNS
    assert result.data.to_dict("records") == [
        {"Date": "2026-05-15", "Open": 100.0, "High": 105.0, "Low": 99.0, "Close": 104.0, "Volume": 1234567},
        {"Date": "2026-05-16", "Open": 104.0, "High": 110.0, "Low": 103.0, "Close": 108.0, "Volume": 2234567},
    ]
    assert session.calls[0]["params"]["apiKey"] == "test-key"


@pytest.mark.unit
def test_massive_price_history_is_registered_for_structured_routing(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(
        FakeResponse(
            {
                "ticker": "AAPL",
                "results": [{"t": 1778803200000, "o": 1, "h": 2, "l": 1, "c": 2, "v": 10}],
            }
        )
    )
    monkeypatch.setattr("tradingagents.dataflows.massive.requests.Session", lambda: session)
    config_module.set_config({"data_vendors": {"core_stock_apis": "massive"}})

    result = structured.get_price_history("AAPL", "2026-05-15", "2026-05-16")

    assert result.ticker == "AAPL"
    assert result.data["Date"].tolist() == ["2026-05-15"]


@pytest.mark.unit
def test_massive_price_history_is_not_implicit_fallback(monkeypatch):
    class ExplodingSession:
        def get(self, url, params=None, timeout=None):
            raise AssertionError("Massive should only run when explicitly configured")

    def failing_provider(ticker: str, start: str, end: str) -> PriceHistory:
        raise DataProviderError(
            "primary failed",
            provider="primary_prices",
            method="get_price_history",
        )

    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    monkeypatch.setattr("tradingagents.dataflows.massive.requests.Session", lambda: ExplodingSession())
    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "primary_prices",
        failing_provider,
    )
    config_module.set_config({"data_vendors": {"core_stock_apis": "primary_prices"}})

    with pytest.raises(RuntimeError, match="No available structured provider for 'get_price_history'"):
        structured.get_price_history("AAPL", "2026-05-15", "2026-05-16")


@pytest.mark.unit
def test_massive_price_history_raises_no_data_for_empty_results(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(FakeResponse({"ticker": "AAPL", "results": []}))

    with pytest.raises(ProviderNoDataError) as exc_info:
        get_massive_price_history("AAPL", "2026-05-15", "2026-05-16", session=session)

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_price_history"


@pytest.mark.unit
def test_structured_massive_price_history_preserves_provider_error(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(FakeResponse({"ticker": "AAPL", "results": []}))
    monkeypatch.setattr("tradingagents.dataflows.massive.requests.Session", lambda: session)
    config_module.set_config({"data_vendors": {"core_stock_apis": "massive"}})

    with pytest.raises(ProviderNoDataError) as exc_info:
        structured.get_price_history("AAPL", "2026-05-15", "2026-05-16")

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_price_history"


@pytest.mark.unit
def test_structured_massive_price_history_error_is_not_masked_by_configured_fallback(monkeypatch):
    fallback_calls = []

    def fallback_provider(ticker: str, start: str, end: str) -> PriceHistory:
        fallback_calls.append((ticker, start, end))
        return PriceHistory(
            ticker=ticker,
            start=start,
            end=end,
            data=pd.DataFrame({"Date": ["2026-05-15"], "Close": [104.0]}),
        )

    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(FakeResponse({"ticker": "AAPL", "results": []}))
    monkeypatch.setattr("tradingagents.dataflows.massive.requests.Session", lambda: session)
    monkeypatch.setitem(
        structured.STRUCTURED_VENDOR_METHODS["get_price_history"],
        "fallback_prices",
        fallback_provider,
    )
    config_module.set_config({"data_vendors": {"core_stock_apis": "massive,fallback_prices"}})

    with pytest.raises(ProviderNoDataError) as exc_info:
        structured.get_price_history("AAPL", "2026-05-15", "2026-05-16")

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_price_history"
    assert fallback_calls == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderRateLimitError),
        (500, ProviderUnavailableError),
    ],
)
def test_massive_price_history_maps_http_errors(monkeypatch, status_code, expected_error):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(FakeResponse({"error": "failed"}, status_code=status_code, headers={"Retry-After": "30"}))

    with pytest.raises(expected_error) as exc_info:
        get_massive_price_history("AAPL", "2026-05-15", "2026-05-16", session=session)

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_price_history"
    assert "test-key" not in str(exc_info.value)


@pytest.mark.unit
def test_massive_price_history_maps_timeout(monkeypatch):
    class TimeoutSession:
        def get(self, url, params=None, timeout=None):
            raise requests.Timeout("request timed out")

    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")

    with pytest.raises(ProviderUnavailableError):
        get_massive_price_history("AAPL", "2026-05-15", "2026-05-16", session=TimeoutSession())


@pytest.mark.unit
def test_massive_price_history_maps_transport_errors(monkeypatch):
    class ConnectionErrorSession:
        def get(self, url, params=None, timeout=None):
            raise requests.ConnectionError("connection failed")

    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")

    with pytest.raises(ProviderUnavailableError) as exc_info:
        get_massive_price_history("AAPL", "2026-05-15", "2026-05-16", session=ConnectionErrorSession())

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_price_history"


@pytest.mark.unit
def test_massive_price_history_maps_malformed_rows(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeSession(FakeResponse({"ticker": "AAPL", "results": [{"t": 1778803200000, "o": 1}]}))

    with pytest.raises(ProviderUnavailableError) as exc_info:
        get_massive_price_history("AAPL", "2026-05-15", "2026-05-16", session=session)

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_price_history"
