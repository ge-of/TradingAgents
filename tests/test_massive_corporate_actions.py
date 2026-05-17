import copy

import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from massive_fakes import FakeMassiveResponse, FakeMassiveSession, load_massive_fixture
from tradingagents.dataflows import structured
from tradingagents.dataflows.exceptions import ProviderUnavailableError
from tradingagents.dataflows.massive import MASSIVE_API_KEY_ENV, get_massive_corporate_actions
from tradingagents.dataflows.structured import CorporateActions


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


@pytest.mark.unit
def test_get_massive_corporate_actions_parses_dividends_and_splits(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeMassiveSession(
        [
            FakeMassiveResponse(load_massive_fixture("dividends_success.json")),
            FakeMassiveResponse(load_massive_fixture("splits_success.json")),
        ]
    )

    result = get_massive_corporate_actions("aapl", "2026-05-01", "2026-05-31", session=session)

    assert isinstance(result, CorporateActions)
    assert result.ticker == "AAPL"
    assert result.start == "2026-05-01"
    assert result.end == "2026-05-31"
    assert result.dividends[0].cash_amount == 0.26
    assert result.dividends[0].currency == "usd"
    assert result.splits[0].split_from == 1.0
    assert result.splits[0].split_to == 4.0
    assert len(session.calls) == 2

    dividend_call, split_call = session.calls
    assert dividend_call["url"].endswith("/v3/reference/dividends")
    assert dividend_call["params"] == {
        "ticker": "AAPL",
        "ex_dividend_date.gte": "2026-05-01",
        "ex_dividend_date.lte": "2026-05-31",
        "apiKey": "test-key",
    }
    assert split_call["url"].endswith("/v3/reference/splits")
    assert split_call["params"] == {
        "ticker": "AAPL",
        "execution_date.gte": "2026-05-01",
        "execution_date.lte": "2026-05-31",
        "apiKey": "test-key",
    }


@pytest.mark.unit
def test_get_massive_corporate_actions_allows_empty_optional_collections(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeMassiveSession(
        [
            FakeMassiveResponse(load_massive_fixture("empty_results.json")),
            FakeMassiveResponse(load_massive_fixture("empty_results.json")),
        ]
    )

    result = get_massive_corporate_actions("AAPL", "2026-05-01", "2026-05-31", session=session)

    assert result.dividends == []
    assert result.splits == []


@pytest.mark.unit
def test_get_massive_corporate_actions_redacts_key_from_http_errors(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeMassiveSession([FakeMassiveResponse({"error": "failed"}, status_code=500)])

    with pytest.raises(ProviderUnavailableError) as exc_info:
        get_massive_corporate_actions("AAPL", "2026-05-01", "2026-05-31", session=session)

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_corporate_actions"
    assert "test-key" not in str(exc_info.value)


@pytest.mark.unit
def test_get_massive_corporate_actions_maps_malformed_rows(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeMassiveSession(
        [FakeMassiveResponse({"results": [None]}), FakeMassiveResponse(load_massive_fixture("empty_results.json"))]
    )

    with pytest.raises(ProviderUnavailableError) as exc_info:
        get_massive_corporate_actions("AAPL", "2026-05-01", "2026-05-31", session=session)

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_corporate_actions"
    assert "test-key" not in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "responses",
    [
        [
            FakeMassiveResponse({"results": [{"ticker": "AAPL", "cash_amount": 0.26}]}),
            FakeMassiveResponse({"results": []}),
        ],
        [
            FakeMassiveResponse({"results": []}),
            FakeMassiveResponse({"results": [{"ticker": "AAPL", "split_from": 1, "split_to": 4}]}),
        ],
    ],
    ids=["missing-ex-dividend-date", "missing-split-execution-date"],
)
def test_get_massive_corporate_actions_rejects_missing_required_event_dates(monkeypatch, responses):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeMassiveSession(responses)

    with pytest.raises(ProviderUnavailableError) as exc_info:
        get_massive_corporate_actions("AAPL", "2026-05-01", "2026-05-31", session=session)

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_corporate_actions"
    assert "test-key" not in str(exc_info.value)


@pytest.mark.unit
def test_structured_get_corporate_actions_routes_to_massive(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = FakeMassiveSession(
        [
            FakeMassiveResponse(load_massive_fixture("empty_results.json")),
            FakeMassiveResponse(load_massive_fixture("empty_results.json")),
        ]
    )
    monkeypatch.setattr("tradingagents.dataflows.massive.requests.Session", lambda: session)
    config_module.set_config({"data_vendors": {"core_stock_apis": "massive"}})

    result = structured.get_corporate_actions("AAPL", "2026-05-01", "2026-05-31")

    assert result.ticker == "AAPL"
    assert result.dividends == []
    assert result.splits == []
    assert len(session.calls) == 2
