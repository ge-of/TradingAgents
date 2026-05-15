import pytest

from tradingagents.dataflows.exceptions import (
    DataProviderError,
    ProviderAuthError,
    ProviderNoDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)


@pytest.mark.unit
def test_data_provider_error_exposes_diagnostic_metadata():
    error = DataProviderError(
        "request failed",
        provider="massive",
        method="get_stock_data",
        retryable=True,
        status_code=502,
        details={"ticker": "AAPL"},
    )

    assert error.message == "request failed"
    assert error.provider == "massive"
    assert error.method == "get_stock_data"
    assert error.retryable is True
    assert error.status_code == 502
    assert error.details == {"ticker": "AAPL"}
    assert str(error) == (
        "request failed "
        "[provider=massive method=get_stock_data status_code=502 retryable=True]"
    )


@pytest.mark.unit
def test_data_provider_error_copies_details_mapping():
    details = {"ticker": "MSFT"}
    error = DataProviderError("request failed", details=details)

    details["ticker"] = "AAPL"

    assert error.details == {"ticker": "MSFT"}


@pytest.mark.unit
def test_provider_auth_error_is_not_retryable_by_default():
    error = ProviderAuthError("missing API key", provider="massive")

    assert isinstance(error, DataProviderError)
    assert error.retryable is False
    assert error.provider == "massive"


@pytest.mark.unit
def test_provider_rate_limit_error_is_retryable_and_tracks_retry_after():
    error = ProviderRateLimitError(
        "rate limited",
        provider="alpha_vantage",
        method="get_news",
        retry_after=60,
    )

    assert isinstance(error, DataProviderError)
    assert error.retryable is True
    assert error.retry_after == 60
    assert error.details == {"retry_after": 60}


@pytest.mark.unit
def test_provider_unavailable_error_is_retryable_by_default():
    error = ProviderUnavailableError(
        "upstream timeout",
        provider="yfinance",
        method="get_stock_data",
        status_code=503,
    )

    assert error.retryable is True
    assert error.status_code == 503


@pytest.mark.unit
def test_provider_no_data_error_is_not_retryable_by_default():
    error = ProviderNoDataError(
        "no price bars found",
        provider="massive",
        method="get_stock_data",
    )

    assert isinstance(error, DataProviderError)
    assert error.retryable is False


from tradingagents.dataflows.alpha_vantage_common import AlphaVantageRateLimitError


@pytest.mark.unit
def test_alpha_vantage_rate_limit_error_uses_shared_rate_limit_contract():
    error = AlphaVantageRateLimitError("Alpha Vantage rate limit exceeded")

    assert isinstance(error, ProviderRateLimitError)
    assert isinstance(error, DataProviderError)
    assert error.provider == "alpha_vantage"
    assert error.retryable is True
    assert str(error) == (
        "Alpha Vantage rate limit exceeded "
        "[provider=alpha_vantage retryable=True]"
    )
