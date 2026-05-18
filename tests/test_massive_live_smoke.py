import copy
import os

import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as config_module
from tradingagents.dataflows import structured
from tradingagents.dataflows.massive import MASSIVE_API_KEY_ENV

RUN_FLAG_ENV = "RUN_MASSIVE_LIVE_SMOKE"


def _massive_live_smoke_enabled() -> bool:
    key = os.environ.get(MASSIVE_API_KEY_ENV, "").strip()
    return (
        os.environ.get(RUN_FLAG_ENV) == "1"
        and bool(key)
        and key not in {"placeholder", "..."}
    )


@pytest.mark.unit
def test_massive_live_smoke_disabled_without_flag(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "real-looking-key")
    monkeypatch.delenv(RUN_FLAG_ENV, raising=False)

    assert _massive_live_smoke_enabled() is False


@pytest.mark.unit
def test_massive_live_smoke_disabled_without_real_key(monkeypatch):
    monkeypatch.setenv(RUN_FLAG_ENV, "1")
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "placeholder")

    assert _massive_live_smoke_enabled() is False


@pytest.mark.unit
def test_massive_live_smoke_disabled_with_blank_key(monkeypatch):
    monkeypatch.setenv(RUN_FLAG_ENV, "1")
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, " ")

    assert _massive_live_smoke_enabled() is False


@pytest.mark.unit
def test_massive_live_smoke_disabled_with_ellipsis_placeholder(monkeypatch):
    monkeypatch.setenv(RUN_FLAG_ENV, "1")
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "...")

    assert _massive_live_smoke_enabled() is False


@pytest.mark.integration
@pytest.mark.smoke
@pytest.mark.skipif(
    not _massive_live_smoke_enabled(),
    reason="Set RUN_MASSIVE_LIVE_SMOKE=1 and MASSIVE_API_KEY to run the Massive live smoke check",
)
def test_massive_live_price_history_smoke(monkeypatch):
    monkeypatch.setattr(config_module, "_config", copy.deepcopy(default_config.DEFAULT_CONFIG))
    config = default_config.DEFAULT_CONFIG.copy()
    config["data_vendors"] = {
        **default_config.DEFAULT_CONFIG["data_vendors"],
        "core_stock_apis": "massive",
    }
    config_module.set_config(config)

    result = structured.get_price_history("AAPL", "2026-01-02", "2026-01-05")

    assert result.ticker == "AAPL"
    assert not result.data.empty
    assert result.data["Date"].max() <= "2026-01-05"
