import copy

import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from massive_fakes import FakeMassiveResponse, FakeMassiveSession, load_massive_fixture
from tradingagents.dataflows import structured
from tradingagents.dataflows.exceptions import ProviderNoDataError, ProviderUnavailableError
from tradingagents.dataflows.massive import MASSIVE_API_KEY_ENV, get_massive_ticker_details
from tradingagents.dataflows.structured import AvailabilityStatus, TickerDetails


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


@pytest.mark.unit
def test_get_massive_ticker_details_parses_reference_payload(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeMassiveSession(FakeMassiveResponse(load_massive_fixture("ticker_details_success.json")))

    result = get_massive_ticker_details("aapl", "2026-05-16", session=session)

    assert isinstance(result, TickerDetails)
    assert result.ticker == "AAPL"
    assert result.as_of == "2026-05-16"
    assert result.name == "Apple Inc."
    assert result.market == "stocks"
    assert result.exchange == "XNAS"
    assert result.currency == "usd"
    assert result.locale == "us"
    assert result.active is True
    assert result.availability == []
    assert session.calls[0]["params"]["date"] == "2026-05-16"
    assert session.calls[0]["params"]["apiKey"] == "test-key"


@pytest.mark.unit
def test_structured_get_ticker_details_routes_to_massive(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    session = FakeMassiveSession(FakeMassiveResponse(load_massive_fixture("ticker_details_success.json")))
    monkeypatch.setattr("tradingagents.dataflows.massive.requests.Session", lambda: session)
    config_module.set_config({"data_vendors": {"core_stock_apis": "massive"}})

    result = structured.get_ticker_details("AAPL", "2026-05-16")

    assert result.ticker == "AAPL"
    assert result.name == "Apple Inc."
    assert result.active is True
    assert session.calls[0]["params"]["date"] == "2026-05-16"
    assert session.calls[0]["params"]["apiKey"] == "test-key"


@pytest.mark.unit
def test_get_massive_ticker_details_records_missing_fields(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeMassiveSession(FakeMassiveResponse(load_massive_fixture("ticker_details_missing_fields.json")))

    result = get_massive_ticker_details("AAPL", "2026-05-16", session=session)

    assert result.ticker == "AAPL"
    assert result.active is None
    assert {record.field for record in result.availability} == {
        "name",
        "market",
        "exchange",
        "currency",
        "locale",
        "active",
    }
    assert {record.status for record in result.availability} == {AvailabilityStatus.MISSING}
    assert {record.provider for record in result.availability} == {"massive"}


@pytest.mark.unit
def test_get_massive_ticker_details_raises_no_data_for_missing_results(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeMassiveSession(FakeMassiveResponse({"results": None}))

    with pytest.raises(ProviderNoDataError) as exc_info:
        get_massive_ticker_details("AAPL", "2026-05-16", session=session)

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_ticker_details"


@pytest.mark.unit
def test_get_massive_ticker_details_maps_malformed_payload(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeMassiveSession(FakeMassiveResponse([]))

    with pytest.raises(ProviderUnavailableError) as exc_info:
        get_massive_ticker_details("AAPL", "2026-05-16", session=session)

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_ticker_details"
