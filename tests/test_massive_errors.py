import traceback

import pytest
import requests

from tradingagents.dataflows.exceptions import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from tradingagents.dataflows.massive import MASSIVE_API_KEY_ENV, request_massive_json


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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderRateLimitError),
        (500, ProviderUnavailableError),
        (503, ProviderUnavailableError),
        (418, ProviderUnavailableError),
    ],
)
def test_request_massive_json_maps_http_statuses(monkeypatch, status_code, expected_error):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "secret-test-key")
    session = FakeSession(FakeResponse({"error": "failed"}, status_code=status_code, headers={"Retry-After": "45"}))

    with pytest.raises(expected_error) as exc_info:
        request_massive_json("/v3/test", {"ticker": "AAPL"}, method="test_method", session=session)

    error = exc_info.value
    assert error.provider == "massive"
    assert error.method == "test_method"
    assert error.status_code == status_code
    assert "secret-test-key" not in str(error)
    assert "apiKey" not in error.details


@pytest.mark.unit
def test_request_massive_json_preserves_retry_after(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "secret-test-key")
    session = FakeSession(FakeResponse({"error": "limited"}, status_code=429, headers={"Retry-After": "45"}))

    with pytest.raises(ProviderRateLimitError) as exc_info:
        request_massive_json("/v3/test", {"ticker": "AAPL"}, method="test_method", session=session)

    assert exc_info.value.retry_after == 45
    assert exc_info.value.details["retry_after"] == 45


class TimeoutSession:
    def get(self, url, params=None, timeout=None):
        raise requests.Timeout("timed out with secret-test-key")


class ConnectionErrorSession:
    def get(self, url, params=None, timeout=None):
        raise requests.ConnectionError("connection failed with secret-test-key")


class MalformedJsonResponse(FakeResponse):
    def json(self):
        raise ValueError("not JSON with secret-test-key")


@pytest.mark.unit
@pytest.mark.parametrize(
    "session",
    [
        pytest.param(TimeoutSession(), id="timeout"),
        pytest.param(ConnectionErrorSession(), id="connection-error"),
        pytest.param(FakeSession(MalformedJsonResponse("<html>no json</html>")), id="malformed-json"),
    ],
)
def test_request_massive_json_redacts_low_level_error_tracebacks(monkeypatch, session):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "secret-test-key")

    with pytest.raises(ProviderUnavailableError) as exc_info:
        request_massive_json("/v3/test", {"ticker": "AAPL"}, method="test_method", session=session)

    traceback_text = "".join(traceback.format_exception(exc_info.value))
    assert "secret-test-key" not in traceback_text
    assert "apiKey" not in exc_info.value.details


@pytest.mark.unit
@pytest.mark.parametrize(
    "session",
    [
        pytest.param(TimeoutSession(), id="timeout"),
        pytest.param(ConnectionErrorSession(), id="connection-error"),
    ],
)
def test_request_massive_json_maps_transport_errors(monkeypatch, session):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "secret-test-key")

    with pytest.raises(ProviderUnavailableError) as exc_info:
        request_massive_json("/v3/test", {"ticker": "AAPL"}, method="test_method", session=session)

    error = exc_info.value
    assert error.provider == "massive"
    assert "secret-test-key" not in str(error)
    assert "apiKey" not in error.details


@pytest.mark.unit
def test_request_massive_json_maps_malformed_json(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "secret-test-key")
    session = FakeSession(MalformedJsonResponse("<html>no json</html>"))

    with pytest.raises(ProviderUnavailableError) as exc_info:
        request_massive_json("/v3/test", {"ticker": "AAPL"}, method="test_method", session=session)

    error = exc_info.value
    assert error.provider == "massive"
    assert "not valid JSON" in str(error)
    assert "secret-test-key" not in str(error)
    assert "apiKey" not in error.details


@pytest.mark.unit
def test_request_massive_json_maps_non_object_json(monkeypatch):
    monkeypatch.setenv(MASSIVE_API_KEY_ENV, "secret-test-key")
    session = FakeSession(FakeResponse(["not", "an", "object"]))

    with pytest.raises(ProviderUnavailableError) as exc_info:
        request_massive_json("/v3/test", {"ticker": "AAPL"}, method="test_method", session=session)

    error = exc_info.value
    assert error.provider == "massive"
    assert "not an object" in str(error)
    assert "secret-test-key" not in str(error)
    assert "apiKey" not in error.details
