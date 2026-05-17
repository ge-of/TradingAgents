import copy

import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from tradingagents.dataflows.exceptions import ProviderAuthError
from tradingagents.dataflows.massive import MASSIVE_API_KEY_ENV, get_massive_api_key


@pytest.fixture(autouse=True)
def reset_dataflows_config(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))


@pytest.mark.unit
def test_get_massive_api_key_returns_configured_key(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "massive-test-key")

    assert get_massive_api_key() == "massive-test-key"


@pytest.mark.unit
def test_get_massive_api_key_raises_provider_auth_error_when_missing(monkeypatch):
    monkeypatch.delenv(MASSIVE_API_KEY_ENV, raising=False)

    with pytest.raises(ProviderAuthError) as exc_info:
        get_massive_api_key()

    error = exc_info.value
    assert error.provider == "massive"
    assert error.method == "credential_detection"
    assert error.retryable is False
    assert MASSIVE_API_KEY_ENV in error.message


@pytest.mark.unit
def test_polygon_alias_normalizes_to_massive_in_data_vendors():
    config_module.set_config({"data_vendors": {"core_stock_apis": "polygon"}})

    assert config_module.get_config()["data_vendors"]["core_stock_apis"] == "massive"


@pytest.mark.unit
def test_polygon_alias_normalizes_inside_comma_separated_fallback_chain():
    config_module.set_config({"data_vendors": {"core_stock_apis": "polygon, yfinance"}})

    assert config_module.get_config()["data_vendors"]["core_stock_apis"] == "massive,yfinance"


@pytest.mark.unit
def test_polygon_alias_normalizes_to_massive_in_tool_vendors():
    config_module.set_config({"tool_vendors": {"get_price_history": "polygon"}})

    assert config_module.get_config()["tool_vendors"]["get_price_history"] == "massive"
