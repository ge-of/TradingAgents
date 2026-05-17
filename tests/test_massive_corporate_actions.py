import copy

import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from tradingagents.dataflows import structured
from tradingagents.dataflows.exceptions import ProviderUnavailableError
from tradingagents.dataflows.massive import MASSIVE_API_KEY_ENV, get_massive_corporate_actions
from tradingagents.dataflows.structured import CorporateActions


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = str(payload)

    def json(self):
        return self._payload


class SequenceSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


@pytest.mark.unit
def test_get_massive_corporate_actions_parses_dividends_and_splits(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = SequenceSession(
        [
            FakeResponse(
                {
                    "results": [
                        {
                            "ticker": "AAPL",
                            "ex_dividend_date": "2026-05-10",
                            "pay_date": "2026-05-20",
                            "cash_amount": 0.26,
                            "currency": "usd",
                        }
                    ]
                }
            ),
            FakeResponse(
                {
                    "results": [
                        {
                            "ticker": "AAPL",
                            "execution_date": "2026-05-12",
                            "split_from": 1,
                            "split_to": 4,
                        }
                    ]
                }
            ),
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
    session = SequenceSession([FakeResponse({"results": []}), FakeResponse({"results": []})])

    result = get_massive_corporate_actions("AAPL", "2026-05-01", "2026-05-31", session=session)

    assert result.dividends == []
    assert result.splits == []


@pytest.mark.unit
def test_get_massive_corporate_actions_redacts_key_from_http_errors(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = SequenceSession([FakeResponse({"error": "failed"}, status_code=500)])

    with pytest.raises(ProviderUnavailableError) as exc_info:
        get_massive_corporate_actions("AAPL", "2026-05-01", "2026-05-31", session=session)

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_corporate_actions"
    assert "test-key" not in str(exc_info.value)


@pytest.mark.unit
def test_get_massive_corporate_actions_maps_malformed_rows(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = SequenceSession([FakeResponse({"results": [None]}), FakeResponse({"results": []})])

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
            FakeResponse({"results": [{"ticker": "AAPL", "cash_amount": 0.26}]}),
            FakeResponse({"results": []}),
        ],
        [
            FakeResponse({"results": []}),
            FakeResponse({"results": [{"ticker": "AAPL", "split_from": 1, "split_to": 4}]}),
        ],
    ],
    ids=["missing-ex-dividend-date", "missing-split-execution-date"],
)
def test_get_massive_corporate_actions_rejects_missing_required_event_dates(monkeypatch, responses):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = SequenceSession(responses)

    with pytest.raises(ProviderUnavailableError) as exc_info:
        get_massive_corporate_actions("AAPL", "2026-05-01", "2026-05-31", session=session)

    assert exc_info.value.provider == "massive"
    assert exc_info.value.method == "get_corporate_actions"
    assert "test-key" not in str(exc_info.value)


@pytest.mark.unit
def test_structured_get_corporate_actions_routes_to_massive(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "test-key")
    session = SequenceSession([FakeResponse({"results": []}), FakeResponse({"results": []})])
    monkeypatch.setattr("tradingagents.dataflows.massive.requests.Session", lambda: session)
    config_module.set_config({"data_vendors": {"core_stock_apis": "massive"}})

    result = structured.get_corporate_actions("AAPL", "2026-05-01", "2026-05-31")

    assert result.ticker == "AAPL"
    assert result.dividends == []
    assert result.splits == []
    assert len(session.calls) == 2
